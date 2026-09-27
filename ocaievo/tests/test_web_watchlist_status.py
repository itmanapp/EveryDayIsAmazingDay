"""監控清單管理、系統狀態、版本與授權頁（TASK-025／AC-047、AC-048、AC-066）。

觀察邊界：
1. **端點（自動）**：`GET/POST /api/watchlist`、`GET /api/instruments/search`、
   `GET /api/status`、`GET /api/version`、`GET /api/license` 的 JSON 與狀態碼；商品搜尋與
   監控以**注入的假來源**（離線）驅動，設定檔與租約以 `tmp_path` 觀察。
2. **接線（自動）**：`POST /api/watchlist` 之後的**下一輪** `run_once` 真的使用新清單；
   監控執行緒會填入狀態頁的資料；事件落地到 `Store`（跨重啟的去重）。
3. **頁面（自動，需 `node`）**：四支前端模組的純函式。
4. **外觀（人工）**：三種授權狀態的實際畫面依 SPEC 第 7 節人工檢查。
"""

from __future__ import annotations

import dataclasses
import http.client
import json
import os
import shutil
import urllib.parse
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ediaad.errors import ConfigError, SourceError
from ediaad.license import Lease, save_lease, signing_payload
from ediaad.markets.base import Instrument, register, unregister
from ediaad.monitor import Watchlist, save_config

from _ed25519_fixture import FIXTURE_PUBLIC_KEY, sign

PROJECT_DIR = Path(__file__).resolve().parent.parent
FINGERPRINT = "0123456789abcdef"
ISSUED = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
EXPIRES = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self):
        return json.loads(self.body)


def call(host, port, method, path, body=None):
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        payload = None
        headers = {}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        return Response(
            status=response.status,
            headers={key.lower(): value for key, value in response.getheaders()},
            body=response.read(),
        )
    finally:
        connection.close()


def build_series(offset: int = 30, total: int = 120, *, hit: bool = True) -> pd.DataFrame:
    """植入「盤整 20 根 → 假跌破 → 回歸」的序列（預設規格為盤整 20～120 根）。"""
    closes = [100.0 + (index % 7) * 0.3 for index in range(total)]
    highs = [value + 1.0 for value in closes]
    lows = [value - 1.0 for value in closes]
    if hit:
        lows[offset - 1] = 90.0
        for step in range(20):
            base = 100.0 if step % 2 == 0 else 100.4
            closes[offset + step] = base
            highs[offset + step] = base + 1.0
            lows[offset + step] = base - 1.0
        closes[offset + 20] = 98.5
        highs[offset + 20] = 99.5
        lows[offset + 20] = 97.0
        closes[offset + 21] = 100.5
        highs[offset + 21] = 101.0
        lows[offset + 21] = 99.5
    times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10.0 + (index % 5) for index in range(total)],
        }
    )


class FakeSource:
    """離線假來源：搜尋回兩筆、抓取回植入序列並標示 `data_source="cache"`。"""

    id = "fake"
    display_name = "假來源（測試用）"
    supported_intervals = ("1h", "1d")
    needs_api_key = False

    def __init__(self, *, error: Exception | None = None, data_source: str = "cache") -> None:
        self.error = error
        self.data_source = data_source
        self.queries: list[tuple[str, int]] = []
        self.fetches: list[tuple[str, str]] = []

    def search(self, query: str, limit: int = 20):
        self.queries.append((query, limit))
        if self.error is not None:
            raise self.error
        candidates = [
            Instrument("2330", "1d", "fake", "台積電"),
            Instrument("1301", "1d", "fake", "台塑"),
            Instrument("2317", "1d", "fake", "鴻海"),
        ]
        return [item for item in candidates if query in item.display_name][:limit]

    def fetch(self, symbol: str, interval: str, limit: int | None = None):
        self.fetches.append((symbol, interval))
        if self.error is not None:
            raise self.error
        frame = build_series()
        if limit is not None:
            frame = frame.iloc[-limit:].reset_index(drop=True)
        frame.attrs["data_source"] = self.data_source
        return frame


@pytest.fixture
def fake_source():
    source = FakeSource()
    register(source, replace=True)
    try:
        yield source
    finally:
        unregister("fake")


def write_watchlist(home: Path, **overrides) -> Path:
    """寫一份有效的 `watchlist.json`（指向假來源）。"""
    payload = {
        "poll_interval_seconds": 60,
        "events_path": str(home / "events.jsonl"),
        "cache_dir": str(home / "cache"),
        "pattern_id": "range_fakeout_reversion",
        "pattern_spec": None,
        "horizon": 5,
        "instruments": [
            {"symbol": "2330", "interval": "1d", "source_id": "fake"},
        ],
    }
    payload.update(overrides)
    path = home / "watchlist.json"
    save_config(path, validate_payload(payload))
    return path


def validate_payload(payload: dict) -> Watchlist:
    from ediaad.monitor import validate_config

    return validate_config(payload)


@pytest.fixture
def service(tmp_path):
    from ediaad.app import Application

    home = tmp_path / "home"
    app = Application.create(home=home)
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(app=app, server=server, host=host, port=port, home=home, tmp=tmp_path)
    finally:
        app.shutdown()


def get(service, path) -> Response:
    return call(service.host, service.port, "GET", path)


def post(service, path, body) -> Response:
    return call(service.host, service.port, "POST", path, body)


# ---- AC-047：下拉搜尋 -------------------------------------------------------


def test_instrument_search_returns_symbol_and_display_name(service, fake_source):
    """第一個失敗行為：端點不存在（404）；實作後必須回可下拉的清單。"""
    response = get(service, "/api/instruments/search?q=" + urllib.parse.quote("台積") + "&source=fake")

    assert response.status == 200, response.text
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["symbol"] == "2330"
    assert payload["items"][0]["display_name"] == "台積電"
    assert all(item["symbol"] and item["display_name"] for item in payload["items"])
    assert fake_source.queries == [("台積", 20)]


def test_instrument_search_respects_limit_and_validates_it(service, fake_source):
    limited = get(service, "/api/instruments/search?q=" + urllib.parse.quote("台") + "&limit=2&source=fake").json()
    assert limited["count"] == 2
    assert fake_source.queries[-1] == ("台", 2)

    for bad in ("0", "-1", "51", "abc"):
        response = get(service, "/api/instruments/search?q=" + urllib.parse.quote("台") + f"&limit={bad}&source=fake")
        assert response.status == 400, bad
        assert "limit" in response.json()["error"]["message"]


def test_instrument_search_requires_a_keyword_and_a_known_source(service, fake_source):
    missing = get(service, "/api/instruments/search")
    assert missing.status == 400
    assert "q" in missing.json()["error"]["message"]

    unknown = get(service, "/api/instruments/search?q=" + urllib.parse.quote("台") + "&source=no-such-source")
    assert unknown.status == 400
    assert "no-such-source" in unknown.json()["error"]["message"]


def test_instrument_search_survives_one_failing_source(service):
    """單一來源失敗不影響其他來源，原因隨回應附上（狀態頁也會呈現）。"""
    register(FakeSource(error=SourceError("上游掛了")), replace=True)
    try:
        response = get(service, "/api/instruments/search?q=" + urllib.parse.quote("台") + "&source=fake")
    finally:
        unregister("fake")

    assert response.status == 200
    payload = response.json()
    assert payload["items"] == []
    assert any("上游掛了" in message for message in payload["errors"])


# ---- AC-047：監控清單讀寫 ---------------------------------------------------


def test_watchlist_is_unconfigured_before_the_first_save(service):
    payload = get(service, "/api/watchlist").json()

    assert payload["configured"] is False
    assert payload["watchlist"]["instruments"] == []
    assert payload["watchlist"]["poll_interval_seconds"] == 60
    assert payload["path"].endswith("watchlist.json")
    assert payload["monitor_running"] is False


def test_watchlist_save_writes_the_file_and_takes_effect_next_round(service, fake_source):
    """AC-047 的核心：寫入後**下一輪** `run_once` 就用新清單。"""
    body = {
        "instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}],
        "poll_interval_seconds": 30,
    }
    response = post(service, "/api/watchlist", body)

    assert response.status == 200, response.text
    payload = response.json()
    assert payload["configured"] is True
    assert payload["watchlist"]["instruments"] == [
        {"symbol": "2330", "interval": "1d", "source_id": "fake"}
    ]
    assert payload["watchlist"]["poll_interval_seconds"] == 30

    written = json.loads((service.home / "watchlist.json").read_text(encoding="utf-8"))
    assert written["poll_interval_seconds"] == 30
    assert service.app.watchlist is not None

    # 下一輪真的用新清單：假來源被問到 2330／1d，且事件落地
    result = service.app.run_monitor_round()
    assert result is not None and result.processed == 1
    assert fake_source.fetches == [("2330", "1d")]
    assert service.app.instrument_status["2330|1d"]["data_source"] == "cache"
    assert service.app.last_poll_at is not None


def test_watchlist_save_supports_add_remove_and_interval_change(service, fake_source):
    post(service, "/api/watchlist", {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]})
    post(
        service,
        "/api/watchlist",
        {
            "instruments": [
                {"symbol": "2330", "interval": "1d", "source_id": "fake"},
                {"symbol": "2317", "interval": "1h", "source_id": "fake"},
            ]
        },
    )
    assert len(service.app.watchlist.instruments) == 2

    removed = post(
        service,
        "/api/watchlist",
        {"instruments": [{"symbol": "2317", "interval": "1h", "source_id": "fake"}]},
    ).json()
    assert removed["watchlist"]["instruments"] == [
        {"symbol": "2317", "interval": "1h", "source_id": "fake"}
    ]
    assert len(service.app.watchlist.instruments) == 1


def test_watchlist_save_rejects_invalid_changes_without_writing(service, fake_source, tmp_path):
    post(service, "/api/watchlist", {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]})
    original = (service.home / "watchlist.json").read_text(encoding="utf-8")

    bad_bodies = [
        ({"instruments": [{"symbol": "2330", "interval": "5m", "source_id": "fake"}]}, "不支援"),
        ({"instruments": []}, "至少"),
        ({"instruments": [{"symbol": "2330"}]}, "interval"),
        ({"instruments": [{"symbol": "", "interval": "1d"}]}, "symbol"),
        ({"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "nope"}]}, "nope"),
        ({"poll_interval_seconds": 0}, "poll_interval_seconds"),
        ({"unknown_key": 1}, "unknown_key"),
    ]
    for body, fragment in bad_bodies:
        response = post(service, "/api/watchlist", body)
        assert response.status == 400, (body, response.text)
        assert fragment in response.json()["error"]["message"], body
        assert (service.home / "watchlist.json").read_text(encoding="utf-8") == original


def test_watchlist_save_maps_a_write_failure_to_a_source_error(service, fake_source):
    post(service, "/api/watchlist", {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]})
    home = service.home
    os.chmod(home, 0o500)
    try:
        response = post(
            service,
            "/api/watchlist",
            {"poll_interval_seconds": 45, "instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]},
        )
    finally:
        os.chmod(home, 0o700)

    assert response.status == 502
    assert "寫入" in response.json()["error"]["message"]


# ---- AC-048：系統狀態與版本 -------------------------------------------------


def test_status_reports_the_last_poll_and_per_instrument_source(service, fake_source):
    post(service, "/api/watchlist", {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]})
    before = get(service, "/api/status").json()
    assert before["last_poll_at"] is None
    assert before["last_result"] is None
    assert before["monitor_running"] is False

    service.app.run_monitor_round()

    payload = get(service, "/api/status").json()
    assert payload["last_poll_at"] is not None
    assert payload["last_result"]["processed"] == 1
    assert payload["last_result"]["alerted"] == 1
    entry = payload["instruments"][0]
    assert entry["symbol"] == "2330" and entry["interval"] == "1d"
    assert entry["source_id"] == "fake" and entry["data_source"] == "cache"
    assert entry["error"] is None


def test_status_reports_a_source_error(service, fake_source):
    fake_source.error = SourceError("上游掛了")
    post(service, "/api/watchlist", {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]})

    service.app.run_monitor_round()

    payload = get(service, "/api/status").json()
    assert payload["last_result"]["processed"] == 0
    assert payload["last_result"]["warnings"] >= 1
    assert "上游掛了" in payload["instruments"][0]["error"]


def test_events_are_written_to_the_store_and_deduped_across_rounds(service, fake_source):
    """Store 寫入端與跨重啟去重（TASK-018 的介面第一次被服務使用）。"""
    post(service, "/api/watchlist", {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "fake"}]})

    first = service.app.run_monitor_round()
    second = service.app.run_monitor_round()

    assert first.alerted == 1 and second.alerted == 0, "同一事件不得重複提醒"
    stored = service.app.store.query_events()
    assert len(stored) == 1
    assert stored[0]["symbol"] == "2330"
    assert len(service.app.store.seen_keys()) == 1


def test_version_page_marks_missing_update_data(service):
    payload = get(service, "/api/version").json()

    assert payload["version"] == service.app.version
    assert payload["latest_version"] is None
    assert payload["released_at"] is None
    assert payload["notes"] is None
    assert payload["update_available"] is False
    assert "尚未檢查" in payload["message"]


def test_version_page_presents_an_update_state(service):
    service.app.update_state = SimpleNamespace(
        latest_version="1.1.0",
        released_at="2026-10-01",
        notes="修正與新功能",
        checked_at="2026-10-02T00:00:00+00:00",
    )

    payload = get(service, "/api/version").json()

    assert payload["latest_version"] == "1.1.0"
    assert payload["released_at"] == "2026-10-01"
    assert payload["notes"] == "修正與新功能"
    assert payload["update_available"] is True


# ---- AC-066：授權頁 ---------------------------------------------------------


def build_lease(**overrides) -> Lease:
    fields = {
        "key_id": "EDIAAD-2026-0001-TEST",
        "machine": FINGERPRINT,
        "issued_at": ISSUED.isoformat().replace("+00:00", "Z"),
        "expires_at": EXPIRES.isoformat().replace("+00:00", "Z"),
        "features": ["start", "update"],
        "catalog_version": "2026-10-01",
        "sig": "00" * 64,
    }
    fields.update(overrides)
    unsigned = Lease(**fields)
    return Lease(**{**fields, "sig": sign(signing_payload(unsigned))})


def test_license_page_shows_the_first_activation_form_state(service):
    payload = get(service, "/api/license").json()

    assert payload["state"] == "inactive"
    assert payload["has_lease"] is False
    assert payload["reapply"] is True
    assert payload["reapply_url"]
    assert payload["features"] == []
    assert payload["days_remaining"] is None


def test_license_page_shows_remaining_days_and_features(service):
    save_lease(service.app.lease_path, build_lease())
    service.app.revoked_path.unlink(missing_ok=True)

    payload = get(service, "/api/license").json()

    assert payload["state"] == "active"
    assert payload["reapply"] is False
    assert payload["expires_at"] == "2026-10-24T12:00:00Z"
    assert payload["days_remaining"] > 0
    assert payload["features"] == ["start", "update"]
    assert payload["key_id"] == "EDIAAD-2026-0001-TEST"
    assert payload["reapply_url"] == "/#license-heading", "連結必須指向頁面上真的存在的錨點"


def test_license_page_reports_expired_and_revoked(service):
    save_lease(service.app.lease_path, build_lease())

    service.app.revoked_path.write_text(
        json.dumps({"key_id": "EDIAAD-2026-0001-TEST", "revoked_at": 1.0}), encoding="utf-8"
    )
    revoked = get(service, "/api/license").json()
    assert revoked["state"] == "revoked"
    assert revoked["reapply"] is True
    assert "撤銷" in revoked["message"]

    service.app.revoked_path.unlink()
    save_lease(service.app.lease_path, build_lease(
        issued_at=(ISSUED - timedelta(days=60)).isoformat().replace("+00:00", "Z"),
        expires_at=(ISSUED - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
    ))
    expired = get(service, "/api/license").json()
    assert expired["state"] == "expired"
    assert expired["reapply"] is True
    assert "重新申請" in expired["message"]
    assert revoked["reapply_url"] == expired["reapply_url"] == "/#license-heading"


def test_reapply_link_points_at_an_anchor_that_exists(service):
    """「重新申請連結」必須真的可用：指到本頁存在的錨點，不能是 404 的頁面。"""
    payload = get(service, "/api/license").json()

    fragment = payload["reapply_url"].split("#", 1)[-1]
    assert payload["reapply_url"].startswith("/#") and fragment
    assert f'id="{fragment}"' in get(service, "/").text


def test_license_page_never_500s_on_a_corrupt_lease(service):
    service.app.lease_path.write_text("{not json", encoding="utf-8")

    response = get(service, "/api/license")

    assert response.status == 200
    payload = response.json()
    assert payload["state"] == "error"
    assert payload["reapply"] is True
    assert "無法解讀" in payload["message"]


# ---- 監控執行緒 -------------------------------------------------------------


def test_monitor_thread_polls_and_stops(service, fake_source, tmp_path):
    write_watchlist(service.home)
    from ediaad.monitor import load_config

    service.app.watchlist = load_config(service.home / "watchlist.json")

    assert service.app.start_monitor(interval=1) is True
    assert service.app.start_monitor() is True, "重複啟動必須是幂等的"
    try:
        deadline = time.monotonic() + 10
        while service.app.last_poll_at is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert service.app.last_poll_at is not None
        assert get(service, "/api/status").json()["monitor_running"] is True
    finally:
        service.app.stop_monitor()

    assert service.app.monitor_running is False
    assert fake_source.fetches, "監控執行緒必須真的抓過資料"


def test_monitor_cannot_start_without_a_watchlist(service):
    assert service.app.start_monitor() is False
    assert "監控清單" in (service.app.monitor_error or "")


# ---- AC-052／AC-057／AC-066：網頁啟用與更換密鑰 ------------------------------


class RecordingHttp:
    """網頁啟用用的假 HTTP 客戶端（介面同 TASK-030 的 `post`）。"""

    def __init__(self, status: int = 200, body=None) -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, dict, float]] = []

    def post(self, url, payload, timeout=10.0):
        self.calls.append((url, dict(payload), timeout))
        return self.status, self.body


def test_activate_endpoint_lands_the_lease_and_reports_active(service, monkeypatch):
    from ediaad.license import machine_fingerprint

    monkeypatch.setenv("EDIAAD_LICENSE_URL", "https://license.example.invalid")
    lease = build_lease(machine=machine_fingerprint())
    http = RecordingHttp(body=json.loads(lease.to_json()))
    service.app.license_http = http
    service.app.license_public_key = FIXTURE_PUBLIC_KEY

    response = post(service, "/api/license/activate", {"key": "EDIAAD-2026-0001-TEST"})

    assert response.status == 200, response.text
    payload = response.json()
    assert payload["state"] == "active"
    assert payload["key_id"] == "EDIAAD-2026-0001-TEST"
    assert http.calls[0][0] == "https://license.example.invalid/v1/activate"
    assert http.calls[0][1]["machine"]
    assert json.loads(service.app.lease_path.read_text(encoding="utf-8"))["key_id"] == (
        "EDIAAD-2026-0001-TEST"
    )


def test_activate_endpoint_requires_a_service_url_and_a_key(service, monkeypatch):
    from ediaad.license import machine_fingerprint

    monkeypatch.delenv("EDIAAD_LICENSE_URL", raising=False)
    service.app.license_http = RecordingHttp(
        body=json.loads(build_lease(machine=machine_fingerprint()).to_json())
    )

    missing_url = post(service, "/api/license/activate", {"key": "K"})
    assert missing_url.status == 400
    assert "EDIAAD_LICENSE_URL" in missing_url.json()["error"]["message"]

    monkeypatch.setenv("EDIAAD_LICENSE_URL", "https://license.example.invalid")
    assert post(service, "/api/license/activate", {}).status == 400
    assert post(service, "/api/license/activate", {"key": "   "}).status == 400


def test_activate_endpoint_maps_rejections_and_replacements(service, monkeypatch):
    from ediaad.license import machine_fingerprint

    monkeypatch.setenv("EDIAAD_LICENSE_URL", "https://license.example.invalid")
    service.app.license_public_key = FIXTURE_PUBLIC_KEY
    fingerprint = machine_fingerprint()

    service.app.license_http = RecordingHttp(status=403, body={"error": "invalid key"})
    rejected = post(service, "/api/license/activate", {"key": "BAD"})
    assert rejected.status == 400
    assert not service.app.lease_path.exists()

    service.app.license_http = RecordingHttp(status=503, body="busy")
    assert post(service, "/api/license/activate", {"key": "K"}).status == 502

    # 更換密鑰：以新租約為準
    first = build_lease(machine=fingerprint)
    service.app.license_http = RecordingHttp(body=json.loads(first.to_json()))
    post(service, "/api/license/activate", {"key": "EDIAAD-2026-0001-TEST"})
    second = build_lease(key_id="EDIAAD-2026-0002-TEST", machine=fingerprint)
    service.app.license_http = RecordingHttp(body=json.loads(second.to_json()))
    replaced = post(service, "/api/license/activate", {"key": "EDIAAD-2026-0002-TEST"})

    assert replaced.status == 200
    assert replaced.json()["key_id"] == "EDIAAD-2026-0002-TEST"
    assert get(service, "/api/license").json()["key_id"] == "EDIAAD-2026-0002-TEST"


def test_activate_endpoint_uses_the_default_http_client(service, monkeypatch):
    """回歸（TASK-036 抓到）：沒有注入 `app.license_http` 時，端點要用**預設**客戶端。

    模組層的 `http_post` 是**函式**，而核心（`activate`／`renew`）要的是有 `.post()` 的
    物件；少了 `HTTP_CLIENT` 這層包裝，真實路徑會以 `AttributeError` 收場（500），而
    本檔其他測試因為都注入 `RecordingHttp` 而看不到。
    """
    from _cli_helpers import LicenseServer, build_lease

    from ediaad.license import machine_fingerprint

    assert service.app.license_http is None, "這個測試要驗的就是預設路徑"
    service.app.license_public_key = FIXTURE_PUBLIC_KEY
    lease = build_lease(machine_fingerprint())

    with LicenseServer(lambda payload, path: (200, json.loads(lease.to_json()))) as server:
        monkeypatch.setenv("EDIAAD_LICENSE_URL", server.url)
        response = post(service, "/api/license/activate", {"key": "EDIAAD-2026-0001"})

    assert response.status == 200, response.text
    assert response.json()["key_id"] == "EDIAAD-2026-0001"
    assert server.paths == ["/v1/activate"]


# ---- 頁面（以 Node 載入四支前端模組驗證純函式） -----------------------------

NODE = shutil.which("node")

PAGE_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const context = {console: console};
context.window = context;
vm.createContext(context);
["watchlist.js", "status.js", "version.js", "license.js"].forEach(function (name) {
  vm.runInContext(fs.readFileSync(name, "utf8"), context);
});

function caught(fn) {
  try {
    fn();
  } catch (error) {
    return String(error.message || error);
  }
  return null;
}

const report = {
  body: context.ediaadWatchlist.buildWatchlistBody(
    [{symbol: "  2330 ", interval: " 1d ", source_id: "twse"}],
    {poll_interval_seconds: "30"}
  ),
  rowErrors: {
    symbol: caught(() => context.ediaadWatchlist.parseInstrumentRow({interval: "1d"})),
    interval: caught(() => context.ediaadWatchlist.parseInstrumentRow({symbol: "2330"})),
    empty: caught(() => context.ediaadWatchlist.buildWatchlistBody([], {})),
    poll: caught(() => context.ediaadWatchlist.buildWatchlistBody([{symbol: "x", interval: "1d"}], {poll_interval_seconds: "0"}))
  },
  watchlistLines: context.ediaadWatchlist.describeWatchlist({
    path: "/tmp/watchlist.json",
    watchlist: {
      poll_interval_seconds: 30,
      pattern_id: "range_fakeout_reversion",
      horizon: 5,
      instruments: [{symbol: "2330", interval: "1d", source_id: "twse"}]
    }
  }),
  searchLines: context.ediaadWatchlist.describeSearchResults([
    {symbol: "2330", display_name: "台積電", interval: "1d"}
  ]),
  statusLines: context.ediaadStatus.describeStatus({
    running: true,
    monitor_running: true,
    last_poll_at: "2026-10-01T00:00:00+00:00",
    last_result: {processed: 1, alerted: 1, skipped: 0, warnings: 0},
    instruments: [
      {symbol: "2330", interval: "1d", source_id: "twse", data_source: "cache", error: null},
      {symbol: "BTCUSDT", interval: "1h", source_id: "binance", data_source: null, error: "上游掛了"}
    ],
    problems: {settings: "壞掉"}
  }),
  statusEmpty: context.ediaadStatus.describeStatus({
    running: false, monitor_running: false, last_poll_at: null, last_result: null, instruments: [], problems: {}
  }),
  versionMissing: context.ediaadVersion.describeVersion({version: "1.0.0", latest_version: null, message: "尚未檢查更新"}),
  versionPresent: context.ediaadVersion.describeVersion({
    version: "1.0.0", latest_version: "1.1.0", released_at: "2026-10-01",
    notes: "修正", checked_at: "2026-10-02T00:00:00+00:00", update_available: true
  }),
  licenseLabels: context.ediaadLicense.STATE_LABELS,
  licenseInactive: context.ediaadLicense.describeLicense({state: "inactive"}),
  licenseActive: context.ediaadLicense.describeLicense({
    state: "active", key_id: "K1", expires_at: "2026-10-24T12:00:00Z",
    days_remaining: 23.4, features: ["start", "update"], reapply: false
  }),
  licenseExpired: context.ediaadLicense.describeLicense({
    state: "expired", key_id: "K1", expires_at: "2026-09-01T00:00:00Z",
    days_remaining: null, features: ["start"], reapply: true,
    message: "租約已過期：請重新申請新密鑰", reapply_url: "/#license-heading"
  }),
  activateBody: context.ediaadLicense.buildActivateBody("  KEY-1 "),
  activateError: caught(() => context.ediaadLicense.buildActivateBody("   "))
};
process.stdout.write(JSON.stringify(report));
"""


@pytest.fixture(scope="module")
def pages():
    if NODE is None:
        pytest.skip("需要 node 才能驗證前端模組的純函式（僅測試期依賴）")
    static = PROJECT_DIR / "ediaad" / "web" / "static"
    completed = subprocess.run(
        [NODE, "-e", PAGE_HARNESS], capture_output=True, text=True, timeout=60, cwd=str(static)
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_watchlist_helpers_trim_and_reject_bad_rows(pages):
    assert pages["body"] == {
        "instruments": [{"symbol": "2330", "interval": "1d", "source_id": "twse"}],
        "poll_interval_seconds": 30,
    }
    assert "symbol" in pages["rowErrors"]["symbol"]
    assert "interval" in pages["rowErrors"]["interval"]
    assert "至少" in pages["rowErrors"]["empty"]
    assert "poll_interval_seconds" in pages["rowErrors"]["poll"]


def test_page_text_helpers_describe_the_state(pages):
    watchlist_text = "\n".join(pages["watchlistLines"])
    assert "2330 1d" in watchlist_text and "30 秒" in watchlist_text
    assert "台積電" in "\n".join(pages["searchLines"])

    status_text = "\n".join(pages["statusLines"])
    assert "cache" in status_text and "上游掛了" in status_text
    assert "settings" in status_text
    assert "尚未輪詢" in "\n".join(pages["statusEmpty"])

    assert "尚未檢查" in "\n".join(pages["versionMissing"])
    version_text = "\n".join(pages["versionPresent"])
    assert "1.1.0" in version_text and "2026-10-01" in version_text and "修正" in version_text


def test_license_page_helpers_cover_the_three_states(pages):
    assert set(pages["licenseLabels"]) == {"inactive", "active", "expired", "revoked", "error"}

    assert "首次啟用" in "\n".join(pages["licenseInactive"])
    active_text = "\n".join(pages["licenseActive"])
    assert "有效期內" in active_text and "23.4" in active_text and "update" in active_text
    expired_text = "\n".join(pages["licenseExpired"])
    assert "已過期" in expired_text and "重新申請" in expired_text
    assert pages["activateBody"] == {"key": "KEY-1"}
    assert "密鑰" in pages["activateError"]


def test_pages_and_scripts_are_served_and_wired(service):
    page = get(service, "/").text
    for marker in (
        'id="watchlist-form"',
        'id="watchlist-search"',
        'id="watchlist-items"',
        'id="status-lines"',
        'id="version-lines"',
        'id="license-lines"',
        'id="license-form"',
        'id="license-key"',
    ):
        assert marker in page, marker
    for name in ("watchlist.js", "status.js", "version.js", "license.js"):
        assert f"/static/{name}" in page
        response = get(service, f"/static/{name}")
        assert response.status == 200
        assert response.headers["content-type"].startswith("text/javascript")


# ---- 來源能力轉接、停止與設定驗證 -------------------------------------------


def test_fetch_passes_the_cache_dir_to_sources_that_support_it(service, tmp_path):
    """來源分派的能力轉接：支援 `cache_dir`／`max_age` 的來源要拿到本服務的快取目錄。"""

    class CachedSource:
        id = "cached"
        display_name = "快取來源（測試用）"
        supported_intervals = ("1d",)
        needs_api_key = False

        def __init__(self):
            self.kwargs: list[dict] = []

        def search(self, query, limit=20):
            return []

        def fetch(self, symbol, interval, limit=None, *, cache_dir=None, max_age=None):
            self.kwargs.append({"cache_dir": cache_dir, "max_age": max_age})
            frame = build_series(total=120)
            frame.attrs["data_source"] = "cache-stale"
            return frame

    source = CachedSource()
    register(source, replace=True)
    try:
        post(
            service,
            "/api/watchlist",
            {"instruments": [{"symbol": "2330", "interval": "1d", "source_id": "cached"}]},
        )
        result = service.app.run_monitor_round()
    finally:
        unregister("cached")

    assert result is not None
    assert source.kwargs == [{"cache_dir": service.app.cache_dir, "max_age": 900}]
    assert service.app.instrument_status["2330|1d"]["data_source"] == "cache-stale"


def test_stop_monitor_really_ends_the_thread(service, fake_source):
    import threading

    from ediaad.monitor import load_config

    write_watchlist(service.home)
    service.app.watchlist = load_config(service.home / "watchlist.json")
    assert service.app.start_monitor(interval=1) is True

    service.app.stop_monitor()

    alive = [item.name for item in threading.enumerate() if item.name == "ediaad-monitor"]
    assert alive == [], "停止後不得留下監控執行緒"


def test_save_config_validates_before_writing(tmp_path):
    """`save_config` 是公開 API：不合法（例如輪詢間隔 0）時必須拒絕且不寫檔。"""
    from ediaad.monitor import save_config, validate_config

    valid = validate_config(
        {
            "poll_interval_seconds": 60,
            "events_path": str(tmp_path / "events.jsonl"),
            "cache_dir": str(tmp_path / "cache"),
            "pattern_id": "range_fakeout_reversion",
            "pattern_spec": None,
            "horizon": 5,
            "instruments": [{"symbol": "2330", "interval": "1d", "source_id": "csv"}],
        }
    )
    broken = dataclasses.replace(valid, poll_interval_seconds=0)
    path = tmp_path / "watchlist.json"

    with pytest.raises(ConfigError):
        save_config(path, broken)

    assert not path.exists()
