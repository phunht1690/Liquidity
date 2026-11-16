from copy import deepcopy
from datetime import datetime, timedelta
import sqlite3

import pytest

from src.data import ranking_history as reader
from src.data.ssi_runtime import store_snapshot
from tests.test_live_analytics import VN, config, snapshots


def save(tmp_path, series):
    database = tmp_path / 'prices.sqlite3'
    for row in series:
        store_snapshot(row, database=database, cache=tmp_path / 'latest.json')
    return database


def test_histories_follow_symbol_even_when_quote_arrays_reorder(tmp_path):
    series = snapshots(4)
    for i, row in enumerate(series):
        row['quotes'][1]['last_price_vnd'] = 90000 + i * 100
    series[1]['quotes'].reverse()
    series[2]['quotes'] = [r for r in series[2]['quotes'] if r['symbol'] != 'FPT']
    original = deepcopy(series)
    result = reader.load_ranking_sparklines(series[-1], database=save(tmp_path, series))
    assert [p['last_price_vnd'] for p in result['points']['FPT']] == [50000, 50010, None, 50030]
    assert [p['last_price_vnd'] for p in result['points']['VCB']] == [90000, 90100, 90200, 90300]
    assert series == original


def test_previous_day_prices_and_missing_prices_are_never_plotted(tmp_path):
    series = snapshots(4)
    series[0]['quotes'][0]['trading_date'] = '2026-10-29'
    series[1]['quotes'][0]['source_match_time_raw'] = '2026/10/29 14:30:00'
    series[2]['quotes'][0]['last_price_vnd'] = None
    result = reader.load_ranking_sparklines(series[-1], database=save(tmp_path, series))
    assert [p['last_price_vnd'] for p in result['points']['FPT']] == [None, None, None, 50030]


@pytest.mark.parametrize('has_gap', [False, True])
def test_sampling_keeps_real_collection_gaps_without_inventing_gaps(tmp_path, has_gap):
    series = snapshots(20)
    if has_gap:
        for s in series[7:]:
            s['captured_at'] = (datetime.fromisoformat(s['captured_at']) + timedelta(minutes=4)).isoformat()
    result = reader.load_ranking_sparklines(series[-1], database=save(tmp_path, series), max_points=2)
    points = result['points']['FPT']
    assert len(points) == 2 and points[-1]['gap_before'] is has_gap


def test_payload_reads_are_bounded_and_cache_is_shared_and_isolated(tmp_path, monkeypatch):
    series = snapshots(240)
    database = save(tmp_path, series[:-1])
    original_loads = reader.json.loads
    decoded = []
    def counted(encoded):
        decoded.append(1)
        return original_loads(encoded)
    monkeypatch.setattr(reader.json, 'loads', counted)
    result = reader.load_ranking_sparklines(series[-1], database=database, max_points=12)
    assert len(decoded) == 11
    assert all(len(points) == 12 for points in result['points'].values())
    assert result['points']['FPT'][-1]['last_price_vnd'] == 52390
    result['points']['FPT'][0]['last_price_vnd'] = -1
    cached = reader.load_ranking_sparklines(series[-1], database=database, max_points=12)
    assert len(decoded) == 11 and cached['points']['FPT'][0]['last_price_vnd'] == 50000
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 239


def test_off_hours_repetitions_do_not_flatten_the_intraday_line(tmp_path):
    series = snapshots(4, start=datetime(2026, 11, 11, 14, 29, tzinfo=VN))
    for i in range(20):
        s = deepcopy(series[-1]);s['dataset_id'] = 'closed-' + str(i)
        s['captured_at'] = datetime(2026, 11, 11, 16, i, tzinfo=VN).isoformat()
        series.append(s)
    result = reader.load_ranking_sparklines(series[-1], database=save(tmp_path, series))
    assert len(result['points']['FPT']) == 5
    assert result['points']['FPT'][-1]['timestamp'] == series[-1]['captured_at']


def test_late_old_writes_and_future_rows_do_not_change_chronology(tmp_path):
    series = snapshots(4)
    database = save(tmp_path, [series[2], series[0], series[3], series[1]])
    result = reader.load_ranking_sparklines(series[2], database=database)
    assert [p['last_price_vnd'] for p in result['points']['FPT']] == [50000, 50010, 50020]


def test_no_history_does_not_create_database_or_manufacture_a_line(tmp_path):
    missing = tmp_path / 'absent.sqlite3'
    latest = snapshots(1)[0]
    result = reader.load_ranking_sparklines(latest, database=missing)
    assert len(result['points']['FPT']) == 1 and not missing.exists()
    latest['source'] = 'simulated'
    assert reader.load_ranking_sparklines(latest, database=missing) == {'day': None, 'points': {}}


def test_product_rows_receive_only_their_own_trend(tmp_path, monkeypatch):
    from src.app import server
    series = snapshots(4)
    for i, s in enumerate(series):s['quotes'][1]['last_price_vnd'] = 90000 + i
    database = save(tmp_path, series)
    monkeypatch.setattr(server, 'snapshot_state', lambda: series[-1])
    monkeypatch.setattr(server, 'history_inventory', lambda: {})
    monkeypatch.setattr(server, 'load_product_history', lambda *a, **kw: (series, lambda identity: series[-1]))
    def cached_lines(product,latest):
        trends=reader.load_ranking_sparklines(latest,database=database)
        product['ranking_history_day']=trends['day']
        for row in product['ranking']:row['price_trend']=trends['points'].get(row['symbol'],[])
        return product
    monkeypatch.setattr(server, 'enrich_ranking_intraday', cached_lines)
    monkeypatch.setattr(server, 'CONFIG', config())
    result = server.product_state({})
    rows = {r['symbol']: r for r in result['ranking']}
    assert result['ranking_history_day'] == '2026-10-30'
    assert rows['FPT']['price_trend'][-1]['last_price_vnd'] == 50030
    assert rows['VCB']['price_trend'][-1]['last_price_vnd'] == 90003
