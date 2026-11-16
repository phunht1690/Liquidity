"""All tests use isolated runtime paths, even while the real dashboard is open."""
import pytest

@pytest.fixture(autouse=True)
def isolate_dashboard_runtime(monkeypatch,tmp_path):
    from src.data import ssi_feed as feed,ssi_runtime as runtime,ssi_worker as worker
    from src.data import ranking_intraday
    monkeypatch.setattr(ranking_intraday,'_service',ranking_intraday.IntradaySparklines(database=tmp_path/'intraday.sqlite3',enabled=False))
    monkeypatch.setattr(feed,'CACHE',tmp_path/'latest.json')
    monkeypatch.setattr(runtime,'CACHE',tmp_path/'latest.json')
    monkeypatch.setattr(runtime,'DATABASE',tmp_path/'observations.sqlite3')
    for module in (runtime,worker):
        monkeypatch.setattr(module,'CONTROL',tmp_path/'control.json')
        monkeypatch.setattr(module,'STATUS',tmp_path/'status.json')
