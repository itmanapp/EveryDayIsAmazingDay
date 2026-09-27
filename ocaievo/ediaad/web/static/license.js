// 授權頁（TASK-025／AC-066）。
// 三種狀態（未啟用／有效期內／已過期或已撤銷）都以**文字**表達，並提供首次啟用與
// 更換密鑰的輸入入口。租約狀態由後端 `GET /api/license` 提供，前端不自行計算。
(function (global) {
  "use strict";

  var STATE_LABELS = {
    inactive: "尚未啟用",
    active: "已啟用（有效期內）",
    expired: "已過期",
    revoked: "已撤銷",
    error: "租約異常"
  };

  function text(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  /** 啟用表單 → `POST /api/license/activate` 的主體。 */
  function buildActivateBody(key) {
    var value = text(key);
    if (!value) {
      throw new Error("請輸入密鑰（key）");
    }
    return { key: value };
  }

  function describeLicense(payload) {
    if (!payload) {
      return ["尚未取得授權狀態"];
    }
    var state = payload.state || "error";
    var lines = ["授權狀態：" + (STATE_LABELS[state] || state)];
    if (state === "inactive") {
      lines.push("請在下方輸入密鑰完成首次啟用。");
      return lines;
    }
    if (state === "error") {
      lines.push(payload.message || "租約無法解讀，請重新啟用。");
      lines.push("重新申請：" + (payload.reapply_url || ""));
      return lines;
    }
    lines.push("密鑰識別碼：" + (payload.key_id || "未知"));
    lines.push("到期時間：" + (payload.expires_at || "未知"));
    if (typeof payload.days_remaining === "number") {
      lines.push("剩餘天數：" + payload.days_remaining.toFixed(1) + " 天");
    }
    lines.push("已授權功能：" + ((payload.features || []).join("、") || "無"));
    if (payload.reapply) {
      lines.push("原因：" + payload.message);
      lines.push("重新申請新密鑰：" + (payload.reapply_url || ""));
    }
    return lines;
  }

  function attach(doc) {
    var box = doc.getElementById("license-lines");
    var status = doc.getElementById("license-status");
    var errorLine = doc.getElementById("license-error");
    var form = doc.getElementById("license-form");
    var input = doc.getElementById("license-key");
    if (!box) {
      return null;
    }

    function refresh() {
      return fetch("/api/license", { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          box.textContent = "";
          describeLicense(payload).forEach(function (line) {
            var item = doc.createElement("p");
            item.textContent = line;
            box.appendChild(item);
          });
          if (status) { status.textContent = "授權狀態已更新"; }
          if (form) { form.hidden = false; }
        })
        .catch(function () {
          if (status) { status.textContent = "無法取得授權狀態"; }
        });
    }

    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var body;
        try {
          body = buildActivateBody(input ? input.value : "");
        } catch (error) {
          if (errorLine) { errorLine.textContent = error.message; }
          return;
        }
        if (errorLine) { errorLine.textContent = ""; }
        fetch("/api/license/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(body)
        })
          .then(function (response) {
            return response.json().then(function (payload) {
              return { ok: response.ok, payload: payload };
            });
          })
          .then(function (result) {
            if (!result.ok) {
              if (errorLine) {
                errorLine.textContent =
                  "啟用失敗：" +
                  (result.payload && result.payload.error
                    ? result.payload.error.message
                    : "未知原因");
              }
              return;
            }
            if (input) { input.value = ""; }
            return refresh();
          })
          .catch(function () {
            if (errorLine) { errorLine.textContent = "啟用失敗（請確認服務仍在執行）"; }
          });
      });
    }

    refresh();
    return { refresh: refresh };
  }

  global.ediaadLicense = {
    STATE_LABELS: STATE_LABELS,
    buildActivateBody: buildActivateBody,
    describeLicense: describeLicense,
    attach: attach
  };

  if (typeof document !== "undefined") {
    attach(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
