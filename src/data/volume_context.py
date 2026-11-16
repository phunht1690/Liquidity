"""Comparable actual volume, from completed provider candles already on disk."""
from datetime import timedelta
from pathlib import Path
from statistics import mean
import sqlite3
from src.data.ssi_feed import PROJECT,event_time,numeric

TARGET=20


def volume_context(row,now,database=None):
    result={'source':'ssi_ohlc_archive','target_sessions':TARGET,'sessions':0,'ratio':None,
            'average_volume_shares':None,'volume_shares':None,'day':None,'basis':None,'until':None,'slots':0}
    path=Path(database or PROJECT/'data/ssi/price_bars.sqlite3')
    trade=event_time(row.get('trade_time'))
    daily=row.get('price_basis') in ('ssi_daily_close','ssi_ohlc_daily')
    day=(row.get('price_asof_date') if daily else trade.date().isoformat() if trade else row.get('trading_date'))
    if not day or not now or day>now.date().isoformat() or not path.is_file():return result
    result['day']=day
    try:
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            if daily:
                result.update(basis='daily',volume_shares=numeric(row.get('volume_shares')))
                rows=db.execute('''SELECT p.day,p.volume FROM price_bars p JOIN price_days d
                    ON p.symbol=d.symbol AND p.timeframe=d.timeframe AND p.day=d.day
                    WHERE p.symbol=? AND p.timeframe='1d' AND p.day<? AND d.closed=1 AND d.bar_count=1
                    ORDER BY p.day DESC LIMIT ?''',(row['symbol'],day,TARGET)).fetchall()
                history=[(d,numeric(v)) for d,v in rows]
            else:
                if not trade:return result
                end=min(trade,now)
                current=db.execute("SELECT stamp,volume FROM price_bars WHERE symbol=? AND timeframe='5m' AND day=? ORDER BY stamp",(row['symbol'],day)).fetchall()
                slots={stamp[11:19]:numeric(v) for stamp,v in current if event_time(stamp) and event_time(stamp)+timedelta(minutes=5)<=end and numeric(v) is not None and numeric(v)>=0}
                if not slots:return result
                last=max(event_time(stamp) for stamp,v in current if stamp[11:19] in slots)
                result.update(basis='aligned_5m_candles',volume_shares=sum(slots.values()),slots=len(slots),until=(last+timedelta(minutes=5)).strftime('%H:%M'))
                previous=db.execute('''SELECT p.day,p.stamp,p.volume FROM price_bars p JOIN price_days d
                    ON p.symbol=d.symbol AND p.timeframe=d.timeframe AND p.day=d.day
                    WHERE p.symbol=? AND p.timeframe='5m' AND p.day<? AND d.closed=1 AND d.bar_count>0
                    ORDER BY p.day DESC,p.stamp''',(row['symbol'],day)).fetchall()
                grouped={}
                for d,stamp,v in previous:grouped.setdefault(d,{})[stamp[11:19]]=numeric(v)
                # Compare exactly the same observed slots. Missing bars are unknown.
                history=[(d,sum(values[s] for s in slots)) for d,values in sorted(grouped.items(),reverse=True)
                    if all(s in values and values[s] is not None and values[s]>=0 for s in slots)][:TARGET]
    except (sqlite3.Error,OSError,ValueError):return result
    history=[(d,v) for d,v in history if v is not None and v>=0]
    result['sessions']=len(history)
    result['first_session']=min((d for d,_ in history),default=None)
    result['last_session']=max((d for d,_ in history),default=None)
    if len(history)==TARGET:
        average=mean(v for _,v in history);result['average_volume_shares']=average
        if average>0 and result['volume_shares'] is not None and result['volume_shares']>=0:result['ratio']=result['volume_shares']/average
    return result


def enrich_volume_context(product,database=None):
    product['volume_context']=volume_context(product['selected'],event_time(product.get('runtime',{}).get('now') or product.get('updated_at')),database)
    return product
