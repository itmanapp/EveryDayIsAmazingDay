"""離線啟動驗證與時鐘篡改防護（TASK-030／AC-053、AC-058）。

觀察邊界：只呼叫 `check_lease`（`activate` 的產物由測試夾具直接寫入 `tmp_path`）；時間
以固定 `now` 注入、`high_water` 以 `tmp_path` 觀察；假 HTTP 可計數、可強制失敗。
**AC-053 的核心斷言是「啟動路徑一次網路呼叫都沒有」**，因此把「任何呼叫都拋例外」的
客戶端也拿來跑同一條路徑。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ediaad.errors import SourceError
from ediaad.license import (
    CLOCK_TOLERANCE_SECONDS,
    Lease,
    check_lease,
    load_high_water,
    save_high_water,
    save_lease,
    signing_payload,
)

from _ed25519_fixture import FIXTURE_PUBLIC_KEY, sign

KEY = "EDIAAD-2026-0001-TEST"
FINGERPRINT = "0123456789abcdef"
ISSUED_AT = "2026-09-24T12:00:00Z"
EXPIRES_AT = "2026-10-24T12:00:00Z"
URL = "https://license.example.invalid"
INSIDE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
ISSUED = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
EXPIRES = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def build_lease(**overrides) -> Lease:
    fields = {
        "key_id": KEY,
        "machine": FINGERPRINT,
        "issued_at": ISSUED_AT,
        "expires_at": EXPIRES_AT,
        "features": ["start", "update"],
        "catalog_version": "2026-10-01",
        "sig": "00" * 64,
    }
    fields.update(overrides)
    unsigned = Lease(**fields)
    return Lease(**{**fields, "sig": sign(signing_payload(unsigned))})


class FakeHttp:
    def __init__(self, *, status: int = 200, body=None, raises: BaseException | None = None) -> None:
        self.status = status
        self.body = body
        self.raises = raises
        self.calls: list[tuple[str, dict, float]] = []

    def post(self, url, payload, timeout=10.0):
        self.calls.append((url, dict(payload), timeout))
        if self.raises is not None:
            raise self.raises
        return self.status, self.body

    @property
    def call_count(self) -> int:
        return len(self.calls)


def startup(tmp_path, lease: Lease | None = None, *, now=INSIDE, http=None, **overrides):
    """寫入租約後跑一次啟動驗證；回傳 `(verdict, high_water_path)`。"""
    lease_path = tmp_path / "lease.json"
    if lease is not None:
        save_lease(lease_path, lease)
    kwargs = {
        "fingerprint": FINGERPRINT,
        "public_key": FIXTURE_PUBLIC_KEY,
        "now": (lambda: now) if isinstance(now, datetime) else now,
        "lease_path": lease_path,
        "high_water_path": tmp_path / "high_water.json",
        "http": http,
        "url": URL,
    }
    kwargs.update(overrides)
    return check_lease(**kwargs), tmp_path / "high_water.json"


# ---- AC-053：離線驗章、指紋、到期 -------------------------------------------


def test_startup_verifies_offline_without_any_network_call(tmp_path):
    """第一個失敗行為：`check_lease` 不存在（collection error）；實作後必須零網路請求。"""
    counting = FakeHttp(raises=AssertionError("啟動路徑不得發出網路請求"))
    verdict, _high_water = startup(tmp_path, build_lease(), http=counting)

    assert counting.call_count == 0
    assert verdict.ok is True
    assert verdict.force_online is False
    assert verdict.reason == ""


def test_startup_passes_even_when_the_client_would_raise(tmp_path):
    """把客戶端換成「任何呼叫都拋 SourceError」也必須完成啟動（離線可用）。"""
    hostile = FakeHttp(raises=SourceError("no network"))
    verdict, _ = startup(tmp_path, build_lease(), http=hostile)

    assert hostile.call_count == 0
    assert verdict.ok is True


def test_startup_reports_a_missing_lease(tmp_path):
    verdict, _ = startup(tmp_path, None)

    assert verdict.ok is False
    assert "啟用" in verdict.reason
    assert verdict.force_online is False


def test_startup_rejects_a_different_machine(tmp_path):
    verdict, _ = startup(tmp_path, build_lease(machine="ffffffffffffffff"))

    assert verdict.ok is False
    assert "指紋" in verdict.reason or "機器" in verdict.reason


def test_startup_rejects_an_invalid_signature(tmp_path):
    lease = build_lease()
    forged = Lease(**{**json.loads(lease.to_json()), "sig": "ab" * 64})
    verdict, _ = startup(tmp_path, forged)

    assert verdict.ok is False
    assert "簽章" in verdict.reason


def test_startup_rejects_a_non_hex_signature(tmp_path):
    lease = build_lease()
    broken = Lease(**{**json.loads(lease.to_json()), "sig": "zz"})
    verdict, _ = startup(tmp_path, broken)

    assert verdict.ok is False
    assert "簽章" in verdict.reason


def test_startup_expiry_boundary(tmp_path):
    """到期判定：`now > expires_at` 才算過期（等於到期時刻仍可啟動）。"""
    at_expiry = startup(tmp_path / "a", build_lease(), now=EXPIRES)[0]
    assert at_expiry.ok is True

    one_second_late = startup(tmp_path / "b", build_lease(), now=EXPIRES + timedelta(seconds=1))[0]
    assert one_second_late.ok is False
    assert "過期" in one_second_late.reason


# ---- AC-058：兩層時鐘防護 ---------------------------------------------------


def test_clock_layer_one_uses_the_signed_issued_at(tmp_path):
    """第一層（真防線）：系統時間早於 `issued_at − 容忍值` → 強制線上驗證。"""
    tolerated = startup(tmp_path / "a", build_lease(), now=ISSUED - timedelta(seconds=900))[0]
    assert tolerated.force_online is False, "恰好等於容忍邊界不得觸發"
    assert tolerated.ok is True

    early = startup(tmp_path / "b", build_lease(), now=ISSUED - timedelta(seconds=901))[0]
    assert early.force_online is True
    assert early.ok is False, "沒有線上驗證可用時不得放行"


def test_clock_layer_two_uses_the_local_high_water(tmp_path):
    """第二層：本地 `high_water` 比現在時間還新 → 強制線上驗證。"""
    lease_path = tmp_path / "lease.json"
    save_lease(lease_path, build_lease())
    high_water = tmp_path / "high_water.json"
    watermark = INSIDE.timestamp()
    save_high_water(high_water, watermark)

    at_boundary = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: datetime.fromtimestamp(watermark - 900, tz=timezone.utc),
        lease_path=lease_path,
        high_water_path=high_water,
    )
    assert at_boundary.force_online is False, "恰好等於容忍邊界不得觸發"
    assert at_boundary.ok is True

    early = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: datetime.fromtimestamp(watermark - 901, tz=timezone.utc),
        lease_path=lease_path,
        high_water_path=high_water,
    )
    assert early.force_online is True
    assert early.ok is False


def test_clock_layer_two_is_skipped_on_the_first_start(tmp_path):
    """第一次啟動（沒有 `high_water`）不得觸發第二層。"""
    verdict, _ = startup(tmp_path, build_lease())

    assert verdict.force_online is False
    assert verdict.ok is True


def test_forced_online_without_a_service_never_passes(tmp_path):
    """強制線上時若服務不可用（或根本沒有客戶端）→ 不得以本地時間延長授權。"""
    early = ISSUED - timedelta(seconds=3600)

    no_client, _ = startup(tmp_path / "a", build_lease(), now=early)
    assert no_client.force_online is True and no_client.ok is False

    broken, _ = startup(
        tmp_path / "b", build_lease(), now=early, http=FakeHttp(raises=SourceError("offline"))
    )
    assert broken.force_online is True and broken.ok is False
    assert "延長" in broken.reason

    rejected, _ = startup(
        tmp_path / "c", build_lease(), now=early, http=FakeHttp(status=403, body={"error": "no"})
    )
    assert rejected.force_online is True and rejected.ok is False


def test_forced_online_with_a_service_refreshes_the_lease(tmp_path):
    """強制線上且服務可用 → 以伺服器回的新租約放行，並更新 `high_water`。"""
    fresh = build_lease(issued_at="2026-09-25T00:00:00Z", expires_at="2026-10-25T00:00:00Z")
    http = FakeHttp(body=json.loads(fresh.to_json()))
    early = ISSUED - timedelta(seconds=3600)

    verdict, high_water = startup(tmp_path, build_lease(), now=early, http=http)

    assert http.call_count == 1
    url, payload, _timeout = http.calls[0]
    assert url == f"{URL}/v1/verify"
    assert payload == {"key": KEY, "machine": FINGERPRINT}
    assert verdict.ok is True and verdict.force_online is True
    assert verdict.lease == fresh
    assert load_high_water(high_water) == pytest.approx(early.timestamp())


def test_forced_online_rejects_an_invalid_refreshed_lease(tmp_path):
    """線上回來的租約也必須驗章、驗指紋、驗到期（不能因為「線上」就放行）。"""
    http = FakeHttp(body=json.loads(build_lease(machine="ffffffffffffffff").to_json()))
    verdict, _ = startup(
        tmp_path, build_lease(), now=ISSUED - timedelta(seconds=3600), http=http
    )

    assert verdict.force_online is True
    assert verdict.ok is False


def test_startup_advances_the_high_water(tmp_path):
    """成功啟動會把 `high_water` 推進到現在；之後時鐘被往回調就會觸發第二層。"""
    verdict, high_water = startup(tmp_path, build_lease())
    assert verdict.ok is True
    assert load_high_water(high_water) == pytest.approx(INSIDE.timestamp())

    rewound = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: INSIDE - timedelta(seconds=CLOCK_TOLERANCE_SECONDS + 1),
        lease_path=tmp_path / "lease.json",
        high_water_path=high_water,
    )
    assert rewound.force_online is True


def test_startup_never_lowers_the_high_water(tmp_path):
    """容忍值內的成功啟動不得把水位往回寫——否則反覆小幅調鐘就能把防線磨掉。"""
    lease_path = tmp_path / "lease.json"
    save_lease(lease_path, build_lease())
    high_water = tmp_path / "high_water.json"
    watermark = INSIDE.timestamp()
    save_high_water(high_water, watermark)

    verdict = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: INSIDE - timedelta(seconds=100),
        lease_path=lease_path,
        high_water_path=high_water,
    )

    assert verdict.ok is True and verdict.force_online is False
    assert load_high_water(high_water) == pytest.approx(watermark), "水位只能往前"


def test_forced_online_rejects_an_expired_refreshed_lease(tmp_path):
    """線上回來的租約若已經過期，也不得放行。"""
    expired = build_lease(issued_at="2026-08-01T00:00:00Z", expires_at="2026-08-31T00:00:00Z")
    http = FakeHttp(body=json.loads(expired.to_json()))

    verdict, _ = startup(
        tmp_path, build_lease(), now=ISSUED - timedelta(seconds=3600), http=http
    )

    assert http.call_count == 1
    assert verdict.force_online is True
    assert verdict.ok is False


def test_high_water_file_handles_missing_and_corrupt_content(tmp_path):
    """`high_water` 可被刪檔繞過（報告第 6.4 節的已知限制）：損毀視為沒有水位。"""
    path = tmp_path / "high_water.json"
    assert load_high_water(path) is None

    path.write_text("{not json", encoding="utf-8")
    assert load_high_water(path) is None

    path.write_text(json.dumps({"high_water": "not-a-number"}), encoding="utf-8")
    assert load_high_water(path) is None

    save_high_water(path, 1234.5)
    assert load_high_water(path) == 1234.5
    assert path.stat().st_mode & 0o777 == 0o600
