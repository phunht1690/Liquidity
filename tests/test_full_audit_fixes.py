"""Regressions for actual financial/data inconsistencies found in the audit."""
from copy import deepcopy
from datetime import datetime,timedelta
import pytest

from src.data.ssi_feed import VN,normalize_board,reference_for_day
from src.data.ohlc_history import normalize_bars,OHLCHistory
from src.data.price_archive import PriceArchive
from src.data.archived_statistics import enrich_archived_statistics
from src.data.alert_history import attach_history
from src.data.product import build_product,export_product
from tests.test_ssi_feed import raw
from tests.test_live_analytics import snapshots,config
from tests.test_history_backfill import spec,data,NOW


def product():
    series=snapshots(1,start=datetime(2026,11,13,14,29,tzinfo=VN))
    return build_product({},series,{'now':NOW.isoformat(),'latest_snapshot':series[-1]},config())


def daily_archive(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3')
    s=spec('2026-11-13',timeframe='1d');archive.record(data(s),s)
    return archive.database


def test_completed_daily_bars_fill_price_and_ohlc_without_creating_fake_turnover(tmp_path):
    path=daily_archive(tmp_path);p=product();before=deepcopy(p['selected'])
    p['selected'].update(last_price_vnd=None,volume_shares=None)
    next(r for r in p['ranking'] if r['symbol']=='FPT').update(last_price_vnd=None,volume_shares=None)
    enrich_archived_statistics(p,path);r=p['selected']
    assert r['last_price_vnd']==50100 and r['volume_shares']==1000
    assert r['price_basis']=='ssi_ohlc_daily' and r['statistics_day']=='2026-11-13'
    assert (r['open_price_vnd'],r['high_price_vnd'],r['low_price_vnd'])==(50000,50200,49900)
    assert r.get('turnover_vnd') is None  # close * volume is not actual matched money.
    for key in ('bids','asks','buy','sell','analysis_at','depth_min_vnd'):assert r[key]==before[key]
    assert 'statistics_source' in export_product(p).decode('utf-8-sig').splitlines()[0]


def test_real_daily_summary_is_never_downgraded_to_daily_candle(tmp_path):
    path=daily_archive(tmp_path);p=product()
    for r in [p['selected'],*p['ranking']]:
        if r['symbol']=='FPT':r.update(last_price_vnd=50200,price_basis='ssi_daily_close',price_asof_date='2026-11-13',daily_statistics={'day':'2026-11-13'},turnover_basis='ssi_daily_summary',turnover_vnd=50005000)
    enrich_archived_statistics(p,path)
    assert p['selected']['last_price_vnd']==50200 and p['selected']['turnover_vnd']==50005000


def test_daily_archive_never_overwrites_a_newer_intraday_trade(tmp_path):
    path=daily_archive(tmp_path);p=product()
    p['runtime']['now']='2026-11-16T10:00:00+07:00'
    for r in [p['selected'],*p['ranking']]:
        if r['symbol']=='FPT':r.update(last_price_vnd=51000,trade_time='2026/11/16 09:59:59',trading_date='2026-11-16')
    enrich_archived_statistics(p,path)
    assert p['selected']['last_price_vnd']==51000 and p['selected']['price_basis']=='last_received_trade'


def test_incomplete_daily_bar_cannot_be_called_a_close(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec('2026-11-13',timeframe='1d')
    s['now']=datetime(2026,11,13,10,tzinfo=VN);archive.record(data(s),s)
    p=product();before=deepcopy(p)
    enrich_archived_statistics(p,archive.database)
    assert p==before


def test_new_master_reference_is_not_applied_to_previous_sessions_price():
    r=raw();r.update(master_date='2026-11-10',refPrice='51000')
    q=normalize_board([r],['FPT'],now=datetime(2026,11,10,8,tzinfo=VN))[0]
    assert q['reference_date']=='2026-11-10' and q['trading_date']=='2026-11-09'
    assert q['change_percent'] is None
    assert reference_for_day(q,'2026-11-09') is None
    assert reference_for_day(q,'2026-11-10')==51000


def test_candle_reference_must_match_its_own_day_not_quotes_latest_date():
    s=spec('2026-11-13');s['quote'].update(reference_price_vnd=52000,reference_date='2026-11-16',trading_date='2026-11-13')
    rows,invalid=normalize_bars([{'symbol':'FPT','tradingDate':'2026/11/13 09:15:00','open':'50000','high':'50200','low':'49900','close':'50100','volume':'100'}],s)
    assert invalid==0 and rows[0]['reference_price_vnd'] is None


def test_legacy_filter_cache_cannot_reintroduce_wrong_session_reference(tmp_path):
    s=spec('2026-11-13',timeframe='1m')
    s['quote'].update(reference_price_vnd=52000,reference_date='2026-11-16',trading_date='2026-11-13')
    latest={'membership':{'universes':{'VN30':['FPT']}},'quotes':[s['quote']]}
    history=OHLCHistory(database=tmp_path/'h.sqlite3',latest_loader=lambda:latest,session_factory=lambda env:pytest.fail('Cache unexpectedly called network'))
    old=data(s);old['bars'][0]['reference_price_vnd']=52000;history._store(s['key'],old)
    result=history.read({'symbol':['FPT'],'range':['custom'],'timeframe':['1m'],'from':['2026-11-13'],'to':['2026-11-13']},now=NOW)
    assert result['cached'] and result['bars'][0]['reference_price_vnd'] is None
    assert history._cached(s['key'])[0]['bars'][0]['reference_price_vnd']==52000


@pytest.mark.parametrize('gap',[10,300])
def test_alert_disappearance_after_gap_does_not_invent_end_time(tmp_path,gap):
    series=snapshots(1,start=datetime(2026,11,13,10,tzinfo=VN))
    p=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1],'auth':{'websocket_status':'connected'}},config())
    assert p['analysis']['mode']=='live' and p['alerts']
    path=tmp_path/'alerts.sqlite3';attach_history(p,path);start=p['analysis']['asof']
    later=deepcopy(p);later['analysis']['asof']=(datetime.fromisoformat(start)+timedelta(seconds=gap)).isoformat();later['alerts']=[]
    attach_history(later,path)
    assert later['alert_history']
    expected=start if gap>35 else later['analysis']['asof']
    assert all(r['resolved_at']==expected for r in later['alert_history'])
