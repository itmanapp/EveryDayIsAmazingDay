// 歷史回看頁（表單化 match，TASK-024／AC-046）。
//
// 這一支只做三件事：把表單的字串轉成請求主體、送到後端、把結果表格與統計文字畫出來。
// **計算完全在後端**（`POST /api/match` → `ediaad.match.run_match` → `scan_similar` ＋
// `forward_stats`）：前端不得自己算相似度，否則回看結果會與 CLI 分岔。
//
// 純函式掛在 `window.ediaadMatch`（可在 Node 裡驗證），只有 `attachMatchForm()` 碰文件。
(function (global) {
  "use strict";

  var REQUIRED_TEXT = ["symbol", "interval"];
  var OPTIONAL_TEXT = ["start", "end"];
  var INTEGER_FIELDS = ["window", "top", "horizon", "step"];

  function text(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  /** 整數字串 → 整數；空白回 `null`（代表「不送這個欄位」，由後端套預設）。 */
  function parseInteger(name, raw, minimum) {
    var value = text(raw);
    if (!value) {
      return null;
    }
    if (!/^[+-]?\d+$/.test(value)) {
      throw new Error("欄位 " + name + " 必須是整數，收到 " + value);
    }
    var number = Number(value);
    if (minimum !== undefined && number < minimum) {
      throw new Error("欄位 " + name + " 必須 >= " + minimum + "，收到 " + number);
    }
    return number;
  }

  /** 數值字串 → 數值；空白回 `null`。`minimum`／`maximum` 為閉／開區間的界。 */
  function parseNumber(name, raw, minimum, maximum) {
    var value = text(raw);
    if (!value) {
      return null;
    }
    if (!/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/.test(value)) {
      throw new Error("欄位 " + name + " 必須是數值，收到 " + value);
    }
    var number = Number(value);
    if (!isFinite(number)) {
      throw new Error("欄位 " + name + " 必須是數值，收到 " + value);
    }
    if (minimum !== undefined && number < minimum) {
      throw new Error("欄位 " + name + " 必須 >= " + minimum + "，收到 " + number);
    }
    if (maximum !== undefined && number >= maximum) {
      throw new Error("欄位 " + name + " 必須 < " + maximum + "，收到 " + number);
    }
    return number;
  }

  /** 表單值 → `POST /api/match` 主體；不合法時丟出指出欄位名的錯誤。 */
  function buildMatchBody(values) {
    var source = values || {};
    var body = {};

    REQUIRED_TEXT.forEach(function (name) {
      var value = text(source[name]);
      if (!value) {
        throw new Error("欄位 " + name + " 為必填");
      }
      body[name] = value;
    });

    var window = parseInteger("window", source.window, 1);
    if (window === null) {
      throw new Error("欄位 window 為必填");
    }
    body.window = window;

    OPTIONAL_TEXT.forEach(function (name) {
      var value = text(source[name]);
      if (value) {
        body[name] = value;
      }
    });

    INTEGER_FIELDS.slice(1).forEach(function (name) {
      var value = parseInteger(name, source[name], 1);
      if (value !== null) {
        body[name] = value;
      }
    });

    var overlap = parseNumber("overlap", source.overlap, 0, 1);
    if (overlap !== null) {
      body.overlap = overlap;
    }
    return body;
  }

  function percent(value) {
    if (value === null || value === undefined) {
      return "無樣本";
    }
    return (Number(value) * 100).toFixed(1) + "%";
  }

  /** 相似片段排行 → 表格列（分數固定小數位，讓排序可讀）。 */
  function matchRows(payload) {
    var matches = (payload && payload.matches) || [];
    return matches.map(function (match) {
      return {
        startIndex: match.start_index,
        endIndex: match.end_index,
        score: Number(match.score).toFixed(4),
        timeStart: match.time_start,
        timeEnd: match.time_end
      };
    });
  }

  /** 後續走勢統計 → 文字列；樣本數為 0 時明說「無樣本」（不得顯示 0%）。 */
  function describeOutlook(outlook) {
    if (!outlook) {
      return ["沒有後續走勢統計"];
    }
    var samples = Number(outlook.samples || 0);
    if (samples === 0) {
      return ["樣本數：0（無樣本，無法提供上漲機率與報酬統計）"];
    }
    return [
      "樣本數：" + samples,
      "上漲機率：" + percent(outlook.up_probability),
      "平均報酬：" + percent(outlook.mean_return),
      "中位數報酬：" + percent(outlook.median_return),
      "標準差：" + percent(outlook.std_return)
    ];
  }

  /** 整份結果的摘要文字（來源、範例、參數、命中數、統計）。 */
  function describeResult(payload) {
    if (!payload) {
      return ["尚未取得結果"];
    }
    var params = payload.params || {};
    var sample = payload.sample || {};
    var lines = [
      "資料來源：" + (payload.data_source || "未知"),
      "範例：最近 " + params.window + " 根（" + sample.time_start + " ～ " + sample.time_end + "）",
      "參數：top=" + params.top + "、horizon=" + params.horizon + "、step=" + params.step + "、overlap=" + params.overlap,
      "命中筆數：" + ((payload.matches || []).length)
    ];
    return lines.concat(describeOutlook(payload.outlook));
  }

  function describeError(payload) {
    if (payload && payload.error && payload.error.message) {
      return "無法取得回看結果：" + payload.error.message;
    }
    return "無法取得回看結果（請確認服務仍在執行）";
  }

  // ---- 以下為 DOM 黏著層（Node 不執行） ----

  function valueOf(doc, id) {
    var element = doc.getElementById(id);
    return element ? element.value : "";
  }

  function clear(element) {
    while (element && element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function renderRows(doc, table, rows) {
    if (!table) {
      return;
    }
    clear(table);
    rows.forEach(function (row) {
      var tr = doc.createElement("tr");
      [row.startIndex, row.endIndex, row.score, row.timeStart, row.timeEnd].forEach(
        function (value) {
          var td = doc.createElement("td");
          td.textContent = String(value);
          tr.appendChild(td);
        }
      );
      table.appendChild(tr);
    });
  }

  function renderLines(doc, element, lines) {
    if (!element) {
      return;
    }
    clear(element);
    lines.forEach(function (line) {
      var item = doc.createElement("p");
      item.textContent = line;
      element.appendChild(item);
    });
  }

  function attachMatchForm(doc) {
    var form = doc.getElementById("match-form");
    var table = doc.getElementById("match-rows");
    var outlookBox = doc.getElementById("match-outlook");
    var statusLine = doc.getElementById("match-status");
    var errorLine = doc.getElementById("match-error");
    if (!form) {
      return null;
    }

    function setStatus(message) {
      if (statusLine) {
        statusLine.textContent = message;
      }
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var body;
      try {
        body = buildMatchBody({
          symbol: valueOf(doc, "match-symbol"),
          interval: valueOf(doc, "match-interval"),
          window: valueOf(doc, "match-window"),
          top: valueOf(doc, "match-top"),
          horizon: valueOf(doc, "match-horizon"),
          step: valueOf(doc, "match-step"),
          overlap: valueOf(doc, "match-overlap"),
          start: valueOf(doc, "match-start"),
          end: valueOf(doc, "match-end")
        });
      } catch (error) {
        if (errorLine) {
          errorLine.textContent = error.message;
        }
        setStatus("參數不合法，尚未查詢");
        return;
      }
      if (errorLine) {
        errorLine.textContent = "";
      }
      setStatus("查詢中…");
      fetch("/api/match", {
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
            renderRows(doc, table, []);
            renderLines(doc, outlookBox, []);
            if (errorLine) {
              errorLine.textContent = describeError(result.payload);
            }
            setStatus("查詢失敗");
            return;
          }
          renderRows(doc, table, matchRows(result.payload));
          renderLines(doc, outlookBox, describeResult(result.payload));
          setStatus("查詢完成");
        })
        .catch(function () {
          renderRows(doc, table, []);
          renderLines(doc, outlookBox, []);
          if (errorLine) {
            errorLine.textContent = describeError(null);
          }
          setStatus("查詢失敗");
        });
    });

    return { submit: form };
  }

  global.ediaadMatch = {
    buildMatchBody: buildMatchBody,
    matchRows: matchRows,
    describeOutlook: describeOutlook,
    describeResult: describeResult,
    describeError: describeError,
    attachMatchForm: attachMatchForm
  };

  if (typeof document !== "undefined") {
    attachMatchForm(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
