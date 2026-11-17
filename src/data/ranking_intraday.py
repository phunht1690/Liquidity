"""Whole-session SSI mini-lines for every tracked equity, fetched in one queue.

Product requests only read the compact cache. Backfill uses the existing OHLC
client and its request lock; it never starts an extra socket or a client per row.
"""
from src.data.sqlite_connection import sqlite_session
from copy import deepcopy
from datetime import datetime,timedelta,time as clock_time
from pathlib import Path
from queue import PriorityQueue,Empty
from threading import Event,RLock,Thread
import json,re,sqlite3,time

from src.data.ssi_feed import PROJECT,VN,SSIAPIError,event_time,positive,reference_for_day
from src.data.ohlc_history import history_service


def compact_session(data,quote,now):
    """Keep one real close per 5-minute bar from the most recent available day."""
    candidates={}
    for bar in data.get('bars') or []:
        stamp=event_time(bar.get('timestamp'));price=positive(bar.get('last_price_vnd',bar.get('close')))
        if stamp and stamp<=now and price:
            candidates[stamp.isoformat()]={'timestamp':stamp.isoformat(),'last_price_vnd':price}
    day=max((key[:10] for key in candidates),default=None)
    points=[candidates[key] for key in sorted(candidates) if key.startswith(day)] if day else []
    previous=None
    for point in points:
        stamp=event_time(point['timestamp'])
        point['gap_before']=bool(previous and (stamp-previous).total_seconds()>1800)
        previous=stamp
    reference=reference_for_day(quote,day)
    return {'day':day,'points':points,'reference_price_vnd':reference,
        'updated_at':data.get('updated_at') or now.isoformat(),
        'checked_day':now.date().isoformat(),'checked_at':now.isoformat()}


def line_for_quote(cached,quote,now,daily=None):
    """Update only the tip with an actual later trade, not repeated poll samples."""
    item=cached or {};points=deepcopy(item.get('points') or []);day=item.get('day')
    stamp=event_time(quote.get('source_match_time_raw'));price=positive(quote.get('last_price_vnd'))
    fetched=event_time(item.get('updated_at'))
    if stamp and stamp<=now and stamp.date()==now.date() and price:
        if day and day<stamp.date().isoformat():points=[];day=None
        if day==stamp.date().isoformat() and (not fetched or stamp>fetched):
            bucket=stamp.replace(minute=stamp.minute//5*5,second=0,microsecond=0).isoformat()
            point={'timestamp':bucket,'last_price_vnd':price,'gap_before':False,'source':'latest_trade'}
            if points and bucket==points[-1]['timestamp']:
                point['gap_before']=points[-1].get('gap_before',False);points[-1]=point
            elif not points or bucket>points[-1]['timestamp']:
                point['gap_before']=bool(points and (event_time(bucket)-event_time(points[-1]['timestamp'])).total_seconds()>1800)
                points.append(point)
        elif not points:
            # One quote is a real point, never a manufactured line.
            day=stamp.date().isoformat();points=[{'timestamp':stamp.isoformat(),'last_price_vnd':price,'gap_before':False,'source':'latest_trade'}]
    reference=reference_for_day(quote,day) or (positive(item.get('reference_price_vnd')) if item.get('day')==day else None)
    change=(points[-1]['last_price_vnd']/reference-1)*100 if points and reference else None
    if change is None and daily and daily.get('day')==day:change=daily.get('change_percent')
    return {'points':points,'day':day,'change_percent':change,'updated_at':item.get('updated_at')}


class IntradaySparklines:
    def __init__(self,*,database=None,history=None,enabled=True,delay=.35):
        self.database=Path(database or PROJECT/'data/ssi/intraday_trends.sqlite3')
        self.history=history;self.enabled=enabled;self.delay=delay
        self.lock=RLock();self.stop=Event();self.queue=PriorityQueue();self.pending={}
        self.quotes={};self.cache={};self.failures={};self.last_error=None;self.retry_at=0;self.serial=0;self.thread=None
        if self.database.is_file():
            try:
                with sqlite_session(f'file:{self.database.as_posix()}?mode=ro',uri=True,timeout=3) as db:
                    self.cache={s:json.loads(p) for s,p in db.execute('SELECT symbol,payload FROM intraday_lines')}
            except (OSError,ValueError,sqlite3.Error):pass

    def request(self,quote,now,priority=10):
        symbol=quote.get('symbol')
        if not self.enabled or not isinstance(symbol,str) or not re.fullmatch(r'[A-Z0-9]{2,6}',symbol):return
        with self.lock:
            self.quotes[symbol]=dict(quote);item=self.cache.get(symbol) or {}
            checked=event_time(item.get('checked_at'))
            active=now.weekday()<5 and clock_time(9)<=now.time().replace(tzinfo=None)<clock_time(15,5)
            ttl=(60 if priority==0 else 300) if active else 10800
            final_refresh=bool(checked and now.weekday()<5 and now.time().replace(tzinfo=None)>=clock_time(15,5)
                and checked.date()==now.date() and checked.time().replace(tzinfo=None)<clock_time(15,5))
            trade=event_time(quote.get('source_match_time_raw'))
            new_session=bool(trade and trade<=now and item.get('day') and trade.date().isoformat()>item['day'])
            recheck_invalid=item.get('fetch_status')=='unavailable' and item.get('error_code')=='invalid_market_response'
            if checked and checked.date()==now.date() and (now-checked).total_seconds()<ttl and not final_refresh and not new_session and not recheck_invalid:return
            if self.failures.get(symbol,0)>time.time():return
            if time.time()<self.retry_at:return
            # Backfill missing stocks before refreshing already usable curves.
            # Repeated quote polls and changing table ranks cannot starve them.
            if not item.get('points'):priority=min(priority,3)
            previous=self.pending.get(symbol)
            if previous and previous[0]<=priority:return
            self.serial+=1;job=(priority,self.serial);self.pending[symbol]=job
            self.queue.put((*job,symbol))
            if not self.thread or not self.thread.is_alive():
                self.thread=Thread(target=self._run,daemon=True,name='ssi-intraday-lines');self.thread.start()

    def _fetch(self,symbol,quote,now):
        if self.history is None:self.history=history_service()
        provider=self.history
        # Fetch only the known trade's session in the common case. A broad
        # lookback is reserved for symbols whose session has no returned bars.
        trade=event_time(quote.get('source_match_time_raw'))
        anchor=trade if trade and trade<=now else now
        start=anchor.replace(hour=0,minute=0,second=0,microsecond=0)
        end=anchor.replace(hour=23,minute=59,second=59,microsecond=0)
        spec={'key':'mini-'+symbol,'symbol':symbol,'range':'session','timeframe':'5m',
              'start':start,'end':end,'now':now,'quote':quote}
        fetch=getattr(provider,'background_fetch',lambda spec:provider._fetch(spec,persist=False))
        data=fetch(spec)
        if not data.get('bars'):
            spec={**spec,'start':(now-timedelta(days=10)).replace(hour=0,minute=0,second=0,microsecond=0),
                  'end':now.replace(hour=23,minute=59,second=59,microsecond=0)}
            data=fetch(spec)
        return compact_session(data,quote,now)

    def _store(self,symbol,item):
        self.database.parent.mkdir(parents=True,exist_ok=True)
        with sqlite_session(self.database,timeout=4) as db:
            db.execute('CREATE TABLE IF NOT EXISTS intraday_lines(symbol TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('INSERT OR REPLACE INTO intraday_lines VALUES(?,?)',(symbol,json.dumps(item,ensure_ascii=False,allow_nan=False)))
        with self.lock:self.cache[symbol]=item

    def _run(self):
        while not self.stop.is_set():
            try:priority,serial,symbol=self.queue.get(timeout=2)
            except Empty:continue
            with self.lock:
                if self.pending.get(symbol)!=(priority,serial):self.queue.task_done();continue
                quote=dict(self.quotes[symbol])
            try:
                if self.stop.wait(max(0,self.retry_at-time.time())):break
                now=datetime.now(VN);item=self._fetch(symbol,quote,now)
                with self.lock:old=self.cache.get(symbol)
                if not item['points'] and old and old.get('points'):
                    item={**old,'checked_day':item['checked_day'],'checked_at':item['checked_at']}
                self._store(symbol,item)
                with self.lock:self.failures.pop(symbol,None)
            except SSIAPIError as exc:
                # Respect the account-wide cooldown; never rotate keys for 429.
                global_failure=exc.code in ('rate_limited','market_access_denied','authentication_failed','missing_credentials') or exc.http_status in (401,403,429) or exc.http_status is None and exc.code=='source_unavailable'
                with self.lock:
                    self.last_error={'symbol':symbol,'code':exc.code,'http_status':exc.http_status}
                    if global_failure:self.retry_at=time.time()+max(60,exc.retry_after or 60)
                    else:self.failures[symbol]=time.time()+900
                provider=self.history
                if provider and global_failure:
                    with provider.lock:provider.retry_at=max(provider.retry_at,self.retry_at)
                if not global_failure:
                    # A ticker-specific rejection must not stall every other
                    # stock. Keep any real old curve; otherwise record no bars.
                    with self.lock:old=self.cache.get(symbol)
                    item={**(old or {'day':None,'points':[],'updated_at':None}),
                        'checked_day':now.date().isoformat(),'checked_at':now.isoformat(),
                        'fetch_status':'unavailable','error_code':exc.code,'http_status':exc.http_status}
                    try:self._store(symbol,item)
                    except (OSError,sqlite3.Error):pass
            except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):
                with self.lock:self.retry_at=time.time()+60
            finally:
                with self.lock:
                    if self.pending.get(symbol)==(priority,serial):self.pending.pop(symbol,None)
                self.queue.task_done()
            if self.stop.wait(self.delay):break

    def enrich(self,product,latest):
        now=event_time(product.get('runtime',{}).get('now')) or datetime.now(VN)
        quotes={r['symbol']:r for r in latest.get('quotes',[]) if isinstance(r,dict) and isinstance(r.get('symbol'),str)}
        selected=product['selected']['symbol'];rows=product.get('ranking') or []
        priority={s:2 for s in (latest.get('membership',{}).get('universes',{}).get('VN30') or [])}
        priority.update({r['symbol']:1 for r in rows[:25]});priority[selected]=0
        for symbol in sorted(quotes,key=lambda s:(priority.get(s,10),s)):
            self.request(quotes[symbol],now,priority.get(symbol,10))
        with self.lock:cache=dict(self.cache);pending=set(self.pending)
        targets={r['symbol']:r for r in rows};targets.setdefault(selected,product['selected'])
        for symbol,row in targets.items():
            line=line_for_quote(cache.get(symbol),quotes.get(symbol,{}),now,row.get('daily_statistics'))
            row.update(price_trend=line['points'],price_trend_day=line['day'],price_trend_change_percent=line['change_percent'],
                price_trend_updated_at=line['updated_at'],price_trend_source='ssi_ohlc_5m',price_trend_pending=symbol in pending)
        days={r['price_trend_day'] for r in rows if r.get('price_trend') and r.get('price_trend_day')}
        common_day=next(iter(days)) if len(days)==1 else None
        product['selected']=dict(targets[selected]);product['ranking_history_day']=common_day
        product['ranking_trend']={'source':'ssi_ohlc_5m','timeframe':'5m','day':common_day,
            'ready':sum(len(r['price_trend'])>=2 for r in rows),'total':len(rows),
            'queued':len(pending),'tracked':len(quotes),'cached':sum(bool(cache.get(s,{}).get('points')) for s in quotes),
            'checked':sum(s in cache for s in quotes),'backoff_seconds':max(0,round(self.retry_at-time.time())),
            'last_fetch_error':self.last_error}
        return product


_service=None;_lock=RLock()


def enrich_ranking_intraday(product,latest):
    global _service
    with _lock:
        if _service is None:_service=IntradaySparklines()
    return _service.enrich(product,latest)
