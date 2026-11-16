"""Bounded local price samples for all table rows, without per-ticker API calls."""
from copy import deepcopy
from datetime import time
import json
from pathlib import Path
import sqlite3
from threading import Lock

from src.data.live_analytics import SOURCE, _automatic, _stamp, receiver_phase
from src.data.price_history import price_fields
from src.data.ssi_runtime import DATABASE

_lock = Lock()
_cached_key = None
_cached_value = None


def _in_session(stamp):
    clock = stamp.time().replace(tzinfo=None)
    return stamp.weekday() < 5 and (time(9) <= clock <= time(11, 30)
                                   or time(13) <= clock <= time(14, 46))


def load_ranking_sparklines(latest, *, database=DATABASE, max_points=96):
    """Sample actual saved observations across the latest capture day.

    Only metadata is scanned for the day; at most max_points full payloads are
    decoded, one at a time, for the entire universe. The current observation is
    included once after hours so repeated cached quotes do not flatten the day.
    A single shared memory cache is reused across symbol/notional/filter changes.
    """
    stamp = _stamp(latest.get('captured_at'))
    if not stamp or latest.get('source') != SOURCE or not _automatic(latest):
        return {'day': None, 'points': {}}
    path = Path(database)
    count = max(2, min(160, int(max_points)))
    # Midnight/startup receipts are not a new trading session. Keep the last
    # real session's stored mini-lines instead of replacing them with blanks.
    market_days=[r['trading_date'] for r in latest.get('quotes',[]) if isinstance(r.get('trading_date'),str) and r.get('last_price_vnd') and _stamp(r['trading_date']+'T00:00:00+07:00')]
    market_day=max((d for d in market_days if d<=stamp.date().isoformat()),default=stamp.date().isoformat())
    if market_day<stamp.date().isoformat() and path.is_file():
        from src.data.observation_store import tables,hydrate
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True,timeout=3) as db:
            candidates=[];names=tables(db)
            for name in ('snapshots','captures'):
                if name in names:
                    row=db.execute(f'SELECT dataset_id,captured_at FROM {name} WHERE day=? ORDER BY seq DESC LIMIT 1',(market_day,)).fetchone()
                    if row:candidates.append(row)
        saved=hydrate(path,max(candidates,key=lambda r:r[1])[0]) if candidates else None
        if saved:return load_ranking_sparklines(saved,database=path,max_points=count)
    key = (str(path.resolve()), latest.get('dataset_id'), latest['captured_at'], count)
    global _cached_key, _cached_value
    with _lock:
        if key == _cached_key:
            return deepcopy(_cached_value)
        result = _read_samples(latest, stamp, path, count)
        from src.data.observation_store import new_trends
        extra=new_trends(path,result['day'],result['points'],count)
        for symbol,points in extra.items():
            merged=sorted(result['points'].get(symbol,[])+points,key=lambda p:p['timestamp'])
            if len(merged)>count:merged=[merged[round(i*(len(merged)-1)/(count-1))] for i in range(count)]
            result['points'][symbol]=merged
        _cached_key, _cached_value = key, result
        return deepcopy(result)


def _read_samples(latest, stamp, path, count):
    symbols = {r['symbol'] for r in latest.get('quotes', [])
               if isinstance(r, dict) and isinstance(r.get('symbol'), str)}
    result = {'day': stamp.date().isoformat(), 'points': {s: [] for s in sorted(symbols)}}
    records = []
    try:
        if path.is_file():
            with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=3) as db:
                metadata = db.execute('SELECT seq,dataset_id,captured_at FROM snapshots '
                                      'WHERE day=? ORDER BY seq', (result['day'],)).fetchall()
                for seq, identity, captured in metadata:
                    observed = _stamp(captured)
                    if observed and observed.date() == stamp.date() and observed <= stamp and _in_session(observed):
                        records.append((seq, identity, captured, observed))
                # Include latest exactly once, even if it is not stored yet.
                records = [r for r in records if r[1] != latest.get('dataset_id')]
                records.append((None, latest.get('dataset_id'), latest['captured_at'], stamp))
                records.sort(key=lambda r: (r[3], r[0] is None, r[0] or 0))
                indices = sorted({round(i * (len(records) - 1) / (count - 1)) for i in range(count)})
                chosen = [records[i] for i in indices]
                ids = [r[0] for r in chosen if r[0] is not None]
                # Cursor iteration keeps at most one decoded quote array alive.
                # Order by sampled chronology even if a late write inserted an
                # older capture after newer observations.
                order = 'CASE seq ' + ' '.join(f'WHEN {int(seq)} THEN {i}' for i, seq in enumerate(ids)) + ' END'
                payloads = db.execute('SELECT seq,payload FROM snapshots WHERE seq IN ('
                                      + ','.join('?' for _ in ids) + ') ORDER BY ' + order, ids) if ids else []
                lookup = {r[0]: i for i, r in enumerate(chosen) if r[0] is not None}
                series = {s: [] for s in symbols}
                gap_prefix = [0]
                previous = None
                for record in records:
                    observed = record[3]
                    phase = receiver_phase(observed)
                    threshold = 35 if phase in ('continuous_am', 'continuous_pm') else 90
                    gap = previous is not None and (observed - previous).total_seconds() > threshold
                    gap_prefix.append(gap_prefix[-1] + int(gap))
                    previous = observed
                positions = {r[1]: i for i, r in enumerate(records)}
                prior_position = None

                def consume(snapshot, record):
                    nonlocal prior_position
                    position = positions[record[1]]
                    gap = prior_position is not None and gap_prefix[position + 1] > gap_prefix[prior_position + 1]
                    usable = snapshot.get('source') == SOURCE and _automatic(snapshot)
                    quotes = {r.get('symbol'): r for r in snapshot.get('quotes', []) if isinstance(r, dict)} if usable else {}
                    for symbol in symbols:
                        price = price_fields(quotes.get(symbol), record[2])['last_price_vnd']
                        series[symbol].append({'timestamp': record[2], 'last_price_vnd': price, 'gap_before': gap})
                    prior_position = position

                for seq, encoded in payloads:
                    record = chosen[lookup[seq]]
                    try:
                        snapshot = json.loads(encoded)
                        if not isinstance(snapshot, dict): snapshot = {}
                    except (TypeError, ValueError): snapshot = {}
                    consume(snapshot, record)
                consume(latest, chosen[-1])
                result['points'] = series
                return result
    except (sqlite3.Error, OSError, ValueError):
        pass
    # Missing local history produces only genuine current points, never a trend.
    for raw in latest.get('quotes', []):
        if not isinstance(raw, dict) or raw.get('symbol') not in symbols: continue
        price = price_fields(raw, latest['captured_at'])['last_price_vnd']
        result['points'][raw['symbol']] = [{'timestamp': latest['captured_at'], 'last_price_vnd': price, 'gap_before': False}]
    return result
