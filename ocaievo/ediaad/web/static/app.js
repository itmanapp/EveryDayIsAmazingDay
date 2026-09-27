// 最小可用的前端骨架（TASK-020）：只讀取健康狀態並以文字呈現。
// 後續 Task 會在這裡加入監控清單、參數預覽、K 線圖與提醒清單。
(function () {
  "use strict";

  function describe(problem, label) {
    return label + "：" + problem;
  }

  function render(payload) {
    var status = document.getElementById("status");
    var details = document.getElementById("status-details");

    if (payload.status === "ok") {
      // 以文字而非顏色表達狀態（SPEC 第 6 節可及性）
      status.textContent = "服務正常（版本 " + payload.version + "）";
    } else {
      status.textContent = "服務狀態異常：" + payload.status;
    }

    details.innerHTML = "";
    var rows = [
      ["版本", payload.version],
      ["已註冊來源", (payload.sources || []).join("、") || "無"]
    ];
    Object.keys(payload.problems || {}).forEach(function (key) {
      rows.push(["問題", describe(payload.problems[key], key)]);
    });
    rows.forEach(function (row) {
      var term = document.createElement("dt");
      term.textContent = row[0];
      var value = document.createElement("dd");
      value.textContent = row[1];
      details.appendChild(term);
      details.appendChild(value);
    });
  }

  function fail(error) {
    document.getElementById("status").textContent = "無法連線到本機服務：" + error;
  }

  // 「關閉服務」按鈕（AC-050）：只送出關閉請求，真正的停止由服務主迴圈執行。
  function attachShutdown() {
    var button = document.getElementById("shutdown-button");
    var status = document.getElementById("shutdown-status");
    if (!button || !status) {
      return;
    }
    button.addEventListener("click", function () {
      button.disabled = true;
      status.textContent = "正在關閉服務…";
      fetch("/api/shutdown", {
        method: "POST",
        headers: { Accept: "application/json" }
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (result.ok) {
            status.textContent = "服務已接受關閉請求，這個頁面即將無法連線。";
          } else {
            button.disabled = false;
            status.textContent =
              "關閉失敗：" +
              (result.payload && result.payload.error
                ? result.payload.error.message
                : "未知原因");
          }
        })
        .catch(function () {
          // 連線中斷通常代表服務已經關閉
          status.textContent = "服務已關閉（連線中斷）。";
        });
    });
  }

  attachShutdown();

  fetch("/api/health", { headers: { Accept: "application/json" } })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(render)
    .catch(fail);
})();
