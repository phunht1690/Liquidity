"""SSI FastConnect v3, market data only. Tokens never leave the server."""
from __future__ import annotations
from src.data.sqlite_connection import sqlite_session
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from hashlib import sha256
from threading import Event,RLock,Thread
import csv,io,json,math,sqlite3,time
import requests,websocket
from dotenv import dotenv_values

VN=ZoneInfo('Asia/Ho_Chi_Minh')
PROJECT=Path(__file__).resolve().parents[2]
CACHE=PROJECT/'data/ssi/latest.json'
SOURCE='ssi_fastconnect'
MAX_BOOK_LEVELS=10
BASE_URL='https://api.ssi.com.vn'
AUTH_URL=BASE_URL+'/api/v3/auth/token'
STREAM_URL='wss://stream.ssi.com.vn/ws/v3'
ALLOWED_PATHS=frozenset(('/api/v3/data/securitiesByBoard','/api/v3/data/masterdata','/api/v3/data/indexSummary','/api/v3/data/ohlc','/api/v3/data/securitiesSummary'))

class SSIAPIError(RuntimeError):
    def __init__(self,code,http_status=None,retry_after=None):
        super().__init__(code);self.code=code;self.http_status=http_status;self.retry_after=retry_after

def numeric(value):
    if isinstance(value,bool) or value is None:return None
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (ValueError,TypeError):return None

def positive(value):
    value=numeric(value)
    return value if value is not None and value>0 else None

def event_time(value):
    if not isinstance(value,str):return None
    for fmt in ('%Y/%m/%d %H:%M:%S.%f','%Y/%m/%d %H:%M:%S','%Y/%m/%d','%Y-%m-%d'):
        try:return datetime.strptime(value,fmt).replace(tzinfo=VN)
        except ValueError:pass
    try:
        stamp=datetime.fromisoformat(value)
        return stamp.astimezone(VN) if stamp.tzinfo else None
    except ValueError:return None

def trading_day(value):
    stamp=event_time(value)
    return stamp.date().isoformat() if stamp else None

def reference_for_day(quote,day):
    reference_day=quote.get('reference_date') or quote.get('trading_date')
    return positive(quote.get('reference_price_vnd')) if reference_day==day else None

def rate_wait(response):
    headers=getattr(response,'headers',None) or getattr(response,'resp_headers',None) or {}
    retry=numeric(headers.get('Retry-After')) or 0
    reset=numeric(headers.get('X-RATELIMIT-RESET')) or 0
    if reset>1e12:reset/=1000
    return max(60,retry,reset-time.time())

def normalize_board(records,symbols,market_status=None,*,now=None,connected=True,generation=None,allowed_boards=('HOSE',),feed_healthy=None):
    """Whole quote arrays replace prior arrays, without inheriting missing levels."""
    now=now or datetime.now(VN);result=[];seen=set()
    for raw in records:
        symbol=raw.get('symbol')
        if symbol not in symbols or symbol in seen:continue
        seen.add(symbol);flags=[]
        def levels(side):
            original=raw.get(side) or []
            if not isinstance(original,list):original=[]
            values=[]
            for i in range(min(MAX_BOOK_LEVELS,len(original)) or 1):
                pair=original[i] if i<len(original) and isinstance(original[i],(list,tuple)) and len(original[i])>=2 else (None,None)
                if isinstance(pair[0],str) and pair[0].upper() in ('ATO','ATC'):flags.append('auction_observation')
                values.append({'price':positive(pair[0]),'volume':numeric(pair[1])})
            return values
        bids,asks=levels('bids'),levels('asks')
        if any(x['price'] is None or x['volume'] is None or x['volume']<0 for x in bids+asks):flags.append('incomplete_levels')
        if not flags:
            if bids and asks and bids[0]['price']>=asks[0]['price']:flags.append('crossed_or_locked_book')
            if bids[0]['volume']<=0 or asks[0]['volume']<=0:flags.append('empty_best_level')
            if any(a['price']<b['price'] for a,b in zip(bids,bids[1:])) or any(a['price']>b['price'] for a,b in zip(asks,asks[1:])):flags.append('unsorted_levels')
        # Empty arrays and explicit [0,0] padding are known absence of orders;
        # absent fields, malformed pairs and nonnumeric values remain unknown.
        def known_side(side):
            original=raw.get(side)
            if not isinstance(original,list):return False
            for pair in original[:MAX_BOOK_LEVELS]:
                if not isinstance(pair,(list,tuple)) or len(pair)!=2:return False
                p,v=numeric(pair[0]),numeric(pair[1])
                if p is None or v is None or p<0 or v<0 or p==0 and v>0:return False
            return True
        structure=known_side('bids') and known_side('asks')
        quote_stamp=event_time(raw.get('book_time'));trade_stamp=event_time(raw.get('trade_time'))
        age=(now-quote_stamp).total_seconds() if quote_stamp else None
        if age is None or age< -5 or age>60 and not feed_healthy:flags.append('stale_or_missing_book_event')
        if not connected:flags.append('stream_disconnected')
        if generation is not None and raw.get('book_generation')!=generation:flags.append('book_from_previous_connection')
        if raw.get('board') not in allowed_boards or raw.get('stockType')!='Stock':flags.append('unsupported_market_or_instrument')
        volume=numeric(raw.get('volume'));average=positive(raw.get('average'))
        proxy=average*volume if average and volume is not None and volume>=0 else None
        ref=positive(raw.get('refPrice'));last=positive(raw.get('price'));phase=raw.get('market_status') or market_status
        floor_price=positive(raw.get('floor'));ceiling=positive(raw.get('ceiling'));lot=positive(raw.get('lotSize'))
        active=[x for x in bids+asks if x['price'] and x['volume'] and x['volume']>0]
        from src.data.market_rules import tick
        units=bool(structure and floor_price and ceiling and lot and quote_stamp
            and raw.get('master_date')==quote_stamp.date().isoformat()
            and all(floor_price<=x['price']<=ceiling and x['volume']%lot==0 and x['price']%tick(x['price'],raw.get('board','HOSE'))==0 for x in active))
        stamp=max((t for t in (quote_stamp,trade_stamp) if t),default=None)
        reference_day=raw.get('master_date') or raw.get('reference_date') or (stamp.date().isoformat() if stamp else None)
        result.append({'symbol':symbol,'name':raw.get('symbolNameVi'),'group':raw.get('icbName'),'source':SOURCE,
            'trading_date':stamp.date().isoformat() if stamp else None,'last_price_vnd':last,'reference_price_vnd':ref,'reference_date':reference_day,
            'ceiling_price_vnd':positive(raw.get('ceiling')),'floor_price_vnd':positive(raw.get('floor')),
            'volume_shares':volume if volume is not None and volume>=0 else None,'avg_match_price_vnd':average,
            'change_percent':(last/ref-1)*100 if last and ref and trade_stamp and reference_day==trade_stamp.date().isoformat() else None,
            'cumulative_turnover_proxy_vnd':proxy,'turnover_basis':'avg_match_price_times_volume_proxy',
            'bids':bids,'asks':asks,'book_flags':list(dict.fromkeys(flags)),
            'book_levels_captured':max(len(bids),len(asks)),
            'book_structure_verified':structure,'units_verified':units,
            'freshness_basis':'healthy_current_subscription' if feed_healthy else 'book_event_time',
            'open_price_vnd':positive(raw.get('open')),'high_price_vnd':positive(raw.get('high')),'low_price_vnd':positive(raw.get('low')),
            'last_trade_quantity_shares':numeric(raw.get('trade_quantity')),
            'last_trade_side':raw.get('trade_side') if raw.get('trade_side') in ('B','S') else None,
            'source_book_time_raw':raw.get('book_time'),'source_match_time_raw':raw.get('trade_time'),
            'exchange_time':quote_stamp.isoformat() if quote_stamp else None,'book_event_age_seconds':age,
            'book_received_at':raw.get('book_received_at'),'trade_received_at':raw.get('trade_received_at'),
            'source_session_raw':phase,'provider_market_status':phase,'phase':'ssi_market_flag' if phase else 'receiver_clock_estimate',
            'lot_segment':'standard_quote_topic','lot_size':numeric(raw.get('lotSize')),
            'market_code':raw.get('board'),'stock_type':raw.get('stockType')})
    return sorted(result,key=lambda r:r['symbol'])

class SSISession:
    def __init__(self,env_file:Path,progress=None,http=None):
        self.env_file=Path(env_file);self._progress=progress or (lambda operation:None)
        self.http=http or requests.Session();self._lock=RLock();self._last_request=0
        self._token='';self._refresh='';self._expires=0;self._refresh_expires=0;self._values={}
        self._active_key=None;self._active_slot=None;self._credential_count=0;self._credential_switches=0
        self._credential_cooldowns={}
        self.authenticated=False;self.market_authorized=False;self.universe_group='VN100'
        self._rows={};self._groups={};self._cached_groups={};self._membership_provenance={};self._membership_day=None;self._master_day=None
        self._metadata_warnings=[];self._master_retry_at=0
        self.pilot_symbols_per_board=15;self._catalog_counts={};self._universe_labels={}
        self.raw_archive_max_mb=2048;self.raw_archive_retention_days=7;self._archive_status='recording'
        self._membership_retry_at=float('inf')
        self._last_transport_at=None;self._last_transport_monotonic=0
        self._stop=Event();self._ready=Event();self._thread=None;self._ws=None;self._generation=0;self._subscription_version=0
        self._stream_status='not_started';self._last_stream_at=None;self._last_stream_code=None
        self._event_count=0;self._duplicate_count=0;self._late_count=0;self._bad_count=0;self._buffers=[]
        self._archive_last_prune=0;self._archive_errors=0;self._ensure_token()
        try:
            cached=load_snapshot()
            self._cached_groups=(cached.get('membership') or {}).get('universes') or {}
            for row in cached.get('quotes',[]):
                self._rows[row['symbol']]={'symbol':row['symbol'],'price':row.get('last_price_vnd'),
                    'average':row.get('avg_match_price_vnd'),'volume':row.get('volume_shares'),
                    'bids':[[x.get('price'),x.get('volume')] for x in row.get('bids',[])],
                    'asks':[[x.get('price'),x.get('volume')] for x in row.get('asks',[])],
                    'book_time':row.get('source_book_time_raw'),'trade_time':row.get('source_match_time_raw'),
                    'book_received_at':row.get('book_received_at'),'trade_received_at':row.get('trade_received_at'),
                    'book_generation':-1,'board':row.get('market_code'),'stockType':row.get('stock_type'),
                    'symbolNameVi':row.get('name'),'icbName':row.get('group'),'lotSize':row.get('lot_size'),
                    'master_date':row.get('reference_date') or (trading_day(row.get('source_book_time_raw')) if row.get('units_verified') else row.get('trading_date')),
                    'refPrice':row.get('reference_price_vnd'),'ceiling':row.get('ceiling_price_vnd'),'floor':row.get('floor_price_vnd'),
                    'open':row.get('open_price_vnd'),'high':row.get('high_price_vnd'),'low':row.get('low_price_vnd'),
                    'trade_quantity':row.get('last_trade_quantity_shares'),'trade_side':row.get('last_trade_side')}
        except (OSError,ValueError,KeyError,TypeError):pass

    def _pace(self):
        delay=.25-(time.monotonic()-self._last_request)
        if delay>0:time.sleep(delay)
        self._last_request=time.monotonic()

    def _auth_request(self,path,body):
        self._pace()
        try:r=self.http.post(BASE_URL+path,json=body,timeout=(8,20),allow_redirects=False)
        except requests.RequestException:raise SSIAPIError('auth_unavailable') from None
        if r.status_code==429:raise SSIAPIError('rate_limited',429,rate_wait(r))
        if r.status_code!=200:raise SSIAPIError('authentication_failed',r.status_code)
        try:p=r.json();d=p.get('data',p)
        except (ValueError,AttributeError):raise SSIAPIError('invalid_auth_response') from None
        if not isinstance(d,dict) or not isinstance(d.get('accessToken'),str) or not d['accessToken']:raise SSIAPIError('invalid_auth_response')
        expires=numeric(d.get('expiresAt'))
        if not expires or expires<=time.time():raise SSIAPIError('invalid_auth_response')
        self._token=d['accessToken'];self._expires=expires
        self._refresh=d.get('refreshToken') or '';self._refresh_expires=numeric(d.get('refreshExpiresAt')) or 0
        self.authenticated=True

    def _credential_pairs(self):
        self._values=dotenv_values(self.env_file);pairs=[];seen=set()
        for slot,suffix in ((1,''),(2,'_2')):
            key=self._values.get('SSI_API_KEY'+suffix);secret=self._values.get('SSI_API_SECRET'+suffix)
            if key and secret and key not in seen:pairs.append((slot,key,secret));seen.add(key)
        self._credential_count=len(pairs)
        return pairs

    def _login(self,*,exclude_active=False):
        pairs=self._credential_pairs()
        if not pairs:raise SSIAPIError('missing_credentials')
        if not exclude_active:pairs.sort(key=lambda p:p[1]!=self._active_key)
        last=None
        for slot,key,secret in pairs:
            if exclude_active and key==self._active_key:continue
            if self._credential_cooldowns.get(key,0)>time.time():continue
            self._progress('auth')
            try:self._auth_request('/api/v3/auth/token',{'apiKey':key,'apiSecret':secret})
            except SSIAPIError as exc:
                if exc.code not in ('authentication_failed','invalid_auth_response'):raise
                self._credential_cooldowns[key]=time.time()+300;last=exc;continue
            if self._active_key is not None and key!=self._active_key:self._credential_switches+=1
            self._active_key=key;self._active_slot=slot
            return
        self.authenticated=False
        waits=[max(0,t-time.time()) for t in self._credential_cooldowns.values() if t>time.time()]
        raise SSIAPIError('authentication_failed',getattr(last,'http_status',None),min(waits) if waits else 300)

    def _failover_credentials(self):
        """Switch complete independent pairs on access failure; never on empty data or 429."""
        with self._lock:
            pairs=self._credential_pairs()
            if not any(key!=self._active_key and self._credential_cooldowns.get(key,0)<=time.time() for _,key,_ in pairs):return False
            if self._active_key:self._credential_cooldowns[self._active_key]=time.time()+300
            self._token='';self._refresh='';self._expires=0;self._refresh_expires=0
            self.authenticated=False;self.market_authorized=False;self._generation+=1
            self._stream_status='connecting'
            if self._ws:
                try:self._ws.close()
                except Exception:pass
            self._login(exclude_active=True)
            return True

    def _ensure_token(self):
        with self._lock:
            if self._token and self._expires>time.time()+60:return
            if self._refresh and self._refresh_expires>time.time()+60:
                try:self._auth_request('/api/v3/auth/refresh',{'refreshToken':self._refresh});return
                except SSIAPIError as exc:
                    if exc.code not in ('authentication_failed','invalid_auth_response'):raise
                    self._token='';self._refresh=''
            self._login()

    def public_auth(self):
        with self._lock:
            return {'authenticated':self.authenticated,'market_authorized':self.market_authorized,
                'token_expires_at':datetime.fromtimestamp(self._expires,VN).isoformat() if self._expires else None,
                'transport':'websocket','websocket_status':self._stream_status,'last_stream_at':self._last_stream_at,
                'last_stream_code':self._last_stream_code,'received_events':self._event_count,
                'duplicate_events':self._duplicate_count,'late_events':self._late_count,'invalid_events':self._bad_count,
                'raw_archive_errors':self._archive_errors,'metadata_warnings':list(self._metadata_warnings),
                'last_transport_at':self._last_transport_at,'catalog_counts':dict(self._catalog_counts),
                'raw_archive_status':self._archive_status,'raw_archive_budget_mb':self.raw_archive_max_mb,
                'raw_archive_retention_days':self.raw_archive_retention_days,
                'credential_profiles':self._credential_count,'active_credential_slot':self._active_slot,
                'credential_switches':self._credential_switches}

    def _get(self,path,params):
        if path not in ALLOWED_PATHS:raise SSIAPIError('endpoint_not_allowed')
        with self._lock:
            for attempt in range(2):
                self._ensure_token();self._pace()
                try:r=self.http.get(BASE_URL+path,params=params,headers={'Authorization':'Bearer '+self._token},timeout=(8,20),allow_redirects=False)
                except requests.RequestException:raise SSIAPIError('source_unavailable') from None
                if r.status_code not in (401,403):break
                self.market_authorized=False
                if attempt==0 and self._failover_credentials():continue
                raise SSIAPIError('market_access_denied',r.status_code)
            if r.status_code==429:raise SSIAPIError('rate_limited',429,rate_wait(r))
            if r.status_code==204 and path=='/api/v3/data/ohlc':return {'data':[]}
            if r.status_code!=200:raise SSIAPIError('source_unavailable',r.status_code)
            try:p=r.json()
            except ValueError:raise SSIAPIError('invalid_market_response') from None
            if not isinstance(p,(list,dict)):raise SSIAPIError('invalid_market_response')
            if isinstance(p,dict) and p.get('code',200) not in (200,204):raise SSIAPIError('market_rejected')
            self.market_authorized=True;return p

    def _membership(self):
        today=datetime.now(VN).date().isoformat()
        if self._membership_day==today and time.monotonic()<self._membership_retry_at:return
        self._progress('membership');groups={};metadata={};provenance={};warnings=[]
        for group in ('VN30','VN100') if self.universe_group in ('VN100','HOSE','ALL') else ('VN30',):
            try:
                data=self._get('/api/v3/data/securitiesByBoard',{'index':group})
                rows=data if isinstance(data,list) else data.get('data')
            except SSIAPIError as exc:
                if exc.code in ('market_access_denied','authentication_failed','missing_credentials','rate_limited'):raise
                rows=[]
            if not isinstance(rows,list):rows=[]
            symbols=sorted({r.get('symbol') for r in rows if isinstance(r,dict) and isinstance(r.get('symbol'),str) and r.get('board')=='HOSE' and r.get('stockType')=='Stock'})
            expected=30 if group=='VN30' else 100
            if len(symbols)==expected:
                groups[group]=symbols;provenance[group]='ssi_api'
                for row in rows:
                    if row.get('symbol') in symbols:metadata[row['symbol']]=row
            else:
                cached=self._cached_groups.get(group,[])
                if isinstance(cached,list) and len(set(cached))==expected and all(s in self._rows for s in cached):
                    groups[group]=sorted(set(cached));provenance[group]='saved_ssi_membership'
                    for symbol in cached:metadata.setdefault(symbol,dict(self._rows[symbol]))
                    warnings.append(group+': đang dùng danh sách SSI đã lưu; chờ nguồn xác nhận lại.')
                else:warnings.append(group+': chưa nhận được danh sách thành phần hợp lệ.')
        if not groups and self.universe_group not in ('HOSE','ALL'):raise SSIAPIError('unexpected_membership_count')
        if 'VN100' in groups and 'VN30' in groups and not set(groups['VN30'])<=set(groups['VN100']):
            groups.pop('VN30');provenance.pop('VN30',None);warnings.append('VN30 chưa khớp danh sách VN100; tạm chỉ hiển thị VN100.')
        if self.universe_group in ('HOSE','ALL'):
            pilots={'HNX':['SHS','PVS','PVI','IDC','CEO','HUT','MBS','NVB','TNG','NTP','DTD','PLC','VC3','L14','LAS'],
                    'UPCOM':['ACV','VEA','ABB','BVB','DDV','QNS','MSR','PHP','FOX','VGI','OIL','SGP','TVN','VGT','BSR']}
            for board in ('HOSE','HNX','UPCOM'):
                try:
                    payload=self._get('/api/v3/data/securitiesByBoard',{'board':board})
                    rows=payload if isinstance(payload,list) else payload.get('data',[])
                    rows=[r for r in rows if isinstance(r,dict) and r.get('board')==board and r.get('stockType')=='Stock'
                          and isinstance(r.get('symbol'),str) and 2<=len(r['symbol'])<=6 and r['symbol'].isascii() and r['symbol'].isalnum() and r['symbol']==r['symbol'].upper()
                          and (not r.get('firstTradingDate') or (trading_day(r['firstTradingDate']) or today)<=today)
                          and (not r.get('lastTradingDate') or (trading_day(r['lastTradingDate']) or today)>=today)]
                    all_symbols=sorted({r['symbol'] for r in rows});self._catalog_counts[board]=len(all_symbols)
                    if board=='HOSE' or self.universe_group=='ALL':chosen=all_symbols;key=board
                    else:
                        chosen=[s for s in pilots[board] if s in all_symbols]
                        chosen=(chosen+[s for s in all_symbols if s not in chosen])[:self.pilot_symbols_per_board];key=board+'_PILOT'
                    if not chosen:raise SSIAPIError('empty_market_catalog')
                    groups[key]=chosen;provenance[key]='ssi_catalog_pilot' if key.endswith('_PILOT') else 'ssi_board_catalog'
                    self._universe_labels[key]=board+' · thử nghiệm' if key.endswith('_PILOT') else board
                    for row in rows:
                        if row['symbol'] in chosen:metadata[row['symbol']]=row
                except SSIAPIError as exc:
                    if exc.code in ('rate_limited','authentication_failed','missing_credentials'):raise
                    warnings.append(board+': đang chờ xác nhận danh mục từ SSI.')
                    cached_key=board if board in self._cached_groups else board+'_PILOT'
                    cached=self._cached_groups.get(cached_key) or []
                    if cached and all(s in self._rows and self._rows[s].get('board')==board and self._rows[s].get('stockType')=='Stock' for s in cached):
                        groups[cached_key]=sorted(set(cached));provenance[cached_key]='saved_ssi_board_catalog'
                        self._universe_labels[cached_key]=board+' · thử nghiệm' if cached_key.endswith('_PILOT') else board
                        for s in cached:metadata[s]=dict(self._rows[s])
        with self._lock:
            if not groups:raise SSIAPIError('unexpected_membership_count')
            selected=set().union(*(set(v) for v in groups.values()))
            if selected!=set(self._rows):self._subscription_version=getattr(self,'_subscription_version',0)+1
            self._groups=groups;self._rows={s:{**self._rows.get(s,{}),**metadata.get(s,{})} for s in selected};self._membership_day=today
            self._cached_groups=groups;self._membership_provenance=provenance;self._metadata_warnings=warnings
            self._membership_retry_at=time.monotonic()+300 if warnings else float('inf')

    def _master(self):
        today=datetime.now(VN).strftime('%Y/%m/%d')
        if self._master_day==today:return
        for page in range(1,21):
            data=self._get('/api/v3/data/masterdata',{'from':today,'to':today,'pageIndex':page,'pageSize':1000})
            if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise SSIAPIError('invalid_market_response')
            with self._lock:
                for row in data['data']:
                    if row.get('symbol') in self._rows and row.get('board')==self._rows[row['symbol']].get('board'):
                        self._rows[row['symbol']].update({k:row.get(k) for k in ('refPrice','ceiling','floor')})
                        self._rows[row['symbol']]['master_date']=datetime.now(VN).date().isoformat()
            pages=numeric(data.get('pagesCount',1))
            if pages is None or pages<0:raise SSIAPIError('invalid_market_response')
            if page>=pages:self._master_day=today;return
        raise SSIAPIError('pagination_limit')

    def _accept_frame(self,frame):
        if not isinstance(frame,dict) or frame.get('channel')!='DATA':return False
        topic=frame.get('topic','');data=frame.get('data')
        if not isinstance(topic,str) or not isinstance(data,dict):return False
        now=datetime.now(VN);kind,_,symbol=topic.partition('.')
        with self._lock:
            if topic=='market.flag':
                board=data.get('b');flag=data.get('f')
                stamp=event_time(data.get('t'))
                if board not in ('HOSE','HNX','UPCOM') or not isinstance(flag,str) or not stamp:return False
                for row in self._rows.values():
                    if row.get('board')==board:row.update(market_status=flag,market_status_date=stamp.date().isoformat())
            elif kind in ('quote','trade') and symbol in self._rows and data.get('s')==symbol:
                row=self._rows[symbol];stamp=event_time(data.get('t'))
                if stamp is None:self._bad_count+=1;return False
                old=event_time(row.get('book_time' if kind=='quote' else 'trade_time'))
                if old and stamp<old:self._late_count+=1;return False
                fingerprint=json.dumps(data,sort_keys=True,separators=(',',':'))
                if row.get('_'+kind+'_fingerprint')==fingerprint:self._duplicate_count+=1;return False
                row['_'+kind+'_fingerprint']=fingerprint
                if kind=='quote':row.update(bids=data.get('bids'),asks=data.get('asks'),book_time=data['t'],book_received_at=now.isoformat(),book_generation=self._generation)
                else:row.update(price=data.get('p'),average=data.get('a'),volume=data.get('v'),trade_time=data['t'],trade_received_at=now.isoformat(),
                    trade_quantity=data.get('q'),trade_side=data.get('si'),open=data.get('o'),high=data.get('h'),low=data.get('l'))
            else:return False
            self._event_count+=1;self._last_stream_at=now.isoformat()
            self._buffers.append((now.date().isoformat(),now.isoformat(),json.dumps(frame,ensure_ascii=False,separators=(',',':'))))
            self._ready.set();return True

    def _flush_events(self):
        with self._lock:batch,self._buffers=self._buffers,[]
        prune_due=not self._archive_last_prune or time.monotonic()-self._archive_last_prune>30
        if not batch and not prune_due:return
        try:
            path=CACHE.with_name('events.sqlite3')
            if not batch and not path.is_file():return
            path.parent.mkdir(parents=True,exist_ok=True)
            with sqlite_session(path,timeout=2) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,day TEXT NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS events_day_seq ON events(day,seq)')
                db.execute("CREATE INDEX IF NOT EXISTS events_symbol_seq ON events(json_extract(payload,'$.data.s'),seq)")
                anchor=max(r[0] for r in batch) if batch else datetime.now(VN).date().isoformat()
                if prune_due:
                    days=max(1,int(self.raw_archive_retention_days))
                    cutoff=(datetime.fromisoformat(anchor).date()-timedelta(days=days-1)).isoformat()
                    db.execute('DELETE FROM events WHERE day<?',(cutoff,))
                    self._archive_last_prune=time.monotonic()
                # Bound disk use by actual bytes, not an arbitrary number of
                # messages. Never delete today's first trades to keep appending.
                page_size=db.execute('PRAGMA page_size').fetchone()[0]
                def used_mb():return (db.execute('PRAGMA page_count').fetchone()[0]-db.execute('PRAGMA freelist_count').fetchone()[0])*page_size/1024**2
                incoming=sum(len(r[2].encode('utf8')) for r in batch)/1024**2
                while used_mb()+incoming>self.raw_archive_max_mb:
                    oldest=db.execute('SELECT MIN(day) FROM events').fetchone()[0]
                    if not oldest or oldest>=anchor:
                        self._archive_status='paused_capacity';return
                    db.execute('DELETE FROM events WHERE day=?',(oldest,))
                self._archive_status='recording'
                db.executemany('INSERT INTO events(day,received_at,payload) VALUES(?,?,?)',batch)
        except (OSError,sqlite3.Error):self._archive_errors+=1

    def _stream_loop(self):
        failures=0
        while not self._stop.is_set():
            ws=None;retry_delay=0
            try:
                self._ensure_token()
                with self._lock:
                    token=self._token;expiry=self._expires;self._stream_status='connecting';self._generation+=1;symbols=sorted(self._rows)
                    membership_day=self._membership_day;subscription_version=self._subscription_version
                    for row in self._rows.values():row.pop('market_status',None)
                ws=websocket.create_connection(STREAM_URL,header={'Authorization':'Bearer '+token},timeout=8)
                ws.settimeout(1);self._ws=ws
                topics=[f'{kind}.{s}' for kind in ('quote','trade') for s in symbols]+['market.flag']
                for start in range(0,len(topics),100):ws.send(json.dumps({'method':'subscribe','channel':'DATA','topics':topics[start:start+100]}))
                self._stream_status='connected';self._last_stream_code=None;last_ping=time.monotonic();last_flush=last_ping;failures=0
                self._last_transport_monotonic=last_ping;self._last_transport_at=datetime.now(VN).isoformat()
                while not self._stop.is_set():
                    if time.time()>=expiry-60 or membership_day!=self._membership_day or subscription_version!=self._subscription_version or token!=self._token:break
                    try:
                        message=ws.recv()
                        if not message:raise ConnectionError('stream_closed')
                        frame=json.loads(message)
                        self._last_transport_monotonic=time.monotonic();self._last_transport_at=datetime.now(VN).isoformat()
                        if isinstance(frame,dict) and frame.get('channel')=='HEARTBEAT':
                            if str(frame.get('method','')).upper()=='PING':
                                ws.send(json.dumps({'method':'PONG','channel':'HEARTBEAT','time':frame.get('time')}))
                            continue
                        if isinstance(frame,dict) and isinstance(frame.get('code'),int) and frame['code']>=400:
                            code=frame['code'];self._last_stream_code=code
                            raise SSIAPIError('rate_limited' if code==429 else 'stream_access_denied' if code in (401,403) else 'stream_rejected',code)
                        self._accept_frame(frame)
                    except websocket.WebSocketTimeoutException:pass
                    except (ValueError,TypeError):self._bad_count+=1
                    now=time.monotonic()
                    if now-last_ping>=25:ws.send(json.dumps({'method':'ping_pong','channel':'HEARTBEAT','topics':[]}));last_ping=now
                    if now-self._last_transport_monotonic>90:raise ConnectionError('heartbeat_timeout')
                    if now-last_flush>=1:self._flush_events();last_flush=now
            except Exception as exc:
                status=getattr(exc,'http_status',None) or getattr(exc,'status_code',None)
                denied=getattr(exc,'code',None)=='stream_access_denied' or status in (401,403)
                self._stream_status='access_denied' if denied else 'disconnected';failures+=1
                if status==429 or getattr(exc,'code',None)=='rate_limited':retry_delay=max(rate_wait(exc),getattr(exc,'retry_after',None) or 0)
                elif denied:
                    try:self._failover_credentials()
                    except SSIAPIError as failed:
                        retry_delay=max(60,failed.retry_after or 0)
            finally:
                if ws:
                    try:ws.close()
                    except Exception:pass
                self._ws=None;self._flush_events()
            self._stop.wait(max(retry_delay,min(60,2**min(failures,6))))
        self._stream_status='stopped'

    def poll(self,now=None):
        started=datetime.now(VN).isoformat();self._membership()
        if time.monotonic()>=self._master_retry_at:
            try:self._master()
            except SSIAPIError as exc:
                if exc.code in ('authentication_failed','missing_credentials'):raise
                self._master_retry_at=time.monotonic()+300
                self._metadata_warnings=[s for s in self._metadata_warnings if not s.startswith('Giá tham chiếu:')]+['Giá tham chiếu: đang giữ bản SSI đã lưu; chờ cập nhật.']
        if not self._thread or not self._thread.is_alive():
            self._thread=Thread(target=self._stream_loop,name='ssi-market-stream',daemon=True);self._thread.start();self._ready.wait(8)
        captured=datetime.now(VN)
        with self._lock:
            scope='ALL' if self.universe_group=='ALL' else 'HOSE' if 'HOSE' in self._groups else 'VN100' if 'VN100' in self._groups else 'VN30'
            symbols=sorted({s for values in self._groups.values() for s in values})
            healthy=self._stream_status=='connected' and time.monotonic()-self._last_transport_monotonic<90
            quotes=normalize_board(list(self._rows.values()),symbols,now=captured,connected=self._stream_status=='connected',generation=self._generation,
                allowed_boards=('HOSE','HNX','UPCOM'),feed_healthy=healthy)
            groups={k:list(v) for k,v in self._groups.items()};auth=self.public_auth()
        for row in quotes:row.update(received_at=captured.isoformat(),timestamp_basis='local_receipt_time')
        result={'schema_version':2,'source':SOURCE,'collection_mode':'auto_collector','collection_kind':'auto_collector',
            'transport':'websocket','request_started_at':started,'captured_at':captured.isoformat(),'completed_at':captured.isoformat(),
            'timestamp_basis':'local_receipt_time','auth':auth,'quotes':quotes,
            'membership':{'source':'SSI FastConnect v3','group':scope,'symbols':symbols,'universes':groups,'status':'provider_index_list','effective_date':None,'provenance':dict(self._membership_provenance),'warnings':list(self._metadata_warnings),
                'catalog_counts':dict(self._catalog_counts),'labels':dict(self._universe_labels),'pilot_boards':['HNX','UPCOM'] if self.universe_group=='HOSE' else []},
            'missing_symbols':[r['symbol'] for r in quotes if not r.get('source_book_time_raw')],
            'limitations':['Dùng các mức chờ SSI cấp, tối đa 10 mỗi phía; lượng chờ có thể đổi hoặc bị hủy.',
                'Thiếu cờ phiên SSI thì pha được ước tính theo giờ Việt Nam; ngày nghỉ/tạm ngừng chưa có lịch riêng.',
                f'Kho bản tin giữ tối đa {self.raw_archive_retention_days} ngày lịch và ngân sách dung lượng. Khi đạt dung lượng trong ngày thì dừng ghi bản tin; luồng giá và ảnh thay đổi vẫn tiếp tục.',
                'Các phép tính theo quy tắc riêng của từng sàn, cần xác nhận giá trần/sàn và lô cùng ngày.']}
        result['dataset_id']='ssi-'+sha256(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()[:16]
        return result

    def close(self):
        self._stop.set()
        if self._ws:
            try:self._ws.close()
            except Exception:pass
        if self._thread:self._thread.join(timeout=4)
        self.http.close()

def load_snapshot(path=None):
    payload=json.loads(Path(path or CACHE).read_text(encoding='utf-8'))
    if payload.get('schema_version')!=2 or payload.get('source')!=SOURCE:raise ValueError('unsupported_snapshot')
    return payload

def export_board(payload):
    stream=io.StringIO(newline='');fields=['source','dataset_id','received_at','symbol','trading_date','last_price_vnd','volume_shares','cumulative_turnover_proxy_vnd','turnover_basis','source_book_time_raw','source_match_time_raw','provider_market_status']
    writer=csv.DictWriter(stream,fields,extrasaction='ignore');writer.writeheader()
    for row in payload['quotes']:writer.writerow({**row,'source':SOURCE,'dataset_id':payload['dataset_id']})
    return stream.getvalue().encode('utf-8-sig')
