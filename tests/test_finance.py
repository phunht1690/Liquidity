"""Dữ liệu simulated có đáp số tính tay; không phải kết quả thực nghiệm."""
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from src.data.schema import PriceLevel, Quote, VN_TZ
from src.finance.execution_sim import simulate_execution
from src.finance.microstructure import compute_metrics, tick_size
from src.finance.scoring import lqs_category, score_cross_section


def book() -> Quote:
    stamp = datetime(2026, 10, 26, 9, 30, tzinfo=VN_TZ)
    return Quote("TEST", stamp, stamp + timedelta(milliseconds=30),
                 (PriceLevel(99_900, 200), PriceLevel(99_800, 300), PriceLevel(99_700, 500)),
                 (PriceLevel(100_100, 100), PriceLevel(100_200, 200), PriceLevel(100_300, 300)),
                 100_000, 1_000_000_000, lot_type="round")


def test_hand_calculated_spread_depth_obi_weighted_mid() -> None:
    result = compute_metrics(book(), 30_000_000)
    assert result["mid"] == 100_000
    assert result["spread_bps"] == 20
    assert result["spread_ticks"] == 2
    assert result["depth_bid_vnd"] == 99_770_000
    assert result["depth_ask_vnd"] == 60_140_000
    assert result["depth_min_vnd"] == 60_140_000
    assert result["obi1"] == pytest.approx(1 / 3)
    assert result["obi3"] == .25
    assert result["obi_w"] == pytest.approx((200 + 300 / 2 + 500 / 3 - 100 - 200 / 2 - 300 / 3) / (200 + 300 / 2 + 500 / 3 + 100 + 200 / 2 + 300 / 3))
    assert result["weighted_mid"] == pytest.approx(100_033.3333333333)
    assert result["weighted_mid_dev_bps"] == pytest.approx(3.3333333333)


def test_hand_calculated_buy_absorption() -> None:
    result = simulate_execution(book(), 30_000_000, "buy")
    assert result["requested_shares"] == 300
    assert result["filled_shares"] == 300
    assert result["vwap"] == pytest.approx((100 * 100_100 + 200 * 100_200) / 300)
    assert result["slip_bps"] == pytest.approx(16.6666666667)
    assert result["fill_ratio"] == 1
    assert result["flag"] == "complete"


def test_partial_fill_reports_cost_of_filled_portion_only() -> None:
    result = simulate_execution(book(), 100_000_000, "buy")
    assert result["requested_shares"] == 1000
    assert result["filled_shares"] == 600
    assert result["fill_ratio"] == .6
    assert result["vwap"] == pytest.approx(60_140_000 / 600)
    assert result["flag"] == "partial_three_levels"
    assert result["unfilled_shares"] == 400
    assert result["filled_value_vnd"] == 60_140_000
    assert result["reference_notional_vnd"] == 100_000_000


def test_sell_slippage_is_positive_cost() -> None:
    result = simulate_execution(book(), 30_000_000, "sell")
    assert result["vwap"] == pytest.approx((200 * 99_900 + 100 * 99_800) / 300)
    assert result["slip_bps"] == pytest.approx(13.3333333333)


def test_zero_target_has_no_division_by_zero_or_false_fill() -> None:
    result = simulate_execution(book(), 1, "buy")
    assert result["requested_shares"] == 0
    assert result["fill_ratio"] is None
    assert result["vwap"] is None
    assert result["flag"] == "below_one_lot"


@pytest.mark.parametrize("price,expected", [(9990, 10), (10000, 50), (49950, 50), (50000, 100)])
def test_tick_boundaries(price: float, expected: int) -> None:
    assert tick_size(price) == expected


def test_price_string_is_parsed_but_auction_string_is_not() -> None:
    assert PriceLevel("100100.0", "100").price == 100_100
    with pytest.raises(ValueError):
        PriceLevel("ATO", 100)
    with pytest.raises(ValueError):
        PriceLevel(float("nan"), 100)
    with pytest.raises(ValueError):
        PriceLevel(True, 100)


def test_lqs_requires_all_five_components() -> None:
    row = compute_metrics(book(), 30_000_000)
    row.update(amihud_5m=None, two_sided_ratio=1.0)
    scored = score_cross_section([row])
    assert scored[0]["lqs"] is None
    assert scored[0]["category"] == "Chưa đủ dữ liệu"


def test_lqs_ties_are_neutral_and_best_row_gets_higher_score() -> None:
    row = compute_metrics(book(), 30_000_000)
    row.update(amihud_5m=.01, two_sided_ratio=1.0)
    assert score_cross_section([row])[0]["lqs"] == 50
    bad = dict(row, symbol="BAD", spread_bps=30, depth_min_vnd=20_000_000, amihud_5m=.03, two_sided_ratio=.8)
    good = dict(row, symbol="GOOD", spread_bps=10, depth_min_vnd=200_000_000, amihud_5m=.001)
    scored = score_cross_section([bad, good])
    assert scored[1]["lqs"] > scored[0]["lqs"]


def test_bad_weights_rejected() -> None:
    with pytest.raises(ValueError):
        score_cross_section([], {"spread_bps": 1})


@pytest.mark.parametrize("fault", ["crossed", "unsorted_bids", "unsorted_asks"])
def test_direct_absorption_rejects_invalid_book(fault: str) -> None:
    quote = book()
    if fault == "crossed":
        quote = replace(quote, asks=(PriceLevel(99_800, 100),) + quote.asks[1:])
    elif fault == "unsorted_bids":
        quote = replace(quote, bids=tuple(reversed(quote.bids)))
    else:
        quote = replace(quote, asks=tuple(reversed(quote.asks)))
    for side in ("buy", "sell"):
        result = simulate_execution(quote, 30_000_000, side)
        assert result["flag"] == "invalid_book"
        assert result["vwap"] is None
        assert result["slip_bps"] is None
        assert result["fill_ratio"] is None
        assert result["filled_shares"] == 0


@pytest.mark.parametrize("empty_side", ["bid", "ask", "both"])
def test_empty_best_level_is_not_scored_or_executed(empty_side: str) -> None:
    quote = book()
    if empty_side in ("bid", "both"):
        quote = replace(quote, bids=(PriceLevel(quote.bids[0].price, 0),) + quote.bids[1:])
    if empty_side in ("ask", "both"):
        quote = replace(quote, asks=(PriceLevel(quote.asks[0].price, 0),) + quote.asks[1:])
    row = compute_metrics(quote, 30_000_000)
    row.update(amihud_5m=.01, two_sided_ratio=1.0)
    assert "empty_best_level" in row["quality_flags"]
    assert row["mid"] is None
    assert score_cross_section([row])[0]["lqs"] is None
    assert simulate_execution(quote, 30_000_000, "buy")["flag"] == "invalid_book"


def test_market_and_obi_config_change_actual_calculations() -> None:
    normal = compute_metrics(book(), 30_000_000)
    configured = compute_metrics(book(), 30_000_000,
        market={"lot_size": 200, "tick_bands": [[None, 200]], "tick_reference": "mid"},
        obi_level_weights=[1, 1, 1])
    assert normal["buy"]["requested_shares"] == 300
    assert configured["buy"]["requested_shares"] == 200
    assert configured["spread_ticks"] == 1
    assert configured["obi_w"] == configured["obi3"] == .25
    assert configured["obi_w"] != pytest.approx(normal["obi_w"])
    assert configured["assumptions"]["lot_size"] == 200


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), True])
def test_tick_rejects_nonpositive_or_nonfinite_price(price) -> None:
    with pytest.raises(ValueError):
        tick_size(price)


@pytest.mark.parametrize("bands", [[], [[10000, 10]], [[None, 10], [50000, 50]],
    [[50000, 10], [10000, 50], [None, 100]], [[None, 0]], [[None, float("nan")]]])
def test_tick_rejects_invalid_band_configuration(bands) -> None:
    with pytest.raises(ValueError):
        tick_size(10000, bands)


@pytest.mark.parametrize("kwargs", [
    {"market": {"lot_size": 0}}, {"market": {"lot_size": 1.5}},
    {"market": {"tick_reference": "unknown"}},
    {"obi_level_weights": [1, 0, 1]}, {"obi_level_weights": [1, 2]},
    {"obi_level_weights": [1, float("inf"), 1]},
])
def test_invalid_financial_configuration_is_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        compute_metrics(book(), **kwargs)


@pytest.mark.parametrize("score,label", [
    (None, "Chưa đủ dữ liệu"), (float("nan"), "Chưa đủ dữ liệu"),
    (0, "Rất thấp"), (24.999, "Rất thấp"), (25, "Thấp"),
    (49.999, "Thấp"), (50, "Trung bình"), (74.999, "Trung bình"),
    (75, "Cao"), (100, "Cao"),
])
def test_lqs_category_boundaries_use_relative_labels(score, label: str) -> None:
    assert lqs_category(score) == label


def test_execution_cost_penalty_can_be_reconstructed_by_hand() -> None:
    row = {"symbol": "TEST", "quality": "valid", "spread_bps": 20,
           "depth_min_vnd": 1_000_000, "amihud_5m": .01, "two_sided_ratio": 1,
           "buy": {"slip_bps": 10, "fill_ratio": 1},
           "sell": {"slip_bps": 20, "fill_ratio": .4}}
    result = score_cross_section([row], incomplete_fill_penalty_bps=200)[0]
    # 15 bps trung bình + 200 × 30% chưa hấp thụ = 75 bps hiệu chỉnh.
    assert result["execution_cost_bps"] == pytest.approx(75)
    assert result["category"] == "Trung bình"  # một mã có phân vị trung tính.
