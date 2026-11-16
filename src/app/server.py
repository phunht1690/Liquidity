"""Loopback-only live dashboard. One collector supplies every dashboard view."""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from threading import Event, BoundedSemaphore, Thread
import webbrowser
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from src.data.live_analytics import build_live_state
from src.data.ssi_runtime import (snapshot_state, history_snapshots, refresh_snapshot,
                                     start_collector, stop_collector, collector_event, history_inventory, collector_status, collector_settings)
from src.data.ssi_feed import export_board
from src.data.chart_archive import read_chart_archive
from src.data.ohlc_history import read_price_history
from src.data.history_backfill import start_backfill,stop_backfill,backfill_status,prioritize_history
from src.data.ssi_feed import SSIAPIError
from src.data.product import build_product,export_product,safe_query
from src.data.data_coverage import project_coverage
from src.data.product_history import load_product_history
from src.data.ranking_intraday import enrich_ranking_intraday
from src.data.daily_summary import enrich_daily_statistics
from src.data.candle_statistics import enrich_candle_statistics
from src.data.archived_statistics import enrich_archived_statistics
from src.data.volume_context import enrich_volume_context
from src.data.market_activity import enrich_market_activity,stop_market_activity
from src.data.alert_history import attach_history
from src.data.trade_history import recent_trades,prepare_trade_index
from src.app.background import background_status,stop_requested

PROJECT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / 'static'
CONFIG = json.loads((PROJECT / 'config/config.json').read_text(encoding='utf-8'))
LOGGER = logging.getLogger('lopm')
QUERY_FIELDS = {'symbol', 'group', 'window', 'notional', 'lqs_profile', 'dataset_id','universe'}
EVENT_SLOTS = BoundedSemaphore(12)


def event_signature(event: dict) -> str:
    runtime=event['runtime']
    return json.dumps([event['revision'],runtime.get('status'),runtime.get('operation'),
        runtime.get('running'),runtime.get('stale_capture'),runtime.get('last_error_code'),
        runtime.get('next_poll_at'),runtime.get('now','')[:16]],sort_keys=True)


def _default_mode() -> str:
    return 'live'


def build_state(query: dict[str, list[str]]) -> dict[str, Any]:
    if set(query) - QUERY_FIELDS:
        raise ValueError('Bộ lọc không hỗ trợ; dashboard chỉ hiển thị dữ liệu hiện tại.')
    if any(len(values) != 1 for values in query.values()):
        raise ValueError('Bộ lọc lặp lại.')
    latest = snapshot_state()
    runtime = dict(latest.get('runtime') or {})
    runtime['latest_snapshot'] = latest
    runtime['history_inventory']=history_inventory()
    snapshots = history_snapshots(limit=CONFIG.get('ssi', {}).get('history_retention_snapshots', 1440))
    return build_live_state(query, snapshots, runtime, CONFIG)


def product_state(query):
    safe_query(query)
    latest=snapshot_state();runtime=dict(latest.get('runtime') or {})
    runtime.update(latest_snapshot=latest,history_inventory=history_inventory())
    snapshots,hydrate=load_product_history(query,latest,CONFIG,limit=CONFIG.get('ssi',{}).get('history_query_limit',10000))
    product=build_product(query,snapshots,runtime,CONFIG,analysis_loader=hydrate)
    product=enrich_daily_statistics(product)
    product=enrich_candle_statistics(product)
    product=enrich_archived_statistics(product)
    product=enrich_volume_context(product)
    product=enrich_ranking_intraday(product,latest)
    product=enrich_market_activity(product)
    product['recent_trades']=recent_trades(product['selected']['symbol'])
    policy=collector_settings(CONFIG)
    product['data_status'].update(history_retention_days=policy['history_retention_days'],
        raw_archive_retention_days=policy['raw_archive_retention_days'],raw_archive_budget_mb=policy['raw_archive_max_mb'],
        price_backfill=backfill_status(),background=background_status())
    prioritize_history(product['selected']['symbol'])
    return attach_history(product,retention_days=policy['history_retention_days'])


def data_coverage_state(query):
    """Read the shared SSI snapshots and existing caches, never enqueue SSI calls."""
    if set(query)-{'universe'} or any(len(values)!=1 for values in query.values()):
        raise ValueError('Độ phủ chỉ nhận bộ chọn phạm vi.')
    filters={**query,'group':['all'],'sort':['symbol']}
    latest=snapshot_state()
    if latest.get('source')!='ssi_fastconnect' or not latest.get('captured_at'):
        raise FileNotFoundError('ssi_not_ready')
    runtime=dict(latest.get('runtime') or {})
    runtime.update(latest_snapshot=latest,history_inventory=history_inventory())
    snapshots,hydrate=load_product_history(filters,latest,CONFIG,limit=CONFIG.get('ssi',{}).get('history_query_limit',10000))
    product=build_product(filters,snapshots,runtime,CONFIG,analysis_loader=hydrate)
    product=enrich_daily_statistics(product,request=False)
    product=enrich_candle_statistics(product)
    product=enrich_archived_statistics(product)
    policy=collector_settings(CONFIG)
    product['data_status'].update(history_retention_days=policy['history_retention_days'],
        raw_archive_retention_days=policy['raw_archive_retention_days'],raw_archive_budget_mb=policy['raw_archive_max_mb'],
        price_backfill=backfill_status(),background=background_status())
    return project_coverage(product)


def export_csv(state: dict[str, Any]) -> bytes:
    """One source, calculation basis and immutable observation ID per export."""
    stream = io.StringIO(newline='')
    metadata_fields = ['export_kind', 'source', 'universe','dataset_id', 'config_version', 'session_id',
        'asof_timestamp', 'timestamp_basis', 'notional_vnd', 'applied_lqs_profile', 'scope',
        'reference_count', 'reference_lqs_count', 'visible_count', 'valid_book_count', 'valid_lqs_count',
        'incomplete_fill_penalty_bps']
    row_fields = ['symbol', 'group', 'timestamp', 'exchange_time', 'received_at', 'quality',
        'quality_flags', 'analytics_flags', 'last_price_vnd', 'trade_price', 'lqs', 'lqs_status',
        'category', 'spread_bps', 'spread_ticks', 'depth_min_vnd', 'obi_w', 'weighted_mid',
        'weighted_mid_dev_bps', 'ofi_l1', 'ofi_level_1', 'ofi_level_2', 'ofi_level_3', 'ofi_3',
        'ofi_normalized', 'ofi_persistence', 'ofi_persistence_count', 'ofi_interval_seconds',
        'ofi_status', 'amihud_5m', 'two_sided_ratio', 'execution_cost_bps', 'turnover_basis',
        'source_match_time_raw', 'source_book_time_raw']
    execution_fields = [f'{side}_{key}' for side in ('buy','sell') for key in ('fill_ratio','vwap','slip_bps','single_order_eligible')]
    writer = csv.DictWriter(stream, metadata_fields + row_fields + execution_fields, extrasaction='ignore')
    writer.writeheader()
    coverage = state.get('coverage', {})
    for row in state['ranking']:
        metadata = {key:state.get(key) for key in ('source','universe','dataset_id','config_version','session_id','notional_vnd','applied_lqs_profile')}
        metadata.update({key:coverage.get(key) for key in ('reference_count','reference_lqs_count','visible_count','valid_book_count','valid_lqs_count')})
        metadata.update(export_kind='liquidity_ranking', asof_timestamp=state.get('updated_at'),
            timestamp_basis='received_at', scope=coverage.get('scope_label'),
            incomplete_fill_penalty_bps=state['methodology'].get('execution_cost_penalty_bps'))
        execution = {f'{side}_{key}':(row.get(side) or {}).get(key) for side in ('buy','sell')
                     for key in ('fill_ratio','vwap','slip_bps','single_order_eligible')}
        flow = {f'ofi_level_{i+1}':v for i,v in enumerate(row.get('ofi_levels') or [None]*3)}
        flags = {key:'|'.join(row.get(key) or []) for key in ('quality_flags','analytics_flags')}
        writer.writerow({**row, **metadata, **execution, **flow, **flags})
    return stream.getvalue().encode('utf-8-sig')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, message: str, *args: Any) -> None:
        LOGGER.debug('HTTP %s', str(args[1]) if len(args)>1 else 'request')

    def _send(self, status: int, body: bytes, content_type: str, attachment: str | None = None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if attachment:self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any):
        self._send(status, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8'), 'application/json; charset=utf-8')

    def _events(self):
        """Push local cache notifications; never calls the remote provider."""
        if not EVENT_SLOTS.acquire(blocking=False):
            self._json(503,{'error':'Đã đủ kết nối thông báo; giao diện dùng đồng bộ định kỳ.'})
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Accel-Buffering','no')
            self.end_headers()
            previous=None;heartbeat=0
            while not self.server.shutdown_event.is_set():
                event=collector_event();signature=event_signature(event)
                if signature!=previous:
                    self.wfile.write(('event: update\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode('utf-8'))
                    self.wfile.flush();previous=signature;heartbeat=0
                else:
                    heartbeat+=1
                    if heartbeat>=30:
                        self.wfile.write(b': keepalive\n\n');self.wfile.flush();heartbeat=0
                self.server.shutdown_event.wait(.5)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError):pass
        finally:EVENT_SLOTS.release()

    def do_POST(self):
        if urlsplit(self.path).path != '/api/ssi/refresh':
            self._json(404, {'error':'Không tìm thấy tài nguyên'})
            return
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        if host not in allowed or (origin and origin != f'http://{host}') or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self._json(403, {'error':'Yêu cầu phải đến từ dashboard cục bộ'})
            return
        if self.headers.get('Content-Length','0') != '0' or self.headers.get('Transfer-Encoding'):
            self._json(400, {'error':'Yêu cầu không nhận nội dung hoặc thông tin xác thực'})
            return
        status, payload = refresh_snapshot()
        self._json(status, payload)

    def do_GET(self):
        path = urlsplit(self.path)
        try:
            if path.path == '/api/health':
                self._json(200, {'status':'ok','app':'lopm_vn30','mode':'live','source':'ssi_fastconnect',
                    'auto_update':True,'transport':'websocket','replay_available':True,
                    'replay_scope':'chart_only','global_replay_available':False,
                    'chart_replay_available':True,
                    'ui_transport':'server_sent_events','collector':collector_event()['runtime'],
                    'ssi_live_available':collector_status().get('auth',{}).get('websocket_status')=='connected','provider':'ssi_fastconnect',
                    'poll_seconds':CONFIG.get('ssi',{}).get('live_poll_seconds',10),
                    'default_notional_vnd':CONFIG.get('notional_vnd',1e9),
                    'price_backfill':backfill_status(),
                    'background':background_status(),
                    'storage_policy':{k:v for k,v in collector_settings(CONFIG).items() if k in ('history_retention_days','raw_archive_retention_days','raw_archive_max_mb')}})
            elif path.path == '/api/events':
                self._events()
            elif path.path == '/api/state':
                self._json(410, {'error':'API nghiên cứu cũ đã ngừng phục vụ. Dùng /api/product.'})
            elif path.path == '/api/product':
                self._json(200,product_state(parse_qs(path.query,keep_blank_values=True)))
            elif path.path == '/api/data-coverage':
                self._json(200,data_coverage_state(parse_qs(path.query,keep_blank_values=True)))
            elif path.path == '/api/product/export.csv':
                query=parse_qs(path.query,keep_blank_values=True);subset=query.pop('symbols',None);state=product_state(query)
                expected=query.get('dataset_id',[None])[0]
                if expected and expected!=state['dataset_id']:
                    self._json(409,{'error':'Dữ liệu vừa đổi. Chờ màn hình cập nhật rồi xuất lại.'});return
                if subset is not None:
                    if len(subset)!=1 or len(subset[0])>16000:raise ValueError('Bộ lọc mã không hợp lệ')
                    requested=set(subset[0].split(','));allowed={r['symbol'] for r in state['ranking']}
                    if not requested or not requested<=allowed:raise ValueError('Mã nằm ngoài phạm vi đang chọn')
                    state={**state,'ranking':[r for r in state['ranking'] if r['symbol'] in requested]}
                self._send(200,export_product(state),'text/csv; charset=utf-8','LOPM_thanh_khoan_SSI.csv')
            elif path.path == '/api/chart-cache':
                self._json(200,read_chart_archive(parse_qs(path.query,keep_blank_values=True),CONFIG))
            elif path.path == '/api/price-history':
                try:self._json(200,read_price_history(parse_qs(path.query,keep_blank_values=True)))
                except SSIAPIError as exc:
                    self._json(503,{'source':'ssi_fastconnect_ohlc','bars':[],'status':'unavailable',
                                    'retry_after':max(30,exc.retry_after or 30)})
            elif path.path == '/api/export.csv':
                self._json(410, {'error':'CSV nghiên cứu cũ đã ngừng phục vụ. Dùng /api/product/export.csv.'})
            elif path.path in ('/api/ssi/state','/api/ssi/export.csv'):
                snapshot = snapshot_state()
                if path.path.endswith('.csv'):
                    expected = parse_qs(path.query).get('dataset_id',[None])[0]
                    if expected and expected != snapshot['dataset_id']:
                        self._json(409, {'error':'Dữ liệu vừa cập nhật. Hãy đồng bộ màn hình.'})
                        return
                    self._send(200, export_board(snapshot),'text/csv; charset=utf-8','LOPM_VN30_book_live.csv')
                else:self._json(200, snapshot)
            elif path.path in ('/demo','/vnstock','/vnstock.html'):
                self.send_response(303)
                self.send_header('Location','/')
                self.send_header('Content-Length','0')
                self.end_headers()
            else:
                relative = 'index.html' if path.path == '/' else path.path.lstrip('/')
                if relative in ('vnstock.js','vnstock.css'):
                    self._json(404, {'error':'Tài nguyên cũ đã được thay bằng dashboard tự cập nhật'})
                    return
                target = (STATIC / relative).resolve()
                if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
                    self._json(404, {'error':'Không tìm thấy tài nguyên'})
                    return
                mime = {'.html':'text/html','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml',
                        '.woff2':'font/woff2','.json':'application/json','.jpg':'image/jpeg','.jpeg':'image/jpeg',
                        '.png':'image/png','.webp':'image/webp','.avif':'image/avif','.gif':'image/gif','.bmp':'image/bmp'}.get(target.suffix.lower(),'application/octet-stream')
                self._send(200, target.read_bytes(), mime + ('; charset=utf-8' if target.suffix in ('.html','.css','.js','.svg') else ''))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except FileNotFoundError:
            runtime=collector_status()
            self._json(202, {'mode':'pending','source':'ssi_fastconnect','error':runtime.get('last_error') or 'Đang kết nối SSI và thu bản đầu tiên. Màn hình sẽ tự thử lại.','runtime':runtime})
        except (ValueError, TypeError):
            self._json(400, {'error':'Chưa có dữ liệu phù hợp hoặc bộ lọc không hợp lệ.'})
        except Exception:
            # No exception payloads: SDK errors may include remote request details.
            LOGGER.error('Không xử lý được dữ liệu dashboard')
            self._json(503, {'error':'Chưa đọc được dữ liệu SSI FastConnect. Dashboard sẽ tự thử lại.'})


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='LOPM VN30 — tự cập nhật SSI FastConnect, chỉ đọc')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--env-file',type=Path,default=PROJECT/'.env')
    parser.add_argument('--open-browser',action='store_true')
    parser.add_argument('--managed-token',default=None,help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if os.environ.get('LOPM_BACKGROUND')=='1':
        directory=PROJECT/'data/logs';directory.mkdir(parents=True,exist_ok=True)
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
            handlers=[RotatingFileHandler(directory/'server.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')])
    else:logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.shutdown_event=Event()
    if args.managed_token:
        def managed_stop():
            while not server.shutdown_event.wait(.5):
                if stop_requested(args.managed_token):server.shutdown();return
        Thread(target=managed_stop,name='lopm-managed-stop',daemon=True).start()
    start_collector(CONFIG,env_file=args.env_file)
    start_backfill(CONFIG,env_file=args.env_file)
    Thread(target=prepare_trade_index,name='ssi-trade-index',daemon=True).start()
    print(f'LOPM SSI FastConnect: http://127.0.0.1:{args.port}',flush=True)
    print('Tự lấy bảng giá; phát lại cache riêng trong biểu đồ. Ctrl+C để dừng.',flush=True)
    if args.open_browser:webbrowser.open(f'http://127.0.0.1:{args.port}/',new=2)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.shutdown_event.set()
        stop_market_activity()
        stop_backfill()
        stop_collector()
        server.server_close()


if __name__ == '__main__':main()
