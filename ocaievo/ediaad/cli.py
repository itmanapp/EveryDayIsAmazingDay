"""ediaad 命令列介面。

只做參數解析、呼叫既有公開函式與錯誤轉譯，**不重複實作任何核心邏輯**
（SPEC 第 5 節；報告第 3.1 節 F14）。

exit code 語意：

| code | 意義 |
| --- | --- |
| 0 | 成功 |
| 1 | 執行期失敗（來源失敗、輸出檔不可寫） |
| 2 | 輸入或設定錯誤（含參數不合法、租約或設定檔損毀、授權已過期／被撤銷） |

`serve` 只做參數轉譯，服務本體（含啟動時的離線授權驗證與功能分級）一律交給
`launcher.serve_main`；`license` 三個子命令分別對應 `license.py` 的 `activate`／
`renew`／`lease_status`，**不重複實作任何授權邏輯**。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .data import load_csv
from .errors import ConfigError, DataFormatError, EdiaadError, SourceError
from .paths import lease_path
from .license import (
    HTTP_CLIENT,
    RENEW_TRIGGERS,
    activate,
    lease_status,
    public_key_from_env,
    load_lease,
    machine_fingerprint,
    renew,
)
from .markets.custom import CsvSource
from .match import (
    DEFAULT_HORIZON,
    DEFAULT_OVERLAP,
    DEFAULT_STEP,
    DEFAULT_TOP,
    run_match,
)
from .monitor import (
    AlertState,
    append_event,
    load_config,
    run_forever,
    run_once,
)

__all__ = ["build_parser", "main", "EXIT_OK", "EXIT_RUNTIME_ERROR", "EXIT_INPUT_ERROR"]

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_INPUT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    """建立命令列解析器。"""
    parser = argparse.ArgumentParser(
        prog="ediaad",
        description="市場規律偵測與監控提醒（完全在本機執行）。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    match = subparsers.add_parser(
        "match", help="在歷史序列中找出與範例相似的片段並統計其後續走勢"
    )
    match.add_argument("--data", required=True, help="歷史 OHLC CSV")
    match.add_argument("--sample", required=True, help="範例 OHLC CSV（長度即視窗）")
    match.add_argument(
        "--top", type=int, default=DEFAULT_TOP, help=f"最多回傳幾筆（預設 {DEFAULT_TOP}）"
    )
    match.add_argument(
        "--horizon",
        type=int,
        default=DEFAULT_HORIZON,
        help=f"後續走勢根數（預設 {DEFAULT_HORIZON}）",
    )
    match.add_argument(
        "--step", type=int, default=DEFAULT_STEP, help=f"滑動步長（預設 {DEFAULT_STEP}）"
    )
    match.add_argument(
        "--overlap",
        type=float,
        default=DEFAULT_OVERLAP,
        help=f"重疊抑制門檻（預設 {DEFAULT_OVERLAP}）",
    )
    match.add_argument("--out", required=True, help="JSON 報表輸出路徑")

    serve = subparsers.add_parser(
        "serve", help="啟動本機網頁服務（前景執行，Ctrl-C 結束）"
    )
    serve.add_argument(
        "--port",
        type=int,
        default=_default_port(),
        help="服務埠（預設 EDIAAD_PORT 或 8787；只 bind 127.0.0.1）",
    )
    serve.add_argument(
        "--home",
        default=os.environ.get("EDIAAD_HOME"),
        help="資料根目錄（預設 EDIAAD_HOME 或 ~/.local/share/ediaad）",
    )

    license_parser = subparsers.add_parser(
        "license", help="授權狀態、啟用與續期（需要時才連線）"
    )
    license_sub = license_parser.add_subparsers(dest="license_command", required=True)
    license_sub.add_parser("status", help="顯示授權狀態（唯讀，不發出任何網路請求）")
    license_activate = license_sub.add_parser(
        "activate", help="以密鑰啟用（需要 EDIAAD_LICENSE_URL）"
    )
    license_activate.add_argument(
        "--key", required=True, help="授權密鑰（以參數傳入，不從 stdin 讀取以免進入 shell 歷史）"
    )
    license_renew = license_sub.add_parser("renew", help="線上續期（需要 EDIAAD_LICENSE_URL）")
    license_renew.add_argument(
        "--trigger",
        choices=list(RENEW_TRIGGERS),
        default="manual",
        help="續期觸發來源（預設 manual）",
    )

    monitor = subparsers.add_parser("monitor", help="輪詢監控清單並在命中時提醒")
    monitor.add_argument("--config", required=True, help="監控設定 JSON")
    monitor.add_argument("--once", action="store_true", help="只執行一輪")

    return parser


def _default_port() -> int:
    """`--port` 的預設值：`EDIAAD_PORT`（無法解讀時先回 8787，由 `serve` 報成設定錯誤）。"""
    try:
        return int((os.environ.get("EDIAAD_PORT") or "").strip() or 8787)
    except ValueError:
        return 8787


def _require_port_env() -> None:
    """`EDIAAD_PORT` 有設但解讀不了時，明確報成設定錯誤（exit 2）而不是安靜忽略。"""
    raw = (os.environ.get("EDIAAD_PORT") or "").strip()
    if raw:
        try:
            int(raw)
        except ValueError as error:
            raise ConfigError(f"EDIAAD_PORT 必須是整數，收到 {raw!r}") from error


def _license_url() -> str:
    return (os.environ.get("EDIAAD_LICENSE_URL") or "").strip()


def _require_license_url() -> str:
    url = _license_url()
    if not url:
        raise ConfigError("尚未設定授權服務網址（環境變數 EDIAAD_LICENSE_URL）")
    return url


def _days_remaining(expires_at: str) -> float:
    from datetime import datetime, timezone

    expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return (expires - datetime.now(timezone.utc)).total_seconds() / 86400.0


def _run_serve(args: argparse.Namespace) -> int:
    """`serve`：只做參數轉譯，服務本體一律交給 `launcher.serve_main`（單一入口）。"""
    _require_port_env()
    from .launcher import serve_main

    argv = ["--serve", "--host", "127.0.0.1", "--port", str(args.port)]
    if args.home:
        argv += ["--home", str(args.home)]
    return serve_main(argv)


def _run_license_status(_args: argparse.Namespace) -> int:
    """唯讀：讀租約 + 判狀態，**不發出任何網路請求**。"""
    lease = load_lease(lease_path())
    status = lease_status(lease)
    if status.state == "unactivated":
        print(
            "錯誤：尚未啟用（找不到租約）；請執行 "
            "`python -m ediaad license activate --key <密鑰>`",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR
    if status.state in ("expired", "revoked"):
        print(f"錯誤：{status.message}", file=sys.stderr)
        print("提示：請至重新申請頁取得新密鑰", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(f"授權狀態：{status.message or '有效期內'}")
    print(f"密鑰：{lease.key_id}")
    print(f"到期日：{status.expires_at}")
    print(f"剩餘天數：{status.days_remaining:.1f}")
    print(f"功能：{'、'.join(lease.features)}")
    return EXIT_OK


def _run_license_activate(args: argparse.Namespace) -> int:
    url = _require_license_url()
    lease = activate(
        args.key.strip(),
        fingerprint=machine_fingerprint(),
        http=HTTP_CLIENT,
        url=url,
        public_key=public_key_from_env(),
    )
    print(f"已啟用：{lease.key_id}")
    print(f"到期日：{lease.expires_at}")
    print(f"功能：{'、'.join(lease.features)}")
    return EXIT_OK


def _run_license_renew(args: argparse.Namespace) -> int:
    url = _require_license_url()
    lease = load_lease(lease_path())
    if lease is None:
        raise ConfigError("尚未啟用：請先以 `python -m ediaad license activate --key <密鑰>` 啟用")
    refreshed = renew(
        lease,
        http=HTTP_CLIENT,
        url=url,
        trigger=args.trigger,
        public_key=public_key_from_env(),
    )
    print(f"已續期：{refreshed.key_id}")
    print(f"到期日：{refreshed.expires_at}（剩餘 {_days_remaining(refreshed.expires_at):.1f} 天）")
    return EXIT_OK


def _write_json_atomically(path: Path, payload: Any) -> None:
    """先寫暫存檔再 rename，避免留下半寫的報表。

    暫存檔與目標檔同目錄（同一檔案系統），因此 `os.replace` 是原子操作。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover - 清不掉也不能掩蓋原錯誤
                pass
        raise


def _run_match(args: argparse.Namespace) -> int:
    """讀兩個 CSV 後把整份流程交給 `match.run_match`（與 `POST /api/match` 同一份）。

    `horizon` 的下限由共用流程擋下（`ConfigError` → exit 2），因此這裡不再重複檢查。
    """
    series = load_csv(args.data)
    sample = load_csv(args.sample)
    report = run_match(
        series,
        sample,
        top=args.top,
        horizon=args.horizon,
        step=args.step,
        overlap=args.overlap,
    )

    out_path = Path(args.out)
    try:
        _write_json_atomically(out_path, report)
    except OSError as error:
        print(f"錯誤：無法寫入報表 {out_path}：{error}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    print(f"[MATCH] {len(report['matches'])} 筆命中，報表已寫入 {out_path}")
    return EXIT_OK


def _local_cache_fetch(cache_dir: str):
    """快取目錄的來源轉接：讀取 `<cache_dir>/<symbol>_<interval>.csv`。

    路徑慣例與解析一律交給 `markets.custom.CsvSource`（其內部用 `data.load_csv`），
    不在 CLI 另寫一套讀檔與解析（報告 F-001 的教訓：同一份資料只能有一條解析路徑）。
    缺少快取檔時 `CsvSource` 丟出 `SourceError` → exit 1。TASK-013 會把這裡換成
    「快取 → 交易所 → 過期快取」的完整來源鏈。
    """
    source = CsvSource(cache_dir)

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return source.fetch(symbol, interval)

    return fetch


def _run_monitor(args: argparse.Namespace) -> int:
    watchlist = load_config(args.config)  # ConfigError → exit 2（由 main 轉譯）

    state = AlertState()

    def emit(line: str, payload: dict[str, Any]) -> None:
        print(line)
        append_event(watchlist.events_path, payload)

    def warn(message: str) -> None:
        print(f"[WARN] {message}", file=sys.stderr)

    fetch = _local_cache_fetch(watchlist.cache_dir)

    if args.once:
        result = run_once(watchlist, fetch, emit, warn, state=state)
        print(
            f"[MONITOR] processed={result.processed} alerted={result.alerted} "
            f"skipped={result.skipped} warnings={result.warnings}"
        )
        # 完全沒有商品被評估、且有 warning → 這一輪整體失敗（例如來源不可用）。
        if result.processed == 0 and result.warnings > 0:
            return EXIT_RUNTIME_ERROR
        return EXIT_OK

    run_forever(watchlist, fetch, emit, warn, state=state)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """命令列入口；回傳 process exit code。

    錯誤分層（SPEC 第 5 節）：`DataFormatError`／`ConfigError` → 2；
    `SourceError` → 1；`KeyboardInterrupt`（使用者中止常駐監控）→ 0，且不印 traceback。
    其他例外不攔截，讓程式缺陷以 traceback 呈現。
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "match":
            return _run_match(args)
        if args.command == "monitor":
            return _run_monitor(args)
        if args.command == "serve":
            return _run_serve(args)
        if args.command == "license":
            if args.license_command == "status":
                return _run_license_status(args)
            if args.license_command == "activate":
                return _run_license_activate(args)
            if args.license_command == "renew":
                return _run_license_renew(args)
        return EXIT_INPUT_ERROR
    except (DataFormatError, ConfigError) as error:
        print(f"錯誤：{error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except SourceError as error:
        print(f"錯誤：{error}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except EdiaadError as error:
        print(f"錯誤：{error}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except KeyboardInterrupt:
        print("[STOP] 已收到中斷訊號", file=sys.stderr)
        return EXIT_OK
    except Exception as error:  # 未知例外：使用者看到的是一行訊息，除錯時可要求堆疊
        if os.environ.get("EDIAAD_DEBUG"):
            raise
        print(f"錯誤：{error.__class__.__name__}: {error}", file=sys.stderr)
        print("提示：設定 EDIAAD_DEBUG=1 可看到完整堆疊（回報問題時請附上）", file=sys.stderr)
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
