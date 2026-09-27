"""功能分級、授權狀態與更換密鑰（TASK-031／AC-057）。

觀察邊界：只呼叫 `has_feature`／`lease_status`／`check_lease`／`activate`；時間注入、
`tmp_path` 觀察產物。`features` 分級的效果（更新功能停用）由 TASK-032 的
`check_update(enabled=...)` 消費，本張只提供判定。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ediaad.errors import ConfigError
from ediaad.license import (
    Lease,
    activate,
    check_lease,
    has_feature,
    lease_status,
    load_lease,
    save_lease,
    signing_payload,
)

from _ed25519_fixture import FIXTURE_PUBLIC_KEY, sign

KEY = "EDIAAD-2026-0001-TEST"
KEY_TWO = "EDIAAD-2026-0002-TEST"
FINGERPRINT = "0123456789abcdef"
URL = "https://license.example.invalid"
ISSUED = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
EXPIRES = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def build_lease(*, key_id: str = KEY, features=("start", "update")) -> Lease:
    fields = {
        "key_id": key_id,
        "machine": FINGERPRINT,
        "issued_at": ISSUED.isoformat().replace("+00:00", "Z"),
        "expires_at": EXPIRES.isoformat().replace("+00:00", "Z"),
        "features": list(features),
        "catalog_version": "2026-10-01",
        "sig": "00" * 64,
    }
    unsigned = Lease(**fields)
    return Lease(**{**fields, "sig": sign(signing_payload(unsigned))})


class FakeHttp:
    def __init__(self, body) -> None:
        self.body = body
        self.calls: list[tuple[str, dict, float]] = []

    def post(self, url, payload, timeout=10.0):
        self.calls.append((url, dict(payload), timeout))
        return 200, self.body


def startup(tmp_path, lease: Lease, *, now=NOW):
    path = tmp_path / "lease.json"
    save_lease(path, lease)
    return check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: now,
        lease_path=path,
        high_water_path=tmp_path / "high_water.json",
        revoked_path=tmp_path / "revoked.json",
    )


# ---- AC-057：features 功能分級 ----------------------------------------------


def test_has_feature_reflects_the_lease_features():
    both = build_lease(features=("start", "update"))
    start_only = build_lease(features=("start",))

    assert has_feature(both, "start") is True
    assert has_feature(both, "update") is True
    assert has_feature(start_only, "start") is True
    assert has_feature(start_only, "update") is False
    assert has_feature(start_only, "Update") is False, "功能名稱比對必須精確"
    assert has_feature(build_lease(features=()), "start") is False


def test_start_only_lease_still_starts_the_service(tmp_path):
    """缺少 `update` 只停用更新功能，服務本身仍可啟動（TASK-032 會收到 enabled=False）。"""
    lease = build_lease(features=("start",))

    verdict = startup(tmp_path, lease)

    assert verdict.ok is True
    assert has_feature(lease, "start") is True
    assert has_feature(lease, "update") is False


# ---- AC-056／AC-057：授權狀態 -----------------------------------------------


def test_lease_status_is_unactivated_without_a_lease(tmp_path):
    status = lease_status(None, now=NOW, revoked_path=tmp_path / "revoked.json")

    assert status.state == "unactivated"
    assert status.reapply is True
    assert "啟用" in status.message
    assert status.days_remaining is None


def test_lease_status_active_reports_days_remaining(tmp_path):
    status = lease_status(build_lease(), now=NOW, revoked_path=tmp_path / "revoked.json")

    assert status.state == "active"
    assert status.reapply is False
    assert status.message == ""
    assert status.expires_at == "2026-10-24T12:00:00Z"
    assert status.days_remaining == pytest.approx(23.0, abs=0.01)


def test_lease_status_expiry_boundary(tmp_path):
    """等於到期時刻仍算有效；超過才過期並附重新申請訊息。"""
    at_expiry = lease_status(build_lease(), now=EXPIRES, revoked_path=tmp_path / "r.json")
    assert at_expiry.state == "active"

    late = lease_status(
        build_lease(), now=EXPIRES + timedelta(seconds=1), revoked_path=tmp_path / "r.json"
    )
    assert late.state == "expired"
    assert late.reapply is True
    assert "重新申請" in late.message


def test_lease_status_revoked_only_for_the_matching_key(tmp_path):
    revoked_path = tmp_path / "revoked.json"
    revoked_path.write_text(
        json.dumps({"key_id": KEY, "revoked_at": NOW.timestamp()}), encoding="utf-8"
    )

    revoked = lease_status(build_lease(key_id=KEY), now=NOW, revoked_path=revoked_path)
    assert revoked.state == "revoked"
    assert revoked.reapply is True
    assert "撤銷" in revoked.message

    other = lease_status(build_lease(key_id=KEY_TWO), now=NOW, revoked_path=revoked_path)
    assert other.state == "active", "別的密鑰不該被別人的撤銷標記影響"


def test_revoked_marker_is_corruption_tolerant(tmp_path):
    revoked_path = tmp_path / "revoked.json"
    for content in ("{not json", json.dumps({"key_id": 123}), json.dumps(["x"]), ""):
        revoked_path.write_text(content, encoding="utf-8")
        status = lease_status(build_lease(), now=NOW, revoked_path=revoked_path)
        assert status.state == "active", content


# ---- AC-057：更換密鑰 -------------------------------------------------------


def test_replacing_the_key_uses_the_new_lease(tmp_path):
    """網頁輸入新密鑰後以新租約為準；舊 key_id 不再被接受（也不受舊撤銷標記影響）。"""
    path = tmp_path / "lease.json"
    revoked_path = tmp_path / "revoked.json"
    old = build_lease(key_id=KEY)
    save_lease(path, old)
    revoked_path.write_text(
        json.dumps({"key_id": KEY, "revoked_at": NOW.timestamp()}), encoding="utf-8"
    )

    new = build_lease(key_id=KEY_TWO, features=("start", "update"))
    http = FakeHttp(json.loads(new.to_json()))
    returned = activate(
        KEY_TWO,
        fingerprint=FINGERPRINT,
        http=http,
        url=URL,
        now=lambda: NOW,
        public_key=FIXTURE_PUBLIC_KEY,
        lease_path=path,
    )

    assert returned == new
    assert load_lease(path) == new
    assert lease_status(new, now=NOW, revoked_path=revoked_path).state == "active"
    verdict = check_lease(
        fingerprint=FINGERPRINT,
        public_key=FIXTURE_PUBLIC_KEY,
        now=lambda: NOW,
        lease_path=path,
        high_water_path=tmp_path / "high_water.json",
        revoked_path=revoked_path,
    )
    assert verdict.ok is True, "換密鑰後不該被舊 key_id 的撤銷標記擋住"


def test_activate_rejects_a_revoked_key_again(tmp_path):
    """同一把已被撤銷的密鑰重新啟用時，伺服器若回 403 → 不得放行。"""
    path = tmp_path / "lease.json"
    revoked_path = tmp_path / "revoked.json"
    revoked_path.write_text(
        json.dumps({"key_id": KEY, "revoked_at": NOW.timestamp()}), encoding="utf-8"
    )

    class Rejecting:
        def post(self, url, payload, timeout=10.0):
            return 403, {"status": "revoked"}

    with pytest.raises(ConfigError):
        activate(
            KEY,
            fingerprint=FINGERPRINT,
            http=Rejecting(),
            url=URL,
            now=lambda: NOW,
            public_key=FIXTURE_PUBLIC_KEY,
            lease_path=path,
        )
    assert not path.exists()


def test_default_revoked_path_lives_in_the_ediaad_home(monkeypatch, tmp_path):
    """未指定路徑時，撤銷標記落在 `$EDIAAD_HOME`（與租約同一個資料根）。"""
    from ediaad import paths

    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))

    assert paths.revoked_path() == tmp_path / "revoked.json"
