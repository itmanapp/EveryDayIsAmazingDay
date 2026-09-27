// 公開重新申請頁（TASK-035／AC-063）：過期者自助重新申請，黑名單指紋自動拒絕。
//
// 規則是「**先查黑名單、再確認真的過期、才發新密鑰**」：
//   * 指紋在黑名單 → 403（不產生密鑰、不留稽核）
//   * 有紀錄但還沒過期 → 409（附上到期日，請對方等過期或找作者延長）
//   * 完全沒有紀錄 → 404（必須先用密鑰啟用過一次，才知道這個指紋是誰）
//   * 已撤銷但沒進黑名單（資料被手動改過）→ 403
// 只有「確實過期」才會產生新密鑰，而且新密鑰**沒有任何授權**，仍要使用者自己完成啟用。
//
// 這一頁與 `/v1/activate`／`/v1/renew` 共用同一個 D1 綁定，但**不需要任何簽章私鑰**：
// 重新申請只是「換一把新密鑰」，授權仍然要經由啟用流程簽發。

import {
  RequestError,
  errorResponse,
  jsonResponse,
  logUnexpected,
  readJsonBody,
  requireDb,
  requireMachine,
  requireMethod,
  resolveNow,
} from "./http.js";
import { createKeys, parseKeyFeatures } from "./admin.js";
import * as store from "./db.js";

export const REAPPLY_PATH = "/reapply";
export const DEFAULT_REAPPLY_FEATURES = ["start", "update"];

/** 指紋是否在黑名單（薄轉接 `db.js`：黑名單的 SQL 只有一份）。 */
export async function isBlacklisted(db, fingerprint) {
  return store.isBlacklisted(db, fingerprint);
}

/** 找出該指紋**已過期**的密鑰；時間比較在 SQL 裡做（UTC `...Z` 字串可直接比較）。 */
export async function findExpiredKey(db, fingerprint, options = {}) {
  const now = resolveNow(options);
  return store.findExpiredKeyForFingerprint(db, fingerprint, new Date(now).toISOString().replace(/\.\d{3}Z$/, "Z"));
}

function resolveFingerprint(body) {
  return requireMachine(body.fingerprint ?? body.machine);
}

export async function handleReapply(request, env, options = {}) {
  try {
    requireMethod(request, "POST");
    const body = await readJsonBody(request);
    const fingerprint = resolveFingerprint(body);
    const db = requireDb(env);
    const now = resolveNow(options);

    if (await isBlacklisted(db, fingerprint)) {
      return errorResponse(403, "blacklisted", `這台機器（${fingerprint}）已被列入黑名單：請聯絡作者`);
    }

    const latest = await store.findKeyForFingerprint(db, fingerprint);
    if (latest === null || latest === undefined) {
      return errorResponse(
        404,
        "unknown_fingerprint",
        "找不到這個機器指紋的授權紀錄：請先在軟體中輸入密鑰完成啟用"
      );
    }
    if (latest.status === "revoked") {
      return errorResponse(403, "revoked", "這把密鑰已被撤銷：請聯絡作者");
    }

    const expiresAt = latest.expires_at ? Date.parse(latest.expires_at) : Number.NaN;
    if (!Number.isFinite(expiresAt) || expiresAt >= now) {
      return errorResponse(
        409,
        "still_valid",
        `授權仍在有效期內（到期 ${latest.expires_at ?? "未設定"}）：不需要重新申請`
      );
    }

    const features = parseKeyFeatures(latest.features) ?? DEFAULT_REAPPLY_FEATURES;
    const [created] = await createKeys(db, 1, features, `reapply:${fingerprint}`, "reapply", { now });
    return jsonResponse(200, {
      key_id: created.key_id,
      secret: created.secret,
      status: created.status,
      features: created.features,
      message: "已產生新的密鑰：請在軟體中輸入它完成啟用",
    });
  } catch (error) {
    if (error instanceof RequestError) {
      return errorResponse(error.status, error.code, error.message);
    }
    logUnexpected(error);
    return errorResponse(500, "internal_error", "授權服務內部錯誤（請稍後再試）");
  }
}

/** 最小可用的申請頁：一個表單、一段行內程式，沒有外部資源。 */
export function reapplyPage() {
  return `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ediaad 重新申請密鑰</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 40rem; padding: 0 1rem; }
  label { display: block; margin: 1rem 0 0.25rem; }
  input { width: 100%; padding: 0.5rem; font-family: monospace; }
  button { margin-top: 1rem; padding: 0.6rem 1.2rem; }
  #result { margin-top: 1.5rem; white-space: pre-wrap; font-family: monospace; }
  .hint { color: #555; }
</style>
</head>
<body>
<h1>重新申請密鑰</h1>
<p>授權過期後可以自助重新申請。<strong>已撤銷或已列入黑名單的機器會被自動拒絕。</strong></p>
<p class="hint">機器指紋可在軟體的「授權」頁看到（16 碼小寫十六進位）。</p>
<form id="reapply-form">
  <label for="fingerprint">機器指紋</label>
  <input id="fingerprint" name="fingerprint" type="text" autocomplete="off"
         pattern="[0-9a-f]{16}" placeholder="例如 0123456789abcdef" required />
  <button type="submit">送出申請</button>
</form>
<p id="result" role="status" aria-live="polite"></p>
<script>
  document.getElementById("reapply-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var fingerprint = document.getElementById("fingerprint").value.trim();
    var result = document.getElementById("result");
    result.textContent = "處理中…";
    fetch(${JSON.stringify(REAPPLY_PATH)}, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fingerprint: fingerprint })
    })
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (payload.secret) {
          result.textContent = "新密鑰（請立刻記下）：" + payload.secret + "\\n" + (payload.message || "");
        } else {
          result.textContent = "無法重新申請：" + (payload.message || payload.error && payload.error.message || "未知原因");
        }
      })
      .catch(function () { result.textContent = "無法連線授權服務"; });
  });
</script>
</body>
</html>
`;
}

/** `GET /reapply` 的 handler（方法不對時回 405 JSON）。 */
export function handleReapplyPage(request, _env, _options = {}) {
  try {
    requireMethod(request, "GET");
  } catch (error) {
    if (error instanceof RequestError) {
      return errorResponse(error.status, error.code, error.message);
    }
    return errorResponse(500, "internal_error", "授權服務內部錯誤（請稍後再試）");
  }
  return new Response(reapplyPage(), {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}
