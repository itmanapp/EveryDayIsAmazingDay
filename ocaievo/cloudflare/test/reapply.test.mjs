// 公開重新申請頁（TASK-035／AC-063）：過期者可自助重新申請；黑名單指紋自動拒絕。
//
// 產生新密鑰之後會**真的走一次 TASK-033 的啟用流程**（`handleActivate`），證明「重新申請
// 拿到的密鑰可用」不是宣稱；黑名單與未過期者則必須「不產生密鑰、不留可啟用的紀錄」。

import assert from "node:assert/strict";
import test from "node:test";

import { handleActivate } from "../worker/src/activate.js";
import { revokeKey } from "../worker/src/admin.js";
import { handleReapply, handleReapplyPage, isBlacklisted, findExpiredKey } from "../worker/src/reapply.js";
import { handleRequest } from "../worker/src/router.js";

import { createFakeD1 } from "./fake-d1.mjs";
import {
  FINGERPRINT,
  NOW_MS,
  insertBlacklist,
  licenseEnv,
  request,
  schemaText,
} from "./support.mjs";

const STAMP = "2026-09-24T12:00:00Z";
const EXPIRED = "2026-09-01T00:00:00Z";
const VALID = "2026-10-24T12:00:00Z";

function setup() {
  const db = createFakeD1(schemaText());
  const env = licenseEnv({ DB: db, CATALOG_VERSION: "2026-10-01" });
  return { db, env };
}

function seedKey(db, { keyId = "EDIAAD-2026-0001", secret = "secret-0001".padEnd(32, "0"), status = "active", expires = EXPIRED, machine = FINGERPRINT } = {}) {
  db.prepare(
    "INSERT INTO keys (key_id, secret, status, features, expires_at, machine, created_at, activated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
  )
    .bind(keyId, secret, status, '["start","update"]', expires, machine, STAMP, STAMP)
    .run();
  // 同一個指紋可以有多把密鑰（重新申請就是這樣），裝置列以指紋為主鍵、指向最新的密鑰。
  db.prepare(
    `INSERT INTO devices (fingerprint, key_id, platform, version, first_seen, last_seen)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(fingerprint) DO UPDATE SET key_id = excluded.key_id, last_seen = excluded.last_seen`
  )
    .bind(machine, keyId, "linux", "1.0.0", STAMP, STAMP)
    .run();
  return { keyId, secret };
}

const keyCount = (db) => db.prepare("SELECT COUNT(*) AS n FROM keys").first().n;
const auditRows = (db) => db.prepare("SELECT * FROM audit ORDER BY id").all().results;

test("過期者自助重新申請：新密鑰可立刻走啟用流程", async () => {
  const { db, env } = setup();
  seedKey(db);

  const response = await handleReapply(
    request("/reapply", { fingerprint: FINGERPRINT, platform: "linux" }),
    env,
    { now: NOW_MS }
  );

  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.key_id, "EDIAAD-2026-0002");
  assert.match(body.secret, /^[0-9a-f]{32}$/);
  assert.equal(body.status, "issued");
  assert.match(body.message, /啟用/);
  assert.equal(keyCount(db), 2);
  assert.equal(db.prepare("SELECT status FROM keys WHERE key_id = ?").bind(body.key_id).first().status, "issued");
  const audit = auditRows(db);
  assert.equal(audit.length, 1);
  assert.equal(audit[0].action, "reapply");
  assert.match(audit[0].actor, /reapply/);

  // 新密鑰真的能用（走 TASK-033 的啟用端點）
  const activated = await handleActivate(
    request("/v1/activate", { key: body.secret, machine: FINGERPRINT }),
    env,
    { now: NOW_MS }
  );
  assert.equal(activated.status, 200, await activated.clone().text());
  assert.equal((await activated.json()).key_id, body.key_id);
});

test("黑名單指紋自動拒絕，且不產生密鑰、不留稽核", async () => {
  const { db, env } = setup();
  seedKey(db);
  insertBlacklist(db, FINGERPRINT, { reason: "已撤銷" });

  assert.equal(await isBlacklisted(db, FINGERPRINT), true);

  const response = await handleReapply(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });

  assert.ok(response.status >= 400 && response.status < 500, `status=${response.status}`);
  const body = await response.json();
  assert.match(body.message, /黑名單/);
  assert.equal(body.secret, undefined, "不得把任何密鑰給黑名單指紋");
  assert.equal(keyCount(db), 1, "不得新增密鑰");
  assert.equal(auditRows(db).length, 0, "不得留下可啟用的紀錄");
});

test("撤銷過的密鑰：指紋進黑名單後連重新申請都被拒絕", async () => {
  const { db, env } = setup();
  seedKey(db, { expires: VALID });
  await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  const response = await handleReapply(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });

  assert.ok(response.status >= 400 && response.status < 500);
  assert.match((await response.json()).message, /黑名單|撤銷/);
  assert.equal(keyCount(db), 1);
});

test("已撤銷但沒有黑名單紀錄的密鑰仍被拒絕（資料被手動改過也不放行）", async () => {
  const { db, env } = setup();
  seedKey(db, { status: "revoked" });

  const response = await handleReapply(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });

  assert.equal(response.status, 403);
  assert.match((await response.json()).message, /撤銷/);
  assert.equal(keyCount(db), 1, "不得新增密鑰");
  assert.equal(auditRows(db).length, 0);
});

test("features 欄位壞掉時用預設功能，不讓重新申請變成 500", async () => {
  const { db, env } = setup();
  seedKey(db);
  db.prepare("UPDATE keys SET features = ?").bind("{not json").run();

  const response = await handleReapply(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });

  assert.equal(response.status, 200, await response.clone().text());
  const body = await response.json();
  assert.deepEqual(body.features, ["start", "update"]);
  const created = db.prepare("SELECT features FROM keys WHERE key_id = ?").bind(body.key_id).first();
  assert.deepEqual(JSON.parse(created.features), ["start", "update"]);
});

test("授權仍在有效期內者不發新密鑰", async () => {
  const { db, env } = setup();
  seedKey(db, { expires: VALID });

  const response = await handleReapply(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });

  assert.equal(response.status, 409);
  const body = await response.json();
  assert.match(body.message, /有效期|不需要/);
  assert.match(body.message, new RegExp(VALID));
  assert.equal(body.secret, undefined);
  assert.equal(keyCount(db), 1);
  assert.equal(auditRows(db).length, 0);
});

test("完全沒有紀錄的指紋回 404 而不是誤發密鑰", async () => {
  const { db, env } = setup();

  const response = await handleReapply(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });

  assert.equal(response.status, 404);
  assert.match((await response.json()).message, /找不到/);
  assert.equal(keyCount(db), 0);
  assert.equal(auditRows(db).length, 0);
});

test("findExpiredKey 只認已過期者，且取最近到期的一把", async () => {
  const { db } = setup();
  seedKey(db, { keyId: "EDIAAD-2026-0001", expires: "2026-08-01T00:00:00Z" });
  seedKey(db, { keyId: "EDIAAD-2026-0002", expires: EXPIRED, secret: "secret-2".padEnd(32, "0") });

  const found = await findExpiredKey(db, FINGERPRINT, { now: NOW_MS });
  assert.equal(found.key_id, "EDIAAD-2026-0002");
  assert.equal(await findExpiredKey(db, "ffffffffffffffff", { now: NOW_MS }), null);

  db.prepare("UPDATE keys SET expires_at = ?").bind(VALID).run();
  assert.equal(await findExpiredKey(db, FINGERPRINT, { now: NOW_MS }), null, "未過期就不是重新申請的對象");
});

test("重新申請的請求驗證：方法、主體、指紋格式", async () => {
  const { db, env } = setup();
  seedKey(db);

  const cases = [
    [request("/reapply", { fingerprint: FINGERPRINT }, { method: "GET" }), 405],
    [request("/reapply", "{not json", { raw: true }), 400],
    [request("/reapply", ["nope"]), 400],
    [request("/reapply", {}), 400],
    [request("/reapply", { fingerprint: "NOT-HEX" }), 400],
    [request("/reapply", { fingerprint: "0123456789ABCDEF" }), 400],
  ];
  for (const [request_, expected] of cases) {
    const response = await handleReapply(request_, env, { now: NOW_MS });
    assert.equal(response.status, expected);
    const text = await response.text();
    assert.match(text, /"error"/);
    assert.doesNotMatch(text, /at .*\.mjs:/);
  }
  assert.equal(keyCount(db), 1);

  // `machine` 可以當 `fingerprint` 的別名（與 activate 的欄位名一致）
  const alias = await handleReapply(request("/reapply", { machine: "ffffffffffffffff" }), env, { now: NOW_MS });
  assert.equal(alias.status, 404);
});

test("重新申請頁是最小可用的 HTML：表單欄位與端點都在", async () => {
  const response = await handleReapplyPage(request("/reapply", undefined, { method: "GET" }));

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /text\/html/);
  const html = await response.text();
  assert.match(html, /<form/);
  assert.match(html, /name="fingerprint"/);
  assert.match(html, /\/reapply/);
  assert.match(html, /機器指紋|fingerprint/);
  assert.doesNotMatch(html, /<script src=/, "不得依賴外部資源");
});

test("路由掛上重新申請頁（GET 與 POST）", async () => {
  const { db, env } = setup();
  seedKey(db);

  const page = await handleRequest(request("/reapply", undefined, { method: "GET" }), env, { now: NOW_MS });
  assert.equal(page.status, 200);
  assert.match(await page.text(), /<form/);

  const submit = await handleRequest(request("/reapply", { fingerprint: FINGERPRINT }), env, { now: NOW_MS });
  assert.equal(submit.status, 200);
  assert.equal((await submit.json()).key_id, "EDIAAD-2026-0002");

  const wrongMethod = await handleRequest(request("/reapply", undefined, { method: "PUT" }), env, { now: NOW_MS });
  assert.equal(wrongMethod.status, 405);
});
