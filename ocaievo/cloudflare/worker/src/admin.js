// 後台操作（TASK-035／AC-062）：批次產生密鑰、清單與搜尋、撤銷／恢復／延長、統計、稽核。
//
// 幾個刻意的決定：
//   * **每個寫入操作都在 `audit` 留一筆**（`auditLog` 是唯一的寫入點），且參數不合法或
//     找不到密鑰時**先失敗、不寫稽核**——稽核要記「真的發生過的事」。
//   * **撤銷會把該密鑰綁定的指紋放進 `blacklist`**（報告第 6.7 節的黑名單就是為此存在），
//     恢復則把同一把密鑰的黑名單列移除；兩者互為反操作。
//   * **延長不會縮短**：已過期的密鑰從「現在」往後算，未到期的從原到期日往後算。
//   * 清單預設**遮蔽密鑰**（只露頭尾），要完整值必須明確 `includeSecret: true`。
//   * 統計的「啟動次數」只算 `trigger='start'`：`timer` 是 24 小時定時回報，把它算成
//     「使用者開了幾次軟體」會嚴重高估（報告第 6.7 節的設計重點）。

import { RequestError, resolveNow } from "./http.js";
import { utcStamp } from "./lease.js";
import * as store from "./db.js";

/** 後台可指派的授權功能（與 TASK-031 的 `has_feature` 名稱一致）。 */
export const ADMIN_FEATURES = ["start", "update"];
export const MAX_BATCH = 100;
export const MAX_EXTEND_DAYS = 3650;
export const DEFAULT_LIST_LIMIT = 50;
export const MAX_LIST_LIMIT = 200;
export const KEY_STATUSES = ["issued", "active", "expired", "revoked"];

const DAY_MS = 86400000;

function requireActor(actor) {
  if (typeof actor !== "string" || actor.trim() === "") {
    throw new RequestError(400, "invalid_argument", "actor 必須是非空字串");
  }
  return actor.trim();
}

function requireKeyId(keyId) {
  if (typeof keyId !== "string" || !/^EDIAAD-\d{4}-\d{4}$/.test(keyId.trim())) {
    throw new RequestError(400, "invalid_argument", "key_id 必須是 EDIAAD-YYYY-NNNN 的形式");
  }
  return keyId.trim();
}

function requireCount(count) {
  if (!Number.isInteger(count) || count < 1 || count > MAX_BATCH) {
    throw new RequestError(400, "invalid_argument", `count 必須介於 1 與 ${MAX_BATCH} 的整數`);
  }
  return count;
}

function requireFeatures(features) {
  if (!Array.isArray(features) || features.length === 0) {
    throw new RequestError(400, "invalid_argument", "features 必須是非空陣列");
  }
  const cleaned = [];
  for (const feature of features) {
    if (typeof feature !== "string" || feature.trim() === "") {
      throw new RequestError(400, "invalid_argument", "features 必須是非空字串陣列");
    }
    if (cleaned.includes(feature.trim())) {
      throw new RequestError(400, "invalid_argument", `features 不得重複：${feature.trim()}`);
    }
    cleaned.push(feature.trim());
  }
  return cleaned;
}

/** 解析資料庫裡的 `features`（JSON 字串）；壞掉時回 `null` 讓呼叫端決定怎麼處理。 */
export function parseKeyFeatures(raw) {
  if (Array.isArray(raw)) {
    return raw;
  }
  try {
    const parsed = JSON.parse(raw ?? "");
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : null;
  } catch (error) {
    return null;
  }
}

export function maskSecret(secret) {
  if (typeof secret !== "string" || secret.length <= 8) {
    return "…";
  }
  return `${secret.slice(0, 4)}…${secret.slice(-4)}`;
}

function defaultSecret() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function toRow(row, { includeSecret = false, starts = null, renewals = null } = {}) {
  const output = {
    key_id: row.key_id,
    secret: includeSecret ? row.secret : maskSecret(row.secret),
    status: row.status,
    features: parseKeyFeatures(row.features) ?? [],
    expires_at: row.expires_at ?? null,
    catalog_version: row.catalog_version ?? null,
    machine: row.machine ?? null,
    created_at: row.created_at,
    activated_at: row.activated_at ?? null,
    last_renewed_at: row.last_renewed_at ?? null,
  };
  if (starts !== null) {
    output.starts = starts;
  }
  if (renewals !== null) {
    output.renewals = renewals;
  }
  return output;
}

/**
 * 稽核的唯一寫入點。
 *
 * `details` 以 JSON 字串存（可為 `null`）；`created_at` 由注入的時鐘決定（測試可固定）。
 */
export async function auditLog(db, actor, action, target, options = {}) {
  const who = requireActor(actor);
  if (typeof action !== "string" || action.trim() === "") {
    throw new RequestError(400, "invalid_argument", "action 必須是非空字串");
  }
  const now = resolveNow(options);
  return store.insertAudit(db, {
    actor: who,
    action: action.trim(),
    target: target === undefined ? null : target,
    details: options.details === undefined || options.details === null ? null : JSON.stringify(options.details),
    createdAt: utcStamp(now),
  });
}

/**
 * 產生 `count` 把新密鑰（`status='issued'`，尚未啟用）並留一筆稽核。
 *
 * `action` 讓重新申請（`reapply`）與後台批次（`generate_keys`）共用同一段實作，
 * 差別只有稽核的動作名稱。`options.secretFactory(index, keyId)` 可注入（測試用），
 * 預設是 `crypto.getRandomValues` 產生的 128 位元十六進位字串。
 */
export async function createKeys(db, count, features, actor, action, options = {}) {
  const total = requireCount(count);
  const list = requireFeatures(features);
  const who = requireActor(actor);
  const now = resolveNow(options);
  const stamp = utcStamp(now);
  const prefix = `EDIAAD-${new Date(now).getUTCFullYear()}-`;
  const latest = await store.latestKeyId(db, `${prefix}%`);
  let sequence = latest ? Number.parseInt(latest.slice(prefix.length), 10) : 0;
  if (!Number.isInteger(sequence)) {
    sequence = 0;
  }
  const factory = typeof options.secretFactory === "function" ? options.secretFactory : defaultSecret;

  const created = [];
  for (let index = 0; index < total; index += 1) {
    sequence += 1;
    const keyId = `${prefix}${String(sequence).padStart(4, "0")}`;
    // 工廠收到序號與 key_id，測試因此可以產生「與 key_id 對應」的確定性密鑰。
    const secret = factory(index, keyId);
    if (typeof secret !== "string" || secret.trim() === "") {
      throw new RequestError(400, "invalid_argument", "secretFactory 必須產生非空字串");
    }
    created.push(
      await store.insertKey(db, {
        keyId,
        secret: secret.trim(),
        features: list,
        status: "issued",
        catalogVersion: options.catalogVersion ?? null,
        createdAt: stamp,
      })
    );
  }

  const target = created.length === 1 ? created[0].key_id : `${created[0].key_id}..${created.at(-1).key_id}`;
  await auditLog(db, who, action, target, {
    now,
    details: { count: created.length, features: list },
  });
  return created.map((row) => toRow(row, { includeSecret: true, starts: 0, renewals: 0 }));
}

/** 後台批次產生密鑰（AC-062）。 */
export async function generateKeys(db, count, features, actor, options = {}) {
  return createKeys(db, count, features, actor, "generate_keys", options);
}

/** 清單與搜尋；預設遮蔽密鑰、預設由新到舊、附上每把密鑰的啟動與回報次數。 */
export async function listKeys(db, filter = {}, options = {}) {
  if (filter === null || typeof filter !== "object" || Array.isArray(filter)) {
    throw new RequestError(400, "invalid_argument", "filter 必須是物件");
  }
  if (filter.status !== undefined && !KEY_STATUSES.includes(filter.status)) {
    throw new RequestError(400, "invalid_argument", `status 必須是 ${KEY_STATUSES.join("／")} 之一`);
  }
  if (filter.search !== undefined && (typeof filter.search !== "string" || filter.search.trim() === "")) {
    throw new RequestError(400, "invalid_argument", "search 必須是非空字串");
  }
  const limit = filter.limit === undefined ? DEFAULT_LIST_LIMIT : filter.limit;
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIST_LIMIT) {
    throw new RequestError(400, "invalid_argument", `limit 必須介於 1 與 ${MAX_LIST_LIMIT} 的整數`);
  }

  const rows = await store.findKeys(db, {
    status: filter.status ?? null,
    search: filter.search === undefined ? null : filter.search.trim(),
    limit,
  });
  const includeSecret = filter.includeSecret === true;
  const output = [];
  for (const row of rows) {
    output.push(
      toRow(row, {
        includeSecret,
        starts: await store.countStartsForKey(db, row.key_id),
        renewals: await store.countRenewalsForKey(db, row.key_id),
      })
    );
  }
  return output;
}

async function requireExistingKey(db, keyId) {
  const key = requireKeyId(keyId);
  const row = await store.getKeyById(db, key);
  if (row === null || row === undefined) {
    throw new RequestError(404, "unknown_key", `找不到密鑰 ${key}`);
  }
  return row;
}

/** 撤銷：狀態改為 `revoked`，並把該密鑰綁定的指紋放進黑名單。 */
export async function revokeKey(db, keyId, actor, options = {}) {
  const row = await requireExistingKey(db, keyId);
  const who = requireActor(actor);
  const now = resolveNow(options);
  const stamp = utcStamp(now);

  const fingerprints = new Set();
  if (typeof row.machine === "string" && row.machine !== "") {
    fingerprints.add(row.machine);
  }
  for (const device of await store.devicesForKey(db, row.key_id)) {
    if (typeof device.fingerprint === "string" && device.fingerprint !== "") {
      fingerprints.add(device.fingerprint);
    }
  }
  for (const fingerprint of fingerprints) {
    await store.addToBlacklist(db, {
      fingerprint,
      keyId: row.key_id,
      reason: "密鑰已撤銷",
      createdAt: stamp,
    });
  }
  await store.updateKeyStatus(db, row.key_id, "revoked");
  await auditLog(db, who, "revoke_key", row.key_id, { now, details: { fingerprints: [...fingerprints] } });
  return toRow({ ...row, status: "revoked" }, { includeSecret: false });
}

/** 恢復：回到 `active`（啟用過）或 `issued`（沒啟用過），並移除同一把密鑰的黑名單列。 */
export async function restoreKey(db, keyId, actor, options = {}) {
  const row = await requireExistingKey(db, keyId);
  const who = requireActor(actor);
  const now = resolveNow(options);
  const status = row.activated_at ? "active" : "issued";

  await store.removeBlacklistForKey(db, row.key_id);
  await store.updateKeyStatus(db, row.key_id, status);
  await auditLog(db, who, "restore_key", row.key_id, { now, details: { status } });
  return toRow({ ...row, status }, { includeSecret: false });
}

/** 延長到期日：未到期者從原到期日往後加，已過期（或沒有到期日）者從現在往後加。 */
export async function extendKey(db, keyId, days, actor, options = {}) {
  const row = await requireExistingKey(db, keyId);
  const who = requireActor(actor);
  if (!Number.isInteger(days) || days < 1 || days > MAX_EXTEND_DAYS) {
    throw new RequestError(400, "invalid_argument", `days 必須介於 1 與 ${MAX_EXTEND_DAYS} 的整數`);
  }
  const now = resolveNow(options);
  const current = row.expires_at ? Date.parse(row.expires_at) : Number.NaN;
  const base = Number.isFinite(current) && current > now ? current : now;
  const expiresAt = utcStamp(base + days * DAY_MS);

  await store.updateKeyExpiry(db, row.key_id, expiresAt);
  await auditLog(db, who, "extend_key", row.key_id, { now, details: { days, expires_at: expiresAt } });
  return toRow({ ...row, expires_at: expiresAt }, { includeSecret: false });
}

/**
 * 統計（AC-062）。`starts` 只算 `trigger='start'`；`active_last_30_days` 是過去 30 天內
 * 有回報的**不同**密鑰數——因為租約是 30 天滾動，這幾乎等於真實活躍使用者。
 */
export async function stats(db, options = {}) {
  const now = resolveNow(options);
  const stamp = utcStamp(now);
  const byStatus = await store.countKeysByStatus(db);
  const computedExpired = await store.countExpiredKeys(db, stamp);
  const total = Object.values(byStatus).reduce((sum, value) => sum + value, 0);

  return {
    as_of: stamp,
    keys: {
      total,
      issued: byStatus.issued ?? 0,
      active: byStatus.active ?? 0,
      expired: (byStatus.expired ?? 0) + computedExpired,
      revoked: byStatus.revoked ?? 0,
    },
    starts: await store.countStarts(db),
    renewals: await store.countRenewalsTotal(db),
    devices: await store.countDevices(db),
    active_last_30_days: await store.countRenewalsSince(db, utcStamp(now - 30 * DAY_MS)),
  };
}
