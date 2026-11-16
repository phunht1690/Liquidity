from copy import deepcopy
from datetime import datetime,timedelta
import sqlite3
import pytest
from src.data.product_history import load_product_history
from src.data.product import build_product
from src.data.ssi_runtime import store_snapshot
from src.data.ssi_feed import VN
from tests.test_live_analytics import snapshots,config


@pytest.mark.parametrize('kind',['normal','reordered','missing','older_selected','invalid_all'])
def test_compact_history_matches_full_book_and_price_results(tmp_path,kind):
    series=snapshots(4,start=datetime(2026,11,11,14,0,tzinfo=VN))
    for i,s in enumerate(series):s['dataset_id']='capture-'+str(i)
    if kind=='reordered':series[1]['quotes'].reverse()
    if kind=='missing':series[1]['quotes']=[r for r in series[1]['quotes'] if r['symbol']!='FPT']
    if kind=='older_selected':
        for s in series[2:]:s['quotes'][0]['book_flags']=['stale_or_missing_book_event']
    if kind=='invalid_all':
        for s in series:
            for r in s['quotes']:r['book_flags']=['stale_or_missing_book_event']
    original=deepcopy(series);database=tmp_path/'observations.sqlite3';cache=tmp_path/'latest.json'
    for s in series:store_snapshot(s,database=database,cache=cache)
    runtime={'latest_snapshot':series[-1],'now':datetime(2026,11,11,16,tzinfo=VN).isoformat()}
    full=build_product({},series,runtime,config())
    compact,hydrate=load_product_history({},series[-1],config(),database=database)
    result=build_product({},compact,runtime,config(),analysis_loader=hydrate)
    for key in ['selected','ranking','history','analysis','alerts','cost_curve']:
        assert result[key]==full[key],key
    assert all(len(s['quotes'])<=1 for s in compact if s.get('_compact'))
    assert series==original
    with sqlite3.connect(database) as db:assert db.execute('select count(*) from snapshots').fetchone()[0]==4


def test_empty_compact_reader_is_read_only(tmp_path):
    missing=tmp_path/'missing.sqlite3'
    rows,hydrate=load_product_history({},snapshots(1)[0],config(),database=missing)
    assert rows==[] and not missing.exists()
    assert hydrate('nonexistent') is None and not missing.exists()


@pytest.mark.parametrize('compact',[False,True])
def test_several_receipt_only_days_do_not_hide_last_real_liquidity_session(tmp_path,compact):
    db=tmp_path/'observations.sqlite3';cache=tmp_path/'latest.json'
    friday=snapshots(1,start=datetime(2026,11,13,14,tzinfo=VN))[0]
    friday['dataset_id']='real-friday'
    store_snapshot(friday,database=db,cache=cache,compact=compact)
    for day in range(14,19):
        empty=deepcopy(friday);empty.update(dataset_id='receipt-'+str(day),captured_at=f'2026-11-{day}T08:00:00+07:00')
        for q in empty['quotes']:q['book_flags']=['stale_or_missing_book_event']
        store_snapshot(empty,database=db,cache=cache,compact=compact)
    records,hydrate=load_product_history({},empty,config(),database=db)
    product=build_product({},records,{'latest_snapshot':empty,'now':empty['captured_at']},config(),analysis_loader=hydrate)
    assert product['analysis']['mode']=='saved'
    assert product['analysis']['asof']==friday['captured_at']
    assert len([r for r in records if r['dataset_id']=='real-friday'])==1
