"""靜態 manifest／catalog 快照必須能被**客戶端**讀取（TASK-034／AC-061）。

`cloudflare/test/static.test.mjs` 驗的是 JS 端的 schema 與快取標頭；這一支從**另一端**
驗同一份檔案：`ediaad.update.parse_manifest`（TASK-032 的更新檢查）與
`ediaad.markets.catalog.load_catalog`（TASK-017 的 catalog 載入器）。

跨語言的檔案如果只被其中一邊驗證過，就可能出現「JS 說合法、客戶端讀不進去」的分岔——
這正是報告 F-001 的形狀。兩個快照的 `catalog_version` 也必須同源。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ediaad.errors import ConfigError
from ediaad.markets.catalog import load_catalog
from ediaad.update import parse_manifest

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "cloudflare" / "static"


def read_json(name: str) -> dict:
    return json.loads((STATIC_DIR / name).read_text(encoding="utf-8"))


def test_manifest_snapshot_parses_with_the_client():
    manifest = read_json("latest.json")

    state = parse_manifest(manifest)

    assert state.latest_version == manifest["version"]
    assert state.released_at == manifest["released_at"]
    assert state.notes == manifest["notes"]
    assert state.catalog_version == manifest["catalog_version"]
    assert state.catalog_url == manifest["catalog_url"]


def test_catalog_snapshot_loads_with_the_client():
    catalog = load_catalog(STATIC_DIR / "catalog.json")

    assert catalog.catalog_version == read_json("catalog.json")["catalog_version"]
    assert catalog.sources, "上線用的快照不該是空的來源清單"
    assert catalog.instruments, "上線用的快照不該是空的商品清單"

    known = {source.id for source in catalog.sources}
    for instrument in catalog.instruments:
        assert instrument.source_id in known, f"{instrument.symbol} 的來源不在 sources 裡"


def test_snapshots_share_one_catalog_version():
    manifest = read_json("latest.json")
    catalog = read_json("catalog.json")

    assert manifest["catalog_version"] == catalog["catalog_version"], (
        "manifest 與 catalog 必須來自同一份快照，否則客戶端會以為 catalog 過期"
    )


def test_snapshot_urls_are_placeholders():
    manifest = read_json("latest.json")

    for field in ("url", "catalog_url"):
        host = manifest[field].split("//", 1)[1].split("/", 1)[0]
        assert host.endswith(".invalid"), f"{field} 必須使用保留的 .invalid 佔位網域"


def test_manifest_snapshot_rejects_a_non_object():
    with pytest.raises(ConfigError):
        parse_manifest(["not", "an", "object"])
