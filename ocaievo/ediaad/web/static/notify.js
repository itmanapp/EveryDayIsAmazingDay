// 瀏覽器原生通知管道（TASK-027／AC-051）。
//
// 伺服器不能直接叫瀏覽器顯示通知，因此後端把「要顯示什麼」以 `event="notification"`
// 推播（payload 只有 title／body／tag），這一支負責權限與顯示。
//
// `http://127.0.0.1` 屬於安全來源（secure context），因此 `Notification` API 可用；
// 但**權限一定要使用者同意**：預設不主動彈窗，第一次互動（點擊頁面）時才詢問。
//
// 純函式掛在 `window.ediaadNotify`（可在 Node 裡用假的 `Notification` 驗證），
// 只有 `attach()` 會碰文件與網路。
(function (global) {
  "use strict";

  function supported(win) {
    return !!(win && typeof win.Notification !== "undefined" && win.Notification);
  }

  function permission(win) {
    if (!supported(win)) {
      return "unsupported";
    }
    return win.Notification.permission || "default";
  }

  /** 要求通知權限；回傳要求後的權限字串，環境不支援時回 `false`。

  `try`／`catch` 已涵蓋「沒有 Notification」與「沒有 requestPermission」兩種情況
  （兩者都會在呼叫時丟出 TypeError），因此不再另外寫一次支援判斷。
  */
  function requestPermission(win) {
    try {
      win.Notification.requestPermission();
    } catch (error) {
      return false;
    }
    return permission(win);
  }

  /** 推播 payload → 顯示用的標題與內容（缺欄位時給安全的預設值）。 */
  function describe(payload) {
    var data = payload || {};
    return {
      title: data.title || "ediaad 提醒",
      body: data.body || ""
    };
  }

  /** 顯示一則通知；沒有權限或環境不支援時回 `false`（絕不拋出例外）。 */
  function show(win, payload) {
    if (permission(win) !== "granted") {
      return false;
    }
    var text = describe(payload);
    var options = { body: text.body };
    if (payload && payload.tag) {
      options.tag = payload.tag;
    }
    try {
      new win.Notification(text.title, options);
    } catch (error) {
      return false;
    }
    return true;
  }

  // ---- 以下為 DOM／網路黏著層（Node 不執行） ----

  function attach(doc, win) {
    var seen = new Set();

    // 權限要在使用者互動時詢問（瀏覽器會拒絕沒有互動的請求）
    if (permission(win) === "default") {
      var ask = function () {
        requestPermission(win);
        doc.removeEventListener("click", ask);
      };
      doc.addEventListener("click", ask);
    }

    if (typeof win.EventSource === "undefined") {
      return null;
    }
    var source = new win.EventSource("/api/events/stream");
    source.addEventListener("notification", function (message) {
      var payload;
      try {
        payload = JSON.parse(message.data);
      } catch (error) {
        return;
      }
      var tag = payload && payload.tag ? String(payload.tag) : "";
      if (tag) {
        if (seen.has(tag)) {
          return; // 第二道防線：同一個事件不重複顯示
        }
        seen.add(tag);
      }
      show(win, payload);
    });
    return source;
  }

  global.ediaadNotify = {
    supported: supported,
    permission: permission,
    requestPermission: requestPermission,
    describe: describe,
    show: show,
    attach: attach
  };

  if (typeof document !== "undefined" && typeof window !== "undefined") {
    attach(document, window);
  }
})(typeof window !== "undefined" ? window : globalThis);
