"""Bounded, asynchronous SSI daily statistics; never delays a quote response."""
from src.data.sqlite_connection import sqlite_session
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from queue import PriorityQueue,Empty
from threading import RLock,Event,Thread
import json,sqlite3,time
from src.data.ssi_feed import PROJECT,SSISession,SSIAPIError,VN,event_time,positive,numeric
from src.data.market_rules import session_finished


def normalize(records,symbol,now):
    valid=[]
    for raw in records:
        if not isinstance(raw,dict) or raw.get('symbol')!=symbol:continue
        stamp=event_time(raw.get('tradingDate'));close=positive(raw.get('close'))
        volume=numeric(raw.get('totalMatch'));value=numeric(raw.get('totalMatchValue'))
        if not stamp or stamp.date()>now.date() or not close or volume is None or volume<0:continue
        counts={}
        for field,key in [('foreign_buy_shares','totalForeignBuy'),('foreign_sell_shares','totalForeignSell'),('foreign_room_remaining_shares','remainForeignRoom'),('foreign_room_total_shares','totalForeignRoom')]:
            number=numeric(raw.get(key));counts[field]=number if number is not None and number>=0 else None
        valid.append({'schema_version':2,'symbol':symbol,'day':stamp.date().isoformat(),'close':close,'volume_shares':volume,
            'turnover_vnd':value if value is not None and value>=0 else None,
            'open_price_vnd':positive(raw.get('open')),'high_price_vnd':positive(raw.get('high')),'low_price_vnd':positive(raw.get('low')),
            'change_percent':numeric(raw.get('priceChangePercentage')),'average_price_vnd':positive(raw.get('average')),
            'foreign_buy_value_raw':numeric(raw.get('totalForeignBuyValue')),'foreign_sell_value_raw':numeric(raw.get('totalForeignSellValue')),
            'foreign_value_unit':'provider_unverified',**counts,
            'received_at':now.isoformat(),'source':'ssi_securities_summary'})
    return max(valid,key=lambda r:r['day']) if valid else None


class DailySummaries:
    def __init__(self,database=None,env_file=None,factory=SSISession):
        self.database=Path(database or PROJECT/'data/ssi/daily_summary.sqlite3');self.env_file=Path(env_file or PROJECT/'.env')
        self.factory=factory;self.client=None;self.lock=RLock();self.stop=Event();self.queue=PriorityQueue()
        self.pending=set();self.promoted=set();self.cache={};self.retry_at=0;self.serial=0;self.thread=None
        if self.database.is_file():
            try:
                with sqlite_session(f'file:{self.database.as_posix()}?mode=ro',uri=True) as db:
                    self.cache={s:json.loads(p) for s,p in db.execute('SELECT symbol,payload FROM summaries')}
            except (sqlite3.Error,OSError,ValueError):pass

    def request(self,symbol,priority=10):
        with self.lock:
            cached=self.cache.get(symbol);stamp=event_time((cached or {}).get('received_at'))
            now=datetime.now(VN);ttl=180 if now.weekday()<5 and 9<=now.hour<15 else 10800
            current_schema=(cached or {}).get('schema_version',0)>=2
            if current_schema and cached.get('day') and cached['day']<now.date().isoformat() and stamp and stamp.date()==now.date() and now.hour<15:return
            if current_schema and stamp and (now-stamp).total_seconds()<ttl:return
            if symbol in self.pending:
                if priority==0 and symbol not in self.promoted:
                    self.serial+=1;self.queue.put((0,self.serial,symbol));self.promoted.add(symbol)
                return
            if time.time()<self.retry_at:return
            self.serial+=1;self.pending.add(symbol);self.queue.put((priority,self.serial,symbol))
            if not self.thread or not self.thread.is_alive():
                self.thread=Thread(target=self._run,daemon=True,name='ssi-daily-statistics');self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:_,_,symbol=self.queue.get(timeout=2)
            except Empty:continue
            with self.lock:
                if symbol not in self.pending:self.queue.task_done();continue
            wait=max(0,self.retry_at-time.time())
            if self.stop.wait(wait):break
            try:
                if self.client is None:self.client=self.factory(self.env_file)
                now=datetime.now(VN)
                response=self.client._get('/api/v3/data/securitiesSummary',{'symbol':symbol,
                    'from':(now-timedelta(days=10)).strftime('%Y/%m/%d'),'to':now.strftime('%Y/%m/%d'),'pageIndex':1,'pageSize':20})
                rows=response if isinstance(response,list) else response.get('data',[])
                result=normalize(rows,symbol,now)
                if result:
                    self.database.parent.mkdir(parents=True,exist_ok=True)
                    with sqlite_session(self.database,timeout=4) as db:
                        db.execute('CREATE TABLE IF NOT EXISTS summaries(symbol TEXT PRIMARY KEY,payload TEXT NOT NULL)')
                        db.execute('INSERT OR REPLACE INTO summaries VALUES(?,?)',(symbol,json.dumps(result,ensure_ascii=False,allow_nan=False)))
                    with self.lock:self.cache[symbol]=result
                else:
                    # An empty response gets a short quiet cooldown too.
                    with self.lock:self.cache[symbol]={'schema_version':2,'symbol':symbol,'received_at':now.isoformat()}
            except SSIAPIError as exc:
                with self.lock:self.retry_at=time.time()+max(60,exc.retry_after or 60)
            except (OSError,ValueError,sqlite3.Error):
                with self.lock:self.retry_at=time.time()+60
            finally:
                with self.lock:self.pending.discard(symbol);self.promoted.discard(symbol)
                self.queue.task_done()
            if self.stop.wait(1):break

    def enrich(self,product,*,request=True):
        rows=product.get('ranking',[]);selected=product['selected']['symbol'];now=event_time(product.get('runtime',{}).get('now')) or datetime.now(VN)
        if request:
            self.request(selected,0)
            for row in rows:self.request(row['symbol'])
        with self.lock:cache=dict(self.cache);pending=len(self.pending)
        for row in rows:
            item=cache.get(row['symbol']) or {};day=item.get('day')
            trade_stamp=event_time(row.get('trade_time'))
            quote_day=(trade_stamp.date().isoformat() if trade_stamp else row.get('trading_date')) if row.get('last_price_vnd') else None
            if not day or day>now.date().isoformat():continue
            clean=dict(item)
            for side in ('buy','sell'):
                legacy=clean.pop(f'foreign_{side}_value_vnd',None)
                if legacy is not None:clean[f'foreign_{side}_value_raw']=legacy;clean['foreign_value_unit']='provider_unverified'
            if quote_day and day<quote_day:
                # Keep the previous session available for dated comparisons;
                # never mix it into today's price, range or turnover fields.
                row['daily_reference']=clean
                continue
            row['daily_statistics']=clean
            for key in ('open_price_vnd','high_price_vnd','low_price_vnd'):
                if item.get(key) is not None:row[key]=item[key]
            row['turnover_vnd']=item.get('turnover_vnd');row['turnover_day']=day
            row['turnover_basis']='ssi_daily_summary';row['turnover_received_at']=item['received_at']
            row.update(statistics_source='ssi_daily_summary',statistics_day=day,statistics_received_at=item['received_at'])
            if session_finished(now,day,row.get('market_code','HOSE')):
                row.update(last_price_vnd=item['close'],volume_shares=item['volume_shares'],
                    change_percent=item.get('change_percent'),trading_date=day,price_basis='ssi_daily_close',
                    price_asof_date=day,price_received_at=item['received_at'])
        # Selected may be outside the sector filter. Enrich it via the same code
        # without changing the filter or performing a second network request.
        chosen=next((r for r in rows if r['symbol']==selected),None)
        if chosen:product['selected']=dict(chosen)
        else:
            single={**product,'ranking':[product['selected']]}
            if product.get('_enrich_selected') is not True:
                single['_enrich_selected']=True;self.enrich(single,request=request);product['selected']=single['selected']
        if product.get('sort')=='volume':rows.sort(key=lambda r:(r.get('volume_shares') is None,-(r.get('volume_shares') or 0),r['symbol']))
        scope=product.get('coverage',{}).get('scope',{})
        scope['received_prices']=sum(isinstance(r.get('last_price_vnd'),(int,float)) and r['last_price_vnd']>0 for r in rows)
        scope['received_volumes']=sum(isinstance(r.get('volume_shares'),(int,float)) and r['volume_shares']>=0 for r in rows)
        if 'kpis' in product:product['kpis']['total_volume_shares']=sum(r['volume_shares'] for r in rows if isinstance(r.get('volume_shares'),(int,float)) and r['volume_shares']>=0)
        product['data_status']['daily_statistics_received']=sum(bool(cache.get(r['symbol'],{}).get('day')) for r in rows)
        product['data_status']['daily_statistics_pending']=pending
        product['data_status']['price_basis']=product['selected'].get('price_basis')
        signature=[(r['symbol'],r.get('price_basis'),r.get('last_price_vnd'),r.get('volume_shares'),r.get('turnover_vnd'),r.get('price_received_at'),r.get('turnover_received_at')) for r in rows]
        product['dataset_id']='product-'+sha256(json.dumps([product['dataset_id'],signature],sort_keys=True).encode()).hexdigest()[:16]
        return product

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)


_service=None;_lock=RLock()


def enrich_daily_statistics(product,*,request=True):
    global _service
    with _lock:
        if _service is None:_service=DailySummaries()
    return _service.enrich(product,request=request)
