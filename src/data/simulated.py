"""Dữ liệu SIMULATED có thể tái tạo; tuyệt đối không dùng làm kết quả báo cáo."""
from __future__ import annotations

from datetime import datetime, timedelta
from math import log, sin
import random
from typing import Any, Sequence

from src.data.quality import quote_flags
from src.data.schema import PriceLevel, Quote, VN_TZ
from src.finance.microstructure import _parameters, compute_metrics, tick_size
from src.finance.flow import flow_at

# Mã minh họa quen thuộc; chưa xác nhận thành phần VN30 tại ngày triển khai.
SYMBOL_GROUPS = {
    "FPT": "Công nghệ", "HPG": "Vật liệu", "VCB": "Ngân hàng",
    "VNM": "Tiêu dùng", "TCB": "Ngân hàng", "MWG": "Bán lẻ",
    "MBB": "Ngân hàng", "VPB": "Ngân hàng", "SSI": "Chứng khoán",
    "CTG": "Ngân hàng", "BID": "Ngân hàng", "VHM": "Bất động sản",
}
BASE_PRICES = (112_000, 27_000, 86_000, 62_000, 35_000, 66_000,
               26_000, 24_000, 31_000, 37_000, 44_000, 52_000)


def build_demo(seed: int = 20261026, frames: int = 120, *, market: dict[str, Any] | None = None) -> dict[str, list[Quote]]:
    """Tạo 120 ảnh chụp 1 phút; số liệu không phải quan sát thị trường."""
    if frames < 1 or frames > 136:
        raise ValueError("Demo chỉ hỗ trợ 1–136 phút, từ 09:15 đến 11:30.")
    lot, bands, _, _ = _parameters(market, 100, None)
    start = datetime(2026, 10, 26, 9, 15, tzinfo=VN_TZ)
    result: dict[str, list[Quote]] = {}
    for s, (symbol, group) in enumerate(SYMBOL_GROUPS.items()):
        rng = random.Random(seed + s * 1009)
        base = BASE_PRICES[s]
        cumulative = 0.0
        quotes = []
        for index in range(frames):
            phase = index / 9 + s * .8
            tick = tick_size(base, bands)
            center = round((base * (1 + .006 * sin(index / 35 + s)) + 2 * tick * sin(phase / 2)) / tick) * tick
            spread_ticks = 1 + int((sin(phase) + 1) * (1 + s % 3))
            bid = center - tick
            ask = bid + spread_ticks * tick
            imbalance = .68 * sin(phase / 1.7)
            scale = (5000 + (s % 5) * 5500) * (1 + .3 * sin(phase / 1.3))
            if s in (3, 9):
                scale *= .35
            bids, asks = [], []
            for level in range(3):
                # Vol là cổ phiếu, bội số lô cấu hình trong schema mô phỏng.
                bid_volume = max(lot, round(scale * (1 + imbalance) * (1 + level * .35) * rng.uniform(.8, 1.2) / lot) * lot)
                ask_volume = max(lot, round(scale * (1 - imbalance) * (1 + level * .35) * rng.uniform(.8, 1.2) / lot) * lot)
                bids.append(PriceLevel(bid - level * tick, bid_volume))
                asks.append(PriceLevel(ask + level * tick, ask_volume))
            # Giao dịch mô phỏng độc lập với tổng depth; chỉ phục vụ Amihud demo.
            trade_price = bid if rng.random() < .5 else ask
            trade_shares = rng.randint(400, 3000) * lot
            cumulative += trade_price * trade_shares
            stamp = start + timedelta(minutes=index)
            quotes.append(Quote(symbol, stamp, stamp + timedelta(milliseconds=40 + s * 3),
                                tuple(bids), tuple(asks), trade_price, cumulative, group, "simulated", lot_type="round"))
        result[symbol] = quotes
    return result


def metrics_at(quotes: list[Quote | None], index: int, notional: float = 1_000_000_000,
               persistence_threshold: float = .5, *, market: dict[str, Any] | None = None,
               obi_level_weights: Sequence[float] | None = None,
               history_gap_seconds: float = 90) -> dict[str, Any]:
    """Chỉ dùng quá khứ đến index; Amihud chưa đủ 5 phút trả None."""
    if not quotes:
        raise ValueError("Chuỗi quote trống.")
    if index < 0 or index >= len(quotes):
        raise IndexError("Khung Replay ngoài phạm vi.")
    quote = quotes[index]
    if not isinstance(quote, Quote):
        raise ValueError("Khung hiện tại chưa có quote hợp lệ để tính chỉ báo.")
    if not 0 < persistence_threshold <= 1:
        raise ValueError("Ngưỡng persistence phải nằm trong (0, 1].")
    row = compute_metrics(quote, notional, market=market, obi_level_weights=obi_level_weights)
    row.update(flow_at(quotes, index, max_gap_seconds=history_gap_seconds))
    flags = quote_flags(quote)
    row["quality"] = "valid" if not flags else ",".join(flags)
    row["quality_flags"] = flags
    # Một khung lịch sử vắng không làm quote hiện tại mất giá trị sử dụng.
    # Không nối qua khung thiếu hay dùng quote tương lai để bù cửa sổ.
    window = quotes[max(0, index - 5):index + 1]
    if any(not isinstance(item, Quote) for item in window):
        row.update({"amihud_5m": None, "five_minute_trade_value_vnd": None,
                    "two_sided_ratio": None, "persistence": None, "obi_persistence": None, "pace": None,
                    "analytics_flags": ["missing_record_in_window", "incomplete_five_minute_window"],
                    "baseline": "simulated_demo — chưa hiệu chuẩn lịch sử thật"})
        return row
    amihud = None
    five_minute_value = None
    analytics_flags = []
    if index >= 5:
        prior = quotes[index - 5]
        trade_window = quotes[index - 5:index + 1]
        elapsed = [(b.exchange_time - a.exchange_time).total_seconds() for a, b in zip(trade_window, trade_window[1:])]
        counter_reset = any(b.cumulative_trade_value < a.cumulative_trade_value for a, b in zip(trade_window, trade_window[1:]))
        if any(quote_flags(item) for item in trade_window):
            analytics_flags.append("invalid_book_in_window")
        if counter_reset:
            analytics_flags.append("trade_counter_reset")
        if any(seconds <= 0 for seconds in elapsed) or sum(elapsed) != 300:
            analytics_flags.append("incomplete_five_minute_window")
        if not analytics_flags:
            five_minute_value = quote.cumulative_trade_value - prior.cumulative_trade_value
        if five_minute_value is not None and five_minute_value > 0:
            # |ln(P_t/P_t-5m)| / giá trị khớp tính bằng tỷ đồng.
            amihud = abs(log(quote.trade_price / prior.trade_price)) / (five_minute_value / 1_000_000_000)
    # Tỷ lệ thời gian đủ hai phía trên các khoảng giữ quote, không nhìn tương lai.
    intervals = [(b.exchange_time - a.exchange_time).total_seconds() for a, b in zip(window, window[1:])]
    total_seconds = sum(intervals) if all(seconds > 0 for seconds in intervals) else 0
    valid_seconds = sum((b.exchange_time - a.exchange_time).total_seconds() for a, b in zip(window, window[1:]) if not quote_flags(a))
    two_sided_ratio = valid_seconds / total_seconds if total_seconds > 0 else None
    imbalance = row["obi_w"]
    recent = [compute_metrics(item, notional, market=market, obi_level_weights=obi_level_weights)["obi_w"] for item in quotes[max(0, index - 4):index + 1]]
    # Ngưỡng DEMO lấy từ config, chưa phải phân vị dữ liệu thị trường thật.
    persistence = (sum(value is not None and imbalance is not None and abs(value) >= persistence_threshold and value * imbalance > 0 for value in recent) / len(recent)
                   if index >= 5 and not analytics_flags else None)
    row.update({"amihud_5m": amihud, "five_minute_trade_value_vnd": five_minute_value,
                "two_sided_ratio": two_sided_ratio, "persistence": persistence, "obi_persistence": persistence,
                "pace": None, "analytics_flags": analytics_flags,
                "baseline": "simulated_demo — chưa hiệu chuẩn lịch sử thật"})
    return row
