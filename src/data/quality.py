"""Kiểm tra quote nội bộ, không suy diễn semantics của feed SSI."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from hashlib import sha256
import json

from src.data.schema import Quote, VN_TZ


def session_phase(quote: Quote) -> str:
    """Use a verified internal phase when present, otherwise the HOSE clock.

    Numeric auction prices are still auction observations. Holidays and unscheduled
    halts need an official calendar/provider status before a real collector runs.
    """
    if quote.phase is not None:
        return quote.phase
    stamp = quote.exchange_time.astimezone(VN_TZ)
    value = stamp.time().replace(tzinfo=None)
    if stamp.weekday() >= 5:
        return "closed"
    if time(9) <= value < time(9, 15):
        return "opening_auction"
    if time(9, 15) <= value < time(11, 30):
        return "continuous_am"
    if time(11, 30) <= value < time(13):
        return "lunch"
    if time(13) <= value < time(14, 30):
        return "continuous_pm"
    if time(14, 30) <= value <= time(14, 45):
        return "closing_auction"
    return "closed"


def quote_flags(quote: Quote, now: datetime | None = None, stale_seconds: float = 60) -> list[str]:
    flags: list[str] = []
    if session_phase(quote) not in ("continuous_am", "continuous_pm"):
        flags.append("non_continuous_phase")
    if quote.lot_type != "round":
        flags.append("separate_odd_lot_book" if quote.lot_type == "odd" else "unverified_lot_segment")
    if not quote.bids or not quote.asks or sum(x.volume for x in quote.bids) <= 0 or sum(x.volume for x in quote.asks) <= 0:
        flags.append("missing_side")
    # Mức giá tốt nhất không có khối lượng không phải quote thực thi hợp lệ.
    # Chưa được tự đẩy mức 2 lên mức 1 khi chưa rõ semantics của nguồn dữ liệu.
    if (quote.bids and quote.bids[0].volume <= 0) or (quote.asks and quote.asks[0].volume <= 0):
        flags.append("empty_best_level")
    if len(quote.bids) != 3 or len(quote.asks) != 3:
        flags.append("incomplete_levels")
    if quote.bids and quote.asks and quote.bids[0].price >= quote.asks[0].price:
        flags.append("crossed_book")
    if any(a.price < b.price for a, b in zip(quote.bids, quote.bids[1:])):
        flags.append("unsorted_bids")
    if any(a.price > b.price for a, b in zip(quote.asks, quote.asks[1:])):
        flags.append("unsorted_asks")
    if now is not None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now phải có múi giờ.")
        if (now - quote.received_at).total_seconds() > stale_seconds:
            flags.append("stale")
    return flags


@dataclass
class QualityTracker:
    """Bộ theo dõi dùng cho demo/thử lỗi; không coi tin đến muộn là cập nhật mới."""
    seen: set[str] = field(default_factory=set)
    latest: dict[str, datetime] = field(default_factory=dict)
    total_messages: int = 0
    duplicate_count: int = 0
    late_count: int = 0
    invalid_count: int = 0

    def inspect(self, quote: Quote, now: datetime | None = None) -> list[str]:
        self.total_messages += 1
        payload = quote.to_dict()
        payload.pop("received_at", None)
        digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        flags = quote_flags(quote, now)
        if digest in self.seen:
            flags.append("duplicate")
            self.duplicate_count += 1
        else:
            self.seen.add(digest)
        latest = self.latest.get(quote.symbol)
        if latest is not None and quote.exchange_time < latest:
            flags.append("late")
            self.late_count += 1
        if latest is None or quote.exchange_time > latest:
            self.latest[quote.symbol] = quote.exchange_time
        if any(flag in flags for flag in ("missing_side", "empty_best_level", "incomplete_levels", "crossed_book", "unsorted_bids", "unsorted_asks")):
            self.invalid_count += 1
        return flags
