"""HTTP cục bộ cho LOPM simulated; không gọi SSI hoặc phát sinh giao dịch."""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import math
import sys
from hashlib import sha256
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import parse_qs, urlsplit

from src.data.quality import QualityTracker, session_phase
from src.data.schema import Quote
from src.data.simulated import SYMBOL_GROUPS, build_demo, metrics_at
from src.finance.microstructure import DEFAULT_OBI_WEIGHTS
from src.finance.scoring import DEFAULT_WEIGHTS, score_cross_section
from src.data.ssi_feed import export_board
from src.data.ssi_runtime import snapshot_state, refresh_snapshot

STATIC = Path(__file__).resolve().parent / "static"
PROJECT = Path(__file__).resolve().parents[2]
DISCLAIMER = "Công cụ phân tích học thuật, không phải khuyến nghị đầu tư."
LOGGER = logging.getLogger("lopm")
CONFIG = json.loads(Path(__file__).with_name("config_fixture.json").read_text(encoding="utf-8"))


def _default_mode() -> str:
    # Only read the nonsecret mode here; the isolated collector loads the API key.
    try:
        from dotenv import dotenv_values
        mode = dotenv_values(PROJECT / '.env').get('LOPM_MODE')
    except ImportError:
        mode = None
    return 'vnstock' if (mode or CONFIG.get('mode')) == 'vnstock' else 'simulated'
DEMO = build_demo(seed=CONFIG.get("sample_seed", 20261026), frames=CONFIG.get("sample_frames", 120),
                  market=CONFIG.get("market"))
SYMBOLS = list(DEMO)
FRAME_COUNT = min(len(quotes) for quotes in DEMO.values())
SESSION_ID = "2026-10-26 (simulated)"
BASELINE = "simulated_demo — ngưỡng minh họa, chưa hiệu chỉnh từ dữ liệu thật"
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
COMPONENTS = {
    "spread_bps": ("Spread", "bps", "thấp tốt"),
    "depth_min_vnd": ("Độ sâu phía mỏng", "VNĐ", "cao tốt"),
    "execution_cost_bps": ("Chi phí và phạt thiếu fill", "bps", "thấp tốt"),
    "amihud_5m": ("Amihud 5 phút", "return/tỷ VNĐ", "thấp tốt"),
    "two_sided_ratio": ("Khả dụng hai phía", "tỷ lệ", "cao tốt"),
}
EXECUTION_COST_FORMULA = "(buy_slip_bps + sell_slip_bps)/2 + penalty_bps*(1-(buy_fill_ratio+sell_fill_ratio)/2)"
DATASET_ID = "simulated-" + sha256(json.dumps(
    {symbol: [quote.to_dict() if isinstance(quote, Quote) else None for quote in quotes] for symbol, quotes in DEMO.items()},
    sort_keys=True, ensure_ascii=False, separators=(",", ":"),
).encode("utf-8")).hexdigest()[:12]


def _config_version() -> str:
    """Chỉ băm cấu hình công khai; không đưa biến môi trường hoặc khóa vào provenance."""
    names = ("schema_version", "market", "lqs_weights", "obi_level_weights", "notional_vnd",
             "incomplete_fill_penalty_bps", "demo_alerts", "quality", "sample_seed", "sample_frames")
    names += ("lqs_profiles", "research")
    public = {name: CONFIG[name] for name in names if name in CONFIG}
    return sha256(json.dumps(public, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _applied_assumptions() -> dict[str, Any]:
    """Các giả định công khai thực sự truyền vào phép tính hiện tại."""
    market = CONFIG.get("market") or {}
    return {
        "lot_size": market.get("lot_size", 100),
        "tick_reference": market.get("tick_reference", "mid"),
        "obi_level_weights": list(CONFIG.get("obi_level_weights", DEFAULT_OBI_WEIGHTS)),
        "incomplete_fill_penalty_bps": CONFIG.get("incomplete_fill_penalty_bps", 100),
    }


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number(query: dict[str, list[str]], name: str, default: float, low: float, high: float,
            integer: bool = False) -> float:
    value = float(query.get(name, [str(default)])[0])
    if not math.isfinite(value) or not low <= value <= high or (integer and not value.is_integer()):
        raise ValueError(f"Giá trị {name} ngoài phạm vi")
    return value


def _thresholds() -> dict[str, Any]:
    return {"wide_spread_bps": 25.0, "thin_depth_vnd": 500_000_000,
            "pressure_obi": .5, "pressure_ofi_normalized": .1, "persistence_ratio": .6, "critical_fill_ratio": .5,
            **CONFIG.get("demo_alerts", {})}


def _lqs_profiles() -> list[dict[str, Any]]:
    configured = CONFIG.get("lqs_profiles", {})
    # Keep the existing baseline weight key authoritative for older public configs.
    return [{"id": key, "label": value["label"], "note": value["note"],
             "weights": CONFIG.get("lqs_weights", DEFAULT_WEIGHTS) if key == "baseline" else value["weights"]}
            for key, value in configured.items()]


def _profile_weights(profile: str) -> dict[str, float]:
    available = {item["id"]: item["weights"] for item in _lqs_profiles()}
    if profile not in available:
        raise ValueError("Kịch bản trọng số LQS không khả dụng")
    return dict(available[profile])


def _execution_value(row: dict[str, Any], side: str, name: str) -> Any:
    return (row.get(side) or {}).get(name)


def _worst_fill(row: dict[str, Any]) -> float | None:
    values = [_execution_value(row, side, "fill_ratio") for side in ("buy", "sell")]
    return min(values) if all(_finite(value) for value in values) else None


def _missing_metrics(symbol: str) -> dict[str, Any]:
    """Không gán thời gian của mã khác hoặc thời gian nhận cho quote không tồn tại."""
    return {"symbol": symbol, "group": SYMBOL_GROUPS.get(symbol, "Khác"), "source": "simulated",
            "timestamp": None, "exchange_time": None, "received_at": None,
            "quality": "missing_record", "quality_flags": ["missing_record"],
            "analytics_flags": ["missing_record"], "valid": False,
            "bids": [], "asks": [], "buy": None, "sell": None, "fill_ratio": None,
            **{key: None for key in ("mid", "spread_bps", "spread_ticks", "depth_bid_vnd",
                 "depth_ask_vnd", "depth_min_vnd", "obi1", "obi3", "obi_w", "weighted_mid",
                 "weighted_mid_dev_bps", "amihud_5m", "two_sided_ratio", "persistence", "obi_persistence",
                 "ofi_l1", "ofi_3", "ofi_normalized", "ofi_interval_seconds", "ofi_persistence")},
            "ofi_levels": [None, None, None], "ofi_status": "invalid_pair", "ofi_persistence_count": 0}


def _metrics(symbol: str, index: int, notional: float) -> dict[str, Any]:
    quotes = DEMO[symbol]
    quote = quotes[index] if index < len(quotes) else None
    if not isinstance(quote, Quote):
        return _missing_metrics(symbol)
    options = {"market": CONFIG.get("market"), "obi_level_weights": CONFIG.get("obi_level_weights"),
               "history_gap_seconds": CONFIG.get("quality", {}).get("history_gap_seconds", 90)}
    try:
        # Lịch sử thiếu được xử lý tại metrics_at; không vô hiệu hóa quote hiện tại hợp lệ.
        row = metrics_at(quotes, index, notional, _thresholds()["pressure_obi"], **options)
    except (AttributeError, ValueError, TypeError, ArithmeticError) as exc:
        LOGGER.warning("Không tính được mã %s: %s", symbol, type(exc).__name__)
        row = {**_missing_metrics(symbol), "quality": "invalid_record", "quality_flags": ["invalid_record"]}
    row["valid"] = row.get("quality") == "valid"
    row["fill_ratio"] = _worst_fill(row)
    row["timestamp"] = quote.exchange_time.isoformat()
    row["exchange_time"] = quote.exchange_time.isoformat()
    row["received_at"] = quote.received_at.isoformat()
    return row


def _alerts(rows: list[dict[str, Any]], timestamp: str | None) -> list[dict[str, Any]]:
    """Gộp điều kiện cùng mã tại thời điểm chọn; không giả làm nhật ký sự kiện."""
    thresholds = _thresholds()
    alerts = []
    for row in rows:
        conditions = []
        if not row["valid"]:
            conditions.append({"severity": "critical", "type": "Dữ liệu sổ lệnh không hợp lệ",
                "kind": "data_quality", "message": "Mã được loại khỏi phép tính: " + ", ".join(row.get("quality_flags") or [row.get("quality", "invalid")])})
        else:
            ratio = row.get("fill_ratio")
            if _finite(ratio) and ratio < 1:
                severity = "critical" if ratio < thresholds["critical_fill_ratio"] else "warning"
                buy = _execution_value(row, "buy", "fill_ratio")
                sell = _execution_value(row, "sell", "fill_ratio")
                conditions.append({"severity": severity, "type": "Thiếu thanh khoản cho quy mô N", "kind": "capacity",
                    "message": f"Ba mức hấp thụ mua {buy:.1%}, bán {sell:.1%}. Không ước lượng chi phí phần còn thiếu; mức độ dùng ngưỡng demo {thresholds['critical_fill_ratio']:.0%}."})
            elif _finite(row.get("depth_min_vnd")) and row["depth_min_vnd"] < thresholds["thin_depth_vnd"]:
                conditions.append({"severity": "warning", "type": "Độ sâu thấp (demo)", "kind": "depth",
                    "message": f"Độ sâu phía mỏng {row['depth_min_vnd']/1e9:.2f} tỷ đồng, dưới ngưỡng demo {thresholds['thin_depth_vnd']/1e9:.2f} tỷ."})
            if _finite(row.get("spread_bps")) and row["spread_bps"] > thresholds["wide_spread_bps"]:
                conditions.append({"severity": "warning", "type": "Spread rộng (demo)", "kind": "spread",
                    "message": f"Spread {row['spread_bps']:.2f} bps vượt ngưỡng minh họa {thresholds['wide_spread_bps']:.0f} bps; chưa phải cảnh báo robust z lịch sử."})
            if (_finite(row.get("ofi_normalized")) and _finite(row.get("ofi_persistence"))
                    and abs(row["ofi_normalized"]) > thresholds["pressure_ofi_normalized"]
                    and row["ofi_persistence"] >= thresholds["persistence_ratio"]):
                side = "mua" if row["ofi_normalized"] > 0 else "bán"
                conditions.append({"severity": "info", "type": "OFI cùng chiều (xấp xỉ demo)", "kind": "pressure",
                    "message": f"OFI₃ giữa snapshot {row['ofi_3']:+.0f} CP, chuẩn hóa {row['ofi_normalized']:+.2f}, persistence {row['ofi_persistence']:.0%} trên {row['ofi_persistence_count']} gia số: phía {side}. Ngưỡng chuẩn hóa {thresholds['pressure_ofi_normalized']:.2f} chỉ minh họa; không phải OFI sự kiện hoặc dự báo giá."})
        if conditions:
            conditions.sort(key=lambda item: SEVERITY_ORDER[item["severity"]])
            alerts.append({"symbol": row["symbol"], "timestamp": timestamp, "baseline": BASELINE,
                "severity": conditions[0]["severity"], "type": conditions[0]["type"],
                "message": " ".join(item["message"] for item in conditions),
                "conditions": conditions, "condition_count": len(conditions)})
    return sorted(alerts, key=lambda item: (SEVERITY_ORDER[item["severity"]], item["symbol"]))


def _explain_lqs(row: dict[str, Any], weights: dict[str, float]) -> None:
    ranks = row.get("component_percentiles") or {}
    row["lqs_explanation"] = [
        {"key": key, "label": label, "raw_value": row.get(key), "percentile": ranks.get(key),
         "weight": weights[key], "contribution": ranks[key] * weights[key] if key in ranks else None,
         "unit": unit, "direction": direction}
        for key, (label, unit, direction) in COMPONENTS.items()
    ]
    if row.get("lqs") is not None:
        row["lqs_reason"] = "Điểm phân vị tương đối trong rổ đủ năm thành phần tại quy mô N; không phải xác suất rủi ro tuyệt đối."
    elif not row["valid"]:
        row["lqs_reason"] = "Không tính LQS vì sổ lệnh không hợp lệ: " + ", ".join(row.get("quality_flags") or [])
    else:
        missing = [label for key, (label, _, _) in COMPONENTS.items() if not _finite(row.get(key))]
        row["lqs_reason"] = "Chưa đủ thành phần: " + ", ".join(missing) + ". Không tự bù dữ liệu hoặc tái chuẩn hóa trọng số."


def _quality_summary(index: int) -> dict[str, Any]:
    tracker = QualityTracker()
    gaps = []
    missing_records = 0
    gap_seconds = CONFIG.get("quality", {}).get("history_gap_seconds", 90)
    for symbol, quotes in DEMO.items():
        previous = None
        for position in range(index + 1):
            quote = quotes[position] if position < len(quotes) else None
            if not isinstance(quote, Quote):
                missing_records += 1
                continue
            tracker.inspect(quote)
            if previous is not None:
                duration = (quote.exchange_time - previous.exchange_time).total_seconds()
                if duration > gap_seconds:
                    gaps.append({"symbol": symbol, "from": previous.exchange_time.isoformat(),
                                 "to": quote.exchange_time.isoformat(), "seconds": duration})
            previous = quote
    return {"total_messages": tracker.total_messages, "missing_record_count": missing_records,
            "duplicate_count": tracker.duplicate_count,
            "late_count": tracker.late_count, "invalid_count": tracker.invalid_count,
            "gaps": len(gaps), "gap_details": gaps[:25], "real_sessions": 0, "source": "simulated",
            "stale_count": None, "note": "Bộ đếm tính trên fixture simulated đến khung chọn, không phải thống kê collector SSI; tuổi quote và stale thời gian thực không áp dụng."}


def _intraday_profile(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Observed medians only; clock buckets never borrow later snapshots."""
    periods = [(9 * 60 + 15, 9 * 60 + 30)] + [(start, start + 30) for start in range(9 * 60 + 30, 11 * 60 + 30, 30)]
    periods += [(start, start + 30) for start in range(13 * 60, 14 * 60 + 30, 30)]
    profile = []
    for start, end in periods:
        samples = []
        for row in rows:
            if not row["valid"] or not row.get("timestamp"):
                continue
            stamp = datetime.fromisoformat(row["timestamp"])
            minute = stamp.hour * 60 + stamp.minute
            if start <= minute < end:
                samples.append(row)
        label = lambda minute: f"{minute // 60:02d}:{minute % 60:02d}"
        result = {"bucket": f"{label(start)}–{label(end)}", "start": label(start), "end": label(end), "sample_count": len(samples)}
        for name in ("spread_bps", "depth_min_vnd"):
            values = [row[name] for row in samples if _finite(row.get(name))]
            result["median_" + name] = median(values) if values else None
        for side in ("buy", "sell"):
            for metric in ("slip_bps", "fill_ratio"):
                values = [_execution_value(row, side, metric) for row in samples]
                values = [value for value in values if _finite(value)]
                result[f"median_{side}_{metric}"] = median(values) if values else None
        profile.append(result)
    return profile


def _tick_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["spread_ticks"] for row in rows if row["valid"] and _finite(row.get("spread_ticks"))]
    one_tick = sum(abs(value - 1) < 1e-8 for value in values)
    return {"sample_count": len(values), "one_tick_count": one_tick,
            "one_tick_share": one_tick / len(values) if values else None,
            "note": "Chỉ snapshot simulated của mã chọn đến thời điểm Replay, không phải tỷ lệ VN30 thật; giả thuyết spread gần luôn một tick vẫn chưa kiểm chứng."}


def build_state(query: dict[str, list[str]]) -> dict[str, Any]:
    symbol = query.get("symbol", [SYMBOLS[0]])[0].upper()
    if symbol not in DEMO:
        raise ValueError("Mã không có trong rổ demo")
    index = int(_number(query, "index", min(60, FRAME_COUNT - 1), 0, FRAME_COUNT - 1, True))
    notional = _number(query, "notional", CONFIG.get("notional_vnd", 1e9), 1e8, 5e9)
    window = min(FRAME_COUNT, int(_number(query, "window", min(30, FRAME_COUNT), 1, 10000, True)))
    group = query.get("group", ["all"])[0] or "all"
    if group not in {"all", *SYMBOL_GROUPS.values()}:
        raise ValueError("Nhóm không có trong rổ demo")
    session = query.get("session", [SESSION_ID])[0]
    if session not in ("", "all", SESSION_ID):
        raise ValueError("Phiên dữ liệu không khả dụng")
    lqs_profile = query.get("lqs_profile", ["baseline"])[0]
    weights = _profile_weights(lqs_profile)
    all_rows = [_metrics(key, index, notional) for key in SYMBOLS]
    # Phân vị tham chiếu toàn rổ hợp lệ; bộ lọc chỉ thay đổi tập hiển thị.
    scored = score_cross_section(all_rows, weights=weights,
                                 incomplete_fill_penalty_bps=CONFIG.get("incomplete_fill_penalty_bps", 100))
    selected = next(row.copy() for row in scored if row["symbol"] == symbol)
    quote = DEMO[symbol][index] if index < len(DEMO[symbol]) else None
    selected.update(bids=[level.to_dict() for level in quote.bids] if isinstance(quote, Quote) else [],
                    asks=[level.to_dict() for level in quote.asks] if isinstance(quote, Quote) else [], baseline=BASELINE)
    _explain_lqs(selected, weights)
    visible = [row for row in scored if group in ("all", row["group"])]
    asof_row = selected if selected.get("timestamp") else next((row for row in scored if row.get("timestamp")), None)
    timestamp = asof_row["timestamp"] if asof_row else None
    alerts = _alerts(visible, timestamp)
    observed = [_metrics(symbol, position, notional) for position in range(index + 1)]
    history = observed[max(0, index - window + 1):]
    cost_curve = []
    for value in (100e6, 250e6, 500e6, 750e6, 1e9, 1.5e9, 2e9, 3e9, 4e9, 5e9):
        point = _metrics(symbol, index, value)
        cost_curve.append({"notional": value, "buy_slip_bps": _execution_value(point, "buy", "slip_bps"),
                           "sell_slip_bps": _execution_value(point, "sell", "slip_bps"),
                           "buy_fill_ratio": _execution_value(point, "buy", "fill_ratio"),
                           "sell_fill_ratio": _execution_value(point, "sell", "fill_ratio"),
                           "fill_ratio": point["fill_ratio"]})
    valid_books = [row for row in visible if row["valid"]]
    valid_lqs = [row for row in visible if row.get("lqs") is not None]
    pressures = [row for row in valid_books if _finite(row.get("ofi_normalized"))]
    spreads = [row["spread_bps"] for row in valid_books if _finite(row.get("spread_bps"))]
    coverage = {"visible_count": len(visible), "valid_book_count": len(valid_books),
        "valid_lqs_count": len(valid_lqs), "reference_count": len(scored),
        "reference_lqs_count": sum(row.get("lqs") is not None for row in scored),
        "scope_label": "Toàn bộ rổ demo" if group == "all" else group,
        "invalid_symbols": [{"symbol": row["symbol"], "flags": row.get("quality_flags") or [row["quality"]]}
                            for row in visible if not row["valid"]], "quote_age_seconds": None}
    return {"mode": "simulated", "source": "simulated", "disclaimer": DISCLAIMER,
        "timezone": "Asia/Ho_Chi_Minh", "updated_at": timestamp, "notional_vnd": notional,
        "asof_source_symbol": asof_row["symbol"] if asof_row else None,
        "dataset_id": DATASET_ID, "config_version": _config_version(), "session_id": SESSION_ID,
        "applied_lqs_profile": lqs_profile,
        "symbols": [{"symbol": key, "group": SYMBOL_GROUPS[key]} for key in SYMBOLS],
        "sessions": [SESSION_ID], "phase_code": session_phase(quote) if isinstance(quote, Quote) else None,
        "session_phase": ({"continuous_am":"Liên tục sáng", "continuous_pm":"Liên tục chiều", "opening_auction":"Định kỳ mở cửa", "closing_auction":"Định kỳ đóng cửa", "lunch":"Nghỉ trưa", "halted":"Tạm ngừng", "closed":"Đóng cửa"}.get(session_phase(quote), "Chưa có trạng thái") if isinstance(quote, Quote) else "Chưa có trạng thái") + " — mô phỏng",
        "frame_index": index, "frame_count": FRAME_COUNT,
        "connection": {"status": "simulated", "lag_ms": None, "live_available": False},
        "coverage": coverage,
        "kpis": {"alert_count": len(alerts), "median_spread_bps": median(spreads) if spreads else None,
                 "high_risk_count": sum(row["lqs"] < 25 for row in valid_lqs) if valid_lqs else None,
                 "valid_lqs_count": len(valid_lqs), "valid_book_count": len(valid_books),
                 "strongest_pressure": max(pressures, key=lambda row: abs(row["ofi_normalized"]), default=None)},
        "ranking": sorted(visible, key=lambda row: row.get("lqs") if row.get("lqs") is not None else -1, reverse=True),
        "selected": selected, "history": history, "cost_curve": cost_curve, "alerts": alerts,
        "intraday_profile": _intraday_profile(observed), "tick_diagnostics": _tick_diagnostics(observed),
        "quality": _quality_summary(index),
        "methodology": {"source": "simulated", "seed": CONFIG.get("sample_seed", 20261026),
            "lqs_weights": weights, "lqs_profiles": _lqs_profiles(), "applied_lqs_profile": lqs_profile,
            "lqs_profile_note": "Kịch bản được chọn thủ công để đối chiếu độ nhạy, chưa hiệu chuẩn hoặc chứng minh tốt hơn trên VN30 thật. Mặc định giữ Spread 25%; không tự giảm trọng số theo fixture.",
            "baseline": BASELINE,
            "execution_cost_penalty_bps": CONFIG.get("incomplete_fill_penalty_bps", 100),
            "execution_cost_formula": EXECUTION_COST_FORMULA,
            "execution_cost_note": "Chi phí hiệu chỉnh để xếp hạng LQS gồm trung bình slippage của phần hấp thụ và phạt thiếu fill. Đây là giả định xếp hạng, không phải VWAP hoặc chi phí thực thi của toàn lệnh; hệ số phạt cần kiểm tra độ nhạy trên dữ liệu thật.",
            "applied_assumptions": _applied_assumptions(),
            "lqs_note": "LQS là phân vị trong rổ đủ năm thành phần tại quy mô N; thiếu thành phần thì để trống. Điểm thấp tương đối không phải xác suất rủi ro tuyệt đối.",
            "baseline_note": "Ngưỡng UI demo, chưa học P95/P99 hoặc median/MAD; cảnh báo chỉ thuộc khung đang chọn, chưa phải nhật ký sự kiện.",
            "scope": f"{len(SYMBOLS)} mã minh họa hướng đến VN30, cần xác nhận thành phần khi thu thật; 0 phiên SSI.",
            "history_gap_seconds": CONFIG.get("quality", {}).get("history_gap_seconds", 90),
            "sample_interval_seconds": 60,
            "pressure_note": "OFI L1 và vector ba mức dùng công thức giá/khối lượng giữa hai snapshot liên tiếp. OFI₃ là tổng ba phần tử để minh họa, không phải hệ số MLOFI đã ước lượng. Chuẩn hóa chia trung bình tổng khối lượng sáu mức của hai snapshot; chỉ là thước đo nội bộ. Mỗi snapshot cách 60 giây nên mất các sự kiện bên trong; không coi đây là OFI sự kiện. Persistence tính tối đa năm gia số hợp lệ liên tiếp, tối thiểu ba; số 0 nằm trong mẫu số nhưng trung tính, gia số hiện tại bằng 0 thì không có hướng.",
            "profile_note": "Median theo khung giờ chỉ dùng snapshot hợp lệ của mã chọn, N hiện tại và dữ liệu đến Replay; ô trống chưa có quan sát. Khung đầu 09:15–09:30 bị cắt theo giờ liên tục. Fixture chỉ có buổi sáng; chưa so sánh mở lại buổi chiều hoặc kết luận khung giờ giao dịch tốt hơn.",
            "effective_spread": {"status": "unavailable", "trade_count": 0,
                "note": "Chưa có sự kiện giao dịch ghép với mid ngay trước khớp. Giá khớp cuối snapshot dùng cho Amihud không đủ điều kiện ghép. Hàm 2·|P−mid_trước|/mid_trước·10⁴ đã có; Lee–Ready chưa triển khai/xác minh."},
            "resilience": {"status": "planned", "note": "Tùy chọn: cần sự kiện ăn sổ và baseline hồi phục riêng. Chưa đo thời gian hồi phục từ fixture phút."},
            "forecast": {"status": "unavailable", "horizons_seconds": [5, 15, 30], "control_seconds": 60,
                "note": "Thiết kế kiểm định theo thay đổi mid kế tiếp và chân trời 5/15/30 giây; 60 giây là đối chứng. Snapshot phút không đủ dữ liệu cho kiểm định này; không nội suy hoặc báo độ chính xác dự báo."},
            "limits": "Chỉ ba mức; VWAP và slippage của phần được hấp thụ, không ngoại suy phần thiếu; chưa tính phí/thuế/độ trễ/tác động thị trường."}}


def export_csv(state: dict[str, Any]) -> bytes:
    """Cùng nguồn và trạng thái áp dụng với dashboard, có provenance cho từng dòng."""
    output = io.StringIO(newline="")
    fields = ["export_kind", "source", "timestamp", "exchange_time", "received_at", "asof_timestamp", "dataset_id", "config_version", "session_id", "frame_index",
              "notional_vnd", "applied_lqs_profile", "scope", "reference_count", "reference_lqs_count", "visible_count",
              "valid_book_count", "valid_lqs_count", "symbol", "group", "quality", "lqs", "category",
              "spread_bps", "spread_ticks", "depth_min_vnd", "obi_w", "weighted_mid", "weighted_mid_dev_bps",
              "ofi_l1", "ofi_level_1", "ofi_level_2", "ofi_level_3", "ofi_3", "ofi_normalized", "ofi_persistence", "ofi_persistence_count", "ofi_interval_seconds", "ofi_status", "amihud_5m", "two_sided_ratio",
              "execution_cost_bps", "incomplete_fill_penalty_bps",
              "buy_single_order_eligible", "sell_single_order_eligible", "buy_fill_ratio", "sell_fill_ratio", "buy_vwap", "sell_vwap", "buy_slip_bps", "sell_slip_bps"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    coverage = state["coverage"]
    for row in state["ranking"]:
        metadata = {name: state[name] for name in ("source", "dataset_id", "config_version", "session_id", "frame_index", "notional_vnd", "applied_lqs_profile")}
        metadata.update({name: coverage[name] for name in ("reference_count", "reference_lqs_count", "visible_count", "valid_book_count", "valid_lqs_count")})
        metadata.update(asof_timestamp=state["updated_at"], scope=coverage["scope_label"],
                        export_kind="liquidity_ranking",
                        incomplete_fill_penalty_bps=state["methodology"]["execution_cost_penalty_bps"])
        execution = {f"{side}_{key}": _execution_value(row, side, key)
                     for side in ("buy", "sell") for key in ("fill_ratio", "vwap", "slip_bps", "single_order_eligible")}
        flow = {f"ofi_level_{level + 1}": value for level, value in enumerate(row["ofi_levels"])}
        writer.writerow({**row, **metadata, **execution, **flow})
    return output.getvalue().encode("utf-8-sig")


