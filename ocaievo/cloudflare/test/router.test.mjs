// 路由對照（TASK-033）：只有兩個公開端點，其餘一律可讀的 JSON 錯誤。

import assert from "node:assert/strict";
import test from "node:test";

import worker, { ROUTES, handleRequest } from "../worker/src/router.js";

import { createFakeD1 } from "./fake-d1.mjs";
import { FINGERPRINT, NOW_MS, insertKey, licenseEnv, request, schemaText } from "./support.mjs";

function setup() {
  const db = createFakeD1(schemaText());
  insertKey(db, { status: "active", machine: FINGERPRINT, expires_at: "2026-10-24T12:00:00Z" });
  return { db, env: licenseEnv({ DB: db, CATALOG_VERSION: "2026-10-01" }) };
}

test("路由表恰有四個端點（新增端點不會悄悄上線）", () => {
  // TASK-035 依 AC-063 加入公開重新申請頁，因此由兩個變成四個；這個測試的用途正是
  // 「端點變動必須被看見」——新增時就要一起更新它。
  assert.deepEqual(Object.keys(ROUTES).sort(), [
    "GET /reapply",
    "POST /reapply",
    "POST /v1/activate",
    "POST /v1/renew",
  ]);
});

test("POST /v1/activate 與 POST /v1/renew 都通", async () => {
  const { env } = setup();

  const activated = await handleRequest(
    request("/v1/activate", { key: "SECRET-0001", machine: FINGERPRINT }),
    env,
    { now: NOW_MS }
  );
  assert.equal(activated.status, 200);

  const renewed = await handleRequest(
    request("/v1/renew", { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" }),
    env,
    { now: NOW_MS }
  );
  assert.equal(renewed.status, 200);
});

test("路徑不存在回 404、方法不對回 405，皆為可讀 JSON", async () => {
  const { env } = setup();

  const missing = await handleRequest(request("/v1/nope", undefined, { method: "GET" }), env, { now: NOW_MS });
  assert.equal(missing.status, 404);
  const missingBody = await missing.json();
  assert.equal(missingBody.error.code, "not_found");

  const wrongMethod = await handleRequest(
    request("/v1/activate", undefined, { method: "GET" }),
    env,
    { now: NOW_MS }
  );
  assert.equal(wrongMethod.status, 405);
  const methodBody = await wrongMethod.json();
  assert.equal(methodBody.error.code, "method_not_allowed");
  assert.match(methodBody.message, /POST/);

  const text = JSON.stringify(methodBody);
  assert.doesNotMatch(text, /at .*\.mjs:/);
});

test("Worker 的預設 export 可以把請求交給同一個入口", async () => {
  const { env } = setup();

  const response = await worker.fetch(
    request("/v1/renew", { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "manual" }),
    env,
    { now: NOW_MS }
  );

  assert.equal(response.status, 200);
  assert.equal((await response.json()).key_id, "EDIAAD-2026-0001");
});
