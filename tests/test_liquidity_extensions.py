"""Hand-checkable extended depth and same-time volume; no provider credentials."""
from copy import deepcopy
from datetime import datetime,date,timedelta
from threading import Event
from unittest.mock import Mock
import sqlite3
import pytest

from src.data.ssi_feed import normalize_board,VN
from src.data.liquidity import analyze_book
from src.data.price_archive import PriceArchive
from src.data.volume_context import volume_context
from src.data.market_activity import normalize as normalize_market,MarketActivity
from src.data.daily_summary import normalize as normalize_daily,DailySummaries
from src.data.product import build_product,export_product
import csv,io
from tests.test_live_analytics import snapshots
from tests.test_ssi_feed import raw
from tests.test_live_analytics import config
from src.data.chart_archive import build_chart_archive


def extended_book(padding=False):
    now=datetime(2026,11,9,9,30,tzinfo=VN)
    data=raw();data.update(board='HNX',master_date='2026-11-09',floor='45000',ceiling='55000')
    data['bids']=[[str(50000-i*100),'1000'] for i in range(10)]
    data['asks']=[[str(50100+i*100),'1000'] for i in range(10)]
    if padding:
        data['bids'][3:]=[['0','0']]*7;data['asks'][3:]=[['0','0']]*7
    return data,now


def analyzed(data,now):
    quote=normalize_board([data],['FPT'],now=now,allowed_boards=('HOSE','HNX','UPCOM'))[0]
    saved={'source':'ssi_fastconnect','captured_at':now.isoformat(),'quotes':[quote]}
    return analyze_book(saved,'FPT',200_000_000,config(),now=now)


def test_ten_real_levels_change_capacity_and_depth_consistently():
    data,now=extended_book();row=analyzed(data,now)
    assert row['valid'] and row['book_level_count']==10
    assert row['known_bid_levels']==row['known_ask_levels']==10
    assert row['depth_min_vnd']==495_500_000
    assert row['buy']['requested_shares']==3900 and row['buy']['fill_ratio']==1
    assert row['buy']['filled_value_vnd']==195_960_000
    old=deepcopy(data);old['bids']=old['bids'][:3];old['asks']=old['asks'][:3]
    three=analyzed(old,now)
    assert three['valid'] and three['book_level_count']==3
    assert three['depth_min_vnd']==149_700_000
    assert three['buy']['fill_ratio']==pytest.approx(3000/3900)
    assert three['buy']['flag']=='partial_visible_levels'


def test_zero_padding_does_not_invent_seven_more_levels():
    data,now=extended_book(padding=True);row=analyzed(data,now)
    assert row['valid'] and row['book_level_count']==3
    assert row['depth_min_vnd']==149_700_000


def test_replay_keeps_legacy_depth_and_marks_the_change_in_recorded_levels():
    data,now=extended_book();full=normalize_board([data],['FPT'],now=now,allowed_boards=('HNX',))[0]
    old=deepcopy(full);old['bids']=old['bids'][:3];old['asks']=old['asks'][:3]
    series=[{'source':'ssi_fastconnect','collection_mode':'auto_collector','dataset_id':'old','captured_at':now.isoformat(),'quotes':[old],'membership':{'universes':{'HNX':['FPT']}}},
            {'source':'ssi_fastconnect','collection_mode':'auto_collector','dataset_id':'new','captured_at':(now+timedelta(seconds=5)).isoformat(),'quotes':[full],'membership':{'universes':{'HNX':['FPT']}}}]
    result=build_chart_archive(series,{'universe':['HNX'],'symbol':['FPT']},config())
    assert [p['known_bid_levels'] for p in result['points']]==[3,10]
    assert result['points'][1]['gap_before']


@pytest.mark.parametrize('bad',[['bad','1000'],['50000','-100'],['40000','1000']])
def test_unverified_deeper_level_is_not_used_for_hnx(bad):
    data,now=extended_book();data['bids'][7]=bad
    assert not analyzed(data,now)['valid']


def archive_fixture(tmp_path):
    path=tmp_path/'bars.sqlite3';archive=PriceArchive(path)
    today=date(2026,11,16);prior=[];cursor=today-timedelta(days=1)
    while len(prior)<20:
        if cursor.weekday()<5:prior.append(cursor.isoformat())
        cursor-=timedelta(days=1)
    with sqlite3.connect(path) as db:
        archive._create(db)
        for day in prior:
            db.execute('INSERT INTO price_days VALUES(?,?,?,?,?,?)',('FPT','1d',day,day+'T16:00:00+07:00',1,1))
            db.execute('INSERT INTO price_days VALUES(?,?,?,?,?,?)',('FPT','5m',day,day+'T16:00:00+07:00',1,3))
            for tf,time,volume in [('1d','00:00',3000),('5m','09:15',1000),('5m','09:20',2000),('5m','09:25',9000)]:
                db.execute('INSERT INTO price_bars VALUES(?,?,?,?,?,?,?,?,?,?)',('FPT',tf,day+'T'+time+':00+07:00',day,50000,50100,49900,50000,volume,None))
        for time,volume in [('09:15',2000),('09:20',4000),('09:25',999999)]:
            db.execute('INSERT INTO price_bars VALUES(?,?,?,?,?,?,?,?,?,?)',('FPT','5m','2026-11-16T'+time+':00+07:00','2026-11-16',50000,50100,49900,50000,volume,None))
    return path,prior


def test_volume_compares_completed_candles_at_the_same_times(tmp_path):
    path,_=archive_fixture(tmp_path)
    row={'symbol':'FPT','trade_time':'2026/11/16 09:27:00','volume_shares':9999999,'price_basis':'last_received_trade'}
    result=volume_context(row,datetime(2026,11,16,9,28,tzinfo=VN),path)
    assert result['basis']=='aligned_5m_candles' and result['until']=='09:25'
    assert result['slots']==2 and result['sessions']==20
    assert result['volume_shares']==6000 and result['average_volume_shares']==3000 and result['ratio']==2


def test_missing_historical_slot_does_not_become_zero_or_full_day(tmp_path):
    path,prior=archive_fixture(tmp_path)
    with sqlite3.connect(path) as db:db.execute("DELETE FROM price_bars WHERE day=? AND timeframe='5m' AND substr(stamp,12,5)='09:20'",(prior[-1],))
    result=volume_context({'symbol':'FPT','trade_time':'2026/11/16 09:27:00'},datetime(2026,11,16,9,28,tzinfo=VN),path)
    assert result['sessions']==19 and result['ratio'] is None and result['average_volume_shares'] is None


def test_daily_zero_volume_is_preserved_and_today_is_not_its_own_baseline(tmp_path):
    path,_=archive_fixture(tmp_path)
    result=volume_context({'symbol':'FPT','price_basis':'ssi_daily_close','price_asof_date':'2026-11-16','volume_shares':0},datetime(2026,11,16,16,tzinfo=VN),path)
    assert result['basis']=='daily' and result['sessions']==20
    assert result['volume_shares']==0 and result['average_volume_shares']==3000 and result['ratio']==0


def test_market_totals_keep_null_and_zero_distinct():
    now=datetime(2026,11,16,16,tzinfo=VN)
    result=normalize_market([{'tradingDate':'2026/11/13','totalMatch':'100','totalMatchValue':'5000000','totalDeal':'0','totalDealValue':None,'totalAdvanceStock':'0'}],'HOSE',now)
    assert result['matched_value_vnd']==5_000_000
    assert result['negotiated_volume_shares']==0 and result['negotiated_value_vnd'] is None
    assert 'totalAdvanceStock' not in result
    assert normalize_market([{'tradingDate':'2099/01/01','totalMatchValue':'1'}],'HOSE',now) is None


def test_market_cache_returns_without_waiting_for_ssi(tmp_path):
    entered=Event();release=Event()
    def get(route,query):
        entered.set();release.wait(2)
        assert route=='/api/v3/data/indexSummary' and query=={'board':'HOSE'}
        return [{'tradingDate':'2026/11/13','totalMatchValue':'5000000','totalDealValue':'0'}]
    client=Mock();client._get.side_effect=get
    service=MarketActivity(tmp_path/'summary.sqlite3',factory=lambda *_:client)
    try:
        initial=service.read();assert entered.wait(1)
        assert initial['items']==[]
    finally:release.set();service.close()
    assert service.cache['HOSE']['matched_value_vnd']==5_000_000
    assert service.cache['HOSE']['negotiated_value_vnd']==0
    assert client._get.call_count==1


def test_foreign_shares_are_available_without_guessing_currency_units():
    result=normalize_daily([{'symbol':'SHS','tradingDate':'2026/11/13','close':'13200','totalMatch':'1000','totalMatchValue':'13200000',
        'totalForeignBuy':'100','totalForeignSell':'0','remainForeignRoom':'5000','totalForeignRoom':'10000','totalForeignBuyValue':'1320'}],
        'SHS',datetime(2026,11,16,16,tzinfo=VN))
    assert result['foreign_buy_shares']==100 and result['foreign_sell_shares']==0
    assert result['foreign_room_remaining_shares']==5000
    assert result['foreign_value_unit']=='provider_unverified' and result['foreign_buy_value_raw']==1320
    assert 'foreign_buy_value_vnd' not in result


def test_previous_daily_reference_remains_dated_without_overwriting_live_statistics(tmp_path):
    series=snapshots(1,start=datetime(2026,11,16,10,tzinfo=VN))
    product=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1],'auth':{'websocket_status':'connected'}},config())
    before=deepcopy(product['selected'])
    service=DailySummaries(database=tmp_path/'s.sqlite3');service.request=lambda *a,**k:None
    service.cache={'FPT':{'symbol':'FPT','source':'ssi_securities_summary','day':'2026-11-13','close':1,
        'volume_shares':1,'turnover_vnd':1,'foreign_buy_shares':100,'foreign_sell_shares':0,
        'open_price_vnd':1,'received_at':'2026-11-16T08:00:00+07:00'}}
    service.enrich(product)
    row=product['selected']
    assert row['last_price_vnd']==before['last_price_vnd'] and row.get('open_price_vnd')==before.get('open_price_vnd')
    assert row.get('turnover_vnd') is None and row.get('daily_statistics') is None
    assert row['daily_reference']['day']=='2026-11-13' and row['daily_reference']['foreign_buy_shares']==100
    exported=next(r for r in csv.DictReader(io.StringIO(export_product(product).decode('utf-8-sig'))) if r['symbol']=='FPT')
    assert exported['summary_day']=='2026-11-13' and exported['foreign_buy_shares']=='100'
    assert exported['foreign_sell_shares']=='0' and exported['turnover_vnd']==''
    assert 'foreign_buy_value_vnd' not in exported
    service.cache['FPT']['day']='2099-01-01'
    fresh=build_product({},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1]},config())
    service.enrich(fresh)
    assert 'daily_reference' not in fresh['selected'] and 'daily_statistics' not in fresh['selected']
