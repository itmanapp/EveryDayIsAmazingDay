"""機器指紋與租約模型（TASK-028／AC-055）。

兩個責任：

1. **機器指紋**：`/etc/machine-id`（實測 33 bytes，含結尾換行）去掉前後空白後取 sha256
   十六進位前 16 碼。同一台機器跨程序必須得到相同字串；讀不到或內容無效時丟出
   `ConfigError` 並指出來源——**絕不回傳空字串或固定常數**（那會讓所有機器看起來一樣，
   等於沒有綁定）。
2. **租約模型**：`Lease`（frozen）與 SPEC 第 5 節的租約 JSON 互相轉換，並提供
   `signing_payload()`——簽章涵蓋**除 `sig` 以外**的所有欄位，這是 TASK-029 驗章的
   唯一依據（只定義一次，避免簽章範圍在兩張 Task 之間分岔）。

`verify_lease` 先檢查指紋，再把簽章交給注入的 `verify_sig`；**未注入時丟出
`ConfigError`**，因為「還沒驗章」與「驗章失敗」是兩件不同的事（回 `False` 會被讀成
「簽章無效」）。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import ConfigError, SourceError

__all__ = [
    "CLOCK_TOLERANCE_SECONDS",
    "DEFAULT_MACHINE_ID_PATH",
    "HTTP_CLIENT",
    "HTTP_TIMEOUT_SECONDS",
    "UrllibHttpClient",
    "LEASE_DURATION",
    "PUBLIC_KEY_ENV",
    "public_key_from_env",
    "LICENSE_PUBLIC_KEY",
    "RENEW_TRIGGERS",
    "REVOKED_FILE_NAME",
    "Lease",
    "LeaseStatus",
    "LeaseVerdict",
    "activate",
    "check_lease",
    "ed25519_verify",
    "has_feature",
    "http_post",
    "lease_status",
    "load_high_water",
    "load_lease",
    "machine_fingerprint",
    "renew",
    "save_high_water",
    "save_lease",
    "sig_bytes",
    "signing_payload",
    "verify_lease",
]

#: 指紋來源；只讀這一個檔案（不新增其他識別來源，避免「指紋取決於讀到什麼」）。
DEFAULT_MACHINE_ID_PATH = "/etc/machine-id"

#: 指紋長度（sha256 十六進位前 16 碼＝64 bit）。
FINGERPRINT_LENGTH = 16


def machine_fingerprint(
    machine_id_path: str = DEFAULT_MACHINE_ID_PATH,
    read_text: Callable[[str], str] | None = None,
) -> str:
    """回傳這台機器的指紋：`sha256(<machine-id 去空白>).hexdigest()[:16]`。

    `read_text` 可注入（測試用假檔案）；讀取失敗或內容為空／只有空白時丟出
    `ConfigError`，訊息一定包含來源路徑。
    """
    reader = read_text if read_text is not None else _default_read_text
    try:
        raw = reader(machine_id_path)
    except OSError as error:
        raise ConfigError(
            f"無法讀取機器指紋來源 {machine_id_path}：{error}"
        ) from error

    cleaned = str(raw).strip()
    if not cleaned:
        raise ConfigError(f"機器指紋來源 {machine_id_path} 是空的，無法計算指紋")

    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


def _default_read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} 必須是非空字串，收到 {value!r}")
    return value


def _require_iso_time(name: str, value: object) -> str:
    text = _require_text(name, value)
    try:
        from datetime import datetime

        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigError(f"{name} 必須是 ISO 8601 時間字串，收到 {text!r}") from error
    return text


@dataclass(frozen=True)
class Lease:
    """一份租約（SPEC 第 5 節的租約 JSON 格式）。"""

    key_id: str
    """授權金鑰識別碼（例如 `EDIAAD-2026-0001`）。"""

    machine: str
    """綁定的機器指紋（`machine_fingerprint()` 的輸出）。"""

    issued_at: str
    """簽發時間（ISO 8601，UTC）。"""

    expires_at: str
    """到期時間（ISO 8601，UTC）。"""

    features: tuple[str, ...] | list[str]
    """已授權功能（例如 `["start", "update"]`）。"""

    catalog_version: str
    """catalog 版本（供更新檢查比對）。"""

    sig: str
    """Ed25519 簽章（十六進位或 base64；由 TASK-029 驗證）。"""

    def __post_init__(self) -> None:
        _require_text("key_id", self.key_id)
        machine = _require_text("machine", self.machine)
        if len(machine) != FINGERPRINT_LENGTH or any(
            character not in "0123456789abcdef" for character in machine
        ):
            raise ConfigError(
                f"machine 必須是 {FINGERPRINT_LENGTH} 碼小寫十六進位指紋，收到 {machine!r}"
            )
        _require_iso_time("issued_at", self.issued_at)
        _require_iso_time("expires_at", self.expires_at)
        if isinstance(self.features, str) or not isinstance(self.features, (list, tuple)):
            raise ConfigError(f"features 必須是字串清單，收到 {self.features!r}")
        for index, feature in enumerate(self.features):
            if not isinstance(feature, str) or not feature.strip():
                raise ConfigError(f"features[{index}] 必須是非空字串，收到 {feature!r}")
        # 正規化為 tuple：`to_json` → `from_json` 的往返必須與原物件相等，而 JSON 只有
        # 陣列（讀回來一定是 list），不統一的話 `Lease(features=("start",))` 會 round-trip 失敗。
        object.__setattr__(self, "features", tuple(self.features))
        _require_text("catalog_version", self.catalog_version)
        if not isinstance(self.sig, str):
            raise ConfigError(f"sig 必須是字串，收到 {self.sig!r}")

    def to_json(self) -> str:
        """穩定鍵序的 JSON（`sort_keys=True`），輸出可逐字比較。"""
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str | Mapping[str, Any]) -> "Lease":
        """嚴格還原：缺欄位、多欄位、型別不符都丟出 `ConfigError`。"""
        if isinstance(payload, str):
            try:
                data: Any = json.loads(payload)
            except json.JSONDecodeError as error:
                raise ConfigError(f"無法解析租約 JSON：{error}") from error
        else:
            data = payload

        if not isinstance(data, Mapping):
            raise ConfigError(f"租約必須是 JSON 物件，收到 {type(data).__name__}")

        expected = {field.name for field in fields(cls)}
        provided = set(data)
        missing = sorted(expected - provided)
        if missing:
            raise ConfigError(f"租約缺少欄位：{'、'.join(missing)}")
        unknown = sorted(provided - expected)
        if unknown:
            raise ConfigError(f"租約含未知欄位：{'、'.join(unknown)}")

        return cls(**dict(data))


#: 覆寫內嵌簽章公鑰的環境變數（64 個十六進位字元＝32 位元組）。
#: 自架授權服務（或測試）用它指向自己的簽章公鑰，不必改動程式碼。
PUBLIC_KEY_ENV = "EDIAAD_LICENSE_PUBLIC_KEY"


def public_key_from_env(env: Mapping[str, str] | None = None) -> bytes:
    """解析 `EDIAAD_LICENSE_PUBLIC_KEY`；未設定時回內嵌的 `LICENSE_PUBLIC_KEY`。

    格式錯誤一律 `ConfigError`，**不回退到內嵌值**：設定打錯卻安靜回退，症狀會變成
    「所有租約都驗不過」，比直接說「這個環境變數不是十六進位」難懂得多。
    """
    source = os.environ if env is None else env
    raw = (source.get(PUBLIC_KEY_ENV) or "").strip()
    if not raw:
        return LICENSE_PUBLIC_KEY
    try:
        key = bytes.fromhex(raw)
    except ValueError as error:
        raise ConfigError(f"{PUBLIC_KEY_ENV} 必須是十六進位字串：{error}") from error
    if len(key) != 32:
        raise ConfigError(
            f"{PUBLIC_KEY_ENV} 必須是 32 位元組（64 個十六進位字元），收到 {len(key)} 位元組"
        )
    return key


def signing_payload(lease: Lease) -> bytes:
    """被簽章的內容：除 `sig` 以外的所有欄位，以穩定鍵序序列化為 UTF-8 bytes。

    TASK-029 的驗章與 TASK-030 的簽發都必須用這一個函式，否則簽章範圍會分岔。
    """
    data = asdict(lease)
    data.pop("sig", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def verify_lease(
    lease: Lease,
    fingerprint: str | None = None,
    verify_sig: Callable[[Lease], bool] | None = None,
) -> bool:
    """檢查租約是否屬於這台機器（並在注入驗章器時檢查簽章）。

    - 指紋不符 → `False`（且**不呼叫** `verify_sig`）。
    - 指紋相符且 `verify_sig` 回 `True` → `True`。
    - `verify_sig` 未注入 → 丟出 `ConfigError`：驗章尚未完成，不得被誤判為通過
      （實作在 TASK-029）。
    """
    current = fingerprint if fingerprint is not None else machine_fingerprint()
    if lease.machine != current:
        return False
    if verify_sig is None:
        raise ConfigError(
            "租約簽章驗證尚未注入（Ed25519 驗章屬 TASK-029）；"
            "本函式不得在沒有驗章的情況下回報租約有效"
        )
    return bool(verify_sig(lease))


# ---- Ed25519 驗章（純 Python，RFC 8032 第 5.1 節；AC-054） --------------------
#
# 只做**驗章**：簽章在 Cloudflare Worker 以 WebCrypto 執行（TASK-033），客戶端不持有
# 私鑰。實作依 RFC 8032 的參考流程（`_recover_x` 對應 5.1.3、`_point_add` 對應 5.1.4、
# `_scalar_mult` 對應 5.1.5、`ed25519_verify` 對應 5.1.7），不自行發明曲線運算
# （ADR-002）。只用標準庫的 `hashlib` 與任意精度整數。
#
# **嚴格性**：`S >= L`、非正規的點編碼（`y >= p`、`x = 0` 卻帶 sign bit）、小階點／
# identity 一律拒絕——否則同一份簽章會有多種編碼（可延展），而 identity 公鑰配上零簽章
# 甚至能通過群等式。驗章是安全邊界，任何輸入都只回 True／False，不拋例外。

#: 質數 `p = 2^255 - 19`。
_P = 2**255 - 19
#: 群階 `L = 2^252 + 27742317777372353535851937790883648493`。
_L = 2**252 + 27742317777372353535851937790883648493
#: 曲線常數 `d = -121665 / 121666`。
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
#: `sqrt(-1) mod p`（`2^((p-1)/4)`），用於開平方的第二個候選根。
_I = pow(2, (_P - 1) // 4, _P)
#: 單位元素（extended coordinates：`X=0, Y=1, Z=1, T=0`）。
_IDENTITY = (0, 1, 1, 0)


def _recover_x(y: int, sign: int) -> int | None:
    """由 `y` 與 sign bit 還原 `x`（RFC 8032 §5.1.3）；無解或非正規編碼回 `None`。"""
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        # x = 0 只有一種編碼：sign bit 必須是 0
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _decompress(encoded: bytes) -> tuple[int, int, int, int] | None:
    """32 bytes 的點編碼 → extended coordinates；不是合法編碼時回 `None`。"""
    if len(encoded) != 32:
        return None
    value = int.from_bytes(encoded, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _point_add(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """extended coordinates 的點加法（RFC 8032 §5.1.4；同時用於加倍）。"""
    a = (first[1] - first[0]) * (second[1] - second[0]) % _P
    b = (first[1] + first[0]) * (second[1] + second[0]) % _P
    c = 2 * first[3] * second[3] * _D % _P
    d = 2 * first[2] * second[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalar_mult(scalar: int, point: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """純量乘法（RFC 8032 §5.1.5 的 double-and-add）。"""
    result = _IDENTITY
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _point_equal(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> bool:
    """投影座標的相等（同一個點可能有不同的 `Z`）。"""
    return (first[0] * second[2] - second[0] * first[2]) % _P == 0 and (
        first[1] * second[2] - second[1] * first[2]
    ) % _P == 0


def _is_small_order(point: tuple[int, int, int, int]) -> bool:
    """小階點（含 identity）判定：`[8]P` 等於單位元素。"""
    return _point_equal(_scalar_mult(8, point), _IDENTITY)


#: Ed25519 的基底點：`y = 4/5`、`x` 取 sign bit 為 0 的那個根（RFC 8032 §5.1）。
_BASE_Y = 4 * pow(5, _P - 2, _P) % _P
_BASE_X = _recover_x(_BASE_Y, 0)
assert _BASE_X is not None  # pragma: no cover - 曲線常數，必然成立
_BASE = (_BASE_X, _BASE_Y, 1, _BASE_X * _BASE_Y % _P)

#: 內嵌的授權公鑰（32 bytes），供 TASK-030 驗租約。
#:
#: **目前是尚未設定的佔位值（全零）**：TASK-033 產生 Cloudflare Worker 的金鑰後才會填入
#: 真值。佔位值是「fail closed」——全零編碼解出來是小階點，`ed25519_verify` 一律拒絕，
#: 因此還沒產生金鑰的組建不可能接受任何租約。
LICENSE_PUBLIC_KEY = bytes(32)


def _is_bytes_like(value: object) -> bool:
    return isinstance(value, (bytes, bytearray, memoryview))


def ed25519_verify(public_key: object, message: object, signature: object) -> bool:
    """驗證 Ed25519 簽章（RFC 8032 §5.1.7）；任何不合法輸入都回 `False`。

    - `public_key` 必須是 32 bytes、`signature` 必須是 64 bytes（`R` ＋ `S`）。
    - `S >= L`、非正規點編碼、小階點／identity 一律拒絕（不接受可延展簽章）。
    - **不拋出例外**：驗章在安全邊界上，失敗就是 `False`。
    """
    if not (
        _is_bytes_like(public_key) and _is_bytes_like(message) and _is_bytes_like(signature)
    ):
        return False
    public = bytes(public_key)
    payload = bytes(message)
    encoded = bytes(signature)
    if len(public) != 32 or len(encoded) != 64:
        return False

    point_a = _decompress(public)
    if point_a is None or _is_small_order(point_a):
        return False
    point_r = _decompress(encoded[:32])
    if point_r is None or _is_small_order(point_r):
        return False
    scalar_s = int.from_bytes(encoded[32:], "little")
    if scalar_s >= _L:
        return False

    challenge = int.from_bytes(
        hashlib.sha512(encoded[:32] + public + payload).digest(), "little"
    ) % _L
    # 群等式：[S]B == R + [k]A
    return _point_equal(
        _scalar_mult(scalar_s, _BASE),
        _point_add(point_r, _scalar_mult(challenge, point_a)),
    )


# ---- 啟用、離線啟動驗證與時鐘篡改防護（TASK-030／AC-052、AC-053、AC-058） ----
#
# 三個觸發點（報告第 6.4 節）：**首次啟用**走線上（`activate`）；**每次啟動**完全離線
# （`check_lease`，只驗簽章／指紋／到期／時鐘，不碰網路）；**強制線上**只在時鐘看起來
# 被往回調時發生（`check_lease` 的 `force_online`）。
#
# 時間一律由 `now` 注入（SPEC 第 5 節原則 2），本模組**不使用 `datetime.now()`**，
# 除了 `_default_now` 這個預設值本身。

#: 租約長度（AC-052：伺服器簽發 30 天租約）。
LEASE_DURATION = timedelta(days=30)
#: 時鐘容忍值（秒）：系統時間比簽發時間或本地水位早這麼多以上就視為異常。
CLOCK_TOLERANCE_SECONDS = 900
#: 線上請求的逾時（秒）。
HTTP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class LeaseVerdict:
    """啟動驗證的結果（`reason` 一律可讀，成功時為空字串）。"""

    ok: bool
    reason: str
    force_online: bool
    lease: Lease | None = None


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _clock(now: Callable[[], datetime] | datetime | None) -> datetime:
    """把注入的時間來源正規化為 tz-aware `datetime`（naive 一律視為 UTC）。"""
    if now is None:
        value: Any = _default_now()
    else:
        value = now() if callable(now) else now
    if not isinstance(value, datetime):
        raise ConfigError(f"now 必須是 datetime 或回傳 datetime 的函式，收到 {value!r}")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _epoch(value: Any) -> float:
    """ISO 時間字串／數值 → epoch 秒（比較用；naive 視為 UTC）。"""
    if isinstance(value, bool):
        raise ConfigError(f"時間必須是 ISO 字串或數值，收到 {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigError(f"無法解析時間 {text!r}：{error}") from error
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def sig_bytes(lease: Lease) -> bytes:
    """租約簽章（十六進位字串）→ 64 bytes；格式不對時丟出可讀的 `ConfigError`。"""
    text = lease.sig.strip()
    if len(text) != 128:
        raise ConfigError(
            f"租約簽章必須是 128 個十六進位字元（64 bytes），收到 {len(text)} 個字元"
        )
    try:
        return bytes.fromhex(text)
    except ValueError as error:
        raise ConfigError(f"租約簽章不是合法的十六進位字串：{error}") from error


def _default_path(value: str | Path | None, fallback: Callable[[], Path]) -> Path:
    return Path(value) if value is not None else fallback()


def save_lease(path: str | Path, lease: Lease) -> Path:
    """原子寫入租約（暫存檔 → `os.replace`）並設為 `0600`。

    先寫暫存檔是必要的：中斷時不得留下半寫的租約，也不得損毀既有檔案。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(lease.to_json() + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except OSError as error:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover - 清不掉也不能掩蓋原錯誤
                pass
        raise SourceError(f"無法寫入租約 {target}：{error}") from error
    return target


def load_lease(path: str | Path) -> Lease | None:
    """讀回租約；檔案不存在回 `None`，內容損毀丟出 `ConfigError`。"""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ConfigError(f"無法讀取租約 {target}：{error}") from error
    if not text.strip():
        raise ConfigError(f"租約檔 {target} 是空的")
    try:
        return Lease.from_json(text)
    except ConfigError as error:
        # 指出檔名：呼叫端（`serve`／`license status`）要能直接告訴使用者是哪個檔案壞了。
        raise ConfigError(f"租約檔 {target}：{error}") from error


def load_high_water(path: str | Path) -> float | None:
    """讀時鐘水位（epoch 秒）；不存在或損毀一律回 `None`。

    損毀視為「沒有水位」是刻意的：水位是可被刪檔繞過的**第二層**防護，真正的防線是
    簽章內的 `issued_at`；為了一個可繞過的檔案而讓服務起不來並不合理。
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
        return None
    value = data.get("high_water")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def save_high_water(path: str | Path, value: float) -> Path:
    """原子寫入時鐘水位（`0600`）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"high_water": float(value)}, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except OSError as error:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover
                pass
        raise SourceError(f"無法寫入時鐘水位 {target}：{error}") from error
    return target


def _body_message(body: Any) -> str:
    """從錯誤回應取出可讀訊息（沒有就用型別名稱）。"""
    if isinstance(body, Mapping):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(body, ensure_ascii=False)[:200]
    if isinstance(body, (bytes, bytearray)):
        return bytes(body).decode("utf-8", "replace").strip()[:200]
    if isinstance(body, str):
        return body.strip()[:200]
    return type(body).__name__


def _lease_from_body(body: Any) -> Lease:
    """把授權服務的回應（JSON 字串或映射）轉成 `Lease`；格式不對丟 `ConfigError`。"""
    if isinstance(body, (bytes, bytearray)):
        body = bytes(body).decode("utf-8", "replace")
    if isinstance(body, str):
        try:
            data: Any = json.loads(body)
        except json.JSONDecodeError as error:
            raise ConfigError(f"授權服務回應不是合法 JSON：{error}") from error
    else:
        data = body
    if not isinstance(data, Mapping):
        raise ConfigError(f"授權服務回應必須是租約物件，收到 {type(data).__name__}")
    return Lease.from_json(data)


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} 必須是非空字串，收到 {value!r}")
    return value.strip()


def activate(
    key: str,
    *,
    fingerprint: str,
    http: Any,
    url: str,
    now: Callable[[], datetime] | datetime | None = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    public_key: bytes = LICENSE_PUBLIC_KEY,
    lease_path: str | Path | None = None,
) -> Lease:
    """首次啟用（AC-052）：送出密鑰與機器指紋，取得簽章租約並原子落地。

    - `http` 是可注入的客戶端，介面只有 `post(url, payload, timeout) -> (status, body)`。
    - 4xx → `ConfigError`（輸入錯誤，exit 2 語意）；5xx／連線失敗 → `SourceError`
      （執行期失敗，exit 1 語意）。**任何失敗都不得落地租約。**
    - 收到的租約必須**屬於這台機器**、長度恰為 30 天、且簽章有效（以 `public_key`
      驗章）；預設公鑰是 `LICENSE_PUBLIC_KEY`（目前是 fail-closed 佔位值）。
    """
    secret = _require_text("密鑰", key)
    machine = _require_text("機器指紋", fingerprint)
    base = _require_text("授權服務網址", url).rstrip("/")
    endpoint = f"{base}/v1/activate"

    try:
        status, body = http.post(endpoint, {"key": secret, "machine": machine}, timeout)
    except SourceError:
        raise
    except OSError as error:
        raise SourceError(f"無法連線授權服務 {endpoint}：{error}") from error

    try:
        code = int(status)
    except (TypeError, ValueError) as error:
        raise SourceError(f"授權服務回應的狀態碼無法解讀：{status!r}") from error
    if not 200 <= code < 300:
        message = _body_message(body)
        if 400 <= code < 500:
            raise ConfigError(f"授權服務拒絕啟用（HTTP {code}）：{message}")
        raise SourceError(f"授權服務暫時無法使用（HTTP {code}）：{message}")

    lease = _lease_from_body(body)
    if lease.machine != machine:
        raise ConfigError(
            f"授權服務回傳的租約不屬於這台機器（machine={lease.machine}）"
        )
    duration = _epoch(lease.expires_at) - _epoch(lease.issued_at)
    if duration != LEASE_DURATION.total_seconds():
        raise ConfigError(
            f"租約長度必須是 {LEASE_DURATION.days} 天，"
            f"收到 {duration / 86400:.3f} 天（issued_at={lease.issued_at}、"
            f"expires_at={lease.expires_at}）"
        )
    if not ed25519_verify(public_key, signing_payload(lease), sig_bytes(lease)):
        raise ConfigError("授權服務回傳的租約簽章無效，已拒絕落地")

    save_lease(_default_path(lease_path, _paths_lease_path), lease)
    return lease


class UrllibHttpClient:
    """`http_post` 的物件包裝：核心要的是 `http.post(url, payload, timeout)`。

    `activate`／`renew`／`check_lease` 都接受「有 `post` 方法的物件」，而模組層的
    `http_post` 是**函式**。少了這層包裝，預設路徑會以 `AttributeError` 收場——
    測試因為都注入自己的假物件而看不到，這正是這個類別存在的理由。
    """

    def post(self, url: str, payload: Mapping[str, Any], timeout: float = HTTP_TIMEOUT_SECONDS):
        return http_post(url, payload, timeout)


#: 標準庫 HTTP 客戶端（預設值；測試與服務可注入自己的實作）。
HTTP_CLIENT = UrllibHttpClient()


def http_post(url: str, payload: Mapping[str, Any], timeout: float = HTTP_TIMEOUT_SECONDS):
    """標準庫 HTTP 客戶端（`urllib`）：回 `(狀態碼, 回應內容字串)`。

    這是 `activate`／`renew` 的**預設**客戶端；測試與服務都可注入自己的實作，因此核心
    邏輯不依賴網路，也不引入第三方套件。
    """
    import urllib.request

    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:  # 4xx／5xx 也是「有回應」
        return int(error.code), error.read().decode("utf-8", "replace")


def _paths_lease_path() -> Path:
    from .paths import lease_path as _lease_path

    return _lease_path()


def _paths_high_water_path() -> Path:
    from .paths import high_water_path as _high_water_path

    return _high_water_path()


def _refresh_online(
    lease: Lease,
    *,
    machine: str,
    http: Any,
    url: str | None,
    public_key: bytes,
    now_epoch: float,
) -> Lease | None:
    """強制線上驗證：向授權服務要一張新租約；任何問題都回 `None`（不放行）。"""
    if http is None or not url:
        return None
    endpoint = f"{str(url).rstrip('/')}/v1/verify"
    try:
        status, body = http.post(
            endpoint, {"key": lease.key_id, "machine": machine}, HTTP_TIMEOUT_SECONDS
        )
    except (SourceError, OSError):
        return None
    try:
        code = int(status)
    except (TypeError, ValueError):
        return None
    if not 200 <= code < 300:
        return None
    try:
        refreshed = _lease_from_body(body)
        if refreshed.machine != machine:
            return None
        if _epoch(refreshed.expires_at) <= now_epoch:
            return None
        if not ed25519_verify(public_key, signing_payload(refreshed), sig_bytes(refreshed)):
            return None
    except ConfigError:
        return None
    return refreshed


def _advance_high_water(path: Path, current: float, previous: float | None) -> None:
    """把本地水位推進到現在（只在往前時寫入）。

    寫不進去不阻止啟動：水位是可被刪檔繞過的**第二層**防護，不該讓服務起不來。
    """
    if previous is not None and current <= previous:
        return
    try:
        save_high_water(path, current)
    except SourceError:
        return


def check_lease(
    *,
    fingerprint: str,
    public_key: bytes = LICENSE_PUBLIC_KEY,
    now: Callable[[], datetime] | datetime | None = None,
    lease_path: str | Path | None = None,
    high_water_path: str | Path | None = None,
    http: Any = None,
    url: str | None = None,
    tolerance_seconds: int = CLOCK_TOLERANCE_SECONDS,
    revoked_path: str | Path | None = None,
) -> LeaseVerdict:
    """離線啟動驗證（AC-053）與兩層時鐘防護（AC-058）。

    順序：讀租約 → 指紋 → 簽章（`ed25519_verify`）→ 到期 → 時鐘 → （必要時）強制線上。

    **啟動路徑本身不發出任何網路請求**：只有在時鐘看起來被往回調時，才會用注入的
    `http`／`url` 做一次線上驗證；沒有可用的線上驗證就**不放行**（不得以本地時間延長
    授權）。`high_water` 的比較與更新都以注入的 `now` 為準。
    """
    machine = _require_text("機器指紋", fingerprint)
    clock = _clock(now)
    current = clock.timestamp()
    path = _default_path(lease_path, _paths_lease_path)
    water_path = _default_path(high_water_path, _paths_high_water_path)

    try:
        lease = load_lease(path)
    except ConfigError as error:
        return LeaseVerdict(False, f"租約無法解讀：{error}", False)
    if lease is None:
        return LeaseVerdict(False, f"尚未啟用（找不到租約 {path}）", False)

    revoked_key = _revoked_key(
        _default_revoked_path(revoked_path if revoked_path is not None else path)
    )
    if revoked_key is not None and revoked_key == lease.key_id:
        return LeaseVerdict(
            False, f"密鑰 {lease.key_id} 已被撤銷：請重新申請新密鑰", False
        )

    if lease.machine != machine:
        return LeaseVerdict(
            False, f"租約不屬於這台機器（指紋不符：{lease.machine} ≠ {machine}）", False
        )

    def _verify_signature(candidate: Lease) -> bool:
        return ed25519_verify(public_key, signing_payload(candidate), sig_bytes(candidate))

    try:
        valid_signature = verify_lease(
            lease, fingerprint=machine, verify_sig=_verify_signature
        )
    except ConfigError as error:
        return LeaseVerdict(False, f"租約簽章無法驗證：{error}", False)
    if not valid_signature:
        return LeaseVerdict(False, "租約簽章驗證失敗", False)

    if current > _epoch(lease.expires_at):
        return LeaseVerdict(False, f"租約已過期（{lease.expires_at}）", False)

    force_online = False
    if current < _epoch(lease.issued_at) - tolerance_seconds:
        force_online = True
    high_water = load_high_water(water_path)
    if high_water is not None and current < high_water - tolerance_seconds:
        force_online = True

    if force_online:
        refreshed = _refresh_online(
            lease,
            machine=machine,
            http=http,
            url=url,
            public_key=public_key,
            now_epoch=current,
        )
        if refreshed is None:
            return LeaseVerdict(
                False,
                "系統時間異常（早於簽發時間或本地時鐘水位），且線上驗證不可用；"
                "不以本地時間延長授權",
                True,
            )
        save_lease(path, refreshed)
        _advance_high_water(water_path, current, high_water)
        return LeaseVerdict(True, "", True, refreshed)

    _advance_high_water(water_path, current, high_water)
    return LeaseVerdict(True, "", False, lease)


# ---- 續期、到期停止、撤銷與功能分級（TASK-031／AC-056、AC-057） -------------
#
# 續期**只走線上**（報告第 6.4 節的第三個觸發點：每次開啟、每 24 小時、或使用者手動
# 更換密鑰），失敗不影響有效期內的使用；成功才原子覆寫租約。
#
# **後端對已過期租約的 `renew` 必須回 403**（否則導流被繞過）：客戶端收到 403 時一律
# 不以本地時間或舊租約續用，並在回應指出 `revoked` 時落地撤銷標記——之後同一把密鑰
# 的啟動驗證也會停止。

#: 續期的觸發來源（與 TASK-033 的後端 schema 對齊）。
RENEW_TRIGGERS: tuple[str, ...] = ("start", "timer", "manual")
#: 撤銷標記檔名（放在租約旁邊，讓不同 `$EDIAAD_HOME` 互不影響）。
REVOKED_FILE_NAME = "revoked.json"


@dataclass(frozen=True)
class LeaseStatus:
    """授權狀態（供授權頁與 CLI 轉譯；本模組不印訊息、不寫網頁）。"""

    state: str
    """`unactivated`／`active`／`expired`／`revoked` 之一。"""

    message: str
    """給人看的說明（`active` 時為空字串）。"""

    expires_at: str | None = None
    """到期時間（沒有租約時為 `None`）。"""

    days_remaining: float | None = None
    """剩餘天數（只有 `active` 時有值）。"""

    reapply: bool = False
    """是否需要重新申請新密鑰（`expired`／`revoked` 為真）。"""


def has_feature(lease: Lease, name: str) -> bool:
    """租約是否含某項功能（`features` 分級；名稱比對精確）。"""
    return name in tuple(lease.features)


def _default_revoked_path(lease_path: str | Path | None) -> Path:
    """撤銷標記的位置：預設與租約同目錄（測試因此天然隔離）。"""
    if lease_path is not None:
        return Path(lease_path).parent / REVOKED_FILE_NAME
    from .paths import revoked_path as _revoked_path

    return _revoked_path()


def _revoked_key(path: str | Path) -> str | None:
    """讀撤銷標記的 `key_id`；不存在或損毀一律回 `None`（不因標記檔壞掉而擋住服務）。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
        return None
    key_id = data.get("key_id")
    if isinstance(key_id, str) and key_id.strip():
        return key_id.strip()
    return None


def _mark_revoked(path: str | Path, key_id: str, epoch: float) -> None:
    """落地撤銷標記（原子、`0600`）；寫不進去不影響「本次拒絕」。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"key_id": key_id, "revoked_at": float(epoch)}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except OSError:
        return


def _indicates_revoked(body: Any) -> bool:
    """後端的拒絕是否明確指出「已撤銷」。"""
    if isinstance(body, (bytes, bytearray)):
        body = bytes(body).decode("utf-8", "replace")
    if isinstance(body, Mapping):
        if str(body.get("status", "")).strip().lower() == "revoked":
            return True
        return body.get("revoked") is True
    if isinstance(body, str):
        return "revoked" in body.lower()
    return False


def lease_status(
    lease: Lease | None,
    *,
    now: Callable[[], datetime] | datetime | None = None,
    revoked_path: str | Path | None = None,
) -> LeaseStatus:
    """目前授權狀態（未啟用／有效／已過期／已撤銷）。

    到期判定為 `now > expires_at`（等於到期時刻仍算有效）；撤銷只認**同一把**
    `key_id` 的標記——換了密鑰就不該被舊標記擋住（AC-057 的更換密鑰）。
    """
    current = _clock(now).timestamp()
    if lease is None:
        return LeaseStatus(
            "unactivated", "尚未啟用：請輸入密鑰完成啟用", None, None, True
        )

    marker = _revoked_key(_default_revoked_path(revoked_path))
    if marker is not None and marker == lease.key_id:
        return LeaseStatus(
            "revoked",
            f"密鑰 {lease.key_id} 已被撤銷：請重新申請新密鑰",
            lease.expires_at,
            None,
            True,
        )

    expires = _epoch(lease.expires_at)
    if current > expires:
        return LeaseStatus(
            "expired",
            f"租約已過期（{lease.expires_at}）：請重新申請新密鑰（不會自動續期）",
            lease.expires_at,
            None,
            True,
        )
    return LeaseStatus("active", "", lease.expires_at, (expires - current) / 86400.0, False)


def renew(
    lease: Lease,
    *,
    http: Any,
    url: str,
    now: Callable[[], datetime] | datetime | None = None,
    trigger: str = "manual",
    timeout: float = HTTP_TIMEOUT_SECONDS,
    public_key: bytes = LICENSE_PUBLIC_KEY,
    lease_path: str | Path | None = None,
    revoked_path: str | Path | None = None,
) -> Lease:
    """線上續期（AC-056）：成功後原子覆寫租約；失敗一律不動本地租約。

    - `trigger` 只接受 `RENEW_TRIGGERS`（`start`／`timer`／`manual`），並隨請求送出。
    - **403**：後端拒絕（過期或撤銷）。不以本地時間或舊租約續用；回應指出 `revoked`
      時落地撤銷標記，之後同一把密鑰的啟動驗證也會停止。
    - 429／5xx／連線失敗 → `SourceError`（可重試，不影響有效期內使用）。
    - 成功的回應必須是**同一把密鑰、同一台機器、30 天、簽章有效、且到期時間有延長**
      的租約；任何一項不符都不落地。
    """
    if trigger not in RENEW_TRIGGERS:
        raise ConfigError(
            f"trigger 必須是 {list(RENEW_TRIGGERS)} 之一，收到 {trigger!r}"
        )
    base = _require_text("授權服務網址", url).rstrip("/")
    endpoint = f"{base}/v1/renew"
    current = _clock(now).timestamp()

    try:
        status, body = http.post(
            endpoint,
            {"key": lease.key_id, "machine": lease.machine, "trigger": trigger},
            timeout,
        )
    except SourceError:
        raise
    except OSError as error:
        raise SourceError(f"無法連線授權服務 {endpoint}：{error}") from error

    try:
        code = int(status)
    except (TypeError, ValueError) as error:
        raise SourceError(f"授權服務回應的狀態碼無法解讀：{status!r}") from error

    if not 200 <= code < 300:
        message = _body_message(body)
        if code == 403:
            if _indicates_revoked(body):
                _mark_revoked(
                    _default_revoked_path(
                        revoked_path if revoked_path is not None else lease_path
                    ),
                    lease.key_id,
                    current,
                )
                raise ConfigError(
                    f"密鑰 {lease.key_id} 已被撤銷：請重新申請新密鑰（HTTP 403）"
                )
            raise ConfigError(
                f"授權服務拒絕續期（HTTP 403）：{message}；"
                "若租約已過期請重新申請新密鑰，本機不會以舊租約續用"
            )
        if code == 429:
            # 429 是**暫時**狀態（客戶端沒有錯），可重試 → 執行期失敗（exit 1）
            raise SourceError(f"授權服務請求過於頻繁（HTTP 429）：{message}")
        if 400 <= code < 500:
            raise ConfigError(f"授權服務拒絕續期（HTTP {code}）：{message}")
        raise SourceError(f"授權服務暫時無法使用（HTTP {code}）：{message}")

    refreshed = _lease_from_body(body)
    if refreshed.key_id != lease.key_id:
        raise ConfigError(
            f"續期回應的密鑰不同（{refreshed.key_id} ≠ {lease.key_id}），已拒絕"
        )
    if refreshed.machine != lease.machine:
        raise ConfigError("續期回應的租約不屬於這台機器，已拒絕")
    duration = _epoch(refreshed.expires_at) - _epoch(refreshed.issued_at)
    if duration != LEASE_DURATION.total_seconds():
        raise ConfigError(
            f"續期後的租約長度必須是 {LEASE_DURATION.days} 天，"
            f"收到 {duration / 86400:.3f} 天"
        )
    if not ed25519_verify(public_key, signing_payload(refreshed), sig_bytes(refreshed)):
        raise ConfigError("續期回應的租約簽章無效，已拒絕")
    if _epoch(refreshed.expires_at) <= _epoch(lease.expires_at):
        raise ConfigError(
            f"續期後的到期時間（{refreshed.expires_at}）沒有比原本"
            f"（{lease.expires_at}）更晚，已拒絕"
        )

    save_lease(_default_path(lease_path, _paths_lease_path), refreshed)
    return refreshed
