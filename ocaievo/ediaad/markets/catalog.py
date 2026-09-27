"""版本化來源與商品清單（catalog）與更新攜帶（AC-038）。

`Catalog` 是本機的商品目錄：`catalog_version`（`YYYY-MM-DD`）、`sources`（各來源的
中介資料）與 `instruments`（可搜尋的商品，重用 `markets.base.Instrument`，因此
**商品的 `source_id` 就在 catalog 裡**——這是「哪個商品該問哪個來源」的權威對照）。

更新流程（`update_catalog`）依報告第 6.5 節的 manifest：manifest 同時提供
`catalog_version` 與 `catalog_url`，因此**版本相同時連請求都不用發**（比下載後才發現
相同更省）。下載成功後以「同目錄暫存檔 ＋ `os.replace`」原子取代本地檔；任何失敗都
保留原檔並以狀態回報（更新檢查不得讓服務失敗——那六條架構約束的排程屬 TASK-032）。

本模組不做 I/O 以外的判斷：不連網（HTTP 客戶端可注入）、不排程、不輸出訊息。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..errors import ConfigError, DataFormatError
from .base import Instrument

__all__ = [
    "Catalog",
    "CatalogSource",
    "UpdateResult",
    "catalog_version",
    "load_catalog",
    "save_catalog",
    "update_catalog",
]

HTTP_TIMEOUT = 5.0

_PAYLOAD_KEYS = ("catalog_version", "sources", "instruments")
_SOURCE_KEYS = ("id", "display_name", "supported_intervals", "needs_api_key")
_INSTRUMENT_KEYS = ("symbol", "interval", "source_id", "display_name")

HttpClient = Callable[[str], Any]


def _require_version(value: Any, *, where: str) -> str:
    """版本必須是 `YYYY-MM-DD`（報告與 SPEC 的 catalog 版本格式）。"""
    if not isinstance(value, str) or not value.strip():
        raise DataFormatError(f"{where} 的 catalog_version 必須是非空字串，收到 {value!r}")
    text = value.strip()
    try:
        dt.date.fromisoformat(text)
    except ValueError as error:
        raise DataFormatError(
            f"{where} 的 catalog_version 必須是 YYYY-MM-DD，收到 {text!r}（{error}）"
        ) from error
    return text


@dataclass(frozen=True)
class CatalogSource:
    """catalog 裡的來源中介資料（`id` 必填，其餘選填）。"""

    id: str
    display_name: str = ""
    supported_intervals: tuple[str, ...] = ()
    needs_api_key: bool = False


@dataclass(frozen=True)
class Catalog:
    """版本化的來源與商品清單。"""

    catalog_version: str
    sources: tuple[CatalogSource, ...] = ()
    instruments: tuple[Instrument, ...] = ()

    def __post_init__(self) -> None:
        _require_version(self.catalog_version, where="Catalog")


@dataclass(frozen=True)
class UpdateResult:
    """一次 catalog 更新嘗試的結果。

    `status` 為 `installed`（首次安裝）／`updated`（遠端較新且已取代）／`current`
    （版本相同，未發出請求）／`local-newer`（遠端較舊，保留本地）／`failed`（下載或
    寫入失敗，本地原檔未動）。
    """

    status: str
    local_version: str | None
    remote_version: str | None
    message: str = ""
    requests: int = 0


def _source_to_payload(source: CatalogSource) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": source.id}
    if source.display_name:
        payload["display_name"] = source.display_name
    if source.supported_intervals:
        payload["supported_intervals"] = list(source.supported_intervals)
    if source.needs_api_key:
        payload["needs_api_key"] = True
    return payload


def _instrument_to_payload(instrument: Instrument) -> dict[str, Any]:
    payload: dict[str, Any] = {"symbol": instrument.symbol, "interval": instrument.interval}
    if instrument.source_id:
        payload["source_id"] = instrument.source_id
    if instrument.display_name:
        payload["display_name"] = instrument.display_name
    return payload


def _catalog_to_payload(catalog: Catalog) -> dict[str, Any]:
    return {
        "catalog_version": catalog.catalog_version,
        "sources": [_source_to_payload(source) for source in catalog.sources],
        "instruments": [
            _instrument_to_payload(instrument) for instrument in catalog.instruments
        ],
    }


def _require_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DataFormatError(f"{where} 必須是 JSON 物件，收到 {type(value).__name__}")
    return value


def _reject_unknown(payload: Mapping[str, Any], allowed: Sequence[str], *, where: str) -> None:
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise DataFormatError(f"{where} 含未知鍵：{'、'.join(unknown)}")


def _source_from_payload(value: Any, *, index: int) -> CatalogSource:
    where = f"sources[{index}]"
    payload = _require_mapping(value, where=where)
    _reject_unknown(payload, _SOURCE_KEYS, where=where)

    identifier = payload.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise DataFormatError(f"{where} 缺少非空字串的 id，收到 {identifier!r}")

    display_name = payload.get("display_name", "")
    if not isinstance(display_name, str):
        raise DataFormatError(f"{where}.display_name 必須是字串，收到 {display_name!r}")

    intervals = payload.get("supported_intervals", [])
    if not isinstance(intervals, Sequence) or isinstance(intervals, (str, bytes)):
        raise DataFormatError(f"{where}.supported_intervals 必須是陣列，收到 {intervals!r}")

    needs_key = payload.get("needs_api_key", False)
    if not isinstance(needs_key, bool):
        raise DataFormatError(f"{where}.needs_api_key 必須是布林值，收到 {needs_key!r}")

    return CatalogSource(
        id=identifier.strip(),
        display_name=display_name.strip(),
        supported_intervals=tuple(str(item) for item in intervals),
        needs_api_key=needs_key,
    )


def _instrument_from_payload(value: Any, *, index: int) -> Instrument:
    where = f"instruments[{index}]"
    payload = _require_mapping(value, where=where)
    _reject_unknown(payload, _INSTRUMENT_KEYS, where=where)

    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise DataFormatError(f"{where} 缺少非空字串的 symbol，收到 {symbol!r}")

    interval = payload.get("interval", "")
    if not isinstance(interval, str):
        raise DataFormatError(f"{where}.interval 必須是字串，收到 {interval!r}")

    source_id = payload.get("source_id", "")
    if not isinstance(source_id, str):
        raise DataFormatError(f"{where}.source_id 必須是字串，收到 {source_id!r}")

    display_name = payload.get("display_name", "")
    if not isinstance(display_name, str):
        raise DataFormatError(f"{where}.display_name 必須是字串，收到 {display_name!r}")

    return Instrument(
        symbol=symbol.strip(),
        interval=interval.strip(),
        source_id=source_id.strip(),
        display_name=display_name.strip(),
    )


def _catalog_from_payload(value: Any) -> Catalog:
    payload = _require_mapping(value, where="catalog")
    _reject_unknown(payload, _PAYLOAD_KEYS, where="catalog")

    version = _require_version(payload.get("catalog_version"), where="catalog")

    raw_sources = payload.get("sources", [])
    if not isinstance(raw_sources, list):
        raise DataFormatError(f"catalog.sources 必須是陣列，收到 {type(raw_sources).__name__}")
    raw_instruments = payload.get("instruments", [])
    if not isinstance(raw_instruments, list):
        raise DataFormatError(
            f"catalog.instruments 必須是陣列，收到 {type(raw_instruments).__name__}"
        )

    return Catalog(
        catalog_version=version,
        sources=tuple(
            _source_from_payload(item, index=index) for index, item in enumerate(raw_sources)
        ),
        instruments=tuple(
            _instrument_from_payload(item, index=index)
            for index, item in enumerate(raw_instruments)
        ),
    )


def load_catalog(path: str | Path) -> Catalog:
    """讀入本地 catalog；缺檔或內容不合法一律 `DataFormatError`（與 `data.load_csv` 一致）。"""
    catalog_path = Path(path)
    if not catalog_path.is_file():
        raise DataFormatError(f"catalog {catalog_path}：找不到檔案")

    try:
        text = catalog_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DataFormatError(f"catalog {catalog_path}：讀不到檔案（{error}）") from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise DataFormatError(f"catalog {catalog_path}：不是合法 JSON（{error}）") from error

    try:
        return _catalog_from_payload(payload)
    except DataFormatError as error:
        raise DataFormatError(f"catalog {catalog_path}：{error}") from error


def save_catalog(catalog: Catalog, path: str | Path) -> Path:
    """以「同目錄暫存檔 ＋ `os.replace`」原子寫入 catalog。"""
    catalog_path = Path(path)
    temporary = catalog_path.with_name(f"{catalog_path.name}.tmp")
    try:
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(_catalog_to_payload(catalog), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, catalog_path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"無法寫入 catalog {catalog_path}：{error}") from error
    return catalog_path


def catalog_version(catalog_or_path: Catalog | str | Path) -> str | None:
    """取得版本：`Catalog` 直接回傳；路徑則讀檔，**檔案不存在時回 `None`**（首次安裝）。"""
    if isinstance(catalog_or_path, Catalog):
        return catalog_or_path.catalog_version
    path = Path(catalog_or_path)
    if not path.is_file():
        return None
    return load_catalog(path).catalog_version


def _default_client(url: str) -> Any:
    """標準庫 HTTP 客戶端；非 2xx 由 `urllib` 丟出例外（呼叫端會轉成失敗狀態）。"""
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_newer(remote: str, local: str) -> bool:
    return dt.date.fromisoformat(remote) > dt.date.fromisoformat(local)


def update_catalog(
    local_path: str | Path,
    catalog_url: str,
    *,
    remote_version: str | None = None,
    client: HttpClient | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> UpdateResult:
    """比對版本並（必要時）下載取代本地 catalog；失敗一律回報狀態而不丟例外。

    `remote_version` 來自更新 manifest。給了它就能在**不發出任何請求**的情況下判斷
    版本是否相同（AC-038 的「版本相同不重複下載」）；未給時才以下載到的內容比對。
    """
    path = Path(local_path)
    local: str | None
    try:
        local = catalog_version(path)
    except DataFormatError as error:
        # 本地檔損毀：視為需要重新下載，但要留下可讀的說明。
        local = None
        local_error = str(error)
    else:
        local_error = ""

    wanted: str | None = None
    if remote_version is not None:
        wanted = _require_version(remote_version, where="manifest")

    if local is not None and wanted is not None and not _is_newer(wanted, local):
        result = UpdateResult(
            status="current" if wanted == local else "local-newer",
            local_version=local,
            remote_version=wanted,
            message="" if wanted == local else f"遠端版本 {wanted} 較本地 {local} 舊，保留本地",
        )
        _record(state, result)
        return result

    getter = client if client is not None else _default_client
    try:
        payload = getter(catalog_url)
    except Exception as error:  # 客戶端是外部邊界；更新失敗不得讓服務失敗
        result = UpdateResult(
            status="failed",
            local_version=local,
            remote_version=wanted,
            message=_combine(f"下載 catalog 失敗：{error}", local_error),
            requests=1,
        )
        _record(state, result)
        return result

    try:
        downloaded = _catalog_from_payload(payload)
    except DataFormatError as error:
        result = UpdateResult(
            status="failed",
            local_version=local,
            remote_version=wanted,
            message=_combine(f"下載的 catalog 內容不合法：{error}", local_error),
            requests=1,
        )
        _record(state, result)
        return result

    if local is not None and not _is_newer(downloaded.catalog_version, local):
        result = UpdateResult(
            status="current" if downloaded.catalog_version == local else "local-newer",
            local_version=local,
            remote_version=downloaded.catalog_version,
            message=f"遠端版本 {downloaded.catalog_version} 未較本地 {local} 新，保留本地",
            requests=1,
        )
        _record(state, result)
        return result

    try:
        save_catalog(downloaded, path)
    except ConfigError as error:
        result = UpdateResult(
            status="failed",
            local_version=local,
            remote_version=downloaded.catalog_version,
            message=_combine(str(error), local_error),
            requests=1,
        )
        _record(state, result)
        return result

    result = UpdateResult(
        status="installed" if local is None else "updated",
        local_version=downloaded.catalog_version,
        remote_version=downloaded.catalog_version,
        message=local_error,
        requests=1,
    )
    _record(state, result)
    return result


def _combine(primary: str, local_error: str) -> str:
    """同時有「本地檔損毀」與「下載失敗」時，兩個都要講，否則使用者只修一半。"""
    if not local_error:
        return primary
    return f"{primary}；本地檔問題：{local_error}"


def _record(state: MutableMapping[str, Any] | None, result: UpdateResult) -> None:
    """把結果寫進呼叫端提供的狀態容器（系統狀態頁與更新排程會讀它）。"""
    if state is None:
        return
    state["catalog"] = {
        "status": result.status,
        "version": result.local_version,
        "message": result.message,
    }
