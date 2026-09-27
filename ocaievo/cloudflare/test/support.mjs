// 測試共用夾具（TASK-033）。
//
// 簽章私鑰使用 RFC 8032 §7.1 TEST 1 的**公開**測試向量——與 Python 端的
// `tests/_ed25519_fixture.py` 是同一把，因此 Node 簽出來的簽章必須與 Python 簽出來的
// **逐字相同**（Ed25519 是決定性的）。這讓「Node 的簽章能被 Python 驗章」有直接的證據，
// 而不是只靠「兩邊都說自己是 Ed25519」。

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = join(HERE, "..");

export const NOW_MS = Date.parse("2026-09-24T12:00:00Z");
export const ISSUED_AT = "2026-09-24T12:00:00Z";
export const EXPIRES_AT = "2026-10-24T12:00:00Z";
export const FINGERPRINT = "0123456789abcdef";

/** RFC 8032 TEST 1 的私鑰（公開向量）以 JWK 表示：Worker 的 secret 就是這個格式。 */
export const FIXTURE_PRIVATE_JWK = {
  kty: "OKP",
  crv: "Ed25519",
  d: "nWGxne_9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A",
  x: "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
};
/** 對應的公鑰欄位（`x`）——測試用它驗章，等同 Python 的 `FIXTURE_PUBLIC_KEY`。 */
export const FIXTURE_PUBLIC_JWK = { kty: "OKP", crv: "Ed25519", x: FIXTURE_PRIVATE_JWK.x };

export function licenseEnv(extra = {}) {
  return { LICENSE_PRIVATE_KEY_JWK: JSON.stringify(FIXTURE_PRIVATE_JWK), ...extra };
}

/** 金標租約內容（與 Python 端 `signing_payload` 的輸入相同）。 */
export const GOLDEN_PAYLOAD = {
  key_id: "EDIAAD-2026-0001",
  machine: FINGERPRINT,
  issued_at: ISSUED_AT,
  expires_at: EXPIRES_AT,
  features: ["start", "update"],
  catalog_version: "2026-10-01",
};

/** Python `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 的輸出。 */
export const GOLDEN_CANONICAL =
  '{"catalog_version":"2026-10-01","expires_at":"2026-10-24T12:00:00Z","features":["start","update"],' +
  '"issued_at":"2026-09-24T12:00:00Z","key_id":"EDIAAD-2026-0001","machine":"0123456789abcdef"}';

/** Python 夾具對 `GOLDEN_CANONICAL` 的簽章（決定性；Node 必須得到同一個值）。 */
export const GOLDEN_SIGNATURE =
  "3166564017bcb3338d6af0d69b8bd6d4da763ed67b1e955d55c9e9e05bea7927" +
  "ee8a9b8247abbf308c44d958ddb0d0ef963a6a2e3f91b0900f29df5ba3636205";

/** 獨立的參考實作（刻意與 Worker 的寫法不同）：排序鍵後序列化，用來交叉檢查。 */
export function referenceCanonical(payload) {
  const sorted = {};
  for (const key of Object.keys(payload).sort()) {
    sorted[key] = payload[key];
  }
  return JSON.stringify(sorted);
}

export function bytesToHex(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function hexToBytes(text) {
  const bytes = new Uint8Array(text.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = parseInt(text.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes;
}

export async function fixturePublicKey() {
  return crypto.subtle.importKey("jwk", FIXTURE_PUBLIC_JWK, { name: "Ed25519" }, false, ["verify"]);
}

/** 以公鑰驗證租約（`sig` 以外的欄位就是被簽的內容）。 */
export async function verifyLeaseSignature(lease, canonical) {
  const { sig, ...payload } = lease;
  const message = new TextEncoder().encode(canonical(payload));
  return crypto.subtle.verify({ name: "Ed25519" }, await fixturePublicKey(), hexToBytes(sig), message);
}

export function request(path, body, { method = "POST", raw = false } = {}) {
  const init = { method };
  // `fetch`/`Request` 不允許 GET／HEAD 帶主體；方法檢查的案例因此只送方法，不送主體。
  const allowsBody = method !== "GET" && method !== "HEAD";
  if (body !== undefined && allowsBody) {
    init.body = raw ? body : JSON.stringify(body);
    init.headers = { "content-type": "application/json" };
  }
  return new Request(`https://license.example.invalid${path}`, init);
}

export function schemaText() {
  return readFileSync(join(ROOT, "schema.sql"), "utf8");
}

export function insertKey(db, overrides = {}) {
  const row = {
    key_id: "EDIAAD-2026-0001",
    secret: "SECRET-0001",
    status: "issued",
    features: JSON.stringify(["start", "update"]),
    expires_at: null,
    catalog_version: null,
    machine: null,
    created_at: "2026-09-01T00:00:00Z",
    activated_at: null,
    ...overrides,
  };
  db.prepare(
    "INSERT INTO keys (key_id, secret, status, features, expires_at, catalog_version, machine, created_at, activated_at) " +
      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
  )
    .bind(
      row.key_id,
      row.secret,
      row.status,
      row.features,
      row.expires_at,
      row.catalog_version,
      row.machine,
      row.created_at,
      row.activated_at
    )
    .run();
  return row;
}

export function insertBlacklist(db, fingerprint, overrides = {}) {
  const row = {
    fingerprint,
    reason: "已撤銷",
    key_id: "EDIAAD-2026-0001",
    created_at: "2026-09-02T00:00:00Z",
    ...overrides,
  };
  db.prepare("INSERT INTO blacklist (fingerprint, reason, key_id, created_at) VALUES (?, ?, ?, ?)")
    .bind(row.fingerprint, row.reason, row.key_id, row.created_at)
    .run();
  return row;
}

export function renewals(db, keyId) {
  return db.prepare("SELECT * FROM renewals WHERE key_id = ? ORDER BY id").bind(keyId).all().results;
}

export function getKeyRow(db, keyId) {
  return db.prepare("SELECT * FROM keys WHERE key_id = ?").bind(keyId).first();
}
