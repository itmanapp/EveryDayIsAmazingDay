// 啟用端點（TASK-033／AC-060）：合法密鑰回 30 天簽章租約；撤銷與黑名單被拒絕。

import assert from "node:assert/strict";
import test from "node:test";

import { handleActivate, verifyLicenseKey } from "../worker/src/activate.js";
import { canonicalJson } from "../worker/src/lease.js";

import { createFakeD1 } from "./fake-d1.mjs";
import {
  EXPIRES_AT,
  FINGERPRINT,
  ISSUED_AT,
  NOW_MS,
  getKeyRow,
  insertBlacklist,
  insertKey,
  licenseEnv,
  request,
  schemaText,
  verifyLeaseSignature,
} from "./support.mjs";

function setup(envOverrides = {}) {
  const db = createFakeD1(schemaText());
  const env = licenseEnv({ DB: db, CATALOG_VERSION: "2026-10-01", ...envOverrides });
  return { db, env };
}

async function activate(db, env, body = { key: "SECRET-0001", machine: FINGERPRINT }, options = { now: NOW_MS }) {
  return handleActivate(request("/v1/activate", body), env, options);
}

const LEASE_KEYS = [
  "catalog_version",
  "expires_at",
  "features",
  "issued_at",
  "key_id",
  "machine",
  "sig",
];

test("合法密鑰回 30 天簽章租約並落地裝置", async () => {
  const { db, env } = setup();
  insertKey(db);

  const response = await activate(db, env);

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /application\/json/);
  const lease = await response.json();
  assert.deepEqual(Object.keys(lease).sort(), LEASE_KEYS);
  assert.equal(lease.key_id, "EDIAAD-2026-0001");
  assert.equal(lease.machine, FINGERPRINT);
  assert.equal(lease.issued_at, ISSUED_AT);
  assert.equal(lease.expires_at, EXPIRES_AT);
  assert.deepEqual(lease.features, ["start", "update"]);
  assert.equal(lease.catalog_version, "2026-10-01");
  assert.match(lease.sig, /^[0-9a-f]{128}$/);
  assert.equal(await verifyLeaseSignature(lease, canonicalJson), true);

  const keyRow = getKeyRow(db, "EDIAAD-2026-0001");
  assert.equal(keyRow.status, "active");
  assert.equal(keyRow.machine, FINGERPRINT);
  assert.equal(keyRow.expires_at, EXPIRES_AT);
  assert.equal(keyRow.activated_at, ISSUED_AT);

  const devices = db.prepare("SELECT * FROM devices").all().results;
  assert.equal(devices.length, 1);
  assert.equal(devices[0].fingerprint, FINGERPRINT);
  assert.equal(devices[0].key_id, "EDIAAD-2026-0001");
  assert.equal(devices[0].first_seen, ISSUED_AT);
  assert.equal(devices[0].last_seen, ISSUED_AT);

  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM renewals").first().n, 0, "啟用不寫 renewals");
});

test("裝置的 platform／version 是選填，帶了就如實記錄", async () => {
  const { db, env } = setup();
  insertKey(db);

  await activate(db, env, {
    key: "SECRET-0001",
    machine: FINGERPRINT,
    platform: "linux",
    version: "1.0.0",
  });

  const device = db.prepare("SELECT * FROM devices WHERE fingerprint = ?").bind(FINGERPRINT).first();
  assert.equal(device.platform, "linux");
  assert.equal(device.version, "1.0.0");
});

test("同一把密鑰重複啟用是幂等的：以新的現在時間重算 30 天", async () => {
  const { db, env } = setup();
  insertKey(db);
  await activate(db, env);

  const later = Date.parse("2026-09-30T12:00:00Z");
  const response = await activate(db, env, { key: "SECRET-0001", machine: FINGERPRINT }, { now: later });
  const lease = await response.json();

  assert.equal(lease.issued_at, "2026-09-30T12:00:00Z");
  assert.equal(lease.expires_at, "2026-10-30T12:00:00Z");
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, lease.expires_at);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM devices").first().n, 1);
  const device = db.prepare("SELECT * FROM devices WHERE fingerprint = ?").bind(FINGERPRINT).first();
  assert.equal(device.last_seen, "2026-09-30T12:00:00Z");
  assert.equal(device.first_seen, ISSUED_AT, "first_seen 只在第一次寫入，重複啟用不得覆蓋");
});

test("已撤銷的密鑰被拒絕（4xx）且不簽發、不落地", async () => {
  const { db, env } = setup();
  insertKey(db, { status: "revoked" });

  const response = await activate(db, env);

  assert.ok(response.status >= 400 && response.status < 500, `status=${response.status}`);
  const body = await response.json();
  assert.match(body.message, /撤銷/);
  assert.equal(body.lease, undefined);
  assert.equal(body.sig, undefined);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM devices").first().n, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, null, "被拒絕時不得延長到期");
});

test("黑名單指紋被拒絕（即使密鑰本身有效）", async () => {
  const { db, env } = setup();
  insertKey(db);
  insertBlacklist(db, FINGERPRINT);

  const response = await activate(db, env);

  assert.ok(response.status >= 400 && response.status < 500);
  const body = await response.json();
  assert.match(body.message, /黑名單/);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").status, "issued", "被拒絕時不得改變密鑰狀態");
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM devices").first().n, 0);
});

test("不存在的密鑰回 404 且訊息可讀", async () => {
  const { db, env } = setup();

  const response = await activate(db, env, { key: "NO-SUCH-KEY", machine: FINGERPRINT });

  assert.equal(response.status, 404);
  const body = await response.json();
  assert.equal(body.error.code, "unknown_key");
  assert.match(body.message, /找不到/);
});

test("verifyLicenseKey 以 secret 查詢並回傳整列（含已撤銷者）", async () => {
  const { db } = setup();
  insertKey(db, { status: "revoked" });

  const found = await verifyLicenseKey("SECRET-0001", { DB: db });
  assert.equal(found.key_id, "EDIAAD-2026-0001");
  assert.equal(found.status, "revoked");
  assert.equal(await verifyLicenseKey("WRONG", { DB: db }), null);
});

test("不合法請求一律回可讀 JSON 且不洩漏堆疊", async () => {
  const { db, env } = setup();
  insertKey(db);
  const cases = [
    [request("/v1/activate", { key: "SECRET-0001", machine: FINGERPRINT }, { method: "GET" }), 405, "method_not_allowed"],
    [request("/v1/activate", "{not json", { raw: true }), 400, "invalid_body"],
    [request("/v1/activate", ["not", "an", "object"]), 400, "invalid_body"],
    [request("/v1/activate", { machine: FINGERPRINT }), 400, "invalid_field"],
    [request("/v1/activate", { key: "   ", machine: FINGERPRINT }), 400, "invalid_field"],
    [request("/v1/activate", { key: "SECRET-0001" }), 400, "invalid_field"],
    [request("/v1/activate", { key: "SECRET-0001", machine: "NOT-HEX" }), 400, "invalid_field"],
    [request("/v1/activate", { key: "SECRET-0001", machine: "0123456789ABCDEF" }), 400, "invalid_field"],
  ];

  for (const [request_, expected, code] of cases) {
    const response = await handleActivate(request_, env, { now: NOW_MS });
    const text = await response.text();
    assert.equal(response.status, expected, text);
    const body = JSON.parse(text);
    assert.equal(body.error.code, code, text);
    assert.equal(typeof body.message, "string", "Python 客戶端的 _body_message 只讀字串的 message");
    assert.ok(body.message.length > 0);
    assert.doesNotMatch(text, /at .*\.mjs:/, "不得洩漏堆疊");
    assert.doesNotMatch(text, /TypeError|ReferenceError/);
  }

  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM devices").first().n, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").status, "issued");
});

test("後端沒有簽章私鑰時回 500：訊息固定、不洩漏設定內容", async () => {
  const db = createFakeD1(schemaText());
  insertKey(db);
  const env = { DB: db, CATALOG_VERSION: "2026-10-01" };

  const response = await handleActivate(request("/v1/activate", { key: "SECRET-0001", machine: FINGERPRINT }), env, {
    now: NOW_MS,
  });

  assert.equal(response.status, 500);
  const text = await response.text();
  assert.match(text, /內部錯誤/);
  assert.doesNotMatch(text, /LICENSE_PRIVATE_KEY_JWK|LeaseError|at .*\.mjs:/);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM devices").first().n, 0, "失敗時不留裝置紀錄");
});

test("catalog_version 的來源：密鑰列優先，其次是環境變數，最後是標示未知的佔位", async () => {
  const withRow = setup();
  insertKey(withRow.db, { catalog_version: "2026-11-01" });
  const rowLease = await (await activate(withRow.db, withRow.env)).json();
  assert.equal(rowLease.catalog_version, "2026-11-01");

  const withEnv = setup({ CATALOG_VERSION: "2026-12-01" });
  insertKey(withEnv.db);
  const envLease = await (await activate(withEnv.db, withEnv.env)).json();
  assert.equal(envLease.catalog_version, "2026-12-01");

  const neither = setup({ CATALOG_VERSION: "" });
  insertKey(neither.db);
  const fallback = await (await activate(neither.db, neither.env)).json();
  assert.equal(fallback.catalog_version, "unknown", "不得假造一個看起來真實的版本");
});
