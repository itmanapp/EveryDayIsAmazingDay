"""`python -m ediaad license …` 的端到端子程序測試（TASK-036／AC-064）。

`activate`／`renew` 以測試內啟動的 loopback 假授權服務驗證（簽章用 TASK-030 的公開測試
向量金鑰），全程不連外網。`status` 則以「服務網址指向關閉的埠」證明**完全不連網**。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from _cli_helpers import (
    NOW,
    LicenseServer,
    build_lease,
    cli_env,
    free_port,
    run_cli,
    write_lease,
)

from ediaad.license import load_lease, machine_fingerprint

FINGERPRINT = machine_fingerprint()


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_license_subcommands_are_registered():
    from ediaad.cli import build_parser

    parser = build_parser()
    status = parser.parse_args(["license", "status"])
    activate = parser.parse_args(["license", "activate", "--key", "K"])
    renew = parser.parse_args(["license", "renew"])
    by_trigger = parser.parse_args(["license", "renew", "--trigger", "timer"])

    assert status.command == "license" and status.license_command == "status"
    assert activate.key == "K"
    assert renew.trigger == "manual", "預設 trigger 必須是 manual"
    assert by_trigger.trigger == "timer"


def test_license_status_without_a_lease_is_an_input_error(home):
    result = run_cli("license", "status", env=cli_env(home))

    assert result.returncode == 2
    assert "尚未啟用" in result.stderr
    assert "Traceback" not in result.stderr


def test_license_status_shows_remaining_days_without_touching_the_network(home):
    write_lease(home, build_lease(FINGERPRINT))
    # 指向一個關閉的埠：`status` 若有任何連網行為就會失敗
    env = cli_env(home, EDIAAD_LICENSE_URL=f"http://127.0.0.1:{free_port()}")

    result = run_cli("license", "status", env=env)

    assert result.returncode == 0, result.stderr
    assert "有效期內" in result.stdout
    assert "2026-10-24T12:00:00Z" in result.stdout
    assert "剩餘天數" in result.stdout
    assert "update" in result.stdout


def test_license_status_reports_expired_and_revoked(home):
    expired = build_lease(FINGERPRINT, issued_at=NOW - timedelta(days=60), expires_at=NOW - timedelta(days=30))
    write_lease(home, expired)

    expired_result = run_cli("license", "status", env=cli_env(home))
    assert expired_result.returncode == 2
    assert "已過期" in expired_result.stdout or "已過期" in expired_result.stderr
    assert "重新申請" in (expired_result.stdout + expired_result.stderr)

    write_lease(home, build_lease(FINGERPRINT))
    (home / "revoked.json").write_text(
        json.dumps({"key_id": "EDIAAD-2026-0001", "revoked_at": 1.0}), encoding="utf-8"
    )
    revoked_result = run_cli("license", "status", env=cli_env(home))
    assert revoked_result.returncode == 2
    assert "撤銷" in (revoked_result.stdout + revoked_result.stderr)


def test_license_status_reports_a_corrupt_lease_file(home):
    (home / "lease.json").write_text("{not json", encoding="utf-8")
    original = (home / "lease.json").read_text(encoding="utf-8")

    result = run_cli("license", "status", env=cli_env(home))

    assert result.returncode == 2
    assert "lease.json" in result.stderr
    assert (home / "lease.json").read_text(encoding="utf-8") == original


def test_license_activate_requires_a_key_and_a_service_url(home):
    missing_key = run_cli("license", "activate", env=cli_env(home))
    assert missing_key.returncode == 2
    assert "--key" in missing_key.stderr

    no_url = run_cli("license", "activate", "--key", "EDIAAD-2026-0001", env=cli_env(home))
    assert no_url.returncode == 2
    assert "EDIAAD_LICENSE_URL" in no_url.stderr


def test_license_activate_lands_the_lease_and_the_service_accepts_it(home):
    lease = build_lease(FINGERPRINT)

    def responder(payload, path):
        assert path == "/v1/activate"
        assert payload["machine"] == FINGERPRINT
        return 200, json.loads(lease.to_json())

    with LicenseServer(responder) as server:
        result = run_cli(
            "license", "activate", "--key", "EDIAAD-2026-0001",
            env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
        )

    assert result.returncode == 0, result.stderr
    assert "已啟用" in result.stdout
    assert "2026-10-24T12:00:00Z" in result.stdout
    stored = load_lease(home / "lease.json")
    assert stored == lease, "落地的必須是伺服器簽發的租約"
    assert server.recorded[0].payload["key"] == "EDIAAD-2026-0001"


def test_license_activate_rejects_a_revoked_key_without_landing(home):
    with LicenseServer(lambda payload, path: (403, {"error": "revoked"})) as server:
        result = run_cli(
            "license", "activate", "--key", "EDIAAD-2026-0001",
            env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
        )

    assert result.returncode == 2, result.stderr
    assert "拒絕" in result.stderr
    assert not (home / "lease.json").exists(), "失敗不得落地租約"


def test_license_activate_reports_an_unreachable_service(home):
    env = cli_env(home, EDIAAD_LICENSE_URL=f"http://127.0.0.1:{free_port()}")

    result = run_cli("license", "activate", "--key", "EDIAAD-2026-0001", env=env, timeout=60)

    assert result.returncode == 1
    assert "無法連線" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (home / "lease.json").exists()


def test_license_activate_requires_a_valid_signature(home):
    """拿著別把金鑰簽的租約（同一台機器、30 天）仍必須被拒絕。"""
    from _ed25519_fixture import sign  # noqa: F401 - 只確認夾具存在
    from ediaad.license import Lease

    lease = build_lease(FINGERPRINT)
    broken = Lease(**{**json.loads(lease.to_json()), "sig": "ab" * 64})

    with LicenseServer(lambda payload, path: (200, json.loads(broken.to_json()))) as server:
        result = run_cli(
            "license", "activate", "--key", "EDIAAD-2026-0001",
            env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
        )

    assert result.returncode == 2
    assert "簽章" in result.stderr
    assert not (home / "lease.json").exists()


def test_license_renew_extends_the_lease(home):
    current = build_lease(FINGERPRINT, issued_at=NOW - timedelta(days=20), expires_at=NOW + timedelta(days=10))
    write_lease(home, current)
    renewed = build_lease(FINGERPRINT, issued_at=NOW, expires_at=NOW + timedelta(days=30))

    with LicenseServer(lambda payload, path: (200, json.loads(renewed.to_json()))) as server:
        result = run_cli(
            "license", "renew",
            env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
        )

    assert result.returncode == 0, result.stderr
    assert "已續期" in result.stdout
    assert server.paths == ["/v1/renew"]
    assert server.recorded[0].payload == {
        "key": "EDIAAD-2026-0001",
        "machine": FINGERPRINT,
        "trigger": "manual",
    }, "預設 trigger 必須是 manual，且 request 欄位與 TASK-031 的契約一致"
    assert load_lease(home / "lease.json") == renewed


def test_license_renew_passes_each_trigger(home):
    for trigger in ("start", "timer", "manual"):
        write_lease(home, build_lease(FINGERPRINT, issued_at=NOW - timedelta(days=20)))
        renewed = build_lease(FINGERPRINT, issued_at=NOW, expires_at=NOW + timedelta(days=30))
        with LicenseServer(lambda payload, path: (200, json.loads(renewed.to_json()))) as server:
            result = run_cli(
                "license", "renew", "--trigger", trigger,
                env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
            )
        assert result.returncode == 0, result.stderr
        assert server.recorded[0].payload["trigger"] == trigger


def test_license_renew_rejects_an_invalid_trigger(home):
    result = run_cli(
        "license", "renew", "--trigger", "cron",
        env=cli_env(home, EDIAAD_LICENSE_URL=f"http://127.0.0.1:{free_port()}"),
    )

    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_license_renew_of_an_expired_lease_is_an_input_error(home):
    """後端對過期租約回 403 → exit 2（狀態錯誤），且**不得**修改本地租約。"""
    expired = build_lease(FINGERPRINT, issued_at=NOW - timedelta(days=60), expires_at=NOW - timedelta(days=30))
    write_lease(home, expired)
    original = (home / "lease.json").read_text(encoding="utf-8")

    with LicenseServer(lambda payload, path: (403, {"status": "expired", "message": "過期"})) as server:
        result = run_cli(
            "license", "renew",
            env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
        )

    assert result.returncode == 2
    assert "重新申請" in result.stderr
    assert (home / "lease.json").read_text(encoding="utf-8") == original, "失敗不得動到租約"


def test_license_renew_revoked_lease_marks_revocation(home):
    write_lease(home, build_lease(FINGERPRINT))
    original = (home / "lease.json").read_text(encoding="utf-8")

    with LicenseServer(lambda payload, path: (403, {"status": "revoked", "message": "撤銷"})) as server:
        result = run_cli(
            "license", "renew",
            env=cli_env(home, EDIAAD_LICENSE_URL=server.url),
        )

    assert result.returncode == 2
    assert "撤銷" in result.stderr
    assert (home / "lease.json").read_text(encoding="utf-8") == original
    assert (home / "revoked.json").is_file(), "403 且指出 revoked 時要落地撤銷標記"


def test_license_renew_reports_an_unreachable_service(home):
    write_lease(home, build_lease(FINGERPRINT))
    original = (home / "lease.json").read_text(encoding="utf-8")
    env = cli_env(home, EDIAAD_LICENSE_URL=f"http://127.0.0.1:{free_port()}")

    result = run_cli("license", "renew", env=env, timeout=60)

    assert result.returncode == 1
    assert "無法連線" in result.stderr
    assert (home / "lease.json").read_text(encoding="utf-8") == original


def test_public_key_from_env_validates_and_defaults():
    from ediaad.errors import ConfigError
    from ediaad.license import LICENSE_PUBLIC_KEY, PUBLIC_KEY_ENV, public_key_from_env

    assert public_key_from_env({}) == LICENSE_PUBLIC_KEY
    assert public_key_from_env({PUBLIC_KEY_ENV: "   "}) == LICENSE_PUBLIC_KEY

    key = b"\x01" * 32
    assert public_key_from_env({PUBLIC_KEY_ENV: key.hex()}) == key

    with pytest.raises(ConfigError, match="十六進位"):
        public_key_from_env({PUBLIC_KEY_ENV: "not-hex"})
    with pytest.raises(ConfigError, match="32 位元組"):
        public_key_from_env({PUBLIC_KEY_ENV: "ab" * 16}), "長度不對必須吵"


def test_license_renew_without_a_lease_is_an_input_error(home):
    with LicenseServer(lambda payload, path: (200, {})) as server:
        result = run_cli("license", "renew", env=cli_env(home, EDIAAD_LICENSE_URL=server.url))

    assert result.returncode == 2
    assert "尚未啟用" in result.stderr
    assert server.recorded == [], "沒有租約就不該發出任何請求"
