"""SQLite WAL cho raw thị trường, gắn nguồn rõ ràng để tách demo/dữ liệu thật."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from src.data.schema import VN_TZ


class RawStorage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS raw_market (
            id INTEGER PRIMARY KEY, source TEXT NOT NULL, symbol TEXT NOT NULL,
            received_at TEXT NOT NULL, exchange_time TEXT,
            payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
            UNIQUE(source, symbol, exchange_time, payload_sha256))""")
        # Migration bổ sung, không xóa bản ghi/duplicates đã tồn tại.
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(raw_market)")}
        if "ingest_key" not in columns:
            self.connection.execute("ALTER TABLE raw_market ADD COLUMN ingest_key TEXT")
        self.connection.execute("CREATE INDEX IF NOT EXISTS raw_market_ingest_key_idx ON raw_market(ingest_key)")
        self.connection.commit()

    def append_many(self, records: Iterable[dict[str, Any]]) -> int:
        prepared: list[tuple[tuple[str, str, str, str | None, str, str, str], bool]] = []
        for record in records:
            source = record.get("source")
            if source not in ("simulated", "ssi"):
                raise ValueError("Nguồn raw phải là simulated hoặc ssi.")
            received = datetime.fromisoformat(record["received_at"])
            exchange = datetime.fromisoformat(record["exchange_time"]) if record.get("exchange_time") else None
            if received.tzinfo is None or (exchange is not None and exchange.tzinfo is None):
                raise ValueError("Thời gian raw phải có múi giờ.")
            payload = json.dumps(record["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = sha256(payload.encode()).hexdigest()
            received_text = received.astimezone(VN_TZ).isoformat()
            exchange_text = exchange.astimezone(VN_TZ).isoformat() if exchange else None
            # message_id/sequence chỉ được adapter đã xác minh truyền vào.
            # Khi thiếu thời gian sàn và ID, chỉ dedup bản ghi nhận lại nguyên vẹn
            # tại cùng receive-time; không xóa update hợp lệ có payload giống nhau.
            if exchange_text is not None:
                identity = ["exchange_time", exchange_text]
            elif record.get("message_id") is not None:
                identity = ["message_id", record["message_id"]]
            elif record.get("sequence") is not None:
                identity = ["sequence", record["sequence"]]
            else:
                identity = ["received_at", received_text]
            key = sha256(json.dumps([source, record["symbol"], identity, digest],
                                    ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            prepared.append(((source, record["symbol"], received_text,
                              exchange_text, payload, digest, key),
                             identity[0] == "received_at"))
        before = self.connection.total_changes
        with self.connection:
            for values, allow_legacy_receive_match in prepared:
                source, symbol, received_text, exchange_text, _, digest, key = values
                # NOT EXISTS xử lý NULL theo nghĩa cụ thể, thay vì dựa UNIQUE(NULL).
                # Nhánh receive-time còn nhận diện chính xác bản legacy chưa có key.
                self.connection.execute("""INSERT OR IGNORE INTO raw_market
                    (source,symbol,received_at,exchange_time,payload,payload_sha256,ingest_key)
                    SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (
                        SELECT 1 FROM raw_market WHERE ingest_key=? OR
                        (?=1 AND ingest_key IS NULL AND source=? AND symbol=? AND exchange_time IS NULL AND ? IS NULL
                         AND received_at=? AND payload_sha256=?)
                    )""", values + (key, allow_legacy_receive_match, source, symbol, exchange_text, received_text, digest))
        return self.connection.total_changes - before

    def backup(self, target: str | Path) -> None:
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target_path) as destination:
            self.connection.backup(destination)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "RawStorage":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
