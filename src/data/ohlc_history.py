"""Documented, read-only SSI OHLC with a bounded local market-data cache.

No credentials, authentication or threads are used on import. The independent
history client never starts a WebSocket or changes the live collector's state.
"""
from datetime import datetime, timedelta, time as day_time
from pathlib import Path
from threading import Condition, Event, RLock, Thread
import json, re, sqlite3, time

from src.data.ssi_feed import PROJECT,VN,SSISession,SSIAPIError,event_time,positive,numeric,load_snapshot,reference_for_day

TIMEFRAMES={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'1d':86400}
RANGES={'15m':timedelta(minutes=15),'30m':timedelta(minutes=30),'1h':timedelta(hours=1),
        '2h':timedelta(hours=2),'4h':timedelta(hours=4),'1w':timedelta(days=7),
        '1mo':timedelta(days=31),'3mo':timedelta(days=93),'1y':timedelta(days=366)}
MAX_DAYS={'1m':7,'5m':35,'15m':100,'30m':200,'1h':366,'1d':366}


def resolve_query(query,latest,now=None,*,session_anchor=None):
    if set(query)-{'symbol','range','timeframe','from','to'} or any(len(v)!=1 for v in query.values()):
        raise ValueError('Bộ lọc biểu đồ không hợp lệ')
    now=(now or datetime.now(VN)).astimezone(VN)
    symbol=query.get('symbol',['FPT'])[0].upper()
    if not re.fullmatch(r'[A-Z0-9]{2,6}',symbol):raise ValueError('Mã không hợp lệ')
    groups=(latest.get('membership') or {}).get('universes') or {}
    allowed={s for items in groups.values() for s in items} or {r['symbol'] for r in latest.get('quotes',[])}
    if symbol not in allowed:raise ValueError('Mã chưa có trong bộ dữ liệu')
    row=next((r for r in latest.get('quotes',[]) if r.get('symbol')==symbol),{})
    anchor=event_time(row.get('source_match_time_raw')) or event_time(row.get('trading_date')) or session_anchor or now
    if anchor>now:anchor=now
    # Relative windows include HNX's post-close session and UPCOM's last
    # continuous minutes. The official SSI schedule ends both at 15:00.
    board=row.get('market_code','HOSE')
    close=day_time(15,0) if board in ('HNX','UPCOM') else day_time(14,45)
    # A relative view is anchored to the last real trading session outside hours.
    if anchor.date()==now.date() and now.time()<close:
        end=now if now.time()<day_time(11,30) or now.time()>=day_time(13) else now.replace(hour=11,minute=30,second=0,microsecond=0)
    else:end=anchor.replace(hour=close.hour,minute=close.minute,second=0,microsecond=0)
    tf=query.get('timeframe',['5m'])[0];span=query.get('range',['session'])[0]
    if tf not in TIMEFRAMES or span not in {*RANGES,'session','custom'}:raise ValueError('Khoảng hoặc đơn vị nến không hợp lệ')
    if span=='custom':
        start_day=query.get('from',[''])[0];end_day=query.get('to',[''])[0]
        try:
            start=datetime.strptime(start_day,'%Y-%m-%d').replace(tzinfo=VN)
            end=datetime.strptime(end_day,'%Y-%m-%d').replace(tzinfo=VN,hour=23,minute=59,second=59)
        except ValueError:raise ValueError('Ngày không hợp lệ') from None
        if start.strftime('%Y-%m-%d')!=start_day or end.strftime('%Y-%m-%d')!=end_day:raise ValueError('Ngày không hợp lệ')
        if end.date()>now.date():raise ValueError('Không lấy ngày trong tương lai')
    elif span=='session':
        start=end.replace(hour=0,minute=0,second=0,microsecond=0)
        end=end.replace(hour=23,minute=59,second=59,microsecond=0)
    else:
        start=end-RANGES[span]
    if start>end or (end-start).total_seconds()>MAX_DAYS[tf]*86400:
        raise ValueError('Chọn đơn vị nến lớn hơn cho khoảng ngày này')
    # Keep existing full-session caches; earlier relative HNX/UPCOM caches used
    # the wrong minute bounds and must not be reused for the corrected view.
    version=3 if board in ('HNX','UPCOM') and span not in ('session','custom') else 2
    key=json.dumps([version,symbol,span,tf,start.date().isoformat(),end.date().isoformat()],separators=(',',':'))
    return {'key':key,'symbol':symbol,'range':span,'timeframe':tf,'start':start,'end':end,'now':now,'quote':row}


def normalize_bars(records,spec):
    bars={};invalid=0
    for r in records:
        if not isinstance(r,dict) or r.get('symbol')!=spec['symbol']:invalid+=1;continue
        stamp=event_time(r.get('tradingDate'))
        o,h,l,c=(positive(r.get(k)) for k in ('open','high','low','close'))
        v=numeric(r.get('volume'))
        if not stamp or any(x is None for x in (o,h,l,c)) or h<max(o,c) or l>min(o,c) or h<l or v is None or v<0:
            invalid+=1;continue
        if not spec['start']<=stamp<=spec['end']:continue
        if stamp>spec['now']:continue
        day=stamp.date().isoformat();quote=spec['quote']
        reference=reference_for_day(quote,day)
        bars[stamp.isoformat()]={'timestamp':stamp.isoformat(),'trading_date':day,
            'open':o,'high':h,'low':l,'close':c,'last_price_vnd':c,'volume_shares':v,
            'reference_price_vnd':reference,'value_vnd':numeric(r.get('value')),
            'is_closed':stamp+timedelta(seconds=TIMEFRAMES[spec['timeframe']])<=spec['now'] if spec['timeframe']!='1d'
                         else stamp.date()<spec['now'].date() or spec['now'].time()>=day_time(15)}
    return [bars[k] for k in sorted(bars)],invalid


class OHLCHistory:
    def __init__(self,*,database=None,env_file=None,session_factory=None,latest_loader=None,archive=None,request_interval=.5):
        self.database=Path(database or PROJECT/'data/ssi/chart_history.sqlite3')
        self.env_file=Path(env_file or PROJECT/'.env')
        self.factory=session_factory or SSISession;self.latest_loader=latest_loader or load_snapshot
        self.client=None;self.lock=RLock();self.inflight={};self.retry_at=0
        from src.data.price_archive import PriceArchive
        self.archive=archive or PriceArchive(self.database.with_name('price_bars.sqlite3'))
        self.request_interval=request_interval
        self.gate=Condition();self.request_active=False;self.foreground_waiters=0;self.next_request=0

    def _request(self,params,*,background=False):
        """A shared OHLC lane: interactive charts go before queued history pages."""
        with self.gate:
            if not background:self.foreground_waiters+=1
            try:
                while self.request_active or background and self.foreground_waiters or time.monotonic()<self.next_request:
                    self.gate.wait(.1)
                if time.time()<self.retry_at:raise SSIAPIError('rate_limited',429,self.retry_at-time.time())
                self.request_active=True
            finally:
                if not background:self.foreground_waiters-=1
        try:
            with self.lock:
                if self.client is None:self.client=self.factory(self.env_file)
                client=self.client
            return client._get('/api/v3/data/ohlc',params)
        except SSIAPIError as exc:
            if exc.code in ('rate_limited','market_access_denied','authentication_failed','missing_credentials') or exc.http_status in (401,403,429):
                with self.lock:self.retry_at=max(self.retry_at,time.time()+max(60,exc.retry_after or 60))
            raise
        finally:
            with self.gate:
                self.request_active=False;self.next_request=time.monotonic()+self.request_interval
                self.gate.notify_all()

    def _cached(self,key):
        if not self.database.exists():return None
        try:
            with sqlite3.connect(f'file:{self.database.as_posix()}?mode=ro',uri=True,timeout=3) as db:
                row=db.execute('SELECT payload,saved_at FROM chart_cache WHERE cache_key=?',(key,)).fetchone()
            if row:return json.loads(row[0]),row[1]
        except (sqlite3.Error,ValueError):pass
        return None

    def _store(self,key,data):
        self.database.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.database,timeout=5) as db:
            db.execute('CREATE TABLE IF NOT EXISTS chart_cache(cache_key TEXT PRIMARY KEY,payload TEXT NOT NULL,saved_at REAL NOT NULL)')
            db.execute('INSERT OR REPLACE INTO chart_cache VALUES(?,?,?)',(key,json.dumps(data,ensure_ascii=False,allow_nan=False),time.time()))
            db.execute('DELETE FROM chart_cache WHERE cache_key NOT IN (SELECT cache_key FROM chart_cache ORDER BY saved_at DESC LIMIT 128)')

    def _fetch(self,spec,*,persist=True,background=False):
        records=[];truncated=False
        for page in range(1,4):
            # The working SSI contract requires the full timestamp for both
            # daily and intraday queries, unlike the short-form API example.
            response=self._request({'symbol':spec['symbol'],
                'from':spec['start'].strftime('%Y/%m/%d %H:%M:%S'),
                # Include the completed closing-auction bucket. SSI filters
                # source rows before grouping, so 14:45:00 omits that bar.
                'to':spec['end'].replace(hour=23,minute=59,second=59).strftime('%Y/%m/%d %H:%M:%S'),
                'timeFrame':spec['timeframe'],'pageIndex':page,'pageSize':1000},background=background)
            rows=response if isinstance(response,list) else response.get('data')
            if isinstance(response,dict) and (response.get('code')==204 or 'data' in response and rows is None):rows=[]
            if not isinstance(rows,list):raise SSIAPIError('invalid_market_response')
            records.extend(rows)
            if len(rows)<1000:break
            if page==3:truncated=True
        bars,invalid=normalize_bars(records,spec)
        data={'source':'ssi_fastconnect_ohlc','symbol':spec['symbol'],'range':spec['range'],
                  'timeframe':spec['timeframe'],'price_unit':'VND','volume_unit':'shares',
                  'requested_from':spec['start'].isoformat(),'requested_to':spec['end'].isoformat(),
                  'updated_at':datetime.now(VN).isoformat(),'bars':bars,'invalid_records':invalid,
                  'complete_range':not truncated,'timestamp_basis':'exchange_bar_time',
                  'value_basis':'ssi_ohlc_value_not_verified_as_turnover'}
        if persist:
            self._store(spec['key'],data)
            self.archive.record(data,spec)
        return data

    def background_fetch(self,spec):
        cached=self.archive.read(spec)
        if cached is not None:return cached
        data=self._fetch(spec,persist=False,background=True)
        self.archive.record(data,spec)
        return data

    def _reference_context(self,data,spec):
        # Legacy filter caches predate reference_date. Rebind on read instead
        # of retaining a next-session reference or rewriting historical prices.
        return {**data,'bars':[{**b,'reference_price_vnd':reference_for_day(spec['quote'],b.get('trading_date'))}
            for b in data.get('bars',[])]}

    def _refresh(self,spec,event):
        try:self._fetch(spec,background=True)
        except SSIAPIError as exc:
            with self.lock:self.retry_at=time.time()+max(60,exc.retry_after or 60)
        except (OSError,sqlite3.Error,ValueError):pass
        finally:
            with self.lock:self.inflight.pop(spec['key'],None)
            event.set()

    def read(self,query,*,now=None):
        latest=self.latest_loader();clock=(now or datetime.now(VN)).astimezone(VN)
        spec=resolve_query(query,latest,clock)
        # On a catalog-only restart, a weekend is not a trading session. Use
        # an actual retained candle as the off-hours anchor, without changing
        # the source quote or overriding a user's explicit date range.
        anchor=None;symbol=spec['symbol'];quote=spec['quote']
        close=day_time(15) if quote.get('market_code') in ('HNX','UPCOM') else day_time(14,45)
        off_hours=clock.weekday()>=5 or clock.time()<day_time(9) or clock.time()>=close
        if spec['range']!='custom' and off_hours and not (
                event_time(quote.get('source_match_time_raw')) or event_time(quote.get('trading_date'))):
            anchor=self.archive.latest_time(symbol,clock)
        if anchor:spec=resolve_query(query,latest,clock,session_anchor=anchor)
        key=spec['key'];cached=self._cached(key)
        archived=self.archive.read(spec)
        if archived is not None:return archived
        ttl=30 if spec['end'].date()>=spec['now'].date() else 86400
        if cached:
            data,saved=cached;stale=time.time()-saved>=ttl
            if stale:
                with self.lock:
                    if key not in self.inflight and time.time()>=self.retry_at:
                        event=Event();self.inflight[key]=event
                        Thread(target=self._refresh,args=(spec,event),daemon=True,name='ssi-chart-history').start()
            return {**self._reference_context(data,spec),'cached':True,'refreshing':stale and key in self.inflight}
        with self.lock:
            event=self.inflight.get(key);owner=event is None
            if owner:event=Event();self.inflight[key]=event
        if not owner:
            event.wait(10);cached=self._cached(key)
            if not cached:raise SSIAPIError('source_unavailable')
            return {**self._reference_context(cached[0],spec),'cached':True,'refreshing':False}
        try:return {**self._fetch(spec),'cached':False,'refreshing':False}
        except SSIAPIError as exc:
            with self.lock:self.retry_at=time.time()+max(60,exc.retry_after or 60)
            partial=self.archive.read(spec,allow_partial=True)
            if partial is not None:return {**partial,'complete_range':False,'refreshing':False}
            raise
        finally:
            with self.lock:self.inflight.pop(key,None)
            event.set()


_service=None
_service_lock=RLock()
def history_service():
    global _service
    with _service_lock:
        if _service is None:_service=OHLCHistory()
    return _service


def read_price_history(query):
    return history_service().read(query)
