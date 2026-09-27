// 白話參數面板（TASK-023／AC-044）。
//
// 這一支只做三件事：把輸入框的字串轉成型別正確的參數、把參數送到後端、把次數顯示出來。
// **判定完全在後端**（`POST /api/pattern/preview` → `ediaad.patterns.detect`）：前端不得
// 自己算命中，否則預覽與正式掃描會變成兩套邏輯（報告第 6.3 節）。
//
// 載入時不碰 DOM（純函式掛在 `window.ediaadParams`），因此可以在 Node 裡驗證轉型、
// 錯誤訊息與去抖動；只有 `attachPanel()` 會碰文件。
(function (global) {
  "use strict";

  //: 白話標籤 ↔ `PatternSpec` 欄位；鍵就是後端要的參數名。
  var FIELD_LABELS = {
    pattern_id: "規律識別名",
    range_bars_min: "盤整最少根數",
    range_bars_max: "盤整最多根數",
    band_atr_multiple_max: "帶寬上限（ATR 倍數）",
    atr_period: "ATR 週期",
    breakdown_bars_max: "跌破需在幾根內",
    breakdown_depth_band_min: "跌破深度下限（帶寬倍數）",
    breakdown_depth_band_max: "跌破深度上限（帶寬倍數）",
    recovery_bars_max: "回歸根數上限",
    recovery_target: "回歸目標"
  };

  //: 面板的顯示順序（由盤整到回歸，與判定的相位順序一致）。
  var FIELD_ORDER = [
    "pattern_id",
    "range_bars_min",
    "range_bars_max",
    "band_atr_multiple_max",
    "atr_period",
    "breakdown_bars_max",
    "breakdown_depth_band_min",
    "breakdown_depth_band_max",
    "recovery_bars_max",
    "recovery_target"
  ];

  var INT_FIELDS = [
    "range_bars_min",
    "range_bars_max",
    "atr_period",
    "breakdown_bars_max",
    "recovery_bars_max"
  ];

  var RECOVERY_TARGETS = ["range_mean"];

  //: 輸入變更後多久送出（去抖動；仍遠小於 AC-044 的 1 秒）。
  var DEBOUNCE_MS = 150;

  function isBlank(raw) {
    return raw === null || raw === undefined || String(raw).trim() === "";
  }

  function isIntegerField(name) {
    return INT_FIELDS.indexOf(name) >= 0;
  }

  function parseValue(name, raw) {
    if (FIELD_ORDER.indexOf(name) < 0) {
      throw new Error("未知的參數：" + name + "（可用：" + FIELD_ORDER.join("、") + "）");
    }
    if (name === "recovery_target") {
      var target = isBlank(raw) ? "" : String(raw).trim();
      if (RECOVERY_TARGETS.indexOf(target) < 0) {
        throw new Error(
          "recovery_target 必須是 " + RECOVERY_TARGETS.join("、") + " 之一，收到 " + target
        );
      }
      return target;
    }
    if (name === "pattern_id") {
      var identifier = isBlank(raw) ? "" : String(raw).trim();
      if (!identifier) {
        throw new Error("pattern_id 必須是非空字串");
      }
      return identifier;
    }
    if (isBlank(raw)) {
      throw new Error(name + " 必須是" + (isIntegerField(name) ? "整數" : "數值") + "，收到空白");
    }
    var text = String(raw).trim();
    if (!/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/.test(text)) {
      throw new Error(name + " 必須是" + (isIntegerField(name) ? "整數" : "數值") + "，收到 " + text);
    }
    var value = Number(text);
    if (!isFinite(value)) {
      throw new Error(name + " 必須是" + (isIntegerField(name) ? "整數" : "數值") + "，收到 " + text);
    }
    if (isIntegerField(name) && !Number.isInteger(value)) {
      throw new Error(name + " 必須是整數，收到 " + text);
    }
    return value;
  }

  /** 把表單的原始字串轉成型別正確的參數；不合法時丟出指出欄位名的錯誤。 */
  function toParams(values) {
    var params = {};
    Object.keys(values || {}).forEach(function (name) {
      params[name] = parseValue(name, values[name]);
    });
    return params;
  }

  /** 組成 `POST /api/pattern/preview` 的主體（只帶有填值的欄位）。 */
  function buildBody(symbol, interval, values) {
    return {
      symbol: String(symbol === null || symbol === undefined ? "" : symbol).trim(),
      interval: String(interval === null || interval === undefined ? "" : interval).trim(),
      params: toParams(values)
    };
  }

  /** 把預覽回應轉成一句人看得懂的話（F-003：資料不足不等於沒有命中）。 */
  function describeHits(payload) {
    if (!payload) {
      return "尚未取得命中次數";
    }
    if (payload.status === "insufficient") {
      return "無法評估：" + payload.message;
    }
    if (payload.status === "no_preview") {
      return "沒有命中預覽";
    }
    if (typeof payload.hits === "number") {
      return payload.hits > 0
        ? "在此參數下命中 " + payload.hits + " 次"
        : "評估後沒有命中（0 次）";
    }
    return payload.message || "尚未取得命中次數";
  }

  function describeError(payload) {
    if (payload && payload.error && payload.error.message) {
      return payload.error.message;
    }
    return "無法取得命中次數（請確認服務仍在執行）";
  }

  /** 去抖動：連續輸入只送最後一次；`wait` 可覆寫（測試用）。 */
  function makeDebouncer(fn, wait) {
    var timer = null;
    var delay = typeof wait === "number" ? wait : DEBOUNCE_MS;
    return function () {
      var args = arguments;
      if (timer !== null) {
        clearTimeout(timer);
      }
      timer = setTimeout(function () {
        timer = null;
        fn.apply(null, args);
      }, delay);
    };
  }

  // ---- 以下為 DOM 黏著層（Node 不執行） ----

  function fieldsOf(root) {
    return Array.prototype.slice.call(root.querySelectorAll("[data-param]"));
  }

  function readValues(root) {
    var values = {};
    fieldsOf(root).forEach(function (input) {
      values[input.getAttribute("data-param")] = input.value;
    });
    return values;
  }

  function fillValues(root, spec) {
    fieldsOf(root).forEach(function (input) {
      var name = input.getAttribute("data-param");
      if (spec && spec[name] !== undefined && spec[name] !== null) {
        input.value = String(spec[name]);
      }
    });
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

  function attachPanel(doc) {
    var root = doc.getElementById("param-panel");
    var hitsLine = doc.getElementById("param-hits");
    var errorLine = doc.getElementById("param-error");
    var symbolInput = doc.getElementById("param-symbol");
    var intervalInput = doc.getElementById("param-interval");
    if (!root || !hitsLine) {
      return null;
    }

    function preview() {
      var symbol = symbolInput ? symbolInput.value.trim() : "";
      var interval = intervalInput ? intervalInput.value.trim() : "";
      var values = readValues(root);
      var body;
      try {
        body = buildBody(symbol, interval, values);
      } catch (error) {
        if (errorLine) {
          errorLine.textContent = error.message;
        }
        hitsLine.textContent = "參數不合法，尚未計算";
        return Promise.resolve();
      }
      if (errorLine) {
        errorLine.textContent = "";
      }
      if (!body.symbol || !body.interval) {
        hitsLine.textContent = "請先選擇商品與週期";
        return Promise.resolve();
      }
      hitsLine.textContent = "計算中…";
      return post("/api/pattern/preview", body).then(function (result) {
        hitsLine.textContent = result.ok
          ? describeHits(result.payload)
          : describeError(result.payload);
      });
    }

    var debounced = makeDebouncer(preview, DEBOUNCE_MS);
    root.addEventListener("input", debounced);
    root.addEventListener("change", debounced);
    if (symbolInput) {
      symbolInput.addEventListener("input", debounced);
    }
    if (intervalInput) {
      intervalInput.addEventListener("input", debounced);
    }

    // 面板一開始顯示的是設定推導出的參數（單一真相：由後端回報，不在前端另抄一份）。
    fetch("/api/patterns", { headers: { Accept: "application/json" } })
      .then(function (response) {
        return response.json();
      })
      .then(function (payload) {
        var patterns = payload.patterns || {};
        var first = Object.keys(patterns)[0];
        if (first) {
          fillValues(root, patterns[first]);
        }
        return preview();
      })
      .catch(function () {
        return preview();
      });

    return { preview: preview, debounced: debounced };
  }

  global.ediaadParams = {
    FIELD_LABELS: FIELD_LABELS,
    FIELD_ORDER: FIELD_ORDER,
    INT_FIELDS: INT_FIELDS,
    DEBOUNCE_MS: DEBOUNCE_MS,
    parseValue: parseValue,
    toParams: toParams,
    buildBody: buildBody,
    describeHits: describeHits,
    describeError: describeError,
    makeDebouncer: makeDebouncer,
    readValues: readValues,
    fillValues: fillValues,
    attachPanel: attachPanel
  };

  if (typeof document !== "undefined") {
    attachPanel(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
