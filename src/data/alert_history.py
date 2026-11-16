"""Journal actual live observations, with no inferred alert onset or gap filling."""
from hashlib import sha256
from pathlib import Path
from threading import RLock
import json,sqlite3
from src.data.ssi_feed import PROJECT,event_time

_lock=RLock()


def attach_history(product,database=None,*,retention_days=30):
    database=Path(database or PROJECT/'data/ssi/alert_history.sqlite3')
    analysis=product.get('analysis') or {};stamp=event_time(analysis.get('asof'))
    product['alert_history']=[]
    if stamp is None:return product
    live=analysis.get('mode')=='live';day=stamp.date().isoformat()
    if not live and not database.is_file():return product
    key=sha256(json.dumps([product['universe'],product['group'],product['notional_vnd'],product['alert_rules']['spread_threshold_bps']]).encode()).hexdigest()[:24]
    with _lock:
        database.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(database,timeout=4) as db:
            db.execute('CREATE TABLE IF NOT EXISTS alert_runs(id INTEGER PRIMARY KEY,scope TEXT,day TEXT,symbol TEXT,kind TEXT,first_at TEXT,last_at TEXT,resolved_at TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS alert_scope_day ON alert_runs(scope,day,symbol,kind,last_at)')
            if live:
                active={(a['symbol'],r['kind']) for a in product['alerts'] for r in a['reasons']}
                eligible={r['symbol'] for r in product['ranking'] if r['valid']}
                opened=db.execute('SELECT id,symbol,kind,first_at,last_at FROM alert_runs WHERE scope=? AND day=? AND resolved_at IS NULL',(key,day)).fetchall()
                current={(s,k):(identity,a,b) for identity,s,k,a,b in opened}
                max_gap=max(35,3*(product.get('runtime',{}).get('poll_seconds') or 5))
                for pair,(identity,first,last) in list(current.items()):
                    elapsed=(stamp-event_time(last)).total_seconds()
                    if elapsed<0:continue
                    if pair not in active and pair[0] in eligible:
                        # Across a gap we know only the old last observation,
                        # not when the condition disappeared while unobserved.
                        resolved=stamp.isoformat() if elapsed<=max_gap else last
                        db.execute('UPDATE alert_runs SET resolved_at=? WHERE id=?',(resolved,identity))
                    elif pair in active and elapsed<=max_gap:
                        db.execute('UPDATE alert_runs SET last_at=? WHERE id=?',(stamp.isoformat(),identity))
                    elif pair in active:
                        # No evidence of what happened in the gap. End the old
                        # observation run at its last receipt, not at reconnection.
                        db.execute('UPDATE alert_runs SET resolved_at=last_at WHERE id=?',(identity,));current.pop(pair,None)
                for symbol,kind in active:
                    if (symbol,kind) not in current:
                        db.execute('INSERT INTO alert_runs(scope,day,symbol,kind,first_at,last_at) VALUES(?,?,?,?,?,?)',(key,day,symbol,kind,stamp.isoformat(),stamp.isoformat()))
                from datetime import timedelta
                days=max(1,min(60,int(retention_days)))
                db.execute('DELETE FROM alert_runs WHERE day<?',((stamp.date()-timedelta(days=days-1)).isoformat(),))
            records=db.execute('SELECT symbol,kind,first_at,last_at,resolved_at FROM alert_runs WHERE scope=? AND day=? AND first_at<=? AND (resolved_at IS NULL OR resolved_at>=?) ORDER BY last_at DESC',(key,day,stamp.isoformat(),stamp.isoformat())).fetchall()
            history=db.execute('SELECT symbol,kind,first_at,last_at,resolved_at FROM alert_runs WHERE scope=? AND day=? AND first_at<=? ORDER BY last_at DESC LIMIT 20',(key,day,stamp.isoformat())).fetchall()
    for alert in product['alerts']:
        matches=[r for r in records if r[0]==alert['symbol'] and r[1] in {x['kind'] for x in alert['reasons']} and (not r[4] or r[4]>=stamp.isoformat())]
        if matches:
            first=min(r[2] for r in matches);last=min(stamp.isoformat(),max(r[3] for r in matches))
            alert['observation']={'first_at':first,'last_at':last,'duration_seconds':max(0,(event_time(last)-event_time(first)).total_seconds()),'basis':'observed_live_run'}
    product['alert_history']=[{'symbol':s,'kind':k,'first_at':a,'last_at':min(b,stamp.isoformat()),'resolved_at':c} for s,k,a,b,c in history]
    return product
