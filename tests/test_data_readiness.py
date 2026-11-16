from copy import deepcopy
from datetime import datetime
import json,sqlite3
import pytest

from tests.test_live_analytics import snapshots,state,config
from tests.test_live_collector import sample
from src.data import ssi_runtime as runtime
from src.data.live_analytics import build_live_state,VN
from src.data.ssi_feed import SSISession


def test_scope_changes_ranking_reference_without_changing_same_raw_observation():
    snaps=snapshots()
    for snapshot in snaps:
        snapshot['membership']['universes']={'VN30':['FPT'],'VN100':['FPT','VCB']}
    core=state(snaps,{'universe':['VN30']})
    expanded=state(snaps,{'universe':['VN100']})
    assert len(core['ranking'])==1 and len(expanded['ranking'])==2
    assert core['coverage']['reference_count']==1 and expanded['coverage']['reference_count']==2
    assert core['selected']['last_price_vnd']==expanded['selected']['last_price_vnd']
    assert core['dataset_id']==expanded['dataset_id']
    assert core['methodology']['lqs_reference_universe']=='VN30'
    assert expanded['methodology']['lqs_reference_universe']=='VN100'


def test_uncollected_scope_is_rejected_and_input_is_not_mutated():
    snaps=snapshots(1);original=deepcopy(snaps)
    with pytest.raises(ValueError):state(snaps,{'universe':['HOSE']})
    state(snaps)
    assert snaps==original and '_quote_index' not in json.dumps(snaps)


def test_readiness_does_not_count_after_hours_as_intraday_research():
    snaps=snapshots(3,start=datetime(2026,10,30,15,30,tzinfo=VN))
    data=state(snaps)['data_readiness']
    assert data['continuous_snapshot_count']==0
    assert data['days_with_continuous_observations']==0
    assert data['items'][0]['available']==2
    assert data['items'][1]['available']==2
    assert data['items'][2]['available']==0
    assert data['status']=='incomplete_for_research'
    assert data['ssi_observation_days']==1


def test_retains_multiple_days_with_daily_cap_and_does_not_mix_them_in_live_history(tmp_path):
    database,cache=tmp_path/'observations.sqlite3',tmp_path/'latest.json'
    for day in ('2026-10-30','2026-11-02'):
        for i in range(4):runtime.store_snapshot(sample(i,day),database=database,cache=cache,retention=3,retention_days=20)
    inventory=runtime.history_inventory(database=database)
    assert inventory['snapshot_count']==6
    assert inventory['days_with_continuous_observations']==2
    assert len(runtime.history_snapshots(database=database))==3
    assert all(s['captured_at'].startswith('2026-11-02') for s in runtime.history_snapshots(database=database))
    runtime.store_snapshot(sample(0,'2026-11-20'),database=database,cache=cache,retention_days=20)
    inventory=runtime.history_inventory(database=database)
    assert [r['day'] for r in inventory['days']]==['2026-11-02','2026-11-20']


