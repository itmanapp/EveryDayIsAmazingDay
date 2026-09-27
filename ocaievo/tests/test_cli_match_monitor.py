"""`ediaad` 命令列的端到端測試（TASK-011）。

觀察邊界：

1. 端到端：以 `subprocess` 執行 `.venv/bin/python -m ediaad`（`match`／`monitor`），
   觀察 exit code、stdout／stderr 與輸出檔內容。
2. 契約層（少數）：直接呼叫 `cli.main` 與 `cli._local_cache_fetch`，用最小 stub 釘住
   SPEC 第 5 節的「錯誤分層」對應表與來源轉接器的例外型別——這些分支在端到端路徑上
   會被 `run_once` 的 warning 計數掩蓋（見 `test_main_maps_errors_to_the_documented_exit_codes`）。

所有測試離線可跑，資料為合成 CSV。
"""

from __future__ import annotations

import itertools
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pandas as pd
import pytest

from ediaad.cli import _local_cache_fetch
from ediaad.errors import ConfigError, DataFormatError, SourceError

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"

REPORT_KEYS = {"sample", "params", "data_source", "matches", "outlook"}
OUTLOOK_KEYS = {
    "samples",
    "up_probability",
    "mean_return",
    "median_return",
    "std_return",
}


def run_cli(*args: str, timeout: float = 180.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PYTHON), "-m", "ediaad", *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def build_series_frame(*, total: int, offset: int = 50, range_bars: int = 12) -> pd.DataFrame:
    """在 `offset` 處植入完整結構的序列。

    背景**刻意帶有變異**（週期性小階梯）：若背景完全平坦，候選池在幾乎每個維度的
    IQR 都是 0，穩健正規化會把它們全部退化為 0，於是所有候選距離皆為 0、全部同分
    1.0（這是規格明訂的 IQR=0 退化行為）。有變異才能讓「完全相同的那個視窗」
    唯一地取得第一名。
    """
    closes = [100.0 + (index % 7) * 0.3 for index in range(total)]
    highs = [value + 1.0 for value in closes]
    lows = [value - 1.0 for value in closes]

    lows[offset - 1] = 90.0
    for step in range(range_bars):
        base = 100.0 if step % 2 == 0 else 100.4
        closes[offset + step] = base
        highs[offset + step] = base + 1.0
        lows[offset + step] = base - 1.0

    breakdown = offset + range_bars
    closes[breakdown] = 98.5
    highs[breakdown] = 99.5
    lows[breakdown] = 97.0

    recovery = breakdown + 1
    closes[recovery] = 100.5
    highs[recovery] = 101.0
    lows[recovery] = 99.5

    times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10.0 + (index % 5) for index in range(total)],
        }
    )


def write_csv(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def prepare_match_inputs(
    tmp_path: Path, *, total: int = 200, offset: int = 50, range_bars: int = 12, name: str = ""
):
    frame = build_series_frame(total=total, offset=offset, range_bars=range_bars)
    data_path = write_csv(tmp_path / f"data{name}.csv", frame)
    sample_path = write_csv(
        tmp_path / f"sample{name}.csv", frame.iloc[offset : offset + range_bars]
    )
    return data_path, sample_path


def read_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- AC-027：match 子命令與五鍵 JSON 報表 -----------------------------------


def test_match_writes_a_report_with_exactly_five_top_level_keys(tmp_path):
    data_path, sample_path = prepare_match_inputs(tmp_path)
    report_path = tmp_path / "report.json"

    completed = run_cli(
        "match",
        "--data",
        str(data_path),
        "--sample",
        str(sample_path),
        "--top",
        "5",
        "--horizon",
        "10",
        "--out",
        str(report_path),
    )

    assert completed.returncode == 0, completed.stderr
    report = read_report(report_path)
    assert set(report) == REPORT_KEYS
    assert set(report["outlook"]) == OUTLOOK_KEYS
    assert report["data_source"] == "csv"
    assert report["matches"], "植入的結構必須被找到"
    assert report["matches"][0]["start_index"] == 50
    assert report["matches"][0]["score"] == pytest.approx(1.0)
    assert report["params"]["window"] == 12
    assert report["params"]["top"] == 5
    assert report["params"]["horizon"] == 10
    assert report["sample"]["length"] == 12


def test_match_prints_a_one_line_summary(tmp_path):
    data_path, sample_path = prepare_match_inputs(tmp_path)
    report_path = tmp_path / "report.json"

    completed = run_cli(
        "match",
        "--data",
        str(data_path),
        "--sample",
        str(sample_path),
        "--top",
        "3",
        "--horizon",
        "10",
        "--out",
        str(report_path),
    )

    assert completed.returncode == 0, completed.stderr
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    assert str(report_path) in stdout_lines[0]


# ---- AC-027：exit code 語意（0／1／2）與不留下半寫報表 ----------------------


def test_match_exits_two_when_the_data_file_does_not_exist(tmp_path):
    _, sample_path = prepare_match_inputs(tmp_path)
    report_path = tmp_path / "report.json"

    completed = run_cli(
        "match",
        "--data",
        str(tmp_path / "missing.csv"),
        "--sample",
        str(sample_path),
        "--top",
        "3",
        "--horizon",
        "10",
        "--out",
        str(report_path),
    )

    assert completed.returncode == 2
    assert "找不到檔案" in completed.stderr
    assert not report_path.exists()


def test_match_uses_the_documented_defaults_when_omitted(tmp_path):
    """省略 --top／--horizon／--step／--overlap 時，報表要帶文件上的預設值。

    這些預設值與 `POST /api/match` 共用同一組常數（`ediaad.match`），因此這一條同時
    釘住兩個入口的預設行為。
    """
    data_path, sample_path = prepare_match_inputs(tmp_path)
    report_path = tmp_path / "report.json"

    completed = run_cli(
        "match",
        "--data",
        str(data_path),
        "--sample",
        str(sample_path),
        "--out",
        str(report_path),
    )

    assert completed.returncode == 0, completed.stderr
    report = read_report(report_path)
    assert report["params"] == {
        "window": 12,
        "top": 10,
        "horizon": 20,
        "step": 1,
        "overlap": 0.5,
    }


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(["--top", "0"], id="top 為 0"),
        pytest.param(["--horizon", "0"], id="horizon 為 0"),
        pytest.param(["--horizon", "-1"], id="horizon 為負"),
        pytest.param(["--step", "0"], id="step 為 0"),
        pytest.param(["--overlap", "1.5"], id="overlap 超出範圍"),
    ],
)
def test_match_exits_two_for_invalid_parameters(tmp_path, extra):
    data_path, sample_path = prepare_match_inputs(tmp_path)
    report_path = tmp_path / "report.json"

    completed = run_cli(
        "match",
        "--data",
        str(data_path),
        "--sample",
        str(sample_path),
        "--top",
        "3",
        "--horizon",
        "10",
        "--out",
        str(report_path),
        *extra,
    )

    assert completed.returncode == 2, completed.stderr
    assert "Traceback" not in completed.stderr
    assert not report_path.exists()


def test_match_exits_one_when_the_report_cannot_be_written(tmp_path):
    data_path, sample_path = prepare_match_inputs(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o500)
    report_path = locked / "report.json"
    try:
        completed = run_cli(
            "match",
            "--data",
            str(data_path),
            "--sample",
            str(sample_path),
            "--top",
            "3",
            "--horizon",
            "10",
            "--out",
            str(report_path),
        )
    finally:
        os.chmod(locked, 0o700)

    assert completed.returncode == 1
    assert not report_path.exists(), "不可寫時不得留下半寫報表"
    assert not list(locked.glob("*")), "不可寫時不得留下任何暫存檔"


def test_match_reports_a_missing_sample_file_as_an_input_error(tmp_path):
    data_path, _ = prepare_match_inputs(tmp_path)

    completed = run_cli(
        "match",
        "--data",
        str(data_path),
        "--sample",
        str(tmp_path / "no-sample.csv"),
        "--top",
        "3",
        "--horizon",
        "10",
        "--out",
        str(tmp_path / "report.json"),
    )

    assert completed.returncode == 2
    assert "找不到檔案" in completed.stderr


# ---- AC-028：monitor 子命令 -------------------------------------------------

MONITOR_SPEC_PAYLOAD = {
    "pattern_id": "range_fakeout_reversion",
    "range_bars_min": 5,
    "range_bars_max": 20,
    "band_atr_multiple_max": 3.0,
    "atr_period": 14,
    "breakdown_bars_max": 2,
    "breakdown_depth_band_min": 0.2,
    "breakdown_depth_band_max": 1.5,
    "recovery_bars_max": 5,
    "recovery_target": "range_mean",
}


def write_monitor_config(
    tmp_path: Path,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    extra: dict | None = None,
) -> Path:
    payload = {
        "poll_interval_seconds": 1,
        "events_path": str(tmp_path / "events.jsonl"),
        "cache_dir": str(tmp_path / "ohlcv"),
        "pattern_id": "range_fakeout_reversion",
        "pattern_spec": MONITOR_SPEC_PAYLOAD,
        "horizon": 3,
        "instruments": [{"symbol": symbol, "interval": interval}],
    }
    if extra:
        payload.update(extra)
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_cache(tmp_path: Path, *, symbol="BTCUSDT", interval="1h", total=80) -> Path:
    frame = build_series_frame(total=total, offset=10)
    return write_csv(tmp_path / "ohlcv" / f"{symbol}_{interval}.csv", frame)


def test_monitor_once_prints_a_summary_and_exits_zero(tmp_path):
    write_cache(tmp_path)
    config_path = write_monitor_config(tmp_path)

    completed = run_cli("monitor", "--config", str(config_path), "--once")

    assert completed.returncode == 0, completed.stderr
    assert "[ALERT] BTCUSDT 1h range_fakeout_reversion" in completed.stdout
    assert "[MONITOR] processed=1 alerted=1 skipped=0 warnings=0" in completed.stdout
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 1
    payload = json.loads(events[0])
    assert payload["symbol"] == "BTCUSDT"
    assert payload["interval"] == "1h"


def test_monitor_exits_two_on_a_config_error(tmp_path):
    write_cache(tmp_path)
    config_path = write_monitor_config(tmp_path, extra={"unexpected": 1})

    completed = run_cli("monitor", "--config", str(config_path), "--once")

    assert completed.returncode == 2
    assert "unexpected" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_monitor_exits_one_when_the_source_is_unavailable(tmp_path):
    config_path = write_monitor_config(tmp_path)  # 刻意不建立快取檔

    completed = run_cli("monitor", "--config", str(config_path), "--once")

    assert completed.returncode == 1
    assert "BTCUSDT_1h.csv" in completed.stderr, "訊息必須指出缺少的快取檔"
    assert "Traceback" not in completed.stderr
    assert "[MONITOR] processed=0" in completed.stdout


def test_monitor_resident_mode_stops_gracefully_on_sigint(tmp_path):
    write_cache(tmp_path)
    config_path = write_monitor_config(tmp_path)
    process = subprocess.Popen(
        [str(PYTHON), "-m", "ediaad", "monitor", "--config", str(config_path)],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # 輪詢間隔 1 秒；等 2.5 秒確保至少完成 2 輪，才能驗證跨輪去重。
        time.sleep(2.5)
        assert process.poll() is None, "常駐模式不應該自己結束"
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()

    assert process.returncode == 0, stderr
    assert "Traceback" not in stderr
    assert "[STOP]" in stderr

    alert_lines = [line for line in stdout.splitlines() if line.startswith("[ALERT]")]
    assert len(alert_lines) >= 1, stdout
    assert all(
        line.startswith("[ALERT] BTCUSDT 1h range_fakeout_reversion") for line in alert_lines
    )
    # 快取檔不變 → 每輪偵測到同一個事件；跨輪去重必須只輸出一次。
    assert len(alert_lines) == 1, f"同一事件不得重複告警：{alert_lines}"
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 1, f"同一事件不得重複寫入事件檔：{events}"
    assert "[ALERT]" in stdout


# ---- AC-029：10,000 根、視窗 60、top 20 的效能門檻與行為一致性 ----------------


def test_match_at_ac_029_scale_meets_the_time_budget(tmp_path):
    """AC-029 的刺激條件：10,000 根、視窗 60、top 20，必須在 60 秒內完成。"""
    sample_path = prepare_match_inputs(
        tmp_path, total=200, offset=50, range_bars=60, name="-w60"
    )[1]
    big_frame = build_series_frame(total=10_000, offset=50, range_bars=60)
    big_data = write_csv(tmp_path / "big-w60.csv", big_frame)
    report_path = tmp_path / "big-w60.json"

    started = time.perf_counter()
    completed = run_cli(
        "match",
        "--data",
        str(big_data),
        "--sample",
        str(sample_path),
        "--top",
        "20",
        "--horizon",
        "10",
        "--out",
        str(report_path),
    )
    elapsed = time.perf_counter() - started

    assert completed.returncode == 0, completed.stderr
    assert elapsed < 60.0, f"10,000 根、視窗 60、top 20 耗時 {elapsed:.2f} 秒，超過 60 秒門檻"

    report = read_report(report_path)
    assert set(report) == REPORT_KEYS
    assert report["params"]["top"] == 20
    assert report["params"]["horizon"] == 10

    matches = report["matches"]
    assert len(matches) == 20, f"10,000 根足以容納 20 個互不高度重疊的命中：{len(matches)}"
    scores = [match["score"] for match in matches]
    assert all(0.0 <= score <= 1.0 for score in scores), scores
    assert scores == sorted(scores, reverse=True), "命中必須依分數由高到低排序"

    # 每個命中都是完整的視窗（60 根），且任兩者重疊比例不得超過 0.5。
    for match in matches:
        assert match["end_index"] - match["start_index"] + 1 == 60
    for left, right in itertools.combinations(matches, 2):
        span = (
            min(left["end_index"], right["end_index"])
            - max(left["start_index"], right["start_index"])
            + 1
        )
        overlap = max(0, span) / 60
        assert overlap <= 0.5 + 1e-9, f"{left} 與 {right} 重疊 {overlap:.3f} > 0.5"

    # 植入的視窗必須是第一名，且不受序列長度影響。
    assert matches[0]["start_index"] == 50
    assert matches[0]["score"] == pytest.approx(1.0)

    print(f"[AC-029] 10,000 根、視窗 60、top 20 耗時 {elapsed:.2f} 秒")


def test_match_behaves_identically_on_a_larger_series(tmp_path):
    """top 1 時，同一份樣本在 200 根與 10,000 根上的報表必須逐欄相同。

    這是 AC-029「結果與小資料集的行為一致」的強形式：命中索引、分數與 outlook
    統計都不因序列變長而改變（分數為 1.0 的精確命中不受候選池正規化影響）。
    """
    small_data, sample_path = prepare_match_inputs(tmp_path, total=200, offset=50)
    big_frame = build_series_frame(total=10_000, offset=50)
    big_data = write_csv(tmp_path / "big.csv", big_frame)
    small_report_path = tmp_path / "small.json"
    big_report_path = tmp_path / "big.json"

    for data_path, out_path in ((small_data, small_report_path), (big_data, big_report_path)):
        completed = run_cli(
            "match",
            "--data",
            str(data_path),
            "--sample",
            str(sample_path),
            "--top",
            "1",
            "--horizon",
            "10",
            "--out",
            str(out_path),
        )
        assert completed.returncode == 0, completed.stderr

    small_report = read_report(small_report_path)
    big_report = read_report(big_report_path)
    assert big_report["matches"] == small_report["matches"]
    assert big_report["outlook"] == small_report["outlook"]
    assert big_report["sample"] == small_report["sample"]
    assert big_report["matches"][0]["start_index"] == 50
    assert big_report["matches"][0]["score"] == pytest.approx(1.0)
    assert big_report["outlook"]["samples"] > 0


# ---- SPEC 第 5 節「錯誤分層」與來源轉接器的例外型別 ---------------------------


def test_local_cache_fetch_raises_source_error_when_the_cache_is_missing(tmp_path):
    """來源轉接器缺檔時必須是 `SourceError`（→ exit 1），不是設定／格式錯誤。"""
    fetch = _local_cache_fetch(str(tmp_path / "empty-cache"))

    with pytest.raises(SourceError) as excinfo:
        fetch("BTCUSDT", "1h")
    assert "BTCUSDT_1h.csv" in str(excinfo.value)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(DataFormatError("壞資料"), 2, id="DataFormatError→2"),
        pytest.param(ConfigError("壞設定"), 2, id="ConfigError→2"),
        pytest.param(SourceError("來源失敗"), 1, id="SourceError→1"),
    ],
)
def test_main_maps_errors_to_the_documented_exit_codes(
    tmp_path, monkeypatch, error, expected
):
    """`cli.main` 的錯誤分層對應表（以 stub 觸發，不依賴 warning 計數路徑）。"""
    from ediaad import cli

    def boom(_args):  # pragma: no cover - 只作為例外來源
        raise error

    monkeypatch.setattr(cli, "_run_monitor", boom)

    code = cli.main(["monitor", "--config", str(tmp_path / "watchlist.json")])

    assert code == expected


def test_run_forever_honours_a_caller_supplied_alert_state(tmp_path):
    """`_run_monitor` 會把 state 傳進 `run_forever`；呼叫端既有的去重狀態必須被尊重。

    TASK-010 只覆蓋 `run_once(state=...)`；這裡補上常駐迴圈這一層，否則「忽略傳入
    state、每輪重建」的缺陷不會被任何測試察覺。
    """
    from ediaad import monitor

    write_cache(tmp_path)
    config_path = write_monitor_config(tmp_path)
    watchlist = monitor.load_config(config_path)
    fetch = _local_cache_fetch(watchlist.cache_dir)

    emitted: list[dict] = []
    state = monitor.AlertState()

    monitor.run_once(
        watchlist, fetch, lambda line, payload: emitted.append(payload), lambda m: None,
        state=state,
    )
    assert len(emitted) == 1, "第一輪應發出唯一一次告警"

    rounds = {"count": 0}

    def stop() -> bool:
        rounds["count"] += 1
        return rounds["count"] > 3

    monitor.run_forever(
        watchlist,
        fetch,
        lambda line, payload: emitted.append(payload),
        lambda m: None,
        state=state,
        sleep=lambda seconds: None,
        should_stop=stop,
    )

    assert rounds["count"] >= 2, "至少應跑過多輪才算驗證跨輪去重"
    assert len(emitted) == 1, f"傳入的 state 已被去重，不應重複告警：{emitted}"
