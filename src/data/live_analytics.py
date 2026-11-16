"""Receiver-clock analytics from real SSI FastConnect polling observations.

No Quote.exchange_time is invented. These are indicative snapshot measures,
not exchange-event reconstruction, forecasts, or an order execution service.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
from math import floor, isfinite, log
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from src.finance.microstructure import DEFAULT_OBI_WEIGHTS, tick_size
from src.finance.scoring import DEFAULT_WEIGHTS, score_cross_section

VN = ZoneInfo('Asia/Ho_Chi_Minh')
SOURCE = 'ssi_fastconnect'
BASELINE = 'Ngưỡng theo dõi định trước · chưa hiệu chuẩn từ lịch sử; chỉ mô tả snapshot'
GROUPS = {'FPT':'Công nghệ','HPG':'Vật liệu','VCB':'Ngân hàng','VNM':'Tiêu dùng',
          'TCB':'Ngân hàng','MWG':'Bán lẻ','MBB':'Ngân hàng','VPB':'Ngân hàng',
          'SSI':'Chứng khoán','CTG':'Ngân hàng','BID':'Ngân hàng','VHM':'Bất động sản'}
COMPONENTS = {'spread_bps':('Spread','bps','thấp tốt'),
              'depth_min_vnd':('Độ sâu phía mỏng','VNĐ','cao tốt'),
              'execution_cost_bps':('Chi phí + phạt thiếu fill','bps','thấp tốt'),
              'amihud_5m':('Amihud ~5 phút (giá trị giao dịch ước tính)','return/tỷ VNĐ','thấp tốt'),
              'two_sided_ratio':('Khả dụng hai phía ~5 phút','tỷ lệ','cao tốt')}
METRICS = ('mid','spread_bps','spread_ticks','depth_bid_vnd','depth_ask_vnd','depth_min_vnd',
           'obi1','obi3','obi_w','weighted_mid','weighted_mid_dev_bps','amihud_5m',
           'two_sided_ratio','persistence','obi_persistence','five_minute_trade_value_vnd',
           'five_minute_elapsed_seconds','execution_cost_bps')


def _finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value)


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone(VN) if stamp.tzinfo and stamp.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def receiver_phase(stamp):
    """Clock estimate only; no claim about holidays or provider session flags."""
    if stamp is None or stamp.weekday() >= 5:
        return 'closed'
    minute = stamp.hour * 60 + stamp.minute
    if 540 <= minute < 555:return 'opening_auction'
    if 555 <= minute < 690:return 'continuous_am'
    if 690 <= minute < 780:return 'lunch'
    if 780 <= minute < 870:return 'continuous_pm'
    if 870 <= minute < 885:return 'closing_auction'
    return 'closed'


def _automatic(snapshot):
    return snapshot.get('collection_mode', snapshot.get('collection_kind')) == 'auto_collector'


def _raw(snapshot, symbol):
    if '_quote_index' in snapshot:return snapshot['_quote_index'].get(symbol)
    return next((row for row in snapshot.get('quotes', []) if row.get('symbol') == symbol), None)


def _fingerprint(raw):
    if not raw:return None
    return json.dumps([raw.get('source_book_time_raw'), raw.get('bids'), raw.get('asks')],sort_keys=True,separators=(',',':'))


def _empty_flow(reason='no_previous_snapshot'):
    return {'ofi_l1':None,'ofi_levels':[None,None,None],'ofi_3':None,'ofi_normalized':None,
            'ofi_interval_seconds':None,'ofi_status':reason,'ofi_persistence':None,'ofi_persistence_count':0}


def _book_flags(raw):
    if not raw:return ['missing_record']
    flags = list(raw.get('book_flags') or [])
    bids, asks = raw.get('bids') or [], raw.get('asks') or []
    if len(bids) != 3 or len(asks) != 3:
        flags.append('incomplete_levels')
    levels = bids + asks
    if any(not _finite(x.get('price')) or x['price'] <= 0 or not _finite(x.get('volume')) or x['volume'] < 0 for x in levels):
        flags.append('invalid_price_or_volume')
    if not flags:
        if bids[0]['price'] >= asks[0]['price']:flags.append('crossed_or_locked_book')
        if bids[0]['volume'] <= 0 or asks[0]['volume'] <= 0:flags.append('empty_best_level')
        if any(a['price'] < b['price'] for a,b in zip(bids,bids[1:])):flags.append('unsorted_bids')
        if any(a['price'] > b['price'] for a,b in zip(asks,asks[1:])):flags.append('unsorted_asks')
    return list(dict.fromkeys(flags))


def _execution(raw, mid, notional, side, config):
    lot = int(config.get('market',{}).get('lot_size',100))
    maximum = config.get('market',{}).get('max_round_lot_order_shares',500000)
    requested = floor(notional / mid / lot) * lot
    remaining, filled, value = requested, 0.0, 0.0
    if requested:
        for level in raw['asks' if side == 'buy' else 'bids']:
            take=min(remaining,level['volume']);value+=take*level['price'];filled+=take;remaining-=take
            if remaining <= 0:break
    vwap=value/filled if filled else None
    slip=(((vwap-mid) if side=='buy' else (mid-vwap))/mid*10000) if vwap else None
    return {'vwap':vwap,'slip_bps':slip,'fill_ratio':filled/requested if requested else None,
        'requested_shares':requested,'filled_shares':filled,'unfilled_shares':remaining,
        'filled_value_vnd':value,'reference_notional_vnd':notional,
        'single_order_eligible':bool(requested and requested<=maximum),'max_order_shares':maximum,
        'lot_size_assumed':lot,'lot_segment_verified':False,
        'scenario_note':'Ước tính hấp thụ ảnh bảng giá với lô quy đổi giả định; chưa xác nhận phân đoạn lô hoặc khả năng thực thi.',
        'flag':'below_one_lot' if not requested else 'partial_three_levels' if remaining else 'complete'}


def _base(snapshot, symbol, notional, config, *, stale=False, now=None, unchanged_age=None):
    raw=_raw(snapshot,symbol);stamp=_stamp(snapshot.get('captured_at'))
    phase=receiver_phase(stamp)
    flags=_book_flags(raw)
    if snapshot.get('source')!=SOURCE or (raw and raw.get('source',SOURCE)!=SOURCE):flags.append('source_mismatch')
    if not stamp:flags.append('invalid_received_timestamp')
    if stamp and now and stamp.date()!=now.date():flags.append('different_trading_day')
    if raw and stamp and raw.get('trading_date')!=stamp.date().isoformat():flags.append('unverified_or_old_trading_date')
    if phase not in ('continuous_am','continuous_pm'):flags.append('non_continuous_receiver_clock')
    source_stamp=_stamp(raw.get('exchange_time')) if raw else None
    if source_stamp and receiver_phase(source_stamp) not in ('continuous_am','continuous_pm'):
        flags.append('non_continuous_source_time')
    if raw and raw.get('provider_market_status') not in (None,'LO'):flags.append('provider_not_continuous')
    if stale:flags.append('stale_capture')
    if unchanged_age is not None and unchanged_age>config.get('ssi',{}).get('source_unchanged_seconds',120):flags.append('source_unchanged')
    valid=not flags
    row={'symbol':symbol,'group':(raw.get('group') if raw else None) or GROUPS.get(symbol,'Chưa phân loại'),'source':SOURCE,
        'name':raw.get('name') if raw else None,'timestamp':stamp.isoformat() if stamp and raw else None,
        'received_at':stamp.isoformat() if stamp and raw else None,'exchange_time':raw.get('exchange_time') if raw else None,
        'observation_at':stamp.isoformat() if stamp else None,
        'timestamp_basis':'received_at','phase':raw.get('phase','unverified') if raw else 'unverified',
        'receiver_phase':phase,'phase_basis':'receiver_clock_estimate','lot_segment':'unverified',
        'source_match_time_raw':raw.get('source_match_time_raw') if raw else None,
        'source_book_time_raw':raw.get('source_book_time_raw') if raw else None,
        'source_session_raw':raw.get('source_session_raw') if raw else None,
        'trading_date':raw.get('trading_date') if raw else None,
        'last_price_vnd':raw.get('last_price_vnd') if raw else None,
        'reference_price_vnd':raw.get('reference_price_vnd') if raw else None,
        'volume_shares':raw.get('volume_shares') if raw else None,
        'change_percent':raw.get('change_percent') if raw else None,
        'bids':raw.get('bids',[]) if raw else [],'asks':raw.get('asks',[]) if raw else [],
        'quality':'valid' if valid else ','.join(dict.fromkeys(flags)),
        'quality_flags':list(dict.fromkeys(flags)),'valid':valid,'analytics_flags':[],
        'buy':None,'sell':None,'fill_ratio':None,'baseline':BASELINE,
        'lqs':None,'lqs_status':'warming_up','category':'Chưa đủ dữ liệu',
        'source_unchanged_seconds':unchanged_age,'quote_age_seconds':raw.get('book_event_age_seconds') if raw else None,
        **dict.fromkeys(METRICS),**_empty_flow()}
    if not valid:return row
    bids,asks=raw['bids'],raw['asks'];b1,a1=bids[0],asks[0]
    mid=(b1['price']+a1['price'])/2
    depth_bid=sum(x['price']*x['volume'] for x in bids);depth_ask=sum(x['price']*x['volume'] for x in asks)
    bv=sum(x['volume'] for x in bids);av=sum(x['volume'] for x in asks)
    weights=config.get('obi_level_weights',DEFAULT_OBI_WEIGHTS)
    bw=sum(x['volume']*w for x,w in zip(bids,weights));aw=sum(x['volume']*w for x,w in zip(asks,weights))
    top=b1['volume']+a1['volume'];weighted=(a1['price']*b1['volume']+b1['price']*a1['volume'])/top
    reference=config.get('market',{}).get('tick_reference','mid')
    ref={'mid':mid,'bid1':b1['price'],'ask1':a1['price']}[reference]
    buy,sell=[_execution(raw,mid,notional,side,config) for side in ('buy','sell')]
    fills=[x['fill_ratio'] for x in (buy,sell)]
    row.update(mid=mid,spread_bps=(a1['price']-b1['price'])/mid*10000,
        spread_ticks=(a1['price']-b1['price'])/tick_size(ref,config.get('market',{}).get('tick_bands')),
        depth_bid_vnd=depth_bid,depth_ask_vnd=depth_ask,depth_min_vnd=min(depth_bid,depth_ask),
        obi1=(b1['volume']-a1['volume'])/top,obi3=(bv-av)/(bv+av),obi_w=(bw-aw)/(bw+aw),
        weighted_mid=weighted,weighted_mid_dev_bps=(weighted-mid)/mid*10000,
        buy=buy,sell=sell,fill_ratio=min(fills) if all(_finite(x) for x in fills) else None)
    return row


def _flow(previous,current,symbol,notional,config,max_gap):
    if not previous or not _automatic(previous) or not _automatic(current):return _empty_flow()
    old,new=_raw(previous,symbol),_raw(current,symbol)
    old_stamp,new_stamp=_stamp(previous.get('captured_at')),_stamp(current.get('captured_at'))
    if not old or not new or not old_stamp or not new_stamp:return _empty_flow('invalid_pair')
    elapsed=(new_stamp-old_stamp).total_seconds()
    if old_stamp.date()!=new_stamp.date() or receiver_phase(old_stamp)!=receiver_phase(new_stamp) or not 0<elapsed<=max_gap:
        return _empty_flow('gap_or_session_boundary')
    if not _base(previous,symbol,notional,config)['valid'] or not _base(current,symbol,notional,config)['valid']:
        return _empty_flow('invalid_pair')
    if _fingerprint(old)==_fingerprint(new):return _empty_flow('source_unchanged')
    values=[]
    for ob,b,oa,a in zip(old['bids'],new['bids'],old['asks'],new['asks']):
        values.append((b['volume'] if b['price']>=ob['price'] else 0)-(ob['volume'] if b['price']<=ob['price'] else 0)
                      -(a['volume'] if a['price']<=oa['price'] else 0)+(oa['volume'] if a['price']>=oa['price'] else 0))
    denominator=sum(x['volume'] for raw in (old,new) for side in ('bids','asks') for x in raw[side])/2
    return {**_empty_flow(),'ofi_l1':values[0],'ofi_levels':values,'ofi_3':sum(values),
        'ofi_normalized':sum(values)/denominator if denominator else None,'ofi_interval_seconds':elapsed,
        'ofi_status':'snapshot_approximation'}


def _historical(current,series,symbol,notional,config,max_gap):
    if not current['valid']:return current
    pos=len(series)-1
    flow=_flow(series[pos-1] if pos else None,series[pos],symbol,notional,config,max_gap)
    recent=[]
    for i in range(pos,max(0,pos-5),-1):
        item=_flow(series[i-1],series[i],symbol,notional,config,max_gap)
        if item['ofi_status']!='snapshot_approximation':break
        recent.append(item['ofi_normalized'])
    value=flow['ofi_normalized']
    flow['ofi_persistence_count']=len(recent)
    flow['ofi_persistence']=(sum(x*value>0 for x in recent)/len(recent) if value and len(recent)>=3 else None)
    current.update(flow)
    now=_stamp(series[-1]['captured_at']);target=now-timedelta(seconds=300)
    start=next((i for i in range(pos,-1,-1) if _stamp(series[i]['captured_at'])<=target),None)
    # Time remaining comes from the most recent continuous usable value window,
    # rather than resetting the display to five minutes on every failed poll.
    valid_start=pos
    while valid_start>0 and _automatic(series[valid_start]):
        a,b=series[valid_start-1],series[valid_start]
        sa,sb=_stamp(a['captured_at']),_stamp(b['captured_at'])
        ra,rb=_raw(a,symbol),_raw(b,symbol)
        if (not _automatic(a) or not ra or not rb or a.get('source')!=SOURCE or b.get('source')!=SOURCE
                or ra.get('source',SOURCE)!=SOURCE or rb.get('source',SOURCE)!=SOURCE
                or not 0<(sb-sa).total_seconds()<=max_gap or sa.date()!=sb.date()
                or receiver_phase(sa)!=receiver_phase(sb)):
            break
        va,vb=ra.get('cumulative_turnover_vnd',ra.get('cumulative_turnover_proxy_vnd')),rb.get('cumulative_turnover_vnd',rb.get('cumulative_turnover_proxy_vnd'))
        if (not _finite(va) or not _finite(vb) or vb<va
                or ra.get('turnover_basis') not in ('provider_total_trading_value_vnd','avg_match_price_times_volume_proxy')
                or rb.get('turnover_basis')!=ra.get('turnover_basis')):
            break
        valid_start-=1
        if (now-sa).total_seconds()>=300:break
    span=(now-_stamp(series[valid_start]['captured_at'])).total_seconds() if _automatic(series[valid_start]) else 0
    current['warmup_seconds']=max(0,300-span)
    if start is None:
        current['analytics_flags']=['incomplete_five_minute_window']
        return current
    window=series[start:]
    stamps=[_stamp(x['captured_at']) for x in window]
    elapsed=(stamps[-1]-stamps[0]).total_seconds()
    raws=[_raw(x,symbol) for x in window]
    bad=(elapsed>300+max_gap or any(not _automatic(x) or x.get('source')!=SOURCE for x in window)
         or any(not raw or raw.get('source',SOURCE)!=SOURCE for raw in raws)
         or any(not 0<(b-a).total_seconds()<=max_gap for a,b in zip(stamps,stamps[1:]))
         or any(x.date()!=now.date() or receiver_phase(x)!=receiver_phase(now) for x in stamps))
    if bad:
        current['analytics_flags']=['gap_or_session_boundary_in_window'];return current
    # Value and last-price windows can remain usable through a structurally bad
    # book; two-sided availability separately counts those invalid intervals.
    values=[raw.get('cumulative_turnover_vnd',raw.get('cumulative_turnover_proxy_vnd')) for raw in raws]
    prices=[raw.get('last_price_vnd') for raw in raws]
    if (any(not _finite(v) or v<0 for v in values) or any(not _finite(v) or v<=0 for v in prices)
            or any(raw.get('turnover_basis') not in ('provider_total_trading_value_vnd','avg_match_price_times_volume_proxy') or raw.get('turnover_basis')!=raws[-1].get('turnover_basis') for raw in raws)):
        current['analytics_flags']=['unavailable_trade_value_proxy'];return current
    if any(b<a for a,b in zip(values,values[1:])):
        current['analytics_flags']=['trade_counter_reset'];return current
    if any(raw.get('trading_date')!=now.date().isoformat() for raw in raws):
        current['analytics_flags']=['unverified_or_old_trading_date'];return current
    dv=values[-1]-values[0]
    current['five_minute_trade_value_vnd']=dv
    current['five_minute_elapsed_seconds']=elapsed
    current['amihud_5m']=abs(log(prices[-1]/prices[0]))/(dv/1e9) if dv>0 else None
    valid_seconds=sum((b-a).total_seconds() for i,(a,b) in enumerate(zip(stamps,stamps[1:]))
                      if _base(window[i],symbol,notional,config)['valid'])
    current['two_sided_ratio']=valid_seconds/elapsed
    current['warmup_seconds']=0
    current['turnover_basis']=raws[-1].get('turnover_basis')
    if dv<=0:current['analytics_flags']=['no_trade_value_in_window']
    return current


def _explain(row,weights):
    ranks=row.get('component_percentiles') or {}
    row['lqs_explanation']=[{'key':key,'label':label,'raw_value':row.get(key),'percentile':ranks.get(key),
        'weight':weights[key],'contribution':ranks[key]*weights[key] if key in ranks else None,
        'unit':unit,'direction':direction} for key,(label,unit,direction) in COMPONENTS.items()]
    if row.get('lqs') is not None:
        row['lqs_status']='provisional';row['lqs_reason']='LQS tạm tính từ ảnh lưu WebSocket, đồng hồ nhận và giá trị giao dịch ước tính từ giá khớp bình quân × khối lượng; đủ năm thành phần, chưa hiệu chuẩn hoặc kiểm định. Không phải xác suất rủi ro.'
    else:
        row['lqs_status']='unavailable' if not row['valid'] else 'warming_up'
        missing=[label for key,(label,_,_) in COMPONENTS.items() if not _finite(row.get(key))]
        row['lqs_reason']='Chưa tính LQS: '+(', '.join(row['quality_flags']) if not row['valid'] else 'thiếu '+', '.join(missing))+'. Không bù dữ liệu hoặc đổi trọng số.'


def _alerts(rows,stamp,enabled,config):
    if not enabled:return []
    th={'wide_spread_bps':25,'thin_depth_vnd':500e6,'critical_fill_ratio':.5,
        'pressure_ofi_normalized':.1,'persistence_ratio':.6,**(config.get('live_alerts') or config.get('monitoring_thresholds') or {})}
    alerts=[];order={'critical':0,'warning':1,'info':2}
    for row in rows:
        conditions=[]
        if not row['valid']:
            conditions.append({'severity':'warning','kind':'data_quality','type':'Chất lượng dữ liệu',
                'message':'Không tính chỉ báo cho '+', '.join(row['quality_flags'])+'.'})
        else:
            ratio=row.get('fill_ratio')
            if _finite(ratio) and ratio<1:
                conditions.append({'severity':'warning' if ratio>=th['critical_fill_ratio'] else 'critical',
                    'kind':'capacity','type':'Thiếu hấp thụ trong ảnh ba mức',
                    'message':f"N hiện tại: mua {row['buy']['fill_ratio']:.1%}, bán {row['sell']['fill_ratio']:.1%}. Ước tính lô giả định, không ngoại suy phần thiếu; ngưỡng chưa hiệu chuẩn."})
            if row['depth_min_vnd']<th['thin_depth_vnd']:
                conditions.append({'severity':'warning','kind':'depth','type':'Độ sâu dưới ngưỡng theo dõi',
                    'message':f"Phía mỏng {row['depth_min_vnd']/1e9:.2f} tỷ đồng; ngưỡng định trước {th['thin_depth_vnd']/1e9:.2f} tỷ, chưa hiệu chuẩn."})
            if row['spread_bps']>th['wide_spread_bps']:
                conditions.append({'severity':'warning','kind':'spread','type':'Spread vượt ngưỡng theo dõi',
                    'message':f"Spread {row['spread_bps']:.2f} bps; ngưỡng {th['wide_spread_bps']:.0f} bps chưa hiệu chuẩn, không phải bất thường thống kê đã xác nhận."})
            if _finite(row.get('ofi_normalized')) and _finite(row.get('ofi_persistence')) and abs(row['ofi_normalized'])>th['pressure_ofi_normalized'] and row['ofi_persistence']>=th['persistence_ratio']:
                conditions.append({'severity':'info','kind':'pressure','type':'OFI giữa ảnh lưu cùng chiều',
                    'message':f"OFI₃ {row['ofi_3']:+.0f} CP, chuẩn hóa {row['ofi_normalized']:+.3f}, persistence {row['ofi_persistence']:.0%}. Xấp xỉ giữa ảnh nhận; ngưỡng chưa kiểm định, không phải dự báo."})
        if conditions:
            conditions.sort(key=lambda c:order[c['severity']])
            alerts.append({'symbol':row['symbol'],'timestamp':stamp,'baseline':BASELINE,
                'severity':conditions[0]['severity'],'type':conditions[0]['type'],
                'message':' '.join(x['message'] for x in conditions),'conditions':conditions,'condition_count':len(conditions)})
    return sorted(alerts,key=lambda x:(order[x['severity']],x['symbol']))


def _intraday(rows):
    periods=[(555,570)]+[(x,x+30) for x in range(570,690,30)]+[(x,x+30) for x in range(780,870,30)]
    result=[]
    for start,end in periods:
        samples=[r for r in rows if r['valid'] and start<=(_stamp(r['timestamp']).hour*60+_stamp(r['timestamp']).minute)<end]
        label=lambda t:f'{t//60:02d}:{t%60:02d}'
        item={'bucket':f'{label(start)}–{label(end)}','start':label(start),'end':label(end),'sample_count':len(samples)}
        for key in ('spread_bps','depth_min_vnd'):
            values=[r[key] for r in samples if _finite(r.get(key))];item['median_'+key]=median(values) if values else None
        for side in ('buy','sell'):
            for key in ('slip_bps','fill_ratio'):
                values=[(r.get(side) or {}).get(key) for r in samples];values=[v for v in values if _finite(v)]
                item[f'median_{side}_{key}']=median(values) if values else None
        result.append(item)
    return result


def build_live_state(query, snapshots, runtime, config):
    """One coherent current snapshot for every panel; no Replay/index selection."""
    if any(k in query for k in ('index','frame','frame_index','replay')):raise ValueError('Replay không còn khả dụng')
    now=_stamp(runtime.get('now')) or datetime.now(VN)
    observations=[];last=None;late_count=0
    for original in snapshots:
        snapshot={**original,'_quote_index':{r['symbol']:r for r in original.get('quotes',[])}}
        stamp=_stamp(snapshot.get('captured_at'))
        if stamp is None:continue
        if last is not None and stamp<=last:
            late_count+=1;continue
        observations.append(snapshot);last=stamp
    latest=runtime.get('latest_snapshot') or (observations[-1] if observations else None)
    if not latest or not latest.get('quotes') or not _stamp(latest.get('captured_at')):raise FileNotFoundError('notready')
    if latest.get('source')!=SOURCE:raise ValueError('Nguồn hiện hành không khả dụng')
    latest={**latest,'_quote_index':{r['symbol']:r for r in latest.get('quotes',[])}}
    stamp=_stamp(latest['captured_at'])
    if _automatic(latest) and (not observations or _stamp(observations[-1]['captured_at'])<stamp):observations.append(latest)
    observations=[s for s in observations if _stamp(s['captured_at']).date()==stamp.date() and _stamp(s['captured_at'])<=stamp]
    current_series=observations if observations and _stamp(observations[-1]['captured_at'])==stamp else [latest]
    symbols=list(dict.fromkeys(latest.get('membership',{}).get('symbols') or [r['symbol'] for r in latest['quotes']]))
    universes=latest.get('membership',{}).get('universes') or {'VN30':symbols}
    universe=query.get('universe',['VN30' if 'VN30' in universes else next(iter(universes))])[0]
    if universe not in universes:raise ValueError('Rổ mã chưa được thu')
    symbols=[s for s in symbols if s in set(universes[universe])]
    if not symbols:raise FileNotFoundError('empty_universe')
    symbol=query.get('symbol',['FPT' if 'FPT' in symbols else symbols[0]])[0].upper()
    if symbol not in symbols:raise ValueError('Mã không có trong rổ nguồn hiện tại')
    def number(name,default,low,high):
        value=float(query.get(name,[str(default)])[0])
        if not isfinite(value) or not low<=value<=high:raise ValueError('Tham số ngoài phạm vi')
        return value
    notional=number('notional',config.get('notional_vnd',1e9),1e8,5e9)
    window=number('window',30,1,1440)
    group=query.get('group',['all'])[0] or 'all'
    def sector(s):
        return (_raw(latest,s) or {}).get('group') or GROUPS.get(s,'Chưa phân loại')
    if group not in {'all',*(sector(s) for s in symbols)}:raise ValueError('Nhóm không khả dụng')
    profiles=[{'id':k,'label':v['label'],'note':v.get('note','Chưa hiệu chuẩn'),
               'weights':config.get('lqs_weights',DEFAULT_WEIGHTS) if k=='baseline' else v['weights']}
              for k,v in config.get('lqs_profiles',{}).items()]
    if not profiles:profiles=[{'id':'baseline','label':'Gốc · Spread 25%','note':'Chưa hiệu chuẩn','weights':config.get('lqs_weights',DEFAULT_WEIGHTS)}]
    profile=query.get('lqs_profile',['baseline'])[0]
    weights=next((p['weights'] for p in profiles if p['id']==profile),None)
    if weights is None:raise ValueError('Trọng số không khả dụng')
    settings=config.get('ssi',{});live_poll=settings.get('live_poll_seconds',10)
    default_poll=live_poll if receiver_phase(now) in ('continuous_am','continuous_pm','opening_auction','closing_auction') else settings.get('off_hours_poll_seconds',300)
    poll=runtime.get('poll_interval_seconds',runtime.get('poll_seconds',default_poll))
    max_gap=settings.get('history_gap_seconds',max(35,live_poll*3.5))
    stale_after=runtime.get('stale_after_seconds',settings.get('snapshot_stale_seconds',max(35,live_poll*3.5)) if poll==live_poll else max(30,poll*3))
    age=(now-stamp).total_seconds();stale=bool(runtime.get('stale_capture')) or age>stale_after or age< -5
    phase=receiver_phase(now);capture_phase=receiver_phase(stamp)
    if phase!=capture_phase:stale=True
    def unchanged_age(s):
        raw=_raw(latest,s);finger=_fingerprint(raw);first=stamp
        for observation in reversed(current_series[:-1]):
            if _fingerprint(_raw(observation,s))!=finger:break
            first=_stamp(observation['captured_at'])
        return max(0,(now-first).total_seconds())
    rows=[]
    for s in symbols:
        row=_base(latest,s,notional,config,stale=stale,now=now,unchanged_age=unchanged_age(s))
        rows.append(_historical(row,current_series,s,notional,config,max_gap))
    scored=score_cross_section(rows,weights,config.get('incomplete_fill_penalty_bps',100))
    for row in scored:_explain(row,weights)
    selected=next(row.copy() for row in scored if row['symbol']==symbol)
    visible=[row for row in scored if group in ('all',row['group'])]
    # Profiles and history derive only genuine collector records, never a legacy
    # one-off cache or repeated browser reads of the same dataset.
    observed=[_base(s,symbol,notional,config) for s in observations if _automatic(s)]
    cutoff=stamp-timedelta(minutes=window)
    history=[r for r in observed if _stamp(r['observation_at'])>=cutoff]
    cost_curve=[]
    for value in (100e6,250e6,500e6,750e6,1e9,1.5e9,2e9,3e9,4e9,5e9):
        point=_base(latest,symbol,value,config,stale=stale,now=now,unchanged_age=unchanged_age(symbol))
        cost_curve.append({'notional':value,**{f'{side}_{key}':(point.get(side) or {}).get(key) for side in ('buy','sell') for key in ('slip_bps','fill_ratio')},'fill_ratio':point['fill_ratio']})
    valid_books=[r for r in visible if r['valid']];lqs=[r for r in visible if _finite(r.get('lqs'))]
    alerts=_alerts(visible,stamp.isoformat(),not stale and phase in ('continuous_am','continuous_pm') and stamp.date()==now.date(),config)
    pressures=[r for r in valid_books if _finite(r.get('ofi_normalized'))]
    spreads=[r['spread_bps'] for r in valid_books]
    ticks=[r['spread_ticks'] for r in observed if r['valid'] and _finite(r['spread_ticks'])]
    one_tick=sum(abs(v-1)<1e-8 for v in ticks)
    gaps=sum((_stamp(b['captured_at'])-_stamp(a['captured_at'])).total_seconds()>max_gap for a,b in zip(observations,observations[1:]))
    coverage={'visible_count':len(visible),'valid_book_count':len(valid_books),'valid_lqs_count':len(lqs),
        'reference_count':len(scored),'reference_lqs_count':sum(_finite(r.get('lqs')) for r in scored),
        'scope_label':f'Rổ {universe} / SSI' if group=='all' else f'{universe} · {group}',
        'invalid_symbols':[{'symbol':r['symbol'],'flags':r['quality_flags']} for r in visible if not r['valid']],
        'quote_age_seconds':selected.get('quote_age_seconds'),'capture_age_seconds':max(0,age)}
    remaining=selected.get('warmup_seconds',300)
    public_runtime={k:v for k,v in runtime.items() if k not in ('latest_snapshot','now')}
    public_runtime.update(now=now.isoformat(),poll_seconds=poll,capture_age_seconds=max(0,age),stale_capture=stale,
        last_success_at=latest['captured_at'],status='stale' if stale else runtime.get('status',runtime.get('state','polling')))
    phase_labels={'continuous_am':'Liên tục sáng','continuous_pm':'Liên tục chiều','lunch':'Nghỉ trưa',
                  'opening_auction':'Định kỳ mở cửa','closing_auction':'Định kỳ đóng cửa','closed':'Ngoài giờ giao dịch'}
    config_keys=('schema_version','market','lqs_weights','obi_level_weights','notional_vnd','incomplete_fill_penalty_bps','lqs_profiles','ssi','live_alerts','monitoring_thresholds')
    config_id=sha256(json.dumps({k:config.get(k) for k in config_keys},sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]
    archive=runtime.get('history_inventory') or {}
    raw_rows=[_raw(latest,s) for s in symbols]
    present=[r for r in raw_rows if r]
    structural=sum(not _book_flags(r) for r in present)
    eligible=sum(r['valid'] for r in scored)
    continuous_count=archive.get('continuous_snapshot_count',sum(receiver_phase(_stamp(s['captured_at'])) in ('continuous_am','continuous_pm') for s in observations))
    context='Ngoài giờ giao dịch liên tục; hiện chỉ xem bảng giá gần nhất.' if phase not in ('continuous_am','continuous_pm') else 'Chỉ dùng sổ hợp lệ, đúng ngày và còn mới.'
    readiness={'status':'incomplete_for_research','scope':universe,'scope_count':len(symbols),
        'collected_scope':latest.get('membership',{}).get('group','VN30'),'collected_count':len(latest['quotes']),
        'snapshot_count':archive.get('snapshot_count',len(observations)),
        'continuous_snapshot_count':continuous_count,
        'days_with_continuous_observations':archive.get('days_with_continuous_observations',int(continuous_count>0)),
        'archive_days':archive.get('days',[]),'ssi_observation_days':len({s['captured_at'][:10] for s in observations if _automatic(s)}),
        'note':'Đủ bảng giá không đồng nghĩa đủ bộ dữ liệu nghiên cứu. Mục tiêu 5–10 phiên cần đánh giá độ phủ từng phiên; số ngày có vài quan sát không phải số phiên hoàn chỉnh.',
        'items':[
            {'name':'Giá và khối lượng','available':sum(_finite(r.get('last_price_vnd')) and _finite(r.get('volume_shares')) for r in present),'total':len(symbols),'reason':'Có thể xem ngay theo thời điểm nhận.'},
            {'name':'Sổ lệnh ba mức hợp lệ','available':structural,'total':len(symbols),'reason':'Kiểm tra cấu trúc giá/khối lượng và cờ đấu giá; chưa xác nhận pha/lô nguồn.'},
            {'name':'Spread, độ sâu, OBI và chi phí','available':eligible,'total':len(symbols),'reason':context},
            {'name':'Dòng lệnh OFI','available':sum(_finite(r.get('ofi_3')) for r in scored),'total':len(symbols),'reason':'Cần hai ảnh sổ hợp lệ liên tiếp trong phiên, không có khoảng trống hoặc nguồn đóng băng.'},
            {'name':'Cửa sổ 5 phút và điểm LQS','available':sum(_finite(r.get('lqs')) for r in scored),'total':len(symbols),'reason':'Cần đủ 5 phút quan sát hợp lệ và đủ cả năm thành phần; thêm mã không thay thế thời gian thu.'},
            {'name':'Effective spread, hồi phục, dự báo','available':None,'total':None,'reason':'Chưa khả dụng: cần giao dịch ghép sổ lệnh, dữ liệu sự kiện và triển khai/kiểm chứng phương pháp.'}]}
    return {'mode':'live','source':SOURCE,'timezone':'Asia/Ho_Chi_Minh',
        'universe':universe,'available_universes':[{'id':k,'count':len(v)} for k,v in universes.items()],
        'data_readiness':readiness,
        'disclaimer':'Công cụ phân tích học thuật, không phải khuyến nghị đầu tư.',
        'updated_at':latest['captured_at'],'timestamp_basis':'received_at','exchange_time':selected.get('exchange_time'),
        'asof_source_symbol':selected['symbol'] if selected.get('timestamp') else next((r['symbol'] for r in scored if r.get('timestamp')),None),
        'dataset_id':latest.get('dataset_id','ssi-pending'),
        'config_version':config_id,'session_id':stamp.date().isoformat()+' / SSI FastConnect v3',
        'notional_vnd':notional,'applied_lqs_profile':profile,
        'symbols':[{'symbol':s,'group':sector(s)} for s in symbols],
        'sessions':[stamp.date().isoformat()],'phase_code':phase,'session_phase':phase_labels[phase]+' · theo giờ nhận, chưa xác minh cờ nguồn',
        'runtime':public_runtime,'connection':{'status':'stale' if stale else 'streaming','lag_ms':None,'live_available':(runtime.get('auth') or {}).get('websocket_status')=='connected',
            'poll_seconds':poll,'timestamp_basis':'received_at','note':'Nhận WebSocket SSI; chỉ số dùng ảnh lưu định kỳ, chưa đo độ trễ đường truyền.'},
        'warmup':{'required_seconds':300,'observed_seconds':max(0,300-remaining),'remaining_seconds':remaining,
            'note':'LQS chờ đủ khoảng 5 phút dữ liệu tự thu hợp lệ; dùng giá trị giao dịch ước tính từ giá khớp bình quân × khối lượng nên luôn là ước tính chưa kiểm định.'},
        'coverage':coverage,'selected':selected,'ranking':sorted(visible,key=lambda r:r.get('lqs') if _finite(r.get('lqs')) else -1,reverse=True),
        'history':history,'cost_curve':cost_curve,'alerts':alerts,'intraday_profile':_intraday(observed),
        'tick_diagnostics':{'sample_count':len(ticks),'one_tick_count':one_tick,'one_tick_share':one_tick/len(ticks) if ticks else None,
            'note':'Mã chọn trên các ảnh lưu từ WebSocket SSI đã tự thu; có thời điểm báo giá SSI; thiếu cờ phiên thì pha được ước tính theo giờ Việt Nam.'},
        'kpis':{'alert_count':len(alerts),'median_spread_bps':median(spreads) if spreads else None,
            'high_risk_count':sum(r['lqs']<25 for r in lqs) if lqs else None,'valid_lqs_count':len(lqs),
            'valid_book_count':len(valid_books),'strongest_pressure':max(pressures,key=lambda r:abs(r['ofi_normalized']),default=None)},
        'quality':{'source':SOURCE,'total_messages':sum(len(s.get('quotes',[])) for s in observations if _automatic(s)),
            'duplicate_count':(latest.get('auth') or {}).get('duplicate_events'),'late_count':(latest.get('auth') or {}).get('late_events',late_count),'invalid_count':sum(not r['valid'] for r in scored),
            'missing_record_count':sum(_raw(latest,s) is None for s in symbols),'gaps':gaps,'gap_details':[],
            'real_sessions':len({s['captured_at'][:10] for s in observations if _automatic(s)}),'ssi_observation_sessions':len({s['captured_at'][:10] for s in observations if _automatic(s)}),
            'recorded_sessions':len({s['captured_at'][:10] for s in observations if _automatic(s)}),
            'stale_count':sum('stale_capture' in r['quality_flags'] or 'source_unchanged' in r['quality_flags'] for r in scored),
            'note':'Quan sát thực từ SSI FastConnect; số ngày có mẫu không đồng nghĩa phiên đầy đủ. Nhóm ngành theo ICB của SSI. Thiếu cờ phiên thì dùng lịch giờ Việt Nam. Chỉ dùng ba mức đầu của quote lô chuẩn.'},
        'methodology':{'source':SOURCE,'lqs_reference_universe':universe,'lqs_weights':weights,'lqs_profiles':profiles,'applied_lqs_profile':profile,
            'lqs_profile_note':'Bộ trọng số định trước để đối chiếu độ nhạy, chưa hiệu chuẩn trên VN30; không tự giảm trọng số spread.',
            'baseline':BASELINE,'baseline_note':BASELINE+'. Cảnh báo theo snapshot hiện hành, không phải khuyến nghị hoặc bất thường thống kê đã kiểm định.',
            'execution_cost_penalty_bps':config.get('incomplete_fill_penalty_bps',100),
            'execution_cost_formula':'(buy_slip_bps + sell_slip_bps)/2 + penalty_bps*(1-(buy_fill_ratio+sell_fill_ratio)/2)',
            'execution_cost_note':'Ước tính hấp thụ ba mức với lô giả định; phạt thiếu fill chỉ là giả định xếp hạng, không phải chi phí toàn lệnh.',
            'applied_assumptions':{'lot_size':config.get('market',{}).get('lot_size',100),
                'tick_reference':config.get('market',{}).get('tick_reference','mid'),'obi_level_weights':list(config.get('obi_level_weights',DEFAULT_OBI_WEIGHTS)),
                'incomplete_fill_penalty_bps':config.get('incomplete_fill_penalty_bps',100),'timestamp_basis':'received_at',
                'lot_segment_verified':False,'phase_basis':'receiver_clock_estimate','turnover_basis':'avg_match_price_times_volume_proxy'},
            'lqs_note':'LQS tạm tính chỉ khi đủ năm thành phần; Amihud dùng giá khớp bình quân × tổng khối lượng từ SSI, có sai số làm tròn. Chờ đủ ~5 phút tự thu, không bù dữ liệu. Thứ hạng tương đối chưa hiệu chuẩn.',
            'scope':f'{len(symbols)} mã theo danh sách {universe} do SSI trả về. LQS được xếp hạng riêng trong rổ đang chọn; đổi rổ có thể đổi điểm. Ngày hiệu lực chưa đối chiếu HOSE. Dữ liệu lưu riêng SSI. Timestamp của bảng và OFI là giờ lưu; thời điểm báo giá nguồn được lưu riêng. Khi thiếu cờ phiên, pha chỉ là ước tính theo giờ Việt Nam.',
            'history_gap_seconds':max_gap,'sample_interval_seconds':poll,
            'pressure_note':'OFI là chênh lệch giữa các ảnh được lưu từ luồng SSI, dùng đồng hồ nhận và pha liên tục ước tính theo giờ Việt Nam; Chỉ báo OFI chưa sử dụng mọi sự kiện gốc. Giữ riêng timestamp báo giá SSI và thời điểm lưu ảnh. Không nối qua thiếu mã, khoảng trống, đổi nguồn/ngày/pha hoặc snapshot nguồn không đổi. Chuẩn hóa theo trung bình tổng KL sáu mức; persistence tối đa năm gia số liên tiếp, tối thiểu ba, số 0 trung tính.',
            'profile_note':'Hồ sơ theo giờ chỉ từ snapshot tự thu trong ngày, theo đồng hồ nhận. Không dùng dữ liệu mô phỏng hoặc tương lai, không nội suy khung trống. Pha phiên/lô chưa xác minh.',
            'effective_spread':{'status':'unavailable','trade_count':0,'note':'Chưa triển khai ghép giao dịch với quote trước khớp; không suy effective spread từ last price hoặc slippage hấp thụ.'},
            'resilience':{'status':'planned','note':'Đã lưu sự kiện SSI nhưng chưa triển khai và kiểm chứng phương pháp đo độ hồi phục.'},
            'forecast':{'status':'unavailable','horizons_seconds':[5,15,30],'control_seconds':60,
                'note':'Chưa kiểm định dự báo hoặc tái dựng sự kiện. Ảnh lưu định kỳ không bảo đảm tái dựng mọi sự kiện trong 5/15/30 giây; không nội suy để công bố độ chính xác.'},
            'limits':'Dữ liệu thị trường thật, chỉ ba mức hiển thị; các phép đo dùng giờ nhận, pha/lô giả định và giá trị giao dịch ước tính từ giá khớp bình quân × khối lượng. Chưa tính phí, thuế, độ trễ hoặc tác động thị trường; không gửi lệnh.'}}
