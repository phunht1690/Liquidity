"""Read-only chart replay of genuine saved observations, independent of Live."""
from src.data.sqlite_connection import sqlite_session
from datetime import date
import json
import sqlite3

from src.data.live_analytics import SOURCE,_automatic,_stamp,_finite,receiver_phase
from src.data.liquidity import analyze_book
from src.data.market_rules import phase as market_phase,resolve_universe
from src.data.observation_store import read_series
from src.data.ssi_runtime import DATABASE,history_inventory
from src.data.price_history import price_fields,add_interval_volumes


def validate_query(query):
    if set(query)-{'day','symbol','universe'} or any(len(v)!=1 for v in query.values()):
        raise ValueError('Bộ lọc phát lại không hợp lệ')
    day=query.get('day',[None])[0]
    if day and date.fromisoformat(day).isoformat()!=day:raise ValueError('Ngày không hợp lệ')
    return day


def build_chart_archive(snapshots,query,config,days=None):
    day=validate_query(query)
    records=sorted((s for s in snapshots if s.get('source')==SOURCE and _automatic(s) and _stamp(s.get('captured_at'))),key=lambda s:_stamp(s['captured_at']))
    if records and not day:day=_stamp(records[-1]['captured_at']).date().isoformat()
    if day:records=[s for s in records if _stamp(s['captured_at']).date().isoformat()==day]
    if not records:
        return {'mode':'chart_replay','source':SOURCE,'days':days or [],'points':[],
                'universes':[],'symbols':[],'note':'Chưa có chuỗi dữ liệu đã lưu cho ngày này. Bộ thu cần chạy và lưu dữ liệu trước khi phát lại.'}
    latest=records[-1];membership=latest.get('membership') or {}
    groups=membership.get('universes') or {membership.get('group','VN30'):membership.get('symbols') or [r['symbol'] for r in latest.get('quotes',[])]}
    universe=resolve_universe(groups,query.get('universe',['VN30' if 'VN30' in groups else next(iter(groups))])[0])
    if universe not in groups:raise ValueError('Rổ chưa có trong ngày lưu')
    symbols=list(groups[universe])
    if not symbols:raise ValueError('Rổ lưu không có mã')
    symbol=query.get('symbol',['FPT' if 'FPT' in symbols else symbols[0]])[0].upper()
    if symbol not in symbols:raise ValueError('Mã chưa có trong rổ lưu')
    points=[];previous=None
    for snapshot in records:
        stamp=_stamp(snapshot['captured_at'])
        row=analyze_book(snapshot,symbol,config.get('notional_vnd',1e9),config,now=stamp)
        raw=next((r for r in snapshot.get('quotes',[]) if r.get('symbol')==symbol),{})
        phase=market_phase(stamp,raw.get('market_code','HOSE'))
        prices=price_fields(raw,snapshot['captured_at']);available=prices['price_available']
        elapsed=(stamp-_stamp(previous['received_at'])).total_seconds() if previous else None
        expected=config.get('ssi',{}).get('live_poll_seconds',10) if phase in ('continuous_am','continuous_pm','opening_auction','closing_auction') else config.get('ssi',{}).get('off_hours_poll_seconds',300)
        gap=bool(previous and (elapsed>max(35,expected*3) or previous['phase']!=phase or not previous['price_available'] or not available or previous.get('book_levels_captured')!=row.get('book_levels_captured')))
        point={'dataset_id':snapshot.get('dataset_id'),'received_at':stamp.isoformat(),
            'timestamp':stamp.isoformat(),'observation_at':stamp.isoformat(),'phase':phase,
            **prices,
            **{key:row.get(key) for key in ('spread_vnd','spread_bps','depth_min_vnd','depth_bid_vnd','depth_ask_vnd','known_bid_levels','known_ask_levels','book_levels_captured')},
            'valid':row['valid'],'quality':'valid' if row['valid'] else ','.join(row['quality_flags']),'quality_flags':row['quality_flags'],
            'price_available':available,'gap_before':gap,'elapsed_seconds':elapsed}
        points.append(point);previous=point
    add_interval_volumes(points)
    prices=[p['last_price_vnd'] for p in points if p['price_available']]
    return {'mode':'chart_replay','source':SOURCE,'timestamp_basis':'received_at',
        'day':_stamp(latest['captured_at']).date().isoformat(),'days':days or [],
        'universe':universe,'universes':[{'id':k,'count':len(v),'label':membership.get('labels',{}).get(k,k)} for k,v in groups.items()],
        'symbol':symbol,'symbols':symbols,'points':points,'frozen_at':latest['captured_at'],
        'summary':{'observations':len(points),'price_observations':len(prices),
            'liquidity_observations':sum(p['valid'] for p in points),
            'distinct_prices':len(set(prices)),'missing_symbol_observations':sum(not p['price_available'] for p in points)},
        'note':'Phát lại các lần máy đã nhận, không phải luồng tick. Giá và khối lượng có thể đứng yên ngoài giờ. Thiếu mẫu thì để trống; không nối qua khoảng trống hoặc đổi pha. Chỉ biểu đồ phát lại, bảng giá và cảnh báo bên ngoài vẫn theo bản mới nhất.'}


def read_chart_archive(query,config,*,database=DATABASE):
    day=validate_query(query)
    inventory=history_inventory(database=database);days=list(reversed(inventory['days']))
    if not days:return build_chart_archive([],query,config,days)
    selected=day or days[0]['day']
    if selected not in {d['day'] for d in days}:raise ValueError('Ngày chưa có dữ liệu lưu')
    result=_read_day(selected,query,config,database,days)
    if day or result.get('summary',{}).get('price_observations',0)>0:return result
    # Receipt-only weekend/holiday checkpoints must not hide the latest real
    # trading session. Keep an explicitly chosen empty day available as-is.
    for older in days[1:]:
        try:candidate=_read_day(older['day'],query,config,database,days)
        except ValueError:continue  # The ticker/scope may not exist in an older membership.
        if candidate.get('summary',{}).get('price_observations',0)>0:
            candidate['selection']={'mode':'latest_with_prices','latest_recorded_day':selected,
                                    'reason':'newest_day_without_prices'}
            return candidate
    return result


def _read_day(selected,query,config,database,days):
    # Resolve the day-specific membership once, then project only the requested
    # ticker. Legacy archives also avoid expanding thousands of whole books.
    from src.data.observation_store import tables,hydrate
    latest=None
    with sqlite_session(f'file:{database.as_posix()}?mode=ro',uri=True,timeout=3) as db:
        names=tables(db)
        candidates=[]
        for name in ('snapshots','captures'):
            if name in names:
                row=db.execute(f'SELECT dataset_id,captured_at FROM {name} WHERE day=? ORDER BY seq DESC LIMIT 1',(selected,)).fetchone()
                if row:candidates.append(row)
        if candidates:latest=hydrate(database,max(candidates,key=lambda r:r[1])[0])
    if not latest:return build_chart_archive([],{**query,'day':[selected]},config,days)
    membership=latest.get('membership') or {}
    groups=membership.get('universes') or {membership.get('group','VN30'):membership.get('symbols') or [r['symbol'] for r in latest.get('quotes',[])]}
    universe=query.get('universe',['VN30' if 'VN30' in groups else next(iter(groups),'VN30')])[0]
    requested_universe=universe
    universe=resolve_universe(groups,universe)
    if universe not in groups:
        # A single-ticker replay may predate expansion. Preserve the historical
        # scope label; never relabel an old VN100 capture as the whole HOSE.
        requested_symbol=query.get('symbol',['FPT'])[0].upper()
        choices=[k for k in ('VN100','VN30',*groups) if k in groups and requested_symbol in groups[k]]
        if universe not in ('VN30','VN100','HOSE','HNX','UPCOM','HNX_PILOT','UPCOM_PILOT') or not choices:raise ValueError('Rổ hoặc mã chưa có trong ngày lưu')
        universe=choices[0]
    symbol=query.get('symbol',['FPT' if 'FPT' in groups[universe] else groups[universe][0]])[0].upper()
    if symbol not in groups[universe]:raise ValueError('Mã chưa có trong rổ lưu')
    records=read_series(database,symbol,day=selected,limit=20000)
    result=build_chart_archive(records,{**query,'day':[selected],'universe':[universe]},config,days)
    result['requested_universe']=requested_universe
    return result
