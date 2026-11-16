"""Live HTTP/export contracts; no provider requests in these tests."""
import csv
import io
import json
from pathlib import Path

import pytest

from src.app import server


@pytest.mark.parametrize('key',['index','frame_index','replay','session'])
def test_old_time_selection_is_rejected_before_reading_data(monkeypatch,key):
    monkeypatch.setattr(server,'snapshot_state',lambda:pytest.fail('unsupported query reached collector cache'))
    with pytest.raises(ValueError):server.build_state({key:['0']})


def test_health_is_live_and_replay_is_chart_only(monkeypatch):
    handler=object.__new__(server.Handler);handler.path='/api/health'
    seen=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:seen.append((status,data)))
    handler.do_GET()
    assert seen[0][0]==200
    assert seen[0][1]['mode']=='live' and seen[0][1]['auto_update']
    assert seen[0][1]['replay_available'] is True
    assert seen[0][1]['replay_scope']=='chart_only' and seen[0][1]['global_replay_available'] is False


@pytest.mark.parametrize('path',['/api/state','/api/export.csv'])
def test_retired_research_routes_do_not_serve_uncalibrated_metrics(monkeypatch,path):
    handler=object.__new__(server.Handler);handler.path=path
    monkeypatch.setattr(server,'build_state',lambda *a:pytest.fail('retired research path ran'))
    seen=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:seen.append(status))
    handler.do_GET();assert seen==[410]


def test_export_guard_does_not_publish_different_snapshot(monkeypatch):
    handler=object.__new__(server.Handler);handler.path='/api/product/export.csv?dataset_id=old'
    monkeypatch.setattr(server,'product_state',lambda query:{'dataset_id':'current'})
    seen=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:seen.append(status))
    monkeypatch.setattr(server,'export_product',lambda state:pytest.fail('exported a different dataset'))
    handler.do_GET();assert seen==[409]


def test_csv_discloses_received_basis_and_unavailable_values():
    state={'source':'ssi_fastconnect','dataset_id':'actual-observation','config_version':'public',
        'session_id':'2026-10-30','updated_at':'2026-10-30T09:30:00+07:00','notional_vnd':2e9,
        'applied_lqs_profile':'depth_cost','coverage':{'scope_label':'Ngân hàng','visible_count':1},
        'methodology':{'execution_cost_penalty_bps':100},'ranking':[{
            'symbol':'VCB','source':'ssi_fastconnect','received_at':'2026-10-30T09:30:00+07:00',
            'exchange_time':None,'lqs':None,'quality_flags':['warming_up'],'ofi_levels':[None,None,None]}]}
    data=server.export_csv(state)
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assert rows[0]['source']=='ssi_fastconnect' and rows[0]['timestamp_basis']=='received_at'
    assert rows[0]['exchange_time']==rows[0]['lqs']==''
    assert rows[0]['applied_lqs_profile']=='depth_cost' and float(rows[0]['notional_vnd'])==2e9
    assert 'frame_index' not in rows[0]


def test_startup_missing_cache_reports_waiting_not_fixture(monkeypatch):
    handler=object.__new__(server.Handler);handler.path='/api/product'
    def pending(query):raise FileNotFoundError('not ready')
    monkeypatch.setattr(server,'product_state',pending)
    seen=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:seen.append((status,data)))
    handler.do_GET()
    assert seen[0][0]==202 and 'runtime' in seen[0][1]


def test_replay_controls_are_scoped_to_chart_and_all_romer_shells_remain():
    text=(server.STATIC/'index.html').read_text(encoding='utf-8')
    assert 'replay-slider' not in text and 'play-button' not in text
    assert 'id="cache-play"' in text and 'id="telemetry-panel"' in text
    assert all(source in text for source in ('romer_command_dashboard/code.html','romer_signals_feed/code.html','romer_executive_reports/code.html'))
