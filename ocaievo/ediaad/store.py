"""SQLite 落地：事件、提醒狀態與租約快取（AC-039）。

**為什麼要落地**：v0.2 的提醒去重狀態只在記憶體，程式重啟後同一事件會再提醒一次
（報告第 8.2 節第 1 點）。本模組把兩件事寫進 `$EDIAAD_HOME/ediaad.db`：

1. **事件**（`events` 表）：供事件歷史與系統狀態頁查詢。
2. **提醒狀態**（`alerts` 表）：去重鍵為 **（商品, 週期, 規律 ID, 事件開始時間）**，
   與 `monitor.AlertState` 的鍵定義完全相同（報告第 3.1 節 F11：用時間而非索引，
   因為不同輪次的序列長度會變、索引會位移）。因此跨程序去重只要
   `AlertState(seen=set(store.seen_keys()))` 就能接上，**不需要修改 `AlertState` 或
   `run_once` 的核心邏輯**。

另保留 `leases` 表作為租約快取的位置（SPEC 第 5 節把 `store.py` 的職責列為「事件、
提醒狀態、租約快取」）。

**公開介面**：`open_store(path)` 回傳 `Store`，其餘能力都是 `Store` 的方法——
`record_event`／`query_events`（事件）、`mark_alerted`／`seen_keys`／`is_alerted`／
`should_alert`（提醒狀態）、`put_lease`／`get_lease`（租約快取）、`journal_mode`、
`close`（支援 context manager）。`Store` 的連線是狀態，因此用方法而不是模組層函式。

**執行緒模型（TASK-021 接線時補上）**：Web handler 跑在 `ThreadingHTTPServer` 的工作
執行緒、監控迴圈跑在自己的執行緒，而 SQLite 連線**預設只能由建立它的執行緒使用**。因此
`open_store` 以 `check_same_thread=False` 開啟，並由 `Store` 內部的 `RLock` 序列化所有
存取——單一連線 ＋ WAL ＋ 序列化，對「每分鐘幾次寫入、偶爾查詢」的本機服務足夠，且不必
處理「每個執行緒一條連線、關閉時跨執行緒」的麻煩。

只使用標準庫 `sqlite3`；`open_store` 的 path 可注入，測試以 `tmp_path` 的真實資料庫檔
執行（SPEC 第 7 節明定不採用 mock）。
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigError, DataFormatError
from .monitor import EVENT_FIELDS

__all__ = ["Store", "open_store"]

#: 等鎖的最長時間（秒／毫秒）：短暫的並行寫入應該排隊，而不是立刻失敗。
BUSY_TIMEOUT_SECONDS = 5.0
BUSY_TIMEOUT_MS = int(BUSY_TIMEOUT_SECONDS * 1000)

#: 事件表的鍵（＝ `AlertState` 的去重鍵）。
KEY_FIELDS: tuple[str, ...] = ("symbol", "interval", "pattern_id", "event_start_time")

#: 需要是 ISO 字串的欄位（存原值以供查詢回傳，另存正規化值以供區間比較）。
_TIME_FIELDS: tuple[str, ...] = ("event_start_time", "event_end_time", "detected_at")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    pattern_id TEXT NOT NULL,
    event_start_time TEXT NOT NULL,
    event_start_at TEXT NOT NULL,
    event_end_time TEXT NOT NULL,
    confidence REAL NOT NULL,
    detected_at TEXT NOT NULL,
    history_up_probability REAL,
    history_samples INTEGER NOT NULL,
    PRIMARY KEY (symbol, interval, pattern_id, event_start_time)
);

CREATE TABLE IF NOT EXISTS alerts (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    pattern_id TEXT NOT NULL,
    event_start_time TEXT NOT NULL,
    alerted_at TEXT NOT NULL,
    PRIMARY KEY (symbol, interval, pattern_id, event_start_time)
);

CREATE TABLE IF NOT EXISTS leases (
    key_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _as_utc_text(value: Any, *, where: str) -> str:
    """把 ISO 時間正規化成 UTC（供區間比較）；要求含時區，避免本地時間歧義。"""
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise DataFormatError(f"{where} 必須是 ISO 時間字串，收到 {value!r}") from error
    if parsed.tzinfo is None:
        raise DataFormatError(f"{where} 必須含時區資訊（例如 +00:00 或 Z），收到 {value!r}")
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _require_text(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataFormatError(f"{where} 必須是非空字串，收到 {value!r}")
    return value


def _require_number(value: Any, *, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataFormatError(f"{where} 必須是數值，收到 {value!r}")
    return float(value)


def _require_int(value: Any, *, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataFormatError(f"{where} 必須是整數，收到 {value!r}")
    return value


def _require_key(key: Any) -> tuple[str, str, str, str]:
    if not isinstance(key, (tuple, list)) or len(key) != len(KEY_FIELDS):
        raise DataFormatError(
            f"去重鍵必須是 {len(KEY_FIELDS)} 項（{'、'.join(KEY_FIELDS)}），收到 {key!r}"
        )
    parts = []
    for name, value in zip(KEY_FIELDS, key):
        parts.append(_require_text(value, where=f"去重鍵的 {name}"))
    return (parts[0], parts[1], parts[2], parts[3])


def _validate_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DataFormatError(f"事件必須是物件，收到 {type(payload).__name__}")

    missing = [name for name in EVENT_FIELDS if name not in payload]
    if missing:
        raise DataFormatError(f"事件缺少欄位：{'、'.join(missing)}")

    record: dict[str, Any] = {}
    for name in ("symbol", "interval", "pattern_id"):
        record[name] = _require_text(payload[name], where=name)
    for name in _TIME_FIELDS:
        record[name] = _require_text(payload[name], where=name)
    record["confidence"] = _require_number(payload["confidence"], where="confidence")

    probability = payload["history_up_probability"]
    record["history_up_probability"] = (
        None if probability is None else _require_number(probability, where="history_up_probability")
    )
    record["history_samples"] = _require_int(payload["history_samples"], where="history_samples")
    return record


class Store:
    """`ediaad.db` 的存取物件（支援 context manager）。"""

    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self._connection = connection
        self.path = path
        # 所有存取都經過這把鎖：連線是跨執行緒共用的（見模組 docstring）。
        self._lock = threading.RLock()

    def _connection_or_raise(self) -> sqlite3.Connection:
        """明確檢查連線狀態。

        不用 `assert`：`assert` 在 `python -O` 下會被整段移除，控制流程就消失了
        （接著會變成對 `None` 呼叫方法的 `AttributeError`）。
        """
        if self._connection is None:
            raise ConfigError(f"store（{self.path}）已關閉，無法再存取")
        return self._connection

    def close(self) -> None:
        """關閉連線；重複呼叫為幂等。"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @property
    def journal_mode(self) -> str:
        """目前的 journal 模式（`wal` 表示並行寫入有 write-ahead logging 保護）。"""
        with self._lock:
            connection = self._connection_or_raise()
            return str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()

    # ---- 事件 ----

    def record_event(self, payload: Mapping[str, Any]) -> None:
        """寫入一筆事件；同一去重鍵重複寫入時更新內容（不產生重複列）。"""
        record = _validate_event(payload)
        start_at = _as_utc_text(record["event_start_time"], where="event_start_time")
        with self._lock:
            connection = self._connection_or_raise()
            connection.execute(
                """
                INSERT INTO events (
                symbol, interval, pattern_id, event_start_time, event_start_at,
                event_end_time, confidence, detected_at, history_up_probability,
                history_samples
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, interval, pattern_id, event_start_time) DO UPDATE SET
                event_start_at = excluded.event_start_at,
                event_end_time = excluded.event_end_time,
                confidence = excluded.confidence,
                detected_at = excluded.detected_at,
                history_up_probability = excluded.history_up_probability,
                history_samples = excluded.history_samples
            """,
            (
                record["symbol"],
                record["interval"],
                record["pattern_id"],
                record["event_start_time"],
                start_at,
                record["event_end_time"],
                record["confidence"],
                record["detected_at"],
                record["history_up_probability"],
                record["history_samples"],
            ),
        )
        connection.commit()

    def query_events(
        self,
        symbol: str | None = None,
        start: Any = None,
        end: Any = None,
    ) -> list[dict[str, Any]]:
        """依商品與時間區間（**含起訖端點**）查詢事件，依事件開始時間升冪排序。"""
        clauses: list[str] = []
        parameters: list[Any] = []
        if symbol is not None:
            clauses.append("symbol = ?")
            parameters.append(_require_text(symbol, where="symbol"))
        if start is not None:
            clauses.append("event_start_at >= ?")
            parameters.append(_as_utc_text(start, where="start"))
        if end is not None:
            normalized_end = _as_utc_text(end, where="end")
            clauses.append("event_start_at <= ?")
            parameters.append(normalized_end)
            if start is not None and parameters[-2] > normalized_end:
                # 與 `markets.adjust.fetch_ex_rights` 一致：反轉的區間是呼叫端的設定錯誤。
                raise ConfigError(
                    f"結束時間（{normalized_end}）不得早於開始時間（{parameters[-2]}）"
                )

        # 明確列出欄位並以**名稱**取值：不靠位置對應，日後新增欄位也不會位移
        # （TWSE 解析與 F-001 的教訓：位置對應是靜默錯誤的來源）。
        sql = f"SELECT {', '.join(EVENT_FIELDS)} FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY event_start_at ASC, symbol ASC, interval ASC, pattern_id ASC"

        with self._lock:
            connection = self._connection_or_raise()
            cursor = connection.execute(sql, parameters)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    # ---- 提醒狀態 ----

    def mark_alerted(self, key: Any, *, alerted_at: Any = None) -> None:
        """記錄某個去重鍵已提醒；重複呼叫為幂等。"""
        parts = _require_key(key)
        stamp = _as_utc_text(alerted_at, where="alerted_at") if alerted_at is not None else _now_iso()
        with self._lock:
            connection = self._connection_or_raise()
            connection.execute(
                """
                INSERT OR IGNORE INTO alerts (
                symbol, interval, pattern_id, event_start_time, alerted_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (*parts, stamp),
        )
        connection.commit()

    def seen_keys(self) -> set[tuple[str, str, str, str]]:
        """所有已提醒的去重鍵（可直接交給 `AlertState(seen=...)`）。"""
        with self._lock:
            connection = self._connection_or_raise()
            cursor = connection.execute(
                "SELECT symbol, interval, pattern_id, event_start_time FROM alerts"
            )
            return {(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()}

    def is_alerted(self, key: Any) -> bool:
        return _require_key(key) in self.seen_keys()

    def should_alert(self, key: Any) -> bool:
        """與 `AlertState.should_alert` 同義（落地版本）。"""
        return not self.is_alerted(key)

    # ---- 租約快取（TASK-029 會使用） ----

    def put_lease(self, key_id: str, payload: str, *, fetched_at: Any = None) -> None:
        identifier = _require_text(key_id, where="key_id")
        stamp = _as_utc_text(fetched_at, where="fetched_at") if fetched_at is not None else _now_iso()
        with self._lock:
            connection = self._connection_or_raise()
            connection.execute(
                "INSERT OR REPLACE INTO leases (key_id, payload, fetched_at) VALUES (?, ?, ?)",
            (identifier, payload, stamp),
        )
        connection.commit()

    def get_lease(self, key_id: str) -> str | None:
        with self._lock:
            connection = self._connection_or_raise()
            cursor = connection.execute(
                "SELECT payload FROM leases WHERE key_id = ?",
                (_require_text(key_id, where="key_id"),),
            )
            row = cursor.fetchone()
            return None if row is None else row[0]


def open_store(path: str | Path) -> Store:
    """開啟（必要時建立）SQLite 資料庫並確保 schema 存在。"""
    store_path = Path(path)
    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ConfigError(f"無法建立資料庫目錄 {store_path.parent}：{error}") from error

    try:
        connection = sqlite3.connect(
            str(store_path), timeout=BUSY_TIMEOUT_SECONDS, check_same_thread=False
        )
    except sqlite3.Error as error:
        raise DataFormatError(f"無法開啟資料庫 {store_path}：{error}") from error

    try:
        # WAL 讓「另一個程序正在讀」時仍可寫入；busy_timeout 讓短暫的鎖等待而不是立刻失敗。
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        connection.executescript(_SCHEMA)
        connection.commit()
    except sqlite3.DatabaseError as error:
        connection.close()
        raise DataFormatError(
            f"資料庫 {store_path} 無法使用（檔案損毀或不是 SQLite 資料庫）：{error}"
        ) from error

    return Store(connection, store_path)
