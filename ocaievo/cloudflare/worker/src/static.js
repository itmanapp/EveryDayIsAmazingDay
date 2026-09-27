// 靜態 manifest 與 catalog（TASK-034／AC-061）。
//
// **這一支刻意不碰任何綁定**：兩個端點由靜態主機（Cloudflare Pages／R2 或任何靜態伺服器）
// 提供，不經過 Worker——報告第 6.5 節的理由是「manifest 是靜態可快取的，renew 是動態的；
// Worker 掛掉時 manifest 仍可讀」。因此本模組：
//   * 不匯入 `db.js`／`activate.js`／`renew.js`（有測試以原始碼斷言）；
//   * 不呼叫 `db.prepare`（有測試以毒環境斷言：只要碰 `env` 任何屬性就會爆）；
//   * 只做「驗證 → 產生帶快取標頭的回應」。
//
// `manifestResponse`／`catalogResponse` 的第二個參數（`env`）是**刻意忽略**的：靜態主機
// 的 handler 簽章通常會傳環境進來，但這裡不需要它；測試會用一個「任何屬性都拋錯」的
// Proxy 傳進來，確保我們沒有偷偷依賴它。

/** 凍結的 manifest 鍵集合（SPEC 第 5 節／報告第 6.5 節，不多不少）。 */
export const MANIFEST_KEYS = [
  "schema",
  "version",
  "released_at",
  "min_supported",
  "notes",
  "catalog_version",
  "catalog_url",
  "url",
  "sha256",
  "size",
];

/** catalog 的鍵集合（SPEC 第 5 節的 `Catalog` 契約）。 */
export const CATALOG_KEYS = ["catalog_version", "sources", "instruments"];
export const SOURCE_KEYS = ["id", "display_name", "supported_intervals", "needs_api_key"];
export const INSTRUMENT_KEYS = ["symbol", "interval", "source_id", "display_name"];

/** 快取標頭：可公開快取 5 分鐘；來源掛掉時允許再用一天（靜態內容的 resilience）。 */
export const CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=86400";

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const STAMP_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireText(payload, name, errors) {
  const value = payload[name];
  if (typeof value !== "string" || value.trim() === "") {
    errors.push(`${name} 必須是非空字串`);
    return null;
  }
  return value;
}

/**
 * 檢查鍵的集合：`required` 一個都不能少、聯集之外的一個都不能多。
 *
 * 分開 `required`／`optional` 是必要的：catalog 的商品一定要有 `symbol`／`interval`／
 * `source_id`（缺了就无法抓資料），但 `display_name` 可以省略（前端會退回代號）。
 */
function requireKeys(payload, { required, optional = [] }, where, errors) {
  const allowed = [...required, ...optional];
  for (const key of required) {
    if (!(key in payload)) {
      errors.push(`${where} 缺少鍵：${key}`);
    }
  }
  for (const key of Object.keys(payload)) {
    if (!allowed.includes(key)) {
      errors.push(`${where} 含未知鍵：${key}`);
    }
  }
}

function requireUrl(value, name, errors) {
  if (value === null) {
    return;
  }
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      errors.push(`${name} 必須是 http(s) 網址`);
    }
  } catch (error) {
    errors.push(`${name} 不是可解析的網址：${error.message}`);
  }
}

/**
 * 驗證 manifest；回傳**錯誤清單**（空陣列代表合法）。
 *
 * 回清單而不是丟例外：這個函式同時被「部署前的檢查」與「執行時的回應」使用，後者需要把
 * 所有問題一次告訴操作者，而不是第一個就中斷。
 */
export function validateManifest(payload) {
  const errors = [];
  if (!isObject(payload)) {
    return [`manifest 必須是 JSON 物件，收到 ${Array.isArray(payload) ? "array" : typeof payload}`];
  }
  requireKeys(payload, { required: MANIFEST_KEYS }, "manifest", errors);

  if (payload.schema !== 1) {
    errors.push(`schema 必須是 1，收到 ${JSON.stringify(payload.schema)}`);
  }

  const version = requireText(payload, "version", errors);
  if (version !== null && !VERSION_PATTERN.test(version)) {
    errors.push(`version 必須是 x.y.z，收到 ${JSON.stringify(version)}`);
  }

  const releasedAt = requireText(payload, "released_at", errors);
  if (releasedAt !== null && (!STAMP_PATTERN.test(releasedAt) || Number.isNaN(Date.parse(releasedAt)))) {
    errors.push(`released_at 必須是 UTC ISO 8601（秒級、以 Z 結尾），收到 ${JSON.stringify(releasedAt)}`);
  }

  requireText(payload, "min_supported", errors);
  requireText(payload, "notes", errors);

  const catalogVersion = requireText(payload, "catalog_version", errors);
  if (catalogVersion !== null && !DATE_PATTERN.test(catalogVersion)) {
    errors.push(`catalog_version 必須是 YYYY-MM-DD，收到 ${JSON.stringify(catalogVersion)}`);
  }

  for (const name of ["catalog_url", "url"]) {
    const value = requireText(payload, name, errors);
    requireUrl(value, name, errors);
  }

  const sha256 = requireText(payload, "sha256", errors);
  if (sha256 !== null && !SHA256_PATTERN.test(sha256)) {
    errors.push(`sha256 必須是 64 個小寫十六進位字元，收到 ${JSON.stringify(sha256)}`);
  }

  if (!Number.isInteger(payload.size) || payload.size < 0) {
    errors.push(`size 必須是 >= 0 的整數，收到 ${JSON.stringify(payload.size)}`);
  }

  return errors;
}

/** 驗證 catalog（SPEC 第 5 節的 `Catalog` 契約）；回傳錯誤清單。 */
export function validateCatalog(payload) {
  const errors = [];
  if (!isObject(payload)) {
    return [`catalog 必須是 JSON 物件，收到 ${Array.isArray(payload) ? "array" : typeof payload}`];
  }
  requireKeys(payload, { required: CATALOG_KEYS }, "catalog", errors);

  const version = requireText(payload, "catalog_version", errors);
  if (version !== null && !DATE_PATTERN.test(version)) {
    errors.push(`catalog_version 必須是 YYYY-MM-DD，收到 ${JSON.stringify(version)}`);
  }

  if (!Array.isArray(payload.sources) || payload.sources.length === 0) {
    errors.push("sources 必須是非空陣列");
  } else {
    payload.sources.forEach((source, index) => {
      const where = `sources[${index}]`;
      if (!isObject(source)) {
        errors.push(`${where} 必須是物件`);
        return;
      }
      requireKeys(source, { required: ["id"], optional: ["display_name", "supported_intervals", "needs_api_key"] }, where, errors);
      requireText(source, "id", errors);
      if (source.display_name !== undefined && typeof source.display_name !== "string") {
        errors.push(`${where}.display_name 必須是字串`);
      }
      if (source.supported_intervals !== undefined) {
        if (!Array.isArray(source.supported_intervals)) {
          errors.push(`${where}.supported_intervals 必須是陣列`);
        } else if (source.supported_intervals.some((item) => typeof item !== "string" || item.trim() === "")) {
          errors.push(`${where}.supported_intervals 必須是非空字串陣列`);
        }
      }
      if (source.needs_api_key !== undefined && typeof source.needs_api_key !== "boolean") {
        errors.push(`${where}.needs_api_key 必須是布林值`);
      }
      if (typeof source.id === "string" && source.id.trim() === "") {
        errors.push(`${where}.id 必須是非空字串`);
      }
    });
  }

  if (!Array.isArray(payload.instruments) || payload.instruments.length === 0) {
    errors.push("instruments 必須是非空陣列");
  } else {
    const known = new Set(
      Array.isArray(payload.sources)
        ? payload.sources.filter((source) => isObject(source)).map((source) => String(source.id))
        : []
    );
    payload.instruments.forEach((instrument, index) => {
      const where = `instruments[${index}]`;
      if (!isObject(instrument)) {
        errors.push(`${where} 必須是物件`);
        return;
      }
      requireKeys(
        instrument,
        { required: ["symbol", "interval", "source_id"], optional: ["display_name"] },
        where,
        errors
      );
      requireText(instrument, "symbol", errors);
      requireText(instrument, "interval", errors);
      const sourceId = requireText(instrument, "source_id", errors);
      if (sourceId !== null && !known.has(sourceId)) {
        errors.push(`${where}.source_id 不在 sources 裡：${JSON.stringify(sourceId)}`);
      }
      if (instrument.display_name !== undefined && typeof instrument.display_name !== "string") {
        errors.push(`${where}.display_name 必須是字串`);
      }
    });
  }

  return errors;
}

/**
 * 兩個快照必須來自同一份快照：manifest 的 `catalog_version` 要等於 catalog 的版本。
 *
 * 分開成一個函式（而不是寫在測試裡）是因為部署前也該跑同一條檢查：版本錯位會讓客戶端
 * 以為 catalog 過期而下載一份其實相同的檔案（或反之）。
 */
export function validateSnapshot(manifest, catalog) {
  const errors = [
    ...validateManifest(manifest).map((error) => `manifest：${error}`),
    ...validateCatalog(catalog).map((error) => `catalog：${error}`),
  ];
  if (
    isObject(manifest) &&
    isObject(catalog) &&
    typeof manifest.catalog_version === "string" &&
    typeof catalog.catalog_version === "string" &&
    manifest.catalog_version !== catalog.catalog_version
  ) {
    errors.push(
      `catalog_version 不一致：manifest=${manifest.catalog_version}、catalog=${catalog.catalog_version}`
    );
  }
  return errors;
}

function staticResponse(payload, errors) {
  if (errors.length > 0) {
    return {
      status: 500,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
      body: JSON.stringify({
        error: { code: "invalid_snapshot", message: "靜態快照不合法（部署前請先修正）", details: errors },
      }),
    };
  }
  return {
    status: 200,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": CACHE_CONTROL },
    body: JSON.stringify(payload),
  };
}

/** `GET /v1/latest` 的回應（`env` 刻意不使用）。 */
export function manifestResponse(manifest, _env) {
  return staticResponse(manifest, validateManifest(manifest));
}

/** `GET /catalog.json` 的回應（`env` 刻意不使用）。 */
export function catalogResponse(catalog, _env) {
  return staticResponse(catalog, validateCatalog(catalog));
}
