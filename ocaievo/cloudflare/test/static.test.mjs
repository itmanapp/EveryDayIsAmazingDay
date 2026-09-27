// 靜態 manifest 與 catalog（TASK-034／AC-061）。
//
// 這一張的核心是「兩個端點必須是**純靜態**的」：它們由靜態主機（Pages／R2）提供，
// **刻意不經過 Worker**（Worker 掛掉時仍要可讀，報告第 6.5 節）。因此測試除了驗 schema
// 與快取標頭，還要以「毒環境」證明回應函式完全不需要 D1，並以原始碼檢查證明它不匯入
// activate／renew／db。

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  MANIFEST_KEYS,
  catalogResponse,
  manifestResponse,
  validateCatalog,
  validateManifest,
  validateSnapshot,
} from "../worker/src/static.js";

import { ROOT } from "./support.mjs";

function readJson(relative) {
  return JSON.parse(readFileSync(join(ROOT, relative), "utf8"));
}

const latest = () => readJson("static/latest.json");
const catalog = () => readJson("static/catalog.json");

/** 只要有任何一行存取 env 的屬性（例如 env.DB）就會爆——證明靜態回應不碰任何綁定。 */
const poisonEnv = new Proxy(
  {},
  {
    get(_target, name) {
      throw new Error(`靜態回應不得存取 env.${String(name)}`);
    },
  }
);

test("manifest 快照的鍵集合恰為凍結 schema 的十個", () => {
  const manifest = latest();

  assert.deepEqual(validateManifest(manifest), []);
  assert.deepEqual(Object.keys(manifest).sort(), [...MANIFEST_KEYS].sort());
  assert.equal(manifest.schema, 1);
});

test("manifest 快照的欄位形狀（型別與格式）", () => {
  const manifest = latest();

  assert.equal(typeof manifest.version, "string");
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
  assert.match(manifest.released_at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  assert.match(manifest.catalog_version, /^\d{4}-\d{2}-\d{2}$/);
  assert.match(manifest.sha256, /^[0-9a-f]{64}$/);
  assert.ok(Number.isInteger(manifest.size) && manifest.size >= 0);
  assert.equal(typeof manifest.notes, "string");
  for (const field of ["catalog_url", "url"]) {
    assert.match(manifest[field], /^https:\/\//, field);
  }
});

test("manifest 的 url／sha256／size 是佔位值：不得指向真實網域，也不下載", () => {
  const manifest = latest();

  // 佔位網域一律用保留的 `.invalid`（不可能解析到真實主機）。
  assert.match(new URL(manifest.url).hostname, /\.invalid$/);
  assert.match(new URL(manifest.catalog_url).hostname, /\.invalid$/);
  assert.equal(manifest.sha256, "0".repeat(64), "佔位內容要用一眼看得出來的值");
  assert.equal(manifest.size, 0);
});

test("catalog 快照符合 SPEC 第 5 節的 Catalog 契約", () => {
  const data = catalog();

  assert.deepEqual(validateCatalog(data), []);
  assert.match(data.catalog_version, /^\d{4}-\d{2}-\d{2}$/);
  assert.ok(data.sources.length > 0);
  assert.ok(data.instruments.length > 0);
  for (const source of data.sources) {
    assert.ok(typeof source.id === "string" && source.id.length > 0);
    assert.ok(Array.isArray(source.supported_intervals));
  }
  for (const instrument of data.instruments) {
    assert.ok(typeof instrument.symbol === "string" && instrument.symbol.length > 0);
    assert.ok(typeof instrument.interval === "string");
    assert.ok(typeof instrument.source_id === "string");
  }
  const ids = data.sources.map((source) => source.id);
  for (const instrument of data.instruments) {
    assert.ok(ids.includes(instrument.source_id), `${instrument.symbol} 的來源必須存在於 sources`);
  }
});

test("兩個快照的 catalog_version 必須來自同一份快照", () => {
  const manifest = latest();
  const data = catalog();

  assert.deepEqual(validateSnapshot(manifest, data), []);
  assert.equal(manifest.catalog_version, data.catalog_version);
});

test("版本錯位一定會被發現（刻意讓兩者不同）", () => {
  const manifest = latest();
  const data = catalog();

  const mismatched = { ...data, catalog_version: "2099-12-31" };
  const errors = validateSnapshot(manifest, mismatched);
  assert.ok(errors.length > 0);
  assert.ok(errors.some((error) => error.includes("catalog_version")), errors.join("、"));
});

test("manifest 的缺鍵／多鍵／型別錯都會被指出欄位名", () => {
  const manifest = latest();
  const cases = [
    [{ ...manifest, schema: 2 }, "schema"],
    [{ ...manifest, version: "0.4" }, "version"],
    [{ ...manifest, notes: 42 }, "notes"],
    [{ ...manifest, size: "1024" }, "size"],
    [{ ...manifest, sha256: "abc" }, "sha256"],
    [{ ...manifest, released_at: "2026-10-01" }, "released_at"],
    [{ ...manifest, catalog_version: "2026/10/01" }, "catalog_version"],
    [{ ...manifest, url: "not-a-url" }, "url"],
  ];
  for (const [payload, field] of cases) {
    const errors = validateManifest(payload);
    assert.ok(errors.length > 0, field);
    assert.ok(errors.some((error) => error.includes(field)), `${field}: ${errors.join("、")}`);
  }

  const { notes, ...missing } = manifest;
  assert.ok(validateManifest(missing).some((error) => error.includes("notes")));
  assert.ok(validateManifest({ ...manifest, extra: 1 }).some((error) => error.includes("extra")));
  assert.ok(validateManifest(null).length > 0);
  assert.ok(validateManifest([]).length > 0);
});

test("catalog 的來源與商品結構錯誤會被指出位置", () => {
  const data = catalog();
  const cases = [
    [{ ...data, catalog_version: "2026/10/01" }, "catalog_version"],
    [{ ...data, sources: [] }, "sources"],
    [{ ...data, instruments: [] }, "instruments"],
    [{ ...data, sources: [{ id: "" }] }, "sources[0]"],
    [{ ...data, sources: [{ id: "twse", extra: 1 }] }, "extra"],
    [{ ...data, instruments: [{ symbol: "2330" }] }, "interval"],
    [{ ...data, instruments: [{ interval: "1d" }] }, "symbol"],
    [{ ...data, instruments: [{ symbol: "2333", interval: "1d", source_id: "nope" }] }, "source_id"],
    [{ ...data, sources: "not-an-array" }, "sources"],
  ];
  for (const [payload, fragment] of cases) {
    const errors = validateCatalog(payload);
    assert.ok(errors.length > 0, fragment);
    assert.ok(errors.some((error) => error.includes(fragment)), `${fragment}: ${errors.join("、")}`);
  }
});

test("兩個回應都有可快取標頭且內容就是快照本身", () => {
  for (const [response, snapshot] of [
    [manifestResponse(latest()), latest()],
    [catalogResponse(catalog()), catalog()],
  ]) {
    assert.equal(response.status, 200);
    assert.match(response.headers["content-type"], /application\/json/);
    const cache = response.headers["cache-control"];
    assert.match(cache, /public/);
    assert.match(cache, /max-age=\d+/);
    assert.match(cache, /stale-while-revalidate=\d+/);
    assert.deepEqual(JSON.parse(response.body), snapshot);
  }
});

test("靜態回應完全不需要 D1 或任何 env 綁定", () => {
  assert.equal(manifestResponse(latest(), poisonEnv).status, 200);
  assert.equal(catalogResponse(catalog(), poisonEnv).status, 200);
  assert.equal(manifestResponse(latest()).status, 200);
  assert.equal(catalogResponse(catalog()).status, 200);

  // 原始碼層級：不得匯入會碰 D1 或授權流程的模組。
  const source = readFileSync(join(ROOT, "worker", "src", "static.js"), "utf8");
  for (const forbidden of ["./db.js", "./activate.js", "./renew.js", "./router.js"]) {
    assert.ok(!source.includes(forbidden), `static.js 不得匯入 ${forbidden}`);
  }
  assert.ok(!source.includes(".prepare("), "static.js 不得查詢 D1");
});

test("快照不合法時回 500 與可讀訊息，且不洩漏堆疊", () => {
  const broken = { ...latest(), schema: 2 };

  const response = manifestResponse(broken, poisonEnv);

  assert.equal(response.status, 500);
  const body = JSON.parse(response.body);
  assert.equal(body.error.code, "invalid_snapshot");
  assert.ok(body.error.details.length > 0);
  assert.doesNotMatch(response.body, /at .*\.mjs:/);
});

test("wrangler.toml 記錄了靜態端點的對照且不填真實網域", () => {
  const text = readFileSync(join(ROOT, "wrangler.toml"), "utf8");

  assert.match(text, /\/v1\/latest/);
  assert.match(text, /catalog\.json/);
  assert.match(text, /\.invalid/);
  assert.doesNotMatch(text, /\b[0-9a-f]{32}\b/i);
});
