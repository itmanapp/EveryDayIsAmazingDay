"""設定解析、驗證與原子寫入（AC-040）。

`$EDIAAD_HOME/settings.json` 是**應用層設定**（與 `monitor.load_config` 讀的
`watchlist.json`、TASK-016 的 `keys.json` 各自獨立）：

| 鍵 | 型別 | 對應需求 |
| --- | --- | --- |
| `market` | `"crypto"`／`"stock"` | AC-035 的市場別規律預設（TASK-015 的 `default_spec_for`） |
| `pattern_id` | 非空字串 | 規律識別名（TASK-007） |
| `pattern_spec` | 物件或 `null` | G4 規律參數面板的覆寫值（`null` 表示用市場別預設） |
| `poll_interval_seconds` | ≥ 1 的整數 | G3 調整輪詢間隔 |
| `horizon` | ≥ 1 的整數 | 後續走勢統計的視窗（TASK-006） |
| `cache_max_age_seconds` | ≥ 0 的整數 | 報告第 4.6 節的快取有效期（TASK-013 的 `max_age`） |
| `update_enabled` | 布林 | 報告第 6.5 節第 6 條「可完全關閉」 |

**原子寫入**：先寫同目錄的**唯一**暫存檔（`tempfile.mkstemp`，因此並發寫入不會互相踩到），
`fsync` 後以 `os.replace` 取代——任何時刻讀到的都是完整的舊內容或完整的新內容。
驗證一律**在碰觸檔案之前**完成：不合法的設定不會覆蓋既有檔案。

公開介面：`DEFAULT_SETTINGS`、`load_settings(path)`、`save_settings_atomic(path, settings)`、
`validate_settings(settings)`（只驗證不寫入，供 TASK-020 的端點在存檔前檢查請求內容）。

只使用標準庫（`json`／`os`／`tempfile`）；路徑由呼叫端提供，本模組不決定 `$EDIAAD_HOME`。
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .markets.calendar import MARKET_PATTERN_DEFAULTS
from .patterns import from_json

__all__ = ["DEFAULT_SETTINGS", "load_settings", "save_settings_atomic", "validate_settings"]

#: 預設設定（`load_settings` 對缺值的補齊來源，與 `DEFAULT_SETTINGS` 本身一致）。
DEFAULT_SETTINGS: dict[str, Any] = {
    "market": "crypto",
    "pattern_id": "range_fakeout_reversion",
    "pattern_spec": None,
    "poll_interval_seconds": 60,
    "horizon": 5,
    "cache_max_age_seconds": 900,
    "update_enabled": True,
}

_KEYS: tuple[str, ...] = tuple(DEFAULT_SETTINGS)


def _require_int(settings: Mapping[str, Any], name: str, minimum: int) -> None:
    value = settings[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{name} 必須是 >= {minimum} 的整數，收到 {value!r}")


def _require_bool(settings: Mapping[str, Any], name: str) -> None:
    if not isinstance(settings[name], bool):
        raise ConfigError(f"{name} 必須是布林值，收到 {settings[name]!r}")


def _require_text(settings: Mapping[str, Any], name: str) -> str:
    value = settings[name]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} 必須是非空字串，收到 {value!r}")
    return value.strip()


def validate_settings(settings: Any) -> dict[str, Any]:
    """驗證並正規化一份設定；任何問題都是指出鍵名的 `ConfigError`。

    回傳值的鍵序固定為 `DEFAULT_SETTINGS` 的宣告順序（未知鍵已在前面擋下），因此輸出
    位元可重現——不需要 `sort_keys`（那反而會把鍵排成字母序、失去邏輯分組）。
    """
    if not isinstance(settings, Mapping):
        raise ConfigError(f"設定必須是 JSON 物件，收到 {type(settings).__name__}")

    unknown = sorted(set(settings) - set(_KEYS))
    if unknown:
        raise ConfigError(f"設定含未知鍵：{'、'.join(unknown)}")

    merged = {**DEFAULT_SETTINGS, **dict(settings)}
    _require_int(merged, "poll_interval_seconds", 1)
    _require_int(merged, "horizon", 1)
    _require_int(merged, "cache_max_age_seconds", 0)
    _require_bool(merged, "update_enabled")

    market = _require_text(merged, "market")
    if market not in MARKET_PATTERN_DEFAULTS:
        raise ConfigError(
            f"market 不支援 {market!r}；可用市場別：{sorted(MARKET_PATTERN_DEFAULTS)}"
        )

    pattern_id = _require_text(merged, "pattern_id")
    spec_value = merged["pattern_spec"]
    if spec_value is not None:
        try:
            spec = from_json(spec_value)
        except ConfigError as error:
            raise ConfigError(f"pattern_spec 不合法：{error}") from error
        if spec.pattern_id != pattern_id:
            raise ConfigError(
                f"pattern_spec.pattern_id（{spec.pattern_id!r}）必須與 pattern_id"
                f"（{pattern_id!r}）一致"
            )
    return merged


def load_settings(path: str | Path) -> dict[str, Any]:
    """讀入設定；**檔案不存在時回傳預設值**（首次啟動的正常狀態）。

    損毀的檔案丟出 `ConfigError`（訊息指出檔名與問題）而**不改動原檔**——不以預設值
    靜默蓋掉，否則使用者下一次儲存就會永久失去原本的內容。
    """
    settings_path = Path(path)
    if not settings_path.is_file():
        return dict(DEFAULT_SETTINGS)

    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"設定檔 {settings_path}：讀不到檔案（{error}）") from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"設定檔 {settings_path}：不是合法 JSON（{error}）") from error

    try:
        return validate_settings(payload)
    except ConfigError as error:
        raise ConfigError(f"設定檔 {settings_path}：{error}") from error


def save_settings_atomic(path: str | Path, settings: Mapping[str, Any]) -> Path:
    """以「唯一暫存檔 ＋ `os.replace`」原子寫入設定。

    驗證在寫入之前完成；暫存檔寫入或取代失敗時清除暫存檔並保留原檔。
    """
    settings_path = Path(path)
    validated = validate_settings(settings)

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ConfigError(f"無法建立設定檔目錄 {settings_path.parent}：{error}") from error

    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=str(settings_path.parent), prefix=f".{settings_path.name}.", suffix=".tmp"
        )
    except OSError as error:
        raise ConfigError(f"無法在 {settings_path.parent} 建立暫存檔：{error}") from error

    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(validated, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, settings_path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"無法寫入設定檔 {settings_path}：{error}") from error

    return settings_path
