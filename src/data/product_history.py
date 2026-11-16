"""Projected ticker history and one on-demand full book, for both storage versions."""
from src.data.observation_store import read_series,hydrate as hydrate_saved
from src.data.ssi_runtime import DATABASE,history_inventory
from src.data.product import _book
from src.data.ssi_feed import event_time
from src.data.market_rules import phase,resolve_universe


def load_product_history(query,latest,config,*,database=DATABASE,limit=10000):
    groups=(latest.get('membership') or {}).get('universes') or {}
    if not groups:
        membership=latest.get('membership') or {};groups={membership.get('group','VN30'):[r['symbol'] for r in latest.get('quotes',[])]}
    universe=resolve_universe(groups,query.get('universe',['VN30' if 'VN30' in groups else next(iter(groups))])[0])
    if universe not in groups:raise ValueError('Phạm vi chưa có dữ liệu')
    symbols=groups[universe];symbol=query.get('symbol',['FPT' if 'FPT' in symbols else symbols[0]])[0].upper()
    if symbol not in symbols:raise ValueError('Mã chưa có trong phạm vi')
    def hydrate(identity):
        if identity==latest.get('dataset_id'):return latest
        return hydrate_saved(database,identity) if database.is_file() else None
    records=read_series(database,symbol,limit=max(5000,int(limit)))
    cutoff=event_time(latest['captured_at'])
    records=[r for r in records if event_time(r['captured_at']) and event_time(r['captured_at'])<=cutoff]
    # If this instrument never had a valid book, one real reference can still
    # populate the other table rows. Never hydrate all snapshots into memory.
    has_valid=any(_book(r,symbol,config.get('notional_vnd',1e9),config,now=event_time(r['captured_at']))['valid'] for r in reversed(records))
    if not has_valid:
        def reference(candidates):
            attempted=0
            for record in reversed(candidates):
                stamp=event_time(record['captured_at'])
                if not stamp or stamp>cutoff or phase(stamp) not in ('continuous_am','continuous_pm'):continue
                if _book(record,symbol,config.get('notional_vnd',1e9),config,now=stamp)['valid']:return record
                full=hydrate(record['dataset_id'])
                if full and any(_book(full,s,config.get('notional_vnd',1e9),config,now=stamp)['valid'] for s in symbols):return full
                attempted+=1
                if attempted>=12:break
            return None
        saved=reference(records)
        if saved is None:
            # Several holiday/receipt-only days can push the real session out of
            # the recent three-day chart window. Seek just one older reference,
            # using inventory to skip days without continuous-market captures.
            represented={r['captured_at'][:10] for r in records}
            oldest=min(represented,default=cutoff.date().isoformat())
            for day in reversed(history_inventory(database=database)['days']):
                if day['day']>=oldest or not day.get('continuous_snapshots'):continue
                saved=reference(read_series(database,symbol,day=day['day'],limit=max(5000,int(limit))))
                if saved:break
        if saved:
            records=[r for r in records if r['dataset_id']!=saved['dataset_id']]+[saved]
            records.sort(key=lambda s:s['captured_at'])
    return records,hydrate
