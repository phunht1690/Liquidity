"""Product behavior from hand-checkable fixtures, including saved-session references."""
from copy import deepcopy
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
import csv,io,json,re
import pytest
from tests.test_live_analytics import snapshots,config
from tests.test_ssi_feed import client,raw
from src.data.product import build_product,export_product
from src.data.ssi_feed import SSIAPIError
from src.app import server

def product(series,query=None,**extra):
    rt={'now':series[-1]['captured_at'],'latest_snapshot':series[-1],'stale_capture':False,
        'auth':{'websocket_status':'connected'},**extra}
    return build_product(query or {},series,rt,config())

def after_hours():
    regular=snapshots(3)
    last=deepcopy(regular[-1]);last['captured_at']=last['captured_at'][:10]+'T15:00:00+07:00';last['dataset_id']='closed'
    for row in last['quotes']:
        row['last_price_vnd']=55000;row['volume_shares']=9999
        row['bids']=[{'price':55000,'volume':0}]*3;row['asks']=[{'price':55000,'volume':0}]*3
        row['book_flags']=['auction_observation']
    return regular+[last]

def test_live_product_has_four_computable_outputs_without_composite():
    result=product(snapshots(2));r=result['selected']
    assert result['analysis']['mode']=='live' and r['valid']
    assert r['spread_vnd']==100 and r['spread_bps']>0
    assert r['depth_min_vnd']>0 and 0<r['buy_share']<1
    assert r['buy']['requested_shares']>0 and r['buy']['fill_ratio']<1
    assert 'lqs' not in r and 'methodology' not in result and 'forecast' not in json.dumps(result)
    assert set(r).isdisjoint({'amihud_5m','ofi_l1','ofi_3','ofi_normalized','component_percentiles'})

def test_closed_market_keeps_latest_trade_and_explicit_saved_book():
    series=after_hours();result=product(series);r=result['selected']
    assert result['analysis']['mode']=='saved' and not result['analysis']['live_alerts']
    assert result['analysis']['asof']==series[-2]['captured_at']
    assert r['last_price_vnd']==55000 and r['volume_shares']==9999
    assert r['bids'][0]['price']==50000 and r['spread_vnd']==100
    assert r['analysis_at']!=result['updated_at'] and result['analysis_dataset_id']!=result['market_dataset_id']

def test_current_chart_keeps_real_sides_and_disconnect_gaps():
    result=product(snapshots(3,step=100))
    assert [p['gap_before'] for p in result['history']]==[False,True,True]
    assert all(p['depth_min_vnd']==min(p['depth_bid_vnd'],p['depth_ask_vnd']) for p in result['history'])
    assert all(p['spread_vnd']==100 for p in result['history'])

def test_no_saved_regular_book_does_not_invent_static_analytics():
    result=product(after_hours()[-1:])
    assert result['analysis']['mode']=='waiting' and not result['selected']['valid']
    assert result['selected']['last_price_vnd']==55000 and result['selected']['buy'] is None
    assert not result['cost_curve'] and not result['alerts']

def test_lost_stream_marks_reference_as_saved_not_live_signal():
    result=product(snapshots(2),auth={'websocket_status':'disconnected'})
    assert result['analysis']['mode']=='saved' and not result['analysis']['live_alerts']

def test_numeric_auction_quote_is_not_used_when_source_time_crosses_boundary():
    series=snapshots(2)
    series[-1]['captured_at']='2026-10-30T14:29:59+07:00'
    for row in series[-1]['quotes']:row['exchange_time']='2026-10-30T14:30:00+07:00'
    result=product(series)
    assert result['analysis']['mode']=='saved'
    assert result['analysis']['asof']==series[0]['captured_at']

def test_scope_filter_sort_and_raw_price_are_consistent():
    series=snapshots(2)
    for s in series:
        s['membership']['universes']={'VN30':['FPT'],'VN100':['FPT','VCB']}
        for r in s['quotes']:r['group']='Ngân hàng' if r['symbol']=='VCB' else 'Công nghệ'
    core=product(series);wide=product(series,{'universe':['VN100'],'group':['Ngân hàng'],'sort':['volume']})
    assert len(core['ranking'])==1 and [r['symbol'] for r in wide['ranking']]==['VCB']
    assert core['selected']['last_price_vnd']==wide['selected']['last_price_vnd']
    assert wide['coverage']['reference_count']==2 and wide['coverage']['visible_count']==1

@pytest.mark.parametrize('query',[{'lqs_profile':['baseline']},{'notional':['NaN']},{'notional':['0']},{'symbol':['XXX']},{'group':['XXX']},{'sort':['lqs']},{'window':['-1']},{'replay':['1']},{'symbol':['FPT','VCB']}])
def test_invalid_or_removed_filters_are_rejected(query):
    with pytest.raises(ValueError):product(snapshots(2),query)

def test_csv_identifies_both_price_and_analysis_times_without_empty_research_columns():
    result=product(after_hours());rows=list(csv.DictReader(io.StringIO(export_product(result).decode('utf-8-sig'))))
    assert rows[0]['source']=='ssi_fastconnect' and rows[0]['analysis_mode']=='saved'
    assert rows[0]['market_captured_at']!=rows[0]['analysis_at']
    assert rows[0]['market_dataset_id']!=rows[0]['analysis_dataset_id']
    assert 'lqs' not in rows[0] and 'amihud_5m' not in rows[0]

def test_product_does_not_mutate_saved_market_data():
    series=after_hours();original=deepcopy(series);product(series)
    assert series==original

@pytest.mark.parametrize('value',['0','501','NaN','Infinity','abc'])
def test_invalid_alert_spread_threshold_is_rejected(value):
    with pytest.raises(ValueError):product(snapshots(1),{'alert_spread_bps':[value]})


def test_threshold_changes_spread_conditions_without_changing_capacity_or_books():
    series=snapshots(2)
    low=product(series,{'alert_spread_bps':['1']})
    high=product(series,{'alert_spread_bps':['500']})
    assert low['dataset_id']!=high['dataset_id']
    assert low['ranking']==high['ranking'] and low['selected']==high['selected']
    assert low['alert_rules']['spread_threshold_bps']==1
    assert all(any(r['kind']=='spread' for r in a['reasons']) for a in low['alerts'])
    assert all([r['kind'] for r in a['reasons']]==['capacity'] for a in high['alerts'])


def test_one_tick_spread_is_disclosed_as_threshold_comparison():
    series=snapshots(1)
    for row in series[0]['quotes']:
        row['bids']=[{'price':11100-i*50,'volume':1e6} for i in range(3)]
        row['asks']=[{'price':11150+i*50,'volume':1e6} for i in range(3)]
    result=product(series)
    reason=result['alerts'][0]['reasons'][0]
    assert reason['kind']=='spread' and reason['label']=='Vượt ngưỡng chênh giá'
    assert reason['value_vnd']==50 and reason['value_ticks']==1
    assert reason['value_bps']==pytest.approx(50/11125*10000)
    assert reason['threshold_bps']==25


def test_alert_priority_follows_shortage_instead_of_ticker_name():
    series=snapshots(1)
    for row in series[0]['quotes']:
        for level in row['bids']+row['asks']:level['volume']=5000 if row['symbol']=='FPT' else 100
    result=product(series)
    assert [a['symbol'] for a in result['alerts']]==['VCB','FPT']
    assert result['alerts'][0]['sell_fill']<result['alerts'][1]['sell_fill']


def test_cached_valid_vn30_does_not_block_valid_vn100_or_relabel_index_point(tmp_path):
    c=client(tmp_path);core=['FPT']+[f'A{i:02}' for i in range(29)];expanded=core+[f'B{i:02}' for i in range(70)]
    c._cached_groups={'VN30':core};c._rows={s:{**raw(s),'stockType':'Stock'} for s in core}
    c._get=lambda path,params: [{'symbol':'VN30','board':'HOSE','stockType':None}] if params['index']=='VN30' else [{'symbol':s,'board':'HOSE','stockType':'Stock'} for s in expanded]
    c._membership()
    assert c._groups['VN30']==sorted(core) and len(c._groups['VN100'])==100
    assert c._membership_provenance['VN30']=='saved_ssi_membership' and c._metadata_warnings
    assert 'VN30' not in c._rows

def test_missing_vn30_without_cache_keeps_available_vn100(tmp_path):
    c=client(tmp_path);expanded=['FPT']+[f'A{i:02}' for i in range(99)]
    c._get=lambda path,params:[] if params['index']=='VN30' else [{'symbol':s,'board':'HOSE','stockType':'Stock'} for s in expanded]
    c._membership()
    assert set(c._groups)=={'VN100'} and len(c._rows)==100

def test_membership_401_is_not_hidden_by_cached_list(tmp_path):
    c=client(tmp_path);c._cached_groups={'VN30':['FPT']*30}
    c._get=lambda *a:(_ for _ in ()).throw(SSIAPIError('market_access_denied',401))
    with pytest.raises(SSIAPIError,match='market_access_denied'):c._membership()

def test_master_error_keeps_market_stream_and_warns(tmp_path):
    c=client(tmp_path);c._membership=lambda:None;c._groups={'VN30':['FPT']};c._rows={'FPT':raw()}
    c._master=lambda:(_ for _ in ()).throw(SSIAPIError('source_unavailable'))
    c._thread=SimpleNamespace(is_alive=lambda:True);c._stream_status='connected'
    result=c.poll()
    assert result['source']=='ssi_fastconnect' and result['quotes'][0]['last_price_vnd']==50100
    assert result['membership']['warnings'] and c._master_retry_at>0

def test_ui_has_supported_product_views_and_no_research_placeholders():
    html=(server.STATIC/'index.html').read_text(encoding='utf-8');js=(server.STATIC/'app.js').read_text(encoding='utf-8')
    for old in ('lqs-score','effective-spread-status','resilience-status','forecast-status','lqs-profile','intraday-section','flow-panel'):
        assert 'id="'+old+'"' not in html
    assert '/api/product?' in js and 'sourceTime' in js
    assert all(s in html for s in ('romer_command_dashboard/code.html','romer_signals_feed/code.html','romer_executive_reports/code.html'))

class IDs(HTMLParser):
    def __init__(self):super().__init__();self.ids=[]
    def handle_starttag(self,tag,attrs):self.ids += [v for k,v in attrs if k=='id']

def test_all_product_control_targets_exist_and_ids_are_unique():
    parser=IDs();parser.feed((server.STATIC/'index.html').read_text(encoding='utf-8'))
    assert len(parser.ids)==len(set(parser.ids))
    for filename in ('app.js','chart-replay.js'):
        js=(server.STATIC/filename).read_text(encoding='utf-8')
        refs=set(re.findall(r'\$\("([\w-]+)"\)',js))
        assert refs<=set(parser.ids),refs-set(parser.ids)
