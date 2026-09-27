// K 線圖與三相位標註（TASK-022）。
//
// 設計：**幾何換算集中在 `xFor`／`yFor`**，其餘函式只使用它們的結果。相位索引一律來自
// 後端 `detect` 的 JSON（前端不重跑偵測、不自行推導相位），因此「標記的水平位置與事件
// 索引一致」是由 `phaseMarkers` 直接以 `xFor(index)` 換算保證的。
//
// 無外部依賴、無 Node 建置工具鏈；載入時不碰 DOM（函式被呼叫時才碰），因此測試可以直接
// 在 Node 裡載入並驗證幾何。
(function (global) {
  "use strict";

  var PHASE_LABELS = {
    range: "盤整",
    breakdown: "假跌破",
    recovery: "回歸"
  };

  function extent(values, fallback) {
    var min = Infinity;
    var max = -Infinity;
    values.forEach(function (value) {
      if (typeof value !== "number" || !isFinite(value)) {
        return;
      }
      if (value < min) {
        min = value;
      }
      if (value > max) {
        max = value;
      }
    });
    if (!isFinite(min) || !isFinite(max)) {
      return [fallback - 1, fallback + 1];
    }
    if (min === max) {
      return [min - 1, max + 1];
    }
    return [min, max];
  }

  function makeViewport(bars, width, height, padding) {
    var pad = padding || { top: 10, right: 20, bottom: 30, left: 40 };
    var prices = (bars.low || []).concat(bars.high || []);
    var span = extent(prices, 0);
    var minPrice = span[0];
    var maxPrice = span[1];
    return {
      width: width,
      height: height,
      padding: { top: pad.top, right: pad.right, bottom: pad.bottom, left: pad.left },
      count: (bars.close || []).length,
      minPrice: minPrice,
      maxPrice: maxPrice,
      priceSpan: maxPrice - minPrice,
      plotWidth: width - pad.left - pad.right,
      plotHeight: height - pad.top - pad.bottom
    };
  }

  // 索引 → 像素：單一根佔一個等寬槽位，回傳槽位中心。
  function xFor(index, viewport) {
    var slot = viewport.plotWidth / viewport.count;
    return viewport.padding.left + (index + 0.5) * slot;
  }

  // 價格 → 像素：螢幕座標向下，因此價格越高 y 越小。
  function yFor(price, viewport) {
    var ratio = (viewport.maxPrice - price) / viewport.priceSpan;
    return viewport.padding.top + ratio * viewport.plotHeight;
  }

  function candleGeometry(bars, viewport) {
    var candles = [];
    for (var index = 0; index < viewport.count; index += 1) {
      var open = bars.open[index];
      var close = bars.close[index];
      candles.push({
        index: index,
        x: xFor(index, viewport),
        highY: yFor(bars.high[index], viewport),
        lowY: yFor(bars.low[index], viewport),
        openY: yFor(open, viewport),
        closeY: yFor(close, viewport),
        rising: close >= open
      });
    }
    return candles;
  }

  function phaseMarkers(event, bars, viewport) {
    var from = event.range_start_index;
    var to = event.range_end_index;
    var rangeHigh = -Infinity;
    var rangeLow = Infinity;
    for (var index = from; index <= to; index += 1) {
      if (bars.high[index] > rangeHigh) {
        rangeHigh = bars.high[index];
      }
      if (bars.low[index] < rangeLow) {
        rangeLow = bars.low[index];
      }
    }

    return [
      {
        phase: "range",
        label: PHASE_LABELS.range,
        shape: "rect",
        from: from,
        to: to,
        x: xFor(from, viewport),
        x2: xFor(to, viewport),
        y: yFor(rangeHigh, viewport),
        height: yFor(rangeLow, viewport) - yFor(rangeHigh, viewport)
      },
      {
        phase: "breakdown",
        label: PHASE_LABELS.breakdown,
        shape: "triangle-down",
        index: event.breakdown_index,
        x: xFor(event.breakdown_index, viewport),
        y: yFor(bars.low[event.breakdown_index], viewport)
      },
      {
        phase: "recovery",
        label: PHASE_LABELS.recovery,
        shape: "triangle-up",
        index: event.recovery_index,
        x: xFor(event.recovery_index, viewport),
        y: yFor(bars.high[event.recovery_index], viewport)
      }
    ];
  }

  function summaryLines(event) {
    var probability =
      event.history_up_probability === null || event.history_up_probability === undefined
        ? "無樣本"
        : Math.round(event.history_up_probability * 100) + "%（" + event.history_samples + " 次）";
    return [
      "規律：" + event.pattern_id + "（信心 " + Number(event.confidence).toFixed(3) + "）",
      "盤整相位：第 " + event.range_start_index + " 根到第 " + event.range_end_index + " 根",
      "假跌破：第 " + event.breakdown_index + " 根（深度 " + Number(event.breakdown_depth).toFixed(2) + " 個帶寬）",
      "回歸：第 " + event.recovery_index + " 根（" + event.recovery_bars + " 根內完成）",
      "後續走勢歷史機率：" + probability
    ];
  }

  function drawCandles(ctx, bars, viewport) {
    var candles = candleGeometry(bars, viewport);
    ctx.save();
    ctx.strokeStyle = "#444";
    ctx.fillStyle = "#888";
    ctx.beginPath();
    candles.forEach(function (candle) {
      ctx.moveTo(candle.x, candle.highY);
      ctx.lineTo(candle.x, candle.lowY);
    });
    ctx.stroke();
    candles.forEach(function (candle) {
      var top = Math.min(candle.openY, candle.closeY);
      var bodyHeight = Math.max(1, Math.abs(candle.closeY - candle.openY));
      ctx.fillStyle = candle.rising ? "#1b7f4b" : "#a12020";
      ctx.fillRect(candle.x - 2, top, 4, bodyHeight);
    });
    ctx.restore();
    return candles;
  }

  function drawPhases(ctx, phases, viewport) {
    var markers = Array.isArray(phases) ? phases : phaseMarkers(phases, phases._bars || {}, viewport);
    ctx.save();
    ctx.lineWidth = 2;
    ctx.font = "12px system-ui, sans-serif";
    markers.forEach(function (marker) {
      ctx.beginPath();
      if (marker.shape === "rect") {
        ctx.strokeStyle = "#14507a";
        ctx.setLineDash([4, 3]);
        ctx.rect(marker.x - 4, marker.y, marker.x2 - marker.x + 8, marker.height);
        ctx.stroke();
        ctx.setLineDash([]);
      } else if (marker.shape === "triangle-down") {
        ctx.fillStyle = "#a12020";
        ctx.moveTo(marker.x, marker.y + 12);
        ctx.lineTo(marker.x - 6, marker.y + 2);
        ctx.lineTo(marker.x + 6, marker.y + 2);
        ctx.closePath();
        ctx.fill();
      } else {
        ctx.fillStyle = "#1b7f4b";
        ctx.moveTo(marker.x, marker.y - 12);
        ctx.lineTo(marker.x - 6, marker.y - 2);
        ctx.lineTo(marker.x + 6, marker.y - 2);
        ctx.closePath();
        ctx.fill();
      }
      // 文字標註：即使不看顏色也能辨識相位。
      ctx.fillStyle = "#111";
      ctx.fillText(marker.label, marker.x - 12, marker.y - 16);
    });
    ctx.restore();
    return markers;
  }

  function renderSummary(el, event) {
    if (!el) {
      return [];
    }
    var lines = summaryLines(event);
    var doc = el.ownerDocument || global.document;
    el.textContent = "";
    lines.forEach(function (line) {
      var item = doc.createElement("p");
      item.textContent = line;
      el.appendChild(item);
    });
    return lines;
  }

  global.ediaadChart = {
    PHASE_LABELS: PHASE_LABELS,
    makeViewport: makeViewport,
    xFor: xFor,
    yFor: yFor,
    candleGeometry: candleGeometry,
    phaseMarkers: phaseMarkers,
    summaryLines: summaryLines,
    drawCandles: drawCandles,
    drawPhases: drawPhases,
    renderSummary: renderSummary
  };
})(typeof window !== "undefined" ? window : globalThis);
