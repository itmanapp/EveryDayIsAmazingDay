#!/bin/sh
# ediaad 優雅停止（TASK-026／AC-050）。
#
# 讀 `<EDIAAD_HOME>/ediaad.pid` → 送 SIGTERM → 等程序結束 → 清除 PID 檔。
# 服務收到 SIGTERM 後會走 `Application.shutdown()`（停 HTTP → 關 SQLite → 移除 PID 檔），
# 因此正常情況下埠在程序結束時就已釋放。
set -u

HOME_DIR="${EDIAAD_HOME:-$HOME/.local/share/ediaad}"
PID_FILE="$HOME_DIR/ediaad.pid"
PORT="${EDIAAD_PORT:-8787}"
WAIT_SECONDS="${EDIAAD_STOP_TIMEOUT:-10}"

if [ ! -f "$PID_FILE" ]; then
  echo "ediaad 未在執行（找不到 PID 檔：$PID_FILE）"
  exit 0
fi

# 程序是否還在跑：`kill -0` 對「已結束但還沒被回收」的殭屍程序也會成功，
# 因此再看一眼 /proc 的狀態欄（Linux）。殭屍等於已經結束。
is_alive() {
  kill -0 "$1" 2>/dev/null || return 1
  if [ -r "/proc/$1/stat" ]; then
    state=$(sed 's/.*) //' "/proc/$1/stat" 2>/dev/null | cut -d' ' -f1)
    [ "$state" = "Z" ] && return 1
  fi
  return 0
}

PID=$(tr -d '[:space:]' < "$PID_FILE" 2>/dev/null || true)
case "$PID" in
  ''|*[!0-9]*)
    echo "ediaad 未在執行（PID 檔內容無法解讀，已清除：$PID_FILE）"
    rm -f "$PID_FILE"
    exit 0
    ;;
esac

if ! is_alive "$PID"; then
  echo "ediaad 未在執行（PID $PID 已不存在，已清除陳舊 PID 檔）"
  rm -f "$PID_FILE"
  exit 0
fi

echo "正在停止 ediaad（PID $PID）…"
kill -TERM "$PID" 2>/dev/null || true

i=0
while [ "$i" -lt "$WAIT_SECONDS" ]; do
  if ! is_alive "$PID"; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

if is_alive "$PID"; then
  echo "警告：PID $PID 在 ${WAIT_SECONDS} 秒內沒有結束，改送 SIGKILL" >&2
  kill -KILL "$PID" 2>/dev/null || true
  sleep 1
fi

rm -f "$PID_FILE"
echo "ediaad 已停止（埠 $PORT 應已釋放）"
exit 0
