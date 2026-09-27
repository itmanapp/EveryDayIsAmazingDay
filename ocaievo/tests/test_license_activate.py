"""首次啟用與租約落地（TASK-030／AC-052）。

觀察邊界：只呼叫 `activate`／`save_lease`／`load_lease`；HTTP 以計數假客戶端注入
（可強制回 200／4xx／5xx／拋例外），時間以固定 `now` 注入，租約檔以 `tmp_path` 觀察。
**全程離線**，租約簽章由測試專用的純 Python 夾具產生。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ediaad.errors import ConfigError, SourceError
from ediaad.license import (
    LICENSE_PUBLIC_KEY,
    Lease,
    activate,
    ed25519_verify,
    load_lease,
    save_lease,
    signing_payload,
)

from _ed25519_fixture import FIXTURE_PUBLIC_KEY, sign

PROJECT_DIR = Path(__file__).resolve().parent.parent

KEY = "EDIAAD-2026-0001-TEST"
FINGERPRINT = "0123456789abcdef"
ISSUED_AT = "2026-09-24T12:00:00Z"
EXPIRES_AT = "2026-10-24T12:00:00Z"
URL = "https://license.example.invalid"
FIXED_NOW = datetime(2026, 9, 24, 12, 30, tzinfo=timezone.utc)


def build_lease(**overrides) -> Lease:
    """一份以測試夾具簽章的合成租約（`sig` 涵蓋除簽章本身以外的所有欄位）。"""
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
    """計數假客戶端：介面只有 `post(url, payload, timeout) -> (status, body)`。"""

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


def activate_with(lease: Lease, **overrides):
    """以假 HTTP 執行一次啟用；回傳 `(lease, http)`。"""
    http = overrides.pop("http", None) or FakeHttp(body=json.loads(lease.to_json()))
    kwargs = {
        "fingerprint": FINGERPRINT,
        "http": http,
        "url": URL,
        "now": lambda: FIXED_NOW,
        "public_key": FIXTURE_PUBLIC_KEY,
    }
    kwargs.update(overrides)
    return activate(KEY, **kwargs), http


# ---- AC-052：啟用請求與落地 -------------------------------------------------


def test_activate_posts_key_and_fingerprint_and_lands_the_lease(tmp_path):
    """第一個失敗行為：`activate` 不存在（collection error）；實作後必須完成啟用。"""
    lease = build_lease()
    path = tmp_path / "lease.json"

    returned, http = activate_with(lease, lease_path=path)

    assert http.call_count == 1
    url, payload, _timeout = http.calls[0]
    assert url == f"{URL}/v1/activate"
    assert payload == {"key": KEY, "machine": FINGERPRINT}
    assert returned == lease
    assert load_lease(path) == lease, "回傳值與落地內容必須一致"

    # 簽章涵蓋「除 sig 外的所有欄位」，以伺服器公鑰驗章必須為真
    assert ed25519_verify(FIXTURE_PUBLIC_KEY, signing_payload(returned), bytes.fromhex(returned.sig))

    # 租約長度恰為 30 天（AC-052）
    issued = datetime.fromisoformat(returned.issued_at.replace("Z", "+00:00"))
    expires = datetime.fromisoformat(returned.expires_at.replace("Z", "+00:00"))
    assert expires - issued == timedelta(days=30)


def test_activate_accepts_a_json_string_body(tmp_path):
    """真實的 HTTP 客戶端回的是字串；`activate` 必須兩種都吃。"""
    lease = build_lease()
    http = FakeHttp(body=lease.to_json())

    returned, _ = activate_with(lease, http=http, lease_path=tmp_path / "lease.json")

    assert returned == lease


def test_activate_rejects_a_lease_for_another_machine(tmp_path):
    lease = build_lease(machine="ffffffffffffffff")
    path = tmp_path / "lease.json"

    with pytest.raises(ConfigError) as error:
        activate_with(lease, lease_path=path)

    assert "機器" in str(error.value) or "machine" in str(error.value)
    assert not path.exists(), "驗證失敗不得落地"


def test_activate_rejects_an_invalid_signature(tmp_path):
    """簽章被換掉（或用了別把金鑰）→ 不得落地。"""
    lease = build_lease()
    forged = Lease(**{**json.loads(lease.to_json()), "sig": "ab" * 64})
    path = tmp_path / "lease.json"

    with pytest.raises(ConfigError) as error:
        activate_with(forged, lease_path=path)

    assert "簽章" in str(error.value)
    assert not path.exists()


def test_activate_rejects_a_non_hex_or_wrong_length_signature(tmp_path):
    """簽章格式不對時要給**可讀的原因**（指出十六進位或長度），不是籠統的「驗證失敗」。"""
    lease = build_lease()
    for bad_sig, fragment in (
        ("not-hex", "十六進位"),
        ("zz", "十六進位"),
        ("ab" * 32, "128"),
        ("ab" * 65, "128"),
    ):
        broken = Lease(**{**json.loads(lease.to_json()), "sig": bad_sig})
        with pytest.raises(ConfigError) as error:
            activate_with(broken, lease_path=tmp_path / "lease.json")
        assert fragment in str(error.value), (bad_sig, str(error.value))


def test_activate_rejects_a_duration_that_is_not_thirty_days(tmp_path):
    short = build_lease(expires_at="2026-10-01T12:00:00Z")

    with pytest.raises(ConfigError) as error:
        activate_with(short, lease_path=tmp_path / "lease.json")

    assert "30" in str(error.value)


def test_activate_maps_failures_to_the_documented_error_layers(tmp_path):
    path = tmp_path / "lease.json"

    with pytest.raises(ConfigError):
        activate_with(build_lease(), http=FakeHttp(status=403, body={"error": "無效密鑰"}), lease_path=path)
    with pytest.raises(SourceError):
        activate_with(build_lease(), http=FakeHttp(status=503, body="busy"), lease_path=path)
    with pytest.raises(SourceError):
        activate_with(build_lease(), http=FakeHttp(raises=OSError("connection refused")), lease_path=path)
    with pytest.raises(SourceError):
        activate_with(build_lease(), http=FakeHttp(raises=SourceError("tls failure")), lease_path=path)

    assert not path.exists(), "任何失敗都不得留下租約"


def test_activate_rejects_a_malformed_response(tmp_path):
    for body in ({"lease": {}}, "{not json", json.dumps({"key_id": "x"})):
        with pytest.raises(ConfigError):
            activate_with(build_lease(), http=FakeHttp(body=body), lease_path=tmp_path / "lease.json")


def test_activate_defaults_to_the_embedded_public_key_and_fails_closed(tmp_path):
    """未指定公鑰時用 `LICENSE_PUBLIC_KEY`（目前是全零佔位）→ 必須拒絕（fail closed）。"""
    assert LICENSE_PUBLIC_KEY == bytes(32)

    with pytest.raises(ConfigError):
        activate(
            KEY,
            fingerprint=FINGERPRINT,
            http=FakeHttp(body=json.loads(build_lease().to_json())),
            url=URL,
            now=lambda: FIXED_NOW,
            lease_path=tmp_path / "lease.json",
        )


def test_activate_requires_a_non_empty_key(tmp_path):
    """空白密鑰不必浪費一次網路請求，也不得落地。"""
    for bad_key in ("", "   ", None, 123):
        with pytest.raises(ConfigError):
            activate(
                bad_key,
                fingerprint=FINGERPRINT,
                http=FakeHttp(body=json.loads(build_lease().to_json())),
                url=URL,
                now=lambda: FIXED_NOW,
                public_key=FIXTURE_PUBLIC_KEY,
                lease_path=tmp_path / "lease.json",
            )
    assert not (tmp_path / "lease.json").exists()


# ---- 落地：原子性、權限與讀回 -------------------------------------------------


def test_save_lease_is_atomic_and_keeps_the_previous_lease(tmp_path):
    path = tmp_path / "lease.json"
    first = build_lease()
    save_lease(path, first)
    original = path.read_text(encoding="utf-8")

    # 目標目錄不可寫 → 寫入失敗，但既有檔案不得損毀、也不得留下暫存檔
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    blocked = readonly / "lease.json"
    blocked.write_text(original, encoding="utf-8")
    os.chmod(readonly, 0o500)
    try:
        with pytest.raises(SourceError):
            save_lease(blocked, build_lease(expires_at="2026-10-01T12:00:00Z"))
    finally:
        os.chmod(readonly, 0o700)

    assert blocked.read_text(encoding="utf-8") == original
    assert not list(readonly.glob("*.tmp")), "不得留下半寫的暫存檔"


def test_lease_file_is_owner_only(tmp_path):
    path = tmp_path / "lease.json"
    save_lease(path, build_lease())

    assert path.stat().st_mode & 0o777 == 0o600


def test_load_lease_handles_missing_and_corrupt_files(tmp_path):
    assert load_lease(tmp_path / "absent.json") is None

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_lease(corrupt)

    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({"key_id": "x"}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_lease(unknown)


def test_save_lease_round_trips_through_the_file(tmp_path):
    path = tmp_path / "lease.json"
    lease = build_lease()

    save_lease(path, lease)

    assert load_lease(path) == lease
    assert json.loads(path.read_text(encoding="utf-8"))["machine"] == FINGERPRINT


def test_default_artifact_paths_live_in_the_ediaad_home(monkeypatch, tmp_path):
    """未指定路徑時，租約與時鐘水位都落在 `$EDIAAD_HOME`（SPEC 第 5 節的產物位置）。"""
    from ediaad import paths

    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))

    assert paths.lease_path() == tmp_path / "lease.json"
    assert paths.high_water_path() == tmp_path / "high_water.json"
