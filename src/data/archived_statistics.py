"""Reuse completed SSI daily OHLC already downloaded in the background.

OHLC `value` is not totalMatchValue: observed values equal close * volume.
Only prices and share volume are used here; money turnover comes from summary.
"""
from hashlib import sha256
from pathlib import Path
import json,sqlite3

from src.data.ssi_feed import PROJECT,VN,event_time,reference_for_day
from src.data.market_rules import session_finished


def enrich_archived_statistics(product,database=None):
    path=Path(database or PROJECT/'data/ssi/price_bars.sqlite3')
    if not path.is_file():return product
    now=event_time(product.get('runtime',{}).get('now'))
    if not now:return product
    try:
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True,timeout=2) as db:
            records=db.execute('''SELECT p.symbol,p.day,p.open,p.high,p.low,p.close,p.volume,d.checked_at
                FROM price_days d JOIN
                    (SELECT symbol,MAX(day) AS day FROM price_days WHERE timeframe='1d' AND closed=1 AND bar_count>0 GROUP BY symbol) latest
                    ON d.symbol=latest.symbol AND d.day=latest.day AND d.timeframe='1d'
                JOIN price_bars p ON p.symbol=d.symbol AND p.day=d.day AND p.timeframe='1d'
                ORDER BY p.stamp''').fetchall()
    except (sqlite3.Error,OSError):return product
    cached={s:(day,o,h,l,c,v,checked) for s,day,o,h,l,c,v,checked in records}
    selected=product['selected']['symbol'];rows=product['ranking']
    targets={r['symbol']:r for r in rows};targets.setdefault(selected,product['selected'])
    changed=[]
    for symbol,row in targets.items():
        item=cached.get(symbol)
        if not item:continue
        day,o,h,l,c,v,checked=item
        stamp=event_time(checked)
        trade=event_time(row.get('trade_time'))
        price_day=(row.get('price_asof_date') or (trade.date().isoformat() if trade else row.get('trading_date'))) if row.get('last_price_vnd') else None
        if not stamp or stamp>now or not session_finished(now,day,row.get('market_code','HOSE')):continue
        if price_day and day<price_day:continue
        summary=row.get('daily_statistics') or {}
        if row.get('price_basis')=='ssi_daily_close' and (row.get('price_asof_date') or '')>=day:continue
        if summary.get('day','')>=day:continue
        reference=reference_for_day(row,day)
        row.update(last_price_vnd=c,volume_shares=v,trading_date=day,price_basis='ssi_ohlc_daily',
            price_asof_date=day,price_received_at=checked,
            open_price_vnd=o,high_price_vnd=h,low_price_vnd=l,
            statistics_source='ssi_ohlc_daily',statistics_day=day,statistics_received_at=checked,
            change_percent=(c/reference-1)*100 if reference else None)
        changed.append((symbol,day,c,v,o,h,l,checked))
    if not changed:return product
    product['selected']=dict(targets[selected])
    if product.get('sort')=='volume':rows.sort(key=lambda r:(r.get('volume_shares') is None,-(r.get('volume_shares') or 0),r['symbol']))
    scope=product.get('coverage',{}).get('scope',{})
    scope['received_prices']=sum(r.get('last_price_vnd') is not None for r in rows)
    scope['received_volumes']=sum(r.get('volume_shares') is not None for r in rows)
    if 'kpis' in product:product['kpis']['total_volume_shares']=sum(r['volume_shares'] for r in rows if r.get('volume_shares') is not None)
    product['data_status']['ohlc_daily_received']=sum(r.get('statistics_source')=='ssi_ohlc_daily' for r in rows)
    product['data_status']['price_basis']=product['selected'].get('price_basis')
    product['dataset_id']='product-'+sha256(json.dumps([product['dataset_id'],changed]).encode()).hexdigest()[:16]
    return product
