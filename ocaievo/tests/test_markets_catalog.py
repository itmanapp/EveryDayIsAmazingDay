"""版本化 catalog 與更新攜帶（TASK-017）。

觀察邊界：`load_catalog`／`save_catalog`／`catalog_version` 對檔案的往返效果，以及
`update_catalog(...)` 的請求次數、回傳狀態與本地檔內容。HTTP 一律注入假客戶端，
本地檔案都在 `tmp_path`，全程離線。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ediaad.errors import DataFormatError, SourceError
from ediaad.markets.base import Instrument


class FakeHttp:
    """假 HTTP 客戶端：記錄請求 URL，回傳固定 payload 或丟出指定例外。"""

    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.payload

    @property
    def count(self) -> int:
        return len(self.calls)


def catalog_payload(version: str = "2026-10-01", **overrides) -> dict:
    payload = {
        "catalog_version": version,
        "sources": [
            {
                "id": "twse",
                "display_name": "臺灣證券交易所（上市日線）",
                "supported_intervals": ["1d"],
                "needs_api_key": False,
            },
            {"id": "twelvedata", "display_name": "Twelve Data（美股）", "needs_api_key": True},
        ],
        "instruments": [
            {"symbol": "2330", "interval": "1d", "source_id": "twse", "display_name": "台積電"},
            {"symbol": "AAPL", "interval": "1d", "source_id": "twelvedata", "display_name": "Apple Inc."},
        ],
    }
    payload.update(overrides)
    return payload


def write_catalog(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ---- AC-038：Catalog 結構與往返 ---------------------------------------------


def test_save_and_load_round_trip_restores_the_same_catalog(tmp_path):
    from ediaad.markets.catalog import Catalog, load_catalog, save_catalog

    path = tmp_path / "catalog.json"
    original = Catalog(
        catalog_version="2026-10-01",
        sources=(),
        instruments=(
            Instrument(symbol="2330", interval="1d", source_id="twse", display_name="台積電"),
        ),
    )

    save_catalog(original, path)
    restored = load_catalog(path)

    assert restored == original


def test_load_catalog_parses_sources_and_instruments(tmp_path):
    from ediaad.markets.catalog import load_catalog

    path = write_catalog(tmp_path / "catalog.json", catalog_payload())

    catalog = load_catalog(path)

    assert catalog.catalog_version == "2026-10-01"
    assert [source.id for source in catalog.sources] == ["twse", "twelvedata"]
    twse = catalog.sources[0]
    assert twse.display_name == "臺灣證券交易所（上市日線）"
    assert tuple(twse.supported_intervals) == ("1d",)
    assert twse.needs_api_key is False
    assert catalog.sources[1].needs_api_key is True
    assert [item.symbol for item in catalog.instruments] == ["2330", "AAPL"]
    assert catalog.instruments[0] == Instrument(
        symbol="2330", interval="1d", source_id="twse", display_name="台積電"
    )


def test_saved_catalog_is_valid_json_with_the_documented_keys(tmp_path):
    from ediaad.markets.catalog import load_catalog, save_catalog

    path = tmp_path / "catalog.json"
    save_catalog(load_catalog(write_catalog(path, catalog_payload())), path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {"catalog_version", "sources", "instruments"}
    assert payload["catalog_version"] == "2026-10-01"
    assert payload["instruments"][0]["symbol"] == "2330"


def test_save_catalog_is_atomic_and_leaves_no_temporary_file(tmp_path):
    from ediaad.markets.catalog import load_catalog, save_catalog

    path = tmp_path / "nested" / "catalog.json"
    save_catalog(load_catalog(write_catalog(tmp_path / "seed.json", catalog_payload())), path)

    assert path.is_file()
    assert sorted(item.name for item in path.parent.iterdir()) == ["catalog.json"]


def test_save_catalog_replaces_an_existing_file(tmp_path):
    from ediaad.markets.catalog import load_catalog, save_catalog

    path = write_catalog(tmp_path / "catalog.json", catalog_payload("2026-09-01"))

    save_catalog(load_catalog(write_catalog(tmp_path / "new.json", catalog_payload("2026-10-01"))), path)

    assert load_catalog(path).catalog_version == "2026-10-01"


def test_catalog_version_accepts_a_catalog_or_a_path(tmp_path):
    from ediaad.markets.catalog import Catalog, catalog_version

    path = write_catalog(tmp_path / "catalog.json", catalog_payload("2026-10-01"))

    assert catalog_version(path) == "2026-10-01"
    assert catalog_version(Catalog(catalog_version="2026-11-30")) == "2026-11-30"


def test_catalog_version_of_a_missing_file_is_none(tmp_path):
    """首次安裝：本地還沒有 catalog，這不是錯誤，而是「需要下載」的訊號。"""
    from ediaad.markets.catalog import catalog_version

    assert catalog_version(tmp_path / "absent.json") is None


def test_load_catalog_reports_a_missing_file(tmp_path):
    from ediaad.markets.catalog import load_catalog

    with pytest.raises(DataFormatError) as excinfo:
        load_catalog(tmp_path / "absent.json")

    assert "absent.json" in str(excinfo.value)


@pytest.mark.parametrize(
    ("payload", "mentions"),
    [
        pytest.param("{not json", "JSON", id="損毀 JSON"),
        pytest.param([], "物件", id="不是物件"),
        pytest.param({"sources": [], "instruments": []}, "catalog_version", id="缺版本"),
        pytest.param(catalog_payload("2026/10/01"), "2026/10/01", id="版本格式錯誤"),
        pytest.param(catalog_payload(version="vNext"), "vNext", id="非日期版本"),
        pytest.param(catalog_payload(catalog_version=20261001), "catalog_version", id="版本不是字串"),
        pytest.param(catalog_payload(sources="x"), "sources", id="sources 不是陣列"),
        pytest.param(catalog_payload(sources=[{"display_name": "x"}]), "id", id="來源缺 id"),
        pytest.param(catalog_payload(instruments="x"), "instruments", id="instruments 不是陣列"),
        pytest.param(catalog_payload(instruments=[{"interval": "1d"}]), "symbol", id="商品缺 symbol"),
        pytest.param(catalog_payload(instruments=[{"symbol": "2330", "interval": "1d", "x": 1}]), "x", id="商品含未知鍵"),
        pytest.param(catalog_payload(extra=1), "extra", id="頂層含未知鍵"),
    ],
)
def test_load_catalog_reports_bad_payloads(tmp_path, payload, mentions):
    from ediaad.markets.catalog import load_catalog

    path = write_catalog(tmp_path / "catalog.json", payload)

    with pytest.raises(DataFormatError, match=mentions):
        load_catalog(path)


def test_catalog_rejects_an_invalid_version_at_construction():
    from ediaad.markets.catalog import Catalog

    with pytest.raises(DataFormatError, match="2026-13-45"):
        Catalog(catalog_version="2026-13-45")

    with pytest.raises(DataFormatError):
        Catalog(catalog_version="")


def test_catalog_is_frozen_and_hashable():
    from ediaad.markets.catalog import Catalog

    catalog = Catalog(catalog_version="2026-10-01")

    with pytest.raises(Exception):
        catalog.catalog_version = "2026-11-01"

    assert catalog.sources == ()
    assert catalog.instruments == ()
    assert isinstance(hash(catalog), int)


# ---- AC-038：版本比對、下載與原子取代 ---------------------------------------


def local_file(tmp_path: Path, version: str) -> Path:
    return write_catalog(tmp_path / "catalog.json", catalog_payload(version))


def test_a_newer_remote_version_is_downloaded_and_replaces_the_local_file(tmp_path):
    from ediaad.markets.catalog import catalog_version, update_catalog

    path = local_file(tmp_path, "2026-09-01")
    http = FakeHttp(catalog_payload("2026-10-01"))

    result = update_catalog(path, "https://example.test/catalog.json", client=http)

    assert result.status == "updated"
    assert result.local_version == "2026-10-01"
    assert result.remote_version == "2026-10-01"
    assert result.requests == 1
    assert http.count == 1
    assert http.calls == ["https://example.test/catalog.json"]
    assert catalog_version(path) == "2026-10-01"
    assert sorted(item.name for item in path.parent.iterdir()) == ["catalog.json"]


def test_an_equal_manifest_version_makes_no_request_at_all(tmp_path):
    from ediaad.markets.catalog import update_catalog

    path = local_file(tmp_path, "2026-10-01")
    before = path.read_bytes()
    http = FakeHttp(catalog_payload("2026-10-01"))

    result = update_catalog(
        path, "https://example.test/catalog.json", remote_version="2026-10-01", client=http
    )

    assert result.status == "current"
    assert http.count == 0, "版本相同時連請求都不該發出"
    assert result.requests == 0
    assert path.read_bytes() == before, "版本相同時本地檔不得被重寫"


def test_an_older_manifest_version_keeps_the_local_catalog(tmp_path):
    from ediaad.markets.catalog import catalog_version, update_catalog

    path = local_file(tmp_path, "2026-10-01")
    before = path.read_bytes()
    http = FakeHttp(catalog_payload("2026-09-01"))

    result = update_catalog(
        path, "https://example.test/catalog.json", remote_version="2026-09-01", client=http
    )

    assert result.status == "local-newer"
    assert http.count == 0
    assert path.read_bytes() == before
    assert catalog_version(path) == "2026-10-01", "不得降版"
    assert "2026-09-01" in result.message


def test_the_downloaded_version_decides_when_the_manifest_omits_it(tmp_path):
    from ediaad.markets.catalog import update_catalog

    path = local_file(tmp_path, "2026-10-01")
    before = path.read_bytes()

    same = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(catalog_payload("2026-10-01")))
    assert same.status == "current"
    assert same.requests == 1, "manifest 沒給版本時只能下載後比對"
    assert path.read_bytes() == before, "比對後發現相同也不得重寫"

    older = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(catalog_payload("2026-01-01")))
    assert older.status == "local-newer"
    assert path.read_bytes() == before


def test_a_first_install_downloads_and_creates_the_file(tmp_path):
    from ediaad.markets.catalog import load_catalog, update_catalog

    path = tmp_path / "ediaad-home" / "catalog.json"
    http = FakeHttp(catalog_payload("2026-10-01"))

    result = update_catalog(path, "https://example.test/catalog.json", client=http)

    assert result.status == "installed"
    assert result.local_version == "2026-10-01"
    assert path.is_file()
    assert load_catalog(path).catalog_version == "2026-10-01"


def test_a_corrupt_local_file_is_replaced_by_a_successful_download(tmp_path):
    from ediaad.markets.catalog import update_catalog

    path = write_catalog(tmp_path / "catalog.json", "{not json")

    result = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(catalog_payload()))

    assert result.status == "installed", "損毀的本地檔視為需要重新下載"
    assert result.local_version == "2026-10-01"
    assert "JSON" in result.message, "狀態必須留下本地檔損毀的說明"


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(OSError("connection refused"), id="連線錯誤"),
        pytest.param(RuntimeError("HTTP 500"), id="非 200"),
        pytest.param(SourceError("boom"), id="來源錯誤"),
    ],
)
def test_a_download_failure_keeps_the_local_file_byte_identical(tmp_path, error):
    from ediaad.markets.catalog import load_catalog, update_catalog

    path = local_file(tmp_path, "2026-09-01")
    before = path.read_bytes()

    result = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(error=error))

    assert result.status == "failed"
    assert result.requests == 1
    assert path.read_bytes() == before, "失敗時本地檔必須位元不變"
    assert load_catalog(path).catalog_version == "2026-09-01", "失敗後原檔仍必須可載入"
    assert "失敗" in result.message
    assert sorted(item.name for item in path.parent.iterdir()) == ["catalog.json"], "不得留下暫存檔"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("{not json", id="非 JSON"),
        pytest.param([], id="不是物件"),
        pytest.param({"sources": [], "instruments": []}, id="缺 catalog_version"),
        pytest.param(catalog_payload("2026/10/01"), id="版本格式錯誤"),
        pytest.param(catalog_payload(instruments=[{"interval": "1d"}]), id="商品缺 symbol"),
    ],
)
def test_a_malformed_download_keeps_the_local_file(tmp_path, payload):
    from ediaad.markets.catalog import load_catalog, update_catalog

    path = local_file(tmp_path, "2026-09-01")
    before = path.read_bytes()

    result = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(payload))

    assert result.status == "failed"
    assert path.read_bytes() == before
    assert load_catalog(path).catalog_version == "2026-09-01"
    assert "不合法" in result.message


def test_an_unwritable_directory_fails_without_damaging_the_original(tmp_path):
    from ediaad.markets.catalog import load_catalog, update_catalog

    directory = tmp_path / "home"
    path = write_catalog(directory / "catalog.json", catalog_payload("2026-09-01"))
    before = path.read_bytes()
    os.chmod(directory, 0o500)
    try:
        result = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(catalog_payload()))
    finally:
        os.chmod(directory, 0o700)

    assert result.status == "failed"
    assert path.read_bytes() == before
    assert load_catalog(path).catalog_version == "2026-09-01"
    assert sorted(item.name for item in directory.iterdir()) == ["catalog.json"]


def test_the_result_and_the_state_container_report_the_outcome(tmp_path):
    from ediaad.markets.catalog import update_catalog

    path = local_file(tmp_path, "2026-09-01")
    state: dict = {"other": 1}

    result = update_catalog(
        path,
        "https://example.test/catalog.json",
        remote_version="2026-10-01",
        client=FakeHttp(catalog_payload("2026-10-01")),
        state=state,
    )

    assert result.status == "updated"
    assert state["other"] == 1, "不得清掉狀態容器裡的其他鍵"
    assert state["catalog"] == {
        "status": "updated",
        "version": "2026-10-01",
        "message": "",
    }


def test_a_failed_update_is_also_recorded_in_the_state(tmp_path):
    from ediaad.markets.catalog import update_catalog

    path = local_file(tmp_path, "2026-09-01")
    state: dict = {}

    update_catalog(
        path,
        "https://example.test/catalog.json",
        client=FakeHttp(error=OSError("down")),
        state=state,
    )

    assert state["catalog"]["status"] == "failed"
    assert state["catalog"]["version"] == "2026-09-01", "失敗時狀態仍顯示可用的本地版本"
    assert "down" in state["catalog"]["message"]


@pytest.mark.parametrize("remote_version", ["2026/10/01", "vNext", "", 20261001])
def test_an_invalid_manifest_version_is_a_data_format_error(tmp_path, remote_version):
    from ediaad.markets.catalog import update_catalog

    path = local_file(tmp_path, "2026-09-01")
    http = FakeHttp(catalog_payload("2026-10-01"))

    with pytest.raises(DataFormatError):
        update_catalog(path, "https://example.test/catalog.json", remote_version=remote_version, client=http)

    assert http.count == 0


def test_a_corrupt_local_file_with_a_failed_download_reports_both(tmp_path):
    """兩個問題同時存在時，訊息必須同時提到，否則使用者只會修一半。"""
    from ediaad.markets.catalog import update_catalog

    path = write_catalog(tmp_path / "catalog.json", "{not json")

    result = update_catalog(path, "https://example.test/catalog.json", client=FakeHttp(error=OSError("down")))

    assert result.status == "failed"
    assert result.local_version is None
    assert "JSON" in result.message, "必須提到本地檔損毀"
    assert "down" in result.message, "也必須提到下載失敗"
    assert path.read_text(encoding="utf-8") == "{not json", "損毀的原檔不得被刪除或改寫"
