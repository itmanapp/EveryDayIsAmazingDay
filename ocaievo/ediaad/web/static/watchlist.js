// 監控清單管理（TASK-025／AC-047）。
// 只做三件事：把表單列轉成請求主體、把回應轉成文字、把結果渲染出來。
// 商品搜尋與設定驗證都在後端（`Source.search`／`monitor.validate_config`）。
(function (global) {
  "use strict";

  function text(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  /** 一列表單 → 一個商品設定；缺欄位時丟出指出欄位名的錯誤。 */
  function parseInstrumentRow(row) {
    var symbol = text(row && row.symbol);
    var interval = text(row && row.interval);
    if (!symbol) {
      throw new Error("商品代號（symbol）為必填");
    }
    if (!interval) {
      throw new Error("週期（interval）為必填");
    }
    var instrument = { symbol: symbol, interval: interval };
    var sourceId = text(row && row.source_id);
    if (sourceId) {
      instrument.source_id = sourceId;
    }
    return instrument;
  }

  /** 表單列 ＋ 輪詢間隔 → `POST /api/watchlist` 的主體。 */
  function buildWatchlistBody(rows, extras) {
    var instruments = (rows || []).map(parseInstrumentRow);
    if (instruments.length === 0) {
      throw new Error("至少要保留一個要監控的商品");
    }
    var body = { instruments: instruments };
    var options = extras || {};
    if (text(options.poll_interval_seconds)) {
      var seconds = Number(text(options.poll_interval_seconds));
      if (!isFinite(seconds) || seconds < 1) {
        throw new Error("輪詢間隔（poll_interval_seconds）必須 >= 1 秒");
      }
      body.poll_interval_seconds = seconds;
    }
    return body;
  }

  /** 目前監控設定 → 文字列。 */
  function describeWatchlist(payload) {
    if (!payload || !payload.watchlist) {
      return ["尚未取得監控清單"];
    }
    var watchlist = payload.watchlist;
    var lines = [
      "設定檔：" + (payload.path || "（未知）"),
      "輪詢間隔：" + watchlist.poll_interval_seconds + " 秒",
      "規律：" + watchlist.pattern_id + "（觀察後續 " + watchlist.horizon + " 根）",
      "監控中的商品（" + (watchlist.instruments || []).length + "）："
    ];
    (watchlist.instruments || []).forEach(function (instrument) {
      lines.push(
        "　" + instrument.symbol + " " + instrument.interval + "（來源 " +
          (instrument.source_id || "預設") + "）"
      );
    });
    if ((watchlist.instruments || []).length === 0) {
      lines.push("　（尚未設定）");
    }
    return lines;
  }

  /** 搜尋結果 → 文字列（下拉清單用）。 */
  function describeSearchResults(items) {
    return (items || []).map(function (item) {
      return item.display_name + "（" + item.symbol + "，" + (item.interval || "未指定週期") + "）";
    });
  }

  function describeError(payload) {
    if (payload && payload.error && payload.error.message) {
      return "無法儲存監控清單：" + payload.error.message;
    }
    return "無法儲存監控清單（請確認服務仍在執行）";
  }

  // ---- DOM 黏著層 ----

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

  function readRows(doc, list) {
    return Array.prototype.map.call(list.querySelectorAll("li[data-instrument]"), function (item) {
      return {
        symbol: item.dataset.symbol,
        interval: item.dataset.interval,
        source_id: item.dataset.sourceId
      };
    });
  }

  function addRow(doc, list, instrument) {
    var item = doc.createElement("li");
    item.dataset.instrument = "1";
    item.dataset.symbol = instrument.symbol;
    item.dataset.interval = instrument.interval;
    item.dataset.sourceId = instrument.source_id || "";
    var label = doc.createElement("span");
    label.textContent =
      instrument.symbol + " " + instrument.interval +
      "（來源 " + (instrument.source_id || "預設") + "）";
    var remove = doc.createElement("button");
    remove.type = "button";
    remove.textContent = "移除";
    remove.addEventListener("click", function () {
      item.remove();
    });
    item.appendChild(label);
    item.appendChild(remove);
    list.appendChild(item);
  }

  function attach(doc) {
    var form = doc.getElementById("watchlist-form");
    var list = doc.getElementById("watchlist-items");
    var summary = doc.getElementById("watchlist-summary");
    var status = doc.getElementById("watchlist-status");
    var errorLine = doc.getElementById("watchlist-error");
    var searchInput = doc.getElementById("watchlist-search");
    var searchResults = doc.getElementById("watchlist-search-results");
    if (!form || !list) {
      return null;
    }

    if (searchInput && searchResults) {
      var debounced = global.ediaadParams
        ? global.ediaadParams.makeDebouncer(search, 200)
        : search;
      searchInput.addEventListener("input", debounced);
    }

    function search() {
      var keyword = text(searchInput.value);
      searchResults.textContent = "";
      if (!keyword) {
        return;
      }
      fetch("/api/instruments/search?source=twse&q=" + encodeURIComponent(keyword), {
        headers: { Accept: "application/json" }
      })
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          describeSearchResults(payload.items).forEach(function (line, index) {
            var item = doc.createElement("button");
            item.type = "button";
            item.textContent = line;
            item.addEventListener("click", function () {
              addRow(doc, list, payload.items[index]);
              searchResults.textContent = "";
              searchInput.value = "";
            });
            searchResults.appendChild(item);
          });
        })
        .catch(function () {
          searchResults.textContent = "商品搜尋失敗";
        });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var body;
      try {
        body = buildWatchlistBody(readRows(doc, list), {
          poll_interval_seconds: doc.getElementById("watchlist-interval")
            ? doc.getElementById("watchlist-interval").value
            : ""
        });
      } catch (error) {
        if (errorLine) { errorLine.textContent = error.message; }
        if (status) { status.textContent = "尚未儲存"; }
        return;
      }
      if (errorLine) { errorLine.textContent = ""; }
      fetch("/api/watchlist", {
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
            if (errorLine) { errorLine.textContent = describeError(result.payload); }
            if (status) { status.textContent = "儲存失敗"; }
            return;
          }
          renderLines(doc, summary, describeWatchlist(result.payload));
          if (status) { status.textContent = "已儲存，下一輪輪詢即生效"; }
        })
        .catch(function () {
          if (errorLine) { errorLine.textContent = describeError(null); }
        });
    });

    return { form: form, addRow: addRow };
  }

  global.ediaadWatchlist = {
    parseInstrumentRow: parseInstrumentRow,
    buildWatchlistBody: buildWatchlistBody,
    describeWatchlist: describeWatchlist,
    describeSearchResults: describeSearchResults,
    describeError: describeError,
    attach: attach
  };

  if (typeof document !== "undefined") {
    attach(document);
  }
})(typeof window !== "undefined" ? window : globalThis);
