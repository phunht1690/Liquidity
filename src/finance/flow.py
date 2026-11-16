"""Snapshot flow diagnostics, not reconstructed exchange event flow.

Cont's price/volume indicator formula is applied independently at each rank.
Missing intermediate events and level re-indexing make this an approximation.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from src.data.quality import quote_flags, session_phase
from src.data.schema import Quote


def snapshot_flow(previous: Quote | None, current: Quote | None, *, max_gap_seconds: float = 90) -> dict[str, Any]:
    result = {"ofi_l1": None, "ofi_levels": [None, None, None], "ofi_3": None,
              "ofi_normalized": None, "ofi_interval_seconds": None,
              "ofi_status": "no_previous_snapshot" if previous is None else "invalid_pair"}
    if not isinstance(previous, Quote) or not isinstance(current, Quote):
        return result
    elapsed = (current.exchange_time - previous.exchange_time).total_seconds()
    if previous.symbol != current.symbol or previous.source != current.source or quote_flags(previous) or quote_flags(current):
        return result
    if not 0 < elapsed <= max_gap_seconds or session_phase(previous) != session_phase(current) or previous.exchange_time.date() != current.exchange_time.date():
        result["ofi_status"] = "gap_or_session_boundary"
        return result
    levels = []
    for old_bid, bid, old_ask, ask in zip(previous.bids, current.bids, previous.asks, current.asks):
        flow = ((bid.volume if bid.price >= old_bid.price else 0)
                - (old_bid.volume if bid.price <= old_bid.price else 0)
                - (ask.volume if ask.price <= old_ask.price else 0)
                + (old_ask.volume if ask.price >= old_ask.price else 0))
        levels.append(flow)
    total = sum(levels)
    denominator = sum(level.volume for q in (previous, current) for side in (q.bids, q.asks) for level in side) / 2
    return {"ofi_l1": levels[0], "ofi_levels": levels, "ofi_3": total,
            "ofi_normalized": total / denominator if denominator > 0 else None,
            "ofi_interval_seconds": elapsed, "ofi_status": "snapshot_approximation"}


def flow_at(quotes: list[Quote | None], index: int, *, max_gap_seconds: float = 90) -> dict[str, Any]:
    """Use at most five contiguous valid increments, including zeros in denominator."""
    current = quotes[index]
    flow = snapshot_flow(quotes[index - 1] if index > 0 else None, current, max_gap_seconds=max_gap_seconds)
    recent = []
    for position in range(index, max(0, index - 5), -1):
        item = snapshot_flow(quotes[position - 1], quotes[position], max_gap_seconds=max_gap_seconds)
        if item["ofi_status"] != "snapshot_approximation":
            break
        recent.append(item["ofi_normalized"])
    value = flow["ofi_normalized"]
    flow["ofi_persistence_count"] = len(recent)
    # No direction for a zero increment; zero histories count as neutral, not persistence.
    flow["ofi_persistence"] = (sum(x * value > 0 for x in recent) / len(recent)
                               if value is not None and value != 0 and len(recent) >= 3 else None)
    return flow


def effective_spread_bps(trade_price: float, pretrade_mid: float) -> float:
    """Absolute effective-spread proxy, bps; not the aggressor-signed metric.

    Caller must supply an aligned pre-trade midpoint. This function neither
    classifies trades nor applies a Lee–Ready lag.
    """
    for value in (trade_price, pretrade_mid):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            raise ValueError("Trade price and pre-trade mid must be positive finite numbers.")
    return 2 * abs(trade_price - pretrade_mid) / pretrade_mid * 10_000


def matched_effective_spread_bps(trade_price: float, trade_time, pretrade_quote: Quote, *, max_quote_age_seconds: float, same_timestamp_order_verified: bool = False) -> float:
    """Reject future/stale quotes; never use a minute-bar close as a trade event."""
    if trade_time.tzinfo is None or trade_time.utcoffset() is None or quote_flags(pretrade_quote):
        raise ValueError("Trade and valid pre-trade quote require timezone-aware timestamps.")
    if isinstance(max_quote_age_seconds, bool) or not isinstance(max_quote_age_seconds, (int, float)) or not isfinite(max_quote_age_seconds) or max_quote_age_seconds < 0:
        raise ValueError("Caller must set an explicit non-negative quote freshness bound.")
    age = (trade_time - pretrade_quote.exchange_time).total_seconds()
    if not 0 <= age <= max_quote_age_seconds or (age == 0 and not same_timestamp_order_verified):
        raise ValueError("Quote is not an eligible pre-trade quote.")
    mid = (pretrade_quote.bids[0].price + pretrade_quote.asks[0].price) / 2
    return effective_spread_bps(trade_price, mid)
