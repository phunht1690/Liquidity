"""Thử lỗi trên dữ liệu simulated; không gọi dịch vụ ngoài."""
from dataclasses import replace
from datetime import datetime, timedelta
import sqlite3
import json
from hashlib import sha256

import pytest

from src.data.quality import QualityTracker, quote_flags
from src.data.schema import PriceLevel, VN_TZ
from src.data.simulated import build_demo, metrics_at
from src.data.storage import RawStorage
from src.finance.microstructure import compute_metrics
from src.finance.scoring import score_cross_section


def test_deterministic_fixture_and_timezone() -> None:
    first, second = build_demo(frames=10), build_demo(frames=10)
    assert len(first) == 12
    assert first["FPT"][7].to_dict() == second["FPT"][7].to_dict()
    assert first["FPT"][7].source == "simulated"
    assert first["FPT"][7].exchange_time.utcoffset() == timedelta(hours=7)
    assert first["FPT"][7].to_dict()["received_at"].endswith("+07:00")


def test_naive_timestamp_rejected() -> None:
    quote = build_demo(frames=1)["FPT"][0]
    with pytest.raises(ValueError):
        replace(quote, exchange_time=datetime(2026, 10, 26, 9, 15))


def test_duplicate_and_late_count_without_moving_clock_back() -> None:
    quotes = build_demo(frames=3)["FPT"]
    tracker = QualityTracker()
    assert tracker.inspect(quotes[1]) == []
    assert "duplicate" in tracker.inspect(replace(quotes[1], received_at=quotes[1].received_at + timedelta(seconds=1)))
    assert "late" in tracker.inspect(quotes[0])
    assert tracker.duplicate_count == tracker.late_count == 1
    assert tracker.latest["FPT"] == quotes[1].exchange_time


def test_crossed_and_missing_side_not_used_as_valid_metrics() -> None:
    quote = build_demo(frames=1)["FPT"][0]
    crossed = replace(quote, asks=(PriceLevel(quote.bids[0].price, 100),) + quote.asks[1:])
    assert "crossed_book" in quote_flags(crossed)
    assert compute_metrics(crossed)["mid"] is None
    assert "missing_side" in quote_flags(replace(quote, asks=()))


def test_stale_and_bad_level_order_flags() -> None:
    quote = build_demo(frames=1)["FPT"][0]
    assert "stale" in quote_flags(quote, quote.received_at + timedelta(seconds=61))
    assert "unsorted_bids" in quote_flags(replace(quote, bids=tuple(reversed(quote.bids))))


def test_no_future_leakage_and_warmup_incomplete_lqs() -> None:
    quotes = build_demo(frames=20)["FPT"]
    row = metrics_at(quotes, 4)
    assert row["amihud_5m"] is None
    assert score_cross_section([row])[0]["lqs"] is None
    assert metrics_at(quotes, 10) == metrics_at(quotes[:11], 10)
    assert metrics_at(quotes, 10)["amihud_5m"] is not None


def test_storage_wal_dedup_source_and_backup(tmp_path) -> None:
    quote = build_demo(frames=1)["FPT"][0]
    record = {"source": "simulated", "symbol": quote.symbol,
              "received_at": quote.received_at.isoformat(), "exchange_time": quote.exchange_time.isoformat(),
              "payload": quote.to_dict()}
    database, backup = tmp_path / "raw.sqlite", tmp_path / "backup.sqlite"
    with RawStorage(database) as storage:
        assert storage.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert storage.append_many([record, record]) == 1
        storage.backup(backup)
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT source,COUNT(*) FROM raw_market GROUP BY source").fetchone() == ("simulated", 1)


def test_storage_rejects_unlabelled_source(tmp_path) -> None:
    with RawStorage(tmp_path / "raw.sqlite") as storage:
        with pytest.raises(ValueError):
            storage.append_many([{"source": "unknown"}])


def test_empty_best_level_counts_as_invalid_even_with_deeper_liquidity() -> None:
    quote = build_demo(frames=1)["FPT"][0]
    invalid = replace(quote, bids=(PriceLevel(quote.bids[0].price, 0),) + quote.bids[1:])
    tracker = QualityTracker()
    assert "empty_best_level" in tracker.inspect(invalid)
    assert tracker.invalid_count == 1


def _raw_without_exchange_time() -> dict:
    return {"source": "simulated", "symbol": "TEST", "received_at": "2026-10-26T09:30:00+07:00",
            "exchange_time": None, "payload": {"symbol": "TEST", "price": 10000}}


def test_null_exchange_time_dedup_preserves_legitimate_repeat(tmp_path) -> None:
    record = _raw_without_exchange_time()
    with RawStorage(tmp_path / "raw.sqlite") as storage:
        assert storage.append_many([record, record]) == 1
        assert storage.append_many([dict(record, received_at="2026-10-26T09:30:01+07:00")]) == 1
        assert storage.append_many([dict(record, source="ssi")]) == 1
        assert storage.connection.execute("SELECT COUNT(*) FROM raw_market").fetchone()[0] == 3


@pytest.mark.parametrize("identity", [{"message_id": "m1"}, {"sequence": 0}])
def test_verified_message_identity_dedups_transport_retry(tmp_path, identity) -> None:
    record = dict(_raw_without_exchange_time(), **identity)
    retry = dict(record, received_at="2026-10-26T09:30:02+07:00")
    with RawStorage(tmp_path / "raw.sqlite") as storage:
        assert storage.append_many([record, retry]) == 1
        # Payload khác cùng ID được giữ để điều tra xung đột, không âm thầm mất raw.
        assert storage.append_many([dict(retry, payload={"symbol": "TEST", "price": 10050})]) == 1


@pytest.mark.parametrize("first_id,second_id", [
    ({"message_id": "m1"}, {"message_id": "m2"}),
    ({"sequence": 0}, {"sequence": 1}),
])
def test_distinct_verified_ids_are_not_collapsed_by_same_receive_time(tmp_path, first_id, second_id) -> None:
    record = _raw_without_exchange_time()
    first, second = dict(record, **first_id), dict(record, **second_id)
    with RawStorage(tmp_path / "raw.sqlite") as storage:
        assert storage.append_many([first, second]) == 2
        assert storage.append_many([dict(first, received_at="2026-10-26T09:30:01+07:00")]) == 0
        assert storage.connection.execute("SELECT COUNT(*) FROM raw_market").fetchone()[0] == 2


def test_storage_migration_keeps_legacy_null_duplicates(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite"
    record = _raw_without_exchange_time()
    payload = json.dumps(record["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha256(payload.encode()).hexdigest()
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE raw_market (id INTEGER PRIMARY KEY, source TEXT NOT NULL,
            symbol TEXT NOT NULL, received_at TEXT NOT NULL, exchange_time TEXT,
            payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
            UNIQUE(source,symbol,exchange_time,payload_sha256))""")
        values = ("simulated", "TEST", record["received_at"], None, payload, digest)
        connection.executemany("INSERT INTO raw_market (source,symbol,received_at,exchange_time,payload,payload_sha256) VALUES (?,?,?,?,?,?)", [values, values])
    with RawStorage(path) as storage:
        assert storage.connection.execute("SELECT COUNT(*) FROM raw_market").fetchone()[0] == 2
        assert storage.append_many([record]) == 0
        assert storage.append_many([dict(record, received_at="2026-10-26T09:30:01+07:00")]) == 1


def test_simulated_metrics_propagate_market_config_to_history() -> None:
    quotes = build_demo(frames=12)["FPT"]
    row = metrics_at(quotes, 10, 30_000_000, market={"lot_size": 200, "tick_bands": [[None, 100]]},
                     obi_level_weights=[1, 1, 1])
    assert row["obi_w"] == row["obi3"]
    assert row["buy"]["requested_shares"] % 200 == 0
    assert row == metrics_at(quotes[:11], 10, 30_000_000,
        market={"lot_size": 200, "tick_bands": [[None, 100]]}, obi_level_weights=[1, 1, 1])
    generated = build_demo(frames=2, market={"lot_size": 200, "tick_bands": [[None, 100]]})
    assert all(level.volume % 200 == 0 for quote in generated["FPT"] for level in quote.bids + quote.asks)


def test_trade_counter_reset_does_not_fabricate_amihud() -> None:
    quotes = build_demo(frames=12)["FPT"]
    quotes[8] = replace(quotes[8], cumulative_trade_value=100)
    row = metrics_at(quotes, 10)
    assert row["amihud_5m"] is None
    assert row["five_minute_trade_value_vnd"] is None
    assert "trade_counter_reset" in row["analytics_flags"]
    assert score_cross_section([row])[0]["lqs"] is None


def test_invalid_history_is_safe_and_gap_is_not_hidden() -> None:
    quotes = build_demo(frames=12)["FPT"]
    quotes[8] = replace(quotes[8], asks=())
    row = metrics_at(quotes, 10)
    assert row["two_sided_ratio"] < 1
    quotes[10] = replace(quotes[10], exchange_time=quotes[10].exchange_time + timedelta(minutes=1))
    row = metrics_at(quotes, 10)
    assert row["amihud_5m"] is None
    assert row["persistence"] is None
    assert "incomplete_five_minute_window" in row["analytics_flags"]


@pytest.mark.parametrize("missing_index", [5, 8, 9])
def test_missing_historical_record_preserves_current_book(missing_index: int) -> None:
    quotes = build_demo(frames=12)["FPT"]
    expected = compute_metrics(quotes[10])
    quotes[missing_index] = None
    row = metrics_at(quotes, 10)
    assert row["quality"] == "valid"
    assert row["spread_bps"] == expected["spread_bps"]
    assert row["obi_w"] == expected["obi_w"]
    assert row["amihud_5m"] is None
    assert row["two_sided_ratio"] is None
    assert row["persistence"] is None
    assert "missing_record_in_window" in row["analytics_flags"]
    assert score_cross_section([row])[0]["lqs"] is None
    assert row == metrics_at(quotes[:11], 10)


def test_missing_current_record_is_explicitly_unavailable() -> None:
    with pytest.raises(ValueError, match="Khung hiện tại"):
        metrics_at([None], 0)
