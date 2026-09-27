"""測試專用的純 Python Ed25519 **簽章**夾具（TASK-030）。

驗章（`ediaad.license.ed25519_verify`）是產品程式碼；**簽章只存在於測試**——正式環境的
簽章在 Cloudflare Worker 以 WebCrypto 執行（TASK-033），客戶端不持有私鑰。

這個夾具使用 RFC 8032 第 7.1 節的**公開** secret key（它們是官方測試向量的一部分，
任何人都知道，因此不可能被誤用為正式金鑰），以產生合成租約的簽章。它重用
`ediaad.license` 的私有群運算（`_BASE`／`_scalar_mult`／`_compress`）——夾具不是公開
契約的一部分，重用內部函式可避免「測試自己實作一套曲線運算而與產品分岔」。

**不引入 `cryptography`**：本檔只用標準庫。
"""

from __future__ import annotations

import hashlib

from ediaad.license import _BASE, _L, _P, _scalar_mult

__all__ = ["FIXTURE_PUBLIC_KEY", "sign"]

#: RFC 8032 第 7.1 節 TEST 1 的 secret key（公開的測試向量，不可用於正式環境）。
_FIXTURE_SECRET = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)
#: 對應的 public key（32 bytes），測試會把它當成「伺服器的簽章公鑰」。
FIXTURE_PUBLIC_KEY = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)


def _clamp(value: bytes) -> int:
    """RFC 8032 §5.1.5 的私鑰整數化（清位、設位、加 2^254）。"""
    scalar = int.from_bytes(value, "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar


def _compress(point: tuple[int, int, int, int]) -> bytes:
    """extended coordinates → 32 bytes 的點編碼（y 加上 x 的 sign bit）。"""
    x, y, z, _t = point
    inverse = pow(z, _P - 2, _P)
    x = x * inverse % _P
    y = y * inverse % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _public_key(secret: bytes) -> bytes:
    digest = hashlib.sha512(secret).digest()
    return _compress(_scalar_mult(_clamp(digest[:32]), _BASE))


def sign(message: bytes, secret: bytes = _FIXTURE_SECRET) -> str:
    """以 RFC 8032 §5.1.6 的流程簽章；回傳 128 個十六進位字元（64 bytes）。"""
    digest = hashlib.sha512(secret).digest()
    scalar = _clamp(digest[:32])
    prefix = digest[32:]
    public = _public_key(secret)

    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    encoded_r = _compress(_scalar_mult(nonce, _BASE))
    challenge = int.from_bytes(
        hashlib.sha512(encoded_r + public + message).digest(), "little"
    ) % _L
    scalar_s = (nonce + challenge * scalar) % _L
    return (encoded_r + scalar_s.to_bytes(32, "little")).hex()


# 自我檢查：夾具產生的公鑰必須與 RFC 8032 的 TEST 1 向量一致（錯了就整個夾具都不可信）。
assert _public_key(_FIXTURE_SECRET) == FIXTURE_PUBLIC_KEY, "簽章夾具的公鑰與 RFC 向量不符"
