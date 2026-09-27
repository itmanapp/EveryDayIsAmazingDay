"""機器指紋與租約模型（TASK-028／AC-055）。

觀察邊界：
1. **指紋（自動）**：`machine_fingerprint` 以注入的 `read_text` 與 `tmp_path` 的假
   `machine-id` 驗證雜湊規則、空白處理、跨程序穩定性與錯誤處理；另以真實
   `/etc/machine-id` 驗證**形狀**（不記錄真實指紋值）。
2. **租約（自動）**：`Lease` 的 JSON 往返與嚴格還原、frozen、簽章涵蓋範圍。
3. **指紋閘門（自動）**：`verify_lease` 以注入的 `verify_sig` 單獨驗證指紋那一半；
   簽章是否有效由 TASK-029 負責（本張不假裝它已經完成）。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ediaad.errors import ConfigError
from ediaad.license import Lease, machine_fingerprint, signing_payload, verify_lease

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"

FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{16}$")


def write_machine_id(tmp_path: Path, content: str, name: str = "machine-id") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def build_lease(**overrides) -> Lease:
    fields = {
        "key_id": "EDIAAD-2026-0001",
        "machine": "0123456789abcdef",
        "issued_at": "2026-09-24T12:00:00Z",
        "expires_at": "2026-10-24T12:00:00Z",
        "features": ["start", "update"],
        "catalog_version": "2026-10-01",
        "sig": "00" * 32,
    }
    fields.update(overrides)
    return Lease(**fields)


# ---- AC-055：機器指紋 -------------------------------------------------------


def test_machine_fingerprint_is_the_sha256_prefix(tmp_path):
    """第一個失敗行為：模組不存在（collection error）；實作後必須是 sha256 前 16 碼。"""
    path = write_machine_id(tmp_path, "abc123\n")

    fingerprint = machine_fingerprint(machine_id_path=str(path))

    assert fingerprint == hashlib.sha256(b"abc123").hexdigest()[:16]
    assert len(fingerprint) == 16
    assert FINGERPRINT_PATTERN.match(fingerprint)


def test_machine_fingerprint_ignores_surrounding_whitespace(tmp_path):
    """實測的 `/etc/machine-id` 是 33 bytes（含結尾換行）；空白一律先去乾淨再雜湊。"""
    expected = hashlib.sha256(b"abc123").hexdigest()[:16]

    for index, content in enumerate(["abc123", "abc123\n", "  abc123  ", "\nabc123\n\n"]):
        path = write_machine_id(tmp_path, content, name=f"machine-id-{index}")
        assert machine_fingerprint(machine_id_path=str(path)) == expected, repr(content)


def test_machine_fingerprint_is_stable_across_processes(tmp_path):
    """同一台機器跨程序重算必須完全相同（租約綁機器，不能每次啟動都變）。"""
    path = write_machine_id(tmp_path, "abc123\n")
    script = (
        "from ediaad.license import machine_fingerprint;"
        f"print(machine_fingerprint(machine_id_path={str(path)!r}))"
    )
    completed = subprocess.run(
        [str(PYTHON), "-c", script],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == machine_fingerprint(machine_id_path=str(path))


def test_machine_fingerprint_reads_the_file_by_default(tmp_path):
    """`read_text` 未注入時必須真的讀檔（不是只支援注入）。"""
    path = write_machine_id(tmp_path, "abcdef\n")

    assert machine_fingerprint(machine_id_path=str(path)) == hashlib.sha256(
        b"abcdef"
    ).hexdigest()[:16]


def test_machine_fingerprint_matches_the_real_machine_id_shape():
    """真實 `/etc/machine-id` 只驗形狀，**不記錄**指紋值（避免把機器資訊寫進證據）。"""
    from ediaad.license import DEFAULT_MACHINE_ID_PATH

    assert DEFAULT_MACHINE_ID_PATH == "/etc/machine-id", "AC-055 指定的來源就是這個檔案"

    try:
        real = machine_fingerprint()
    except ConfigError as error:
        pytest.skip(f"這台機器沒有可讀的 /etc/machine-id：{error}")

    assert FINGERPRINT_PATTERN.match(real)


def test_machine_fingerprint_rejects_unreadable_or_empty_sources(tmp_path):
    def broken(_path: str) -> str:
        raise OSError("permission denied")

    with pytest.raises(ConfigError) as missing:
        machine_fingerprint(machine_id_path="/etc/does-not-exist", read_text=broken)
    assert "/etc/does-not-exist" in str(missing.value)

    empty = write_machine_id(tmp_path, "", name="empty")
    with pytest.raises(ConfigError) as blank:
        machine_fingerprint(machine_id_path=str(empty))
    assert str(empty) in str(blank.value)

    spaces = write_machine_id(tmp_path, "   \n", name="spaces")
    with pytest.raises(ConfigError):
        machine_fingerprint(machine_id_path=str(spaces))


def test_machine_fingerprint_differs_for_different_machine_ids(tmp_path):
    first = write_machine_id(tmp_path, "machine-one\n", name="one")
    second = write_machine_id(tmp_path, "machine-two\n", name="two")

    assert machine_fingerprint(machine_id_path=str(first)) != machine_fingerprint(
        machine_id_path=str(second)
    )


# ---- AC-055：租約模型 -------------------------------------------------------


def test_lease_json_round_trip_uses_the_spec_fields():
    lease = build_lease()

    payload = json.loads(lease.to_json())

    assert set(payload) == {
        "key_id",
        "machine",
        "issued_at",
        "expires_at",
        "features",
        "catalog_version",
        "sig",
    }
    assert lease.to_json() == json.dumps(payload, sort_keys=True, ensure_ascii=False)
    assert Lease.from_json(lease.to_json()) == lease
    assert Lease.from_json(payload) == lease

    # 以 tuple 建構也必須能往返（JSON 只有陣列，讀回來是 list）
    tuple_lease = build_lease(features=("start", "update"))
    assert Lease.from_json(tuple_lease.to_json()) == tuple_lease


def test_lease_is_frozen():
    lease = build_lease()

    with pytest.raises(Exception):
        lease.machine = "ffffffffffffffff"  # type: ignore[misc]


def test_lease_from_json_is_strict():
    lease = build_lease()
    payload = json.loads(lease.to_json())

    missing = dict(payload)
    del missing["machine"]
    with pytest.raises(ConfigError) as missing_error:
        Lease.from_json(missing)
    assert "machine" in str(missing_error.value)

    unknown = dict(payload, extra="x")
    with pytest.raises(ConfigError) as unknown_error:
        Lease.from_json(unknown)
    assert "extra" in str(unknown_error.value)

    with pytest.raises(ConfigError):
        Lease.from_json(json.dumps(["not", "an", "object"]))
    # 非 Mapping 但「鍵剛好齊全」的輸入（欄位名的 tuple）也必須被明確擋下：
    # 少了型別檢查就會落到 cls(**dict(...)) 的 ValueError，訊息不可讀
    with pytest.raises(ConfigError):
        Lease.from_json(tuple(sorted(payload)))
    with pytest.raises(ConfigError):
        Lease.from_json("{not json")
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, features="start"))
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, features=[1, 2]))
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, key_id=""))
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, machine="not-a-fingerprint"))
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, issued_at=123))
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, expires_at="not-a-time"))
    with pytest.raises(ConfigError):
        Lease.from_json(dict(payload, sig=None))


def test_signing_payload_covers_every_field_except_the_signature():
    lease = build_lease()
    payload = signing_payload(lease)

    assert isinstance(payload, bytes)
    assert payload == signing_payload(build_lease())
    # 逐字釘住正規形式（TASK-029 驗章與 TASK-030 簽發都必須用同一組 bytes）
    assert payload == (
        b'{"catalog_version":"2026-10-01","expires_at":"2026-10-24T12:00:00Z",'
        b'"features":["start","update"],"issued_at":"2026-09-24T12:00:00Z",'
        b'"key_id":"EDIAAD-2026-0001","machine":"0123456789abcdef"}'
    )
    # 簽章本身不在被簽的內容裡（否則無法用同一把公鑰驗章）
    assert signing_payload(build_lease(sig="ff" * 32)) == payload
    # 其他每一個欄位都必須影響被簽內容
    for field, value in (
        ("key_id", "EDIAAD-2026-0002"),
        ("machine", "ffffffffffffffff"),
        ("issued_at", "2026-09-25T12:00:00Z"),
        ("expires_at", "2026-11-24T12:00:00Z"),
        ("features", ["start"]),
        ("catalog_version", "2026-11-01"),
    ):
        assert signing_payload(build_lease(**{field: value})) != payload, field


# ---- AC-055：指紋閘門 -------------------------------------------------------


def test_verify_lease_rejects_a_different_machine():
    calls: list[Lease] = []
    lease = build_lease(machine="0123456789abcdef")

    result = verify_lease(
        lease, fingerprint="ffffffffffffffff", verify_sig=lambda item: calls.append(item) or True
    )

    assert result is False
    assert calls == [], "指紋不符時不該浪費一次驗章"


def test_verify_lease_accepts_a_matching_machine_and_valid_signature():
    lease = build_lease(machine="0123456789abcdef")
    calls: list[Lease] = []

    result = verify_lease(
        lease,
        fingerprint="0123456789abcdef",
        verify_sig=lambda item: calls.append(item) or True,
    )

    assert result is True
    assert calls == [lease]


def test_verify_lease_propagates_a_failed_signature():
    lease = build_lease()

    assert (
        verify_lease(
            lease, fingerprint=lease.machine, verify_sig=lambda item: False
        )
        is False
    )


def test_verify_lease_refuses_to_pass_without_a_signature_checker():
    """沒有驗章器時**不得回 True**：那會讓未簽章的租約看起來有效（TASK-029 才實作驗章）。"""
    lease = build_lease()

    with pytest.raises(ConfigError) as error:
        verify_lease(lease, fingerprint=lease.machine)

    assert "TASK-029" in str(error.value) or "驗章" in str(error.value)


def test_verify_lease_computes_the_fingerprint_when_not_given(monkeypatch):
    from ediaad import license as license_module

    monkeypatch.setattr(
        license_module, "machine_fingerprint", lambda **_kwargs: "0123456789abcdef"
    )
    lease = build_lease(machine="0123456789abcdef")

    assert verify_lease(lease, verify_sig=lambda item: True) is True
    assert (
        verify_lease(
            build_lease(machine="ffffffffffffffff"), verify_sig=lambda item: True
        )
        is False
    )
