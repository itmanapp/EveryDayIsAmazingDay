"""純 Python Ed25519 驗章（TASK-029／AC-054）。

觀察邊界：
1. **正確性 oracle（自動）**：RFC 8032 第 7.1 節「Test Vectors for Ed25519」的五組向量
   （TEST 1、TEST 2、TEST 3、TEST 1024、TEST SHA(abc)）以常數內嵌，全程離線。
   **這些常數在寫測試之前先以系統的獨立實作交叉核對過**（見 TDD 紀錄）：由 secret key
   推導出的 public key 必須相符、簽章必須在該訊息上通過；Ed25519 簽章是決定性的，
   因此 `SHA(abc)` 的簽章可由同一把 secret key 重算確認。
2. **嚴格性（自動）**：篡改（訊息／簽章／公鑰任一位元）、非正規編碼（`S >= L`、
   `y >= p`、`x = 0` 卻帶 sign bit）、小階點／identity、長度與型別錯誤，一律回 `False`
   且**不拋出例外**——驗章是安全邊界，不接受可延展（malleable）簽章。
3. **純標準庫（自動）**：`.venv` 不含 `cryptography`、requirements 不含它、模組 import
   不引入 `socket`／`urllib`／`ssl` 等 I/O 模組（SPEC 第 5 節原則 1：計算不碰 I/O）。
"""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ediaad.license import LICENSE_PUBLIC_KEY, ed25519_verify

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"

#: RFC 8032 第 7.1 節的官方測試向量：名稱 → (secret, public, message, signature)。
#: `secret` 只用來說明來源（本模組**不簽章**），測試只使用 public／message／signature。
RFC8032_VECTORS: dict[str, tuple[str, str, str, str]] = {
    "TEST1": (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    "TEST2": (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    "TEST3": (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
    "TEST1024": (
        "f5e5767cf153319517630f226876b86c8160cc583bc013744c6bf255f5cc0ee5",
        "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
        "08b8b2b733424243760fe426a4b54908632110a66c2f6591eabd3345e3e4eb98"
        "fa6e264bf09efe12ee50f8f54e9f77b1e355f6c50544e23fb1433ddf73be84d8"
        "79de7c0046dc4996d9e773f4bc9efe5738829adb26c81b37c93a1b270b20329d"
        "658675fc6ea534e0810a4432826bf58c941efb65d57a338bbd2e26640f89ffbc"
        "1a858efcb8550ee3a5e1998bd177e93a7363c344fe6b199ee5d02e82d522c4fe"
        "ba15452f80288a821a579116ec6dad2b3b310da903401aa62100ab5d1a36553e"
        "06203b33890cc9b832f79ef80560ccb9a39ce767967ed628c6ad573cb116dbef"
        "efd75499da96bd68a8a97b928a8bbc103b6621fcde2beca1231d206be6cd9ec7"
        "aff6f6c94fcd7204ed3455c68c83f4a41da4af2b74ef5c53f1d8ac70bdcb7ed1"
        "85ce81bd84359d44254d95629e9855a94a7c1958d1f8ada5d0532ed8a5aa3fb2"
        "d17ba70eb6248e594e1a2297acbbb39d502f1a8c6eb6f1ce22b3de1a1f40cc24"
        "554119a831a9aad6079cad88425de6bde1a9187ebb6092cf67bf2b13fd65f270"
        "88d78b7e883c8759d2c4f5c65adb7553878ad575f9fad878e80a0c9ba63bcbcc"
        "2732e69485bbc9c90bfbd62481d9089beccf80cfe2df16a2cf65bd92dd597b07"
        "07e0917af48bbb75fed413d238f5555a7a569d80c3414a8d0859dc65a46128ba"
        "b27af87a71314f318c782b23ebfe808b82b0ce26401d2e22f04d83d1255dc51a"
        "ddd3b75a2b1ae0784504df543af8969be3ea7082ff7fc9888c144da2af58429e"
        "c96031dbcad3dad9af0dcbaaaf268cb8fcffead94f3c7ca495e056a9b47acdb7"
        "51fb73e666c6c655ade8297297d07ad1ba5e43f1bca32301651339e22904cc8c"
        "42f58c30c04aafdb038dda0847dd988dcda6f3bfd15c4b4c4525004aa06eeff8"
        "ca61783aacec57fb3d1f92b0fe2fd1a85f6724517b65e614ad6808d6f6ee34df"
        "f7310fdc82aebfd904b01e1dc54b2927094b2db68d6f903b68401adebf5a7e08"
        "d78ff4ef5d63653a65040cf9bfd4aca7984a74d37145986780fc0b16ac451649"
        "de6188a7dbdf191f64b5fc5e2ab47b57f7f7276cd419c17a3ca8e1b939ae49e4"
        "88acba6b965610b5480109c8b17b80e1b7b750dfc7598d5d5011fd2dcc5600a3"
        "2ef5b52a1ecc820e308aa342721aac0943bf6686b64b2579376504ccc493d97e"
        "6aed3fb0f9cd71a43dd497f01f17c0e2cb3797aa2a2f256656168e6c496afc5f"
        "b93246f6b1116398a346f1a641f3b041e989f7914f90cc2c7fff357876e506b5"
        "0d334ba77c225bc307ba537152f3f1610e4eafe595f6d9d90d11faa933a15ef1"
        "369546868a7f3a45a96768d40fd9d03412c091c6315cf4fde7cb68606937380d"
        "b2eaaa707b4c4185c32eddcdd306705e4dc1ffc872eeee475a64dfac86aba41c"
        "0618983f8741c5ef68d3a101e8a3b8cac60c905c15fc910840b94c00a0b9d0",
        "0aab4c900501b3e24d7cdf4663326a3a87df5e4843b2cbdb67cbf6e460fec350"
        "aa5371b1508f9f4528ecea23c436d94b5e8fcd4f681e30a6ac00a9704a188a03",
    ),
    "TEST_SHA_ABC": (
        "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
        "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
        "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
        "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
        "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
        "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704",
    ),
}

#: Ed25519 的群階（`L = 2^252 + 27742317777372353535851937790883648493`）。
L = 2**252 + 27742317777372353535851937790883648493
#: 質數 `p = 2^255 - 19`。
P = 2**255 - 19


def vector(name: str) -> tuple[bytes, bytes, bytes]:
    secret, public, message, signature = RFC8032_VECTORS[name]
    return bytes.fromhex(public), bytes.fromhex(message), bytes.fromhex(signature)


# ---- AC-054：RFC 8032 官方向量 -------------------------------------------------


def test_rfc8032_test1_empty_message():
    """第一個失敗行為：`ed25519_verify` 不存在（collection error）；實作後必須回 True。"""
    public, message, signature = vector("TEST1")

    assert message == b""
    assert ed25519_verify(public, message, signature) is True


@pytest.mark.parametrize("name", sorted(RFC8032_VECTORS))
def test_rfc8032_vectors_verify(name):
    public, message, signature = vector(name)

    assert len(public) == 32 and len(signature) == 64
    assert ed25519_verify(public, message, signature) is True


def test_cross_vector_negatives_are_rejected():
    """同一公鑰配上另一組向量的訊息與簽章必須失敗（避免「什麼都回 True」）。"""
    for name in sorted(RFC8032_VECTORS):
        public, _message, _signature = vector(name)
        for other in sorted(RFC8032_VECTORS):
            if other == name:
                continue
            _public, message, signature = vector(other)
            assert ed25519_verify(public, message, signature) is False, (name, other)


def test_tampered_message_signature_or_public_key_is_rejected():
    public, message, signature = vector("TEST3")

    flipped_message = bytearray(message)
    flipped_message[0] ^= 0x01
    assert ed25519_verify(public, bytes(flipped_message), signature) is False

    flipped_signature = bytearray(signature)
    flipped_signature[63] ^= 0x01
    assert ed25519_verify(public, message, bytes(flipped_signature)) is False

    flipped_public = bytearray(public)
    flipped_public[0] ^= 0x01
    assert ed25519_verify(bytes(flipped_public), message, signature) is False

    # 額外訊息（尾端多一個 byte）也不得通過
    assert ed25519_verify(public, message + b"\x00", signature) is False


def test_non_canonical_scalar_s_is_rejected():
    """`S >= L` 是可延展簽章：同一份 (R, S) 有多種編碼，必須只接受正規的那一個。"""
    public, message, signature = vector("TEST2")
    s = int.from_bytes(signature[32:], "little")

    for extra in (L, L + 1, 2 * L):
        malleable = signature[:32] + (s + extra).to_bytes(32, "little")
        assert int.from_bytes(malleable[32:], "little") < 2**256
        assert ed25519_verify(public, message, malleable) is False, extra


def test_non_canonical_point_encodings_are_rejected():
    public, message, signature = vector("TEST2")

    # y >= p 不是正規編碼（即使同餘到同一個點）
    non_canonical_a = (P + 1).to_bytes(32, "little")
    assert ed25519_verify(non_canonical_a, message, signature) is False
    non_canonical_r = (P + 2).to_bytes(32, "little") + signature[32:]
    assert ed25519_verify(public, message, non_canonical_r) is False

    # x = 0 的點（identity，y = 1）不得帶 sign bit：否則同一點有兩種編碼
    signed_identity = bytearray((1).to_bytes(32, "little"))
    signed_identity[31] |= 0x80
    assert ed25519_verify(bytes(signed_identity), message, signature) is False


def test_small_order_points_and_identity_are_rejected():
    """小階點／identity 會讓「零簽章」通過等式檢查，必須明確擋下。"""
    _public, message, signature = vector("TEST1")

    # 8 個小階點的編碼（RFC 8032 §6 的 small-order points，含 identity）
    small_order = [
        "0100000000000000000000000000000000000000000000000000000000000000",
        "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "0000000000000000000000000000000000000000000000000000000000000080",
        "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
        "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
        "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85",
        "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
    ]
    for encoded in small_order:
        assert ed25519_verify(bytes.fromhex(encoded), message, signature) is False, encoded

    # R 全零（小階點）＋ S 全零：經典的偽造嘗試
    assert ed25519_verify(_public, message, bytes(64)) is False
    assert ed25519_verify(bytes(32), message, bytes(64)) is False
    assert ed25519_verify(bytes(32), b"anything", bytes(64)) is False


def test_internal_decoding_rejects_non_canonical_encodings():
    """解碼層的正規性規則（RFC 8032 §5.1.3）。

    公開 API 無法構造「`y >= p` 且不是小階點」的輸入（那需要一個 `y < 19` 的真實金鑰），
    因此這條規則只能在解碼層固定——它是安全邊界的一部分（可延展編碼）。
    """
    from ediaad import license as module

    assert module._recover_x(module._P, 0) is None, "y == p 不是正規編碼"
    assert module._recover_x(module._P + 1, 0) is None, "y > p 不是正規編碼"
    assert module._recover_x(1, 1) is None, "x = 0 的點不得帶 sign bit"
    assert module._recover_x(1, 0) == 0
    assert module._decompress((module._P + 1).to_bytes(32, "little")) is None
    # 31 bytes 的 identity（`01` ＋ 30 個 0）本身是合法點，長度檢查必須先擋下
    assert module._decompress(b"\x01" + b"\x00" * 30) is None, "長度不是 32 不得解碼"
    assert module._decompress(bytes(33)) is None


def test_internal_point_equality_compares_both_coordinates():
    """只比 X 會把 P 與「同 X、Y 相反」的點視為相等——那是驗章等式上的錯誤。"""
    from ediaad import license as module

    order_two = (0, module._P - 1, 1, 0)  # (0, -1)：與 identity 同 X、不同 Y
    assert module._point_equal(module._IDENTITY, module._IDENTITY) is True
    assert module._point_equal(module._IDENTITY, order_two) is False
    assert module._point_equal(order_two, module._IDENTITY) is False


def test_internal_small_order_detection():
    from ediaad import license as module

    identity = module._decompress(bytes.fromhex("01" + "00" * 31))
    assert module._is_small_order(identity) is True
    assert module._is_small_order(module._decompress(bytes(32))) is True
    base = module._decompress(bytes.fromhex("58" + "66" * 31))
    assert module._is_small_order(base) is False


def test_identity_key_with_identity_r_and_zero_s_is_rejected():
    """經典偽造：`A = identity`、`R = identity`、`S = 0` 會**滿足**群等式，
    只有小階點檢查能擋下（少了它，任何人都能對任意訊息偽造簽章）。"""
    identity = bytes.fromhex("01" + "00" * 31)
    forged = identity + bytes(32)

    assert ed25519_verify(identity, b"any message", forged) is False
    assert ed25519_verify(identity, b"", forged) is False
    assert ed25519_verify(identity, b"any message", identity + (1).to_bytes(32, "little")) is False

    # 更強的偽造：A = identity 時 `[k]A` 恆為 identity，於是攻擊者只要取 R = [S]B
    # （例如 S = 1、R = 基底點）就**對任意訊息**滿足群等式——只有 A 的小階點檢查能擋。
    base_encoding = bytes.fromhex("58" + "66" * 31)
    universal_forgery = base_encoding + (1).to_bytes(32, "little")
    assert ed25519_verify(identity, b"any message", universal_forgery) is False
    assert ed25519_verify(identity, b"", universal_forgery) is False


def test_bad_lengths_and_types_return_false():
    public, message, signature = vector("TEST1")

    for bad_public in (b"", public[:31], public + b"\x00"):
        assert ed25519_verify(bad_public, message, signature) is False
    for bad_signature in (b"", signature[:63], signature + b"\x00"):
        assert ed25519_verify(public, message, bad_signature) is False

    # bytes-like（bytearray／memoryview）視為同一種輸入
    assert ed25519_verify(bytearray(public), bytearray(message), bytearray(signature)) is True
    assert ed25519_verify(memoryview(public), memoryview(message), memoryview(signature)) is True

    for bad in ("string", None, 123, ["x"], object()):
        assert ed25519_verify(bad, message, signature) is False
        assert ed25519_verify(public, bad, signature) is False
        assert ed25519_verify(public, message, bad) is False


def test_hostile_input_never_raises():
    """驗章是安全邊界：任何輸入都只回 True／False，不得讓例外往上跑。"""
    public, message, signature = vector("TEST2")
    rng = random.Random(20260924)
    for _ in range(40):
        candidate_public = bytes(rng.randrange(256) for _ in range(32))
        candidate_signature = bytes(rng.randrange(256) for _ in range(64))
        candidate_message = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 40)))
        assert ed25519_verify(candidate_public, candidate_message, candidate_signature) in (
            True,
            False,
        )
    # 真實向量配上大量隨機雜訊也不得拋出例外
    for _ in range(20):
        noisy = bytearray(signature)
        for index in rng.sample(range(64), 3):
            noisy[index] ^= 0xFF
        assert ed25519_verify(public, message, bytes(noisy)) in (True, False)


def test_verification_is_fast_enough():
    """報告第 6.4 節的效能註記：一次驗章必須遠低於 1 秒（純 Python 也夠快）。"""
    public, message, signature = vector("TEST1024")

    started = time.perf_counter()
    assert ed25519_verify(public, message, signature) is True
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"一次驗章耗時 {elapsed:.3f} 秒"


# ---- AC-054：純標準庫、模組邊界 -----------------------------------------------


def test_cryptography_is_not_installed_in_the_venv():
    """AC-054 的直接證據：`.venv` 內不得有 `cryptography`。"""
    assert importlib.util.find_spec("cryptography") is None


def test_requirements_do_not_mention_cryptography():
    for name in ("requirements.txt", "requirements-dev.txt"):
        text = (PROJECT_DIR / name).read_text(encoding="utf-8")
        assert "cryptography" not in text.lower(), name


def test_module_import_does_not_pull_in_io_modules():
    """SPEC 第 5 節原則 1（計算不碰 I/O）：import 不得拉進 socket／urllib／ssl 等。"""
    # 注意：`pathlib` 在 CPython 3.12 會拉進 `urllib.parse`（純字串解析、沒有 I/O），
    # 因此這裡檢查的是**網路與第三方密碼學**的模組，而不是所有含 "urllib" 的名字。
    script = (
        "import json, sys, ediaad.license as module;"
        "print(json.dumps(sorted(name for name in sys.modules "
        "if name.split('.')[0] in {'socket', 'ssl', 'http', 'cryptography', 'requests'})));"
        "print(hasattr(module, 'ed25519_verify'))"
    )
    completed = subprocess.run(
        [str(PYTHON), "-c", script],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.strip().splitlines()
    assert json.loads(lines[0]) == []
    assert lines[1] == "True"


def test_license_public_key_is_a_fail_closed_placeholder():
    """內嵌公鑰（供 TASK-030 驗租約）目前是**未設定**的佔位值。

    佔位值必須「fail closed」：用它在任何輸入上都驗不過，因此未產生金鑰的組建
    （TASK-033 才產生 Worker 金鑰）不可能接受任何租約。
    """
    assert isinstance(LICENSE_PUBLIC_KEY, bytes)
    assert len(LICENSE_PUBLIC_KEY) == 32
    assert LICENSE_PUBLIC_KEY == bytes(32), "TASK-033 產生 Worker 金鑰後才會填入真值"

    _public, message, signature = vector("TEST1")
    assert ed25519_verify(LICENSE_PUBLIC_KEY, message, signature) is False
    assert ed25519_verify(LICENSE_PUBLIC_KEY, b"", bytes(64)) is False
