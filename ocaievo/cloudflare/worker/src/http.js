// HTTP 請求／回應的共同處理（TASK-033）。
//
// 兩個 handler 共用同一套規則，**錯誤格式只有一份**：4xx 一律是
// `{"error":{"code","message"},"message":...}`——同時滿足 SPEC 第 5 節的錯誤格式，也讓
// Python 客戶端的 `_body_message` 讀得到可讀訊息（它只認字串值的 `message`）。
//
// 所有失敗都經過這裡轉譯，因此 5xx 的訊息固定、不含堆疊或例外內容。

export const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

/** 帶狀態碼的請求錯誤（handler 只負責丟出它，轉譯集中在 `handleRequest`）。 */
export class RequestError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = "RequestError";
    this.status = status;
    this.code = code;
  }
}

export function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

/** 錯誤回應；`extra` 用於導流閘門（`{"status":"expired"}`／`{"status":"revoked"}`）。 */
export function errorResponse(status, code, message, extra = {}) {
  return jsonResponse(status, { error: { code, message }, message, ...extra });
}

/** 把 handler 的例外轉成回應：已知的請求錯誤照原樣，其餘一律 500 且訊息固定。 */
export function toErrorResponse(error) {
  if (error instanceof RequestError) {
    return errorResponse(error.status, error.code, error.message);
  }
  return errorResponse(500, "internal_error", "授權服務內部錯誤（請稍後再試）");
}

/**
 * 未預期錯誤的觀測點：只記訊息（Cloudflare 的 `wrangler tail` 看得到），
 * **不把堆疊寫進回應**。回應本身一律是固定的 500 訊息。
 */
export function logUnexpected(error) {
  console.error(`[ediaad-license] 未預期的錯誤：${error && error.message ? error.message : error}`);
}

export function requireMethod(request, method) {
  const actual = (request.method ?? "GET").toUpperCase();
  if (actual !== method) {
    throw new RequestError(405, "method_not_allowed", `這個端點只接受 ${method}，收到 ${actual}`);
  }
}

/**
 * 讀取 JSON 主體。
 *
 * 非物件（陣列、字串、數字）一律 400：主體一定是 `{...}`，默默接受其他形狀只會讓
 * 「使用者少送一個欄位」變成難懂的錯誤。
 */
export async function readJsonBody(request) {
  let text;
  try {
    text = await request.text();
  } catch (error) {
    throw new RequestError(400, "invalid_body", `無法讀取請求主體：${error.message}`);
  }
  if (text.trim() === "") {
    throw new RequestError(400, "invalid_body", "請求主體不得為空");
  }
  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new RequestError(400, "invalid_body", `請求主體不是合法 JSON：${error.message}`);
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new RequestError(400, "invalid_body", "請求主體必須是 JSON 物件");
  }
  return payload;
}

export function requireText(body, name) {
  const value = body[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new RequestError(400, "invalid_field", `${name} 必須是非空字串`);
  }
  return value.trim();
}

export function optionalText(body, name) {
  const value = body[name];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string" || value.trim() === "") {
    throw new RequestError(400, "invalid_field", `${name} 必須是非空字串或省略`);
  }
  return value.trim();
}

/** 指紋格式與客戶端的 `machine_fingerprint`／`Lease` 契約一致（16 碼小寫十六進位）。 */
export function requireMachine(value) {
  if (typeof value !== "string" || !/^[0-9a-f]{16}$/.test(value)) {
    throw new RequestError(400, "invalid_field", "machine 必須是 16 碼小寫十六進位指紋");
  }
  return value;
}

/** 續期時鐘：預設為 `Date.now()`；測試以 `options.now`（毫秒）注入。 */
export function resolveNow(options) {
  const value = options ? options.now : undefined;
  if (value === undefined || value === null) {
    return Date.now();
  }
  const milliseconds = value instanceof Date ? value.getTime() : Number(value);
  if (!Number.isFinite(milliseconds)) {
    throw new RequestError(400, "invalid_clock", "now 必須是可解讀的時間");
  }
  return milliseconds;
}

/**
 * 租約的 `catalog_version`：密鑰列 → 環境變數 → `"unknown"`。
 *
 * 不假造日期：客戶端拿到的是一個誠實的「後端沒有設定版本」，而不是一個看起來像真的版本。
 */
export function resolveCatalogVersion(keyRow, env) {
  const fromRow = keyRow ? keyRow.catalog_version : null;
  if (typeof fromRow === "string" && fromRow.trim() !== "") {
    return fromRow.trim();
  }
  const fromEnv = env ? env.CATALOG_VERSION : null;
  if (typeof fromEnv === "string" && fromEnv.trim() !== "") {
    return fromEnv.trim();
  }
  return "unknown";
}

export function requireDb(env) {
  const db = env ? env.DB : undefined;
  if (db === null || db === undefined || typeof db.prepare !== "function") {
    throw new Error("缺少 D1 綁定（env.DB）");
  }
  return db;
}
