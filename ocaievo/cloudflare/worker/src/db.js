// D1 轉接層（TASK-033／TASK-035 共用）。
//
// 只是一個薄轉接：每個函式一句 SQL，讓 handler 讀起來是「驗證 → 查詢 → 回應」而不是
// SQL 字串。**SQL 一律用綁定參數**（`?`）——指紋與密鑰都來自請求，字串串接就是注入。
//
// 假 D1（`test/fake-d1.mjs`）建立在 `node:sqlite` 上，因此這些 SQL 在測試裡是**真的被
// SQLite 執行**：欄位名拼錯、語法錯誤、UNIQUE／CHECK 違反都會當場失敗。

export async function getKeyBySecret(db, secret) {
  return db.prepare("SELECT * FROM keys WHERE secret = ?").bind(secret).first();
}

export async function getKeyById(db, keyId) {
  return db.prepare("SELECT * FROM keys WHERE key_id = ?").bind(keyId).first();
}

export async function getDevice(db, fingerprint) {
  return db.prepare("SELECT * FROM devices WHERE fingerprint = ?").bind(fingerprint).first();
}

export async function isBlacklisted(db, fingerprint) {
  const row = await db.prepare("SELECT 1 AS found FROM blacklist WHERE fingerprint = ?").bind(fingerprint).first();
  return row !== null && row !== undefined;
}

export async function countRenewals(db, keyId) {
  const row = await db.prepare("SELECT COUNT(*) AS total FROM renewals WHERE key_id = ?").bind(keyId).first();
  return row ? Number(row.total) : 0;
}

/**
 * 新增或更新裝置（`ON CONFLICT` 讓「同一台重複啟用」不會留下多列）。
 *
 * `first_seen` 只在第一次寫入，`last_seen` 每次更新——後台的「裝置」清單靠這兩欄看出
 * 首次與最近使用時間。
 */
export async function upsertDevice(db, { fingerprint, keyId = null, platform = null, version = null, seenAt }) {
  await db
    .prepare(
      `INSERT INTO devices (fingerprint, key_id, platform, version, first_seen, last_seen)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(fingerprint) DO UPDATE SET
         key_id = excluded.key_id,
         platform = excluded.platform,
         version = excluded.version,
         last_seen = excluded.last_seen`
    )
    .bind(fingerprint, keyId, platform, version, seenAt, seenAt)
    .run();
}

export async function insertRenewal(db, { keyId, fingerprint, trigger, createdAt, version = null }) {
  await db
    .prepare(
      "INSERT INTO renewals (key_id, fingerprint, trigger, version, created_at) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(keyId, fingerprint, trigger, version, createdAt)
    .run();
}

export async function markKeyActivated(db, { keyId, machine, expiresAt, activatedAt }) {
  await db
    .prepare(
      "UPDATE keys SET status = 'active', machine = ?, expires_at = ?, activated_at = ? WHERE key_id = ?"
    )
    .bind(machine, expiresAt, activatedAt, keyId)
    .run();
}

export async function markKeyRenewed(db, { keyId, machine, expiresAt, renewedAt }) {
  await db
    .prepare(
      "UPDATE keys SET status = 'active', machine = ?, expires_at = ?, last_renewed_at = ? WHERE key_id = ?"
    )
    .bind(machine, expiresAt, renewedAt, keyId)
    .run();
}

// ---- 後台與重新申請（TASK-035） ---------------------------------------------

/** 找出同一年的最後一組序號（`EDIAAD-YYYY-NNNN`）；沒有就回 `null`。 */
export async function latestKeyId(db, pattern) {
  const row = await db
    .prepare("SELECT key_id FROM keys WHERE key_id LIKE ? ORDER BY key_id DESC LIMIT 1")
    .bind(pattern)
    .first();
  return row ? row.key_id : null;
}

export async function insertKey(db, { keyId, secret, features, status = "issued", catalogVersion = null, createdAt }) {
  await db
    .prepare(
      `INSERT INTO keys (key_id, secret, status, features, catalog_version, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(keyId, secret, status, JSON.stringify(features), catalogVersion, createdAt)
    .run();
  return { key_id: keyId, secret, status, features, expires_at: null, created_at: createdAt };
}

/** 清單查詢：`status` 與 `search`（key_id／secret 的子字串）都是綁定參數。 */
export async function findKeys(db, { status = null, search = null, limit = 50 } = {}) {
  const clauses = [];
  const params = [];
  if (status) {
    clauses.push("status = ?");
    params.push(status);
  }
  if (search) {
    clauses.push("(key_id LIKE ? OR secret LIKE ?)");
    params.push(`%${search}%`, `%${search}%`);
  }
  const where = clauses.length > 0 ? ` WHERE ${clauses.join(" AND ")}` : "";
  const rows = await db
    .prepare(`SELECT * FROM keys${where} ORDER BY key_id DESC LIMIT ?`)
    .bind(...params, limit)
    .all();
  return rows.results ?? [];
}

export async function countKeysByStatus(db) {
  const rows = await db.prepare("SELECT status, COUNT(*) AS total FROM keys GROUP BY status").all();
  const counts = {};
  for (const row of rows.results ?? []) {
    counts[row.status] = Number(row.total);
  }
  return counts;
}

export async function countExpiredKeys(db, cutoff) {
  const row = await db
    .prepare(
      "SELECT COUNT(*) AS total FROM keys WHERE expires_at IS NOT NULL AND expires_at < ? AND status NOT IN ('revoked', 'expired')"
    )
    .bind(cutoff)
    .first();
  return row ? Number(row.total) : 0;
}

export async function countDevices(db) {
  const row = await db.prepare("SELECT COUNT(*) AS total FROM devices").first();
  return row ? Number(row.total) : 0;
}

export async function countRenewalsTotal(db) {
  const row = await db.prepare("SELECT COUNT(*) AS total FROM renewals").first();
  return row ? Number(row.total) : 0;
}

/** 啟動次數：**只算 `trigger='start'`**（`timer` 的定時回報不得被算成開啟軟體）。 */
export async function countStarts(db) {
  const row = await db.prepare("SELECT COUNT(*) AS total FROM renewals WHERE trigger = 'start'").first();
  return row ? Number(row.total) : 0;
}

export async function countStartsForKey(db, keyId) {
  const row = await db
    .prepare("SELECT COUNT(*) AS total FROM renewals WHERE key_id = ? AND trigger = 'start'")
    .bind(keyId)
    .first();
  return row ? Number(row.total) : 0;
}

export async function countRenewalsForKey(db, keyId) {
  const row = await db
    .prepare("SELECT COUNT(*) AS total FROM renewals WHERE key_id = ?")
    .bind(keyId)
    .first();
  return row ? Number(row.total) : 0;
}

/** 過去 window 內有回報的**不同**密鑰數（活躍使用者的近似值）。 */
export async function countRenewalsSince(db, cutoff) {
  const row = await db
    .prepare("SELECT COUNT(DISTINCT key_id) AS total FROM renewals WHERE created_at >= ?")
    .bind(cutoff)
    .first();
  return row ? Number(row.total) : 0;
}

export async function devicesForKey(db, keyId) {
  const rows = await db.prepare("SELECT * FROM devices WHERE key_id = ?").bind(keyId).all();
  return rows.results ?? [];
}

/**
 * 找出某個指紋最新的密鑰列（不論是否過期）。
 *
 * 兩條線索都要看：`keys.machine`（啟用時綁定）與 `devices.key_id`（裝置紀錄）——
 * 只查其中一邊會漏掉另一邊建立過關聯的情況。
 */
export async function findKeyForFingerprint(db, fingerprint) {
  return db
    .prepare(
      `SELECT DISTINCT k.* FROM keys k
       LEFT JOIN devices d ON d.key_id = k.key_id
       WHERE (d.fingerprint = ? OR k.machine = ?)
       ORDER BY k.expires_at DESC
       LIMIT 1`
    )
    .bind(fingerprint, fingerprint)
    .first();
}

/** 只找**已過期**的密鑰（時間比較在 SQL 裡做；所有時間字串都是同格式的 UTC `...Z`）。 */
export async function findExpiredKeyForFingerprint(db, fingerprint, cutoff) {
  return db
    .prepare(
      `SELECT DISTINCT k.* FROM keys k
       LEFT JOIN devices d ON d.key_id = k.key_id
       WHERE (d.fingerprint = ? OR k.machine = ?)
         AND k.expires_at IS NOT NULL AND k.expires_at < ?
       ORDER BY k.expires_at DESC
       LIMIT 1`
    )
    .bind(fingerprint, fingerprint, cutoff)
    .first();
}

export async function updateKeyStatus(db, keyId, status) {
  await db.prepare("UPDATE keys SET status = ? WHERE key_id = ?").bind(status, keyId).run();
}

export async function updateKeyExpiry(db, keyId, expiresAt) {
  await db.prepare("UPDATE keys SET expires_at = ? WHERE key_id = ?").bind(expiresAt, keyId).run();
}

export async function addToBlacklist(db, { fingerprint, keyId = null, reason = "", createdAt }) {
  await db
    .prepare(
      `INSERT INTO blacklist (fingerprint, key_id, reason, created_at) VALUES (?, ?, ?, ?)
       ON CONFLICT(fingerprint) DO UPDATE SET key_id = excluded.key_id, reason = excluded.reason`
    )
    .bind(fingerprint, keyId, reason, createdAt)
    .run();
}

export async function removeBlacklistForKey(db, keyId) {
  await db.prepare("DELETE FROM blacklist WHERE key_id = ?").bind(keyId).run();
}

export async function insertAudit(db, { actor, action, target = null, details = null, createdAt }) {
  const result = await db
    .prepare("INSERT INTO audit (actor, action, target, details, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(actor, action, target, details, createdAt)
    .run();
  return {
    id: result.meta ? result.meta.last_row_id : null,
    actor,
    action,
    target,
    details,
    created_at: createdAt,
  };
}
