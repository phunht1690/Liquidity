"""Schema nội bộ độc lập với tên trường của nhà cung cấp."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def finite_number(value: Any) -> float:
    """Chấp nhận giá dạng chuỗi số, từ chối ATO/ATC, bool và số vô hạn."""
    if isinstance(value, bool):
        raise ValueError("Boolean không phải giá hoặc khối lượng.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Giá/khối lượng phải là số hữu hạn.") from exc
    if not isfinite(number):
        raise ValueError("Giá/khối lượng phải là số hữu hạn.")
    return number


@dataclass(frozen=True)
class PriceLevel:
    price: float
    volume: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", finite_number(self.price))
        object.__setattr__(self, "volume", finite_number(self.volume))
        if self.price <= 0 or self.volume < 0:
            raise ValueError("Giá phải dương và khối lượng không âm.")

    def to_dict(self) -> dict[str, float]:
        return {"price": self.price, "volume": self.volume}


@dataclass(frozen=True)
class Quote:
    symbol: str
    exchange_time: datetime
    received_at: datetime
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
    trade_price: float
    cumulative_trade_value: float
    group: str = "Khác"
    source: str = "simulated"
    # Internal semantics only; a future adapter must map the provider's verified fields.
    phase: str | None = None
    lot_type: str = "unknown"

    def __post_init__(self) -> None:
        for value in (self.exchange_time, self.received_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timestamp phải có múi giờ.")
        object.__setattr__(self, "exchange_time", self.exchange_time.astimezone(VN_TZ))
        object.__setattr__(self, "received_at", self.received_at.astimezone(VN_TZ))
        object.__setattr__(self, "trade_price", finite_number(self.trade_price))
        object.__setattr__(self, "cumulative_trade_value", finite_number(self.cumulative_trade_value))
        if self.trade_price <= 0 or self.cumulative_trade_value < 0:
            raise ValueError("Giá khớp phải dương và giá trị lũy kế không âm.")
        if self.phase not in (None, "opening_auction", "continuous_am", "lunch", "continuous_pm", "closing_auction", "closed", "halted"):
            raise ValueError("Pha phiên nội bộ không hợp lệ.")
        if self.lot_type not in ("round", "odd", "unknown"):
            raise ValueError("Sổ lệnh phải tách rõ lô chẵn/lô lẻ.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.exchange_time.isoformat(),
            "exchange_time": self.exchange_time.isoformat(),
            "received_at": self.received_at.isoformat(),
            "bids": [level.to_dict() for level in self.bids],
            "asks": [level.to_dict() for level in self.asks],
            "trade_price": self.trade_price,
            "cumulative_trade_value": self.cumulative_trade_value,
            "group": self.group,
            "source": self.source,
            "phase": self.phase,
            "lot_type": self.lot_type,
        }
