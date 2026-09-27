"""續期、到期停止與撤銷（TASK-031／AC-056）。

觀察邊界：只呼叫 `renew`／`lease_status`／`check_lease`；HTTP 以假客戶端注入（可回
200／403／429／5xx／拋例外），時間以固定 `now` 注入，`lease.json` 以 `tmp_path` 觀察。
租約簽章沿用 TASK-030 的測試夾具。**全程離線。**
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ediaad.errors import ConfigError, SourceError
from ediaad.license import (
    Lease,
    check_lease,
    lease_status,
    load_lease,
    renew,
    save_lease,
    signing_payload,
)

from _ed25519_fixture import FIXTURE_PUBLIC_KEY, sign

KEY = "EDIAAD-2026-0001-TEST"
FINGERPRINT = "0123456789abcdef"
URL = "https://license.example.invalid"
ISSUED = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
EXPIRES = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
RENEWED_EXPIRES = "2026-11-19T12:00:00Z"


def build_lease(
    *,
    key_id: str = KEY,
    issued_at: datetime = ISSUED,
    expires_at: datetime = EXPIRES,
    machine: str = FINGERPRINT,
    features=("start", "update"),
) -> Lease:
    fields = {
        "key_id": key_id,
        "machine": machine,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "features": list(features),
        "catalog_version": "2026-10-01",
        "sig": "00" * 64,
    }
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


def renewed_lease(**overrides) -> Lease:
    """伺服器續期後應回的租約：`issued_at = now`、`expires_at = now + 30 天`。"""
    values = {"issued_at": NOW, "expires_at": NOW + timedelta(days=30)}
    values.update(overrides)
    return build_lease(**values)


def renew_with(tmp_path, lease: Lease, **overrides):
    path = tmp_path / "lease.json"
    save_lease(path, lease)
    http = overrides.pop("http", None) or FakeHttp(body=json.loads(renewed_lease().to_json()))
    kwargs = {
        "http": http,
        "url": URL,
        "now": lambda: NOW,
        "trigger": "timer",
        "public_key": FIXTURE_PUBLIC_KEY,
        "lease_path": path,
    }
    kwargs.update(overrides)
    return renew(lease, **kwargs), http, path


# ---- AC-056：成功續期 -------------------------------------------------------


def test_renew_extends_thirty_days(tmp_path):
    """第一個失敗行為：`renew` 不存在（collection error）；實作後必須重算 30 天並覆寫。"""
    lease = build_lease()
    returned, http, path = renew_with(tmp_path, lease)

    assert http.call_count == 1
    url, payload, _timeout = http.calls[0]
    assert url == f"{URL}/v1/renew"
    assert payload == {"key": KEY, "machine": FINGERPRINT, "trigger": "timer"}
    assert returned.expires_at == RENEWED_EXPIRES
    assert returned.issued_at == "2026-10-20T12:00:00Z"
    assert load_lease(path) == returned, "續期成功必須原子覆寫租約檔"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("trigger", ["start", "timer", "manual"])
def test_renew_accepts_the_three_documented_triggers(tmp_path, trigger):
    _returned, http, _path = renew_with(tmp_path / trigger, build_lease(), trigger=trigger)

    assert http.calls[0][1]["trigger"] == trigger


def test_renew_rejects_an_unknown_trigger_without_a_request(tmp_path):
    http = FakeHttp(body=json.loads(renewed_lease().to_json()))

    with pytest.raises(ConfigError) as error:
        renew_with(tmp_path, build_lease(), trigger="forever", http=http)

    assert "trigger" in str(error.value)
    assert http.call_count == 0, "不合法的觸發來源不必送出去"


def test_renewed_lease_passes_the_startup_check(tmp_path):
    _returned, _http, path = renew_with(tmp_path, build_lease())

    verdict = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: NOW + timedelta(days=1),
        lease_path=path,
        high_water_path=tmp_path / "high_water.json",
    )

    assert verdict.ok is True


# ---- AC-056：後端對過期租約回 403（導流的核心） -----------------------------


def test_renew_403_does_not_touch_the_local_lease(tmp_path):
    """後端拒絕續期時，本地租約的到期日不得被動到，且要能判斷為已過期。"""
    lease = build_lease()
    after_expiry = EXPIRES + timedelta(days=1)
    http = FakeHttp(status=403, body={"error": "lease expired"})

    with pytest.raises(ConfigError) as error:
        renew_with(tmp_path, lease, http=http, now=lambda: after_expiry)

    assert "拒絕" in str(error.value) or "過期" in str(error.value)
    assert load_lease(tmp_path / "lease.json") == lease, "失敗不得改寫租約"

    status = lease_status(lease, now=after_expiry, revoked_path=tmp_path / "revoked.json")
    assert status.state == "expired"
    assert status.reapply is True
    assert "重新申請" in status.message


def test_renew_403_with_revoked_status_marks_the_key_revoked(tmp_path):
    lease = build_lease()
    http = FakeHttp(status=403, body={"status": "revoked", "error": "key revoked"})

    with pytest.raises(ConfigError) as error:
        renew_with(tmp_path, lease, http=http)

    assert "撤銷" in str(error.value)
    status = lease_status(lease, now=NOW, revoked_path=tmp_path / "revoked.json")
    assert status.state == "revoked"
    assert status.reapply is True

    # 之後同一把密鑰的啟動驗證也必須停止（即使租約本身還沒到期）
    verdict = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: NOW,
        lease_path=tmp_path / "lease.json",
        high_water_path=tmp_path / "high_water.json",
        revoked_path=tmp_path / "revoked.json",
    )
    assert verdict.ok is False
    assert "撤銷" in verdict.reason


def test_renew_maps_failures_to_the_documented_error_layers(tmp_path):
    lease = build_lease()
    for http, expected in (
        (FakeHttp(status=429, body="slow down"), SourceError),
        (FakeHttp(status=500, body="boom"), SourceError),
        (FakeHttp(raises=OSError("refused")), SourceError),
        (FakeHttp(raises=SourceError("tls")), SourceError),
        (FakeHttp(status=400, body={"error": "bad request"}), ConfigError),
    ):
        with pytest.raises(expected):
            renew_with(tmp_path, lease, http=http)
        assert load_lease(tmp_path / "lease.json") == lease


def test_renew_rejects_a_response_that_does_not_extend_the_lease(tmp_path):
    """每一個契約檢查都必須**各自**可觀測，否則兩條檢查會互相掩蓋。"""
    lease = build_lease()
    cases = {
        # 長度不是 30 天，但確實有延長 → 只有「長度」檢查能擋
        "duration": renewed_lease(expires_at=NOW + timedelta(days=60)),
        # 長度是 30 天，但到期時間比原本更早 → 只有「必須延長」檢查能擋
        "not-extending": build_lease(
            issued_at=EXPIRES - timedelta(days=60), expires_at=EXPIRES - timedelta(days=30)
        ),
        "other-machine": renewed_lease(machine="ffffffffffffffff"),
        "bad-signature": Lease(**{**json.loads(renewed_lease().to_json()), "sig": "ab" * 64}),
        "other-key": renewed_lease(key_id="EDIAAD-2026-9999"),
    }
    for name, bad in cases.items():
        with pytest.raises(ConfigError) as error:
            renew_with(tmp_path, lease, http=FakeHttp(body=json.loads(bad.to_json())))
        assert str(error.value), name
        assert load_lease(tmp_path / "lease.json") == lease, f"不合法的續期結果不得落地（{name}）"
