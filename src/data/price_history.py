"""Price freshness is independent from order-book validity."""
from src.data.ssi_feed import event_time, positive, numeric,reference_for_day


def price_fields(raw, captured_at):
    raw=raw or {};stamp=event_time(captured_at)
    day=event_time(raw.get('trading_date'))
    trade=event_time(raw.get('source_match_time_raw'))
    same_day=bool(stamp and day and day.date()==stamp.date())
    fresh=same_day and (trade is None or trade.date()==stamp.date())
    price=positive(raw.get('last_price_vnd')) if fresh else None
    volume=numeric(raw.get('volume_shares')) if fresh else None
    return {'last_price_vnd':price,'volume_shares':volume if volume is not None and volume>=0 else None,
            'reference_price_vnd':reference_for_day(raw,stamp.date().isoformat()) if same_day else None,
            'avg_match_price_vnd':positive(raw.get('avg_match_price_vnd')) if fresh else None,
            'trading_date':raw.get('trading_date'),'source_match_time_raw':raw.get('source_match_time_raw'),
            'price_available':price is not None}


def add_interval_volumes(points):
    """Never turn an unknown baseline, counter reset or collection gap into volume."""
    previous=None
    for p in points:
        stamp=event_time(p.get('received_at') or p.get('timestamp'))
        prior=event_time(previous.get('received_at') or previous.get('timestamp')) if previous else None
        phase=p.get('phase') or p.get('receiver_phase')
        max_gap=35 if phase in ('continuous_am','continuous_pm') else 90
        gap=bool(previous and (not stamp or not prior or stamp.date()!=prior.date()
                 or (stamp-prior).total_seconds()>max_gap or (stamp-prior).total_seconds()<=0
                 or phase!=(previous.get('phase') or previous.get('receiver_phase'))
                 or not previous.get('price_available') or not p.get('price_available')))
        p['gap_before']=bool(p.get('gap_before') or gap)
        current=numeric(p.get('volume_shares'));old=numeric(previous.get('volume_shares')) if previous else None
        p['interval_volume_shares']=current-old if previous and not p['gap_before'] and current is not None and old is not None and current>=old else None
        previous=p
    return points
