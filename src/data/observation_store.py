"""Store quote changes once; read a ticker without decoding the whole universe.

Legacy snapshots remain readable and are never migrated or overwritten in place.
Each capture day begins with a full checkpoint of quotes, so day retention cannot
remove a prerequisite for a retained day. Unchanged after-hours polls add no rows.
"""
from src.data.sqlite_connection import sqlite_session
from datetime import datetime,timedelta
from functools import lru_cache
from hashlib import sha256
import json,sqlite3,zlib
from src.data.ssi_feed import event_time,VN
from src.data.market_rules import phase

_fingerprint_cache={}


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def decode(value):
    try:return json.loads(zlib.decompress(value).decode('utf8') if isinstance(value,bytes) else value)
    except (ValueError,zlib.error,UnicodeDecodeError):return {}


def tables(db):return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def create(db):
    db.execute('CREATE TABLE IF NOT EXISTS capture_meta(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS captures(seq INTEGER PRIMARY KEY AUTOINCREMENT,dataset_id TEXT UNIQUE NOT NULL,day TEXT NOT NULL,captured_at TEXT NOT NULL,meta_id TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS captures_day_seq ON captures(day,seq)')
    db.execute('CREATE TABLE IF NOT EXISTS quote_changes(capture_seq INTEGER NOT NULL,day TEXT NOT NULL,symbol TEXT NOT NULL,fingerprint TEXT NOT NULL,payload BLOB NOT NULL,price_vnd REAL,trading_date TEXT,market_code TEXT,PRIMARY KEY(capture_seq,symbol))')
    db.execute('CREATE INDEX IF NOT EXISTS changes_day_symbol_seq ON quote_changes(day,symbol,capture_seq DESC)')
    columns={r[1] for r in db.execute('PRAGMA table_info(quote_changes)')}
    for name,kind in (('price_vnd','REAL'),('trading_date','TEXT'),('market_code','TEXT')):
        if name not in columns:db.execute(f'ALTER TABLE quote_changes ADD COLUMN {name} {kind}')


def append(payload,database,retention_days=30):
    stamp=event_time(payload['captured_at']);day=stamp.date().isoformat()
    with sqlite_session(database,timeout=8) as db:
        db.execute('PRAGMA journal_mode=WAL');create(db)
        prior=db.execute('SELECT seq,captured_at,meta_id FROM captures WHERE day=? ORDER BY seq DESC LIMIT 1',(day,)).fetchone()
        meta={k:payload[k] for k in ('schema_version','source','collection_mode','collection_kind','transport','membership','limitations') if k in payload}
        meta_text=encoded(meta);meta_id=sha256(meta_text.encode()).hexdigest()
        cache_key=str(database.resolve());cached=_fingerprint_cache.get(cache_key)
        if cached and prior and cached[0:2]==(day,prior[0]):fingerprints=dict(cached[2])
        else:
            fingerprints=dict(db.execute('SELECT q.symbol,q.fingerprint FROM quote_changes q JOIN (SELECT symbol,MAX(capture_seq) seq FROM quote_changes WHERE day=? GROUP BY symbol) v ON q.symbol=v.symbol AND q.capture_seq=v.seq',(day,))) if prior else {}
        changed=[]
        for quote in payload.get('quotes',[]):
            stable={k:v for k,v in quote.items() if k not in ('received_at','book_event_age_seconds','book_received_at','trade_received_at')}
            fingerprint=sha256(encoded(stable).encode()).hexdigest()
            if fingerprints.get(quote['symbol'])!=fingerprint:changed.append((quote['symbol'],fingerprint,zlib.compress(encoded(quote).encode('utf8')),quote.get('last_price_vnd'),quote.get('trading_date'),quote.get('market_code')))
        # A checkpoint supplies an explicit observation during long quiet spans.
        active=any(phase(stamp,r.get('market_code','HOSE')) in ('continuous_am','continuous_pm') for r in payload.get('quotes',[]))
        due=not prior or (stamp-event_time(prior[1])).total_seconds()>=(60 if active else 1800)
        if not changed and prior and prior[2]==meta_id and not due:return False
        db.execute('INSERT OR IGNORE INTO capture_meta VALUES(?,?)',(meta_id,meta_text))
        cursor=db.execute('INSERT OR IGNORE INTO captures(dataset_id,day,captured_at,meta_id) VALUES(?,?,?,?)',(payload['dataset_id'],day,payload['captured_at'],meta_id))
        if not cursor.rowcount:return False
        seq=cursor.lastrowid
        db.executemany('INSERT INTO quote_changes(capture_seq,day,symbol,fingerprint,payload,price_vnd,trading_date,market_code) VALUES(?,?,?,?,?,?,?,?)',[(seq,day,*r) for r in changed])
        fingerprints.update({r[0]:r[1] for r in changed})
        if len(_fingerprint_cache)>4:_fingerprint_cache.clear()
        _fingerprint_cache[cache_key]=(day,seq,fingerprints)
        cutoff=(stamp.date()-timedelta(days=max(1,int(retention_days))-1)).isoformat()
        db.execute('DELETE FROM quote_changes WHERE day<?',(cutoff,))
        removed=db.execute('DELETE FROM captures WHERE day<?',(cutoff,)).rowcount
        if 'snapshots' in tables(db):db.execute('DELETE FROM snapshots WHERE day<?',(cutoff,))
        if removed:db.execute('DELETE FROM capture_meta WHERE id NOT IN (SELECT DISTINCT meta_id FROM captures)')
        return True


def hydrate(database,identity):
    try:
        with sqlite_session(f'file:{database.as_posix()}?mode=ro',uri=True,timeout=3) as db:
            names=tables(db)
            row=db.execute('SELECT seq,day,captured_at,m.payload FROM captures c JOIN capture_meta m ON m.id=c.meta_id WHERE dataset_id=?',(identity,)).fetchone() if 'captures' in names else None
            if row:
                seq,day,captured,meta=row
                rows=db.execute('SELECT q.payload FROM quote_changes q JOIN (SELECT symbol,MAX(capture_seq) seq FROM quote_changes WHERE day=? AND capture_seq<=? GROUP BY symbol) v ON q.symbol=v.symbol AND q.capture_seq=v.seq',(day,seq))
                return {**json.loads(meta),'dataset_id':identity,'captured_at':captured,'quotes':[decode(x[0]) for x in rows]}
            if 'snapshots' in names:
                row=db.execute('SELECT payload FROM snapshots WHERE dataset_id=?',(identity,)).fetchone()
                if row:return json.loads(row[0])
    except (sqlite3.Error,OSError,ValueError):pass
    return None


@lru_cache(maxsize=20)
def _legacy_series(path,symbol,day,max_seq,limit):
    """The legacy archive stops growing after upgrade; cache its small projection."""
    result=[]
    with sqlite_session(f'file:{path}?mode=ro',uri=True,timeout=4) as db:
        last=db.execute('SELECT payload FROM snapshots WHERE day=? AND seq<=? ORDER BY seq DESC LIMIT 1',(day,max_seq)).fetchone()
        if not last:return ()
        final=json.loads(last[0]);meta={k:final.get(k) for k in ('membership','schema_version','source','collection_mode','collection_kind')}
        membership=final.get('membership') or {}
        known={s for values in (membership.get('universes') or {}).values() for s in values} or set(membership.get('symbols') or [])
        if known and symbol not in known:
            first=db.execute("SELECT json_extract(payload,'$.membership') FROM snapshots WHERE day=? AND seq<=? ORDER BY seq LIMIT 1",(day,max_seq)).fetchone()
            earlier=json.loads(first[0]) if first and first[0] else {}
            old={s for values in (earlier.get('universes') or {}).values() for s in values} or set(earlier.get('symbols') or [])
            if old and symbol not in old:return ()
        index=next((i for i,q in enumerate(final.get('quotes',[])) if q.get('symbol')==symbol),None)
        # Historical membership can change: fall back to symbol lookup per record.
        pointer=f'$.quotes[{index}]' if index is not None else '$.quotes[0]'
        rows=db.execute('''SELECT dataset_id,captured_at,
            CASE WHEN json_extract(payload,?)=? THEN json_extract(payload,?)
            ELSE (SELECT q.value FROM json_each(s.payload,'$.quotes') q WHERE json_extract(q.value,'$.symbol')=? LIMIT 1) END,
            json_extract(payload,'$.source'),json_extract(payload,'$.collection_mode')
            FROM snapshots s WHERE day=? AND seq<=? AND json_valid(payload) ORDER BY seq DESC LIMIT ?''',
            (pointer+'.symbol',symbol,pointer,symbol,day,max_seq,limit))
        for identity,captured,quote,source,mode in rows:
            result.append({**meta,'source':source,'collection_mode':mode,'dataset_id':identity,'captured_at':captured,
                'quotes':[json.loads(quote)] if quote else [],'_compact':True})
    return tuple(reversed(result))


def read_series(database,symbol,*,day=None,limit=10000,recent_days=3):
    if not database.is_file():return []
    result=[];metadata_cache={}
    try:
        with sqlite_session(f'file:{database.as_posix()}?mode=ro',uri=True,timeout=4) as db:
            names=tables(db);days=set()
            for name in ('snapshots','captures'):
                if name in names:days.update(r[0] for r in db.execute(f'SELECT DISTINCT day FROM {name}'))
            selected=[day] if day else sorted(days,reverse=True)[:recent_days]
            for selected_day in selected:
                if 'snapshots' in names:
                    maximum=db.execute('SELECT MAX(seq) FROM snapshots WHERE day=?',(selected_day,)).fetchone()[0]
                    if maximum:result.extend(_legacy_series(database.as_posix(),symbol,selected_day,maximum,limit))
                if 'captures' not in names:continue
                rows=db.execute('''SELECT c.dataset_id,c.captured_at,m.payload,
                    (SELECT payload FROM quote_changes q WHERE q.day=c.day AND q.symbol=? AND q.capture_seq<=c.seq ORDER BY q.capture_seq DESC LIMIT 1)
                    FROM captures c JOIN capture_meta m ON m.id=c.meta_id WHERE c.day=? ORDER BY c.seq DESC LIMIT ?''',(symbol,selected_day,limit))
                for identity,captured,meta,quote in rows:
                    if meta not in metadata_cache:metadata_cache[meta]=json.loads(meta)
                    result.append({**metadata_cache[meta],'dataset_id':identity,'captured_at':captured,'quotes':[decode(quote)] if quote else [],'_compact':True})
    except (OSError,sqlite3.Error,ValueError):pass
    return sorted(result,key=lambda s:event_time(s['captured_at']))[-limit:]


def compact_inventory(db):
    if 'captures' not in tables(db):return []
    return db.execute("""SELECT day,COUNT(*),MIN(captured_at),MAX(captured_at),SUM(CASE WHEN strftime('%w',day) NOT IN ('0','6') AND
        ((substr(captured_at,12,8)>='09:00:00' AND substr(captured_at,12,8)<'11:30:00') OR
         (substr(captured_at,12,8)>='13:00:00' AND substr(captured_at,12,8)<'15:00:00')) THEN 1 ELSE 0 END)
        FROM captures GROUP BY day""").fetchall()


def new_trends(database,day,symbols,max_points=96):
    result={}
    if not database.is_file():return result
    try:
        with sqlite_session(f'file:{database.as_posix()}?mode=ro',uri=True,timeout=3) as db:
            if 'quote_changes' not in tables(db):return result
            for symbol in symbols:
                rows=db.execute('SELECT c.captured_at,q.price_vnd,q.trading_date,q.market_code FROM quote_changes q JOIN captures c ON c.seq=q.capture_seq WHERE q.day=? AND q.symbol=? ORDER BY q.capture_seq DESC LIMIT ?',(day,symbol,max_points*3)).fetchall()
                points=[];previous=None
                for captured,p,trading_date,board in reversed(rows):
                    observed=event_time(captured)
                    if not observed or trading_date!=day or phase(observed,board or 'HOSE') not in ('continuous_am','continuous_pm','closing_auction'):continue
                    if p!=previous:points.append({'timestamp':captured,'last_price_vnd':p,'gap_before':False});previous=p
                if len(points)>max_points:points=[points[round(i*(len(points)-1)/(max_points-1))] for i in range(max_points)]
                if points:result[symbol]=points
    except (sqlite3.Error,OSError,ValueError):pass
    return result
