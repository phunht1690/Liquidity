"""Economic edge cases and archive invariants for the expanded cash-equity product."""
from copy import deepcopy
from datetime import datetime,timedelta
import sqlite3
from pathlib import Path
import pytest
from src.data.ssi_feed import normalize_board,VN
from src.data.liquidity import analyze_book
from src.data.market_rules import tick_distance,phase
from src.data.ssi_runtime import store_snapshot,history_inventory
from src.data.observation_store import hydrate,read_series
from src.data.daily_summary import normalize,DailySummaries
from src.data.alert_history import attach_history
from src.data.candle_statistics import enrich_candle_statistics
from src.data.product import build_product
from src.data.chart_archive import read_chart_archive
from tests.test_ssi_feed import raw
from tests.test_live_analytics import snapshots,config


def book_fixture(change=None,board='HOSE'):
    now=datetime(2026,11,9,9,30,tzinfo=VN);r=raw()
    r.update(change or {});r['board']=board
    quote=normalize_board([r],['FPT'],now=now,allowed_boards=('HOSE','HNX','UPCOM'))[0]
    return {'source':'ssi_fastconnect','captured_at':now.isoformat(),'quotes':[quote]},now


def test_known_one_level_is_usable_but_missing_field_is_not():
    s,now=book_fixture({'bids':[['50000','1000']],'asks':[['50100','2000']]})
    r=analyze_book(s,'FPT',1e9,config(),now=now)
    assert r['valid'] and r['known_bid_levels']==r['known_ask_levels']==1
    assert r['depth_bid_vnd']==50_000_000 and r['spread_vnd']==100
    unknown,now=book_fixture({'asks':None})
    assert not analyze_book(unknown,'FPT',1e9,config(),now=now)['valid']


@pytest.mark.parametrize('empty',[[],[['0','0'],['0','0'],['0','0']]])
def test_known_empty_sell_side_means_zero_capacity_not_missing_data(empty):
    s,now=book_fixture({'asks':empty})
    r=analyze_book(s,'FPT',1e9,config(),now=now)
    assert r['valid'] and r['buy']['fill_ratio']==0
    assert r['depth_ask_vnd']==0 and r['spread_vnd'] is None and r['buy']['vwap'] is None
    assert r['sizing_basis']=='last_trade_or_reference'


def test_crossed_book_still_fails_after_sparse_support():
    s,now=book_fixture({'bids':[['50200','1000']],'asks':[['50100','2000']]})
    assert not analyze_book(s,'FPT',1e9,config(),now=now)['valid']


def test_tick_steps_cross_price_band_without_fractional_midband_artifact():
    assert tick_distance(49950,50100,'HOSE')==2
    assert tick_distance(9900,10050,'HOSE')==11
    assert tick_distance(10000,10300,'HNX')==3


def test_pilot_book_needs_same_day_metadata_and_correct_lot_and_price_units():
    data={'bids':[['50000','1000']],'asks':[['50100','2000']],'floor':'45000','ceiling':'55000','master_date':'2026-11-09'}
    s,now=book_fixture(data,'HNX');assert s['quotes'][0]['units_verified']
    assert analyze_book(s,'FPT',1e9,config(),now=now)['valid']
    wrong,now=book_fixture({**data,'bids':[['50','10']]},'HNX')
    assert not wrong['quotes'][0]['units_verified']
    assert not analyze_book(wrong,'FPT',1e9,config(),now=now)['valid']


def test_phase_rules_do_not_apply_hose_opening_auction_to_hnx():
    at=datetime(2026,11,12,9,5,tzinfo=VN)
    assert phase(at,'HOSE')=='opening_auction' and phase(at,'HNX')=='continuous_am'
    assert phase(at.replace(hour=14,minute=50),'HNX')=='post_close'
    assert phase(at.replace(hour=14,minute=50),'UPCOM')=='continuous_pm'


def test_reference_notional_discloses_cash_instead_of_claiming_budget_cap():
    s,now=book_fixture({'bids':[['50700','100000']],'asks':[['50800','100000']]})
    r=analyze_book(s,'FPT',1e9,config(),now=now)
    assert r['buy']['requested_shares']==19700
    assert r['buy']['filled_value_vnd']==1_000_760_000
    assert r['buy']['reference_notional_vnd']==1e9


def test_delta_archive_reconstructs_unchanged_ticker_and_skips_quiet_poll(tmp_path):
    series=snapshots(3);db=tmp_path/'observations.sqlite3';cache=tmp_path/'latest.json'
    first=series[0];second=deepcopy(first);second.update(dataset_id='changed',captured_at=series[1]['captured_at'])
    second['quotes'][0]['last_price_vnd']=50500
    quiet=deepcopy(second);quiet.update(dataset_id='quiet',captured_at=series[2]['captured_at'])
    for s in (first,second,quiet):store_snapshot(s,database=db,cache=cache,compact=True)
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT COUNT(*) FROM captures').fetchone()[0]==2
        assert c.execute('SELECT COUNT(*) FROM quote_changes').fetchone()[0]==3
    restored=hydrate(db,'changed');quotes={q['symbol']:q for q in restored['quotes']}
    assert quotes['FPT']['last_price_vnd']==50500
    assert quotes['VCB']==first['quotes'][1]
    assert len(read_series(db,'FPT'))==2
    assert history_inventory(database=db)['snapshot_count']==2


def test_delta_retention_day_starts_with_independent_checkpoint(tmp_path):
    first=snapshots(1)[0];next_day=deepcopy(first)
    next_day.update(dataset_id='tomorrow',captured_at=(datetime.fromisoformat(first['captured_at'])+timedelta(days=1)).isoformat())
    db=tmp_path/'o.sqlite3';cache=tmp_path/'latest.json'
    for s in (first,next_day):store_snapshot(s,database=db,cache=cache,compact=True,retention_days=1)
    assert hydrate(db,first['dataset_id']) is None
    assert hydrate(db,'tomorrow')['quotes']==first['quotes']


def test_daily_summary_selects_latest_valid_date_not_first_provider_row():
    now=datetime(2026,11,12,8,tzinfo=VN)
    rows=[{'symbol':'FPT','tradingDate':d,'close':p,'totalMatch':'100','totalMatchValue':'5000000'} for d,p in [('2026/11/09','51000'),('2026/11/11','50900'),('2026/11/10','50800')]]
    r=normalize(rows,'FPT',now)
    assert r['day']=='2026-11-11' and r['close']==50900 and r['turnover_vnd']==5000000


def test_summary_does_not_overwrite_a_newer_intraday_trade(tmp_path):
    series=snapshots(1,start=datetime(2026,11,12,10,tzinfo=VN))
    product=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1],'auth':{'websocket_status':'connected'}},config())
    svc=DailySummaries(database=tmp_path/'s.sqlite3');svc.request=lambda *a,**k:None
    svc.cache={'FPT':{'day':'2026-11-11','close':1,'volume_shares':1,'turnover_vnd':1,'received_at':'2026-11-12T08:00:00+07:00'}}
    before=deepcopy(product['selected']);svc.enrich(product)
    assert product['selected']['last_price_vnd']==before['last_price_vnd']
    assert product['selected']['price_basis']=='last_received_trade'


def test_previous_close_can_replace_old_tick_when_new_day_book_has_arrived(tmp_path):
    series=snapshots(1,start=datetime(2026,11,12,9,10,tzinfo=VN))
    series[-1]['quotes'][0]['source_match_time_raw']='2026/11/11 14:29:16'
    product=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1]},config())
    book=deepcopy(product['selected']['bids']);svc=DailySummaries(database=tmp_path/'s.sqlite3');svc.request=lambda *a,**k:None
    svc.cache={'FPT':{'day':'2026-11-11','close':50900,'volume_shares':7000000,'turnover_vnd':350000000000,'received_at':'2026-11-12T09:00:00+07:00'}}
    svc.enrich(product)
    assert product['selected']['last_price_vnd']==50900 and product['selected']['price_basis']=='ssi_daily_close'
    assert product['selected']['bids']==book and product['selected']['trade_time']=='2026/11/11 14:29:16'


def test_journal_has_observed_duration_and_splits_a_collection_gap(tmp_path):
    series=snapshots(1);p=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1],'auth':{'websocket_status':'connected'}},config())
    assert p['alerts'];db=tmp_path/'a.sqlite3'
    attach_history(p,db);assert p['alerts'][0]['observation']['duration_seconds']==0
    start=datetime.fromisoformat(p['analysis']['asof'])
    later=deepcopy(p);later['analysis']['asof']=(start+timedelta(seconds=10)).isoformat();attach_history(later,db)
    assert later['alerts'][0]['observation']['duration_seconds']==10
    gap=deepcopy(p);gap['analysis']['asof']=(start+timedelta(minutes=5)).isoformat();attach_history(gap,db)
    assert gap['alerts'][0]['observation']['duration_seconds']==0


def test_saved_reference_does_not_manufacture_alert_history(tmp_path):
    p={'analysis':{'mode':'saved','asof':'2026-11-11T14:29:00+07:00'}};db=tmp_path/'a.sqlite3'
    attach_history(p,db);assert p['alert_history']==[] and not db.exists()


def test_one_missing_selected_book_does_not_freeze_other_live_stocks():
    series=snapshots(1);series[-1]['quotes'][0]['book_flags']=['book_from_previous_connection']
    p=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1],'auth':{'websocket_status':'connected'}},config())
    assert p['analysis']['mode']=='live' and not p['selected']['valid']
    assert next(r for r in p['ranking'] if r['symbol']=='VCB')['valid']


def write_candle_cache(path,day='2026-11-11',stamp='2026-11-11T14:45:00+07:00'):
    import json
    data={'symbol':'FPT','range':'session','timeframe':'5m','complete_range':True,'invalid_records':0,
        'requested_from':day+'T00:00:00+07:00','updated_at':day+'T15:00:00+07:00',
        'bars':[{'timestamp':stamp,'trading_date':day,'close':50900,'volume_shares':100,'value_vnd':5090000}]}
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE chart_cache(cache_key TEXT,payload TEXT,saved_at REAL)')
        db.execute('INSERT INTO chart_cache VALUES(?,?,?)',('test',json.dumps(data),1))


def test_later_candle_advances_old_price_with_explicit_candle_basis(tmp_path):
    series=snapshots(1,start=datetime(2026,11,11,14,29,tzinfo=VN))
    series[0]['quotes'][0]['source_match_time_raw']='2026/11/11 14:29:00'
    p=build_product({},series,{'now':'2026-11-11T15:00:00+07:00','latest_snapshot':series[-1]},config())
    before=deepcopy(p['selected']['bids']);db=tmp_path/'c.sqlite3';write_candle_cache(db)
    enrich_candle_statistics(p,db)
    assert p['selected']['last_price_vnd']==50900 and p['selected']['price_basis']=='ssi_ohlc_bar'
    assert p['selected'].get('turnover_vnd') is None and p['selected']['bids']==before


def test_official_daily_close_is_not_downgraded_to_cached_candle(tmp_path):
    series=snapshots(1,start=datetime(2026,11,11,14,29,tzinfo=VN))
    p=build_product({},series,{'now':'2026-11-11T16:00:00+07:00','latest_snapshot':series[-1]},config())
    r=next(r for r in p['ranking'] if r['symbol']=='FPT');r.update(last_price_vnd=51000,price_basis='ssi_daily_close',price_asof_date='2026-11-11',turnover_vnd=1e9,turnover_day='2026-11-11',turnover_basis='ssi_daily_summary')
    db=tmp_path/'c.sqlite3';write_candle_cache(db);enrich_candle_statistics(p,db)
    actual=next(r for r in p['ranking'] if r['symbol']=='FPT')
    assert actual['last_price_vnd']==51000 and actual['price_basis']=='ssi_daily_close'
    assert actual['turnover_vnd']==1e9


def test_expanded_scope_can_replay_existing_ticker_without_relabelling_history(tmp_path):
    series=snapshots(2);db=tmp_path/'o.sqlite3';cache=tmp_path/'latest.json'
    for s in series:store_snapshot(s,database=db,cache=cache)
    archive=read_chart_archive({'universe':['HOSE'],'symbol':['FPT']},config(),database=db)
    assert archive['universe']=='VN30' and archive['requested_universe']=='HOSE' and len(archive['points'])==2
    with pytest.raises(ValueError):read_chart_archive({'universe':['HNX_PILOT'],'symbol':['PVS']},config(),database=db)


def test_new_day_trade_does_not_make_previous_day_book_usable():
    now=datetime(2026,11,12,9,30,tzinfo=VN);r=raw()
    r.update(book_time='2026/11/11 14:29:00',trade_time='2026/11/12 09:30:00')
    quote=normalize_board([r],['FPT'],now=now,feed_healthy=True)[0]
    assert quote['trading_date']=='2026-11-12'
    snapshot={'source':'ssi_fastconnect','captured_at':now.isoformat(),'quotes':[quote]}
    row=analyze_book(snapshot,'FPT',1e9,config(),now=now)
    assert not row['valid'] and 'book_from_another_trading_day' in row['quality_flags']
