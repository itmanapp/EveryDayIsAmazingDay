// 續租端點（TASK-033／AC-060）：`POST /v1/renew`。
//
// 客戶端（`ediaad.license.renew`）送 `{"key": <key_id>, "machine": <指紋>, "trigger": ...}`。
// **注意 `key` 在這裡是 `key_id`**（租約裡的那個識別碼），不是使用者輸入的密鑰 secret——
// 客戶端只有租約，沒有 secret。
//
// 導流閘門（本張最重要的一條）：
// - 已撤銷（密鑰狀態或指紋在黑名單）→ **403 ＋ `status:"revoked"`**，客戶端據此落地撤銷
//   標記並停止服務。
// - 已過期（`keys.expires_at` 早於現在，或該欄位無法解讀）→ **403 ＋ `status:"expired"`**，
//   客戶端據此顯示重新申請訊息，**不會**用舊租約一直續期。
// 兩者都**不寫 renewals、不延長到期**。
//
// 機器不符是 409（衝突）而不是 403：它不該被客戶端當成「要重新申請」。

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
import { getKeyById, insertRenewal, isBlacklisted, markKeyRenewed, upsertDevice } from "./db.js";
import { leasePayload, signLease, utcStamp } from "./lease.js";

/** `trigger` 的合法值（與 TASK-031 的 `RENEW_TRIGGERS` 及 D1 的 CHECK 約束一致）。 */
export const RENEW_TRIGGERS = ["start", "timer", "manual"];

function requireTrigger(body) {
  const value = body.trigger;
  if (typeof value !== "string" || !RENEW_TRIGGERS.includes(value)) {
    throw new RequestError(
      400,
      "invalid_field",
      `trigger 必須是 ${RENEW_TRIGGERS.map((item) => JSON.stringify(item)).join("／")} 之一`
    );
  }
  return value;
}

export async function handleRenew(request, env, options = {}) {
  try {
    requireMethod(request, "POST");
    const body = await readJsonBody(request);
    const keyId = requireText(body, "key");
    const machine = requireMachine(body.machine);
    const trigger = requireTrigger(body);
    const version = optionalText(body, "version");
    const now = resolveNow(options);

    const db = requireDb(env);
    const keyRow = await getKeyById(db, keyId);
    if (keyRow === null || keyRow === undefined) {
      return errorResponse(404, "unknown_key", `找不到密鑰 ${keyId}：請確認輸入是否正確`);
    }

    if (keyRow.status === "revoked" || (await isBlacklisted(db, machine))) {
      return errorResponse(403, "revoked", `密鑰 ${keyId} 已被撤銷：請重新申請新密鑰`, {
        status: "revoked",
      });
    }

    const expiresAt = keyRow.expires_at;
    if (expiresAt !== null && expiresAt !== undefined && String(expiresAt).trim() !== "") {
      const expiry = Date.parse(expiresAt);
      // 讀不懂的到期時間一律視為過期（fail closed）：資料壞掉時不能默默延長授權。
      if (!Number.isFinite(expiry) || expiry < now) {
        return errorResponse(
          403,
          "expired",
          `授權已於 ${expiresAt} 到期：請重新申請新密鑰，本機不會以舊租約續用`,
          { status: "expired" }
        );
      }
    }

    if (keyRow.machine !== null && keyRow.machine !== undefined && keyRow.machine !== "" && keyRow.machine !== machine) {
      return errorResponse(
        409,
        "machine_mismatch",
        `這把密鑰已綁定另一台機器（${keyRow.machine}）：請在原本的機器上使用或重新申請`
      );
    }

    const payload = leasePayload(keyRow, machine, now, resolveCatalogVersion(keyRow, env));
    const lease = await signLease(payload, env);
    const stamp = utcStamp(now);

    await insertRenewal(db, {
      keyId: lease.key_id,
      fingerprint: machine,
      trigger,
      createdAt: stamp,
      version,
    });
    await upsertDevice(db, {
      fingerprint: machine,
      keyId: lease.key_id,
      platform: optionalText(body, "platform"),
      version,
      seenAt: stamp,
    });
    await markKeyRenewed(db, {
      keyId: lease.key_id,
      machine,
      expiresAt: lease.expires_at,
      renewedAt: stamp,
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
