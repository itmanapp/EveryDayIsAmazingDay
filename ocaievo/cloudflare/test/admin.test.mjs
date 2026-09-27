// 後台操作（TASK-035／AC-062）：批次產生密鑰、清單與搜尋、撤銷／恢復／延長、統計與稽核。
//
// 全部建立在**真的 SQL** 上（`test/fake-d1.mjs` 用 `node:sqlite`），因此欄位名、UNIQUE 與
// CHECK 約束、以及每一句查詢的語法都是真的被資料庫檢查過。

import assert from "node:assert/strict";
import test from "node:test";

import {
  auditLog,
  extendKey,
  generateKeys,
  listKeys,
  restoreKey,
  revokeKey,
  stats,
} from "../worker/src/admin.js";

import { createFakeD1 } from "./fake-d1.mjs";
import { FINGERPRINT, NOW_MS, schemaText } from "./support.mjs";

const STAMP = "2026-09-24T12:00:00Z";

function setup() {
  return createFakeD1(schemaText());
}

/** 可預期的假密鑰：`deadbeef` ＋ key_id 的序號 ＋ 補滿 32 個十六進位字元。 */
function fixedSecret(_index, keyId) {
  return `deadbeef${keyId.slice(-4)}`.padEnd(32, "f");
}

async function makeKeys(db, count = 1, features = ["start", "update"], actor = "作者") {
  return generateKeys(db, count, features, actor, { now: NOW_MS, secretFactory: fixedSecret });
}

function auditRows(db) {
  return db.prepare("SELECT * FROM audit ORDER BY id").all().results;
}

test("批次產生：狀態未啟用、features 如實、恰留一筆稽核", async () => {
  const db = setup();

  const created = await makeKeys(db, 3, ["start", "update"], "作者");

  assert.equal(created.length, 3);
  assert.deepEqual(created.map((row) => row.key_id), [
    "EDIAAD-2026-0001",
    "EDIAAD-2026-0002",
    "EDIAAD-2026-0003",
  ]);
  for (const row of created) {
    assert.equal(row.status, "issued");
    assert.deepEqual(row.features, ["start", "update"]);
    assert.equal(row.expires_at, null, "尚未啟用就沒有到期日");
    assert.match(row.secret, /^[0-9a-f]{32}$/);
  }
  const rows = db.prepare("SELECT * FROM keys ORDER BY key_id").all().results;
  assert.equal(rows.length, 3);
  assert.equal(rows[0].created_at, STAMP);
  assert.equal(JSON.parse(rows[0].features).length, 2);

  const audit = auditRows(db);
  assert.equal(audit.length, 1, "一批只留一筆稽核");
  assert.equal(audit[0].actor, "作者");
  assert.equal(audit[0].action, "generate_keys");
  assert.match(audit[0].target, /EDIAAD-2026-0001/);
  assert.equal(audit[0].created_at, STAMP);
});

test("序號接續既有密鑰，刪除後也不重用", async () => {
  const db = setup();
  await makeKeys(db, 3);

  db.prepare("DELETE FROM keys WHERE key_id = ?").bind("EDIAAD-2026-0002").run();
  const created = await makeKeys(db, 1);

  assert.deepEqual(created.map((row) => row.key_id), ["EDIAAD-2026-0004"]);
});

test("不合法參數一律拒絕且不留任何痕跡", async () => {
  const db = setup();
  const cases = [
    [0, ["start"]],
    [-1, ["start"]],
    ["3", ["start"]],
    [101, ["start"]],
    [2.5, ["start"]],
    [1, []],
    [1, [""]],
    [1, "start"],
    [1, ["start", "start"]],
  ];
  for (const [count, features] of cases) {
    await assert.rejects(
      () => generateKeys(db, count, features, "作者", { now: NOW_MS }),
      (error) => error instanceof Error && error.message.length > 0,
      `${count}/${JSON.stringify(features)}`
    );
  }
  await assert.rejects(() => generateKeys(db, 1, ["start"], "", { now: NOW_MS }), /actor/);

  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM keys").first().n, 0);
  assert.equal(auditRows(db).length, 0);
});

test("預設密鑰用 WebCrypto 產生且不重複", async () => {
  const db = setup();

  const created = await generateKeys(db, 20, ["start"], "作者", { now: NOW_MS });

  const secrets = new Set(created.map((row) => row.secret));
  assert.equal(secrets.size, 20);
  for (const secret of secrets) {
    assert.match(secret, /^[0-9a-f]{32}$/);
  }
});

test("清單預設遮蔽密鑰，明確要求時才回傳完整值", async () => {
  const db = setup();
  await makeKeys(db, 2);

  const masked = await listKeys(db);
  assert.equal(masked.length, 2);
  assert.match(masked[0].secret, /…/);
  assert.ok(!masked[0].secret.includes("deadbeef0001"), "遮蔽後不得含完整密鑰");
  assert.equal(masked[0].key_id, "EDIAAD-2026-0002", "預設由新到舊");
  assert.deepEqual(masked[0].features, ["start", "update"]);

  const full = await listKeys(db, { includeSecret: true });
  assert.equal(full[0].secret.startsWith("deadbeef0002"), true);
});

test("清單可以依狀態與關鍵字篩選", async () => {
  const db = setup();
  await makeKeys(db, 3);
  await revokeKey(db, "EDIAAD-2026-0002", "作者", { now: NOW_MS });

  assert.deepEqual((await listKeys(db, { status: "revoked" })).map((row) => row.key_id), [
    "EDIAAD-2026-0002",
  ]);
  assert.equal((await listKeys(db, { status: "issued" })).length, 2);
  assert.deepEqual((await listKeys(db, { search: "0003" })).map((row) => row.key_id), [
    "EDIAAD-2026-0003",
  ]);
  assert.deepEqual((await listKeys(db, { search: "deadbeef0001" })).map((row) => row.key_id), [
    "EDIAAD-2026-0001",
  ]);
  assert.equal((await listKeys(db, { search: "不存在" })).length, 0);
  await assert.rejects(() => listKeys(db, { status: "nope" }), /status/);
  await assert.rejects(() => listKeys(db, { limit: 0 }), /limit/);
  await assert.rejects(() => listKeys(db, { limit: 201 }), /limit/);
  await assert.rejects(() => listKeys(db, { limit: 2.5 }), /limit/);
});

test("撤銷：改狀態、把已綁定的指紋放進黑名單、留一筆稽核", async () => {
  const db = setup();
  await makeKeys(db, 2, ["start"], "作者");
  const otherFingerprint = "ffffffffffffffff";
  db.prepare(
    "INSERT INTO devices (fingerprint, key_id, platform, version, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)"
  )
    .bind(FINGERPRINT, "EDIAAD-2026-0001", "linux", "1.0.0", STAMP, STAMP)
    .run();
  db.prepare(
    "INSERT INTO devices (fingerprint, key_id, platform, version, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)"
  )
    .bind(otherFingerprint, "EDIAAD-2026-0001", "linux", "1.0.0", STAMP, STAMP)
    .run();
  db.prepare("UPDATE keys SET machine = ?, status = 'active', expires_at = ? WHERE key_id = ?")
    .bind(FINGERPRINT, "2026-10-24T12:00:00Z", "EDIAAD-2026-0001")
    .run();

  const row = await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  assert.equal(row.status, "revoked");
  const blacklist = db.prepare("SELECT * FROM blacklist ORDER BY fingerprint").all().results;
  assert.deepEqual(
    blacklist.map((row) => row.fingerprint),
    [FINGERPRINT, otherFingerprint].sort(),
    "綁定的機器欄位與裝置表的指紋都要進黑名單"
  );
  assert.equal(blacklist[0].key_id, "EDIAAD-2026-0001");
  const audit = auditRows(db);
  assert.equal(audit.at(-1).action, "revoke_key");
  assert.equal(audit.at(-1).target, "EDIAAD-2026-0001");

  // 幂等：再撤銷一次不會多出黑名單列，但每次請求都留一筆稽核
  await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM blacklist").first().n, 2);
  assert.equal(auditRows(db).length, 3);
});

test("撤銷沒有綁定機器的密鑰不會亂加黑名單", async () => {
  const db = setup();
  await makeKeys(db, 1);

  await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM blacklist").first().n, 0);
  assert.equal(db.prepare("SELECT status FROM keys").first().status, "revoked");
});

test("撤銷也會把「只有機器欄位、沒有裝置列」的指紋放進黑名單", async () => {
  const db = setup();
  await makeKeys(db, 1);
  db.prepare("UPDATE keys SET status = 'active', machine = ? WHERE key_id = ?")
    .bind(FINGERPRINT, "EDIAAD-2026-0001")
    .run();

  await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  const blacklist = db.prepare("SELECT * FROM blacklist").all().results;
  assert.deepEqual(blacklist.map((row) => row.fingerprint), [FINGERPRINT], "機器欄位就是綁定線索");
});

test("對不存在的 key_id 操作一律回可讀錯誤且不寫稽核", async () => {
  const db = setup();

  for (const operation of [
    () => revokeKey(db, "EDIAAD-2099-9999", "作者", { now: NOW_MS }),
    () => restoreKey(db, "EDIAAD-2099-9999", "作者", { now: NOW_MS }),
    () => extendKey(db, "EDIAAD-2099-9999", 30, "作者", { now: NOW_MS }),
  ]) {
    await assert.rejects(operation, (error) => error.code === "unknown_key" && /找不到/.test(error.message));
  }
  assert.equal(auditRows(db).length, 0);
});

test("恢復：回到可用狀態並移除同一把密鑰的黑名單", async () => {
  const db = setup();
  await makeKeys(db, 1);
  db.prepare("UPDATE keys SET status = 'active', machine = ?, activated_at = ?, expires_at = ? WHERE key_id = ?")
    .bind(FINGERPRINT, STAMP, "2026-10-24T12:00:00Z", "EDIAAD-2026-0001")
    .run();
  await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  const row = await restoreKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  assert.equal(row.status, "active", "啟用過的密鑰恢復後仍是可用狀態");
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM blacklist").first().n, 0);
  assert.equal(auditRows(db).at(-1).action, "restore_key");
});

test("恢復未啟用過的密鑰回到 issued", async () => {
  const db = setup();
  await makeKeys(db, 1);
  await revokeKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  const row = await restoreKey(db, "EDIAAD-2026-0001", "作者", { now: NOW_MS });

  assert.equal(row.status, "issued");
});

test("延長：沒有到期日、尚未到期、已過期三種情境都不會縮短", async () => {
  const db = setup();
  await makeKeys(db, 3);

  const future = "2026-10-24T12:00:00Z";
  const past = "2026-09-01T00:00:00Z";
  db.prepare("UPDATE keys SET expires_at = ? WHERE key_id = ?").bind(future, "EDIAAD-2026-0001").run();
  db.prepare("UPDATE keys SET expires_at = ? WHERE key_id = ?").bind(past, "EDIAAD-2026-0002").run();

  const fromNull = await extendKey(db, "EDIAAD-2026-0003", 30, "作者", { now: NOW_MS });
  const fromFuture = await extendKey(db, "EDIAAD-2026-0001", 30, "作者", { now: NOW_MS });
  const fromPast = await extendKey(db, "EDIAAD-2026-0002", 30, "作者", { now: NOW_MS });

  assert.equal(fromNull.expires_at, "2026-10-24T12:00:00Z");
  assert.equal(fromFuture.expires_at, "2026-11-23T12:00:00Z", "未到期：從原到期日往後加");
  assert.equal(fromPast.expires_at, "2026-10-24T12:00:00Z", "已過期：從現在往後加（不是從過去）");
  assert.equal(auditRows(db).filter((row) => row.action === "extend_key").length, 3);
});

test("延長的參數驗證與稽核", async () => {
  const db = setup();
  await makeKeys(db, 1);

  for (const days of [0, -5, "30", 2.5, 3651]) {
    await assert.rejects(() => extendKey(db, "EDIAAD-2026-0001", days, "作者", { now: NOW_MS }), /days/);
  }
  await assert.rejects(() => extendKey(db, "EDIAAD-2026-0001", 30, "", { now: NOW_MS }), /actor/);
  assert.equal(auditRows(db).length, 1, "只有產生密鑰那筆");
});

test("統計：啟動次數只算 trigger='start'，且不同密鑰不互相加總", async () => {
  const db = setup();
  await makeKeys(db, 2, ["start"], "作者");
  const insert = (keyId, trigger, createdAt) =>
    db
      .prepare("INSERT INTO renewals (key_id, fingerprint, trigger, created_at) VALUES (?, ?, ?, ?)")
      .bind(keyId, FINGERPRINT, trigger, createdAt)
      .run();
  const recent = "2026-09-20T00:00:00Z";
  for (let index = 0; index < 3; index += 1) insert("EDIAAD-2026-0001", "start", recent);
  insert("EDIAAD-2026-0001", "timer", recent);
  insert("EDIAAD-2026-0001", "timer", recent);
  insert("EDIAAD-2026-0002", "start", "2026-07-01T00:00:00Z"); // 超過 30 天

  const report = await stats(db, { now: NOW_MS });

  assert.equal(report.starts, 4, "全部 key 的 start 次數：3 + 1");
  assert.equal(report.renewals, 6, "全部回報筆數：5 + 1");
  assert.equal(report.active_last_30_days, 1, "只有一把密鑰在 30 天內回報過");
  assert.deepEqual(report.keys, { total: 2, issued: 2, active: 0, expired: 0, revoked: 0 });
  assert.equal(report.as_of, STAMP);

  const rows = await listKeys(db);
  const byId = Object.fromEntries(rows.map((row) => [row.key_id, row]));
  assert.equal(byId["EDIAAD-2026-0001"].starts, 3, "timer 不得被算成啟動");
  assert.equal(byId["EDIAAD-2026-0001"].renewals, 5, "只有 key 1 的那五筆");
  assert.equal(byId["EDIAAD-2026-0002"].starts, 1);
});

test("統計把已過期與已撤銷分開算", async () => {
  const db = setup();
  await makeKeys(db, 3, ["start"], "作者");
  db.prepare("UPDATE keys SET expires_at = ? WHERE key_id = ?").bind("2026-09-01T00:00:00Z", "EDIAAD-2026-0001").run();
  db.prepare("UPDATE keys SET status = 'active', expires_at = ? WHERE key_id = ?")
    .bind("2026-10-24T12:00:00Z", "EDIAAD-2026-0002")
    .run();
  await revokeKey(db, "EDIAAD-2026-0003", "作者", { now: NOW_MS });

  const report = await stats(db, { now: NOW_MS });

  assert.deepEqual(report.keys, { total: 3, issued: 1, active: 1, expired: 1, revoked: 1 });
  assert.equal(report.devices, 0);
});

test("稽核函式自己也會驗證參數", async () => {
  const db = setup();

  await assert.rejects(() => auditLog(db, "", "action", "target"), /actor/);
  await assert.rejects(() => auditLog(db, "作者", "", "target"), /action/);

  const row = await auditLog(db, "作者", "custom", "target", { now: NOW_MS, details: { note: "x" } });
  assert.equal(row.created_at, STAMP);
  assert.equal(JSON.parse(row.details).note, "x");
  assert.equal(auditRows(db).length, 1);
});
