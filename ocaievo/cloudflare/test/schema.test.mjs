// `schema.sql` 與 `wrangler.toml`（TASK-033／AC-060 的落地基礎；五張表的完整後台操作屬
// TASK-035）。假 D1 建立在 `node:sqlite` 上，因此這裡執行的是**真的建表語句**。

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { createFakeD1 } from "./fake-d1.mjs";
import { ROOT, schemaText } from "./support.mjs";

const FIVE_TABLES = ["audit", "blacklist", "devices", "keys", "renewals"];

test("schema.sql 在空的資料庫上建立恰五張表", () => {
  const db = createFakeD1(schemaText());

  assert.deepEqual(db.tableNames(), FIVE_TABLES);
});

test("schema.sql 可以重複套用（IF NOT EXISTS）", () => {
  const db = createFakeD1(schemaText());

  assert.doesNotThrow(() => db.exec(schemaText()));
  assert.deepEqual(db.tableNames(), FIVE_TABLES);
});

test("activate／renew 需要的欄位都在（拼錯欄位名會在真實 SQL 上失敗）", () => {
  const db = createFakeD1(schemaText());

  for (const column of ["key_id", "secret", "status", "features", "expires_at", "catalog_version", "machine", "created_at", "activated_at"]) {
    assert.ok(db.columns("keys").includes(column), `keys.${column}`);
  }
  for (const column of ["fingerprint", "platform", "version", "key_id", "first_seen", "last_seen"]) {
    assert.ok(db.columns("devices").includes(column), `devices.${column}`);
  }
  for (const column of ["id", "key_id", "fingerprint", "trigger", "created_at"]) {
    assert.ok(db.columns("renewals").includes(column), `renewals.${column}`);
  }
  for (const column of ["fingerprint", "reason", "key_id", "created_at"]) {
    assert.ok(db.columns("blacklist").includes(column), `blacklist.${column}`);
  }
  for (const column of ["id", "actor", "action", "target", "details", "created_at"]) {
    assert.ok(db.columns("audit").includes(column), `audit.${column}`);
  }
});

test("資料庫層的約束是真的：trigger 只能是三種、secret 唯一、fingerprint 唯一", () => {
  const db = createFakeD1(schemaText());

  db.prepare(
    "INSERT INTO keys (key_id, secret, status, features, created_at) VALUES (?, ?, ?, ?, ?)"
  )
    .bind("K1", "S1", "issued", '["start"]', "2026-09-01T00:00:00Z")
    .run();

  const insertRenewal = (trigger) =>
    db
      .prepare("INSERT INTO renewals (key_id, fingerprint, trigger, created_at) VALUES (?, ?, ?, ?)")
      .bind("K1", "0123456789abcdef", trigger, "2026-09-24T12:00:00Z")
      .run();

  assert.throws(() => insertRenewal("cron"), /CHECK|constraint/i, "CHECK 約束必須擋下非法 trigger");
  assert.throws(
    () =>
      db
        .prepare("INSERT INTO keys (key_id, secret, status, features, created_at) VALUES (?, ?, ?, ?, ?)")
        .bind("K2", "S1", "issued", '["start"]', "2026-09-01T00:00:00Z")
        .run(),
    /UNIQUE|constraint/i
  );
  db.prepare("INSERT INTO blacklist (fingerprint, created_at) VALUES (?, ?)")
    .bind("0123456789abcdef", "2026-09-02T00:00:00Z")
    .run();
  assert.throws(
    () =>
      db
        .prepare("INSERT INTO blacklist (fingerprint, created_at) VALUES (?, ?)")
        .bind("0123456789abcdef", "2026-09-02T00:00:00Z")
        .run(),
    /UNIQUE|constraint/i
  );
});

test("統計查詢用得到的索引都在（索引名稱是交付物的一部分）", () => {
  const db = createFakeD1(schemaText());

  // `sqlite_autoindex_*` 是 PRIMARY KEY／UNIQUE 自動產生的內部索引，不是本檔的交付物。
  const indexes = db.db
    .prepare("SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    .all()
    .map((row) => row.name);

  assert.deepEqual(indexes, [
    "idx_devices_key_id",
    "idx_keys_status",
    "idx_renewals_created_at",
    "idx_renewals_key_id",
    "idx_renewals_trigger",
  ]);
});

test("wrangler.toml 只有佔位值，不含任何真實資源識別碼", () => {
  const text = readFileSync(join(ROOT, "wrangler.toml"), "utf8");

  assert.match(text, /main\s*=\s*"worker\/src\/router\.js"/);
  assert.match(text, /binding\s*=\s*"DB"/);
  assert.match(text, /account_id\s*=\s*"REPLACE_WITH/);
  assert.match(text, /database_id\s*=\s*"REPLACE_WITH/);
  assert.doesNotMatch(text, /\b[0-9a-f]{32}\b/i, "不得出現看起來像真實 UUID 的識別碼");
  assert.doesNotMatch(text, /\.workers\.dev/, "不得寫入真實網域");
  assert.doesNotMatch(text, /LICENSE_PRIVATE_KEY_JWK\s*=/, "私鑰只能是 secret，不得寫進設定檔");
  assert.match(text, /LICENSE_PRIVATE_KEY_JWK/, "仍要留下 secret 名稱的說明");
});
