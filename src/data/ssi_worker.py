"""Persistent SDK worker. All public output goes to cache/status, never secrets."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
from threading import Event, Thread
import time

from src.data.ssi_feed import SSISession, PROJECT, VN, load_snapshot
from src.data.ssi_runtime import (STATUS, CONTROL, collector_settings, poll_delay,
    store_snapshot, write_json_atomic)


def error_category(exc: BaseException) -> str:
    """Inspect only in memory; never expose SDK error strings, URLs or headers."""
    code=str(getattr(exc,'code','')).lower()
    if code in ERROR_MESSAGES:return code
    name=type(exc).__name__.lower()
    message=str(exc).lower()
    if '429' in message or 'rate' in code or 'quota' in code or 'rate' in name or 'quota' in name or message=='rate_limited':
        return 'rate_limited'
    if 'challenge' in name or 'challenge' in code or 'blocked' in code:
        return 'source_verification_required'
    if message in ('missing_key','key_not_accepted','auth_unavailable','unsupported_version','empty_board','unexpected_membership_count'):
        return message
    return 'source_unavailable'


def retry_after_seconds(exc: BaseException) -> float | None:
    try:
        direct=getattr(exc,'retry_after',None)
        if isinstance(direct,(int,float)) and 0<direct<86400:return direct
        response=getattr(exc,'response',None)
        value=getattr(response,'headers',{}).get('Retry-After')
        seconds=float(value)
        return seconds if 0<seconds<86400 else None
    except (TypeError,ValueError,AttributeError):return None


def backoff_seconds(failures: int, settings: dict, category: str, retry_after: float | None = None) -> float:
    delay=min(settings['max_backoff_seconds'],settings['live_poll_seconds']*2**min(max(1,failures),8))
    if category in ('market_access_denied','authentication_failed','missing_credentials'):
        delay=max(300,delay)
    if category in ('rate_limited','source_verification_required'):
        delay=max(60,delay)
    return max(delay,retry_after or 0)


def remaining_poll_delay(settings: dict, requested_monotonic: float, now_monotonic=None) -> float:
    """Target request-start cadence; no extra full sleep after a slow request."""
    now=time.monotonic() if now_monotonic is None else now_monotonic
    return max(0,requested_monotonic+poll_delay(settings)-now)


ERROR_MESSAGES={
    'market_access_denied':'Đăng nhập SSI thành công nhưng API thị trường trả 401/403. Kiểm tra quyền Market Data trên SSI Developer Portal; hệ thống đang tự thử lại.',
    'missing_credentials':'Thiếu SSI_API_KEY / SSI_API_SECRET trong .env.',
    'authentication_failed':'SSI không chấp nhận thông tin đăng nhập. Kiểm tra .env cục bộ.',
    'auth_unavailable':'Chưa kết nối được máy chủ đăng nhập SSI; đang thử lại.',
    'rate_limited':'SSI đang giới hạn lượt gọi; bộ thu đã giãn nhịp.',
    'unexpected_membership_count':'Danh sách VN30 từ SSI chưa đủ hoặc không đúng cấu trúc; chưa xuất bản dữ liệu.',
    'empty_board':'SSI chưa trả bảng giá có giá hợp lệ.',
    'source_unavailable':'Chưa nhận được dữ liệu SSI; bộ thu giữ riêng nguồn SSI và tự thử lại.',
    'unknown_market_status':'Chưa xác định được trạng thái phiên từ SSI.'}



def run_worker(env_file: Path, settings: dict, worker_token: str) -> None:
    stop,wake=Event(),Event()
    def commands():
        serial=-1
        started=time.monotonic()
        while not stop.wait(.25):
            try:
                control=json.loads(CONTROL.read_text(encoding='utf-8'))
                if control.get('worker_token')!=worker_token:
                    stop.set();wake.set();return
                heartbeat=control.get('heartbeat_monotonic')
                if not isinstance(heartbeat,(int,float)) or time.monotonic()-heartbeat>15:
                    stop.set();wake.set();return
                if control.get('serial')!=serial:
                    serial=control.get('serial')
                    if control.get('command')=='stop':stop.set();wake.set();return
                    if control.get('command')=='refresh':wake.set()
            except (OSError,ValueError):
                if time.monotonic()-started>15:
                    stop.set();wake.set();return
    Thread(target=commands,name='collector-commands',daemon=True).start()
    state={'worker_token':worker_token,'pid':os.getpid(),'status':'starting',
        'failure_count':0,'poll_attempts':0,'success_count':0,'last_error':None,
        'last_success_at':None,'last_attempt_at':None,'next_poll_at':None,
        'last_error_code':None,'daily_history_status':'not_used_by_live_dashboard',
        'operation_timings_seconds':{}}
    session=None
    last_attempt=0.0
    started_at=time.monotonic()
    operation_started=None
    def status(name,**extra):
        state.update(status=name,updated_at=datetime.now(VN).isoformat(),**extra)
        write_json_atomic(STATUS,state)
    def fetching(operation):
        nonlocal operation_started,last_attempt
        now=time.monotonic()
        if operation_started is not None and state.get('operation'):
            state['operation_timings_seconds'][state['operation']]=round(now-operation_started,3)
        operation_started=now
        if operation=='board':last_attempt=now
        status('fetching',operation=operation,attempt_started_monotonic=time.monotonic())
    def waiting(delay):
        deadline=time.monotonic()+delay
        while not stop.is_set():
            if not state.get('failure_count'):
                # A 5-minute off-hours wait must not postpone the first poll
                # after 09:00 or the 13:00 reopening.
                deadline=min(deadline,last_attempt+poll_delay(settings))
            remaining=deadline-time.monotonic()
            if remaining<=0:return
            if wake.wait(min(remaining,1)):
                wake.clear()
                # Manual requests coalesce and cannot bypass the minimum cadence
                # or provider backoff. Parent handles a second request too.
                if state.get('failure_count'):
                    continue
                minimum=settings['live_poll_seconds']-(time.monotonic()-last_attempt)
                if minimum>0:
                    deadline=min(deadline,time.monotonic()+minimum)
                    continue
                return
    status('starting')
    while not stop.is_set():
        try:
            last_attempt=time.monotonic()
            state['last_attempt_at']=datetime.now(VN).isoformat()
            state['poll_attempts']+=1
            fetching('connect' if session is None else 'board')
            if session is None:
                session=SSISession(env_file,progress=fetching)
                session.universe_group=settings.get('universe_group','VN30')
                session.pilot_symbols_per_board=settings.get('pilot_symbols_per_board',15)
                session.raw_archive_max_mb=settings.get('raw_archive_max_mb',2048)
                session.raw_archive_retention_days=settings.get('raw_archive_retention_days',7)
            if stop.is_set():break
            payload=session.poll()
            if stop.is_set():break
            store_snapshot(payload,retention=settings['history_retention_snapshots'],retention_days=settings['history_retention_days'],compact=True)
            if stop.is_set():break
            state.update(auth=session.public_auth() if hasattr(session,'public_auth') else {})
            state['success_count']+=1
            state.update(failure_count=0,last_error=None,last_error_code=None,last_http_status=200,last_success_at=payload['captured_at'])
            if state['success_count']==1:state['startup_seconds']=round(time.monotonic()-started_at,3)
            state['last_request_seconds']=round((datetime.fromisoformat(payload.get('captured_at'))-
                datetime.fromisoformat(payload.get('request_started_at',payload['captured_at']))).total_seconds(),3)
            if operation_started is not None:
                state['operation_timings_seconds']['board']=round(time.monotonic()-operation_started,3)
            operation_started=None
            # The live dashboard does not consume daily candles. Never block
            # the next quote on an unrelated optional history request.
            delay=remaining_poll_delay(settings,last_attempt)
            status('waiting',operation=None,next_poll_at=(datetime.now(VN)+timedelta(seconds=delay)).isoformat(),
                attempt_started_monotonic=None,backoff_seconds=0)
        except (Exception,SystemExit) as exc:
            state.update(auth=session.public_auth() if session and hasattr(session,'public_auth') else {})
            state['last_http_status']=getattr(exc,'http_status',None)
            category=error_category(exc)
            state['failure_count']+=1
            delay=backoff_seconds(state['failure_count'],settings,category,retry_after_seconds(exc))
            state.update(last_error_code=category,last_error=ERROR_MESSAGES.get(category,ERROR_MESSAGES['source_unavailable']))
            if category in ('missing_credentials','authentication_failed','auth_unavailable'):
                if session and hasattr(session,'close'):session.close()
                session=None
            status('backoff',operation=None,next_poll_at=(datetime.now(VN)+timedelta(seconds=delay)).isoformat(),
                attempt_started_monotonic=None,backoff_seconds=delay)
        waiting(delay)
    if session and hasattr(session,'close'):session.close()
    status('stopped',operation=None,next_poll_at=None,attempt_started_monotonic=None)


def main():
    parser=argparse.ArgumentParser(description='LOPM automatic SSI FastConnect worker')
    parser.add_argument('--env-file',type=Path,default=PROJECT/'.env')
    args=parser.parse_args()
    try:
        first=json.loads(sys.stdin.readline())
        # SDKs may inspect/read stdin. No controller thread shares this stream,
        # and an unexpected interactive read receives EOF instead of hanging.
        sys.stdin=open(os.devnull,'r',encoding='utf-8')
        settings=collector_settings(first.get('settings'))
        token=str(first['worker_token'])
        if not token or len(token)>64:return 2
        run_worker(args.env_file,settings,token)
    except (Exception,SystemExit):
        # No traceback: third-party exceptions can include credential-bearing URLs.
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
