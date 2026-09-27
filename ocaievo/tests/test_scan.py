"""`ediaad.scan` 的公開契約測試（TASK-005）。

觀察邊界：只呼叫 `ediaad.scan.scan_similar`，觀察回傳 `ScanMatch` 清單的長度、
`start_index`／`end_index`／`score` 與時間欄位，以及 `ConfigError` 的型別與訊息；
不檢視貪婪迴圈或內部快取。

**夾具設計**：序列長度 100、視窗 20。把一段 10 根週期圖樣 `R` 重複 4 次鋪在
`[60, 100)`，因此起始索引 60、70、80 三個視窗**完全相同**（分數 1.0），且兩兩
間距為 10 → 重疊恰好 `(20-10)/20 = 50%`；起始索引 68 與 60 的間距為 8 →
重疊 `60%`。
"""

from __future__ import annotations

import pandas as pd
import pytest

from ediaad.errors import ConfigError
from ediaad.features import extract, extract_matrix
from ediaad.scan import ScanMatch, scan_similar
from ediaad.similarity import rank

WINDOW = 20
SERIES_LENGTH = 100
R_CLOSE = [0, 2, 4, 3, 1, -1, 0, 2, 3, 1]
PATTERN_START = 60
REPEAT_UNTIL = 100


def build_series(length: int = SERIES_LENGTH) -> pd.DataFrame:
    """確定性合成序列；`[60, 100)` 為 10 根週期圖樣的四次重複。"""
    times = pd.date_range("2024-01-01T00:00:00Z", periods=length, freq="1h", tz="UTC")
    rows = []
    for index in range(length):
        if PATTERN_START <= index < REPEAT_UNTIL:
            close = 100.0 + R_CLOSE[(index - PATTERN_START) % len(R_CLOSE)]
            volume = 10.0 + (index - PATTERN_START) % len(R_CLOSE)
        else:
            close = 50.0 + index * 0.1
            volume = 5.0
        rows.append((times[index], close - 0.2, close + 0.5, close - 0.5, close, volume))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def build_sample(series: pd.DataFrame) -> pd.DataFrame:
    return series.iloc[PATTERN_START : PATTERN_START + WINDOW].reset_index(drop=True)


def overlap_ratio(first: ScanMatch, second: ScanMatch, window: int = WINDOW) -> float:
    """規格第 5.3 節的重疊比例公式（含頭尾的閉區間）。"""
    return max(
        0, min(first.end_index, second.end_index) - max(first.start_index, second.start_index) + 1
    ) / window


# ---- AC-010：結果寬度、筆數上限、重疊抑制與 50% 邊界 ------------------------


def test_results_have_window_width_and_matching_time_bounds():
    series = build_series()

    results = scan_similar(series, build_sample(series), WINDOW, top=5)

    assert results
    for match in results:
        assert match.end_index == match.start_index + WINDOW - 1
        assert match.time_start == series["time"].iloc[match.start_index]
        assert match.time_end == series["time"].iloc[match.end_index]


def test_top_limits_the_number_of_results():
    series = build_series()
    sample = build_sample(series)

    assert len(scan_similar(series, sample, WINDOW, top=1)) == 1
    assert len(scan_similar(series, sample, WINDOW, top=3)) <= 3


def test_top_larger_than_candidates_does_not_pad_with_empty_values():
    series = build_series()
    sample = build_sample(series)

    results = scan_similar(series, sample, WINDOW, top=1000)

    candidates = len(range(0, SERIES_LENGTH - WINDOW + 1, 1))
    assert len(results) <= candidates
    assert all(match.score > 0 for match in results)


def test_no_two_results_overlap_more_than_the_threshold():
    series = build_series()

    results = scan_similar(series, build_sample(series), WINDOW, top=10)

    for index, first in enumerate(results):
        for second in results[index + 1 :]:
            assert overlap_ratio(first, second) <= 0.5


def test_exactly_fifty_percent_overlap_is_kept():
    """嚴格大於門檻才丟棄：間距 10（重疊 50%）的兩段必須都保留。"""
    series = build_series()

    results = scan_similar(series, build_sample(series), WINDOW, top=10)
    starts = {match.start_index for match in results}

    assert {60, 70, 80} <= starts
    by_start = {match.start_index: match for match in results}
    assert overlap_ratio(by_start[60], by_start[70]) == pytest.approx(0.5)
    assert overlap_ratio(by_start[70], by_start[80]) == pytest.approx(0.5)


def test_sixty_percent_overlap_keeps_only_the_higher_scoring_match():
    """起始 68 與 60 重疊 60%：68 在完整排名中名列前茅，但必須被抑制。"""
    series = build_series()
    sample = build_sample(series)

    results = scan_similar(series, sample, WINDOW, top=10)
    starts = {match.start_index for match in results}

    # 反事實：若不抑制，68 確實在會被接受的名次內（否則「被抑制」的說法不成立）
    full_ranking = [match.index for match in rank(extract(sample), extract_matrix(series, WINDOW, 1))]
    assert 68 in full_ranking[:10]

    assert 60 in starts
    assert 68 not in starts


def test_results_are_sorted_by_score_descending():
    series = build_series()

    scores = [match.score for match in scan_similar(series, build_sample(series), WINDOW, top=10)]

    assert scores == sorted(scores, reverse=True)


def test_step_restricts_candidate_starts_to_multiples_of_step():
    series = build_series()

    results = scan_similar(series, build_sample(series), WINDOW, top=5, step=10)

    assert results
    assert all(match.start_index % 10 == 0 for match in results)
    assert {60, 70, 80} <= {match.start_index for match in results}


def test_zero_overlap_threshold_allows_only_disjoint_matches():
    series = build_series()

    results = scan_similar(series, build_sample(series), WINDOW, top=10, overlap=0.0)

    for index, first in enumerate(results):
        for second in results[index + 1 :]:
            assert overlap_ratio(first, second) == 0.0


# ---- AC-011：四類不合法參數的 ConfigError -----------------------------------


def test_rejects_sample_whose_length_is_not_window():
    series = build_series()
    too_short_sample = build_sample(series).iloc[: WINDOW - 5]

    with pytest.raises(ConfigError, match="範例長度"):
        scan_similar(series, too_short_sample, WINDOW, top=3)


def test_rejects_series_shorter_than_window():
    short_series = build_series(length=WINDOW - 5)
    sample = build_sample(build_series())

    with pytest.raises(ConfigError, match="短於"):
        scan_similar(short_series, sample, WINDOW, top=3)


def test_rejects_top_below_one():
    series = build_series()

    with pytest.raises(ConfigError, match="top"):
        scan_similar(series, build_sample(series), WINDOW, top=0)


def test_rejects_step_below_one():
    series = build_series()

    with pytest.raises(ConfigError, match="step"):
        scan_similar(series, build_sample(series), WINDOW, top=3, step=0)


@pytest.mark.parametrize("bad_overlap", [-0.1, 1.0, 1.5])
def test_rejects_overlap_outside_zero_inclusive_one_exclusive(bad_overlap):
    series = build_series()

    with pytest.raises(ConfigError, match="overlap"):
        scan_similar(series, build_sample(series), WINDOW, top=3, overlap=bad_overlap)


def test_rejects_series_without_time_column():
    series = build_series().drop(columns=["time"])
    sample = build_sample(build_series())

    with pytest.raises(ConfigError, match="time"):
        scan_similar(series, sample, WINDOW, top=3)


def test_rejects_non_positive_window():
    series = build_series()

    with pytest.raises(ConfigError, match="window"):
        scan_similar(series, build_sample(series), 0, top=3)
