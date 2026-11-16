from copy import deepcopy
from datetime import datetime,timedelta
import json
import pytest
from src.data.ohlc_history import OHLCHistory,resolve_query,normalize_bars
from src.data.price_history import price_fields,add_interval_volumes
from src.data.ssi_feed import VN,SSIAPIError
from src.data.chart_archive import build_chart_archive
from tests.test_live_analytics import snapshots,config
from src.app import server


NOW=datetime(2026,11,11,14,40,tzinfo=VN)
def latest():
    s=snapshots(1,start=NOW)[0]
    s['quotes'][0]['source_match_time_raw']='2026/11/11 14:39:00'
    return s
def query(**extra):return {k:[v] for k,v in {'symbol':'FPT','range':'session','timeframe':'5m',**extra}.items()}
def candle(stamp='2026/11/11 09:15:00',**extra):
    return {'symbol':'FPT','tradingDate':stamp,'open':'50000','high':'50200','low':'49900','close':'50100','volume':'1000','value':'50050000',**extra}


def test_old_trade_is_not_promoted_by_a_fresh_quote_date():
    raw=latest()['quotes'][0];raw['source_match_time_raw']='2026/11/10 14:45:00'
    fields=price_fields(raw,NOW.isoformat())
    assert fields['last_price_vnd'] is None and not fields['price_available']
    assert fields['volume_shares'] is None


def test_prices_outside_continuous_market_remain_visible_without_a_valid_book():
    series=snapshots(3,start=datetime(2026,11,11,16,tzinfo=VN))
    archive=build_chart_archive(series,{},config())
    assert [p['last_price_vnd'] for p in archive['points']]==[50000,50010,50020]
    assert not any(p['valid'] for p in archive['points'])


def test_volume_differences_do_not_invent_a_baseline_or_span_gaps():
    points=[{'received_at':(NOW+timedelta(seconds=5*i)).isoformat(),'phase':'continuous_pm',
             'volume_shares':v,'price_available':True} for i,v in enumerate([1000,1000,1200,200])]
    add_interval_volumes(points)
    assert [p['interval_volume_shares'] for p in points]==[None,0,200,None]
    points[2]['received_at']=(NOW+timedelta(minutes=10)).isoformat()
    add_interval_volumes(points)
    assert points[2]['gap_before'] and points[2]['interval_volume_shares'] is None


@pytest.mark.parametrize('extra',[{'range':'bad'},{'symbol':'UNKNOWN'},{'symbol':'../env'},
    {'range':'1y','timeframe':'1m'},{'range':'custom','from':'2026-11-12','to':'2026-11-13'},
    {'range':'custom','from':'2026-11-11','to':'2026-11-01'}])
def test_rejects_unknown_or_excessive_history_queries(extra):
    with pytest.raises(ValueError):resolve_query(query(**extra),latest(),NOW)


def test_candles_use_official_extrema_and_never_fill_invalid_bars():
    spec=resolve_query(query(),latest(),NOW)
    records=[candle(),candle('2026/11/11 09:20:00',high='49800'),candle('2026/11/11 09:25:00',volume='-1'),
             candle('2026/11/11 09:30:00',symbol='VCB'),candle('2026/11/11 15:00:00')]
    bars,invalid=normalize_bars(records,spec)
    assert len(bars)==1 and invalid==3
    assert (bars[0]['open'],bars[0]['high'],bars[0]['low'],bars[0]['close'])==(50000,50200,49900,50100)
    assert bars[0]['volume_shares']==1000 and bars[0]['reference_price_vnd']==50000


def test_off_hours_relative_window_uses_the_last_actual_session():
    spec=resolve_query(query(range='1h',timeframe='1m'),latest(),datetime(2026,11,14,10,tzinfo=VN))
    assert spec['end'].date().isoformat()=='2026-11-11'
    assert (spec['end']-spec['start']).total_seconds()==3600


@pytest.mark.parametrize('board,hour,minute',[('HOSE',14,45),('HNX',15,0),('UPCOM',15,0)])
def test_short_view_keeps_the_end_of_each_boards_session(board,hour,minute):
    source=latest();source['quotes'][0]['market_code']=board
    source['quotes'][0]['source_match_time_raw']='2026/11/11 15:00:00'
    spec=resolve_query(query(range='1h',timeframe='1m'),source,datetime(2026,11,11,16,tzinfo=VN))
    assert (spec['end'].hour,spec['end'].minute)==(hour,minute)
    assert spec['start']==spec['end']-timedelta(hours=1)
    assert json.loads(spec['key'])[0]==(2 if board=='HOSE' else 3)
    full=resolve_query(query(),source,datetime(2026,11,11,16,tzinfo=VN))
    assert json.loads(full['key'])[0]==2


def test_upcom_chart_does_not_stop_while_its_market_is_still_open():
    source=latest();source['quotes'][0]['market_code']='UPCOM'
    now=datetime(2026,11,11,14,50,tzinfo=VN)
    spec=resolve_query(query(range='1h',timeframe='1m'),source,now)
    assert spec['end']==now and spec['start']==now-timedelta(hours=1)


def test_cache_paging_and_units_without_credentials_or_live_mutation(tmp_path):
    calls=[];source=latest();before=deepcopy(source)
    class Client:
        def _get(self,path,params):
            calls.append((path,params));assert path=='/api/v3/data/ohlc'
            start=datetime(2026,11,9,9,15)
            offset=0 if params['pageIndex']==1 else 1000
            n=1000 if offset==0 else 2
            return {'data':[candle((start+timedelta(minutes=i)).strftime('%Y/%m/%d %H:%M:%S')) for i in range(offset,offset+n)]}
    db=tmp_path/'history.sqlite3'
    service=OHLCHistory(database=db,session_factory=lambda env:Client(),latest_loader=lambda:source)
    result=service.read(query(range='1w',timeframe='1m'),now=NOW)
    again=service.read(query(range='1w',timeframe='1m'),now=NOW)
    assert len(calls)==2 and len(result['bars'])==1002
    assert all(' ' in params['from'] and params['pageSize']==1000 for _,params in calls)
    assert all(params['to'].endswith('23:59:59') for _,params in calls)
    assert result['price_unit']=='VND' and result['volume_unit']=='shares'
    assert again['cached'] and again['bars']==result['bars'] and source==before
    assert 'Authorization' not in json.dumps(result) and 'accessToken' not in json.dumps(result)


def test_history_route_does_not_request_the_live_state(monkeypatch):
    handler=object.__new__(server.Handler);handler.path='/api/price-history?symbol=FPT'
    monkeypatch.setattr(server,'build_state',lambda *a:pytest.fail('History requested Live'))
    monkeypatch.setattr(server,'read_price_history',lambda query:{'source':'ssi_fastconnect_ohlc','bars':[]})
    result=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:result.append((status,data)))
    handler.do_GET();assert result==[(200,{'source':'ssi_fastconnect_ohlc','bars':[]})]


@pytest.mark.parametrize('payload',[{'data':None},{'code':204,'msg':'No data'}])
def test_provider_null_data_means_no_candles_not_a_global_failure(tmp_path,payload):
    class Client:
        def _get(self,path,params):return payload
    service=OHLCHistory(database=tmp_path/'h.sqlite3',session_factory=lambda env:Client())
    result=service._fetch(resolve_query(query(),latest(),NOW),persist=False)
    assert result['bars']==[] and result['invalid_records']==0
    assert service.retry_at==0 and not service.database.exists()


def test_history_failure_sanitizes_provider_information(monkeypatch):
    handler=object.__new__(server.Handler);handler.path='/api/price-history?symbol=FPT'
    def fail(query):raise SSIAPIError('source_unavailable',400)
    monkeypatch.setattr(server,'read_price_history',fail)
    result=[];monkeypatch.setattr(server.Handler,'_json',lambda self,status,data:result.append((status,data)))
    handler.do_GET();assert result[0][0]==503 and result[0][1]['bars']==[]
