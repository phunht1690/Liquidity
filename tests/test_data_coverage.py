"""Coverage cannot inherit an overview sector/symbol or enqueue SSI requests."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from src.app import server
from src.data.data_coverage import project_coverage
from src.data.daily_summary import DailySummaries
from tests.test_live_analytics import snapshots,config
from tests.test_product import product,after_hours


def test_coverage_reads_whole_universe_and_only_local_caches(monkeypatch):
    series=snapshots(2)
    for saved in series:
        saved['membership']['universes']={'VN30':['FPT','VCB'],'HNX':['VCB']}
        saved['quotes'][0]['group']='Phần mềm';saved['quotes'][1]['group']='Ngân hàng'
    latest={**deepcopy(series[-1]),'runtime':{'now':series[-1]['captured_at'],'auth':{'websocket_status':'connected'}}}
    monkeypatch.setattr(server,'snapshot_state',lambda:deepcopy(latest))
    monkeypatch.setattr(server,'history_inventory',lambda:{'days':[]})
    history=Mock(return_value=(deepcopy(series),None));monkeypatch.setattr(server,'load_product_history',history)
    cached=Mock(side_effect=lambda data,**kwargs:data);monkeypatch.setattr(server,'enrich_daily_statistics',cached)
    for name in ('enrich_candle_statistics','enrich_archived_statistics'):
        monkeypatch.setattr(server,name,lambda data:data)
    monkeypatch.setattr(server,'collector_settings',lambda _:dict(history_retention_days=30,raw_archive_retention_days=7,raw_archive_max_mb=2048))
    monkeypatch.setattr(server,'backfill_status',lambda:{})
    monkeypatch.setattr(server,'background_status',lambda:{})
    for name in ('enrich_ranking_intraday','recent_trades','prioritize_history','attach_history'):
        monkeypatch.setattr(server,name,Mock(side_effect=AssertionError('Coverage must not schedule or load a stock view')))
    query={'universe':['VN30']};result=server.data_coverage_state(query)
    assert query=={'universe':['VN30']}
    assert result['group']=='all' and result['coverage']['scope']['symbols']==2
    assert result['coverage']['scope']['received_prices']==2
    assert result['coverage']['scope']['valid_books']==2
    assert history.call_args.args[0]['group']==['all']
    assert cached.call_args.kwargs=={'request':False}
    assert not {'selected','ranking','history','cost_curve','notional_vnd'} & result.keys()
    assert not {'price_time','book_time','price_basis'} & result['data_status'].keys()
    hnx=server.data_coverage_state({'universe':['HNX']})
    assert hnx['coverage']['scope']['symbols']==1
    assert hnx['universe']=='HNX' and query=={'universe':['VN30']}


@pytest.mark.parametrize('query',[
    {'group':['Ngân hàng']},{'symbol':['FPT']},{'notional':['5000000000']},
    {'universe':['VN30','HNX']},{'universe':['VN30'],'group':['all']},
])
def test_coverage_rejects_hidden_filters(query):
    with pytest.raises(ValueError):server.data_coverage_state(query)


def test_projection_refuses_a_filtered_product():
    p=product(snapshots(2));p['group']='Ngân hàng'
    with pytest.raises(ValueError):project_coverage(p)


def test_cached_daily_prices_apply_without_a_network_worker(tmp_path):
    service=DailySummaries(database=tmp_path/'missing.sqlite3')
    service.request=Mock(side_effect=AssertionError('No request allowed'))
    service.cache={'FPT':{'day':'2026-10-30','close':55000,'volume_shares':0,'received_at':'2026-10-30T14:59:00+07:00'}}
    cached_product=product(after_hours());cached_product['runtime']['now']='2026-10-30T16:00:00+07:00'
    result=service.enrich(cached_product,request=False)
    row=next(r for r in result['ranking'] if r['symbol']=='FPT')
    assert row['last_price_vnd']==55000 and row['volume_shares']==0
    assert result['coverage']['scope']['received_prices']==2
    assert result['coverage']['scope']['received_volumes']==2
    assert service.client is None and service.thread is None
    service.request.assert_not_called()
