"""Hand-calculated flow, temporal integrity and applied-profile regression cases."""
import csv
import io
import json
from dataclasses import replace
from datetime import datetime, timedelta
from statistics import median

import pytest

from tests.support import dashboard_fixture as server
from src.data.quality import quote_flags, session_phase
from src.data.schema import PriceLevel, Quote, VN_TZ
from src.data.simulated import metrics_at
from src.finance.execution_sim import simulate_execution
from src.finance.flow import effective_spread_bps, flow_at, matched_effective_spread_bps, snapshot_flow
from src.finance.microstructure import compute_metrics
from src.ssi_api.adapter import inspect_price_observation


def quote(minute=0, *, bv=(200, 300, 500), av=(100, 200, 300), bid_shift=0, ask_shift=0):
    stamp = datetime(2026, 10, 26, 9, 30, tzinfo=VN_TZ) + timedelta(minutes=minute)
    return Quote('TEST', stamp, stamp + timedelta(milliseconds=30),
                 tuple(PriceLevel(p + bid_shift, v) for p, v in zip((99900, 99800, 99700), bv)),
                 tuple(PriceLevel(p + ask_shift, v) for p, v in zip((100100, 100200, 100300), av)),
                 100000, 1e9 + minute * 1e6, lot_type='round')


def test_unchanged_prices_use_volume_changes_at_all_three_levels():
    # Bid changes +100,+100,+100; ask changes -50,+100,-100 => +150,0,+200.
    old, new = quote(), quote(1, bv=(300,400,600), av=(50,300,200))
    flow = snapshot_flow(old,new)
    assert flow['ofi_levels'] == [150,0,200]
    assert flow['ofi_l1'] == 150 and flow['ofi_3'] == 350
    assert flow['ofi_normalized'] == pytest.approx(350/1725)
    assert flow['ofi_interval_seconds'] == 60


@pytest.mark.parametrize('bid_shift,ask_shift,expected',[
    (100,0,[300,400,600]), (-100,0,[-200,-300,-500]),
    (0,100,[100,200,300]), (0,-100,[-50,-300,-200]),
])
def test_price_improvements_and_deteriorations_use_correct_queue(bid_shift,ask_shift,expected):
    new=quote(1,bv=(300,400,600),av=(50,300,200),bid_shift=bid_shift,ask_shift=ask_shift)
    # Isolate the other side so its unchanged price/volume contributes zero.
    if bid_shift: new=replace(new,asks=quote().asks)
    else: new=replace(new,bids=quote().bids)
    assert snapshot_flow(quote(),new)['ofi_levels'] == expected


@pytest.mark.parametrize('fault',['gap','late','same_time','symbol','source','missing','crossed','auction','odd','unknown_lot','day'])
def test_flow_never_bridges_ineligible_observations(fault):
    old,new=quote(),quote(1)
    if fault=='gap': new=quote(2)
    elif fault=='late': new=quote(-1)
    elif fault=='same_time': new=quote()
    elif fault=='symbol': new=replace(new,symbol='OTHER')
    elif fault=='source': new=replace(new,source='other')
    elif fault=='missing': old=None
    elif fault=='crossed': new=replace(new,asks=(PriceLevel(99800,100),)+new.asks[1:])
    elif fault=='auction': new=replace(new,phase='closing_auction')
    elif fault=='odd': new=replace(new,lot_type='odd')
    elif fault=='unknown_lot': new=replace(new,lot_type='unknown')
    elif fault=='day': new=replace(new,exchange_time=new.exchange_time+timedelta(days=1))
    flow=snapshot_flow(old,new)
    assert flow['ofi_l1'] is None and flow['ofi_3'] is None
    assert flow['ofi_normalized'] is None


def test_persistence_counts_neutral_zeros_and_requires_three_increments():
    # Three increments +100,0,+100, so only 2/3 have the current positive sign.
    quotes=[quote(i,bv=(v,300,500)) for i,v in enumerate((200,300,300,400))]
    assert flow_at(quotes,2)['ofi_persistence'] is None
    result=flow_at(quotes,3)
    assert result['ofi_persistence_count']==3
    assert result['ofi_persistence']==pytest.approx(2/3)
    assert flow_at(quotes,2)['ofi_3']==0
    quotes[2]=None
    assert flow_at(quotes,3)['ofi_persistence_count']==0
    assert flow_at(quotes,3)['ofi_persistence'] is None


def test_flow_uses_the_applied_gap_limit():
    old,new=quote(),quote(1,bv=(300,400,600))
    new=replace(new,exchange_time=old.exchange_time+timedelta(seconds=70))
    assert metrics_at([old,new],1)['ofi_status']=='snapshot_approximation'
    assert metrics_at([old,new],1,history_gap_seconds=60)['ofi_status']=='gap_or_session_boundary'


@pytest.mark.parametrize('hour,minute,phase',[(9,0,'opening_auction'),(9,15,'continuous_am'),
    (11,30,'lunch'),(13,0,'continuous_pm'),(14,30,'closing_auction'),(15,0,'closed')])
def test_clock_classification_does_not_depend_on_numeric_price(hour,minute,phase):
    q=quote();q=replace(q,exchange_time=q.exchange_time.replace(hour=hour,minute=minute))
    assert session_phase(q)==phase
    if phase not in ('continuous_am','continuous_pm'):
        assert 'non_continuous_phase' in quote_flags(q)
        assert compute_metrics(q)['weighted_mid'] is None


def test_declared_halt_and_separate_lot_segments_are_not_traded():
    assert 'non_continuous_phase' in quote_flags(replace(quote(),phase='halted'))
    for lot in ('odd','unknown'):
        assert simulate_execution(replace(quote(),lot_type=lot),1e9,'buy')['fill_ratio'] is None
    large=simulate_execution(quote(),100_000_000_000,'buy')
    assert large['requested_shares']==1_000_000
    assert large['single_order_eligible'] is False
    assert large['max_order_shares']==500_000


def test_price_guard_handles_both_auction_representations_without_enabling_live():
    assert inspect_price_observation('ATO','opening_auction')['numeric_price'] is None
    result=inspect_price_observation('100100','opening_auction')
    assert result['numeric_price']==100100 and not result['continuous_eligible']
    assert inspect_price_observation(100100,'continuous_am')['continuous_eligible']
    with pytest.raises(ValueError): inspect_price_observation('ATC','continuous_am')
    with pytest.raises(ValueError): inspect_price_observation(100100,'unknown')


def test_weighted_mid_keeps_hand_calculated_value_under_correct_name():
    m=compute_metrics(quote())
    assert m['weighted_mid']==pytest.approx(100033.3333333333)
    assert m['weighted_mid_dev_bps']==pytest.approx(3.3333333333)
    assert 'microprice' not in m


def test_effective_spread_is_bps_and_rejects_future_stale_and_unordered_ties():
    assert effective_spread_bps(100100,100000)==20
    assert effective_spread_bps(99900,100000)==20
    q=quote();stamp=q.exchange_time
    assert matched_effective_spread_bps(100100,stamp+timedelta(seconds=1),q,max_quote_age_seconds=2)==20
    for time in (stamp-timedelta(seconds=1),stamp,stamp+timedelta(seconds=3)):
        with pytest.raises(ValueError): matched_effective_spread_bps(100100,time,q,max_quote_age_seconds=2)
    assert matched_effective_spread_bps(100100,stamp,q,max_quote_age_seconds=2,same_timestamp_order_verified=True)==20
    with pytest.raises(ValueError): matched_effective_spread_bps(100100,stamp,q,max_quote_age_seconds='5')


def test_applied_profile_is_consistent_in_components_and_csv():
    baseline=server.build_state({})
    alternative=server.build_state({'lqs_profile':['depth_cost'],'group':['Ngân hàng']})
    for s,profile,spread_weight in ((baseline,'baseline',.25),(alternative,'depth_cost',.10)):
        assert s['applied_lqs_profile']==s['methodology']['applied_lqs_profile']==profile
        assert s['methodology']['lqs_weights']['spread_bps']==spread_weight
        assert sum(x['contribution'] for x in s['selected']['lqs_explanation'])==pytest.approx(s['selected']['lqs'])
        for component in s['selected']['lqs_explanation']:
            assert component['weight']==s['methodology']['lqs_weights'][component['key']]
        exported=list(csv.DictReader(io.StringIO(server.export_csv(s).decode('utf-8-sig'))))
        assert exported and all(r['applied_lqs_profile']==profile for r in exported)
        assert all('weighted_mid' in r and 'ofi_level_3' in r and 'microprice' not in r for r in exported)
    assert baseline['selected']['lqs'] != alternative['selected']['lqs']
    with pytest.raises(ValueError): server.build_state({'lqs_profile':['unrecognized']})


def test_intraday_counts_and_fills_are_causal_and_costs_do_not_hide_capacity(monkeypatch):
    s=server.build_state({'index':['10']})
    assert sum(b['sample_count'] for b in s['intraday_profile'])==11
    assert all(b['sample_count']==0 and b['median_spread_bps'] is None for b in s['intraday_profile'][1:])
    expected=[server._metrics('FPT',i,s['notional_vnd'])['sell']['fill_ratio'] for i in range(11)]
    assert s['intraday_profile'][0]['median_sell_fill_ratio']==median(expected)
    # Alter all later observations: the as-of profile and diagnostics must be identical.
    quotes=list(server.DEMO['FPT'])
    for i in range(11,len(quotes)): quotes[i]=None
    monkeypatch.setitem(server.DEMO,'FPT',quotes)
    after=server.build_state({'index':['10']})
    assert after['intraday_profile']==s['intraday_profile']
    assert after['tick_diagnostics']==s['tick_diagnostics']
    assert after['selected']['ofi_3']==s['selected']['ofi_3']


def test_warmup_has_no_flow_or_fabricated_research_results():
    s=server.build_state({'index':['0']})
    assert s['selected']['ofi_3'] is None and s['selected']['ofi_persistence'] is None
    assert s['methodology']['effective_spread']['trade_count']==0
    assert s['methodology']['effective_spread']['status']=='unavailable'
    assert s['methodology']['forecast']['horizons_seconds']==[5,15,30]
    assert s['methodology']['forecast']['control_seconds']==60
    assert s['methodology']['resilience']['status']=='planned'
    json.dumps(s,allow_nan=False)
