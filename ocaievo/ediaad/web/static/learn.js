// 範例學習頁（TASK-023／AC-045）。
//
// 這一支只做三件事：把貼上或上傳的 CSV 內容組成請求、送到後端、把推估結果或錯誤原因
// 渲染出來。**推估完全在後端**（`POST /api/pattern/learn` → `ediaad.patterns.learn`）：
// 前端不猜參數、不畫線、不判定。
//
// 純函式掛在 `window.ediaadLearn`（可在 Node 裡驗證），只有 `attachLearnForm()` 碰文件。
(function (global) {
  "use strict";

  function text(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  /** 組成 `POST /api/pattern/learn` 的主體；沒有目前商品時只送範例。 */
  function buildLearnBody(csvText, symbol, interval, limit) {
    var body = { csv: text(csvText) };
    var trimmedSymbol = text(symbol).trim();
    var trimmedInterval = text(interval).trim();
    if (trimmedSymbol) {
      body.symbol = trimmedSymbol;
    }
    if (trimmedInterval) {
      body.interval = trimmedInterval;
    }
    if (limit !== undefined && limit !== null && limit !== "") {
      body.limit = limit;
    }
    return body;
  }

  function labelFor(name) {
    var labels = global.ediaadParams && global.ediaadParams.FIELD_LABELS;
    return labels && labels[name] ? labels[name] : name;
  }

  /** 把學習結果轉成一行一行的文字（推估參數 → 命中預覽 → 規格 JSON）。 */
  function describeLearnResult(payload) {
    if (!payload) {
      return ["尚未取得學習結果"];
    }
    var lines = [];
    var spec = payload.spec || {};
    Object.keys(spec).forEach(function (name) {
      lines.push(labelFor(name) + "：" + spec[name]);
    });
    lines.push("範例根數：" + payload.sample_bars);
    if (payload.status === "evaluated") {
      lines.push("目前商品的命中預覽：" + payload.hits + " 次");
    } else if (payload.status === "insufficient") {
      lines.push("目前商品無法評估：" + payload.message);
    } else {
      lines.push("沒有命中預覽（未指定商品與週期）");
    }
    lines.push("規格 JSON：" + payload.spec_json);
    return lines;
  }

  /** 把後端的錯誤主體轉成一句話；沒有可讀訊息時給固定訊息（不顯示例外內容）。 */
  function describeLearnError(payload) {
    if (payload && payload.error && payload.error.message) {
      return "無法推估：" + payload.error.message;
    }
    return "無法推估（請確認範例是含 time／open／high／low／close／volume 的 CSV，且服務仍在執行）";
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { ok: response.ok, payload: payload };
      });
    });
  }

  function renderLines(doc, element, lines) {
    if (!element) {
      return;
    }
    element.textContent = "";
    lines.forEach(function (line) {
      var item = doc.createElement("p");
      item.textContent = line;
      element.appendChild(item);
    });
  }

  function attachLearnForm(doc) {
    var form = doc.getElementById("learn-form");
    var csvInput = doc.getElementById("learn-csv");
    var fileInput = doc.getElementById("learn-file");
    var statusLine = doc.getElementById("learn-status");
    var resultBox = doc.getElementById("learn-result");
    var errorLine = doc.getElementById("learn-error");
    if (!form || !csvInput) {
      return null;
    }

    function setStatus(message) {
      if (statusLine) {
        statusLine.textContent = message;
      }
    }

    if (fileInput) {
      fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) {
          return;
        }
        var reader = new FileReader();
        reader.onload = function () {
          csvInput.value = String(reader.result || "");
          setStatus("已讀取 " + file.name + "（按「學習」推估參數）");
        };
        reader.onerror = function () {
          setStatus("無法讀取檔案：" + file.name);
        };
        reader.readAsText(file, "utf-8");
      });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var body = buildLearnBody(
        csvInput.value,
        doc.getElementById("param-symbol") ? doc.getElementById("param-symbol").value : "",
        doc.getElementById("param-interval") ? doc.getElementById("param-interval").value : ""
      );
      if (errorLine) {
        errorLine.textContent = "";
      }
      if (!body.csv.trim()) {
        if (errorLine) {
          errorLine.textContent = "請先貼上或上傳範例 CSV";
        }
        return;
      }
      setStatus("推估中…");
      post("/api/pattern/learn", body)
        .then(function (result) {
          if (result.ok) {
            renderLines(doc, resultBox, describeLearnResult(result.payload));
            setStatus("推估完成");
          } else {
            renderLines(doc, resultBox, []);
            if (errorLine) {
              errorLine.textContent = describeLearnError(result.payload);
            }
            setStatus("推估失敗");
          }
        })
        .catch(function () {
          renderLines(doc, resultBox, []);
          if (errorLine) {
            errorLine.textContent = describeLearnError(null);
          }
          setStatus("推估失敗");
        });
    });

    return { submit: form };
  }

  global.ediaadLearn = {
    buildLearnBody: buildLearnBody,
    describeLearnResult: describeLearnResult,
    describeLearnError: describeLearnError,
    attachLearnForm: attachLearnForm
  };

  if (typeof document !== "undefined") {
    attachLearnForm(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
