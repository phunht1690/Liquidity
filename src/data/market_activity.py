"""Small asynchronous cache of SSI matched and negotiated market totals."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from queue import Queue,Empty
from threading import Event,RLock,Thread
import json,sqlite3,time
from src.data.ssi_feed import PROJECT,VN,SSISession,SSIAPIError,event_time,numeric

SCOPES=[('HOSE','board'),('HNX','board'),('UPCOM','board'),('VN30','index'),('VN100','index')]


def normalize(data,scope,now):
    rows=data if isinstance(data,list) else data.get('data',[])
    if isinstance(rows,dict):rows=[rows]
    valid=[]
    for row in rows or []:
        if not isinstance(row,dict):continue
        stamp=event_time(row.get('tradingDate'))
        if not stamp or stamp.date()>now.date():continue
        values={}
        for field,source in [('matched_volume_shares','totalMatch'),('matched_value_vnd','totalMatchValue'),('negotiated_volume_shares','totalDeal'),('negotiated_value_vnd','totalDealValue')]:
            value=numeric(row.get(source));values[field]=value if value is not None and value>=0 else None
        if not any(v is not None for v in values.values()):continue
        valid.append({'scope':scope,'day':stamp.date().isoformat(),'received_at':now.isoformat(),'source':'ssi_index_summary',**values})
    return max(valid,key=lambda row:row['day']) if valid else None


class MarketActivity:
    def __init__(self,database=None,factory=SSISession):
        self.database=Path(database or PROJECT/'data/ssi/market_activity.sqlite3')
        self.factory=factory;self.client=None;self.lock=RLock();self.stop=Event();self.queue=Queue();self.pending=set();self.checked={};self.cache={};self.retry_at=0;self.thread=None
        if self.database.is_file():
            try:
                with sqlite3.connect(f'file:{self.database.as_posix()}?mode=ro',uri=True) as db:
                    self.cache={key:json.loads(payload) for key,payload in db.execute('SELECT scope,payload FROM summaries')}
            except (OSError,sqlite3.Error,ValueError):pass

    def request(self):
        with self.lock:
            if time.time()<self.retry_at:return
            for scope,kind in SCOPES:
                if scope in self.pending or time.time()-self.checked.get(scope,0)<300:continue
                self.pending.add(scope);self.queue.put((scope,kind))
            if self.pending and (not self.thread or not self.thread.is_alive()):
                self.thread=Thread(target=self._run,daemon=True,name='ssi-market-activity');self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:scope,kind=self.queue.get(timeout=1)
            except Empty:continue
            if self.stop.wait(max(0,self.retry_at-time.time())):break
            try:
                if self.client is None:self.client=self.factory(PROJECT/'.env')
                result=normalize(self.client._get('/api/v3/data/indexSummary',{kind:scope}),scope,datetime.now(VN))
                if result:
                    self.database.parent.mkdir(parents=True,exist_ok=True)
                    with sqlite3.connect(self.database,timeout=3) as db:
                        db.execute('CREATE TABLE IF NOT EXISTS summaries(scope TEXT PRIMARY KEY,payload TEXT NOT NULL)')
                        db.execute('INSERT OR REPLACE INTO summaries VALUES(?,?)',(scope,json.dumps(result,allow_nan=False)))
                    with self.lock:self.cache[scope]=result
            except SSIAPIError as exc:
                if exc.code in ('rate_limited','market_access_denied','authentication_failed','missing_credentials'):
                    with self.lock:self.retry_at=time.time()+max(60,exc.retry_after or 60)
            except (OSError,sqlite3.Error,ValueError,TypeError):pass
            finally:
                with self.lock:self.pending.discard(scope);self.checked[scope]=time.time()
                self.queue.task_done()
            if self.stop.wait(.5):break

    def read(self):
        self.request()
        with self.lock:return {'source':'ssi_index_summary','items':deepcopy([self.cache[scope] for scope,_ in SCOPES if scope in self.cache]),'refresh_seconds':300}

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        if self.client:self.client.close()


_service=None;_lock=RLock()


def enrich_market_activity(product):
    global _service
    with _lock:
        if _service is None:_service=MarketActivity()
    product['market_activity']=_service.read()
    return product


def stop_market_activity():
    if _service:_service.close()
