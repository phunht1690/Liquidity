from copy import deepcopy
from datetime import datetime
import json,sqlite3
import pytest

from tests.test_live_analytics import snapshots,config,state
from src.data.chart_archive import build_chart_archive,read_chart_archive
from src.data.ssi_runtime import store_snapshot
from src.data.live_analytics import VN
from src.app import server


def test_closed_cache_replays_actual_price_without_inventing_liquidity():
    series=snapshots(3,start=datetime(2026,10,30,15,30,tzinfo=VN))
    original=deepcopy(series)
    archive=build_chart_archive(series,{},config())
    assert archive['mode']=='chart_replay'
    assert [p['last_price_vnd'] for p in archive['points']]==[50000,50010,50020]
    assert all(p['spread_bps'] is None and p['depth_min_vnd'] is None for p in archive['points'])
    assert archive['summary']['liquidity_observations']==0
    assert all(p['depth_bid_vnd'] is None and p['depth_ask_vnd'] is None and p['spread_vnd'] is None for p in archive['points'])
    assert series==original
    assert 'alerts' not in archive and 'ranking' not in archive


def test_real_historical_continuous_metrics_use_the_recorded_time():
    archive=build_chart_archive(snapshots(3),{},config())
    assert archive['summary']['liquidity_observations']==3
    assert archive['points'][0]['spread_bps']==pytest.approx(100/50050*10000)
    point=archive['points'][0];raw=snapshots(3)[0]['quotes'][0]
    assert point['depth_bid_vnd']==sum(p['price']*p['volume'] for p in raw['bids'])
    assert point['depth_ask_vnd']==sum(p['price']*p['volume'] for p in raw['asks'])
    assert point['depth_min_vnd']==min(point['depth_bid_vnd'],point['depth_ask_vnd'])
    assert point['spread_vnd']==100
    assert archive['points'][0]['received_at'].startswith('2026-10-30T09:15:00')


def test_sparse_cache_reports_gaps_and_missing_symbol_instead_of_filling():
    series=snapshots(3,step=100)
    for s in series:s['membership']['universes']={'VN100':['FPT','VCB']}
    series[0]['quotes']=[r for r in series[0]['quotes'] if r['symbol']!='VCB']
    archive=build_chart_archive(series,{'universe':['VN100'],'symbol':['VCB']},config())
    assert archive['points'][0]['last_price_vnd'] is None
    assert archive['points'][1]['gap_before']
    assert archive['points'][2]['gap_before']
    assert archive['summary']['missing_symbol_observations']==1


def test_legacy_manual_and_other_sources_are_never_promoted_to_replay():
    series=snapshots(3)
    series[0].pop('collection_mode');series[1]['source']='simulated'
    archive=build_chart_archive(series,{},config())
    assert len(archive['points'])==1 and archive['points'][0]['dataset_id']=='vnstock-2'


@pytest.mark.parametrize('query',[{'index':['1']},{'day':['../secret']},{'day':['20261030']},{'symbol':['FPT','VCB']},{'universe':['HOSE']},{'symbol':['UNKNOWN']}])
def test_replay_rejects_unavailable_or_ambiguous_queries(query):
    with pytest.raises(ValueError):build_chart_archive(snapshots(1),query,config())


def test_archive_reads_selected_day_without_changing_database_or_live_state(tmp_path):
    database,cache=tmp_path/'observations.sqlite3',tmp_path/'latest.json'
    friday=snapshots(2);monday=snapshots(2,start=datetime(2026,11,2,9,15,tzinfo=VN))
    for day in (friday,monday):
        for i,s in enumerate(day):
            s['dataset_id']=s['captured_at']
            store_snapshot(s,database=database,cache=cache)
    live_before=state(monday)
    old=read_chart_archive({'day':['2026-10-30']},config(),database=database)
    assert len(old['days'])==2 and old['day']=='2026-10-30'
    assert len(old['points'])==2
    with sqlite3.connect(database) as db:assert db.execute('select count(*) from snapshots').fetchone()[0]==4
    assert state(monday)==live_before
    assert read_chart_archive({},config(),database=database)['day']=='2026-11-02'
    with pytest.raises(ValueError):read_chart_archive({'day':['2026-11-01']},config(),database=database)


def test_empty_archive_works_when_collector_has_never_run(tmp_path):
    assert read_chart_archive({},config(),database=tmp_path/'none.sqlite3')['points']==[]


def test_cache_route_does_not_call_live_state(monkeypatch):
    handler=object.__new__(server.Handler);handler.path='/api/chart-cache?symbol=FPT'
    monkeypatch.setattr(server,'build_state',lambda *a:pytest.fail('Archive requested Live'))
    monkeypatch.setattr(server,'read_chart_archive',lambda query,config:{'mode':'chart_replay','points':[]})
    result=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:result.append((status,data)))
    handler.do_GET();assert result==[(200,{'mode':'chart_replay','points':[]})]
