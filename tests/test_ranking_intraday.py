from copy import deepcopy
from datetime import datetime,timedelta
from threading import RLock
import pytest
from src.data.ssi_feed import VN,SSIAPIError
from src.data.ranking_intraday import IntradaySparklines,compact_session,line_for_quote

NOW=datetime(2026,11,13,10,tzinfo=VN)


def quote(symbol='FPT',**extra):
    return {'symbol':symbol,'trading_date':'2026-11-13','reference_price_vnd':50000,
        'source_match_time_raw':'2026/11/13 09:59:30','last_price_vnd':50100,**extra}


def bar(minute,price,day=13,hour=9):
    return {'timestamp':datetime(2026,11,day,hour,minute,tzinfo=VN).isoformat(),'close':price}


def session(points=None):
    return compact_session({'bars':points or [bar(15,50000),bar(20,50200)],'updated_at':NOW.isoformat()},quote(),NOW)


def test_provider_bars_are_sorted_deduplicated_and_limited_to_one_actual_day():
    rows=[bar(20,50200),bar(15,49900),bar(25,1,day=12),bar(15,50000),bar(5,9,hour=10),bar(30,-1)]
    result=compact_session({'bars':rows},quote(),NOW)
    assert result['day']=='2026-11-13'
    assert [p['last_price_vnd'] for p in result['points']]==[50000,50200]
    assert result['reference_price_vnd']==50000


def test_intraday_lines_do_not_invent_overnight_or_lunch_segments():
    result=compact_session({'bars':[bar(25,50000,hour=11),bar(0,50100,hour=13)]},quote(),NOW.replace(hour=14))
    assert result['points'][1]['gap_before']
    assert compact_session({'bars':[]},quote(),NOW)['points']==[]


def test_current_trade_replaces_same_bucket_instead_of_creating_poll_sawtooth():
    cached=session([bar(50,50000),bar(55,50200)])
    cached['updated_at']='2026-11-13T09:57:00+07:00'
    cached['points'][-1]['gap_before']=True
    before=deepcopy(cached)
    result=line_for_quote(cached,quote(),NOW)
    assert len(result['points'])==2 and result['points'][-1]['last_price_vnd']==50100
    assert result['points'][-1]['gap_before']
    assert result['change_percent']==pytest.approx(.2)
    assert cached==before


def test_trade_older_than_candle_fetch_cannot_overwrite_provider_close():
    cached=session([bar(50,50000),bar(55,50200)])
    result=line_for_quote(cached,quote(),NOW)
    assert result['points'][-1]['last_price_vnd']==50200


def test_new_day_trade_never_connects_to_previous_days_line():
    cached=session([bar(15,50000,day=12),bar(20,50200,day=12)])
    cached['reference_price_vnd']=49000
    result=line_for_quote(cached,quote(last_price_vnd=51000),NOW)
    assert result['day']=='2026-11-13' and len(result['points'])==1
    assert all(p['timestamp'].startswith('2026-11-13') for p in result['points'])
    assert result['change_percent']==pytest.approx(2)


def test_quiet_symbol_keeps_its_last_real_session_with_that_sessions_reference():
    cached=session([bar(15,50000,day=12),bar(20,50200,day=12)])
    cached['reference_price_vnd']=49000
    result=line_for_quote(cached,quote(source_match_time_raw='2026/11/12 09:20:00'),NOW)
    assert result['day']=='2026-11-12'
    assert result['change_percent']==pytest.approx((50200/49000-1)*100)


def test_unavailable_history_gives_at_most_one_real_trade_without_a_fake_line():
    result=line_for_quote(None,quote(),NOW)
    assert len(result['points'])==1 and result['points'][0]['last_price_vnd']==50100
    assert line_for_quote(None,quote(source_match_time_raw=None),NOW)['points']==[]


def test_all_tracked_symbols_are_requested_even_outside_current_filter(tmp_path,monkeypatch):
    service=IntradaySparklines(database=tmp_path/'m.sqlite3',enabled=False)
    received=[];monkeypatch.setattr(service,'request',lambda q,n,priority:received.append(q['symbol']))
    quotes=[quote(f'A{i:03d}') for i in range(439)]
    product={'runtime':{'now':NOW.isoformat()},'ranking':[{'symbol':'A002'}],'selected':{'symbol':'A002'}}
    service.cache['A002']=session()
    result=service.enrich(product,{'quotes':quotes})
    assert len(received)==len(set(received))==439
    assert result['ranking_trend']['ready']==1 and result['ranking_trend']['tracked']==439
    assert result['ranking'][0]['price_trend_source']=='ssi_ohlc_5m'
    assert not service.database.exists()


def test_queue_deduplicates_repeated_product_polls_and_promotes_selected_symbol(tmp_path):
    service=IntradaySparklines(database=tmp_path/'m.sqlite3')
    class Running:
        def is_alive(self):return True
    service.thread=Running()
    service.request(quote(),NOW,10);service.request(quote(),NOW,10);service.request(quote(),NOW,0)
    assert len(service.pending)==1 and service.pending['FPT'][0]==0
    assert service.queue.qsize()==2
    service.cache['VCB']=session();service.request(quote('VCB'),NOW)
    assert 'VCB' not in service.pending


def test_cached_previous_day_does_not_skip_the_new_day_backfill(tmp_path):
    service=IntradaySparklines(database=tmp_path/'m.sqlite3')
    class Running:
        def is_alive(self):return True
    service.thread=Running();item=session();item['checked_at']=(NOW-timedelta(days=1)).isoformat()
    service.cache['FPT']=item;service.request(quote(),NOW)
    assert 'FPT' in service.pending


def test_cold_symbols_are_not_starved_by_refreshes_of_existing_curves(tmp_path):
    service=IntradaySparklines(database=tmp_path/'m.sqlite3')
    class Running:
        def is_alive(self):return True
    service.thread=Running();item=session();item['checked_at']=(NOW-timedelta(minutes=10)).isoformat()
    service.cache['FPT']=item
    service.request(quote(),NOW,10);service.request(quote('VCB'),NOW,10)
    assert service.queue.get_nowait()[2]=='VCB'


def test_cache_survives_restart_without_waiting_for_api(tmp_path):
    database=tmp_path/'m.sqlite3';item=session()
    service=IntradaySparklines(database=database,enabled=False);service._store('FPT',item)
    reloaded=IntradaySparklines(database=database,enabled=False)
    assert reloaded.cache['FPT']==item and reloaded.history is None


@pytest.mark.parametrize('mixed',[False,True])
def test_heading_uses_actual_line_session_instead_of_weekend_receipt_date(tmp_path,mixed):
    service=IntradaySparklines(database=tmp_path/'m.sqlite3',enabled=False)
    service.cache={'FPT':session(),'VCB':session([bar(15,49000,day=12),bar(20,49100,day=12)]) if mixed else session()}
    source={'quotes':[quote(),quote('VCB')]}
    product={'runtime':{'now':'2026-11-14T10:00:00+07:00'},'selected':{'symbol':'FPT'},'ranking':[{'symbol':'FPT'},{'symbol':'VCB'}]}
    result=service.enrich(product,source)
    assert result['ranking_history_day']==(None if mixed else '2026-11-13')
    assert result['ranking_trend']['day']==result['ranking_history_day']


def test_backfill_reuses_shared_ohlc_client_without_expanding_large_chart_cache(tmp_path):
    calls=[]
    class Provider:
        def _fetch(self,spec,*,persist):
            calls.append((spec,persist));return {'bars':[bar(15,50000),bar(20,50200)]}
    service=IntradaySparklines(database=tmp_path/'m.sqlite3',history=Provider(),enabled=False)
    result=service._fetch('FPT',quote(),NOW)
    assert len(calls)==1 and calls[0][1] is False
    spec=calls[0][0]
    assert spec['timeframe']=='5m' and spec['symbol']=='FPT'
    assert spec['end'].date()==spec['start'].date()==NOW.date() and result['day']=='2026-11-13'


def test_empty_session_alone_uses_a_short_fallback_lookback(tmp_path):
    calls=[]
    class Provider:
        def _fetch(self,spec,*,persist):
            calls.append(spec)
            return {'bars':[] if len(calls)==1 else [bar(15,50000,day=12),bar(20,50200,day=12)]}
    service=IntradaySparklines(database=tmp_path/'m.sqlite3',history=Provider(),enabled=False)
    result=service._fetch('FPT',quote(),NOW)
    assert len(calls)==2 and (calls[1]['end']-calls[1]['start']).days==10
    assert result['day']=='2026-11-12'


def test_429_respects_cooldown_without_retrying_other_keys(tmp_path):
    calls=[]
    class Provider:
        lock=RLock();retry_at=0
        def _fetch(self,*args,**kwargs):
            calls.append(1);service.stop.set();raise SSIAPIError('rate_limited',429,120)
    provider=Provider();service=IntradaySparklines(database=tmp_path/'m.sqlite3',history=provider,delay=0)
    service.quotes['FPT']=quote();service.pending['FPT']=(0,1);service.queue.put((0,1,'FPT'))
    service._run()
    assert len(calls)==1 and provider.retry_at==service.retry_at
    assert service.retry_at>0


def test_ticker_specific_rejection_does_not_block_the_remaining_universe(tmp_path):
    class Provider:
        lock=RLock();retry_at=0
        def _fetch(self,*args,**kwargs):
            service.stop.set();raise SSIAPIError('source_unavailable',400)
    provider=Provider();service=IntradaySparklines(database=tmp_path/'m.sqlite3',history=provider,delay=0)
    service.quotes['FPT']=quote();service.pending['FPT']=(0,1);service.queue.put((0,1,'FPT'))
    service._run()
    assert service.retry_at==provider.retry_at==0 and service.failures['FPT']>0
    assert service.cache['FPT']['points']==[] and service.cache['FPT']['fetch_status']=='unavailable'
