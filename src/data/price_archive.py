"""Bounded OHLCV history; never used as a historical order book.

One row per provider candle. Coverage is recorded only for fully requested days
and complete responses; missing candles are never filled or interpolated.
"""
from src.data.sqlite_connection import sqlite_session
from datetime import datetime, timedelta, time as day_time
from pathlib import Path
import sqlite3
import time

from src.data.ssi_feed import PROJECT, VN, event_time, positive, reference_for_day


class PriceArchive:
    def __init__(self, database=None, *, retention_days=30):
        self.database = Path(database or PROJECT/'data/ssi/price_bars.sqlite3')
        self.retention_days = max(1, min(35, int(retention_days)))
        self._inventory = None
        self._inventory_at = 0

    def _create(self, db):
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS price_bars(
            symbol TEXT NOT NULL,timeframe TEXT NOT NULL,stamp TEXT NOT NULL,day TEXT NOT NULL,
            open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,close REAL NOT NULL,
            volume REAL NOT NULL,value REAL,PRIMARY KEY(symbol,timeframe,stamp)) WITHOUT ROWID''')
        db.execute('CREATE INDEX IF NOT EXISTS price_bars_day ON price_bars(day)')
        db.execute('''CREATE TABLE IF NOT EXISTS price_days(
            symbol TEXT NOT NULL,timeframe TEXT NOT NULL,day TEXT NOT NULL,
            checked_at TEXT NOT NULL,closed INTEGER NOT NULL,bar_count INTEGER NOT NULL,
            PRIMARY KEY(symbol,timeframe,day)) WITHOUT ROWID''')
        db.execute('CREATE INDEX IF NOT EXISTS price_days_day ON price_days(day)')

    def record(self, data, spec):
        now = spec['now'].astimezone(VN)
        cutoff = (now.date()-timedelta(days=self.retention_days-1)).isoformat()
        bars = [b for b in data.get('bars', []) if b['trading_date'] >= cutoff]
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite_session(self.database, timeout=5) as db:
            self._create(db)
            db.executemany('''INSERT INTO price_bars VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol,timeframe,stamp) DO UPDATE SET
                open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
                volume=excluded.volume,value=excluded.value''',
                [(spec['symbol'],spec['timeframe'],b['timestamp'],b['trading_date'],
                  b['open'],b['high'],b['low'],b['close'],b['volume_shares'],b.get('value_vnd')) for b in bars])
            # A short relative window must not claim that the whole day is held.
            if data.get('complete_range') is True and not data.get('invalid_records'):
                day = max(spec['start'].date(), datetime.fromisoformat(cutoff).date())
                while day <= min(spec['end'].date(), now.date()):
                    start = datetime.combine(day, day_time(), VN)
                    end = datetime.combine(day, day_time(23,59,59), VN)
                    if spec['start'] <= start and spec['end'] >= end:
                        closed = day < now.date() or now.time().replace(tzinfo=None) >= day_time(15,15)
                        count = db.execute('SELECT COUNT(*) FROM price_bars WHERE symbol=? AND timeframe=? AND day=?',
                            (spec['symbol'],spec['timeframe'],day.isoformat())).fetchone()[0]
                        db.execute('INSERT OR REPLACE INTO price_days VALUES(?,?,?,?,?,?)',
                            (spec['symbol'],spec['timeframe'],day.isoformat(),now.isoformat(),int(closed),count))
                    day += timedelta(days=1)
            db.execute('DELETE FROM price_bars WHERE day<?', (cutoff,))
            db.execute('DELETE FROM price_days WHERE day<?', (cutoff,))

    def coverage(self, symbol, timeframe):
        if not self.database.is_file(): return {}
        try:
            with sqlite_session(f'file:{self.database.as_posix()}?mode=ro', uri=True, timeout=3) as db:
                return {d:{'checked_at':checked,'closed':bool(closed),'bars':count}
                    for d,checked,closed,count in db.execute(
                        'SELECT day,checked_at,closed,bar_count FROM price_days WHERE symbol=? AND timeframe=?', (symbol,timeframe))}
        except (OSError,sqlite3.Error): return {}

    def prune(self, now):
        if not self.database.is_file():return
        cutoff=(now.astimezone(VN).date()-timedelta(days=self.retention_days-1)).isoformat()
        with sqlite_session(self.database,timeout=5) as db:
            removed=db.execute('DELETE FROM price_bars WHERE day<?',(cutoff,)).rowcount
            removed+=db.execute('DELETE FROM price_days WHERE day<?',(cutoff,)).rowcount
        if removed:self._inventory=None

    def missing_ranges(self, symbol, timeframe, start, end, now, *, current_ttl=600):
        coverage = self.coverage(symbol,timeframe)
        missing = []
        day = start
        while day <= end:
            item = coverage.get(day.isoformat())
            checked = event_time(item.get('checked_at')) if item else None
            fresh = bool(checked and 0 <= (now-checked).total_seconds() < current_ttl)
            # Recheck recent empty days in case SSI publishes late. A complete
            # empty response for an older day is held too; repeatedly downloading
            # every historical weekend would otherwise dominate the API queue.
            old_day=(now.date()-day).days>=3
            held = bool(item and item['closed'] and (item['bars'] or old_day or checked and 0 <= (now-checked).total_seconds() < 21600))
            if not (held or fresh):
                if missing and missing[-1][1]+timedelta(days=1) == day: missing[-1] = (missing[-1][0],day)
                else: missing.append((day,day))
            day += timedelta(days=1)
        return missing

    def read(self, spec, *, allow_partial=False):
        if not self.database.is_file(): return None
        missing = self.missing_ranges(spec['symbol'],spec['timeframe'],spec['start'].date(),
            min(spec['end'].date(),spec['now'].date()),spec['now'],current_ttl=30)
        if missing and not allow_partial: return None
        try:
            with sqlite_session(f'file:{self.database.as_posix()}?mode=ro', uri=True, timeout=3) as db:
                rows = db.execute('''SELECT stamp,day,open,high,low,close,volume,value FROM price_bars
                    WHERE symbol=? AND timeframe=? AND stamp>=? AND stamp<=? ORDER BY stamp''',
                    (spec['symbol'],spec['timeframe'],spec['start'].isoformat(),min(spec['end'],spec['now']).isoformat())).fetchall()
        except (OSError,sqlite3.Error): return None
        if not rows and missing: return None
        quote = spec['quote']
        from src.data.ohlc_history import TIMEFRAMES
        bars = []
        for stamp,day,o,h,l,c,v,value in rows:
            observed = event_time(stamp)
            bars.append({'timestamp':stamp,'trading_date':day,'open':o,'high':h,'low':l,'close':c,
                'last_price_vnd':c,'volume_shares':v,'value_vnd':value,
                'reference_price_vnd':reference_for_day(quote,day),
                'is_closed':observed+timedelta(seconds=TIMEFRAMES[spec['timeframe']])<=spec['now'] if spec['timeframe']!='1d'
                    else observed.date()<spec['now'].date() or spec['now'].time().replace(tzinfo=None)>=day_time(15)})
        checks = self.coverage(spec['symbol'],spec['timeframe'])
        checked = max((v['checked_at'] for d,v in checks.items() if spec['start'].date().isoformat()<=d<=spec['end'].date().isoformat()),default=None)
        return {'source':'ssi_fastconnect_ohlc','symbol':spec['symbol'],'range':spec['range'],'timeframe':spec['timeframe'],
            'price_unit':'VND','volume_unit':'shares','requested_from':spec['start'].isoformat(),'requested_to':spec['end'].isoformat(),
            'updated_at':checked,'bars':bars,'invalid_records':0,'complete_range':not missing,
            'timestamp_basis':'exchange_bar_time','value_basis':'ssi_ohlc_value_not_verified_as_turnover',
            'local_archive':True,'cached':True,'refreshing':False}

    def latest_time(self,symbol,now):
        """Last actual candle for one issuer, within the retained date window."""
        if not self.database.is_file():return None
        cutoff=(now.astimezone(VN).date()-timedelta(days=self.retention_days-1)).isoformat()
        try:
            with sqlite_session(f'file:{self.database.as_posix()}?mode=ro',uri=True,timeout=3) as db:
                row=db.execute('SELECT MAX(stamp) FROM price_bars WHERE symbol=? AND day>=? AND stamp<=?',
                               (symbol,cutoff,now.isoformat())).fetchone()
            return event_time(row[0]) if row and row[0] else None
        except (OSError,sqlite3.Error):return None

    def inventory(self):
        if self._inventory is not None and time.monotonic()-self._inventory_at<20: return dict(self._inventory)
        result = {'bars':0,'symbols':0,'first_day':None,'last_day':None,'bytes':0,'retention_days':self.retention_days}
        if self.database.is_file():
            try:
                with sqlite_session(f'file:{self.database.as_posix()}?mode=ro', uri=True, timeout=3) as db:
                    n,s,first,last = db.execute('SELECT COUNT(*),COUNT(DISTINCT symbol),MIN(day),MAX(day) FROM price_bars').fetchone()
                    result.update(bars=n,symbols=s,first_day=first,last_day=last)
                result['bytes'] = sum(p.stat().st_size for p in (self.database,self.database.with_name(self.database.name+'-wal')) if p.is_file())
            except (OSError,sqlite3.Error): pass
        self._inventory,self._inventory_at = result,time.monotonic()
        return dict(result)
