"""監控：設定、輪詢、提醒去重、錯誤隔離與提醒輸出。

**設計原則（SPEC 第 5 節原則 2）**：`run_once` 的所有外部效果都是參數——
`fetch`（取得序列）、`emit`（輸出提醒）、`warn`（輸出警告）、`state`（去重狀態）、
`sleep`／`should_stop`（節奏與中止）。因此監控邏輯**完全離線可測**，時間與資料都
可以控制。

**錯誤分層（原則 3）**：`run_once` 只攔截 `(EdiaadError, KeyError, IndexError)`——
前兩者是領域錯誤與來源轉接器回傳的畸形資料框架；**其他例外（程式錯誤）一律向上拋出**，
避免缺陷被 warning 掩蓋。

**F-003 的教訓**：「資料不足（無法評估）」與「評估後沒有命中」是兩件事。前者計入
`skipped` 並附上明確的「資料不足」warning，後者計入 `processed` 而 `alerted` 不變。

**提醒去重鍵** = `(商品, 週期, 規律 ID, 事件開始時間)`。用**時間**而非索引，因為不同
輪詢取得序列的長度可能不同（新 K 線陸續進來），索引會位移，時間不會（報告第 5.9 節）。
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import ConfigError, EdiaadError
from .markets.base import DEFAULT_SOURCE_ID, Instrument, get_source
from .outlook import forward_stats
from .patterns import (
    NAMED_PATTERNS,
    PatternEvent,
    PatternSpec,
    detect,
    from_json,
    to_json,
)

__all__ = [
    "Instrument",
    "Watchlist",
    "AlertState",
    "RunResult",
    "load_config",
    "save_config",
    "validate_config",
    "run_once",
    "run_forever",
    "format_alert",
    "append_event",
    "event_times",
]

_REQUIRED_CONFIG_KEYS: tuple[str, ...] = (
    "poll_interval_seconds",
    "events_path",
    "cache_dir",
    "pattern_id",
    "pattern_spec",
    "horizon",
    "instruments",
)

#: `symbol`／`interval` 必填；`source_id` 選填（未給時使用預設來源）。
_INSTRUMENT_REQUIRED_KEYS: tuple[str, ...] = ("symbol", "interval")
_INSTRUMENT_KEYS: tuple[str, ...] = ("symbol", "interval", "source_id")

#: 事件檔的九個欄位（報告第 3.1 節 F12）
EVENT_FIELDS: tuple[str, ...] = (
    "symbol",
    "interval",
    "pattern_id",
    "event_start_time",
    "event_end_time",
    "confidence",
    "detected_at",
    "history_up_probability",
    "history_samples",
)


@dataclass(frozen=True)
class Watchlist:
    """監控清單：輪詢節奏、輸出路徑、規律與要監控的商品。"""

    poll_interval_seconds: int
    events_path: str
    cache_dir: str
    pattern_id: str
    pattern_spec: PatternSpec | None
    horizon: int
    instruments: tuple[Instrument, ...]


@dataclass
class AlertState:
    """記憶體內提醒去重狀態（v0.2 限制：程式重啟後會再提醒一次；TASK-018 改為落地）。"""

    seen: set[Any] = field(default_factory=set)

    def should_alert(self, key: Any) -> bool:
        return key not in self.seen

    def mark_alerted(self, key: Any) -> None:
        self.seen.add(key)


@dataclass(frozen=True)
class RunResult:
    """單輪輪詢的結果計數。"""

    processed: int
    alerted: int
    skipped: int
    warnings: int


def load_config(path: str | Path) -> Watchlist:
    """讀入監控設定 JSON 並驗證，回傳 `Watchlist`。

    錯誤一律為 `ConfigError`，且訊息**指出出錯的鍵名或索引位置**（例如
    `instruments[1].interval`），讓使用者能直接修正設定檔。
    """
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigError(f"找不到設定檔：{config_path}") from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"設定檔不是合法 JSON（{config_path}）：{error}") from error

    return validate_config(payload)


def validate_config(payload: Any) -> Watchlist:
    """驗證一份監控設定的映射並轉成 `Watchlist`（`save_config` 與 `load_config` 共用）。

    錯誤一律為 `ConfigError`，訊息指出出錯的鍵名或索引位置。
    """
    if not isinstance(payload, Mapping):
        raise ConfigError(f"設定檔必須是 JSON 物件，收到 {type(payload).__name__}")

    missing = [key for key in _REQUIRED_CONFIG_KEYS if key not in payload]
    if missing:
        raise ConfigError(f"設定檔缺少鍵：{'、'.join(missing)}")
    unknown = sorted(set(payload) - set(_REQUIRED_CONFIG_KEYS))
    if unknown:
        raise ConfigError(f"設定檔含未知鍵：{'、'.join(unknown)}")

    poll_interval = payload["poll_interval_seconds"]
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, int) or poll_interval < 1:
        raise ConfigError(
            f"poll_interval_seconds 必須是 >= 1 的整數，收到 {poll_interval!r}"
        )

    horizon = payload["horizon"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ConfigError(f"horizon 必須是 >= 1 的整數，收到 {horizon!r}")

    for key in ("events_path", "cache_dir", "pattern_id"):
        value = payload[key]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{key} 必須是非空字串，收到 {value!r}")

    raw_instruments = payload["instruments"]
    if not isinstance(raw_instruments, Sequence) or isinstance(raw_instruments, (str, bytes)):
        raise ConfigError(f"instruments 必須是陣列，收到 {type(raw_instruments).__name__}")
    if len(raw_instruments) == 0:
        raise ConfigError("instruments 不得為空：至少要有一個要監控的商品")

    instruments: list[Instrument] = []
    for index, raw in enumerate(raw_instruments):
        if not isinstance(raw, Mapping):
            raise ConfigError(f"instruments[{index}] 必須是物件，收到 {type(raw).__name__}")
        extra = sorted(set(raw) - set(_INSTRUMENT_KEYS))
        if extra:
            raise ConfigError(f"instruments[{index}] 含未知鍵：{'、'.join(extra)}")
        for key in _INSTRUMENT_REQUIRED_KEYS:
            if key not in raw:
                raise ConfigError(f"instruments[{index}] 缺少鍵 {key}")
            if not isinstance(raw[key], str) or not raw[key].strip():
                raise ConfigError(f"instruments[{index}].{key} 必須是非空字串，收到 {raw[key]!r}")

        raw_source_id = raw.get("source_id", "")
        if not isinstance(raw_source_id, str):
            raise ConfigError(
                f"instruments[{index}].source_id 必須是字串，收到 {raw_source_id!r}"
            )
        source_id = raw_source_id.strip() or DEFAULT_SOURCE_ID
        try:
            source = get_source(source_id)
        except ConfigError as error:
            raise ConfigError(f"instruments[{index}].source_id：{error}") from error

        # 週期只問來源，不查全域清單（AC-030）；訊息同時指出來源與該來源的可用週期。
        if raw["interval"] not in source.supported_intervals:
            raise ConfigError(
                f"instruments[{index}].interval 不支援 {raw['interval']!r}"
                f"（來源 {source.id!r}），"
                f"可用週期：{list(source.supported_intervals)}"
            )

        instruments.append(
            Instrument(
                symbol=raw["symbol"], interval=raw["interval"], source_id=source.id
            )
        )

    pattern_spec: PatternSpec | None = None
    if payload["pattern_spec"] is not None:
        pattern_spec = from_json(payload["pattern_spec"])
        if pattern_spec.pattern_id != payload["pattern_id"]:
            raise ConfigError(
                "pattern_spec.pattern_id "
                f"（{pattern_spec.pattern_id!r}）必須與頂層 pattern_id"
                f"（{payload['pattern_id']!r}）一致"
            )

    return Watchlist(
        poll_interval_seconds=poll_interval,
        events_path=payload["events_path"],
        cache_dir=payload["cache_dir"],
        pattern_id=payload["pattern_id"],
        pattern_spec=pattern_spec,
        horizon=horizon,
        instruments=tuple(instruments),
    )


def event_times(
    event: PatternEvent,
    series: pd.DataFrame,
    *,
    start_attr: str = "range_start_index",
    end_attr: str = "recovery_index",
) -> tuple[Any, Any]:
    """由事件取得去重所需的時間鍵：`(事件開始時間, 事件結束時間)`。"""
    times = series["time"]
    return (
        times.iloc[int(getattr(event, start_attr))],
        times.iloc[int(getattr(event, end_attr))],
    )


def _default_clock() -> Any:
    return pd.Timestamp.now(tz="UTC")


def format_alert(
    *,
    symbol: str,
    interval: str,
    pattern_id: str,
    start_time: Any,
    end_time: Any,
    confidence: float,
    up_probability: float | None,
    samples: int,
) -> str:
    """產生欄位順序固定的單行提醒摘要（報告第 3.1 節 F12）。

    無歷史樣本時 `history_up_probability` 為 `None`，摘要以 `-` 呈現；`samples` 仍為 0。
    """
    up_text = "-" if up_probability is None else f"{float(up_probability):.4f}"
    return (
        f"[ALERT] {symbol} {interval} {pattern_id} "
        f"{pd.Timestamp(start_time).isoformat()}..{pd.Timestamp(end_time).isoformat()} "
        f"confidence={float(confidence):.4f} "
        f"history_up_prob={up_text} samples={int(samples)}"
    )


def save_config(path: str | Path, watchlist: Watchlist) -> Path:
    """把監控設定**原子**寫入 JSON（先驗證再寫暫存檔，最後 `os.replace`）。

    寫入前先以 `validate_config` 走一次同一套規則：不對的內容不該有機會落成檔案。
    """
    payload: dict[str, Any] = {
        "poll_interval_seconds": watchlist.poll_interval_seconds,
        "events_path": watchlist.events_path,
        "cache_dir": watchlist.cache_dir,
        "pattern_id": watchlist.pattern_id,
        "pattern_spec": (
            None
            if watchlist.pattern_spec is None
            else json.loads(to_json(watchlist.pattern_spec))
        ),
        "horizon": watchlist.horizon,
        "instruments": [
            {
                "symbol": instrument.symbol,
                "interval": instrument.interval,
                "source_id": instrument.source_id,
            }
            for instrument in watchlist.instruments
        ],
    }
    validate_config(payload)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)
    return target


def run_once(
    watchlist: Watchlist,
    fetch: Callable[[str, str], pd.DataFrame],
    emit: Callable[..., None],
    warn: Callable[[str], None],
    state: AlertState | None = None,
    sleep: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    now: Callable[[], Any] | None = None,
) -> RunResult:
    """執行單輪輪詢：逐商品取得序列 → 偵測 → 去重 → 發送提醒。

    回傳 `RunResult`：`processed` 為完成評估的商品數、`alerted` 為新提醒數、
    `skipped` 為因資料不足而未評估的商品數、`warnings` 為警告訊息數。
    """
    state = state if state is not None else AlertState()
    clock = now if now is not None else _default_clock
    spec = watchlist.pattern_spec
    if spec is None:
        spec = from_json(dict(NAMED_PATTERNS[watchlist.pattern_id]))

    processed = alerted = skipped = warnings = 0
    for instrument in watchlist.instruments:
        # 評估階段：取得資料、偵測、去重、統計。任何領域錯誤或來源回傳的畸形
        # 資料框架（KeyError／IndexError）都只記 warning 並繼續下一個商品；
        # 其他例外（程式缺陷）不在此攔截，會直接向上拋出。
        minimum_bars = spec.range_bars_min + 1
        try:
            series = fetch(instrument.symbol, instrument.interval)

            # F-003：「無法評估」與「評估後沒有命中」必須分開。長度不足時不呼叫
            # detect（那只會回傳空清單，兩者就無法區分），而是明確跳過並記錄原因。
            if len(series) < minimum_bars:
                warn(
                    f"{instrument.symbol} {instrument.interval}：資料不足"
                    f"（{len(series)} 根 < 需要的 {minimum_bars} 根），無法評估規律"
                )
                skipped += 1
                warnings += 1
                continue

            events = detect(series, spec)

            pending: list[tuple[tuple[Any, ...], str, dict[str, Any]]] = []
            for event in events:
                start_time, end_time = event_times(event, series)
                start_iso = pd.Timestamp(start_time).isoformat()
                key = (
                    instrument.symbol,
                    instrument.interval,
                    spec.pattern_id,
                    start_iso,
                )
                if not state.should_alert(key):
                    continue

                stats = forward_stats(
                    [event], series, watchlist.horizon, end_attr="recovery_index"
                )
                pending.append(
                    (
                        key,
                        format_alert(
                            symbol=instrument.symbol,
                            interval=instrument.interval,
                            pattern_id=spec.pattern_id,
                            start_time=start_time,
                            end_time=end_time,
                            confidence=event.confidence,
                            up_probability=stats.up_probability,
                            samples=stats.samples,
                        ),
                        {
                            "symbol": instrument.symbol,
                            "interval": instrument.interval,
                            "pattern_id": spec.pattern_id,
                            "event_start_time": start_iso,
                            "event_end_time": pd.Timestamp(end_time).isoformat(),
                            "confidence": float(event.confidence),
                            "detected_at": pd.Timestamp(clock()).isoformat(),
                            "history_up_probability": stats.up_probability,
                            "history_samples": stats.samples,
                        },
                    )
                )
        except (EdiaadError, KeyError, IndexError) as error:
            warn(
                f"{instrument.symbol} {instrument.interval}："
                f"取得或解析資料失敗（{type(error).__name__}）：{error}"
            )
            warnings += 1
            continue

        processed += 1
        for key, line, payload in pending:
            state.mark_alerted(key)
            emit(line, payload)
            alerted += 1

    return RunResult(
        processed=processed, alerted=alerted, skipped=skipped, warnings=warnings
    )


def run_forever(
    watchlist: Watchlist,
    fetch: Callable[[str, str], pd.DataFrame],
    emit: Callable[..., None],
    warn: Callable[[str], None],
    state: AlertState | None = None,
    sleep: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    now: Callable[[], Any] | None = None,
) -> None:
    """以注入的 `sleep`／`should_stop` 重複呼叫 `run_once`（最小迴圈）。

    不新增 SPEC 未定義的語意：每一輪就是一次 `run_once`，之後以
    `poll_interval_seconds` 呼叫 `sleep`；`should_stop()` 為真時結束。
    """
    sleeper = sleep if sleep is not None else time.sleep
    stopper = should_stop if should_stop is not None else (lambda: False)
    # 整個迴圈共用同一份去重狀態，否則每一輪都會重新提醒同一事件。
    shared_state = state if state is not None else AlertState()
    while not stopper():
        run_once(watchlist, fetch, emit, warn, state=shared_state, now=now)
        sleeper(watchlist.poll_interval_seconds)


def append_event(path: str | Path, event: Mapping[str, Any]) -> None:
    """以附加寫入把事件寫成 JSONL 的一行。

    **附加寫入、永不改寫既有行**：事件檔是累積的歷史紀錄，重新輪詢只會往後追加。
    缺少的父目錄會自動建立（預設路徑為 `.cache/events.jsonl`）。
    欄位鍵序固定並以 `sort_keys=True` 輸出，讓兩份檔案可以直接比對。
    """
    missing = [field for field in EVENT_FIELDS if field not in event]
    if missing:
        raise ConfigError(f"事件缺少欄位：{'、'.join(missing)}")

    event_path = Path(path)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(event), ensure_ascii=False, sort_keys=True)
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
