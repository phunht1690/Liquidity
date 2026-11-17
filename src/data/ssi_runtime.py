"""Automatic collector supervision and bounded observation storage.

No SDK import, key read, network call or thread starts on module import.
The HTTP server explicitly starts/stops the collector in its lifecycle.
"""
from __future__ import annotations
from src.data.sqlite_connection import sqlite_session

from datetime import datetime, time as clock_time
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event, Lock, Thread, current_thread
import time
import uuid

from src.data.ssi_feed import CACHE, PROJECT, VN, load_snapshot

DATABASE = CACHE.with_name('observations.sqlite3')
STATUS = CACHE.with_name('collector_status.json')
CONTROL = CACHE.with_name('collector_control.json')
_lock = Lock()
_stop = Event()
_thread = None
_process = None
_config = None
_env_file = None
_token = None
_last_attempt = None
_last_error = None
_control = {}
REFRESH_SECONDS = 10


def collector_settings(config: dict | None = None) -> dict:
    supplied = dict(config or {})
    supplied.update((config or {}).get('ssi') or {})
    def bounded(name, default, low, high):
        try:
            value = float(supplied.get(name,default))
            return max(low,min(high,value)) if value == value and abs(value) != float('inf') else default
        except (TypeError,ValueError):
            return default
    return {'universe_group':supplied.get('universe_group') if supplied.get('universe_group') in ('VN30','VN100','HOSE','ALL') else 'VN30',
        'pilot_symbols_per_board':int(bounded('pilot_symbols_per_board',15,1,30)),
        'raw_archive_max_mb':int(bounded('raw_archive_max_mb',2048,256,16384)),
        'raw_archive_retention_days':int(bounded('raw_archive_retention_days',7,1,30)),
        'history_retention_days':int(bounded('history_retention_days',30,1,60)),
        'live_poll_seconds':bounded('live_poll_seconds',10,5,60),
        'off_hours_poll_seconds':bounded('off_hours_poll_seconds',30,15,1800),
        'history_retention_snapshots':int(bounded('history_retention_snapshots',1440,36,5000)),
        'collector_timeout_seconds':bounded('collector_timeout_seconds',50,35,90),
        'snapshot_stale_seconds':bounded('snapshot_stale_seconds',35,15,300),
        'max_backoff_seconds':bounded('max_backoff_seconds',300,60,1800)}


def market_clock_open(now: datetime | None = None, *, include_upcom=False) -> bool:
    """Clock schedule including auctions, not an official holiday/halts calendar."""
    now = (now or datetime.now(VN)).astimezone(VN)
    value = now.time().replace(tzinfo=None)
    return now.weekday()<5 and (clock_time(9)<=value<=clock_time(11,30) or clock_time(13)<=value<(clock_time(15) if include_upcom else clock_time(14,45,1)))


def poll_delay(settings: dict, now: datetime | None = None) -> float:
    return settings['live_poll_seconds'] if market_clock_open(now,include_upcom=settings.get('universe_group') in ('HOSE','ALL')) else settings['off_hours_poll_seconds']


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    # Windows readers can briefly hold a file without FILE_SHARE_DELETE.
    # Retry only the atomic rename; never expose a partially written status/cache.
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==4:raise
            time.sleep(.015*(attempt+1))


def store_snapshot(payload: dict, *, database: Path = DATABASE, cache: Path = CACHE, retention: int = 1440, retention_days: int = 30, compact: bool = False) -> None:
    """Never manufacture collector history from a legacy/manual latest cache."""
    if payload.get('source')!='ssi_fastconnect' or payload.get('collection_mode')!='auto_collector':
        raise ValueError('not_an_auto_observation')
    stamp = datetime.fromisoformat(payload['captured_at'])
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('observation_timezone_required')
    day = stamp.astimezone(VN).date().isoformat()
    encoded = json.dumps(payload,ensure_ascii=False,allow_nan=False)
    database.parent.mkdir(parents=True,exist_ok=True)
    if compact:
        from src.data.observation_store import append
        append(payload,database,retention_days)
        write_json_atomic(cache,payload)
        return
    with sqlite_session(database,timeout=5) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS snapshots (seq INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id TEXT UNIQUE NOT NULL, day TEXT NOT NULL, captured_at TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO snapshots(dataset_id,day,captured_at,payload) VALUES(?,?,?,?)',
            (payload['dataset_id'],day,payload['captured_at'],encoded))
        from datetime import timedelta
        cutoff=(stamp.astimezone(VN).date()-timedelta(days=max(1,min(60,int(retention_days)))-1)).isoformat()
        db.execute('CREATE INDEX IF NOT EXISTS snapshots_day_seq ON snapshots(day,seq)')
        db.execute('DELETE FROM snapshots WHERE day < ?', (cutoff,))
        db.execute('DELETE FROM snapshots WHERE day = ? AND seq NOT IN (SELECT seq FROM snapshots WHERE day = ? ORDER BY seq DESC LIMIT ?)',(day,day,max(1,int(retention))))
    write_json_atomic(cache,payload)


def history_snapshots(limit: int = 720, *, database: Path = DATABASE) -> list[dict]:
    if not database.is_file():
        return []
    count = max(1,min(5000,int(limit)))
    try:
        with sqlite_session(f'file:{database.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            rows = db.execute('SELECT payload FROM snapshots WHERE day = (SELECT MAX(day) FROM snapshots) ORDER BY seq DESC LIMIT ?',(count,)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]
    except (sqlite3.Error,ValueError,json.JSONDecodeError):
        return []


def _history_count() -> int:
    if not DATABASE.is_file():return 0
    try:
        with sqlite_session(f'file:{DATABASE.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            from src.data.observation_store import tables
            names=tables(db)
            return sum(db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('snapshots','captures') if name in names)
    except sqlite3.Error:return 0


def history_inventory(*, database: Path = DATABASE) -> dict:
    """Count saved observations across days without loading all book payloads."""
    result={'snapshot_count':0,'days':[],'days_with_continuous_observations':0,'continuous_snapshot_count':0}
    if not database.is_file():return result
    try:
        with sqlite_session(f'file:{database.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            from src.data.observation_store import tables,compact_inventory
            names=tables(db)
            rows=db.execute("""SELECT day,COUNT(*),MIN(captured_at),MAX(captured_at),
                SUM(CASE WHEN strftime('%w',day) NOT IN ('0','6') AND
                ((substr(captured_at,12,8)>='09:15:00' AND substr(captured_at,12,8)<'11:30:00') OR
                 (substr(captured_at,12,8)>='13:00:00' AND substr(captured_at,12,8)<'14:30:00')) THEN 1 ELSE 0 END)
                FROM snapshots GROUP BY day ORDER BY day""").fetchall() if 'snapshots' in names else []
            combined={d:[d,n,a,b,c] for d,n,a,b,c in rows}
            for d,n,a,b,c in compact_inventory(db):
                old=combined.get(d,[d,0,a,b,0]);old[1]+=n;old[2]=min(old[2],a);old[3]=max(old[3],b);old[4]+=c;combined[d]=old
            rows=[combined[d] for d in sorted(combined)]
            result['storage_format']='quote_changes' if 'captures' in names else 'legacy_snapshots'
        result['days']=[{'day':d,'snapshots':n,'first':a,'last':b,'continuous_snapshots':c} for d,n,a,b,c in rows]
        result['snapshot_count']=sum(r[1] for r in rows)
        result['continuous_snapshot_count']=sum(r[4] for r in rows)
        result['days_with_continuous_observations']=sum(r[4]>0 for r in rows)
    except sqlite3.Error:result['status']='unavailable'
    return result


def _status_file() -> dict:
    try:
        state = json.loads(STATUS.read_text(encoding='utf-8'))
        return state if isinstance(state,dict) else {}
    except (OSError,ValueError):
        return {}


def _publish_control(command: str | None = None) -> None:
    """Public local heartbeat/commands; never includes credentials or SDK input."""
    with _lock:
        if not _control or _control.get('worker_token')!=_token:
            _control.clear()
            _control.update(worker_token=_token,serial=0,command='run')
        if command is not None:
            _control['serial']+=1
            _control['command']=command
        _control['heartbeat_monotonic']=time.monotonic()
        write_json_atomic(CONTROL,dict(_control))


def collector_status() -> dict:
    with _lock:
        running = _thread is not None and _thread.is_alive() and not _stop.is_set()
        process,token,settings = _process,_token,_config or collector_settings()
    raw = _status_file()
    if not running or raw.get('worker_token')!=token:
        raw = {'status':'stopped' if not running else 'starting','failure_count':0,'last_error':_last_error}
    raw.pop('worker_token',None);raw.pop('pid',None);raw.pop('attempt_started_monotonic',None)
    return {**raw,'now':datetime.now(VN).isoformat(),'automatic':True,'running':running,
        'process_running':process is not None and process.poll() is None,
        'poll_seconds':poll_delay(settings),'poll_interval_seconds':poll_delay(settings),
        'live_poll_seconds':settings['live_poll_seconds'],
        'off_hours_poll_seconds':settings['off_hours_poll_seconds'],
        'market_clock_open':market_clock_open(include_upcom=settings.get('universe_group') in ('HOSE','ALL')),
        'clock_schedule_note':'Lịch theo giờ Việt Nam; chưa xác minh ngày nghỉ/lệnh tạm ngừng từ sàn.'}


def snapshot_state() -> dict:
    payload = load_snapshot()
    stamp = datetime.fromisoformat(payload['captured_at'])
    if stamp.tzinfo is None:raise ValueError('snapshot_timezone_required')
    age = (datetime.now(VN)-stamp).total_seconds()
    state = collector_status()
    stale_after = max((_config or collector_settings())['snapshot_stale_seconds'],state['poll_interval_seconds']*3)
    payload['runtime'] = {**state,'capture_age_seconds':max(0,age),
        'stale_capture':age>stale_after or age< -5 or payload.get('collection_mode')!='auto_collector' or not state['running'],
        'clock_warning':age< -5,'refreshing':state.get('status') in ('fetching','starting'),
        'last_refresh_error':state.get('last_error'),'stale_after_seconds':stale_after,
        'refresh_cooldown_seconds':state['live_poll_seconds'],'history_count':_history_count(),
        'note':'Tuổi lần nhận tại máy, không phải độ trễ sàn; ảnh lưu định kỳ từ WebSocket SSI.'}
    return payload


def collector_event() -> dict:
    """Small public notification; no book/analytics scan and no remote request."""
    runtime=collector_status()
    revision=None;captured_at=None;stale=True
    try:
        revision=str(CACHE.stat().st_mtime_ns)
        payload=load_snapshot()
        captured_at=payload['captured_at']
        stamp=datetime.fromisoformat(captured_at)
        age=(datetime.now(VN)-stamp).total_seconds()
        threshold=max((_config or collector_settings())['snapshot_stale_seconds'],runtime['poll_seconds']*3)
        stale=not runtime['running'] or age>threshold or age< -5 or payload.get('collection_mode')!='auto_collector'
    except (OSError,ValueError,KeyError,TypeError):pass
    runtime.update(stale_capture=stale,refreshing=runtime.get('status') in ('starting','fetching'))
    return {'revision':revision,'captured_at':captured_at,'runtime':runtime}


def _end_process(process) -> None:
    if process is None:return
    try:
        if process.stdin:
            try:
                process.stdin.write('stop\n');process.stdin.flush();process.stdin.close()
            except (OSError,ValueError):pass
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        # The virtual-environment launcher may have a Python child on Windows;
        # terminate only this owned Popen process tree, never an arbitrary PID.
        try:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=5)
            else:process.kill()
        except (OSError,subprocess.TimeoutExpired):
            try:process.kill()
            except OSError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:pass
    except (OSError,ValueError):pass


def _supervise() -> None:
    global _process,_token,_last_error
    failures = 0
    while not _stop.is_set():
        with _lock:
            settings,env_file = dict(_config),_env_file
            token=uuid.uuid4().hex;_token=token
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
        started=time.monotonic();process=None
        try:
            _publish_control('run')
            process=subprocess.Popen([sys.executable,'-B','-m','src.data.ssi_worker','--env-file',str(env_file)],
                cwd=PROJECT,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with _lock:_process=process
            process.stdin.write(json.dumps({'settings':settings,'worker_token':token})+'\n');process.stdin.flush()
            process.stdin.close()
            while not _stop.wait(.5):
                _publish_control()
                if process.poll() is not None:raise RuntimeError('worker_exited')
                status=_status_file()
                if status.get('worker_token')==token and status.get('status')=='fetching':
                    attempt=status.get('attempt_started_monotonic')
                    if isinstance(attempt,(int,float)) and time.monotonic()-attempt>settings['collector_timeout_seconds']:
                        raise TimeoutError('worker_timeout')
                elif (not status or status.get('worker_token')!=token) and time.monotonic()-started>settings['collector_timeout_seconds']:
                    raise TimeoutError('worker_start_timeout')
            failures=0
        except Exception:
            failures+=1
            _last_error='Bộ thu bị ngắt hoặc nguồn phản hồi quá lâu; đang thử lại có giãn nhịp.'
        finally:
            try:_publish_control('stop')
            except OSError:pass
            _end_process(process)
            with _lock:_process=None
        if not _stop.is_set():_stop.wait(min(settings['max_backoff_seconds'],10*2**min(failures,5)))


def start_collector(config: dict | None = None, env_file: Path | None = None) -> None:
    global _thread,_config,_env_file
    with _lock:
        if _thread is not None and _thread.is_alive():return
        _config=collector_settings(config)
        _env_file=Path(env_file) if env_file else PROJECT/'.env'
        _stop.clear()
        _thread=Thread(target=_supervise,name='ssi-collector-supervisor',daemon=True)
        _thread.start()


def stop_collector() -> None:
    global _thread
    _stop.set()
    try:_publish_control('stop')
    except OSError:pass
    with _lock:thread,process=_thread,_process
    _end_process(process)
    if thread and thread is not current_thread():thread.join(timeout=10)
    with _lock:
        if _thread is thread and (thread is None or not thread.is_alive()):_thread=None


def refresh_snapshot() -> tuple[int,dict]:
    global _last_attempt
    with _lock:
        process=_process
        if not _thread or not _thread.is_alive() or _stop.is_set():
            return 503,{'status':'stopped','message':'Bộ thu tự động chưa chạy. Khởi động lại dashboard.'}
        raw=_status_file()
        if raw.get('worker_token')==_token and raw.get('status') in ('fetching','starting','backoff'):
            return 202,{'status':raw['status'],'message':'Bộ thu đang xử lý hoặc chờ nguồn; giao diện sẽ tự nhận bản mới.'}
        now=time.monotonic();interval=(_config or collector_settings())['live_poll_seconds']
        # New tabs share one worker. Opening/reloading must not multiply calls.
        try:
            stamp=datetime.fromisoformat(load_snapshot()['request_started_at'])
            if 0<=(datetime.now(VN)-stamp).total_seconds()<interval:
                return 202,{'status':'recent','message':'Bộ thu vừa hỏi nguồn; đang dùng bản nhận gần nhất.'}
        except (OSError,ValueError,KeyError,TypeError):pass
        if _last_attempt is not None and now-_last_attempt<interval:
            return 429,{'status':'cooldown','message':f'Đang thu tự động; mỗi lần lấy cách nhau ít nhất {interval:g} giây.'}
        _last_attempt=now
        if process is None or process.poll() is not None:
            return 202,{'status':'starting','message':'Bộ thu tự động đang khởi động lại.'}
    try:_publish_control('refresh')
    except OSError:
        return 202,{'status':'starting','message':'Bộ thu đang nối lại; các mục tự cập nhật khi nhận dữ liệu.'}
    return 202,{'status':'scheduled','message':'Đã yêu cầu lần lấy tiếp theo; các mục tự cập nhật khi nhận dữ liệu.'}
