// 即時提醒與事件歷史（TASK-021）。
// 去重的兩道防線：(1) 伺服器不會廣播重複的 event id；(2) 這裡以 id 記錄已顯示者，
// 因此重連（瀏覽器自動帶 Last-Event-ID）或手動重新載入歷史都不會重複顯示。
(function () {
  "use strict";

  var seen = new Set();
  var list = document.getElementById("event-list");
  var status = document.getElementById("event-status");
  var form = document.getElementById("event-filter");
  var count = document.getElementById("event-count");

  function eventKey(payload, id) {
    if (id) {
      return id;
    }
    return [payload.symbol, payload.interval, payload.pattern_id, payload.event_start_time].join("|");
  }

  function describe(payload) {
    var probability =
      payload.history_up_probability === null || payload.history_up_probability === undefined
        ? "無樣本"
        : "歷史上漲機率 " + Math.round(payload.history_up_probability * 100) + "%（" + payload.history_samples + " 次）";
    return (
      payload.symbol +
      " " +
      payload.interval +
      "：跌破後回歸（信心 " +
      payload.confidence +
      "，事件起點 " +
      payload.event_start_time +
      "，" +
      probability +
      "）"
    );
  }

  function render(payload) {
    var item = document.createElement("li");
    item.textContent = describe(payload);
    item.dataset.eventId = eventKey(payload, null);
    list.insertBefore(item, list.firstChild);
  }

  function accept(payload, id) {
    var key = eventKey(payload, id);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    render(payload);
    count.textContent = String(seen.size);
    return true;
  }

  function filterQuery() {
    var data = new FormData(form);
    var parts = [];
    ["symbol", "start", "end"].forEach(function (name) {
      var value = (data.get(name) || "").toString().trim();
      if (value) {
        parts.push(encodeURIComponent(name) + "=" + encodeURIComponent(value));
      }
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  function loadHistory() {
    status.textContent = "讀取事件歷史…";
    fetch("/api/events" + filterQuery(), { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (payload) {
        list.innerHTML = "";
        var events = payload.events || [];
        events.forEach(function (event) {
          accept(event, null);
        });
        status.textContent = "事件歷史：" + events.length + " 筆";
      })
      .catch(function (error) {
        status.textContent = "讀取事件歷史失敗：" + error;
      });
  }

  function connect() {
    var source = new EventSource("/api/events/stream");
    source.addEventListener("alert", function (message) {
      try {
        accept(JSON.parse(message.data), message.lastEventId);
      } catch (error) {
        status.textContent = "收到無法解析的提醒：" + error;
      }
    });
    source.onopen = function () {
      status.textContent = "即時提醒已連線（只在本機）";
      loadHistory();
    };
    source.onerror = function () {
      // EventSource 會自動重連並帶上 Last-Event-ID；伺服器不會重播已去重的事件。
      status.textContent = "即時提醒中斷，正在重連…";
    };
    return source;
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      seen.clear();
      count.textContent = "0";
      loadHistory();
    });
  }

  connect();
})();
