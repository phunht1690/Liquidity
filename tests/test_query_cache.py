from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from src.app.query_cache import QueryCache, QueryBusy


def test_parallel_tabs_share_one_query_and_result():
    cache = QueryCache()
    started, release = Event(), Event()
    calls = []
    value = {'source': 'ssi_fastconnect', 'dataset_id': 'real-capture'}
    def produce():
        calls.append(1); started.set()
        assert release.wait(2)
        return value
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cache.get, 'same-query', produce) for _ in range(8)]
        assert started.wait(1)
        release.set()
        assert all(f.result(timeout=2) is value for f in futures)
    assert calls == [1]
    assert cache.status()['active_queries'] == 0


def test_other_filters_cannot_exceed_query_memory_budget():
    cache = QueryCache(max_workers=1, wait_seconds=.01)
    started, release = Event(), Event()
    def produce():
        started.set(); assert release.wait(2); return 'ready'
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(cache.get, 'FPT', produce)
        assert started.wait(1)
        with pytest.raises(QueryBusy): cache.get('VCB', lambda: pytest.fail('Unbounded work started'))
        with pytest.raises(QueryBusy): cache.get('FPT', lambda: pytest.fail('Duplicate work started'))
        release.set()
        assert first.result(timeout=2) == 'ready'
    assert cache.get('FPT', lambda: pytest.fail('Fresh result recomputed')) == 'ready'


def test_ttl_eviction_and_failure_release_all_resources():
    now = [0.]
    cache = QueryCache(max_entries=2, ttl=2, clock=lambda: now[0])
    assert cache.get('a', lambda: 1) == 1
    assert cache.get('a', lambda: 2) == 1
    now[0] = 3
    assert cache.get('a', lambda: 2) == 2
    cache.get('b', lambda: 3); cache.get('c', lambda: 4)
    assert cache.status()['cached_queries'] == 2
    assert cache.get('a', lambda: 5) == 5
    def fail(): raise ValueError('not retained')
    with pytest.raises(ValueError): cache.get('failed', fail)
    assert cache.status()['active_queries'] == 0
    assert cache.get('failed', lambda: 'retry worked') == 'retry worked'


def test_new_capture_invalidates_query_and_health_bypasses_gate(monkeypatch, tmp_path):
    from src.app import server
    from src.data import ssi_feed
    cache_file = tmp_path/'latest.json'; cache_file.write_text('one')
    monkeypatch.setattr(ssi_feed, 'CACHE', cache_file)
    monkeypatch.setattr(server, 'QUERY_CACHE', QueryCache(ttl=100))
    calls = []
    def build(query): calls.append(1); return len(calls)
    assert server.cached_query(build, {'symbol': ['FPT']}) == 1
    assert server.cached_query(build, {'symbol': ['FPT']}) == 1
    cache_file.write_text('a different capture')
    assert server.cached_query(build, {'symbol': ['FPT']}) == 2
    replacement=tmp_path/'next.json';replacement.write_text('b different capture');replacement.replace(cache_file)
    assert server.cached_query(build, {'symbol': ['FPT']}) == 3
    monkeypatch.setattr(server, 'cached_query', lambda *a: pytest.fail('Health blocked by a heavy query'))
    handler = object.__new__(server.Handler); handler.path = '/api/health'
    replies = []; monkeypatch.setattr(server.Handler, '_json', lambda self, status, data: replies.append((status, data)))
    handler.do_GET()
    assert replies[0][0] == 200
    assert 'query_processing' in replies[0][1]
