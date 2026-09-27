"""更新檢查子系統與六條架構約束（TASK-032／AC-059）。

觀察邊界：
1. **模組（自動）**：`check_update`／`fetch_catalog`／`load_cache`／`save_cache`／`parse_manifest`
   的行為與六條約束；HTTP 與時鐘全部注入，全程離線（不得連向任何真實位址）。
2. **服務（自動）**：`Application.start()`、網頁請求、`run_monitor_round()` 三者都不被更新
   檢查阻塞；`/api/version` 立即回快取並在背景檢查、且去抖動。
3. **頁面（自動，需 `node`）**：`version.js` 區分「尚未檢查」「檢查中」「已關閉」「檢查失敗」。

六條約束的對應測試見各 Cycle 標題。
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ediaad.errors import ConfigError, SourceError
from ediaad.markets.base import Instrument, register, unregister
from ediaad.markets.catalog import load_catalog
from ediaad.monitor import validate_config
from ediaad.paths import update_state_path
from ediaad.update import (
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_TIMEOUT,
    UpdateState,
    check_update,
    fetch_catalog,
    load_cache,
    parse_manifest,
    save_cache,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
MANIFEST_URL = "https://update.example.invalid/v1/latest"
CATALOG_URL = "https://update.example.invalid/ediaad/catalog.json"
DOWNLOAD_URL = "https://update.example.invalid/ediaad/ediaad-0.4.0.tar.gz"


def manifest(**overrides) -> dict:
    """合成 manifest（欄位同報告第 6.5 節）。"""
    payload = {
        "schema": 1,
        "version": "0.4.0",
        "released_at": "2026-10-01T00:00:00Z",
        "min_supported": "0.3.0",
        "notes": "新增台股來源與桌面通知",
        "catalog_version": "2026-10-01",
        "catalog_url": CATALOG_URL,
        "url": DOWNLOAD_URL,
        "sha256": "ab" * 32,
        "size": 1048576,
    }
    payload.update(overrides)
    return payload


def cached_state(**overrides) -> UpdateState:
    fields = {
        "latest_version": "0.3.0",
        "released_at": "2026-09-01T00:00:00Z",
        "min_supported": "0.2.0",
        "notes": "舊版說明",
        "catalog_version": "2026-09-01",
        "catalog_url": CATALOG_URL,
        "checked_at": "2026-10-02T11:00:00Z",
        "source": "network",
        "error": None,
    }
    fields.update(overrides)
    return UpdateState(**fields)


class FakeHttp:
    """假 HTTP 客戶端（介面同 `update.http_get`：`get(url, timeout) -> (status, body)`）。"""

    def __init__(self, responses=None, *, error: Exception | None = None, block=None) -> None:
        self.responses = dict(responses or {MANIFEST_URL: (200, json.dumps(manifest()))})
        self.error = error
        self.block = block
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, timeout: float = DEFAULT_TIMEOUT):
        self.calls.append((url, timeout))
        if self.block is not None:
            self.block.wait(30)
        if self.error is not None:
            raise self.error
        response = self.responses.get(url)
        if response is None:
            return 404, "not found"
        if callable(response):
            return response(url)
        return response

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]


class RecordingExecutor:
    """記錄被交付的工作但**不執行**：讓「立即返回」與「背景真的做了什麼」都可斷言。"""

    def __init__(self) -> None:
        self.tasks: list = []

    def submit(self, function):
        self.tasks.append(function)

    def run_all(self) -> None:
        for task in list(self.tasks):
            task()


def check(http, cache_path, **overrides):
    kwargs = {
        "http": http,
        "manifest_url": MANIFEST_URL,
        "cache_path": cache_path,
        "now": NOW,
    }
    kwargs.update(overrides)
    return check_update(**kwargs)


# ---- Cycle 1：manifest 解析、快取往返與「只顯示不下載不安裝」 -------------------


def test_manifest_is_parsed_and_cached(tmp_path):
    http = FakeHttp()
    cache = tmp_path / "update.json"

    state = check(http, cache)

    assert state.latest_version == "0.4.0"
    assert state.released_at == "2026-10-01T00:00:00Z"
    assert state.min_supported == "0.3.0"
    assert state.notes == "新增台股來源與桌面通知"
    assert state.catalog_version == "2026-10-01"
    assert state.catalog_url == CATALOG_URL
    assert state.source == "network"
    assert state.error is None
    assert state.checked_at == "2026-10-02T12:00:00Z"
    assert http.calls == [(MANIFEST_URL, DEFAULT_TIMEOUT)]
    assert load_cache(cache) == state


def test_cache_round_trip_and_corrupt_cache_is_ignored(tmp_path):
    cache = tmp_path / "update.json"
    assert load_cache(cache) is None

    save_cache(cache, cached_state())
    assert load_cache(cache) == cached_state()

    cache.write_text("{not json", encoding="utf-8")
    assert load_cache(cache) is None, "損毀的快取不得讓版本頁壞掉"

    cache.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    assert load_cache(cache) is None

    cache.write_bytes(b"\xff\xfe\x00\x01")
    assert load_cache(cache) is None, "非 UTF-8 的快取同樣只是「沒有可用快取」"


def test_cache_rejects_wrong_types_and_non_states(tmp_path):
    cache = tmp_path / "update.json"

    with pytest.raises(ConfigError):
        save_cache(cache, "not a state")
    with pytest.raises(ConfigError):
        UpdateState.from_json(json.dumps(["not", "an", "object"]))
    with pytest.raises(ConfigError):
        UpdateState.from_json(json.dumps({"latest_version": 5}))
    assert not cache.exists(), "不合法的内容不得落地"


@pytest.mark.parametrize(
    "payload, fragment",
    [
        (manifest(schema=2), "schema"),
        (manifest(version=""), "version"),
        (manifest(released_at=None), "released_at"),
        (["not", "an", "object"], "物件"),
    ],
)
def test_manifest_validation_rejects_bad_payloads(payload, fragment):
    with pytest.raises(ConfigError) as error:
        parse_manifest(payload)
    assert fragment in str(error.value)


@pytest.mark.parametrize(
    "body",
    ["{not json", "", "<html>維護中</html>"],
)
def test_unparseable_manifest_is_silent_and_records_the_error(tmp_path, body, capsys, caplog):
    http = FakeHttp({MANIFEST_URL: (200, body)})
    cache = tmp_path / "update.json"

    state = check(http, cache)

    assert state.latest_version is None
    assert state.error and "JSON" in state.error
    assert load_cache(cache) is not None, "失敗也要記狀態"
    assert capsys.readouterr().out == "" and capsys.readouterr().err == ""
    assert [record for record in caplog.records if record.levelname == "ERROR"] == []


def test_update_never_downloads_or_installs(tmp_path):
    """約束 7：只讀 manifest 的顯示欄位，不抓 `url`／`sha256`，也不在快取外寫任何檔案。"""
    http = FakeHttp()
    cache = tmp_path / "update.json"
    before = sorted(item.name for item in tmp_path.iterdir())

    check(http, cache)

    assert http.urls == [MANIFEST_URL], "不得對下載位址發出請求"
    assert DOWNLOAD_URL not in http.urls
    assert sorted(item.name for item in tmp_path.iterdir()) == before + ["update.json"]


# ---- Cycle 2：約束 1「逾時上限 5 秒」 ----------------------------------------


def test_default_timeout_is_five_seconds(tmp_path):
    http = FakeHttp()
    check(http, tmp_path / "update.json")
    assert http.calls[0][1] == 5.0 == DEFAULT_TIMEOUT


def test_blocking_http_returns_within_the_deadline(tmp_path, capsys):
    """會卡住的客戶端也必須在期限內回來：逾時是硬上限，不只是 socket 選項。"""
    release = threading.Event()
    http = FakeHttp(block=release)
    cache = tmp_path / "update.json"

    started = time.monotonic()
    state = check(http, cache, timeout=0.2)
    elapsed = time.monotonic() - started

    assert elapsed < 0.4, f"must not wait for the socket timeout（實測 {elapsed:.3f}s）"
    assert http.calls[0][1] == 0.2, "同一個值要同時給 socket 與硬上限"
    assert state.error and "逾時" in state.error
    assert state.latest_version is None
    assert capsys.readouterr().out == "" and capsys.readouterr().err == ""

    workers = [item for item in threading.enumerate() if item.name.startswith("ediaad-update")]
    assert workers and all(item.daemon for item in workers), "卡住的工作必須是 daemon，不能阻止行程結束"
    release.set()


# ---- Cycle 3：約束 3「失敗一律靜默，只記狀態」 --------------------------------


def test_transport_failure_is_silent(tmp_path, capsys, caplog):
    http = FakeHttp(error=SourceError("連線失敗"))
    cache = tmp_path / "update.json"

    state = check(http, cache)

    assert state.error and "連線失敗" in state.error
    assert state.source == "network" and state.latest_version is None
    assert load_cache(cache).error is not None
    assert capsys.readouterr().out == "" and capsys.readouterr().err == ""
    assert [record for record in caplog.records if record.levelname in {"ERROR", "CRITICAL"}] == []


def test_http_500_keeps_the_previous_display_values(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-02T05:00:00Z"))
    http = FakeHttp({MANIFEST_URL: (500, "boom")})

    state = check(http, cache)

    assert state.source == "cache", "顯示的資料來自快取"
    assert state.latest_version == "0.3.0" and state.notes == "舊版說明"
    assert state.error and "500" in state.error
    assert load_cache(cache).latest_version == "0.3.0", "失敗不得抹掉已知的顯示資料"


def test_http_404_is_recorded_as_an_error(tmp_path):
    http = FakeHttp({MANIFEST_URL: (404, "not found")})
    state = check(http, tmp_path / "update.json")
    assert state.error and "404" in state.error


# ---- Cycle 4：約束 4「先回快取、背景檢查」 ------------------------------------


def test_background_check_returns_the_cached_result_immediately(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-01T00:00:00Z"))
    http = FakeHttp()
    executor = RecordingExecutor()

    state = check(http, cache, background=True, executor=executor)

    assert state.source == "cache" and state.latest_version == "0.3.0"
    assert http.calls == [], "呼叫端不得等待網路"
    assert len(executor.tasks) == 1


def test_background_check_without_cache_reports_pending(tmp_path):
    http = FakeHttp()
    executor = RecordingExecutor()

    state = check(http, tmp_path / "update.json", background=True, executor=executor)

    assert state.source == "pending"
    assert state.latest_version is None
    assert http.calls == []
    assert len(executor.tasks) == 1


def test_background_task_refreshes_cache_and_reports_the_result(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-01T00:00:00Z"))
    http = FakeHttp()
    executor = RecordingExecutor()
    results: list[UpdateState] = []

    check(http, cache, background=True, executor=executor, on_result=results.append)
    executor.run_all()

    assert http.urls == [MANIFEST_URL]
    assert len(results) == 1 and results[0].source == "network"
    assert results[0].latest_version == "0.4.0"
    assert load_cache(cache).latest_version == "0.4.0"


def test_background_failure_is_recorded_through_the_callback(tmp_path, capsys):
    http = FakeHttp(error=SourceError("斷線"))
    executor = RecordingExecutor()
    results: list[UpdateState] = []

    check(http, tmp_path / "update.json", background=True, executor=executor, on_result=results.append)
    executor.run_all()

    assert len(results) == 1 and results[0].error and "斷線" in results[0].error
    assert capsys.readouterr().out == "" and capsys.readouterr().err == ""


def test_background_respects_the_debounce(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-02T11:59:00Z"))
    http = FakeHttp()
    executor = RecordingExecutor()
    results: list[UpdateState] = []

    state = check(http, cache, background=True, executor=executor, on_result=results.append)

    assert state.source == "network"
    assert executor.tasks == [] and http.calls == [] and results == []


def test_background_without_an_executor_uses_a_daemon_thread(tmp_path):
    """沒有注入執行器時，背景工作必須是**具名 daemon 執行緒**，而且會完成。

    以 `join()` 等它而不是輪詢檔案：join 直接等在那個執行緒上（沒有檔案輪詢的競態），
    也會在它真的卡住時給出可讀的失敗。第一版用 10 秒輪詢，在整套測試的高負載下曾
    間歇性失敗；第二版放寬到 30 秒仍然偶發，因此改成 join 並一併斷言 daemon 性質
    （這正是測試名稱所宣稱的事）。
    """
    cache = tmp_path / "update.json"
    http = FakeHttp()

    state = check(http, cache, background=True)

    assert state.source == "pending" and http.calls == []
    workers = [item for item in threading.enumerate() if item.name == "ediaad-update-check"]
    assert workers, "預設路徑必須建立背景執行緒"
    assert all(item.daemon for item in workers), "背景執行緒必須是 daemon，不能阻止行程結束"
    for worker in workers:
        worker.join(timeout=60)
    assert not any(item.is_alive() for item in workers), "背景檢查必須在期限內結束"

    assert http.urls == [MANIFEST_URL]
    assert load_cache(cache).latest_version == "0.4.0"


# ---- Cycle 5：約束 5「去抖動 5 分鐘」 ----------------------------------------


def test_debounce_blocks_the_second_request_within_five_minutes(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-02T11:55:01Z"))  # 299 秒前

    http = FakeHttp()
    state = check(http, cache)

    assert state.source == "network", "沿用上次檢查的來源標記（資料確實來自那次網路檢查）"
    assert state.latest_version == "0.3.0"
    assert http.calls == [], "五分鐘內不得重複發出請求"
    assert DEFAULT_DEBOUNCE_SECONDS == 300


def test_debounce_expires_at_five_minutes(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-02T11:55:00Z"))  # 正好 300 秒前

    http = FakeHttp()
    state = check(http, cache)

    assert state.source == "network" and state.latest_version == "0.4.0"
    assert http.urls == [MANIFEST_URL]
    assert load_cache(cache).checked_at == "2026-10-02T12:00:00Z"


def test_force_bypasses_the_debounce(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state(checked_at="2026-10-02T11:59:59Z"))

    http = FakeHttp()
    state = check(http, cache, force=True)

    assert state.source == "network" and http.calls != []


def test_debounce_is_persisted_in_the_cache_file(tmp_path):
    """去抖動必須跨程序有效：靠快取檔的 `checked_at`，不是記憶體狀態。"""
    cache = tmp_path / "update.json"
    http = FakeHttp()
    check(http, cache)
    assert len(http.calls) == 1

    assert check(http, cache).source == "network"
    assert len(http.calls) == 1, "同一份快取不得再發請求"

    cache.unlink()
    assert check(http, cache).source == "network"
    assert len(http.calls) == 2, "快取已不在，就該重新檢查"


def test_module_never_reads_the_clock_itself():
    """時間一律由呼叫端注入（SPEC 第 6 節可測試性）。"""
    source = (PROJECT_DIR / "ediaad" / "update.py").read_text(encoding="utf-8")
    assert "datetime.now(" not in source
    assert "time.time(" not in source


# ---- Cycle 6：約束 6「可完全關閉」 -------------------------------------------


def test_disabled_makes_no_request_and_no_background_work(tmp_path):
    http = FakeHttp()
    executor = RecordingExecutor()

    state = check(http, tmp_path / "update.json", enabled=False, background=True, executor=executor)

    assert state.source == "disabled"
    assert http.calls == [] and executor.tasks == []
    assert state.error is None


def test_disabled_still_shows_the_last_known_values(tmp_path):
    cache = tmp_path / "update.json"
    save_cache(cache, cached_state())

    state = check(FakeHttp(), cache, enabled=False)

    assert state.source == "disabled"
    assert state.latest_version == "0.3.0" and state.notes == "舊版說明"


def test_disabled_ignores_force(tmp_path):
    http = FakeHttp()
    state = check(http, tmp_path / "update.json", enabled=False, force=True)
    assert state.source == "disabled" and http.calls == []


# ---- Cycle 7：`fetch_catalog` ------------------------------------------------


def catalog_payload(**overrides) -> dict:
    payload = {
        "catalog_version": "2026-10-01",
        "sources": [{"id": "twse", "display_name": "台灣證券交易所", "supported_intervals": ["1d"]}],
        "instruments": [{"symbol": "2330", "interval": "1d", "source_id": "twse", "display_name": "台積電"}],
    }
    payload.update(overrides)
    return payload


def test_catalog_is_fetched_validated_and_installed(tmp_path):
    """下載、驗證與原子取代重用 TASK-017 的 `update_catalog`（不是第二份流程）。"""
    catalog = catalog_payload()
    http = FakeHttp({CATALOG_URL: (200, json.dumps(catalog))})
    cache = tmp_path / "catalog.json"

    result = fetch_catalog(http=http, catalog_url=CATALOG_URL, cache_path=cache)

    assert result.status == "installed" and result.requests == 1
    assert result.remote_version == "2026-10-01"
    installed = load_catalog(cache)  # 以 TASK-017 的讀取端驗證：寫出來的是同一套 schema
    assert installed.catalog_version == "2026-10-01"
    assert installed.instruments[0].symbol == "2330"
    assert installed.sources[0].id == "twse"
    assert http.calls == [(CATALOG_URL, DEFAULT_TIMEOUT)]


def test_catalog_skips_the_request_when_the_version_is_current(tmp_path):
    """AC-038：manifest 說版本相同時**連請求都不發**（有效的遠端版本由 TASK-032 傳入）。"""
    http = FakeHttp({CATALOG_URL: (200, json.dumps(catalog_payload()))})
    cache = tmp_path / "catalog.json"
    fetch_catalog(http=http, catalog_url=CATALOG_URL, cache_path=cache)
    http.calls.clear()

    result = fetch_catalog(
        http=http, catalog_url=CATALOG_URL, cache_path=cache, remote_version="2026-10-01"
    )

    assert result.status == "current" and result.requests == 0
    assert http.calls == []

    older = fetch_catalog(
        http=http, catalog_url=CATALOG_URL, cache_path=cache, remote_version="2026-09-01"
    )
    assert older.status == "local-newer" and http.calls == []
    assert load_catalog(cache).catalog_version == "2026-10-01", "較舊的遠端版本不得覆蓋本地"


def test_catalog_failure_is_reported_and_writes_nothing(tmp_path):
    http = FakeHttp({CATALOG_URL: (500, "boom")})
    cache = tmp_path / "catalog.json"

    result = fetch_catalog(http=http, catalog_url=CATALOG_URL, cache_path=cache)

    assert result.status == "failed"
    assert "500" in result.message
    assert not cache.exists(), "失敗不得留下任何檔案"


def test_catalog_rejects_an_invalid_body(tmp_path):
    http = FakeHttp({CATALOG_URL: (200, json.dumps(["nope"]))})
    cache = tmp_path / "catalog.json"

    result = fetch_catalog(http=http, catalog_url=CATALOG_URL, cache_path=cache)

    assert result.status == "failed"
    assert "不合法" in result.message
    assert not cache.exists()


def test_catalog_timeout_is_bounded(tmp_path):
    release = threading.Event()
    http = FakeHttp({CATALOG_URL: (200, "{}")}, block=release)
    cache = tmp_path / "catalog.json"

    started = time.monotonic()
    result = fetch_catalog(http=http, catalog_url=CATALOG_URL, cache_path=cache, timeout=0.2)
    elapsed = time.monotonic() - started

    assert elapsed < 0.4
    assert http.calls[0][1] == 0.2
    assert result.status == "failed" and "逾時" in result.message
    assert not cache.exists()
    release.set()


def test_update_state_path_is_the_documented_artifact(tmp_path):
    assert update_state_path(tmp_path) == tmp_path / "update.json"


# ---- Cycle 8：服務整合（不阻塞啟動／網頁／輪詢、版本頁） -----------------------


def build_series(total: int = 120) -> pd.DataFrame:
    closes = [100.0 + (index % 7) * 0.3 for index in range(total)]
    times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1h", tz="UTC")
    frame = pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [10.0 + (index % 5) for index in range(total)],
        }
    )
    frame.attrs["data_source"] = "cache"
    return frame


class FakeSource:
    id = "fake"
    display_name = "假來源（測試用）"
    supported_intervals = ("1d",)
    needs_api_key = False

    def search(self, query: str, limit: int = 20):
        return [Instrument("2330", "1d", "fake", "台積電")]

    def fetch(self, symbol: str, interval: str, limit: int | None = None):
        return build_series()


@pytest.fixture
def fake_source():
    source = FakeSource()
    register(source, replace=True)
    try:
        yield source
    finally:
        unregister("fake")


@pytest.fixture
def service(tmp_path, fake_source, monkeypatch):
    from ediaad.app import Application

    monkeypatch.delenv("EDIAAD_UPDATE_URL", raising=False)
    home = tmp_path / "home"
    app = Application.create(home=home)
    app.settings["update_enabled"] = True
    app.update_url = MANIFEST_URL
    app.update_http = FakeHttp()
    app.update_executor = RecordingExecutor()
    server = app.start(port=0)
    # `start()` 本身就會排一次檢查（啟動路徑也是被測行為，另有測試）；這裡把它清掉，
    # 讓各測試從「乾淨的服務」開始觀察網頁路徑與去抖動。
    app.update_executor.tasks.clear()
    app.update_state = None
    app._update_inflight = False
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(
            app=app, server=server, host=host, port=port, home=home, tmp=tmp_path,
            executor=app.update_executor,
        )
    finally:
        app.shutdown()


def call(host, port, method, path):
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()


def test_start_does_not_block_on_the_update_check(tmp_path, fake_source, monkeypatch):
    """約束 2（啟動）：更新檢查在獨立執行緒上，`start()` 立即返回。"""
    from ediaad.app import Application

    monkeypatch.delenv("EDIAAD_UPDATE_URL", raising=False)
    release = threading.Event()
    app = Application.create(home=tmp_path / "home")
    app.update_url = MANIFEST_URL
    app.update_http = FakeHttp(block=release)
    try:
        started = time.monotonic()
        app.start(port=0)
        elapsed = time.monotonic() - started

        assert elapsed < 1.0, f"啟動不得等待更新檢查（實測 {elapsed:.3f}s）"
        assert app.update_state is not None and app.update_state.source in {"pending", "cache"}
        workers = [item for item in threading.enumerate() if item.name.startswith("ediaad-update")]
        assert workers, "檢查必須真的被排到背景執行"
    finally:
        release.set()
        app.shutdown()


def test_web_responses_are_not_blocked_by_the_update_check(tmp_path, fake_source, monkeypatch):
    """約束 2（網頁）：更新服務卡住時，所有頁面仍立即回應。"""
    from ediaad.app import Application

    monkeypatch.delenv("EDIAAD_UPDATE_URL", raising=False)
    release = threading.Event()
    app = Application.create(home=tmp_path / "home")
    app.update_url = MANIFEST_URL
    app.update_http = FakeHttp(block=release)
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        for path in ("/", "/api/version", "/api/status"):
            started = time.monotonic()
            status, _body = call(host, port, "GET", path)
            elapsed = time.monotonic() - started
            assert status == 200, path
            assert elapsed < 1.0, f"{path} 被更新檢查阻塞（實測 {elapsed:.3f}s）"
    finally:
        release.set()
        app.shutdown()


def test_monitor_round_is_not_blocked_by_the_update_check(tmp_path, fake_source, monkeypatch):
    """約束 2（監控輪詢）：更新服務卡住時，一輪監控照常完成。"""
    from ediaad.app import Application

    monkeypatch.delenv("EDIAAD_UPDATE_URL", raising=False)
    release = threading.Event()
    app = Application.create(home=tmp_path / "home")
    app.update_url = MANIFEST_URL
    app.update_http = FakeHttp(block=release)
    app.watchlist = validate_config(
        {
            "poll_interval_seconds": 60,
            "events_path": str(tmp_path / "events.jsonl"),
            "cache_dir": str(tmp_path / "cache"),
            "pattern_id": "range_fakeout_reversion",
            "pattern_spec": None,
            "horizon": 5,
            "instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}],
        }
    )
    app.start(port=0)
    try:
        started = time.monotonic()
        result = app.run_monitor_round()
        elapsed = time.monotonic() - started

        assert result is not None and result.processed == 1
        assert elapsed < 1.0, f"監控輪詢被更新檢查阻塞（實測 {elapsed:.3f}s）"
    finally:
        release.set()
        app.shutdown()


def test_version_endpoint_returns_cache_immediately_and_checks_in_background(service):
    """約束 4＋5：頁面立即回快取（第一次為 pending），背景完成後才更新，且不重複檢查。"""
    status, body = call(service.host, service.port, "GET", "/api/version")
    assert status == 200
    assert json.loads(body)["latest_version"] is None
    assert len(service.executor.tasks) == 1, "第一次載入要排一次背景檢查"
    assert service.app.update_http.calls == [], "不得在請求中連網"

    call(service.host, service.port, "GET", "/api/version")
    assert len(service.executor.tasks) == 1, "同一輪不得重複排程"

    service.executor.run_all()
    assert service.app.update_http.urls == [MANIFEST_URL]
    assert service.app.update_state.latest_version == "0.4.0"
    assert load_cache(service.app.update_cache_path).latest_version == "0.4.0"

    payload = json.loads(call(service.host, service.port, "GET", "/api/version")[1])
    assert payload["latest_version"] == "0.4.0"
    assert payload["source"] == "network" and payload["error"] is None
    assert len(service.executor.tasks) == 1, "五分鐘內不得再檢查"


def test_version_endpoint_reports_disabled_and_failed_checks(service):
    """AC-057／F-003：「已關閉」與「檢查失敗」都不是「尚未檢查」。"""
    # 這裡測的是**呈現**：把網址清掉，避免端點又去排一次檢查蓋掉注入的狀態。
    service.app.update_url = ""
    service.app.settings["update_enabled"] = False
    payload = json.loads(call(service.host, service.port, "GET", "/api/version")[1])
    assert payload["update_enabled"] is False
    assert "已關閉" in payload["message"]
    assert service.executor.tasks == [] and service.app.update_http.calls == []

    service.app.settings["update_enabled"] = True
    service.app.update_state = UpdateState(error="HTTP 500", source="cache", checked_at="2026-10-02T12:00:00Z")
    payload = json.loads(call(service.host, service.port, "GET", "/api/version")[1])
    assert payload["update_enabled"] is True
    assert "失敗" in payload["message"] and "尚未檢查" not in payload["message"]
    assert payload["error"] == "HTTP 500"

    service.app.update_state = UpdateState(source="pending")
    payload = json.loads(call(service.host, service.port, "GET", "/api/version")[1])
    assert "進行中" in payload["message"]
    assert "失敗" not in payload["message"] and "尚未檢查" not in payload["message"]


def test_trigger_update_check_decides_alone(tmp_path, fake_source):
    """排程與否的規則只在 `trigger_update_check`：沒有網址、已關閉都回 `False` 且不排工作。"""
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    app.update_http = FakeHttp()
    app.update_executor = RecordingExecutor()
    try:
        app.update_url = ""
        assert app.trigger_update_check() is False

        app.update_url = MANIFEST_URL
        app.settings["update_enabled"] = False
        assert app.trigger_update_check() is False
        assert app.trigger_update_check(force=True) is False, "關閉時連 force 也不得繞過"

        assert app.update_executor.tasks == []
        assert app.update_http.calls == []
        assert app.update_state is None
    finally:
        app.close()


def test_trigger_uses_the_home_default_cache_path(tmp_path, fake_source):
    """`update_cache_path` 未設定時退回 `<home>/update.json`（不是悄悄不檢查）。"""
    import dataclasses

    from ediaad.app import Application

    home = tmp_path / "home"
    app = dataclasses.replace(Application.create(home=home), update_cache_path=None)
    app.update_url = MANIFEST_URL
    app.update_http = FakeHttp()
    app.update_executor = RecordingExecutor()
    try:
        assert app.trigger_update_check() is True
        app.update_executor.run_all()
        assert load_cache(update_state_path(home)).latest_version == "0.4.0"
    finally:
        app.close()


def test_close_shuts_down_the_update_pool(tmp_path, fake_source):
    """`close()` 必須關閉預設的更新 worker pool（否則行程關不掉、或關掉後還能排工作）。"""
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    app.update_url = MANIFEST_URL
    app.update_http = FakeHttp()
    assert app.trigger_update_check() is True
    pool = app._update_pool
    assert pool is not None

    app.close()

    with pytest.raises(RuntimeError):
        pool.submit(lambda: None)


def test_version_endpoint_never_checks_without_a_configured_url(service):
    """沒有 `EDIAAD_UPDATE_URL` 時不得連網（保護預設安裝與其他測試）。"""
    service.app.update_url = ""
    payload = json.loads(call(service.host, service.port, "GET", "/api/version")[1])

    assert service.app.update_http.calls == []
    assert service.executor.tasks == []
    assert "尚未檢查" in payload["message"]


# ---- Cycle 9：版本頁文字（以 Node 載入真實 `version.js`） ---------------------

NODE = shutil.which("node")

VERSION_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const context = {console: console};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync("version.js", "utf8"), context);

function lines(payload) {
  return context.ediaadVersion.describeVersion(payload).join("\n");
}
process.stdout.write(JSON.stringify({
  missing: lines({version: "1.0.0", latest_version: null, message: "尚未檢查更新"}),
  pending: lines({version: "1.0.0", latest_version: null, source: "pending", message: "更新檢查進行中"}),
  disabled: lines({version: "1.0.0", latest_version: null, update_enabled: false, source: "disabled", message: "更新檢查已關閉"}),
  failed: lines({version: "1.0.0", latest_version: null, update_enabled: true, source: "cache", error: "HTTP 500", message: "更新檢查失敗：HTTP 500"}),
  failedWithData: lines({
    version: "1.0.0", latest_version: "0.3.0", released_at: "2026-09-01", notes: "舊版",
    checked_at: "2026-10-02T12:00:00Z", update_available: true, error: "HTTP 500", source: "cache"
  })
}));
"""


@pytest.fixture(scope="module")
def version_text():
    if NODE is None:
        pytest.skip("需要 node 才能驗證前端模組的純函式（僅測試期依賴）")
    static = PROJECT_DIR / "ediaad" / "web" / "static"
    completed = subprocess.run(
        [NODE, "-e", VERSION_HARNESS], capture_output=True, text=True, timeout=60, cwd=str(static)
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_version_page_distinguishes_every_state(version_text):
    assert "尚未檢查" in version_text["missing"]

    assert "檢查中" in version_text["pending"]
    assert "尚未檢查" not in version_text["pending"]

    assert "更新檢查：已關閉" in version_text["disabled"], "要有專屬的一行，不能只靠訊息文字"

    assert "失敗" in version_text["failed"] and "尚未檢查" not in version_text["failed"]

    assert "0.3.0" in version_text["failedWithData"]
    assert "上次檢查失敗" in version_text["failedWithData"]


def test_version_script_is_served_with_the_right_type(service):
    status, _body = call(service.host, service.port, "GET", "/static/version.js")
    assert status == 200
