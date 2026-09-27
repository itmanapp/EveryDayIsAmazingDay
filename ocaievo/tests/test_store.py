"""SQLite 落地與跨程序提醒去重（TASK-018）。

觀察邊界：以 `tmp_path` 下的**真實** SQLite 檔與真實檔案系統驗證（SPEC 第 7 節明定
`ediaad.store` 不能只對 mock 宣稱通過）；跨程序情境另以 `subprocess` 執行短腳本。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ediaad.errors import ConfigError, DataFormatError
from ediaad.monitor import AlertState

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"

KEY = ("2330", "1d", "range_fakeout_reversion", "2024-07-01T00:00:00+00:00")


def event(
    *,
    symbol: str = "2330",
    interval: str = "1d",
    pattern_id: str = "range_fakeout_reversion",
    event_start_time: str = "2024-07-01T00:00:00+00:00",
    event_end_time: str = "2024-07-05T00:00:00+00:00",
    confidence: float = 0.75,
    detected_at: str = "2024-07-06T01:00:00+00:00",
    history_up_probability: float | None = 0.6,
    history_samples: int = 5,
) -> dict:
    return {
        "symbol": symbol,
        "interval": interval,
        "pattern_id": pattern_id,
        "event_start_time": event_start_time,
        "event_end_time": event_end_time,
        "confidence": confidence,
        "detected_at": detected_at,
        "history_up_probability": history_up_probability,
        "history_samples": history_samples,
    }


# ---- AC-039：開檔、建表與寫入 -----------------------------------------------


def test_opening_an_empty_database_creates_the_schema(tmp_path):
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as store:
        assert store.path == path
        assert store.seen_keys() == set()

    assert path.is_file(), "開啟時就應該建立資料庫檔"


def test_opening_creates_missing_parent_directories(tmp_path):
    from ediaad.store import open_store

    path = tmp_path / "home" / "nested" / "ediaad.db"
    with open_store(path):
        pass

    assert path.is_file()


def test_record_event_and_query_it_back(tmp_path):
    from ediaad.store import open_store

    written = event()
    with open_store(tmp_path / "ediaad.db") as store:
        store.record_event(written)

    with open_store(tmp_path / "ediaad.db") as store:
        rows = store.query_events()

    assert len(rows) == 1
    assert rows[0] == written, "查詢結果的欄位與寫入值必須一致（含型別）"


def test_recording_the_same_event_twice_updates_instead_of_duplicating(tmp_path):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        store.record_event(event(confidence=0.5, history_samples=3))
        store.record_event(event(confidence=0.9, history_samples=7))
        rows = store.query_events()

    assert len(rows) == 1, "同一事件的鍵相同時不得產生重複列"
    assert rows[0]["confidence"] == pytest.approx(0.9)
    assert rows[0]["history_samples"] == 7


@pytest.mark.parametrize("missing", ["symbol", "confidence", "history_samples"])
def test_record_event_rejects_an_incomplete_event(tmp_path, missing):
    from ediaad.store import open_store

    payload = event()
    payload.pop(missing)

    with open_store(tmp_path / "ediaad.db") as store:
        with pytest.raises(DataFormatError, match=missing):
            store.record_event(payload)


def test_record_event_rejects_a_blank_symbol(tmp_path):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        with pytest.raises(DataFormatError, match="symbol"):
            store.record_event(event(symbol="  "))


def test_mark_alerted_is_idempotent_and_lists_the_key(tmp_path):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        store.mark_alerted(KEY)
        store.mark_alerted(KEY)

        assert store.seen_keys() == {KEY}
        assert store.is_alerted(KEY) is True
        assert store.is_alerted(("9999", "1d", "p", "2024-07-01T00:00:00+00:00")) is False


def test_mark_alerted_rejects_a_malformed_key(tmp_path):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        for bad in (("a", "b", "c"), "not-a-key", ("a", "b", "c", ""), ("a", "b", "c", 7)):
            with pytest.raises(DataFormatError, match="去重鍵|鍵"):
                store.mark_alerted(bad)


# ---- AC-039：跨程序去重 -----------------------------------------------------


def test_dedup_survives_a_new_store_instance(tmp_path):
    """先後兩個 `Store` 實例模擬程序重啟：第二次必須看到第一次的提醒。"""
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as first:
        assert first.should_alert(KEY) is True
        first.mark_alerted(KEY)
        first.record_event(event())

    with open_store(path) as second:
        assert second.seen_keys() == {KEY}
        assert second.should_alert(KEY) is False, "重啟後同一事件不得再提醒"


def test_the_store_hydrates_an_alert_state_without_touching_monitor(tmp_path):
    """`AlertState` 的核心邏輯不變：以既有的 `seen` 補齊落地狀態即可。"""
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as first:
        first.mark_alerted(KEY)

    with open_store(path) as second:
        state = AlertState(seen=set(second.seen_keys()))

    assert state.should_alert(KEY) is False
    assert state.should_alert(("2330", "1d", "range_fakeout_reversion", "2024-08-01T00:00:00+00:00")) is True


def test_a_separate_process_sees_the_alert(tmp_path):
    """真正的跨程序驗證：另一個 Python 程序開啟同一個資料庫。"""
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as store:
        store.mark_alerted(KEY)

    script = (
        "import json, sys;"
        "from ediaad.store import open_store;"
        "s = open_store(sys.argv[1]);"
        "print(json.dumps({'seen': sorted(list(k) for k in s.seen_keys()),"
        " 'should_alert': s.should_alert(tuple(sys.argv[2:6]))}))"
    )
    completed = subprocess.run(
        [str(PYTHON), "-c", script, str(path), *KEY],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["seen"] == [list(KEY)]
    assert payload["should_alert"] is False, "另一個程序必須看到已提醒狀態"


# ---- AC-039：查詢邊界 -------------------------------------------------------


def seed_events(tmp_path: Path) -> Path:
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as store:
        store.record_event(event(symbol="2330", event_start_time="2024-07-01T00:00:00+00:00"))
        store.record_event(event(symbol="2330", event_start_time="2024-07-15T00:00:00+00:00"))
        store.record_event(event(symbol="2317", event_start_time="2024-07-10T00:00:00+00:00"))
    return path


def test_query_events_filters_by_symbol(tmp_path):
    from ediaad.store import open_store

    path = seed_events(tmp_path)
    with open_store(path) as store:
        rows = store.query_events(symbol="2330")

    assert [row["event_start_time"] for row in rows] == [
        "2024-07-01T00:00:00+00:00",
        "2024-07-15T00:00:00+00:00",
    ]
    assert all(row["symbol"] == "2330" for row in rows)


def test_query_events_includes_both_range_endpoints(tmp_path):
    from ediaad.store import open_store

    path = seed_events(tmp_path)
    with open_store(path) as store:
        inclusive = store.query_events(start="2024-07-01T00:00:00+00:00", end="2024-07-15T00:00:00+00:00")
        narrow = store.query_events(start="2024-07-02T00:00:00+00:00", end="2024-07-14T00:00:00+00:00")
        empty = store.query_events(start="2024-08-01T00:00:00+00:00")

    assert len(inclusive) == 3, "起訖端點都必須含在區間內"
    assert [row["symbol"] for row in narrow] == ["2317"]
    assert empty == []


def test_query_events_sorts_by_start_time_then_symbol(tmp_path):
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as store:
        store.record_event(event(symbol="9999", event_start_time="2024-07-01T00:00:00+00:00"))
        store.record_event(event(symbol="1111", event_start_time="2024-07-01T00:00:00+00:00"))
        store.record_event(event(symbol="5555", event_start_time="2024-06-30T00:00:00+00:00"))
        rows = store.query_events()

    assert [(row["event_start_time"], row["symbol"]) for row in rows] == [
        ("2024-06-30T00:00:00+00:00", "5555"),
        ("2024-07-01T00:00:00+00:00", "1111"),
        ("2024-07-01T00:00:00+00:00", "9999"),
    ]


@pytest.mark.parametrize(
    ("written", "start", "end", "expected"),
    [
        pytest.param(
            "2024-07-01T08:00:00+08:00",
            "2024-06-30T23:59:00+00:00",
            "2024-07-01T00:01:00+00:00",
            True,
            id="正偏移且 UTC 較早：應命中",
        ),
        pytest.param(
            "2024-06-30T20:00:00-08:00",
            "2024-07-01T00:00:00+00:00",
            "2024-07-01T04:01:00+00:00",
            True,
            id="負偏移且 UTC 較晚：應命中（原始字串比較會誤判為較早）",
        ),
        pytest.param(
            "2024-07-01T08:00:00+08:00",
            "2024-07-01T00:30:00+00:00",
            "2024-07-01T01:00:00+00:00",
            False,
            id="正偏移但 UTC 早於起點：不應命中（原始字串比較會誤判為較晚）",
        ),
    ],
)
def test_query_events_normalises_offsets_for_comparison(tmp_path, written, start, end, expected):
    """區間比較用**正規化後的 UTC**；用原始字串比較會出現兩種方向的誤判。"""
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as store:
        store.record_event(event(event_start_time=written))
        rows = store.query_events(start=start, end=end)

    assert (len(rows) == 1) is expected
    if expected:
        assert rows[0]["event_start_time"] == written, "回傳原始寫入值"


@pytest.mark.parametrize("bad", ["not-a-time", "2024-07-01T00:00:00", 7])
def test_naive_or_bad_times_are_rejected(tmp_path, bad):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        with pytest.raises(DataFormatError):
            store.record_event(event(event_start_time=bad))
        with pytest.raises(DataFormatError):
            store.query_events(start=bad)


# ---- 租約快取（TASK-029 會使用） --------------------------------------------


def test_lease_cache_round_trip_and_replace(tmp_path):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        assert store.get_lease("EDIAAD-2026-0001") is None
        store.put_lease("EDIAAD-2026-0001", '{"v": 1}')
        assert store.get_lease("EDIAAD-2026-0001") == '{"v": 1}'
        store.put_lease("EDIAAD-2026-0001", '{"v": 2}')
        assert store.get_lease("EDIAAD-2026-0001") == '{"v": 2}'


# ---- 強健性：損毀檔、並行與連線釋放 -----------------------------------------


def test_an_empty_file_is_initialised_as_a_new_database(tmp_path):
    """0 位元組的檔案對 SQLite 而言是「全新的資料庫」（例如中斷的下載所留下）。"""
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    path.write_bytes(b"")

    with open_store(path) as store:
        assert store.seen_keys() == set()
        store.record_event(event())
        assert len(store.query_events()) == 1


@pytest.mark.parametrize(
    "corrupt",
    [
        pytest.param(b"this is not a database" * 10, id="隨機位元組"),
        pytest.param(b"SQLite format 3\x00" + b"\x00" * 40, id="標頭正確但內容全零"),
        pytest.param(b"\xff" * 4096, id="全 0xff"),
    ],
)
def test_a_corrupt_database_file_gives_a_readable_error(tmp_path, corrupt):
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    path.write_bytes(corrupt)

    result = None
    try:
        with open_store(path):
            pass
    except DataFormatError as error:
        result = error

    assert result is not None, "損毀的資料庫必須是可讀的 DataFormatError，不是 sqlite3 的原始例外"
    assert "ediaad.db" in str(result)


def test_two_connections_do_not_lose_events(tmp_path):
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as first, open_store(path) as second:
        first.record_event(event(symbol="2330", event_start_time="2024-07-01T00:00:00+00:00"))
        second.record_event(event(symbol="2317", event_start_time="2024-07-02T00:00:00+00:00"))

        assert len(first.query_events()) == 2
        assert len(second.query_events()) == 2
        assert first.seen_keys() == second.seen_keys()


def test_the_database_uses_write_ahead_logging(tmp_path):
    from ediaad.store import open_store

    with open_store(tmp_path / "ediaad.db") as store:
        assert store.journal_mode == "wal", "並行寫入需要 WAL（或等價的鎖定策略）"


def test_closing_releases_the_connection_and_is_idempotent(tmp_path):
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    store = open_store(path)
    store.record_event(event())
    store.close()
    store.close()

    with open_store(path) as reopened:
        assert len(reopened.query_events()) == 1
        assert reopened.seen_keys() == set()


def test_leaving_the_context_manager_closes_the_store(tmp_path):
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    with open_store(path) as store:
        store.mark_alerted(KEY)

    with open_store(path) as reopened:
        assert reopened.is_alerted(KEY) is True


def test_writes_are_visible_to_a_separate_process(tmp_path):
    """跨程序不只讀得到，也寫得進去（事件與提醒狀態都落地）。"""
    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    script = (
        "import sys;"
        "from ediaad.store import open_store;"
        "s = open_store(sys.argv[1]);"
        "s.record_event({'symbol': '2330', 'interval': '1d',"
        " 'pattern_id': 'range_fakeout_reversion',"
        " 'event_start_time': '2024-09-01T00:00:00+00:00',"
        " 'event_end_time': '2024-09-05T00:00:00+00:00', 'confidence': 0.5,"
        " 'detected_at': '2024-09-06T00:00:00+00:00',"
        " 'history_up_probability': None, 'history_samples': 2});"
        "s.mark_alerted(('2330', '1d', 'range_fakeout_reversion', '2024-09-01T00:00:00+00:00'));"
        "s.close();"
        "print('ok')"
    )
    subprocess.run(
        [str(PYTHON), "-c", script, str(path)],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )

    with open_store(path) as store:
        assert len(store.query_events(symbol="2330")) == 1
        assert len(store.seen_keys()) == 1


def test_using_a_closed_store_gives_a_readable_error(tmp_path):
    """控制流程不用 `assert`（`python -O` 會移除它），關閉後必須是可讀的領域錯誤。"""
    from ediaad.errors import ConfigError
    from ediaad.store import open_store

    store = open_store(tmp_path / "ediaad.db")
    store.close()

    for action in (
        lambda: store.seen_keys(),
        lambda: store.query_events(),
        lambda: store.record_event(event()),
        lambda: store.mark_alerted(KEY),
        lambda: store.get_lease("k"),
        lambda: store.journal_mode,
    ):
        with pytest.raises(ConfigError, match="已關閉"):
            action()


def test_a_reversed_range_is_rejected(tmp_path):
    from ediaad.store import open_store

    path = seed_events(tmp_path)
    with open_store(path) as store:
        with pytest.raises(ConfigError, match="不得早於"):
            store.query_events(
                start="2024-07-15T00:00:00+00:00", end="2024-07-01T00:00:00+00:00"
            )


def test_the_store_can_be_used_from_several_threads(tmp_path):
    """Web handler 與監控迴圈跑在不同的執行緒：SQLite 預設會拒絕跨執行緒使用連線。

    TASK-021 接線時才發現這件事（`Application.create` 在主執行緒開檔，HTTP handler 在
    `ThreadingHTTPServer` 的工作執行緒查詢 → `ProgrammingError`）。
    """
    import threading

    from ediaad.store import open_store

    path = tmp_path / "ediaad.db"
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for turn in range(5):
                store.record_event(
                    event(
                        symbol=f"S{index}",
                        event_start_time=f"2024-07-{turn + 1:02d}T00:00:00+00:00",
                    )
                )
                assert store.seen_keys() == set()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    with open_store(path) as store:
        threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == [], f"跨執行緒使用不得失敗：{errors}"
        assert len(store.query_events()) == 20
