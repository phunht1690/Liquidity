"""Low-priority, resumable price backfill independent of browser requests."""
from datetime import datetime, timedelta, time as day_time
from threading import Event, RLock, Thread
import sqlite3
import time

from src.data.ssi_feed import VN, SSIAPIError, event_time, load_snapshot
from src.data.ohlc_history import history_service


class HistoryBackfill:
    def __init__(self, *, history=None, latest_loader=None, retention_days=30, initial_delay=10):
        self.history = history or history_service()
        self.latest_loader = latest_loader or load_snapshot
        self.retention_days = max(1,min(35,int(retention_days)))
        self.history.archive.retention_days = self.retention_days
        self.initial_delay = initial_delay
        self.stop_event = Event()
        self.lock = RLock()
        self.thread = None
        self.focus = 'FPT'
        self.failures = {}
        self.checked = set()
        self.last_prune_day = None
        self.state = {'status':'starting','checked_symbols':0,'total_symbols':0,'pending':0,
            'timeframes':['5m','1d'],'retention_days':self.retention_days,'last_updated':None}

    def promote(self, symbol):
        with self.lock:self.focus = symbol

    def _plan(self, latest, now):
        if self.last_prune_day!=now.date():
            self.history.archive.prune(now)
            self.last_prune_day=now.date()
        quotes = {q['symbol']:q for q in latest.get('quotes',[]) if isinstance(q.get('symbol'),str)}
        if not quotes:return []
        dates = [stamp.date() for q in quotes.values()
            if (stamp:=event_time(q.get('source_match_time_raw')) or event_time(q.get('trading_date'))) and stamp<=now]
        # A newly added board can have its catalog before its first WebSocket
        # trade, especially when the app starts on a weekend. Request genuine
        # OHLC through the latest weekday in that case; only provider bars become history.
        # A calendar query endpoint is not evidence that a session took place.
        end = max(dates) if dates else now.date()
        if not dates:
            while end.weekday()>=5:end-=timedelta(days=1)
        start = now.date()-timedelta(days=self.retention_days-1)
        # A stale cache older than the retention window cannot invent a session.
        if end<start:return []
        first = set((latest.get('membership',{}).get('universes') or {}).get('VN30') or [])
        pending=[];checked=set()
        for symbol in sorted(quotes,key=lambda s:(s!=self.focus,s not in first,s)):
            done=True
            for tf in ('5m','1d'):
                missing = self.history.archive.missing_ranges(symbol,tf,start,end,now)
                if missing:done=False
                for a,b in missing:
                    if self.failures.get((symbol,tf),0)>time.time():continue
                    pending.append({'key':f'backfill-{symbol}-{tf}-{a}-{b}','symbol':symbol,'range':'custom',
                        'timeframe':tf,'start':datetime.combine(a,day_time(),VN),
                        'end':datetime.combine(b,day_time(23,59,59),VN),'now':now,'quote':quotes[symbol]})
            if done:checked.add(symbol)
        with self.lock:
            self.checked=checked
            self.state.update(total_symbols=len(quotes),checked_symbols=len(checked),pending=len(pending),
                requested_from=start.isoformat(),requested_to=end.isoformat())
        return pending

    def step(self, spec, now=None):
        spec={**spec,'now':now or datetime.now(VN)}
        with self.lock:self.state.update(status='filling',current_symbol=spec['symbol'])
        try:
            result=self.history.background_fetch(spec)
            complete=result.get('complete_range') is True and not result.get('invalid_records')
            if not complete:
                self.failures[(spec['symbol'],spec['timeframe'])]=time.time()+900
            with self.lock:self.state.update(last_updated=datetime.now(VN).isoformat())
            if complete and self.state.get('requested_from'):
                start=datetime.fromisoformat(self.state['requested_from']).date()
                end=datetime.fromisoformat(self.state['requested_to']).date()
                if not any(self.history.archive.missing_ranges(spec['symbol'],tf,start,end,spec['now']) for tf in ('5m','1d')):
                    with self.lock:
                        self.checked.add(spec['symbol']);self.state['checked_symbols']=len(self.checked)
            return complete
        except SSIAPIError as exc:
            global_error=exc.code in ('rate_limited','market_access_denied','authentication_failed','missing_credentials') or exc.http_status in (401,403,429) or exc.http_status is None and exc.code=='source_unavailable'
            if global_error:
                with self.history.lock:self.history.retry_at=max(self.history.retry_at,time.time()+max(60,exc.retry_after or 60))
                with self.lock:self.state.update(status='backoff')
            else:self.failures[(spec['symbol'],spec['timeframe'])]=time.time()+900
            return False
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
            self.failures[(spec['symbol'],spec['timeframe'])]=time.time()+60
            return False

    def _run(self):
        if self.stop_event.wait(self.initial_delay):return
        while not self.stop_event.is_set():
            try:latest=self.latest_loader()
            except (OSError,ValueError,TypeError,KeyError):latest={}
            try:
                pending=self._plan(latest,datetime.now(VN))
            except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):pending=[]
            if not pending:
                with self.lock:
                    status='ready' if self.state['total_symbols'] and self.state['checked_symbols']==self.state['total_symbols'] else 'retrying' if self.state['total_symbols'] else 'waiting'
                    self.state.update(status=status,current_symbol=None,pending=0)
                self.stop_event.wait(30);continue
            while pending and not self.stop_event.is_set():
                delay=max(0,self.history.retry_at-time.time())
                if delay:
                    with self.lock:self.state['status']='backoff'
                    if self.stop_event.wait(min(delay,30)):break
                    if time.time()<self.history.retry_at:continue
                # A new selection is promoted between API calls, never interrupts
                # the live WebSocket or starts one client per ticker.
                with self.lock:focus=self.focus
                index=next((i for i,s in enumerate(pending) if s['symbol']==focus),0)
                spec=pending.pop(index)
                self.step(spec)
                with self.lock:self.state['pending']=len(pending)
                if self.stop_event.wait(.2):break
            # Re-plan from durable coverage after every pass; crashes/restarts
            # resume missing days and don't download already-held sessions.
            self.stop_event.wait(2)

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self.stop_event.clear()
            self.thread=Thread(target=self._run,daemon=True,name='ssi-price-backfill')
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
        with self.lock:self.state['status']='stopped'

    def status(self):
        with self.lock:state=dict(self.state)
        return {**state,'running':bool(self.thread and self.thread.is_alive() and not self.stop_event.is_set()),
            'retry_after':max(0,round(self.history.retry_at-time.time())),
            'archive':self.history.archive.inventory()}


_service=None
_lock=RLock()


def start_backfill(config=None, *, env_file=None):
    global _service
    settings=(config or {}).get('ssi',{})
    if settings.get('auto_price_backfill',True) is False:return
    with _lock:
        if _service is None:
            history=history_service()
            if env_file:history.env_file=env_file
            history.request_interval=max(.5,min(5,float(settings.get('history_request_interval_seconds',1))))
            _service=HistoryBackfill(history=history,retention_days=settings.get('price_history_retention_days',30))
        _service.start()


def stop_backfill():
    if _service:_service.stop()


def backfill_status():
    if _service:return _service.status()
    return {'status':'stopped','running':False,'retention_days':30,'timeframes':['5m','1d'],
        'archive':{'bars':0,'symbols':0,'first_day':None,'last_day':None,'bytes':0,'retention_days':30}}


def prioritize_history(symbol):
    if _service:_service.promote(symbol)
