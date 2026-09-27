// K 線圖頁的黏著層：向後端取序列與事件，交給 chart.js 繪製，並列出文字摘要。
(function () {
  "use strict";

  var chart = window.ediaadChart;
  var form = document.getElementById("chart-form");
  var status = document.getElementById("chart-status");
  var canvas = document.getElementById("chart-canvas");
  var summary = document.getElementById("event-summary");
  var detail = document.getElementById("chart-summary");

  function query() {
    var data = new FormData(form);
    var parts = [];
    ["symbol", "interval", "source", "limit"].forEach(function (name) {
      var value = (data.get(name) || "").toString().trim();
      if (value) {
        parts.push(encodeURIComponent(name) + "=" + encodeURIComponent(value));
      }
    });
    return parts.join("&");
  }

  function draw(bars, events) {
    var context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    var viewport = chart.makeViewport(bars, canvas.width, canvas.height, {
      top: 24,
      right: 24,
      bottom: 32,
      left: 48
    });
    chart.drawCandles(context, bars, viewport);
    events.forEach(function (event) {
      chart.drawPhases(context, chart.phaseMarkers(event, bars, viewport), viewport);
    });
  }

  function listSummaries(events) {
    summary.innerHTML = "";
    detail.innerHTML = "";
    events.forEach(function (event, position) {
      var holder = document.createElement("div");
      chart.renderSummary(holder, event);
      var item = document.createElement("li");
      item.appendChild(holder);
      summary.appendChild(item);
      if (position === 0) {
        chart.renderSummary(detail, event);
      }
    });
  }

  function load() {
    status.textContent = "載入序列與事件…";
    var parameters = query();
    Promise.all([
      fetch("/api/series?" + parameters, { headers: { Accept: "application/json" } }).then(readJson),
      fetch("/api/patterns/events?" + parameters, { headers: { Accept: "application/json" } }).then(readJson)
    ])
      .then(function (results) {
        var bars = results[0];
        var events = results[1];
        draw(bars, events.events || []);
        listSummaries(events.events || []);
        status.textContent =
          "共 " + bars.count + " 根（來源 " + bars.source + "）；" + events.message ? events.message : "已標註 " + (events.events || []).length + " 個事件";
        if (events.dropped) {
          status.textContent += "；有 " + events.dropped + " 個事件的索引超出序列範圍，已略過";
        }
      })
      .catch(function (error) {
        status.textContent = "載入失敗：" + error;
      });
  }

  function readJson(response) {
    return response.json().then(function (payload) {
      if (!response.ok) {
        throw new Error((payload.error && payload.error.message) || "HTTP " + response.status);
      }
      return payload;
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    load();
  });
  load();
})();
