// 版本頁（TASK-025／AC-048；更新檢查 TASK-032／AC-059）。
// 這裡只呈現目前版本與最近一次檢查的結果。**四種「沒有新版本可顯示」的處境不得混淆**：
// 還沒檢查、檢查進行中、更新功能已關閉、檢查失敗（見 `_update_message` 的同一條紀律）。
(function (global) {
  "use strict";

  function missingText(payload) {
    if (payload.error) {
      return "無法取得（更新檢查失敗）";
    }
    if (payload.source === "pending") {
      return "檢查中…";
    }
    return "尚未檢查";
  }

  function describeVersion(payload) {
    if (!payload) {
      return ["尚未取得版本資訊"];
    }
    var lines = ["目前版本：" + payload.version];
    if (payload.update_enabled === false) {
      lines.push("更新檢查：已關閉");
    }
    if (!payload.latest_version) {
      lines.push("最新版本：" + missingText(payload));
      lines.push("說明：" + (payload.message || "尚未檢查更新"));
      return lines;
    }
    lines.push("最新版本：" + payload.latest_version);
    lines.push("發佈日期：" + (payload.released_at || "未提供"));
    lines.push("說明：" + (payload.notes || "未提供"));
    lines.push(
      payload.update_available
        ? "有可用的新版本（目前版本較舊）"
        : "已是最新版本"
    );
    if (payload.checked_at) {
      lines.push("檢查時間：" + payload.checked_at);
    }
    if (payload.error) {
      lines.push("上次檢查失敗：" + payload.error);
    }
    return lines;
  }

  function attach(doc) {
    var box = doc.getElementById("version-lines");
    if (!box) {
      return null;
    }
    return fetch("/api/version", { headers: { Accept: "application/json" } })
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        box.textContent = "";
        describeVersion(payload).forEach(function (line) {
          var item = doc.createElement("p");
          item.textContent = line;
          box.appendChild(item);
        });
      })
      .catch(function () {
        box.textContent = "無法取得版本資訊";
      });
  }

  global.ediaadVersion = { describeVersion: describeVersion, attach: attach };

  if (typeof document !== "undefined") {
    attach(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
