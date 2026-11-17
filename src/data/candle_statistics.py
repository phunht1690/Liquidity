"""Use already-cached session candles; no extra REST call in a product request."""
from src.data.sqlite_connection import sqlite_session
from hashlib import sha256
import json,sqlite3
from src.data.ssi_feed import PROJECT,event_time,reference_for_day


def enrich_candle_statistics(product,database=None):
    path=database or PROJECT/'data/ssi/chart_history.sqlite3'
    if not path.is_file():return product
    selected=product['selected']['symbol'];rows=product['ranking']
    targets={r['symbol']:r for r in rows}
    if selected not in targets:targets[selected]=product['selected']
    try:
        with sqlite_session(f'file:{path.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            cached=db.execute("SELECT payload FROM chart_cache WHERE json_extract(payload,'$.range')='session' AND json_extract(payload,'$.timeframe')='5m' ORDER BY saved_at").fetchall()
        for (text,) in cached:
            data=json.loads(text);r=targets.get(data.get('symbol'));bars=data.get('bars') or []
            if not r or not bars or not data.get('complete_range') or data.get('invalid_records'):continue
            bars=sorted(bars,key=lambda b:b['timestamp']);day=bars[-1]['trading_date']
            if any(b.get('trading_date')!=day for b in bars) or not data.get('requested_from','').startswith(day):continue
            trade=event_time(r.get('trade_time'));bar_time=event_time(bars[-1]['timestamp'])
            if trade and trade.date().isoformat()>day:continue
            # SSI OHLC value in the received dataset equals close * volume;
            # it is not the actual matched value. Never promote it to turnover.
            daily_close=r.get('price_basis') in ('ssi_daily_close','ssi_ohlc_daily')
            can_advance=bool(trade and bar_time>trade) or not r.get('last_price_vnd') or daily_close and day>(r.get('price_asof_date') or '')
            if daily_close and (r.get('price_asof_date') or '')>=day:can_advance=False
            if can_advance and sum(b.get('volume_shares') or 0 for b in bars)>0 and day>=(r.get('trading_date') or ''):
                close=bars[-1]['close'];reference=reference_for_day(r,day)
                r.update(last_price_vnd=close,price_basis='ssi_ohlc_bar',price_asof_bar=bars[-1]['timestamp'],
                    price_received_at=data.get('updated_at'),trading_date=day)
                r['change_percent']=(close/reference-1)*100 if reference else None
                total=sum(b.get('volume_shares') or 0 for b in bars)
                if not trade or trade.date().isoformat()<day or total>=(r.get('volume_shares') or 0):r['volume_shares']=total
    except (sqlite3.Error,OSError,ValueError,KeyError,TypeError):return product
    if selected in targets:product['selected']=dict(targets[selected])
    if product.get('sort')=='volume':rows.sort(key=lambda r:(r.get('volume_shares') is None,-(r.get('volume_shares') or 0),r['symbol']))
    scope=product.get('coverage',{}).get('scope',{})
    scope['received_prices']=sum(isinstance(r.get('last_price_vnd'),(int,float)) and r['last_price_vnd']>0 for r in rows)
    scope['received_volumes']=sum(isinstance(r.get('volume_shares'),(int,float)) and r['volume_shares']>=0 for r in rows)
    product['data_status']['price_basis']=product['selected'].get('price_basis')
    if 'kpis' in product:product['kpis']['total_volume_shares']=sum(r['volume_shares'] for r in rows if isinstance(r.get('volume_shares'),(int,float)) and r['volume_shares']>=0)
    signature=[(r['symbol'],r.get('turnover_vnd'),r.get('turnover_received_at'),r.get('price_basis'),r.get('price_asof_bar'),r.get('price_received_at'),r.get('last_price_vnd')) for r in targets.values()]
    product['dataset_id']='product-'+sha256(json.dumps([product['dataset_id'],signature]).encode()).hexdigest()[:16]
    return product
