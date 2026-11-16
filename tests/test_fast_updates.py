"""Cold startup, request cadence, shared refresh and local push boundaries."""
from datetime import datetime,timedelta
import http.client
import json
from threading import Event,Thread
from types import SimpleNamespace

import pytest

from src.app import launcher,server
from src.data import ssi_runtime as runtime, ssi_worker as worker
from src.data.ssi_feed import VN


@pytest.mark.parametrize('elapsed,expected',[(.3,9.7),(7,3),(15,0)])
def test_request_cadence_deducts_source_time(monkeypatch,elapsed,expected):
    monkeypatch.setattr(worker,'poll_delay',lambda settings:10)
    assert worker.remaining_poll_delay({},100,100+elapsed)==pytest.approx(expected)


@pytest.mark.parametrize('status',['fetching','starting','backoff'])
def test_page_open_never_queues_an_extra_request_while_busy_or_backing_off(monkeypatch,status):
    monkeypatch.setattr(runtime,'_thread',SimpleNamespace(is_alive=lambda:True))
    monkeypatch.setattr(runtime,'_stop',Event())
    monkeypatch.setattr(runtime,'_token','owned')
    monkeypatch.setattr(runtime,'_status_file',lambda:{'worker_token':'owned','status':status})
    monkeypatch.setattr(runtime,'_publish_control',lambda *a:pytest.fail('No extra source request'))
    assert runtime.refresh_snapshot()==(202,{'status':status,'message':'Bộ thu đang xử lý hoặc chờ nguồn; giao diện sẽ tự nhận bản mới.'})


def test_new_tab_reuses_recent_batch_across_tabs(monkeypatch):
    monkeypatch.setattr(runtime,'_thread',SimpleNamespace(is_alive=lambda:True))
    monkeypatch.setattr(runtime,'_stop',Event())
    monkeypatch.setattr(runtime,'_status_file',lambda:{})
    monkeypatch.setattr(runtime,'_config',runtime.collector_settings())
    monkeypatch.setattr(runtime,'load_snapshot',lambda:{'request_started_at':(datetime.now(VN)-timedelta(seconds=2)).isoformat()})
    monkeypatch.setattr(runtime,'_publish_control',lambda *a:pytest.fail('Duplicated batch'))
    assert runtime.refresh_snapshot()[1]['status']=='recent'


def test_notifications_contain_only_public_state_and_work_without_first_cache(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'CACHE',tmp_path/'not_created.json')
    monkeypatch.setattr(runtime,'collector_status',lambda:{'running':True,'status':'starting','poll_seconds':10})
    result=runtime.collector_event()
    assert result['revision'] is None and result['runtime']['stale_capture']
    assert result['runtime']['refreshing']


def test_push_signature_ignores_tick_age_but_detects_failure_and_phase_minute():
    event={'revision':'one','runtime':{'now':'2026-10-30T09:14:59+07:00','status':'waiting','stale_capture':False}}
    initial=server.event_signature(event)
    event['runtime']['now']='2026-10-30T09:14:59.9+07:00'
    assert server.event_signature(event)==initial
    event['runtime']['now']='2026-10-30T09:15:00+07:00'
    assert server.event_signature(event)!=initial
    event['runtime']['stale_capture']=True
    assert server.event_signature(event)!=initial


def test_sse_delivers_notification_without_requesting_analytics_or_remote_data(monkeypatch):
    sample={'revision':'actual-cache-revision','runtime':{'status':'waiting','now':'2026-10-30T09:15:00+07:00'}}
    monkeypatch.setattr(server,'collector_event',lambda:sample)
    monkeypatch.setattr(server,'build_state',lambda *a:pytest.fail('SSE must not compute full analytics'))
    httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    httpd.shutdown_event=Event()
    thread=Thread(target=httpd.serve_forever,daemon=True);thread.start()
    connection=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=3)
    try:
        connection.request('GET','/api/events')
        response=connection.getresponse()
        assert response.status==200 and response.getheader('Content-Type').startswith('text/event-stream')
        assert response.readline()==b'event: update\n'
        event=json.loads(response.readline().decode().removeprefix('data: '))
        assert event['revision']=='actual-cache-revision'
    finally:
        connection.close();httpd.shutdown_event.set();httpd.shutdown();httpd.server_close();thread.join(3)


def test_launcher_reuses_collector_instead_of_starting_second_worker(monkeypatch):
    opened=[]
    ensured=[]
    monkeypatch.setattr(launcher,'ensure_background',lambda port:ensured.append(port) or True)
    monkeypatch.setattr(launcher.webbrowser,'open',lambda url,**kwargs:opened.append(url))
    monkeypatch.setattr(server,'main',lambda *a:pytest.fail('Duplicate server/collector'))
    assert launcher.main([])==0 and ensured==[8765]
    assert opened==['http://127.0.0.1:8765/']


def test_daily_history_does_not_hold_up_live_board(monkeypatch,tmp_path):
    token='test-owned-worker';controls=tmp_path/'control.json'
    monkeypatch.setattr(worker,'CONTROL',controls)
    monkeypatch.setattr(worker,'STATUS',tmp_path/'status.json')
    class Session:
        def __init__(self,*a,**k):self.daily_history_day=None
        def fetch_daily_history(self):pytest.fail('Daily candles are unused by live dashboard')
        def poll(self):
            now=datetime.now(VN).isoformat()
            return {'captured_at':now,'request_started_at':now}
    monkeypatch.setattr(worker,'SSISession',Session)
    def stored(payload,**kwargs):
        controls.write_text(json.dumps({'worker_token':token,'serial':1,'command':'stop','heartbeat_monotonic':__import__('time').monotonic()}))
    monkeypatch.setattr(worker,'store_snapshot',stored)
    worker.run_worker(tmp_path/'not-read.env',runtime.collector_settings(),token)
    final=json.loads((tmp_path/'status.json').read_text(encoding='utf-8'))
    assert final['success_count']==1 and final['startup_seconds']>=0
