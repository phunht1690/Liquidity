"""Kiểm tra hợp đồng demo xuyên suốt, không phụ thuộc payload nhà cung cấp."""

import json

import pytest


@pytest.mark.parametrize("abort_type", [BrokenPipeError, ConnectionResetError, ConnectionAbortedError])
def test_client_cancel_does_not_send_a_second_error_response(monkeypatch, abort_type) -> None:
    from src.app.server import Handler

    handler = object.__new__(Handler)
    handler.path = "/api/health"
    statuses = []

    def disconnected_response(self, status, data):
        statuses.append(status)
        raise abort_type("Client intentionally cancelled")

    monkeypatch.setattr(Handler, "_json", disconnected_response)
    handler.do_GET()
    assert statuses == [200]

from tests.support.dashboard_fixture import build_state
from src.ssi_api.adapter import SSIContractNotConfirmed, normalize_ssi_message


def test_demo_is_labeled_and_no_real_sessions() -> None:
    state = build_state({})
    assert state["source"] == state["mode"] == "simulated"
    assert state["quality"]["real_sessions"] == 0
    assert state["connection"]["lag_ms"] is None
    assert all(row["source"] == "simulated" for row in state["ranking"])
    json.dumps(state, allow_nan=False)


def test_no_lqs_before_five_minute_component_exists() -> None:
    state = build_state({"index": ["0"]})
    assert all(row["lqs"] is None for row in state["ranking"])
    assert state["selected"]["amihud_5m"] is None
    assert state["selected"]["persistence"] is None
    assert state["kpis"]["high_risk_count"] is None
    assert state["kpis"]["valid_lqs_count"] == 0
    assert not any("Áp lực một chiều" in row["type"] for row in state["alerts"])


def test_group_filter_does_not_change_reference_ranking() -> None:
    full = build_state({})
    group = full["symbols"][0]["group"]
    filtered = build_state({"group": [group]})
    lookup = {row["symbol"]: row["lqs"] for row in full["ranking"]}
    assert filtered["ranking"]
    assert all(row["group"] == group and row["lqs"] == lookup[row["symbol"]]
               for row in filtered["ranking"])


@pytest.mark.parametrize("query", [
    {"notional": ["NaN"]}, {"notional": ["-1"]}, {"index": ["999"]},
    {"symbol": ["UNKNOWN"]}, {"window": ["0"]},
])
def test_bad_query_is_rejected(query: dict[str, list[str]]) -> None:
    with pytest.raises(ValueError):
        build_state(query)


def test_ssi_adapter_waits_for_confirmed_contract() -> None:
    with pytest.raises(SSIContractNotConfirmed):
        normalize_ssi_message({"symbol": "FPT"})

# Hồi quy tích hợp cho các lỗi được phát hiện trong lần rà soát dashboard.
from dataclasses import replace
import csv
import io

from tests.support import dashboard_fixture as server


def _invalidate_at(monkeypatch: pytest.MonkeyPatch, symbol: str, index: int = 60) -> None:
    quotes = list(server.DEMO[symbol])
    quotes[index] = replace(quotes[index], asks=())
    monkeypatch.setitem(server.DEMO, symbol, quotes)


def test_one_bad_symbol_does_not_blank_the_basket(monkeypatch: pytest.MonkeyPatch) -> None:
    _invalidate_at(monkeypatch, "HPG")
    state = server.build_state({})
    assert state["selected"]["valid"]
    assert len(state["ranking"]) == 12
    assert state["coverage"]["valid_book_count"] == 11
    assert state["coverage"]["reference_lqs_count"] == 11
    assert state["coverage"]["invalid_symbols"] == [
        {"symbol": "HPG", "flags": ["missing_side", "incomplete_levels"]}
    ]
    bad = next(row for row in state["ranking"] if row["symbol"] == "HPG")
    assert bad["lqs"] is None and bad["fill_ratio"] is None
    assert state["quality"]["invalid_count"] == 1
    assert any(row["symbol"] == "HPG" and row["severity"] == "critical" for row in state["alerts"])
    json.dumps(state, allow_nan=False)


def test_selected_bad_book_keeps_null_execution_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    _invalidate_at(monkeypatch, "FPT")
    state = server.build_state({})
    selected = state["selected"]
    assert not selected["valid"]
    assert selected["buy"] is None and selected["sell"] is None
    assert selected["lqs"] is None and selected["fill_ratio"] is None
    assert "không hợp lệ" in selected["lqs_reason"]
    assert all(point["buy_slip_bps"] is None and point["buy_fill_ratio"] is None
               for point in state["cost_curve"])
    assert state["history"][-1]["spread_bps"] is None
    assert state["history"][-1]["timestamp"] == state["updated_at"]
    assert state["coverage"]["valid_book_count"] == 11


def test_all_bad_books_report_unavailable_not_false_zero_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    for symbol in server.SYMBOLS:
        _invalidate_at(monkeypatch, symbol)
    state = server.build_state({})
    assert state["coverage"]["valid_book_count"] == 0
    assert state["coverage"]["valid_lqs_count"] == 0
    assert state["kpis"]["median_spread_bps"] is None
    assert state["kpis"]["high_risk_count"] is None
    assert state["kpis"]["strongest_pressure"] is None
    assert len(state["alerts"]) == 12
    assert all(alert["severity"] == "critical" for alert in state["alerts"])
    json.dumps(state, allow_nan=False)


def test_lqs_explanation_reconstructs_the_score() -> None:
    selected = server.build_state({})["selected"]
    details = selected["lqs_explanation"]
    assert len(details) == 5
    assert sum(item["weight"] for item in details) == pytest.approx(1)
    assert sum(item["contribution"] for item in details) == pytest.approx(selected["lqs"])
    for item in details:
        assert item["raw_value"] == selected[item["key"]]
        assert item["contribution"] == pytest.approx(item["percentile"] * item["weight"])


def test_warmup_explanation_keeps_missing_components_visible() -> None:
    selected = server.build_state({"index": ["0"]})["selected"]
    assert len(selected["lqs_explanation"]) == 5
    assert all(item["contribution"] is None for item in selected["lqs_explanation"])
    assert "Amihud" in selected["lqs_reason"]


def test_two_execution_sides_and_cost_coverage_are_independent() -> None:
    state = server.build_state({"notional": ["5000000000"]})
    selected = state["selected"]
    assert selected["buy"]["fill_ratio"] == pytest.approx(.5112612612612613)
    assert selected["sell"]["fill_ratio"] == pytest.approx(.18693693693693694)
    assert selected["buy"]["unfilled_shares"] > 0
    assert selected["sell"]["unfilled_shares"] > selected["buy"]["unfilled_shares"]
    point = state["cost_curve"][-1]
    assert point["buy_fill_ratio"] == selected["buy"]["fill_ratio"]
    assert point["sell_fill_ratio"] == selected["sell"]["fill_ratio"]
    assert selected["buy"]["filled_value_vnd"] == pytest.approx(
        selected["buy"]["vwap"] * selected["buy"]["filled_shares"])


def test_alerts_are_consolidated_and_partial_fill_not_always_critical() -> None:
    state = server.build_state({})
    alerts = state["alerts"]
    assert len(alerts) == len({row["symbol"] for row in alerts})
    assert any(row["condition_count"] > 1 for row in alerts)
    fpt = next(row for row in alerts if row["symbol"] == "FPT")
    assert fpt["severity"] == "warning"
    assert all(row["condition_count"] == len(row["conditions"]) for row in alerts)
    assert all("demo" in row["baseline"] for row in alerts)


def test_default_notional_uses_config_and_small_fixture_has_safe_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(server.CONFIG, "notional_vnd", 2_000_000_000)
    monkeypatch.setattr(server, "FRAME_COUNT", 3)
    state = server.build_state({})
    assert state["notional_vnd"] == 2_000_000_000
    assert state["frame_index"] == 2
    assert len(state["history"]) == 3


def test_export_contains_applied_state_and_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(server.CONFIG, "SSI_ACCESS_TOKEN", "DO_NOT_EXPORT")
    state = server.build_state({"index": ["10"], "notional": ["2000000000"], "group": ["Ngân hàng"]})
    data = server.export_csv(state)
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    assert len(rows) == 6
    assert all(row["source"] == "simulated" for row in rows)
    assert all(row["frame_index"] == "10" and float(row["notional_vnd"]) == 2_000_000_000 for row in rows)
    assert all(row["reference_count"] == "12" and row["visible_count"] == "6" for row in rows)
    assert all(row["dataset_id"] == state["dataset_id"] and row["config_version"] == state["config_version"] for row in rows)
    assert all(row["buy_fill_ratio"] and row["sell_fill_ratio"] for row in rows)
    assert b"DO_NOT_EXPORT" not in data


def test_history_retains_invalid_points_for_gap_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    _invalidate_at(monkeypatch, "FPT", 59)
    state = server.build_state({})
    previous = state["history"][-2]
    assert not previous["valid"]
    assert previous["timestamp"] is not None
    assert previous["spread_bps"] is None
    assert state["selected"]["valid"]


@pytest.mark.parametrize("query", [
    {"index": ["1.5"]}, {"window": ["2.5"]}, {"group": ["missing"]}, {"session": ["unknown"]},
])
def test_invalid_filter_contract_is_rejected(query: dict[str, list[str]]) -> None:
    with pytest.raises(ValueError):
        server.build_state(query)


def _remove_at(monkeypatch: pytest.MonkeyPatch, symbol: str, index: int = 60) -> None:
    quotes = list(server.DEMO[symbol])
    quotes[index] = None
    monkeypatch.setitem(server.DEMO, symbol, quotes)


def test_selected_absent_record_keeps_source_times_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _remove_at(monkeypatch, "FPT")
    state = server.build_state({})
    selected = state["selected"]
    assert selected["timestamp"] is None
    assert selected["exchange_time"] is None and selected["received_at"] is None
    assert selected["bids"] == [] and selected["asks"] == []
    assert not selected["valid"] and selected["buy"] is None
    assert state["coverage"]["valid_book_count"] == 11
    assert state["updated_at"] == server.DEMO["HPG"][60].exchange_time.isoformat()
    assert state["asof_source_symbol"] == "HPG"
    assert state["history"][-1]["timestamp"] is None
    assert state["quality"]["total_messages"] == 731
    assert state["quality"]["missing_record_count"] == 1
    assert state["quality"]["invalid_count"] == 0
    json.dumps(state, allow_nan=False)


def test_other_absent_record_keeps_selected_book_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    _remove_at(monkeypatch, "HPG")
    state = server.build_state({})
    assert state["selected"]["valid"]
    assert state["selected"]["lqs"] is not None
    assert state["coverage"]["reference_lqs_count"] == 11
    missing = next(row for row in state["ranking"] if row["symbol"] == "HPG")
    assert missing["quality_flags"] == ["missing_record"]
    assert missing["lqs"] is None and missing["fill_ratio"] is None


def test_all_absent_current_records_leave_frame_clock_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    for symbol in server.SYMBOLS:
        _remove_at(monkeypatch, symbol)
    state = server.build_state({})
    assert state["updated_at"] is None and state["asof_source_symbol"] is None
    assert state["coverage"]["valid_book_count"] == 0
    assert state["kpis"]["median_spread_bps"] is None
    assert state["kpis"]["high_risk_count"] is None
    assert state["quality"]["total_messages"] == 720
    assert state["quality"]["missing_record_count"] == 12
    assert all(point["buy_slip_bps"] is None for point in state["cost_curve"])
    assert all(alert["timestamp"] is None for alert in state["alerts"])
    json.dumps(state, allow_nan=False)


def test_missing_history_keeps_current_book_but_blocks_temporal_score(monkeypatch: pytest.MonkeyPatch) -> None:
    _remove_at(monkeypatch, "FPT", 59)
    state = server.build_state({})
    selected = state["selected"]
    assert selected["valid"]
    assert selected["spread_bps"] is not None
    assert selected["buy"]["fill_ratio"] is not None
    assert selected["amihud_5m"] is None
    assert selected["two_sided_ratio"] is None
    assert selected["lqs"] is None
    assert set(selected["analytics_flags"]) == {"missing_record_in_window", "incomplete_five_minute_window"}
    assert state["history"][-2]["timestamp"] is None
    assert state["quality"]["gaps"] == 1


def test_csv_category_and_cost_match_the_applied_ranking() -> None:
    state = server.build_state({"notional": ["5000000000"]})
    rows = list(csv.DictReader(io.StringIO(server.export_csv(state).decode("utf-8-sig"))))
    ranking = {row["symbol"]: row for row in state["ranking"]}
    relative_labels = {"Cao", "Trung bình", "Thấp", "Rất thấp", "Chưa đủ dữ liệu"}
    assert len(rows) == len(ranking)
    for row in rows:
        applied = ranking[row["symbol"]]
        assert row["category"] == applied["category"]
        assert row["category"] in relative_labels
        assert row["export_kind"] == "liquidity_ranking"
        assert float(row["execution_cost_bps"]) == pytest.approx(applied["execution_cost_bps"])
        assert float(row["incomplete_fill_penalty_bps"]) == 100
    hpg = next(row for row in rows if row["symbol"] == "HPG")
    assert hpg["category"] == "Rất thấp"


def test_nondefault_penalty_and_assumptions_are_exposed_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(server.CONFIG, "incomplete_fill_penalty_bps", 37.5)
    monkeypatch.setitem(server.CONFIG, "obi_level_weights", [1, 1, 1])
    monkeypatch.setitem(server.CONFIG, "market", {
        **server.CONFIG["market"], "lot_size": 200, "tick_reference": "bid1",
    })
    state = server.build_state({"notional": ["5000000000"]})
    method, selected = state["methodology"], state["selected"]
    assert method["execution_cost_penalty_bps"] == 37.5
    assert method["execution_cost_formula"] == server.EXECUTION_COST_FORMULA
    assert method["applied_assumptions"] == {
        "lot_size": 200, "tick_reference": "bid1", "obi_level_weights": [1, 1, 1],
        "incomplete_fill_penalty_bps": 37.5,
    }
    buy, sell = selected["buy"], selected["sell"]
    expected = (buy["slip_bps"] + sell["slip_bps"]) / 2 + 37.5 * (1 - (buy["fill_ratio"] + sell["fill_ratio"]) / 2)
    assert selected["execution_cost_bps"] == pytest.approx(expected)
    # Xuất trạng thái cũ phải giữ đúng giả định đã áp dụng, không lấy config mới.
    monkeypatch.setitem(server.CONFIG, "incomplete_fill_penalty_bps", 999)
    rows = list(csv.DictReader(io.StringIO(server.export_csv(state).decode("utf-8-sig"))))
    assert all(float(row["incomplete_fill_penalty_bps"]) == 37.5 for row in rows)
