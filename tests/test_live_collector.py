"""Offline boundaries: automatic samples, bounded history, scheduling and isolation."""
from datetime import datetime,timedelta
import io
import json
from pathlib import Path
from types import SimpleNamespace
from queue import Queue

import pytest

from src.data.ssi_feed import VN,normalize_board,SSISession
from src.data import ssi_runtime as runtime
from src.data.ssi_worker import backoff_seconds,error_category
from src.data import ssi_worker as worker


@pytest.fixture(autouse=True)
def isolate_runtime_files(monkeypatch,tmp_path):
    """A test must never send control commands to a running real collector."""
    monkeypatch.setattr(runtime,'CONTROL',tmp_path/'control.json')
    monkeypatch.setattr(worker,'CONTROL',tmp_path/'control.json')
    monkeypatch.setattr(runtime,'STATUS',tmp_path/'status.json')
    monkeypatch.setattr(worker,'STATUS',tmp_path/'status.json')
    monkeypatch.setattr(runtime,'DATABASE',tmp_path/'runtime.sqlite3')
    monkeypatch.setattr(runtime,'load_snapshot',lambda: (_ for _ in ()).throw(FileNotFoundError()))


def sample(seq=0,day='2026-10-30'):
    stamp=datetime.fromisoformat(day+'T09:15:00+07:00')+timedelta(seconds=10*seq)
    return {'schema_version':2,'source':'ssi_fastconnect','collection_mode':'auto_collector',
        'collection_kind':'auto_collector','captured_at':stamp.isoformat(),'dataset_id':f'live-{day}-{seq}',
        'quotes':[{'symbol':'FPT','exchange_time':None,'received_at':stamp.isoformat()}]}


def test_store_keeps_only_real_auto_observations_and_never_seeds_legacy(tmp_path):
    database,cache=tmp_path/'history.sqlite3',tmp_path/'latest.json'
    legacy=sample();legacy.pop('collection_mode')
    cache.write_text(json.dumps(legacy))
    assert runtime.history_snapshots(database=database)==[]
    with pytest.raises(ValueError):runtime.store_snapshot(legacy,database=database,cache=cache)
    assert json.loads(cache.read_text())==legacy


def test_history_order_dedup_retention_and_rollover(tmp_path):
    database,cache=tmp_path/'history.sqlite3',tmp_path/'latest.json'
    for i in range(5):runtime.store_snapshot(sample(i),database=database,cache=cache,retention=3)
    runtime.store_snapshot(sample(4),database=database,cache=cache,retention=3)
    rows=runtime.history_snapshots(limit=99,database=database)
    assert [r['dataset_id'] for r in rows]==[f'live-2026-10-30-{i}' for i in (2,3,4)]
    assert json.loads(cache.read_text())['dataset_id']=='live-2026-10-30-4'
    runtime.store_snapshot(sample(0,'2026-11-02'),database=database,cache=cache,retention=3)
    assert [r['dataset_id'] for r in runtime.history_snapshots(database=database)]==['live-2026-11-02-0']


def test_storage_does_not_invent_timezone(tmp_path):
    payload=sample();payload['captured_at']='2026-10-30T09:15:00'
    with pytest.raises(ValueError):runtime.store_snapshot(payload,database=tmp_path/'h.sqlite3',cache=tmp_path/'latest.json')


@pytest.mark.parametrize('stamp,expected',[
    ('2026-10-30T09:00:00+07:00',True),('2026-10-30T09:10:00+07:00',True),
    ('2026-10-30T11:31:00+07:00',False),('2026-10-30T13:00:00+07:00',True),
    ('2026-10-30T14:40:00+07:00',True),('2026-10-30T14:46:00+07:00',False),
    ('2026-10-31T10:00:00+07:00',False),
])
def test_market_clock_cadence_includes_auctions_but_not_lunch_weekend(stamp,expected):
    now=datetime.fromisoformat(stamp)
    assert runtime.market_clock_open(now) is expected
    settings=runtime.collector_settings()
    assert runtime.poll_delay(settings,now)==(10 if expected else 30)


def test_poll_settings_cannot_cause_tight_retry_loop_or_unbounded_history():
    config=runtime.collector_settings({'ssi':{'live_poll_seconds':0,'history_retention_snapshots':10**9,
        'collector_timeout_seconds':'NaN','off_hours_poll_seconds':-1}})
    assert config['live_poll_seconds']==5
    assert config['off_hours_poll_seconds']==15
    assert config['history_retention_snapshots']==5000
    assert config['collector_timeout_seconds']==50


def test_rate_limit_backoff_respects_provider_wait_and_never_echoes_secret():
    error=RuntimeError('HTTP 429 bearer SECRET')
    category=error_category(error)
    assert category=='rate_limited' and 'SECRET' not in category
    settings=runtime.collector_settings()
    assert backoff_seconds(1,settings,category)>=60
    assert backoff_seconds(1,settings,category,600)==600
    assert backoff_seconds(30,settings,'source_unavailable')==300






def test_lifecycle_import_and_stopped_refresh_never_launch_network(monkeypatch):
    monkeypatch.setattr(runtime,'_thread',None)
    monkeypatch.setattr(runtime.subprocess,'Popen',lambda *a,**k:pytest.fail('No process launch on status/read'))
    assert runtime.collector_status()['running'] is False
    assert runtime.refresh_snapshot()[0]==503
    runtime.stop_collector()


def test_refresh_only_signals_existing_worker_and_coalesces(monkeypatch):
    commands=[]
    monkeypatch.setattr(runtime,'_thread',SimpleNamespace(is_alive=lambda:True))
    monkeypatch.setattr(runtime,'_process',SimpleNamespace(poll=lambda:None))
    monkeypatch.setattr(runtime,'_last_attempt',None)
    monkeypatch.setattr(runtime,'_config',runtime.collector_settings())
    monkeypatch.setattr(runtime,'_stop',SimpleNamespace(is_set=lambda:False))
    monkeypatch.setattr(runtime,'_publish_control',lambda command=None:commands.append(command))
    assert runtime.refresh_snapshot()[0]==202
    assert commands==['refresh']
    assert runtime.refresh_snapshot()[0]==429
    assert commands==['refresh']


def test_stale_legacy_cache_keeps_capture_time_without_exchange_lag(monkeypatch):
    payload=sample();payload.pop('collection_mode')
    payload['captured_at']=(datetime.now(VN)-timedelta(seconds=2)).isoformat()
    monkeypatch.setattr(runtime,'load_snapshot',lambda:payload)
    monkeypatch.setattr(runtime,'_history_count',lambda:0)
    result=runtime.snapshot_state()
    assert result['runtime']['stale_capture'] is True
    assert 'lag_ms' not in result['runtime']
    assert result['quotes'][0]['exchange_time'] is None


def test_worker_failure_retains_previous_success_and_sanitizes_status(monkeypatch,tmp_path):
    commands=Queue()
    class Input:
        def __iter__(self):return self
        def __next__(self):return commands.get(timeout=2)
    class Session:
        def __init__(self,*args,**kwargs):
            self.calls=0
            self.daily_history_day=datetime.now(VN).date().isoformat()
        def poll(self):
            self.calls+=1
            if self.calls==1:return sample()
            worker.CONTROL.write_text(json.dumps({'worker_token':'test-worker','command':'stop','serial':1,
                'heartbeat_monotonic':__import__('time').monotonic()}),encoding='utf-8')
            raise RuntimeError('HTTP429 Authorization=SECRET')
    database,cache,status=tmp_path/'history.sqlite3',tmp_path/'latest.json',tmp_path/'status.json'
    monkeypatch.setattr(worker.sys,'stdin',Input())
    monkeypatch.setattr(worker,'SSISession',Session)
    monkeypatch.setattr(worker,'STATUS',status)
    monkeypatch.setattr(worker,'store_snapshot',lambda payload,**kwargs:runtime.store_snapshot(payload,database=database,cache=cache))
    settings=runtime.collector_settings();settings['live_poll_seconds']=.001;settings['off_hours_poll_seconds']=.001
    worker.run_worker(Path('not-read.env'),settings,'test-worker')
    assert json.loads(cache.read_text())['dataset_id']==sample()['dataset_id']
    assert len(runtime.history_snapshots(database=database))==1
    final=json.loads(status.read_text(encoding='utf-8'))
    assert final['status']=='stopped' and final['last_error_code']=='rate_limited'
    assert final['failure_count']==1
    assert 'SECRET' not in status.read_text(encoding='utf-8')


def test_worker_does_not_publish_after_stop_arrives_during_fetch(monkeypatch,tmp_path):
    from threading import Event
    events=[]
    def event_factory():
        event=Event();events.append(event);return event
    class Input:
        def __iter__(self):return self
        def __next__(self):
            events[0].wait(timeout=1)
            raise StopIteration
    class Session:
        def __init__(self,*args,**kwargs):pass
        def poll(self):
            events[0].set()
            return sample()
    monkeypatch.setattr(worker,'Event',event_factory)
    monkeypatch.setattr(worker.sys,'stdin',Input())
    monkeypatch.setattr(worker,'SSISession',Session)
    monkeypatch.setattr(worker,'STATUS',tmp_path/'status.json')
    monkeypatch.setattr(worker,'store_snapshot',lambda *a,**k:pytest.fail('Late result published after cancellation'))
    worker.run_worker(Path('not-read.env'),runtime.collector_settings(),'test-stop')
    assert json.loads((tmp_path/'status.json').read_text(encoding='utf-8'))['status']=='stopped'

def test_worker_closes_failed_auth_session_so_stream_cannot_be_orphaned(monkeypatch,tmp_path):
    from threading import Event
    from src.data.ssi_feed import SSIAPIError
    events=[];closed=[]
    def event_factory():
        event=Event();events.append(event);return event
    class Session:
        def __init__(self,*args,**kwargs):pass
        def poll(self):
            events[0].set()
            raise SSIAPIError('authentication_failed',401)
        def close(self):closed.append(True)
    monkeypatch.setattr(worker,'Event',event_factory)
    monkeypatch.setattr(worker,'SSISession',Session)
    monkeypatch.setattr(worker,'STATUS',tmp_path/'status.json')
    worker.run_worker(Path('not-read.env'),runtime.collector_settings(),'test-close')
    assert closed==[True]
