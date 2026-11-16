"""Phép tính hấp thụ giả định; không chứa chức năng gửi lệnh."""
from __future__ import annotations

from math import floor, isfinite
from typing import Any, Literal

from src.data.quality import quote_flags
from src.data.schema import Quote


def simulate_execution(
    quote: Quote,
    notional: float,
    side: Literal["buy", "sell"],
    lot_size: int = 100,
    *, max_order_shares: int = 500_000,
) -> dict[str, Any]:
    if side not in ("buy", "sell"):
        raise ValueError("side phải là buy hoặc sell.")
    if isinstance(notional, bool) or not isfinite(notional) or notional < 0 or isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size <= 0:
        raise ValueError("Quy mô phải không âm, hữu hạn; lô phải dương.")
    if isinstance(max_order_shares, bool) or not isinstance(max_order_shares, int) or max_order_shares <= 0:
        raise ValueError("Giới hạn cổ phiếu một lệnh phải là số nguyên dương.")
    invalid_flags = quote_flags(quote)
    if invalid_flags:
        # Hàm có thể được gọi trực tiếp, nên tự bảo vệ trước quote không hợp lệ.
        return {"vwap": None, "slip_bps": None, "fill_ratio": None,
                "requested_shares": 0, "filled_shares": 0, "unfilled_shares": None,
                "filled_value_vnd": None, "reference_notional_vnd": notional,
                "flag": "missing_side" if "missing_side" in invalid_flags else "invalid_book",
                "quality_flags": invalid_flags, "single_order_eligible": False, "max_order_shares": max_order_shares}
    mid = (quote.bids[0].price + quote.asks[0].price) / 2
    # q = floor(N / mid / 100) × 100; ngân sách quy đổi theo mid.
    requested = floor(notional / mid / lot_size) * lot_size
    if requested == 0:
        return {"vwap": None, "slip_bps": None, "fill_ratio": None,
                "requested_shares": 0, "filled_shares": 0, "unfilled_shares": 0,
                "filled_value_vnd": 0.0, "reference_notional_vnd": notional,
                "flag": "below_one_lot", "single_order_eligible": False, "max_order_shares": max_order_shares}
    levels = quote.asks[:3] if side == "buy" else quote.bids[:3]
    remaining = float(requested)
    value = 0.0
    filled = 0.0
    for level in levels:
        take = min(remaining, level.volume)
        value += take * level.price
        filled += take
        remaining -= take
        if remaining <= 0:
            break
    vwap = value / filled if filled else None
    # Chi phí dương cho cả mua và bán; VWAP chỉ tính phần hấp thụ được.
    slip = ((vwap - mid) if side == "buy" else (mid - vwap)) / mid * 10_000 if vwap is not None else None
    return {"vwap": vwap, "slip_bps": slip, "fill_ratio": filled / requested,
            "requested_shares": requested, "filled_shares": filled,
            "unfilled_shares": remaining, "filled_value_vnd": value,
            "reference_notional_vnd": notional,
            "single_order_eligible": requested <= max_order_shares, "max_order_shares": max_order_shares,
            "scenario_note": "Vượt giới hạn một lệnh; chỉ là kịch bản tổng quy mô, không phải một lệnh hợp lệ." if requested > max_order_shares else "Kịch bản hấp thụ lô chẵn trong ba mức; không gửi lệnh.",
            "flag": "partial_three_levels" if remaining > 0 else "complete"}
