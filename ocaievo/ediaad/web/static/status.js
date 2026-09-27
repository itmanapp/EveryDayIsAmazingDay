// 系統狀態頁（TASK-025／AC-048）。
// 只呈現後端算好的資料：最後輪詢時間、各商品的來源與錯誤、最近的計數。
(function (global) {
  "use strict";

  /** 一筆商品狀態 → 一行文字（來源與快取狀態都寫出來，不只靠顏色）。 */
  function sourceText(entry) {
    var label = entry.symbol + " " + entry.interval + "：來源 " + (entry.source_id || "預設");
    if (entry.error) {
      return label + "，錯誤：" + entry.error;
    }
    return label + "，本次資料來自 " + (entry.data_source || "未知");
  }

  function describeStatus(payload) {
    if (!payload) {
      return ["尚未取得系統狀態"];
    }
    var lines = [
      "網頁服務：" + (payload.running ? "執行中" : "已停止"),
      "監控執行緒：" + (payload.monitor_running ? "執行中" : "未執行"),
      "最後輪詢時間：" + (payload.last_poll_at || "尚未輪詢")
    ];
    var result = payload.last_result;
    if (result) {
      lines.push(
        "最近一輪：評估 " + result.processed + " 檔、提醒 " + result.alerted +
        " 次、資料不足 " + result.skipped + " 檔、警告 " + result.warnings + " 則"
      );
    } else {
      lines.push("最近一輪：尚未執行");
    }
    if (payload.monitor_error) {
      lines.push("監控問題：" + payload.monitor_error);
    }
    (payload.instruments || []).forEach(function (entry) {
      lines.push(sourceText(entry));
    });
    Object.keys(payload.problems || {}).forEach(function (key) {
      lines.push("啟動問題（" + key + "）：" + payload.problems[key]);
    });
    return lines;
  }

  function attach(doc) {
    var box = doc.getElementById("status-lines");
    var statusLine = doc.getElementById("status-page-state");
    if (!box) {
      return null;
    }

    function refresh() {
      return fetch("/api/status", { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          box.textContent = "";
          describeStatus(payload).forEach(function (line) {
            var item = doc.createElement("p");
            item.textContent = line;
            box.appendChild(item);
          });
          if (statusLine) { statusLine.textContent = "狀態已更新"; }
        })
        .catch(function () {
          if (statusLine) { statusLine.textContent = "無法取得系統狀態"; }
        });
    }

    refresh();
    return { refresh: refresh };
  }

  global.ediaadStatus = {
    sourceText: sourceText,
    describeStatus: describeStatus,
    attach: attach
  };

  if (typeof document !== "undefined") {
    attach(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
