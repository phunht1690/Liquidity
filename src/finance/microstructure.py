"""Chỉ báo vi cấu trúc; các đơn vị đầu vào là VNĐ và cổ phiếu."""
from __future__ import annotations

from math import isfinite
from typing import Any, Sequence

from src.data.quality import quote_flags
from src.data.schema import Quote
from src.finance.execution_sim import simulate_execution


DEFAULT_TICK_BANDS = ((10_000, 10), (50_000, 50), (None, 100))
DEFAULT_OBI_WEIGHTS = (1.0, .5, 1 / 3)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} phải là số dương hữu hạn.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} phải là số dương hữu hạn.") from exc
    if not isfinite(result) or result <= 0:
        raise ValueError(f"{name} phải là số dương hữu hạn.")
    return result


def tick_size(price: float, tick_bands: Sequence[Sequence[float | None]] | None = None) -> float:
    """Các cận trên loại trừ; cận cuối None bao phủ toàn bộ miền giá dương."""
    value = _number(price, "Giá")
    bands = DEFAULT_TICK_BANDS if tick_bands is None else tick_bands
    if not bands:
        raise ValueError("Bảng bước giá không được trống.")
    previous = 0.0
    parsed = []
    for index, band in enumerate(bands):
        if len(band) != 2:
            raise ValueError("Mỗi khoảng bước giá phải có cận trên và tick.")
        upper, tick = band
        amount = _number(tick, "Bước giá")
        if upper is None:
            if index != len(bands) - 1:
                raise ValueError("Cận None chỉ được ở khoảng cuối.")
        else:
            upper = _number(upper, "Cận giá")
            if upper <= previous:
                raise ValueError("Cận giá phải tăng nghiêm ngặt.")
            previous = upper
        parsed.append((upper, amount))
    if parsed[-1][0] is not None:
        raise ValueError("Khoảng bước giá cuối phải có cận None.")
    for upper, amount in parsed:
        if upper is None or value < upper:
            return amount
    raise AssertionError("Bảng bước giá không bao phủ giá.")


def _parameters(market: dict[str, Any] | None, lot_size: int,
                obi_level_weights: Sequence[float] | None) -> tuple[int, Sequence[Sequence[float | None]] | None, str, tuple[float, ...]]:
    settings = market or {}
    lot = settings.get("lot_size", lot_size)
    if isinstance(lot, bool) or not isinstance(lot, int) or lot <= 0:
        raise ValueError("Lô phải là số nguyên dương.")
    bands = settings.get("tick_bands")
    tick_size(1, bands)  # kiểm tra toàn bảng kể cả khi quote hiện tại lỗi.
    reference = settings.get("tick_reference", "mid")
    if reference not in ("mid", "bid1", "ask1"):
        raise ValueError("tick_reference phải là mid, bid1 hoặc ask1.")
    supplied = DEFAULT_OBI_WEIGHTS if obi_level_weights is None else obi_level_weights
    if len(supplied) != 3:
        raise ValueError("OBI cần ba trọng số mức giá.")
    weights = tuple(_number(weight, "Trọng số OBI") for weight in supplied)
    return lot, bands, reference, weights


def _imbalance(bid_volume: float, ask_volume: float) -> float | None:
    total = bid_volume + ask_volume
    return (bid_volume - ask_volume) / total if total > 0 else None


def compute_metrics(quote: Quote, notional: float = 1_000_000_000, lot_size: int = 100, *,
                    market: dict[str, Any] | None = None,
                    obi_level_weights: Sequence[float] | None = None) -> dict[str, Any]:
    lot, bands, reference, weights = _parameters(market, lot_size, obi_level_weights)
    result: dict[str, Any] = {"symbol": quote.symbol, "group": quote.group, "source": quote.source,
                              "timestamp": quote.exchange_time.isoformat(),
                              "bids": [x.to_dict() for x in quote.bids[:3]],
                              "asks": [x.to_dict() for x in quote.asks[:3]],
                              "assumptions": {"lot_size": lot, "tick_reference": reference,
                                              "obi_level_weights": list(weights), "max_round_lot_order_shares": (market or {}).get("max_round_lot_order_shares", 500000)}}
    invalid_flags = quote_flags(quote)
    if invalid_flags:
        result.update({key: None for key in ("mid", "spread_bps", "spread_ticks", "depth_bid_vnd",
                      "depth_ask_vnd", "depth_min_vnd", "obi1", "obi3", "obi_w", "weighted_mid", "weighted_mid_dev_bps")})
        result.update({"buy": None, "sell": None, "quality": ",".join(invalid_flags), "quality_flags": invalid_flags})
        return result
    bids, asks = quote.bids[:3], quote.asks[:3]
    b1, a1 = bids[0], asks[0]
    mid = (b1.price + a1.price) / 2
    spread = a1.price - b1.price
    depth_bid = sum(x.price * x.volume for x in bids)
    depth_ask = sum(x.price * x.volume for x in asks)
    top_volume = b1.volume + a1.volume
    weighted_mid = (a1.price * b1.volume + b1.price * a1.volume) / top_volume if top_volume > 0 else None
    result.update({
        "mid": mid,
        "spread_bps": spread / mid * 10_000,
        # Giá tham chiếu tick được chọn trong config, mặc định dùng mid.
        "spread_ticks": spread / tick_size({"mid": mid, "bid1": b1.price, "ask1": a1.price}[reference], bands),
        "depth_bid_vnd": depth_bid, "depth_ask_vnd": depth_ask,
        "depth_min_vnd": min(depth_bid, depth_ask),
        "obi1": _imbalance(b1.volume, a1.volume),
        "obi3": _imbalance(sum(x.volume for x in bids), sum(x.volume for x in asks)),
        # Trọng số mặc định 1/i; cấu hình có thể đổi để kiểm tra độ nhạy.
        "obi_w": _imbalance(sum(x.volume * weight for x, weight in zip(bids, weights)),
                             sum(x.volume * weight for x, weight in zip(asks, weights))),
        "weighted_mid": weighted_mid,
        "weighted_mid_dev_bps": (weighted_mid - mid) / mid * 10_000 if weighted_mid is not None else None,
        "buy": simulate_execution(quote, notional, "buy", lot, max_order_shares=(market or {}).get("max_round_lot_order_shares", 500000)),
        "sell": simulate_execution(quote, notional, "sell", lot, max_order_shares=(market or {}).get("max_round_lot_order_shares", 500000)),
        "quality": "valid" if len(bids) == len(asks) == 3 else "incomplete_levels",
    })
    return result
