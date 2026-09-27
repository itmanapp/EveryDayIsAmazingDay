"""應用協調層：設定、資料庫、監控清單、來源 registry 與 Web 服務的生命週期。

本模組是 TASK-020 的骨架：把已經完成的模組接起來，並提供可被其他執行緒安全呼叫的
`stop()`（TASK-026 的優雅關閉會複用它；`serve` 子命令的完整接線在 TASK-036）。

**啟動不得因單一產物損毀而失敗**：設定檔或資料庫有問題時，`create()` 會記錄在
`problems` 並以可用的替代值繼續（設定用預設值、資料庫為 `None`），讓網頁能啟動並把
問題顯示給使用者——否則使用者沒有任何介面可以修它。SSE hub 是 TASK-021 的佔位。
"""

from __future__ import annotations

import inspect
import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import DEFAULT_SETTINGS, load_settings
from .license import LICENSE_PUBLIC_KEY
from .markets.catalog import Catalog, load_catalog
from .errors import EdiaadError
from .markets.base import DEFAULT_SOURCE_ID, Source, all_sources, get_source
from .monitor import AlertState, RunResult, Watchlist, load_config, run_once
from .paths import (
    catalog_path,
    db_path,
    home_root,
    lease_path as license_path,
    pid_path,
    revoked_path,
    settings_path,
    update_state_path,
    watchlist_path,
)
from .store import Store, open_store
from .update import check_update, http_get as update_http_get
from .web.sse_hub import SSEHub

__all__ = ["Application"]


def _utc_stamp() -> str:
    """UTC ISO 時間字串（狀態頁顯示用；不參與任何判斷，因此可用系統時鐘）。"""
    return datetime.now(timezone.utc).isoformat()


logger = logging.getLogger("ediaad.app")


@dataclass
class Application:
    """持有服務所需的全部狀態；`start()`／`stop()` 管理 Web 服務生命週期。"""

    home: Path
    settings_path: Path
    watchlist_path: Path
    db_path: Path
    pid_path: Path
    lease_path: Path
    revoked_path: Path
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    store: Store | None = None
    watchlist: Watchlist | None = None
    catalog: Catalog | None = None
    sources: tuple[Source, ...] = ()
    hub: SSEHub = field(default_factory=SSEHub)
    #: 已啟用的通知管道（空＝只有網頁推播；由 `enable_notifications()` 建立）。
    notifiers: tuple[Any, ...] = ()
    #: 最近一次更新檢查的結果（TASK-032；未檢查時為 `None`）。
    update_state: Any = None
    #: 更新 manifest 位址（由服務入口以 `EDIAAD_UPDATE_URL` 設定；空字串＝不檢查）。
    update_url: str = ""
    #: 更新快取位置（`<home>/update.json`）。
    update_cache_path: Path | None = None
    #: 更新檢查要用的 HTTP 客戶端（預設為標準庫；測試與服務可注入）。
    update_http: Any = None
    #: 更新檢查的 executor（預設由本物件建立單一 worker 的 pool；測試可注入）。
    update_executor: Any = None
    #: 驗租約用的公鑰（預設為內嵌的 `LICENSE_PUBLIC_KEY`；TASK-033 產生 Worker 金鑰後替換）。
    license_public_key: bytes = LICENSE_PUBLIC_KEY
    #: 啟用／續期要用的 HTTP 客戶端（預設為標準庫；測試與服務可注入）。
    license_http: Any = None
    #: 監控狀態（系統狀態頁的資料來源）：最後輪詢時間、最近一輪結果與逐商品狀態。
    last_poll_at: str | None = None
    last_result: RunResult | None = None
    instrument_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    monitor_error: str | None = None
    problems: dict[str, str] = field(default_factory=dict)
    shutdown_event: threading.Event = field(default_factory=threading.Event)
    _server: Any = None
    _thread: threading.Thread | None = None
    _monitor_thread: threading.Thread | None = None
    _monitor_stop: threading.Event = field(default_factory=threading.Event)
    _update_pool: Any = None
    _update_inflight: bool = False

    @property
    def version(self) -> str:
        return __version__

    @property
    def cache_dir(self) -> Path:
        """序列快取目錄：監控清單有設定時用它，否則為 `<home>/cache`。"""
        if self.watchlist is not None:
            return Path(self.watchlist.cache_dir)
        return self.home / "cache"

    def make_emit(self) -> Callable[[str, Mapping[str, Any]], None]:
        """回傳可注入 `monitor.run_once` 的 `emit`：輸出摘要並推入 SSE。

        這是「引擎 → 瀏覽器」的接縫：引擎的行為完全不變（`emit` 本來就是注入的），
        只是同一個回呼現在同時做兩件事。
        """

        def emit(line: str, payload: Mapping[str, Any]) -> None:
            if line:
                print(line)
            if self.store is not None:
                # 事件落地（AC-023 的跨重啟去重靠它；狀態頁的歷史也來自這裡）
                try:
                    self.store.record_event(payload)
                except EdiaadError as error:
                    logger.warning("事件無法寫入資料庫：%s", error)
            if not self.notifiers:
                # 尚未啟用通知：維持 TASK-021 的行為（只推播網頁管道）
                self.hub.publish(payload)
                return
            for notifier in self.notifiers:
                notifier.notify(payload)

        return emit

    def enable_notifications(
        self,
        *,
        platform: str | None = None,
        which: Any = None,
        runner: Any = None,
        env: Any = None,
        warn: Any = None,
    ) -> tuple[Any, ...]:
        """建立並啟用通知管道（網頁內提示 ＋ 瀏覽器原生 ＋ 服務端桌面）。

        **預設不啟用**：`create()` 只做網頁推播，避免測試或工具在使用者的桌面上彈出
        真實通知。服務啟動路徑（`launcher --serve`）會明確呼叫本方法。
        """
        from .notify import build_notifiers

        options: dict[str, Any] = {}
        if platform is not None:
            options["platform"] = platform
        if which is not None:
            options["which"] = which
        if runner is not None:
            options["runner"] = runner
        if env is not None:
            options["env"] = env
        if warn is not None:
            options["warn"] = warn
        self.notifiers = tuple(build_notifiers(self.hub, **options))
        return self.notifiers

    @classmethod
    def create(cls, home: str | Path | None = None) -> "Application":
        """由 `$EDIAAD_HOME` 建立應用；損毀的產物只記錄問題，不阻止啟動。"""
        root = home_root(home)
        root.mkdir(parents=True, exist_ok=True)

        application = cls(
            home=root,
            settings_path=settings_path(root),
            watchlist_path=watchlist_path(root),
            db_path=db_path(root),
            pid_path=pid_path(root),
            lease_path=license_path(root),
            revoked_path=revoked_path(root),
            update_cache_path=update_state_path(root),
            sources=tuple(all_sources()),
        )

        try:
            application.settings = load_settings(application.settings_path)
        except EdiaadError as error:
            application.problems["settings"] = str(error)
            application.settings = dict(DEFAULT_SETTINGS)

        try:
            application.store = open_store(application.db_path)
        except EdiaadError as error:
            application.problems["store"] = str(error)

        if application.watchlist_path.is_file():
            try:
                application.watchlist = load_config(application.watchlist_path)
            except EdiaadError as error:
                application.problems["watchlist"] = str(error)

        # catalog 是可選的：有它才能把商品對照到來源（否則用預設來源）。
        if catalog_path(root).is_file():
            try:
                application.catalog = load_catalog(catalog_path(root))
            except EdiaadError as error:
                application.problems["catalog"] = str(error)

        return application

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self, host: str = "127.0.0.1", port: int = 8787):
        """啟動 Web 服務（已啟動時直接回傳既有 server）。"""
        from .web.server import create_server

        if self._server is not None:
            return self._server

        server = create_server(host=host, port=port, app=self)
        thread = threading.Thread(
            target=server.serve_forever, name="ediaad-web", daemon=True
        )
        thread.start()
        self._server = server
        self._thread = thread
        # 更新檢查絕不阻塞啟動（AC-059 第 2 條）：這裡只排程，沒有網址時完全不做事。
        self.trigger_update_check()
        return server

    def stop(self) -> None:
        """停止 Web 服務；幂等，且**可由其他執行緒呼叫**（`shutdown()` 的既有保證）。"""
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        # 只有當 `serve_forever()` 真的在跑時才能呼叫 `shutdown()`：它會等迴圈結束，
        # 若迴圈從未啟動（或已死）就會**永久阻塞**。這是「服務執行緒」的狀態檢查，
        # 不是控制流程的裝飾——漏掉它會讓關閉永遠回不來。
        if thread is not None and thread.is_alive():
            server.shutdown()
        server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def close(self) -> None:
        """停止服務並關閉資料庫與更新檢查的執行緒池（幂等）。"""
        self.stop()
        pool = self._update_pool
        self._update_pool = None
        if pool is not None:
            # `wait=False`：檢查最多卡 5 秒，關閉不該等它（worker 是 daemon）。
            pool.shutdown(wait=False)
        if self.store is not None:
            self.store.close()

    # ---- 更新檢查（TASK-032／AC-059） ----

    def trigger_update_check(self, *, force: bool = False) -> bool:
        """**非阻塞**地排一次更新檢查；沒有網址、已關閉或已在進行中時都不做事。

        立即回傳值（快取，或沒有快取時的 `pending`）會放進 `self.update_state`，
        實際結果由背景工作透過 `_absorb_update_state` 寫回。回傳「是否排了檢查」。
        """
        url = (self.update_url or "").strip()
        if not url or not bool(self.settings.get("update_enabled", True)):
            return False
        if self._update_inflight and not force:
            return False

        self._update_inflight = True
        try:
            self.update_state = check_update(
                http=self.update_http or update_http_get,
                manifest_url=url,
                cache_path=self.update_cache_path or update_state_path(self.home),
                now=datetime.now(timezone.utc),
                force=force,
                background=True,
                executor=self._update_pool_ref(),
                on_result=self._absorb_update_state,
            )
        except Exception:  # `check_update` 不拋例外；保險起見也不讓它影響服務
            self._update_inflight = False
            logger.debug("更新檢查排程失敗", exc_info=True)
            return False
        return True

    def _update_pool_ref(self) -> Any:
        """更新檢查的單一 worker 執行緒池（延後建立；可由 `update_executor` 覆寫）。"""
        if self.update_executor is not None:
            return self.update_executor
        if self._update_pool is None:
            from concurrent.futures import ThreadPoolExecutor

            self._update_pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="ediaad-update"
            )
        return self._update_pool

    def _absorb_update_state(self, state: Any) -> None:
        """背景檢查完成時寫回結果（由 `check_update` 的 `on_result` 呼叫）。"""
        self.update_state = state
        self._update_inflight = False

    # ---- 監控執行緒與逐商品來源分派（TASK-025／AC-047、AC-048） ----

    @property
    def monitor_running(self) -> bool:
        thread = self._monitor_thread
        return thread is not None and thread.is_alive()

    def fetch_for(self, symbol: str, interval: str):
        """依商品的 `source_id` 取得序列，並把**該輪的資料來源**記進狀態。

        這是「來源分派」與「快取目錄」兩條跨 Task 缺口的收斂點：來源由
        `Instrument.source_id` 決定（catalog 的權威對照在 `_source_id_for` 已用於網頁），
        而支援 `cache_dir`／`max_age` 的來源會拿到本服務的快取目錄與設定的有效期
        （以 `inspect.signature` 判斷能力，不在這裡寫死來源名稱）。
        """
        instrument = self._instrument(symbol, interval)
        source_id = (instrument.source_id if instrument is not None else "") or DEFAULT_SOURCE_ID
        source = get_source(source_id)
        kwargs: dict[str, Any] = {}
        parameters = inspect.signature(source.fetch).parameters
        if "cache_dir" in parameters:
            kwargs["cache_dir"] = self.cache_dir
        if "max_age" in parameters:
            kwargs["max_age"] = self.settings.get("cache_max_age_seconds", 900)
        try:
            series = source.fetch(symbol, interval, **kwargs)
        except BaseException as error:
            self._record_instrument(symbol, interval, source_id, None, str(error))
            raise
        data_source = str(series.attrs.get("data_source", source_id))
        self._record_instrument(symbol, interval, source_id, data_source, None)
        if self.store is not None:
            series.attrs["data_source"] = data_source
        return series

    def _instrument(self, symbol: str, interval: str):
        watchlist = self.watchlist
        if watchlist is None:
            return None
        for instrument in watchlist.instruments:
            if instrument.symbol == symbol and instrument.interval == interval:
                return instrument
        return None

    def _record_instrument(
        self,
        symbol: str,
        interval: str,
        source_id: str,
        data_source: str | None,
        error: str | None,
    ) -> None:
        self.instrument_status[f"{symbol}|{interval}"] = {
            "symbol": symbol,
            "interval": interval,
            "source_id": source_id,
            "data_source": data_source,
            "error": error,
            "checked_at": _utc_stamp(),
        }

    def _monitor_state(self) -> Any:
        """去重狀態：有 SQLite 就用它（跨重啟仍有效），否則退回記憶體。"""
        return self.store if self.store is not None else AlertState()

    def run_monitor_round(self) -> RunResult | None:
        """執行一輪監控（沒有監控清單時回 `None`）：與 CLI `monitor --once` 同一條路徑。"""
        watchlist = self.watchlist
        if watchlist is None:
            self.monitor_error = "尚未設定監控清單"
            return None
        try:
            result = run_once(
                watchlist,
                self.fetch_for,
                self.make_emit(),
                self.warn,
                state=self._monitor_state(),
            )
        except EdiaadError as error:
            self.monitor_error = str(error)
            self.warn(f"監控輪詢失敗：{error}")
            return None
        self.monitor_error = None
        self.last_result = result
        self.last_poll_at = _utc_stamp()
        return result

    def start_monitor(self, *, interval: int | None = None, run_immediately: bool = True) -> bool:
        """啟動背景監控執行緒（幂等）；沒有監控清單時回 `False`。

        每輪之間以 `Event.wait` 等待，因此 `stop_monitor()` 可以立刻叫醒它（不必等一輪）。
        """
        if self.monitor_running:
            return True
        if self.watchlist is None:
            self.monitor_error = "尚未設定監控清單"
            return False
        seconds = int(interval if interval is not None else self.settings["poll_interval_seconds"])
        self._monitor_stop = threading.Event()

        def loop() -> None:
            if run_immediately:
                self.run_monitor_round()
            while not self._monitor_stop.wait(max(1, seconds)):
                self.run_monitor_round()

        self._monitor_thread = threading.Thread(target=loop, name="ediaad-monitor", daemon=True)
        self._monitor_thread.start()
        return True

    def stop_monitor(self) -> None:
        """停止監控執行緒（幂等，最多等 5 秒）。"""
        thread = self._monitor_thread
        self._monitor_thread = None
        self._monitor_stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def warn(self, message: str) -> None:
        """監控迴圈的 warning 出口（目前只寫日誌與輸出，不影響服務）。"""
        print(f"[WARN] {message}")
        logger.warning("%s", message)

    def status_payload(self) -> dict[str, Any]:
        """系統狀態頁的資料（AC-048）：來源、最後輪詢時間、逐商品來源與錯誤。"""
        result = self.last_result
        return {
            "running": self.running,
            "monitor_running": self.monitor_running,
            "last_poll_at": self.last_poll_at,
            "monitor_error": self.monitor_error,
            "last_result": (
                None
                if result is None
                else {
                    "processed": result.processed,
                    "alerted": result.alerted,
                    "skipped": result.skipped,
                    "warnings": result.warnings,
                }
            ),
            "instruments": [dict(item) for item in self.instrument_status.values()],
            "problems": dict(self.problems),
            "version": self.version,
        }

    # ---- PID 檔與優雅關閉（TASK-026／AC-049、AC-050） ----

    def write_pid_file(self) -> Path:
        """把**自己的** PID 原子寫入 `<home>/ediaad.pid`。

        原子（先寫暫存檔再 `os.replace`）是必要的：啟動器可能在另一個行程讀這個檔，
        半寫的內容會被誤判為損毀。
        """
        self.pid_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.pid_path.with_name(self.pid_path.name + ".tmp")
        temporary.write_text(f"{os.getpid()}\n", encoding="utf-8")
        os.replace(temporary, self.pid_path)
        return self.pid_path

    def remove_pid_file(self) -> None:
        """只移除「內容是自己的 PID」的 PID 檔。

        別人的 PID 檔不得被我們刪掉：那會讓真正在服務的程序失去防護（AC-049 的
        重複啟動判定就是靠這個檔）。
        """
        try:
            content = self.pid_path.read_text(encoding="utf-8").strip()
        except OSError:
            return
        if content != str(os.getpid()):
            return
        try:
            self.pid_path.unlink()
        except OSError:
            return

    def request_shutdown(self) -> None:
        """要求服務結束；`POST /api/shutdown` 與訊號處理常式都走這裡（單一入口）。"""
        self.shutdown_event.set()

    def install_signal_handlers(self) -> None:
        """把 `SIGTERM`／`SIGINT` 接到同一條優雅關閉路徑（必須在主執行緒呼叫）。"""
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, self._on_signal)

    def _on_signal(self, _signum: int, _frame: Any) -> None:
        self.request_shutdown()

    def shutdown(self) -> None:
        """優雅關閉：停止服務 → 關閉資料庫 → **最後**才移除 PID 檔（AC-050 的順序）。

        順序有意義：PID 檔留到最後，讓「還在服務但正在關閉」的窗口仍能被啟動器視為
        已啟動（不會有第二個程序被叫起來搶同一個埠）。
        """
        self.stop_monitor()
        self.stop()
        self.close()
        self.remove_pid_file()
