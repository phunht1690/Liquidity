"""History recovery is real OHLC, deduplicated and separate from recorded books."""
from copy import deepcopy
from datetime import datetime,timedelta
from threading import Event,Thread
import sqlite3
import time
import pytest

from src.data.ssi_feed import VN,SSIAPIError
from src.data.ohlc_history import OHLCHistory,resolve_query,normalize_bars
from src.data.price_archive import PriceArchive
from src.data.history_backfill import HistoryBackfill
from tests.test_ohlc_history import latest,query,candle

NOW=datetime(2026,11,14,10,tzinfo=VN)


def spec(day='2026-11-06',**extra):
    return resolve_query(query(**{'range':'custom','timeframe':'5m','from':day,'to':day,**extra}),latest(),NOW)


def data(s,records=None):
    rows,invalid=normalize_bars(records if records is not None else [candle(s['start'].strftime('%Y/%m/%d')+' 09:15:00')],s)
    return {'bars':rows,'invalid_records':invalid,'complete_range':True,'updated_at':NOW.isoformat()}


def test_historical_bars_recovered_without_existing_book_and_survive_restart(tmp_path):
    calls=[];before=deepcopy(latest())
    class Provider:
        def _get(self,path,params):calls.append(params);return {'data':[candle('2026/11/06 09:15:00')]}
    history=OHLCHistory(database=tmp_path/'chart.sqlite3',latest_loader=latest,session_factory=lambda env:Provider(),request_interval=0)
    history.background_fetch(spec())
    other=OHLCHistory(database=tmp_path/'chart.sqlite3',latest_loader=latest,session_factory=lambda env:pytest.fail('Cached history called SSI'))
    result=other.read(query(range='custom',**{'from':'2026-11-06','to':'2026-11-06'}),now=NOW)
    assert len(calls)==1 and result['local_archive'] and result['complete_range']
    assert result['bars'][0]['close']==50100 and latest()==before
    assert not (tmp_path/'chart.sqlite3').exists()  # No 128-filter cache pollution.
    with sqlite3.connect(tmp_path/'price_bars.sqlite3') as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}=={'price_bars','price_days'}
    assert not (tmp_path/'observations.sqlite3').exists()


def test_upsert_updates_candle_and_volume_without_duplicate_rows(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec()
    archive.record(data(s),s)
    archive.record(data(s,[candle('2026/11/06 09:15:00',close='50200',volume='3000')]),s)
    result=archive.read(s)
    assert len(result['bars'])==1 and result['bars'][0]['close']==50200
    assert result['bars'][0]['volume_shares']==3000


def test_calendar_retention_is_inclusive_and_does_not_expand_on_old_queries(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3')
    for day in ('2026-10-15','2026-10-16','2026-11-13'):
        s=spec(day);archive.record(data(s),s)
    with sqlite3.connect(archive.database) as db:
        assert [r[0] for r in db.execute('SELECT DISTINCT day FROM price_bars ORDER BY day')]==['2026-10-16','2026-11-13']
        assert [r[0] for r in db.execute('SELECT DISTINCT day FROM price_days ORDER BY day')]==['2026-10-16','2026-11-13']
    assert archive.read(spec('2026-10-15')) is None


def test_idle_cleanup_does_not_require_new_quotes_or_api_calls(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec()
    archive.record(data(s),s)
    archive.prune(datetime(2026,12,6,10,tzinfo=VN))
    assert archive.inventory()['bars']==0
    with sqlite3.connect(archive.database) as db:assert db.execute('SELECT COUNT(*) FROM price_days').fetchone()[0]==0
    assert not PriceArchive(tmp_path/'absent.sqlite3').database.exists()


def test_planner_requests_only_missing_dates_and_tickers_after_restart(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3')
    source=latest();source['quotes'][0]['source_match_time_raw']='2026/11/13 14:45:00'
    for tf in ('5m','1d'):
        s=spec('2026-11-12',timeframe=tf,**{'to':'2026-11-13'});archive.record(data(s),s)
    history=OHLCHistory(database=tmp_path/'filters.sqlite3',archive=archive)
    backfill=HistoryBackfill(history=history,retention_days=3)
    plan=backfill._plan(source,NOW)
    assert not any(p['symbol']=='FPT' for p in plan)
    assert backfill.state['checked_symbols']==1
    # Removing just one day does not make the other two dates re-download.
    with sqlite3.connect(archive.database) as db:db.execute("DELETE FROM price_days WHERE symbol='FPT' AND timeframe='5m' AND day='2026-11-12'")
    plan=backfill._plan(source,NOW)
    fpt=[p for p in plan if p['symbol']=='FPT']
    assert len(fpt)==1 and fpt[0]['timeframe']=='5m'
    assert fpt[0]['start'].date().isoformat()==fpt[0]['end'].date().isoformat()=='2026-11-12'


def test_catalog_only_weekend_startup_recovers_actual_history_without_waiting_for_a_trade(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3')
    history=OHLCHistory(database=tmp_path/'filters.sqlite3',archive=archive)
    source={'quotes':[{'symbol':'ABC','market_code':'HNX'},
                      {'symbol':'XYZ','market_code':'UPCOM'}],
            'membership':{'universes':{'HNX':['ABC'],'UPCOM':['XYZ']}}}
    before=deepcopy(source)
    backfill=HistoryBackfill(history=history,retention_days=3)
    plan=backfill._plan(source,NOW)
    assert {(p['symbol'],p['timeframe']) for p in plan}=={
        ('ABC','5m'),('ABC','1d'),('XYZ','5m'),('XYZ','1d')}
    assert all(p['end'].date()==(NOW-timedelta(days=1)).date() for p in plan)
    assert backfill.state['total_symbols']==2
    assert source==before and archive.inventory()['bars']==0


def test_catalog_only_off_hours_chart_uses_last_actual_candle_day(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec('2026-11-12')
    archive.record(data(s,[candle('2026/11/12 09:15:00')]),s)
    source=deepcopy(latest());row=source['quotes'][0]
    row.update(source_match_time_raw=None,trading_date=None)
    before=deepcopy(source)
    history=OHLCHistory(database=tmp_path/'filters.sqlite3',archive=archive,
        latest_loader=lambda:source,session_factory=lambda env:pytest.fail('Existing session should be read locally'))
    result=history.read(query(range='session',timeframe='5m'),now=NOW)
    assert result['requested_from'].startswith('2026-11-12')
    assert result['bars'][0]['trading_date']=='2026-11-12'
    assert source==before  # No fake live quote or last-trade timestamp.


@pytest.mark.parametrize('explicit,clock',[(True,NOW),(False,datetime(2026,11,16,10,tzinfo=VN))])
def test_chart_does_not_retarget_explicit_date_or_an_open_market_to_old_candles(tmp_path,explicit,clock):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec('2026-11-12')
    archive.record(data(s,[candle('2026/11/12 09:15:00')]),s)
    source=deepcopy(latest());source['quotes'][0].update(source_match_time_raw=None,trading_date=None)
    calls=[]
    class Provider:
        def _get(self,path,params):calls.append(params);return {'data':[]}
    history=OHLCHistory(database=tmp_path/'filters.sqlite3',archive=archive,
        latest_loader=lambda:source,session_factory=lambda env:Provider(),request_interval=0)
    requested=query(range='custom',**{'from':'2026-11-14','to':'2026-11-14'}) if explicit else query(range='session')
    result=history.read(requested,now=clock)
    expected='2026-11-14' if explicit else '2026-11-16'
    assert result['requested_from'].startswith(expected) and result['bars']==[]
    assert len(calls)==1 and calls[0]['from'].startswith(expected.replace('-','/'))


def test_partial_or_invalid_response_cannot_mark_an_entire_session_complete(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec()
    for change in ({'complete_range':False},{'invalid_records':1}):
        archive.record({**data(s),**change},s)
        assert archive.read(s) is None
        result=archive.read(s,allow_partial=True)
        assert result['complete_range'] is False and len(result['bars'])==1
    short={**s,'start':s['start'].replace(hour=10)}
    archive.record(data(short),short)
    assert archive.read(s) is None


def test_empty_day_is_cached_but_is_not_claimed_to_have_trading_data(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec('2026-11-14')
    archive.record(data(s,[]),s)
    result=archive.read(s)
    assert result['bars']==[] and result['complete_range']
    assert archive.inventory()['symbols']==archive.inventory()['bars']==0
    later={**s,'now':NOW+timedelta(seconds=31)}
    assert archive.read(later) is None  # Current day is not a completed session.


def test_closed_empty_day_rechecks_if_provider_was_late(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec('2026-11-13')
    archive.record(data(s,[]),s)
    assert archive.read(s)['bars']==[]
    assert archive.read({**s,'now':NOW+timedelta(hours=7)}) is None


def test_old_confirmed_empty_dates_do_not_fill_queue_again_every_six_hours(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec('2026-11-07')
    archive.record(data(s,[]),s)
    later={**s,'now':NOW+timedelta(hours=7)}
    assert archive.missing_ranges('FPT','5m',s['start'].date(),s['end'].date(),later['now'])==[]
    assert archive.read(later)['bars']==[]


def test_archive_uses_only_same_day_reference_and_never_fabricates_bars(tmp_path):
    archive=PriceArchive(tmp_path/'bars.sqlite3');s=spec()
    rows=[candle('2026/11/06 09:15:00'),candle('2026/11/06 10:15:00')]
    archive.record(data(s,rows),s)
    result=archive.read(s)
    assert len(result['bars'])==2
    assert all(b['reference_price_vnd'] is None for b in result['bars'])
    assert not any('bids' in b or 'asks' in b for b in result['bars'])


def test_chart_request_goes_before_waiting_background_request(tmp_path):
    entered=Event();release=Event();calls=[]
    class Provider:
        def _get(self,path,params):
            calls.append(params['symbol'])
            if len(calls)==1:entered.set();assert release.wait(3)
            return {'data':[]}
    history=OHLCHistory(database=tmp_path/'h.sqlite3',session_factory=lambda env:Provider(),request_interval=0)
    threads=[Thread(target=history._request,args=({'symbol':'FPT'},),kwargs={'background':True}),
        Thread(target=history._request,args=({'symbol':'HPG'},),kwargs={'background':True}),
        Thread(target=history._request,args=({'symbol':'VCB'},))]
    threads[0].start();assert entered.wait(3)
    threads[1].start();threads[2].start()
    deadline=time.monotonic()+3
    while time.monotonic()<deadline and not history.foreground_waiters:time.sleep(.005)
    assert history.foreground_waiters==1
    release.set()
    for thread in threads:thread.join(3);assert not thread.is_alive()
    assert calls==['FPT','VCB','HPG']


def test_account_backoff_stops_other_history_calls_without_key_rotation(tmp_path):
    calls=[]
    class Provider:
        def _get(self,*a):calls.append(1);raise SSIAPIError('rate_limited',429,120)
    history=OHLCHistory(database=tmp_path/'h.sqlite3',session_factory=lambda env:Provider(),request_interval=0)
    runner=HistoryBackfill(history=history)
    assert not runner.step(spec(),NOW)
    assert runner.status()['status']=='backoff' and runner.status()['retry_after']>=119
    assert not runner.step(spec(),NOW)
    assert len(calls)==1 and not history.archive.database.exists()


def test_ticker_failure_does_not_stop_backfill_for_all_other_stocks(tmp_path):
    class Provider:
        def _get(self,*a):raise SSIAPIError('source_unavailable',400)
    history=OHLCHistory(database=tmp_path/'h.sqlite3',session_factory=lambda env:Provider(),request_interval=0)
    runner=HistoryBackfill(history=history)
    assert not runner.step(spec(),NOW)
    assert history.retry_at==0 and runner.failures[('FPT','5m')]>0
