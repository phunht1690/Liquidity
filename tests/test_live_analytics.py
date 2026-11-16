"""Hand-computed live polling checks; no credentials/network or fake warmup."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from math import log

import pytest

from src.data.live_analytics import build_live_state,VN,SOURCE


def config():
    return {'notional_vnd':1e9,'ssi':{'live_poll_seconds':10,'snapshot_stale_seconds':35,'history_gap_seconds':35},
        'market':{'lot_size':100,'tick_reference':'mid','max_round_lot_order_shares':500000},
        'incomplete_fill_penalty_bps':100}


def snapshots(count=31,step=10,start=None):
    start=start or datetime(2026,10,30,9,15,tzinfo=VN)
    result=[]
    for i in range(count):
        stamp=start+timedelta(seconds=step*i)
        rows=[]
        for symbol in ('FPT','VCB'):
            rows.append({'symbol':symbol,'source':SOURCE,'name':symbol,'trading_date':stamp.date().isoformat(),
                'last_price_vnd':50000+10*i,'reference_price_vnd':50000,
                'volume_shares':2000+100*i,'avg_match_price_vnd':50000,
                'cumulative_turnover_proxy_vnd':100e6+5e6*i,
                'turnover_basis':'avg_match_price_times_volume_proxy',
                'source_book_time_raw':f'{i:09d}','source_match_time_raw':f'{i:09d}',
                'provider_market_status':'LO','source_session_raw':'unverified','phase':'unverified','lot_segment':'unverified','exchange_time':None,
                'bids':[{'price':50000-j*100,'volume':1000+100*i} for j in range(3)],
                'asks':[{'price':50100+j*100,'volume':1000} for j in range(3)],'book_flags':[]})
        result.append({'source':SOURCE,'collection_mode':'auto_collector','schema_version':2,
            'dataset_id':f'vnstock-{i}','captured_at':stamp.isoformat(),'quotes':rows,
            'membership':{'symbols':['FPT','VCB']}})
    return result


def state(snaps,query=None,runtime=None):
    rt={'now':snaps[-1]['captured_at'],'stale_capture':False,'latest_snapshot':snaps[-1],**(runtime or {})}
    return build_live_state(query or {},snaps,rt,config())


def test_real_source_static_metrics_and_received_time_are_not_exchange_time():
    payload=state(snapshots(1))
    row=payload['selected']
    assert payload['mode']=='live' and payload['source']==SOURCE
    assert row['valid'] and row['quality']=='valid'
    assert row['mid']==50050
    assert row['spread_bps']==pytest.approx(100/50050*10000)
    assert row['spread_ticks']==1
    assert row['depth_bid_vnd']==149700000
    assert row['exchange_time'] is None and row['timestamp_basis']=='received_at'
    assert row['phase']=='unverified' and row['phase_basis']=='receiver_clock_estimate'
    assert row['buy']['lot_size_assumed']==100 and not row['buy']['lot_segment_verified']
    assert row['buy']['requested_shares']==19900
    assert row['buy']['filled_shares']==3000
    assert row['buy']['fill_ratio']==pytest.approx(3000/19900)
    assert row['buy']['vwap']==50200
    assert row['lqs'] is None and row['ofi_3'] is None
    assert payload['warmup']['remaining_seconds']==300
    assert 'frame_index' not in payload and 'frame_count' not in payload
    json.dumps(payload,allow_nan=False)


def test_ofi_hand_computed_and_persistence_after_three_actual_changes():
    payload=state(snapshots(2));row=payload['selected']
    assert row['ofi_levels']==[100,100,100]
    assert row['ofi_l1']==100 and row['ofi_3']==300
    assert row['ofi_normalized']==pytest.approx(300/6150)
    assert row['ofi_interval_seconds']==10
    assert row['ofi_persistence'] is None
    row=state(snapshots(4))['selected']
    assert row['ofi_persistence_count']==3 and row['ofi_persistence']==1


def test_five_minute_requires_elapsed_time_then_proxy_lqs_becomes_provisional():
    early=state(snapshots(30))['selected']
    assert early['amihud_5m'] is None and early['lqs'] is None and early['warmup_seconds']==10
    payload=state(snapshots(31));row=payload['selected']
    assert row['five_minute_elapsed_seconds']==300
    assert row['five_minute_trade_value_vnd']==150e6
    assert row['amihud_5m']==pytest.approx(abs(log(50300/50000))/.15)
    assert row['two_sided_ratio']==1
    assert row['lqs']==50 and row['lqs_status']=='provisional'
    assert payload['warmup']['remaining_seconds']==0


def test_more_records_without_elapsed_time_never_fake_five_minute_warmup():
    payload=state(snapshots(31,step=1))
    assert payload['selected']['lqs'] is None
    assert payload['selected']['amihud_5m'] is None
    assert payload['warmup']['remaining_seconds']==270


@pytest.mark.parametrize('break_kind',['missing_symbol','source','gap','manual','counter_reset','turnover_basis'])
def test_broken_five_minute_history_does_not_score(break_kind):
    snaps=snapshots(31)
    if break_kind=='missing_symbol':snaps[20]['quotes']=[snaps[20]['quotes'][1]]
    elif break_kind=='source':snaps[20]['source']='other_source'
    elif break_kind=='gap':
        for i in range(20,31):snaps[i]['captured_at']=(datetime.fromisoformat(snaps[i]['captured_at'])+timedelta(seconds=40)).isoformat()
    elif break_kind=='manual':snaps[20]['collection_mode']='manual'
    elif break_kind=='counter_reset':snaps[20]['quotes'][0]['cumulative_turnover_proxy_vnd']=1
    else:snaps[20]['quotes'][0].pop('turnover_basis')
    payload=state(snaps)
    assert payload['selected']['lqs'] is None and payload['selected']['amihud_5m'] is None


def test_frozen_book_cannot_build_ofi_persistence_or_new_history_events():
    snaps=snapshots(5)
    original=deepcopy(snaps[0]['quotes'][0])
    for s in snaps:s['quotes'][0]=deepcopy(original)
    row=state(snaps)['selected']
    assert row['ofi_status']=='source_unchanged'
    assert row['ofi_3'] is row['ofi_persistence'] is None
    assert row['ofi_persistence_count']==0
    # Freeze long enough: current source data becomes conservative/unavailable.
    snaps=snapshots(14)
    for s in snaps:s['quotes'][0]=deepcopy(original)
    row=state(snaps)['selected']
    assert not row['valid'] and 'source_unchanged' in row['quality_flags']


@pytest.mark.parametrize('kind',['stale','prior_day','lunch','auction','weekend'])
def test_noncurrent_or_noncontinuous_data_does_not_emit_current_signals(kind):
    starts={'lunch':datetime(2026,10,30,12,tzinfo=VN),'auction':datetime(2026,10,30,14,30,tzinfo=VN),
            'weekend':datetime(2026,10,31,9,15,tzinfo=VN)}
    snaps=snapshots(31,start=starts.get(kind))
    rt={}
    if kind=='stale':rt={'now':(datetime.fromisoformat(snaps[-1]['captured_at'])+timedelta(seconds=40)).isoformat()}
    if kind=='prior_day':rt={'now':(datetime.fromisoformat(snaps[-1]['captured_at'])+timedelta(days=1)).isoformat()}
    payload=state(snaps,runtime=rt)
    assert not payload['selected']['valid']
    assert payload['selected']['ofi_3'] is payload['selected']['lqs'] is None
    assert payload['alerts']==[]


def test_legacy_one_off_cache_shows_raw_book_without_manufactured_history():
    legacy=snapshots(1)[0];legacy.pop('collection_mode');legacy['schema_version']=1
    payload=build_live_state({},[],{'now':legacy['captured_at'],'latest_snapshot':legacy},config())
    assert payload['selected']['bids']
    assert payload['history']==[]
    assert payload['selected']['lqs'] is None and payload['selected']['ofi_3'] is None
    assert sum(r['sample_count'] for r in payload['intraday_profile'])==0


def test_duplicate_capture_does_not_inflate_profile_or_messages():
    snaps=snapshots(4)
    payload=state([snaps[0],snaps[1],deepcopy(snaps[1]),snaps[2],snaps[3]])
    assert len(payload['history'])==4
    assert payload['quality']['total_messages']==8
    assert payload['quality']['late_count']==1


def test_group_filter_keeps_full_real_reference_score():
    snaps=snapshots(31)
    full=state(snaps);filtered=state(snaps,{'group':['Ngân hàng'],'symbol':['VCB']})
    assert len(filtered['ranking'])==1
    assert filtered['coverage']['reference_count']==2
    assert filtered['selected']['lqs']==next(r['lqs'] for r in full['ranking'] if r['symbol']=='VCB')


def test_invalid_current_book_is_not_synthetic_zero_data():
    snaps=snapshots(4);snaps[-1]['quotes'][0]['asks']=[]
    row=state(snaps)['selected']
    assert not row['valid'] and row['spread_bps'] is row['fill_ratio'] is row['ofi_3'] is None


def test_missing_symbol_keeps_batch_marker_without_inventing_received_timestamp():
    snaps=snapshots(4)
    snaps[-1]['quotes']=[snaps[-1]['quotes'][1]]
    payload=state(snaps)
    row=payload['selected']
    assert row['timestamp'] is row['received_at'] is row['exchange_time'] is None
    assert row['observation_at']==snaps[-1]['captured_at']
    assert not payload['history'][-1]['valid'] and payload['history'][-1]['timestamp'] is None
    assert payload['asof_source_symbol']=='VCB'


def test_outside_hours_reports_actual_poll_cadence_without_false_capture_stale():
    snaps=snapshots(1,start=datetime(2026,10,30,16,tzinfo=VN))
    now=datetime.fromisoformat(snaps[-1]['captured_at'])+timedelta(seconds=100)
    payload=state(snaps,runtime={'now':now.isoformat(),'poll_interval_seconds':300,'stale_after_seconds':900})
    assert payload['runtime']['poll_seconds']==300
    assert payload['connection']['poll_seconds']==300
    assert payload['methodology']['sample_interval_seconds']==300
    assert not payload['runtime']['stale_capture']
    assert payload['phase_code']=='closed'
    assert payload['alerts']==[] and not payload['selected']['valid']


def test_no_replay_query_and_no_implicit_fixture_fallback():
    with pytest.raises(ValueError):state(snapshots(2),{'index':['0']})
    with pytest.raises(FileNotFoundError):build_live_state({},[],{},config())
