"""Recent market trades only. Never read credentials or private channel events."""
from src.data.sqlite_connection import sqlite_session
from pathlib import Path
import json,sqlite3
from src.data.ssi_feed import PROJECT,event_time,positive,numeric


def prepare_trade_index(database=None):
    path=Path(database or PROJECT/'data/ssi/events.sqlite3')
    if not path.is_file():return
    try:
        with sqlite_session(path,timeout=5) as db:
            db.execute("CREATE INDEX IF NOT EXISTS events_symbol_seq ON events(json_extract(payload,'$.data.s'),seq)")
    except (OSError,sqlite3.Error):pass


def recent_trades(symbol,*,database=None,limit=12):
    path=Path(database or PROJECT/'data/ssi/events.sqlite3')
    if not path.is_file():return []
    result=[]
    try:
        with sqlite_session(f'file:{path.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            rows=db.execute("SELECT payload FROM events WHERE json_extract(payload,'$.data.s')=? AND json_extract(payload,'$.topic')=? ORDER BY seq DESC LIMIT ?",(symbol,'trade.'+symbol,max(1,min(30,int(limit))))).fetchall()
        for row in rows:
            d=json.loads(row[0]).get('data') or {};stamp=event_time(d.get('t'));p=positive(d.get('p'));q=numeric(d.get('q'))
            if not stamp or p is None or q is None or q<0:continue
            result.append({'timestamp':stamp.isoformat(),'price_vnd':p,'quantity_shares':q,'side':d.get('si') if d.get('si') in ('B','S') else None})
    except (sqlite3.Error,OSError,ValueError):pass
    return result
