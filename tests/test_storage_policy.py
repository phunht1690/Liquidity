"""Calendar retention boundaries and replay selection; local temporary DBs only."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import RLock
import json,sqlite3
import pytest

from src.data import ssi_feed as feed
from src.data.ssi_runtime import collector_settings,store_snapshot,history_inventory
from src.data.observation_store import hydrate
from src.data.chart_archive import read_chart_archive
from src.data.alert_history import attach_history
from tests.test_live_analytics import snapshots,config,VN


def sample(day):
    record=snapshots(1,start=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=VN))[0]
    record['dataset_id']=day
    record['membership']['labels']={'VN30':day}
    return record


def test_defaults_and_config_keep_replay_and_raw_policies_separate():
    defaults=collector_settings()
    assert defaults['history_retention_days']==30
    assert defaults['raw_archive_retention_days']==7
    assert defaults['raw_archive_max_mb']==2048
    actual=json.loads((Path(__file__).parents[1]/'config/config.json').read_text('utf8'))
    policy=collector_settings(actual)
    assert all(policy[k]==defaults[k] for k in ('history_retention_days','raw_archive_retention_days','raw_archive_max_mb'))
    assert collector_settings({'ssi':{'raw_archive_retention_days':0}})['raw_archive_retention_days']==1


def test_thirty_calendar_days_keep_boundary_checkpoint_and_remove_expired_metadata(tmp_path):
    db=tmp_path/'observations.sqlite3';cache=tmp_path/'latest.json'
    store_snapshot(sample('2026-10-31'),database=db,cache=cache)
    for day in ('2026-11-01','2026-11-02','2026-12-01'):
        store_snapshot(sample(day),database=db,cache=cache,compact=True)
    assert [d['day'] for d in history_inventory(database=db)['days']]==['2026-11-02','2026-12-01']
    assert hydrate(db,'2026-11-01') is None
    assert hydrate(db,'2026-11-02')['quotes'][0]['symbol']=='FPT'
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM capture_meta').fetchone()[0]==2
        assert conn.execute("SELECT COUNT(*) FROM quote_changes WHERE day<'2026-11-02'").fetchone()[0]==0


@pytest.mark.parametrize('compact',[False,True])
@pytest.mark.parametrize('empty_day',['2026-11-14','2026-11-16'])
def test_default_replay_skips_receipt_only_weekend_or_weekday_without_prices(tmp_path,compact,empty_day):
    db=tmp_path/'observations.sqlite3';cache=tmp_path/'latest.json'
    friday=sample('2026-11-13');empty=deepcopy(friday)
    empty.update(dataset_id=empty_day,captured_at=empty_day+'T10:00:00+07:00')
    for record in (friday,empty):store_snapshot(record,database=db,cache=cache,compact=compact)
    before=cache.read_bytes()
    result=read_chart_archive({},config(),database=db)
    assert result['day']=='2026-11-13' and result['summary']['price_observations']==1
    assert result['selection']['latest_recorded_day']==empty_day
    explicit=read_chart_archive({'day':[empty_day]},config(),database=db)
    assert explicit['day']==empty_day and explicit['summary']['price_observations']==0
    assert 'selection' not in explicit
    assert history_inventory(database=db)['snapshot_count']==2 and cache.read_bytes()==before
    with pytest.raises(ValueError):read_chart_archive({'symbol':['UNKNOWN']},config(),database=db)


def test_replay_keeps_latest_real_price_even_without_usable_book(tmp_path):
    db=tmp_path/'observations.sqlite3';cache=tmp_path/'latest.json'
    for day in ('2026-11-12','2026-11-13'):
        record=sample(day);record['captured_at']=day+'T16:00:00+07:00'
        store_snapshot(record,database=db,cache=cache,compact=True)
    result=read_chart_archive({},config(),database=db)
    assert result['day']=='2026-11-13' and result['summary']['price_observations']==1
    assert result['summary']['liquidity_observations']==0 and 'selection' not in result


def raw_session(monkeypatch,tmp_path):
    monkeypatch.setattr(feed,'CACHE',tmp_path/'latest.json')
    session=object.__new__(feed.SSISession)
    session._lock=RLock();session._buffers=[];session._archive_last_prune=0
    session._archive_errors=0;session._archive_status='recording'
    session.raw_archive_max_mb=2048;session.raw_archive_retention_days=7
    return session


def seed_events(tmp_path,rows):
    path=tmp_path/'events.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,day TEXT,received_at TEXT,payload TEXT)')
        db.executemany('INSERT INTO events(day,received_at,payload) VALUES(?,?,?)',rows)
    return path


def event(day,padding=0):
    return (day,day+'T10:00:00+07:00',json.dumps({'data':{'s':'FPT'},'padding':'x'*padding}))


def test_raw_retention_keeps_seven_day_boundary_without_touching_replay(monkeypatch,tmp_path):
    session=raw_session(monkeypatch,tmp_path)
    path=seed_events(tmp_path,[event('2026-11-07'),event('2026-11-08'),event('2026-11-13')])
    protected=tmp_path/'observations.sqlite3';protected.write_bytes(b'replay-is-independent')
    session._buffers=[event('2026-11-14')];session._flush_events()
    with sqlite3.connect(path) as db:
        assert [r[0] for r in db.execute('SELECT day FROM events ORDER BY day')]==['2026-11-08','2026-11-13','2026-11-14']
    assert protected.read_bytes()==b'replay-is-independent'


def test_raw_expiry_runs_during_an_idle_weekend(monkeypatch,tmp_path):
    session=raw_session(monkeypatch,tmp_path)
    path=seed_events(tmp_path,[event('2026-11-07'),event('2026-11-08')])
    class FixedClock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,14,10,tzinfo=VN)
    monkeypatch.setattr(feed,'datetime',FixedClock)
    session._flush_events()
    with sqlite3.connect(path) as db:assert db.execute('SELECT day FROM events').fetchall()==[('2026-11-08',)]


def test_raw_budget_removes_older_day_before_rejecting_new_data(monkeypatch,tmp_path):
    session=raw_session(monkeypatch,tmp_path);session.raw_archive_max_mb=.05
    path=seed_events(tmp_path,[event('2026-11-13',100000)])
    session._buffers=[event('2026-11-14')];session._flush_events()
    with sqlite3.connect(path) as db:assert db.execute('SELECT day FROM events').fetchall()==[('2026-11-14',)]
    assert session._archive_status=='recording'


def test_raw_budget_keeps_first_records_of_current_day(monkeypatch,tmp_path):
    session=raw_session(monkeypatch,tmp_path);session.raw_archive_max_mb=.05
    path=seed_events(tmp_path,[event('2026-11-14',100000)])
    session._buffers=[event('2026-11-14')];session._flush_events()
    with sqlite3.connect(path) as db:assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
    assert session._archive_status=='paused_capacity'


def test_alert_history_uses_matching_thirty_day_window(tmp_path):
    db=tmp_path/'alerts.sqlite3'
    product={'analysis':{'mode':'live','asof':'2026-12-01T09:30:00+07:00'},'universe':'VN30','group':'all',
        'notional_vnd':1e9,'alert_rules':{'spread_threshold_bps':25},'alerts':[],'ranking':[]}
    attach_history(deepcopy(product),db)
    with sqlite3.connect(db) as conn:
        conn.executemany('INSERT INTO alert_runs(scope,day,symbol,kind,first_at,last_at) VALUES(?,?,?,?,?,?)',
            [('old',day,'FPT','capacity',day+'T09:30:00+07:00',day+'T09:30:00+07:00') for day in ('2026-11-01','2026-11-02')])
    attach_history(deepcopy(product),db)
    with sqlite3.connect(db) as conn:assert conn.execute('SELECT day FROM alert_runs').fetchall()==[('2026-11-02',)]
