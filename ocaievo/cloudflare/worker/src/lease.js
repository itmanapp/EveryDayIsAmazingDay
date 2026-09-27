// 租約內容與 Ed25519 簽章（TASK-033／AC-060）。
//
// **簽章範圍必須與客戶端逐字相同**：Python 端 `ediaad.license.signing_payload` 的定義是
// `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 的 UTF-8
// bytes。這裡的 `canonicalJson` 就是同一件事的 JS 實作，並且有**金標值**交叉驗證
// （`test/lease.test.mjs` 比對 Python 產生的字串與簽章），不是「兩邊各自說自己是 JSON」。
//
// 私鑰由 `env.LICENSE_PRIVATE_KEY_JWK`（Cloudflare secret）注入，格式是 OKP／Ed25519 的
// JWK。**私鑰永遠不落檔、不進版控**；`signLease` 在缺少或格式不對時直接拒絕，不會簽出
// 一個沒人能驗的租約。

export const LEASE_DAYS = 30;

/** 租約欄位（不含 `sig`），順序即 `canonicalJson` 排序後的結果。 */
export const LEASE_FIELDS = [
  "catalog_version",
  "expires_at",
  "features",
  "issued_at",
  "key_id",
  "machine",
];

const FINGERPRINT_PATTERN = /^[0-9a-f]{16}$/;
const SECOND = 1000;
const DAY_MS = 86400 * SECOND;

/** 租約內容或簽章設定有問題時丟這個（訊息一律可讀，供 500 以外的分層使用）。 */
export class LeaseError extends Error {
  constructor(message) {
    super(message);
    this.name = "LeaseError";
  }
}

/**
 * 穩定序列化：鍵排序、無多餘空白，與 Python 的 `signing_payload` 同一種 bytes。
 *
 * 值域刻意只支援 JSON 的基本型別與陣列／物件：租約的欄位是字串與字串陣列，數字與
 * `undefined` 不該出現在被簽的內容裡（出現就是程式錯誤，寧可吵也不要簽出模糊的內容）。
 */
export function canonicalJson(payload) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new LeaseError(`canonicalJson 只接受物件，收到 ${Array.isArray(payload) ? "array" : typeof payload}`);
  }
  const parts = Object.keys(payload)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${serialize(payload[key], key)}`);
  return `{${parts.join(",")}}`;
}

function serialize(value, where) {
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new LeaseError(`${where} 不是有限數值：${value}`);
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => serialize(item, where)).join(",")}]`;
  }
  if (typeof value === "object") {
    return canonicalJson(value);
  }
  throw new LeaseError(`${where} 的型別不支援：${typeof value}`);
}

/** ISO 8601（秒級、UTC、以 `Z` 結尾）——與 SPEC 第 5 節的租約範例同一種寫法。 */
export function utcStamp(milliseconds) {
  return new Date(milliseconds).toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** 由毫秒時間與天數算出到期時間（租約長度恰為 `LEASE_DAYS` 天）。 */
export function expiresAt(milliseconds, days = LEASE_DAYS) {
  return utcStamp(milliseconds + days * DAY_MS);
}

function parseFeatures(raw, keyId) {
  let parsed;
  try {
    parsed = JSON.parse(raw ?? "");
  } catch (error) {
    throw new LeaseError(`密鑰 ${keyId} 的 features 不是合法 JSON：${error.message}`);
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new LeaseError(`密鑰 ${keyId} 的 features 必須是非空陣列`);
  }
  for (const feature of parsed) {
    if (typeof feature !== "string" || feature.trim() === "") {
      throw new LeaseError(`密鑰 ${keyId} 的 features 必須是非空字串陣列`);
    }
  }
  return parsed.map((feature) => feature.trim());
}

/**
 * 租約的七個欄位中除 `sig` 以外的六個（SPEC 第 5 節）。
 *
 * `catalogVersion` 由呼叫端解析（密鑰列 → 環境變數 → `"unknown"`）：這裡只負責「必須是
 * 非空字串」，因為假造一個看起來真實的版本比說「不知道」更糟。
 */
export function leasePayload(keyRow, machine, now, catalogVersion) {
  if (keyRow === null || typeof keyRow !== "object" || typeof keyRow.key_id !== "string" || keyRow.key_id.trim() === "") {
    throw new LeaseError("租約需要一個有 key_id 的密鑰列");
  }
  if (typeof machine !== "string" || !FINGERPRINT_PATTERN.test(machine)) {
    throw new LeaseError(`machine 必須是 16 碼小寫十六進位指紋，收到 ${JSON.stringify(machine)}`);
  }
  if (typeof catalogVersion !== "string" || catalogVersion.trim() === "") {
    throw new LeaseError("catalog_version 必須是非空字串");
  }
  if (!Number.isFinite(now)) {
    throw new LeaseError(`now 必須是毫秒時間，收到 ${JSON.stringify(now)}`);
  }

  return {
    key_id: keyRow.key_id.trim(),
    machine,
    issued_at: utcStamp(now),
    expires_at: expiresAt(now),
    features: parseFeatures(keyRow.features, keyRow.key_id),
    catalog_version: catalogVersion.trim(),
  };
}

function privateKeyJwk(env) {
  const raw = env ? env.LICENSE_PRIVATE_KEY_JWK : undefined;
  if (typeof raw !== "string" && (raw === null || typeof raw !== "object")) {
    throw new LeaseError("缺少 LICENSE_PRIVATE_KEY_JWK（Cloudflare secret 未設定）");
  }
  let jwk = raw;
  if (typeof raw === "string") {
    if (raw.trim() === "") {
      throw new LeaseError("缺少 LICENSE_PRIVATE_KEY_JWK（Cloudflare secret 未設定）");
    }
    try {
      jwk = JSON.parse(raw);
    } catch (error) {
      throw new LeaseError(`LICENSE_PRIVATE_KEY_JWK 不是合法 JSON：${error.message}`);
    }
  }
  if (jwk === null || typeof jwk !== "object" || jwk.kty !== "OKP" || jwk.crv !== "Ed25519") {
    throw new LeaseError("LICENSE_PRIVATE_KEY_JWK 必須是 OKP／Ed25519 的 JWK");
  }
  if (typeof jwk.d !== "string" || jwk.d.trim() === "" || typeof jwk.x !== "string" || jwk.x.trim() === "") {
    throw new LeaseError("LICENSE_PRIVATE_KEY_JWK 缺少 d 或 x 欄位");
  }
  return jwk;
}

function toHex(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * 以私鑰簽章租約內容，回傳帶 `sig` 的完整租約物件。
 *
 * WebCrypto 的 Ed25519 是決定性的，因此同一把金鑰與同一組 bytes 一定得到同一個簽章——
 * 測試用這一點比對 Python 夾具的輸出。`sig` 是 128 個小寫十六進位字元（客戶端的契約）。
 */
export async function signLease(payload, env) {
  const jwk = privateKeyJwk(env);
  const message = new TextEncoder().encode(canonicalJson(payload));
  let key;
  try {
    key = await crypto.subtle.importKey("jwk", { ...jwk, key_ops: ["sign"] }, { name: "Ed25519" }, false, ["sign"]);
  } catch (error) {
    throw new LeaseError(`LICENSE_PRIVATE_KEY_JWK 無法匯入：${error.message}`);
  }
  const signature = await crypto.subtle.sign({ name: "Ed25519" }, key, message);
  return { ...payload, sig: toHex(signature) };
}
