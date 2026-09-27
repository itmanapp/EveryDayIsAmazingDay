// 續租端點（TASK-033／AC-060）：**過期租約必須回 403**、每次成功寫恰一筆 renewals 並記
// `trigger`、撤銷者被拒絕且不延長。

import assert from "node:assert/strict";
import test from "node:test";

import { canonicalJson } from "../worker/src/lease.js";
import { handleRenew } from "../worker/src/renew.js";

import { createFakeD1 } from "./fake-d1.mjs";
import {
  FINGERPRINT,
  NOW_MS,
  getKeyRow,
  insertBlacklist,
  insertKey,
  licenseEnv,
  renewals,
  request,
  schemaText,
  verifyLeaseSignature,
} from "./support.mjs";

const ACTIVE_KEY = {
  status: "active",
  machine: FINGERPRINT,
  expires_at: "2026-10-24T12:00:00Z",
  activated_at: "2026-09-24T12:00:00Z",
};

function setup(overrides = {}) {
  const db = createFakeD1(schemaText());
  const env = licenseEnv({ DB: db, CATALOG_VERSION: "2026-10-01" });
  insertKey(db, { ...ACTIVE_KEY, ...overrides });
  return { db, env };
}

async function renew(db, env, body, options = { now: NOW_MS }) {
  return handleRenew(request("/v1/renew", body), env, options);
}

test("成功續期：以新的現在時間重算 30 天並寫一筆 renewals", async () => {
  const { db, env } = setup();
  const now = Date.parse("2026-10-20T12:00:00Z");

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "timer" }, { now });

  assert.equal(response.status, 200);
  const lease = await response.json();
  assert.equal(lease.key_id, "EDIAAD-2026-0001");
  assert.equal(lease.machine, FINGERPRINT);
  assert.equal(lease.issued_at, "2026-10-20T12:00:00Z");
  assert.equal(lease.expires_at, "2026-11-19T12:00:00Z");
  assert.equal(
    (Date.parse(lease.expires_at) - Date.parse(lease.issued_at)) / 86400000,
    30
  );
  assert.ok(Date.parse(lease.expires_at) > Date.parse(ACTIVE_KEY.expires_at), "到期時間必須真的延後");
  assert.equal(await verifyLeaseSignature(lease, canonicalJson), true);

  const rows = renewals(db, "EDIAAD-2026-0001");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].trigger, "timer");
  assert.equal(rows[0].fingerprint, FINGERPRINT);
  assert.equal(rows[0].created_at, "2026-10-20T12:00:00Z");
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, lease.expires_at);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").last_renewed_at, "2026-10-20T12:00:00Z");
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").status, "active");
  assert.equal(
    db.prepare("SELECT last_seen FROM devices WHERE fingerprint = ?").bind(FINGERPRINT).first().last_seen,
    "2026-10-20T12:00:00Z"
  );
});

test("三種 trigger 各自如實落表（start／timer／manual）", async () => {
  const triggers = ["start", "timer", "manual"];

  for (const [index, trigger] of triggers.entries()) {
    const { db, env } = setup();
    const now = NOW_MS + index * 1000;
    const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger }, { now });

    assert.equal(response.status, 200, trigger);
    const rows = renewals(db, "EDIAAD-2026-0001");
    assert.equal(rows.length, 1, trigger);
    assert.equal(rows[0].trigger, trigger);
  }
});

test("**過期租約的續期回 403**：不寫 renewals、不延長到期、不簽發租約", async () => {
  const { db, env } = setup({ expires_at: "2026-09-01T00:00:00Z" });

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" });

  assert.equal(response.status, 403, "過期是導流閘門，必須 403");
  const body = await response.json();
  assert.equal(body.status, "expired");
  assert.match(body.message, /過期|重新申請/);
  assert.equal(body.sig, undefined, "不得附上任何租約");
  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, "2026-09-01T00:00:00Z");
});

test("到期時間讀不懂時 fail closed：回 403 而不是默默延長", async () => {
  const { db, env } = setup({ expires_at: "not-a-time" });

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" });

  assert.equal(response.status, 403);
  const body = await response.json();
  assert.equal(body.status, "expired");
  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, "not-a-time", "壞掉的到期日不得被覆寫成有效值");
});

test("已撤銷的密鑰回 403 且標示 status=revoked（客戶端據此落地撤銷標記）", async () => {
  const { db, env } = setup({ status: "revoked" });

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" });

  assert.equal(response.status, 403);
  const body = await response.json();
  assert.equal(body.status, "revoked");
  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, ACTIVE_KEY.expires_at);
});

test("黑名單指紋在續期時同樣被拒絕", async () => {
  const { db, env } = setup();
  insertBlacklist(db, FINGERPRINT);

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" });

  assert.equal(response.status, 403);
  const body = await response.json();
  assert.equal(body.status, "revoked");
  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
});

test("不存在的密鑰回 404；續期以 key_id 查詢（不是 secret）", async () => {
  const { db, env } = setup();

  const unknown = await renew(db, env, { key: "EDIAAD-9999-9999", machine: FINGERPRINT, trigger: "start" });
  assert.equal(unknown.status, 404);

  const withSecret = await renew(db, env, { key: "SECRET-0001", machine: FINGERPRINT, trigger: "start" });
  assert.equal(withSecret.status, 404, "secret 不是續期用的識別碼");

  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
});

test("換一台機器的續期被拒絕（409）且不帶 expired／revoked 標記", async () => {
  const { db, env } = setup({ machine: "ffffffffffffffff" });

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" });

  assert.equal(response.status, 409, "機器不符是衝突，不該混進導流用的 403");
  const body = await response.json();
  assert.equal(body.status, undefined, "不得讓客戶端誤以為要重新申請");
  assert.match(body.message, /機器/);
  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, ACTIVE_KEY.expires_at);
});

test("未綁定機器的密鑰首次續期會綁定目前這台", async () => {
  const { db, env } = setup({ machine: null });

  const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "manual" });

  assert.equal(response.status, 200);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").machine, FINGERPRINT);
});

test("非法 trigger 回 400 且不落表、不延長", async () => {
  const { db, env } = setup();
  const bodies = [
    { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "cron" },
    { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "" },
    { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: 42 },
    { key: "EDIAAD-2026-0001", machine: FINGERPRINT },
    { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "TIMER" },
  ];

  for (const body of bodies) {
    const response = await renew(db, env, body);
    assert.equal(response.status, 400, JSON.stringify(body));
    assert.match((await response.json()).message, /trigger/);
  }

  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 0);
  assert.equal(getKeyRow(db, "EDIAAD-2026-0001").expires_at, ACTIVE_KEY.expires_at);
});

test("不合法請求一律回可讀 JSON 且不洩漏堆疊", async () => {
  const { db, env } = setup();
  const cases = [
    [request("/v1/renew", { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "start" }, { method: "GET" }), 405],
    [request("/v1/renew", "{not json", { raw: true }), 400],
    [request("/v1/renew", { machine: FINGERPRINT, trigger: "start" }), 400],
    [request("/v1/renew", { key: "EDIAAD-2026-0001", trigger: "start" }), 400],
    [request("/v1/renew", { key: "EDIAAD-2026-0001", machine: "nope", trigger: "start" }), 400],
  ];

  for (const [request_, expected] of cases) {
    const response = await handleRenew(request_, env, { now: NOW_MS });
    assert.equal(response.status, expected);
    const text = await response.text();
    assert.match(text, /"error"/);
    assert.doesNotMatch(text, /at .*\.mjs:/);
  }
});

test("連續多次續期不會把到期日累加成非 30 天", async () => {
  const { db, env } = setup();

  for (const day of [20, 21, 22]) {
    const now = Date.parse(`2026-10-${day}T12:00:00Z`);
    const response = await renew(db, env, { key: "EDIAAD-2026-0001", machine: FINGERPRINT, trigger: "timer" }, { now });
    const lease = await response.json();
    assert.equal(
      (Date.parse(lease.expires_at) - Date.parse(lease.issued_at)) / 86400000,
      30,
      `第 ${day} 天`
    );
  }

  assert.equal(renewals(db, "EDIAAD-2026-0001").length, 3);
});
