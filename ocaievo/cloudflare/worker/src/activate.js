// 啟用端點（TASK-033／AC-060）：`POST /v1/activate`。
//
// 客戶端（`ediaad.license.activate`）送 `{"key": <密鑰>, "machine": <指紋>}`，並要求回應
// **就是租約物件本身**（不多包一層），且租約屬於這台機器、長度恰為 30 天、簽章有效。
// 因此這裡的成功回應就是 `signLease` 的輸出，一個欄位都不多加（多一個鍵，客戶端的
// `Lease.from_json` 就會拒絕）。
//
// 拒絕的層次：未知密鑰 404、已撤銷 403、指紋在黑名單 403——**都不會簽出任何租約**，
// 也不會改動密鑰狀態或留下裝置紀錄。

import {
  RequestError,
  errorResponse,
  jsonResponse,
  requireDb,
  requireMachine,
  requireMethod,
  requireText,
  optionalText,
  logUnexpected,
  readJsonBody,
  resolveCatalogVersion,
  resolveNow,
  toErrorResponse,
} from "./http.js";
import { getKeyBySecret, isBlacklisted, markKeyActivated, upsertDevice } from "./db.js";
import { leasePayload, signLease, utcStamp } from "./lease.js";

/**
 * 以密鑰（secret）查詢密鑰列；找不到回 `null`。
 *
 * **已撤銷的密鑰仍然回傳整列**（不是 `null`）：handler 才能分辨「查無此密鑰」與
 * 「這把密鑰被撤銷了」——兩者要給使用者不同的訊息（與 F-003 同一條紀律）。
 */
export async function verifyLicenseKey(key, env) {
  const db = requireDb(env);
  return getKeyBySecret(db, key);
}

export async function handleActivate(request, env, options = {}) {
  try {
    requireMethod(request, "POST");
    const body = await readJsonBody(request);
    const secret = requireText(body, "key");
    const machine = requireMachine(body.machine);
    const platform = optionalText(body, "platform");
    const version = optionalText(body, "version");
    const now = resolveNow(options);

    const db = requireDb(env);
    const keyRow = await verifyLicenseKey(secret, env);
    if (keyRow === null || keyRow === undefined) {
      return errorResponse(404, "unknown_key", "找不到這把密鑰：請確認輸入是否正確");
    }
    if (keyRow.status === "revoked") {
      return errorResponse(403, "revoked", "這把密鑰已被撤銷：請重新申請新密鑰");
    }
    if (await isBlacklisted(db, machine)) {
      return errorResponse(403, "blacklisted", `這台機器（${machine}）已被列入黑名單：請聯絡作者`);
    }

    const payload = leasePayload(keyRow, machine, now, resolveCatalogVersion(keyRow, env));
    const lease = await signLease(payload, env);
    const stamp = utcStamp(now);

    await upsertDevice(db, {
      fingerprint: machine,
      keyId: lease.key_id,
      platform,
      version,
      seenAt: stamp,
    });
    await markKeyActivated(db, {
      keyId: lease.key_id,
      machine,
      expiresAt: lease.expires_at,
      activatedAt: stamp,
    });

    return jsonResponse(200, lease);
  } catch (error) {
    if (error instanceof RequestError) {
      return errorResponse(error.status, error.code, error.message);
    }
    logUnexpected(error);
    return toErrorResponse(error);
  }
}
