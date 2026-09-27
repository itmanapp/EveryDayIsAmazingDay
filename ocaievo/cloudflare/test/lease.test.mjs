// 租約內容與簽章（TASK-033／AC-060）。
//
// 最重要的兩條：**canonical JSON 必須與 Python `signing_payload` 逐字相同**、**Node 簽出來
// 的簽章必須等於 Python 夾具簽出來的值**。兩者都用固定的金標值（golden）釘住，因此
// 「Worker 簽的租約能被客戶端驗章」不是宣稱而是交叉實作的證據。

import assert from "node:assert/strict";
import test from "node:test";

import { LEASE_DAYS, canonicalJson, leasePayload, signLease, utcStamp } from "../worker/src/lease.js";

import {
  GOLDEN_CANONICAL,
  GOLDEN_PAYLOAD,
  GOLDEN_SIGNATURE,
  ISSUED_AT,
  EXPIRES_AT,
  NOW_MS,
  licenseEnv,
  referenceCanonical,
  verifyLeaseSignature,
} from "./support.mjs";

test("canonical JSON 與 Python 的 signing_payload 逐字相同", () => {
  assert.equal(canonicalJson(GOLDEN_PAYLOAD), GOLDEN_CANONICAL);
  assert.equal(canonicalJson(GOLDEN_PAYLOAD), referenceCanonical(GOLDEN_PAYLOAD));
});

test("canonical JSON 不依賴鍵的插入順序", () => {
  const shuffled = {
    machine: GOLDEN_PAYLOAD.machine,
    key_id: GOLDEN_PAYLOAD.key_id,
    catalog_version: GOLDEN_PAYLOAD.catalog_version,
    features: [...GOLDEN_PAYLOAD.features],
    issued_at: GOLDEN_PAYLOAD.issued_at,
    expires_at: GOLDEN_PAYLOAD.expires_at,
  };
  assert.equal(canonicalJson(shuffled), GOLDEN_CANONICAL);
});

test("Node 的 Ed25519 簽章與 Python 夾具逐字相同", async () => {
  const lease = await signLease(GOLDEN_PAYLOAD, licenseEnv());

  assert.equal(lease.sig, GOLDEN_SIGNATURE, "同一把測試金鑰與同一組 bytes 必須得到同一個簽章");
  assert.match(lease.sig, /^[0-9a-f]{128}$/, "客戶端要求 128 個小寫十六進位字元");
});

test("簽章涵蓋到期日：改一位元就驗不過", async () => {
  const lease = await signLease(GOLDEN_PAYLOAD, licenseEnv());

  assert.equal(await verifyLeaseSignature(lease, canonicalJson), true);
  const tampered = { ...lease, expires_at: "2026-10-25T12:00:00Z" };
  assert.equal(await verifyLeaseSignature(tampered, canonicalJson), false);
  const tamperedMachine = { ...lease, machine: "ffffffffffffffff" };
  assert.equal(await verifyLeaseSignature(tamperedMachine, canonicalJson), false);
});

test("utcStamp 產生 SPEC 格式：秒級、以 Z 結尾、不含毫秒", () => {
  assert.equal(utcStamp(NOW_MS), ISSUED_AT);
  assert.equal(utcStamp(Date.parse("2026-09-24T12:00:00.987Z")), ISSUED_AT);
  assert.match(utcStamp(NOW_MS), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
});

test("leasePayload 是 30 天，且欄位恰為 SPEC 第 5 節的六個（sig 之後才加）", () => {
  const keyRow = {
    key_id: "EDIAAD-2026-0001",
    features: JSON.stringify(["start"]),
    catalog_version: "2026-10-01",
  };

  const payload = leasePayload(keyRow, "0123456789abcdef", NOW_MS, "2026-10-01");

  assert.deepEqual(Object.keys(payload).sort(), [
    "catalog_version",
    "expires_at",
    "features",
    "issued_at",
    "key_id",
    "machine",
  ]);
  assert.equal(payload.issued_at, ISSUED_AT);
  assert.equal(payload.expires_at, EXPIRES_AT);
  assert.equal(
    (Date.parse(payload.expires_at) - Date.parse(payload.issued_at)) / 86400000,
    LEASE_DAYS
  );
  assert.deepEqual(payload.features, ["start"]);
  assert.equal(payload.catalog_version, "2026-10-01");
  assert.equal(payload.machine, "0123456789abcdef");
});

test("leasePayload 對不合法輸入丟出可讀錯誤", () => {
  const keyRow = { key_id: "EDIAAD-2026-0001", features: JSON.stringify(["start"]) };

  assert.throws(() => leasePayload(keyRow, "not-hex", NOW_MS, "2026-10-01"), /machine/);
  assert.throws(() => leasePayload(keyRow, "0123456789abcdef", NOW_MS, ""), /catalog_version/);
  assert.throws(
    () => leasePayload({ ...keyRow, features: "{not json" }, "0123456789abcdef", NOW_MS, "2026-10-01"),
    /features/
  );
  assert.throws(
    () => leasePayload({ ...keyRow, features: JSON.stringify([]) }, "0123456789abcdef", NOW_MS, "2026-10-01"),
    /features/
  );
});

test("缺少或損毀的私鑰 secret 一律拒絕簽章，且訊息指出原因（不簽出無效租約）", async () => {
  await assert.rejects(() => signLease(GOLDEN_PAYLOAD, {}), /LICENSE_PRIVATE_KEY_JWK/);
  await assert.rejects(
    () => signLease(GOLDEN_PAYLOAD, { LICENSE_PRIVATE_KEY_JWK: "   " }),
    /LICENSE_PRIVATE_KEY_JWK/
  );
  await assert.rejects(
    () => signLease(GOLDEN_PAYLOAD, { LICENSE_PRIVATE_KEY_JWK: "{not json" }),
    /LICENSE_PRIVATE_KEY_JWK/
  );
  await assert.rejects(
    () => signLease(GOLDEN_PAYLOAD, { LICENSE_PRIVATE_KEY_JWK: JSON.stringify({ kty: "oct", k: "AAAA" }) }),
    /OKP|Ed25519/,
    "型別不對要說型別不對"
  );
  await assert.rejects(
    () => signLease(GOLDEN_PAYLOAD, { LICENSE_PRIVATE_KEY_JWK: JSON.stringify({ kty: "OKP", crv: "Ed25519" }) }),
    /d 或 x/
  );
  await assert.rejects(
    () =>
      signLease(GOLDEN_PAYLOAD, {
        LICENSE_PRIVATE_KEY_JWK: JSON.stringify({ kty: "OKP", crv: "Ed25519", d: "", x: "AAAA" }),
      }),
    /d 或 x/,
    "空字串的 d 等同缺少"
  );
});
