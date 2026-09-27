// 路由（TASK-033）：兩個公開端點，其餘一律可讀的 JSON 錯誤。
//
// `ROUTES` 是唯一的路徑 → handler 對照表（測試斷言它恰好兩個鍵，因此新增端點不會悄悄
// 上線）。`handleRequest` 就是 Worker 的 `fetch`，第三個參數在正式執行時是 Workers 的
// `ExecutionContext`（本服務不使用它）；測試以 `{ now }` 注入時鐘，`resolveNow` 只讀
// `options.now`，因此傳入 ctx 也無害。

import { handleActivate } from "./activate.js";
import { handleRenew } from "./renew.js";
import { handleReapply, handleReapplyPage } from "./reapply.js";
import { errorResponse } from "./http.js";

export const ROUTES = {
  "POST /v1/activate": handleActivate,
  "POST /v1/renew": handleRenew,
  // 公開重新申請頁（TASK-035／AC-063）：GET 給頁面、POST 給申請。
  "GET /reapply": handleReapplyPage,
  "POST /reapply": handleReapply,
};

export async function handleRequest(request, env, options = {}) {
  const { pathname } = new URL(request.url);
  const method = (request.method ?? "GET").toUpperCase();
  const handler = ROUTES[`${method} ${pathname}`];
  if (handler !== undefined) {
    return handler(request, env, options);
  }
  const allowed = Object.keys(ROUTES)
    .filter((key) => key.endsWith(` ${pathname}`))
    .map((key) => key.split(" ", 1)[0]);
  if (allowed.length > 0) {
    return errorResponse(405, "method_not_allowed", `${pathname} 只接受 ${allowed.join("／")}`);
  }
  return errorResponse(404, "not_found", `找不到路徑 ${pathname}`);
}

export default { fetch: handleRequest };
