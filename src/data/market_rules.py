"""Cash-equity rules. Provider phase flags can restrict, never widen the clock.

Reference: SSI's current Quy định giao dịch cổ phiếu, checked 2026-11-11.
Holidays, suspensions and restricted instruments still require provider data.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

VN=ZoneInfo('Asia/Ho_Chi_Minh')
RULES_SOURCE='https://www.ssi.com.vn/khach-hang-ca-nhan/quy-dinh-giao-dich/quy-dinh-giao-dich-co-phieu'
BOARDS=('HOSE','HNX','UPCOM')


def resolve_universe(groups,requested):
    """Keep saved pilot scopes readable without relabelling them as full boards."""
    if requested in groups:return requested
    aliases={'HNX_PILOT':'HNX','UPCOM_PILOT':'UPCOM'}
    if requested in aliases and aliases[requested] in groups:return aliases[requested]
    if requested in ('HNX','UPCOM') and requested+'_PILOT' in groups:return requested+'_PILOT'
    return requested


def phase(stamp, board='HOSE'):
    if stamp is None or stamp.weekday()>=5 or board not in BOARDS:return 'closed'
    minute=stamp.astimezone(VN).hour*60+stamp.astimezone(VN).minute
    start=555 if board=='HOSE' else 540
    if board=='HOSE' and 540<=minute<555:return 'opening_auction'
    if start<=minute<690:return 'continuous_am'
    if 690<=minute<780:return 'lunch'
    end=900 if board=='UPCOM' else 870
    if 780<=minute<end:return 'continuous_pm'
    if board in ('HOSE','HNX') and 870<=minute<885:return 'closing_auction'
    if board=='HNX' and 885<=minute<900:return 'post_close'
    return 'closed'


def tick(price,board='HOSE'):
    if board!='HOSE':return 100
    return 10 if price<10000 else 50 if price<50000 else 100


def tick_distance(bid,ask,board='HOSE'):
    """Count actual price steps across band boundaries, without mid-band division."""
    if bid is None or ask is None or ask<bid:return None
    if board!='HOSE':return (ask-bid)/100
    total=0.0;start=bid
    for boundary,unit in ((10000,10),(50000,50),(float('inf'),100)):
        stop=min(ask,boundary)
        if stop>start:total+=(stop-start)/unit;start=stop
        if start>=ask:break
    return total


def session_finished(now,day,board='HOSE'):
    if not day:return False
    today=now.astimezone(VN).date().isoformat()
    return day<today or day==today and now.astimezone(VN).hour*60+now.astimezone(VN).minute>=905

