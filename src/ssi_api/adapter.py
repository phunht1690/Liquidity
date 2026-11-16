"""Không suy đoán ý nghĩa trường thiếu hoặc giao thức snapshot/delta."""

from typing import Any, NoReturn

from src.data.schema import finite_number


class SSIContractNotConfirmed(RuntimeError):
    """Thiếu bằng chứng để chuyển thông điệp SSI sang schema nội bộ."""


def inspect_price_observation(raw_price: Any, phase: str) -> dict[str, Any]:
    """Vendor-independent guard; ``phase`` must already have verified semantics.

    This does not map a SSI message. Retain numeric indicative prices and legacy
    ATO/ATC text for inspection, but neither is a continuous executable quote.
    """
    allowed = {"opening_auction", "continuous_am", "lunch", "continuous_pm", "closing_auction", "closed", "halted"}
    if phase not in allowed:
        raise ValueError("Cần pha phiên đã được xác nhận; không suy từ giá.")
    if isinstance(raw_price, str) and raw_price.upper().strip() in {"ATO", "ATC"}:
        expected = "opening_auction" if raw_price.upper().strip() == "ATO" else "closing_auction"
        if phase != expected:
            raise ValueError("Nhãn giá đấu giá không khớp pha phiên đã xác nhận.")
        return {"raw_price": raw_price, "numeric_price": None, "phase": phase, "continuous_eligible": False}
    price = finite_number(raw_price)
    if price <= 0:
        raise ValueError("Giá phải dương.")
    return {"raw_price": raw_price, "numeric_price": price, "phase": phase,
            "continuous_eligible": phase in {"continuous_am", "continuous_pm"}}


def normalize_ssi_message(message: dict[str, Any]) -> NoReturn:
    """TODO: xác nhận payload thật, units, timestamp và snapshot/delta trước khi viết."""
    raise SSIContractNotConfirmed(
        "Không chuẩn hóa thông điệp tùy ý. Dùng SSISession trong src/data/ssi_feed.py "
        "với các topic quote/trade/market.flag và cấu trúc SSI v3 đã đối chiếu."
    )
