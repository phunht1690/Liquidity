"""User-facing liquidity workspace from SSI observations, without research placeholders."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
from statistics import median
import csv,io,json,math

from src.data.live_analytics import SOURCE,VN,_base,_stamp,_automatic,receiver_phase
from src.data.price_history import price_fields,add_interval_volumes
from src.data.liquidity import analyze_book
from src.data.market_rules import phase,resolve_universe

FIELDS={'symbol','group','universe','notional','window','sort','dataset_id','alert_spread_bps'}

def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def safe_query(query):
    if set(query)-FIELDS or any(len(v)!=1 for v in query.values()):raise ValueError('Bộ lọc không hợp lệ')
    return query

def _number(query,key,default,low,high):
    try:value=float(query.get(key,[default])[0])
    except (TypeError,ValueError):raise ValueError('Giá trị bộ lọc không hợp lệ') from None
    if not math.isfinite(value) or not low<=value<=high:raise ValueError('Giá trị ngoài phạm vi')
    return value

def _rows(snapshot):return {r['symbol']:r for r in snapshot.get('quotes',[]) if isinstance(r,dict) and isinstance(r.get('symbol'),str)}

def _received_counts(rows):
    """Receipt is independent of session validity and freshness of the book."""
    def has_quote(row):
        def side_has_level(side):
            levels=row.get(side) or []
            return isinstance(levels,list) and any(isinstance(p,dict) and finite(p.get('price')) and p['price']>0
                       and finite(p.get('volume')) and p['volume']>=0 for p in levels)
        return bool(row.get('source_book_time_raw')) and (row.get('book_structure_verified') or side_has_level('bids') and side_has_level('asks'))
    return {'symbols':len(rows),
            'received_prices':sum(finite(r.get('last_price_vnd')) and r['last_price_vnd']>0 for r in rows),
            'received_volumes':sum(finite(r.get('volume_shares')) and r['volume_shares']>=0 for r in rows),
            'received_books':sum(has_quote(r) for r in rows)}


def _book(snapshot,symbol,notional,config,*,now=None,stale=False):
    return analyze_book(snapshot,symbol,notional,config,now=now,stale=stale)

def build_product(query,snapshots,runtime,config,*,analysis_loader=None):
    safe_query(query);now=_stamp(runtime.get('now')) or datetime.now(VN)
    latest=runtime.get('latest_snapshot') or (snapshots[-1] if snapshots else None)
    if not latest or latest.get('source')!=SOURCE or not _stamp(latest.get('captured_at')):raise FileNotFoundError('ssi_not_ready')
    latest_stamp=_stamp(latest['captured_at']);market_rows=_rows(latest)
    membership=latest.get('membership') or {};universes=membership.get('universes') or {membership.get('group','VN30'):list(market_rows)}
    default='VN30' if 'VN30' in universes else next(iter(universes))
    universe=resolve_universe(universes,query.get('universe',[default])[0])
    if universe not in universes:raise ValueError('Phạm vi chưa có dữ liệu')
    symbols=list(dict.fromkeys(universes[universe]))
    if not symbols:raise FileNotFoundError('empty_scope')
    symbol=query.get('symbol',['FPT' if 'FPT' in symbols else symbols[0]])[0].upper()
    if symbol not in symbols:raise ValueError('Mã chưa có trong phạm vi')
    sector=lambda s:(market_rows.get(s) or {}).get('group') or 'Khác'
    group=query.get('group',['all'])[0]
    if group not in {'all',*(sector(s) for s in symbols)}:raise ValueError('Nhóm ngành không hợp lệ')
    notional=_number(query,'notional',config.get('notional_vnd',1e9),1e8,5e9)
    window=_number(query,'window',1440,1,1440)
    spread_threshold=_number(query,'alert_spread_bps',config.get('live_alerts',{}).get('wide_spread_bps',25),1,500)
    sort=query.get('sort',['depth'])[0]
    if sort not in ('depth','spread','volume','symbol'):raise ValueError('Cách sắp xếp không hợp lệ')
    observations=[];seen=set()
    for snapshot in [*snapshots,latest]:
        stamp=_stamp(snapshot.get('captured_at'))
        if snapshot.get('source')!=SOURCE or not _automatic(snapshot) or not stamp or stamp>latest_stamp:continue
        if snapshot.get('dataset_id') in seen:continue
        seen.add(snapshot.get('dataset_id'));observations.append(snapshot)
    observations.sort(key=lambda s:_stamp(s['captured_at']))
    selected_board=market_rows.get(symbol,{}).get('market_code','HOSE')
    live_phase=phase(now,selected_board);stale=bool(runtime.get('stale_capture')) or (now-latest_stamp).total_seconds()>max(35,float(runtime.get('poll_seconds',30))*3)
    analysis=None;analysis_mode='waiting'
    if live_phase in ('continuous_am','continuous_pm') and latest_stamp.date()==now.date() and not stale and (runtime.get('auth') or {}).get('websocket_status')=='connected':
        if any(_book(latest,s,notional,config,now=now)['valid'] for s in symbols):analysis=latest;analysis_mode='live'
    if analysis is None:
        # Use a genuine saved continuous-market observation as an explicitly dated reference.
        # This is not global replay, and current prices retain their own source timestamps.
        for saved in reversed(observations):
            stamp=_stamp(saved['captured_at'])
            if phase(stamp,selected_board) not in ('continuous_am','continuous_pm'):continue
            raw=_rows(saved).get(symbol)
            if raw and _book(saved,symbol,notional,config,now=stamp)['valid']:
                analysis=saved;analysis_mode='saved';break
        if analysis is None:
            for saved in reversed(observations):
                if saved.get('_compact'):continue
                stamp=_stamp(saved['captured_at'])
                if receiver_phase(stamp) not in ('continuous_am','continuous_pm'):continue
                if any(_book(saved,s,notional,config,now=stamp)['valid'] for s in symbols):analysis=saved;analysis_mode='saved';break
    if analysis and analysis.get('_compact') and analysis_loader:
        full=analysis_loader(analysis['dataset_id'])
        if full and full.get('dataset_id')==analysis['dataset_id'] and full.get('source')==SOURCE:analysis=full
        else:analysis=None;analysis_mode='waiting'
    analysis_stamp=_stamp(analysis['captured_at']) if analysis else None
    analysis_rows=_rows(analysis) if analysis else {}
    if analysis:analysis={**analysis,'_quote_index':analysis_rows}
    calculated={s:_book(analysis,s,notional,config,now=now if analysis_mode=='live' else analysis_stamp) for s in symbols} if analysis else {}
    rows=[]
    for s in symbols:
        quote=market_rows.get(s,{})
        row=calculated.get(s) or {'symbol':s,'valid':False,'quality_flags':['waiting_for_regular_book'],'bids':quote.get('bids',[]),'asks':quote.get('asks',[]),'buy':None,'sell':None,'buy_share':None,'sell_share':None}
        row={**row,'group':sector(s),'name':quote.get('name'),
             'last_price_vnd':quote.get('last_price_vnd'),'reference_price_vnd':quote.get('reference_price_vnd'),'reference_date':quote.get('reference_date') or quote.get('trading_date'),
             'change_percent':quote.get('change_percent'),'volume_shares':quote.get('volume_shares'),
             'trading_date':quote.get('trading_date'),'trade_time':quote.get('source_match_time_raw'),
             **{k:quote.get(k) for k in ('market_code','open_price_vnd','high_price_vnd','low_price_vnd','last_trade_quantity_shares','last_trade_side','ceiling_price_vnd','floor_price_vnd','avg_match_price_vnd')},
             'price_basis':'last_received_trade',
             'analysis_at':analysis['captured_at'] if analysis and row['valid'] else None,'analysis_mode':analysis_mode}
        rows.append(row)
    selected=deepcopy(next(r for r in rows if r['symbol']==symbol))
    visible=[r for r in rows if group in ('all',r['group'])]
    def order(r):
        if sort=='symbol':return (False,r['symbol'])
        key={'depth':'depth_min_vnd','spread':'spread_bps','volume':'volume_shares'}[sort];value=r.get(key)
        return (not finite(value),value if sort=='spread' and finite(value) else -value if finite(value) else 0,r['symbol'])
    visible.sort(key=order)
    alerts=[]
    for r in visible:
        if not r['valid']:continue
        reasons=[]
        buy,sell=r.get('buy') or {},r.get('sell') or {}
        if any(finite(side.get('fill_ratio')) and side['fill_ratio']<1 for side in (buy,sell)):
            reasons.append({'kind':'capacity','label':'Chưa đủ khối lượng chờ','buy_fill':buy.get('fill_ratio'),'sell_fill':sell.get('fill_ratio')})
        if finite(r.get('spread_bps')) and r['spread_bps']>spread_threshold:
            reasons.append({'kind':'spread','label':'Vượt ngưỡng chênh giá','value_bps':r['spread_bps'],
                            'value_vnd':r.get('spread_vnd'),'value_ticks':r.get('spread_ticks'),'threshold_bps':spread_threshold})
        if reasons:alerts.append({'symbol':r['symbol'],'group':r['group'],'reasons':reasons,'priority':'capacity' if reasons[0]['kind']=='capacity' else 'spread',
            'buy_fill':buy.get('fill_ratio'),'sell_fill':sell.get('fill_ratio'),'spread_bps':r.get('spread_bps'),
            'spread_vnd':r.get('spread_vnd'),'spread_ticks':r.get('spread_ticks'),
            'analysis_at':r['analysis_at'],'analysis_mode':analysis_mode})
    # Rank by observable shortage first, without inventing a risk probability.
    alerts.sort(key=lambda a:(a['priority']!='capacity',
        min(a[k] if finite(a.get(k)) else 1 for k in ('buy_fill','sell_fill')),
        -(a['spread_bps'] if finite(a.get('spread_bps')) else 0),a['symbol']))
    cutoff=latest_stamp-timedelta(minutes=window);history=[]
    for saved in observations:
        stamp=_stamp(saved['captured_at'])
        if stamp<cutoff or stamp.date()!=latest_stamp.date():continue
        raw=_rows(saved).get(symbol)
        if not raw:continue
        measure=_book(saved,symbol,notional,config,now=stamp)
        phase_code=phase(stamp,raw.get('market_code','HOSE'))
        expected=config.get('ssi',{}).get('live_poll_seconds',10) if phase_code in ('continuous_am','continuous_pm','opening_auction','closing_auction') else config.get('ssi',{}).get('off_hours_poll_seconds',300)
        gap=bool(history and ((stamp-_stamp(history[-1]['received_at'])).total_seconds()>max(35,expected*3) or history[-1]['phase']!=phase_code or history[-1].get('book_levels_captured')!=measure.get('book_levels_captured')))
        history.append({'timestamp':saved['captured_at'],'received_at':saved['captured_at'],
            **price_fields(raw,saved['captured_at']),
            **{key:measure.get(key) for key in ('spread_vnd','spread_bps','depth_min_vnd','depth_bid_vnd','depth_ask_vnd','known_bid_levels','known_ask_levels','book_levels_captured')},
            'valid':measure['valid'],'quality':'valid' if measure['valid'] else 'not_continuous','phase':phase_code,'gap_before':gap})
    add_interval_volumes(history)
    curve=[]
    if analysis and selected['valid']:
        for n in (1e8,2.5e8,5e8,7.5e8,1e9,1.5e9,2e9,3e9,4e9,5e9):
            row=_book(analysis,symbol,n,config,now=analysis_stamp)
            curve.append({'notional':n,**{f'{side}_{key}':(row.get(side) or {}).get(key) for side in ('buy','sell') for key in ('slip_bps','fill_ratio')}})
    auth=runtime.get('auth') or {};inventory=runtime.get('history_inventory') or {}
    collector_counts=_received_counts(list(market_rows.values()))
    scope_counts=_received_counts([market_rows[r['symbol']] for r in visible if r['symbol'] in market_rows])
    scope_counts['symbols']=len(visible)
    scope_counts['valid_books']=sum(r['valid'] for r in visible)
    connected=auth.get('websocket_status')=='connected'
    reference='Đang cập nhật trong phiên' if analysis_mode=='live' else 'Ảnh sổ đã lưu trong phiên' if analysis_mode=='saved' else 'Đang chờ ảnh sổ trong phiên'
    view_id='product-'+sha256(json.dumps([latest.get('dataset_id'),analysis.get('dataset_id') if analysis else None,universe,group,notional,sort,spread_threshold],ensure_ascii=False).encode()).hexdigest()[:16]
    valid_rows=[r for r in visible if r['valid']]
    spreads=[r['spread_bps'] for r in valid_rows if finite(r.get('spread_bps'))]
    return {'schema_version':1,'mode':'live','source':SOURCE,'timezone':'Asia/Ho_Chi_Minh','dataset_id':view_id,
        'market_dataset_id':latest.get('dataset_id'),'analysis_dataset_id':analysis.get('dataset_id') if analysis else None,
        'updated_at':latest['captured_at'],'universe':universe,'group':group,'sort':sort,'notional_vnd':notional,
        'available_universes':[{'id':k,'count':len(v),'label':membership.get('labels',{}).get(k,k),'pilot':k.endswith('_PILOT')} for k,v in universes.items()],
        'symbols':[{'symbol':s,'group':sector(s)} for s in symbols],
        'selected':selected,'ranking':visible,'alerts':alerts,'history':history,'cost_curve':curve,
        'alert_rules':{'spread_threshold_bps':spread_threshold,'basis':'monitoring_threshold',
                       'note':'Ngưỡng theo dõi có thể điều chỉnh; không phải kết luận bất thường hay dự báo giá.'},
        'analysis':{'mode':analysis_mode,'label':reference,'asof':analysis['captured_at'] if analysis else None,
                    'live_alerts':analysis_mode=='live','book_reference_time':selected.get('source_book_time_raw')},
        'phase_code':live_phase,'runtime':{k:v for k,v in runtime.items() if k not in ('latest_snapshot','history_inventory')},
        'coverage':{'visible_count':len(visible),'reference_count':len(symbols),'valid_book_count':len(valid_rows),
                    'received_prices':collector_counts['received_prices'],'received_books':collector_counts['received_books'],
                    'collected_count':len(market_rows),'scope':scope_counts,'collector':collector_counts},
        'kpis':{'median_spread_bps':median(spreads) if spreads else None,
                'attention_count':len(alerts),'total_volume_shares':sum(r['volume_shares'] for r in visible if finite(r.get('volume_shares')))},
        'data_status':{'stream_connected':connected,'last_stream_at':auth.get('last_stream_at'),'cached':analysis_mode!='live',
            'snapshots':inventory.get('snapshot_count',len(observations)),'days':inventory.get('days',[]),
            'membership_warnings':membership.get('warnings',[]),'membership_provenance':membership.get('provenance',{}),
            'catalog_counts':membership.get('catalog_counts',{}),'pilot_boards':membership.get('pilot_boards',[]),
            'storage_format':inventory.get('storage_format','legacy_snapshots'),
            'raw_archive_status':auth.get('raw_archive_status'),'raw_archive_budget_mb':auth.get('raw_archive_budget_mb'),
            'received_events':auth.get('received_events',0),'last_error':runtime.get('last_error'),
            'price_time':selected.get('trade_time'),'book_time':selected.get('source_book_time_raw')},
        'disclaimer':'Ước tính từ lượng chờ công khai; không phải khuyến nghị đầu tư.'}

def export_product(state):
    fields=['source','universe','market_dataset_id','analysis_dataset_id','analysis_mode','market_captured_at',
            'symbol','name','group','market_code','last_price_vnd','reference_price_vnd','reference_date','ceiling_price_vnd','floor_price_vnd','avg_match_price_vnd','change_percent','volume_shares','trade_time',
            'price_basis','price_asof_date','price_asof_bar','price_received_at','turnover_vnd','turnover_day','turnover_basis','turnover_received_at',
            'open_price_vnd','high_price_vnd','low_price_vnd','statistics_source','statistics_day','statistics_received_at',
            'summary_day','summary_turnover_vnd','summary_received_at','foreign_buy_shares','foreign_sell_shares','foreign_room_remaining_shares',
            'analysis_at','source_book_time_raw','valid','known_bid_levels','known_ask_levels','book_level_count','book_level_limit','book_levels_captured','spread_vnd','spread_bps','depth_bid_vnd','depth_ask_vnd','depth_min_vnd',
            'buy_share','sell_share','notional_vnd','buy_fill_ratio','sell_fill_ratio','buy_vwap','sell_vwap','buy_slip_bps','sell_slip_bps',
            'buy_requested_shares','sell_requested_shares','buy_filled_value_vnd','sell_filled_value_vnd','sizing_price_vnd','sizing_basis','lot_size']
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fields,extrasaction='ignore');writer.writeheader()
    for row in state['ranking']:
        summary=row.get('daily_statistics') or row.get('daily_reference') or {}
        writer.writerow({**row,'source':SOURCE,'universe':state['universe'],'market_dataset_id':state['market_dataset_id'],
            'analysis_dataset_id':state['analysis_dataset_id'],'market_captured_at':state['updated_at'],'notional_vnd':state['notional_vnd'],
            'summary_day':summary.get('day'),'summary_turnover_vnd':summary.get('turnover_vnd'),'summary_received_at':summary.get('received_at'),
            **{key:summary.get(key) for key in ('foreign_buy_shares','foreign_sell_shares','foreign_room_remaining_shares')},
            **{f'{side}_{key}':(row.get(side) or {}).get(key) for side in ('buy','sell') for key in ('fill_ratio','vwap','slip_bps','requested_shares','filled_value_vnd')}})
    return stream.getvalue().encode('utf-8-sig')
