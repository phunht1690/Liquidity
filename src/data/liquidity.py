"""Product calculations for known sparse books; missing and empty are distinct."""
from math import floor,isfinite
from src.data.ssi_feed import event_time,MAX_BOOK_LEVELS
from src.data.market_rules import phase,tick_distance


def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(v)


def analyze_book(snapshot,symbol,notional,config,*,now=None,stale=False):
    raw=(snapshot.get('_quote_index') or {}).get(symbol)
    if raw is None:raw=next((r for r in snapshot.get('quotes',[]) if r.get('symbol')==symbol),{})
    stamp=event_time(snapshot.get('captured_at'));board=raw.get('market_code') or 'HOSE'
    flags=list(raw.get('book_flags') or [])
    verified=bool(raw.get('book_structure_verified'))
    if verified:flags=[f for f in flags if f not in ('incomplete_levels','empty_best_level','invalid_price_or_volume','crossed_or_locked_book','unsorted_levels')]
    if not raw:flags.append('missing_record')
    if snapshot.get('source')!='ssi_fastconnect':flags.append('source_mismatch')
    if not stamp:flags.append('invalid_received_timestamp')
    if stamp and raw.get('trading_date')!=stamp.date().isoformat():flags.append('unverified_or_old_trading_date')
    if stamp and now and stamp.date()!=now.date():flags.append('different_trading_day')
    if phase(stamp,board) not in ('continuous_am','continuous_pm'):flags.append('non_continuous_receiver_clock')
    source_stamp=event_time(raw.get('exchange_time'))
    if source_stamp and stamp and source_stamp.date()!=stamp.date():flags.append('book_from_another_trading_day')
    if source_stamp and phase(source_stamp,board) not in ('continuous_am','continuous_pm'):flags.append('non_continuous_source_time')
    if raw.get('provider_market_status') not in (None,'LO'):flags.append('provider_not_continuous')
    if board not in ('HOSE','HNX','UPCOM'):flags.append('unsupported_market_or_instrument')
    if board!='HOSE' and not raw.get('units_verified'):flags.append('pilot_units_not_verified')
    if stale:flags.append('stale_capture')
    sides={}
    for side in ('bids','asks'):
        values=raw.get(side) or []
        if not verified and (not 1<=len(values)<=MAX_BOOK_LEVELS or any(not finite(x.get('price')) or x['price']<=0 or not finite(x.get('volume')) or x['volume']<0 for x in values)):
            flags.append('incomplete_levels')
        sides[side]=[x for x in values[:MAX_BOOK_LEVELS] if finite(x.get('price')) and x['price']>0 and finite(x.get('volume')) and x['volume']>0]
    bids,asks=sides['bids'],sides['asks']
    if bids and asks and bids[0]['price']>=asks[0]['price']:flags.append('crossed_or_locked_book')
    if any(a['price']<b['price'] for a,b in zip(bids,bids[1:])) or any(a['price']>b['price'] for a,b in zip(asks,asks[1:])):flags.append('unsorted_levels')
    row={k:raw.get(k) for k in ('symbol','name','group','source','exchange_time','source_book_time_raw','source_match_time_raw','received_at','market_code')}
    row.update(symbol=symbol,valid=not flags,quality_flags=list(dict.fromkeys(flags)),bids=(raw.get('bids') or [])[:MAX_BOOK_LEVELS],asks=(raw.get('asks') or [])[:MAX_BOOK_LEVELS],
        mid=None,spread_bps=None,spread_ticks=None,spread_vnd=None,depth_bid_vnd=None,depth_ask_vnd=None,depth_min_vnd=None,
        buy=None,sell=None,fill_ratio=None,buy_share=None,sell_share=None,two_sided=bool(bids and asks),
        known_bid_levels=len(bids),known_ask_levels=len(asks),book_level_count=max(len(bids),len(asks)),book_level_limit=MAX_BOOK_LEVELS,
        book_levels_captured=min(MAX_BOOK_LEVELS,max(len(raw.get('bids') or []),len(raw.get('asks') or []))),book_structure_verified=verified)
    if flags:return row
    mid=(bids[0]['price']+asks[0]['price'])/2 if bids and asks else None
    sizing=mid or raw.get('last_price_vnd') or raw.get('reference_price_vnd')
    lot=raw.get('lot_size') or config.get('market',{}).get('lot_size',100)
    lot=int(lot) if finite(lot) and lot>0 else 100
    depth_b=sum(x['price']*x['volume'] for x in bids);depth_a=sum(x['price']*x['volume'] for x in asks)
    bv=sum(x['volume'] for x in bids);av=sum(x['volume'] for x in asks)
    row.update(mid=mid,depth_bid_vnd=depth_b,depth_ask_vnd=depth_a,depth_min_vnd=min(depth_b,depth_a),
        buy_share=bv/(bv+av) if bv+av else None,sell_share=av/(bv+av) if bv+av else None,
        sizing_price_vnd=sizing,sizing_basis='mid' if mid else 'last_trade_or_reference',lot_size=lot)
    if mid:
        spread=asks[0]['price']-bids[0]['price']
        row.update(spread_vnd=spread,spread_bps=spread/mid*10000,spread_ticks=tick_distance(bids[0]['price'],asks[0]['price'],board))
    if finite(sizing) and sizing>0:
        requested=floor(notional/sizing/lot)*lot
        for side,levels in (('buy',asks),('sell',bids)):
            remaining=requested;value=0.0
            for level in levels:
                take=min(remaining,level['volume']);value+=take*level['price'];remaining-=take
                if remaining<=0:break
            filled=requested-remaining;vwap=value/filled if filled else None
            slip=((vwap-mid) if side=='buy' else (mid-vwap))/mid*10000 if vwap and mid else None
            row[side]={'requested_shares':requested,'filled_shares':filled,'unfilled_shares':remaining,
                'fill_ratio':filled/requested if requested else None,'vwap':vwap,'slip_bps':slip,
                'filled_value_vnd':value,'reference_notional_vnd':notional,'lot_size_assumed':lot,
                'sizing_price_vnd':sizing,'sizing_basis':row['sizing_basis'],
                'flag':'below_one_lot' if not requested else 'partial_visible_levels' if remaining else 'complete'}
        fills=[row[s]['fill_ratio'] for s in ('buy','sell')]
        row['fill_ratio']=min(fills) if all(finite(x) for x in fills) else None
    return row
