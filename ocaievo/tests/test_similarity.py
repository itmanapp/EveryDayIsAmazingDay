"""`ediaad.similarity` 的公開契約測試（TASK-004）。

觀察邊界：只呼叫 `ediaad.similarity.rank`，並讀取 `Match`、`DEFAULT_WEIGHTS` 與
`ediaad.features.FEATURE_NAMES`；不檢視私有輔助函式（例如正規化或距離的內部步驟）。

**oracle 的來源**：分數與距離的期望值以規格第 5.2 節的公式在測試中**獨立實作一次**
（獨立的候選池統計量與 L1 距離計算），不是呼叫待測的 `rank`。
所有測試離線可跑，資料為確定的合成特徵向量。
"""

from __future__ import annotations

import numpy as np
import pytest

from ediaad.errors import ConfigError
from ediaad.features import FEATURE_NAMES
from ediaad.similarity import DEFAULT_WEIGHTS, Match, rank

# 與範例完全相同的一列，用來驗證「完全相同 → 分數 1.0、排名第 1」
SAMPLE = np.array(
    [0.10, 0.02, 0.50, 0.20, 0.20, 0.60, 0.10, 0.30, 1.50, 0.40],
    dtype=np.float64,
)

# 索引 2 與索引 4 都與 SAMPLE 完全相同（用來驗證同分時以索引升冪）
POOL = np.array(
    [
        [0.30, 0.05, 0.10, 0.60, 0.60, 0.20, 0.50, -0.20, 0.50, 0.90],
        [0.20, 0.01, 0.90, 0.10, 0.10, 0.90, 0.05, 0.80, 2.50, 0.10],
        [0.10, 0.02, 0.50, 0.20, 0.20, 0.60, 0.10, 0.30, 1.50, 0.40],
        [0.12, 0.021, 0.49, 0.21, 0.19, 0.61, 0.11, 0.29, 1.48, 0.41],
        [0.10, 0.02, 0.50, 0.20, 0.20, 0.60, 0.10, 0.30, 1.50, 0.40],
        [0.90, 0.10, 0.05, 0.95, 0.95, 0.05, 0.90, -0.90, 0.20, 1.00],
    ],
    dtype=np.float64,
)


def robust_normalize(values: np.ndarray, pool: np.ndarray) -> np.ndarray:
    """規格第 5.2 節的穩健正規化，獨立實作（不使用待測模組）。"""
    median = np.median(pool, axis=0)
    q75 = np.percentile(pool, 75, axis=0)
    q25 = np.percentile(pool, 25, axis=0)
    iqr = q75 - q25
    normalized = np.zeros_like(np.asarray(values, dtype=np.float64))
    nonzero = iqr != 0
    normalized[nonzero] = (
        np.asarray(values, dtype=np.float64)[nonzero] - median[nonzero]
    ) / iqr[nonzero]
    return normalized


def weighted_l1_distance(
    sample: np.ndarray, candidate: np.ndarray, pool: np.ndarray, weights: np.ndarray
) -> float:
    """規格第 5.2 節的加權 L1 距離，獨立實作（不使用待測模組）。"""
    z_sample = robust_normalize(sample, pool)
    z_candidate = robust_normalize(candidate, pool)
    return float(np.sum(weights * np.abs(z_sample - z_candidate)) / np.sum(weights))


# ---- AC-008：完全相同者第 1、分數值域與同分排序 ------------------------------


def test_default_weights_match_feature_count():
    assert len(DEFAULT_WEIGHTS) == len(FEATURE_NAMES)
    assert all(weight > 0 for weight in DEFAULT_WEIGHTS)


def test_rank_returns_match_objects_in_score_order():
    matches = rank(SAMPLE, POOL)

    assert len(matches) == len(POOL)
    assert all(isinstance(match, Match) for match in matches)
    for match in matches:
        assert isinstance(match.index, int)
        assert 0 <= match.index < len(POOL)


def test_identical_candidates_rank_first_with_score_one_and_zero_distance():
    matches = rank(SAMPLE, POOL)

    top = matches[0]
    assert top.index == 2
    assert top.score == pytest.approx(1.0, abs=1e-12)
    assert top.feature_distance == pytest.approx(0.0, abs=1e-12)


def test_all_scores_are_within_zero_exclusive_and_one_inclusive():
    scores = np.array([match.score for match in rank(SAMPLE, POOL)])

    assert (scores > 0.0).all()
    assert (scores <= 1.0).all()


def test_ties_are_ordered_by_ascending_index():
    matches = rank(SAMPLE, POOL)

    identical = [match for match in matches if match.feature_distance < 1e-12]
    assert [match.index for match in identical] == [2, 4]
    assert [match.index for match in matches[:2]] == [2, 4]


def test_distances_and_scores_match_independently_implemented_formula():
    weights = np.asarray(DEFAULT_WEIGHTS, dtype=np.float64)

    matches = {match.index: match for match in rank(SAMPLE, POOL)}

    for index in range(len(POOL)):
        expected_distance = weighted_l1_distance(SAMPLE, POOL[index], POOL, weights)
        expected_score = 1.0 / (1.0 + expected_distance)
        assert matches[index].feature_distance == pytest.approx(
            expected_distance, abs=1e-12
        ), index
        assert matches[index].score == pytest.approx(expected_score, abs=1e-12), index


def test_ranking_is_sorted_by_score_descending():
    scores = [match.score for match in rank(SAMPLE, POOL)]

    assert scores == sorted(scores, reverse=True)


# ---- AC-009：權重契約（長度、負值、總和為 0）與尺度無關性 --------------------


def test_rank_rejects_weights_with_wrong_length():
    bad_weights = [1.0] * (len(FEATURE_NAMES) - 1)

    with pytest.raises(ConfigError) as error:
        rank(SAMPLE, POOL, bad_weights)

    assert "權重" in str(error.value)


def test_rank_rejects_negative_weights():
    bad_weights = list(DEFAULT_WEIGHTS)
    bad_weights[3] = -0.5

    with pytest.raises(ConfigError) as error:
        rank(SAMPLE, POOL, bad_weights)

    assert "權重" in str(error.value)


def test_rank_rejects_zero_sum_weights():
    bad_weights = [0.0] * len(FEATURE_NAMES)

    with pytest.raises(ConfigError) as error:
        rank(SAMPLE, POOL, bad_weights)

    assert "權重" in str(error.value)


def test_weight_scale_does_not_change_order_or_scores():
    base = rank(SAMPLE, POOL, DEFAULT_WEIGHTS)
    weights = np.asarray(DEFAULT_WEIGHTS, dtype=np.float64)

    scaled = rank(SAMPLE, POOL, weights * 2.0)

    assert [match.index for match in scaled] == [match.index for match in base]
    for scaled_match, base_match in zip(scaled, base):
        assert scaled_match.score == pytest.approx(base_match.score, abs=1e-12)
        assert scaled_match.feature_distance == pytest.approx(
            base_match.feature_distance, abs=1e-12
        )


# 專為「權重真的有作用」設計的候選池：每一列只在單一維度上偏離範例，
# 因此把該維度加重時，名次必然改變（原 POOL 各列在多維同時偏離，權重不具辨識力）。
DEVIATION_POOL = np.vstack(
    [
        SAMPLE + np.array([0.10, 0, 0, 0, 0, 0, 0, 0, 0.00, 0]),
        SAMPLE + np.array([0.00, 0, 0, 0, 0, 0, 0, 0, 0.60, 0]),
        SAMPLE,
        SAMPLE + np.array([0.20, 0, 0, 0, 0, 0, 0, 0, 0.00, 0]),
        SAMPLE + np.array([0.00, 0, 0, 0, 0, 0, 0, 0, 0.30, 0]),
    ]
)


def test_default_weights_rank_the_smaller_normalized_deviation_ahead():
    order = [match.index for match in rank(SAMPLE, DEVIATION_POOL)]

    assert order[0] == 2  # 與範例完全相同，永遠第 1
    # 預設權重下，第 1 列（第 9 維偏離 0.60）的整體距離小於第 3 列（第 1 維偏離 0.20）
    assert order.index(1) < order.index(3)


def test_upweighting_a_dimension_changes_the_ranking():
    """權重不是裝飾品：加重第 9 維後，在該維偏離大的第 1 列會被往後排。"""
    volume_heavy = [1.0] * len(FEATURE_NAMES)
    volume_heavy[8] = 10.0

    order = [match.index for match in rank(SAMPLE, DEVIATION_POOL, volume_heavy)]

    assert order[0] == 2  # 距離 0 的候選任何權重都排第 1
    assert order.index(3) < order.index(1)
