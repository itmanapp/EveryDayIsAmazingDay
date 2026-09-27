"""設定解析、驗證與原子寫入（TASK-019）。

觀察邊界：對 `tmp_path` 下的**真實**設定檔呼叫 `load_settings`／`save_settings_atomic`，
以檔案位元組、目錄內容與例外型別為觀察邊界（SPEC 第 7 節明定原子寫入不能只對 mock
宣稱通過）；不檢視私有的暫存檔命名常數。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ediaad.errors import ConfigError
from ediaad.patterns import NAMED_PATTERNS


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def temp_leftovers(directory: Path, *, keep: str = "settings.json") -> list[str]:
    return sorted(item.name for item in directory.iterdir() if item.name != keep)


# ---- AC-040：原子寫入與讀取 -------------------------------------------------


def test_save_then_load_round_trips_the_settings(tmp_path):
    from ediaad.config import load_settings, save_settings_atomic

    path = tmp_path / "settings.json"
    settings = {"poll_interval_seconds": 30, "horizon": 7}

    save_settings_atomic(path, settings)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["poll_interval_seconds"] == 30
    assert stored["horizon"] == 7
    assert load_settings(path)["poll_interval_seconds"] == 30
    assert load_settings(path)["horizon"] == 7


def test_save_leaves_no_temporary_file(tmp_path):
    from ediaad.config import save_settings_atomic

    save_settings_atomic(tmp_path / "settings.json", {})

    assert temp_leftovers(tmp_path) == []


def test_save_creates_the_parent_directory(tmp_path):
    from ediaad.config import load_settings, save_settings_atomic

    path = tmp_path / "home" / "nested" / "settings.json"
    save_settings_atomic(path, {"horizon": 3})

    assert path.is_file()
    assert load_settings(path)["horizon"] == 3


def test_save_replaces_the_previous_content(tmp_path):
    from ediaad.config import save_settings_atomic

    path = tmp_path / "settings.json"
    write_text(path, json.dumps({"horizon": 1}))

    save_settings_atomic(path, {"horizon": 9})

    assert json.loads(path.read_text(encoding="utf-8"))["horizon"] == 9
    assert temp_leftovers(tmp_path) == []


def test_default_settings_are_available_and_consistent(tmp_path):
    from ediaad.config import DEFAULT_SETTINGS, load_settings

    assert set(DEFAULT_SETTINGS) == {
        "market",
        "pattern_id",
        "pattern_spec",
        "poll_interval_seconds",
        "horizon",
        "cache_max_age_seconds",
        "update_enabled",
    }

    # 檔案不存在時（首次啟動）＝ 預設值
    missing = load_settings(tmp_path / "absent.json")
    assert missing == DEFAULT_SETTINGS
    assert missing is not DEFAULT_SETTINGS, "回傳可變副本，避免呼叫端改到共用的預設值"


def test_missing_keys_are_filled_from_the_defaults(tmp_path):
    from ediaad.config import DEFAULT_SETTINGS, load_settings

    path = write_text(tmp_path / "settings.json", json.dumps({"horizon": 11}))

    settings = load_settings(path)

    assert settings["horizon"] == 11, "檔案有給的值優先"
    for key, value in DEFAULT_SETTINGS.items():
        if key != "horizon":
            assert settings[key] == value, f"{key} 應補上預設值"


def test_saved_defaults_load_back_as_the_same_mapping(tmp_path):
    from ediaad.config import DEFAULT_SETTINGS, load_settings, save_settings_atomic

    path = tmp_path / "settings.json"
    save_settings_atomic(path, dict(DEFAULT_SETTINGS))

    assert load_settings(path) == DEFAULT_SETTINGS


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("{not json", id="非 JSON"),
        pytest.param("", id="空檔案"),
        pytest.param("[1, 2, 3]", id="頂層是陣列"),
        pytest.param('"just a string"', id="頂層是字串"),
    ],
)
def test_a_corrupt_settings_file_is_reported_and_never_rewritten(tmp_path, text):
    from ediaad.config import load_settings

    path = write_text(tmp_path / "settings.json", text)
    before = path.read_bytes()

    with pytest.raises(ConfigError) as excinfo:
        load_settings(path)

    assert "settings.json" in str(excinfo.value), "訊息必須指出檔名"
    assert path.read_bytes() == before, "讀取失敗不得改動原檔"
    assert temp_leftovers(tmp_path) == []


# ---- AC-040：驗證、失敗保護與並發 -------------------------------------------


def test_unknown_keys_are_rejected_with_the_key_name(tmp_path):
    from ediaad.config import load_settings, save_settings_atomic

    with pytest.raises(ConfigError, match="unexpected"):
        save_settings_atomic(tmp_path / "settings.json", {"unexpected": 1})

    path = write_text(tmp_path / "other.json", json.dumps({"unexpected": 1}))
    with pytest.raises(ConfigError, match="unexpected"):
        load_settings(path)


@pytest.mark.parametrize(
    ("overrides", "mentions"),
    [
        pytest.param({"poll_interval_seconds": "60"}, "poll_interval_seconds", id="輪詢間隔是字串"),
        pytest.param({"poll_interval_seconds": 0}, "poll_interval_seconds", id="輪詢間隔為 0"),
        pytest.param({"poll_interval_seconds": True}, "poll_interval_seconds", id="輪詢間隔是布林"),
        pytest.param({"horizon": 0}, "horizon", id="horizon 為 0"),
        pytest.param({"cache_max_age_seconds": -1}, "cache_max_age_seconds", id="快取有效期為負"),
        pytest.param({"update_enabled": "yes"}, "update_enabled", id="開關不是布林"),
        pytest.param({"market": "nasdaq"}, "market", id="未知市場別"),
        pytest.param({"market": ""}, "market", id="空市場別"),
        pytest.param({"pattern_id": "   "}, "pattern_id", id="空規律 ID"),
        pytest.param({"pattern_spec": "nope"}, "pattern_spec", id="規格不是物件"),
        pytest.param(
            {"pattern_spec": {**NAMED_PATTERNS["range_fakeout_reversion"], "pattern_id": "other"}},
            "pattern_id",
            id="規格身分不一致",
        ),
        pytest.param({"pattern_spec": {"range_bars_min": 0}}, "pattern_spec", id="規格參數不合法"),
    ],
)
def test_invalid_values_are_rejected_with_the_key_name(tmp_path, overrides, mentions):
    from ediaad.config import save_settings_atomic

    with pytest.raises(ConfigError, match=mentions):
        save_settings_atomic(tmp_path / "settings.json", overrides)


def test_an_invalid_save_never_touches_the_existing_file(tmp_path):
    from ediaad.config import save_settings_atomic

    path = write_text(tmp_path / "settings.json", json.dumps({"horizon": 4}))
    before = path.read_bytes()

    with pytest.raises(ConfigError):
        save_settings_atomic(path, {"horizon": 0})

    assert path.read_bytes() == before, "驗證必須在碰觸檔案之前完成"
    assert temp_leftovers(tmp_path) == []


def test_a_failure_before_replace_keeps_the_original_and_cleans_up(tmp_path, monkeypatch):
    from ediaad import config

    path = write_text(tmp_path / "settings.json", json.dumps({"horizon": 4}))
    before = path.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(config.json, "dump", boom)

    with pytest.raises(ConfigError, match="disk full"):
        config.save_settings_atomic(path, {"horizon": 8})

    assert path.read_bytes() == before, "取代前的失敗必須保留原內容"
    assert temp_leftovers(tmp_path) == [], "失敗時必須清掉暫存檔"


def test_a_valid_pattern_spec_round_trips(tmp_path):
    from ediaad.config import load_settings, save_settings_atomic
    from ediaad.patterns import NAMED_PATTERNS

    spec = dict(NAMED_PATTERNS["range_fakeout_reversion"])
    path = tmp_path / "settings.json"

    save_settings_atomic(path, {"pattern_spec": spec, "pattern_id": spec["pattern_id"]})

    assert load_settings(path)["pattern_spec"] == spec


def test_loading_never_writes_anything(tmp_path):
    from ediaad.config import load_settings

    path = write_text(tmp_path / "settings.json", json.dumps({"horizon": 4}))
    before = path.read_bytes()
    stamp = path.stat().st_mtime_ns

    load_settings(path)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == stamp
    assert temp_leftovers(tmp_path) == []


def test_two_saves_of_the_same_settings_produce_identical_bytes(tmp_path):
    from ediaad.config import save_settings_atomic

    first, second = tmp_path / "a.json", tmp_path / "b.json"
    settings = {
        "horizon": 6,
        "pattern_id": "p",
        "pattern_spec": {**NAMED_PATTERNS["range_fakeout_reversion"], "pattern_id": "p"},
    }

    save_settings_atomic(first, settings)
    save_settings_atomic(second, settings)

    assert first.read_bytes() == second.read_bytes(), "輸出的位元必須可重現"


def test_concurrent_saves_use_distinct_temporary_files(tmp_path, monkeypatch):
    from ediaad import config

    seen: list[str] = []
    real_replace = os.replace

    def spy(source, destination):
        seen.append(Path(source).name)
        return real_replace(source, destination)

    monkeypatch.setattr(config.os, "replace", spy)
    path = tmp_path / "settings.json"

    config.save_settings_atomic(path, {"horizon": 1})
    config.save_settings_atomic(path, {"horizon": 2})

    assert len(set(seen)) == 2, f"暫存檔名不得重複：{seen}"


def test_saving_from_several_threads_keeps_the_file_valid(tmp_path):
    import threading

    from ediaad.config import load_settings, save_settings_atomic

    path = tmp_path / "settings.json"
    errors: list[BaseException] = []

    def worker(horizon: int) -> None:
        try:
            for _ in range(5):
                save_settings_atomic(path, {"horizon": horizon})
        except BaseException as error:  # noqa: BLE001 - 測試要把任何例外帶回主執行緒
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(value,)) for value in (3, 7, 11, 13)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [], f"並發寫入不得失敗：{errors}"
    assert temp_leftovers(tmp_path) == [], "並發寫入不得留下暫存檔"
    final = json.loads(path.read_text(encoding="utf-8"))
    assert final["horizon"] in (3, 7, 11, 13), "最終內容必須是某一份完整設定"
    assert load_settings(path)["horizon"] == final["horizon"]


def test_zero_cache_max_age_is_allowed(tmp_path):
    """`cache_max_age_seconds = 0` 是合法值（等於不快取／一律視為過期）。"""
    from ediaad.config import load_settings, save_settings_atomic

    path = tmp_path / "settings.json"
    save_settings_atomic(path, {"cache_max_age_seconds": 0})

    assert load_settings(path)["cache_max_age_seconds"] == 0


def test_the_same_settings_in_a_different_key_order_produce_identical_bytes(tmp_path):
    """位元可重現（SPEC 第 6 節）：鍵的插入順序不得影響輸出。"""
    from ediaad.config import save_settings_atomic

    first, second = tmp_path / "a.json", tmp_path / "b.json"

    save_settings_atomic(first, {"horizon": 6, "market": "stock", "update_enabled": False})
    save_settings_atomic(second, {"update_enabled": False, "market": "stock", "horizon": 6})

    assert first.read_bytes() == second.read_bytes()
