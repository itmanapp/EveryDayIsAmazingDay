-- ediaad 授權後端的 D1 schema（TASK-033 交付；五張表的後台操作屬 TASK-035）。
--
-- 五張表對應報告第 6.7 節：
--   keys      密鑰、狀態、features、到期（`expires_at` 是續期導流的判斷依據）
--   devices   裝置指紋、平台、版本與最近看到時間
--   renewals  每次成功的驗證一筆，含 trigger（start／timer／manual）
--   blacklist 已撤銷的指紋（重新申請頁對它自動拒絕）
--   audit     後台寫入操作的稽核紀錄
--
-- 全部使用 `IF NOT EXISTS`：本檔可以重複套用（`wrangler d1 execute --file` 的幂等前提）。

CREATE TABLE IF NOT EXISTS keys (
  key_id          TEXT PRIMARY KEY,
  secret          TEXT NOT NULL UNIQUE,
  status          TEXT NOT NULL DEFAULT 'issued'
                  CHECK (status IN ('issued', 'active', 'expired', 'revoked')),
  features        TEXT NOT NULL DEFAULT '["start"]',
  expires_at      TEXT,
  catalog_version TEXT,
  machine         TEXT,
  created_at      TEXT NOT NULL,
  activated_at    TEXT,
  last_renewed_at TEXT
);

CREATE TABLE IF NOT EXISTS devices (
  fingerprint TEXT PRIMARY KEY,
  key_id      TEXT,
  platform    TEXT,
  version     TEXT,
  first_seen  TEXT NOT NULL,
  last_seen   TEXT NOT NULL
);

-- `INTEGER PRIMARY KEY`（不用 AUTOINCREMENT）：兩者都會自動配號，但 AUTOINCREMENT 會多出
-- SQLite 內部的 `sqlite_sequence` 表，讓「恰五張表」的驗證與 D1 的實際狀態都變模糊。
CREATE TABLE IF NOT EXISTS renewals (
  id          INTEGER PRIMARY KEY,
  key_id      TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  trigger     TEXT NOT NULL CHECK (trigger IN ('start', 'timer', 'manual')),
  version     TEXT,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blacklist (
  fingerprint TEXT PRIMARY KEY,
  key_id      TEXT,
  reason      TEXT,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
  id         INTEGER PRIMARY KEY,
  actor      TEXT NOT NULL,
  action     TEXT NOT NULL,
  target     TEXT,
  details    TEXT,
  created_at TEXT NOT NULL
);

-- 統計與清單查詢用（活躍使用者 ≈ 過去 30 天有 renew 的 distinct key_id）。
CREATE INDEX IF NOT EXISTS idx_renewals_key_id ON renewals (key_id);
CREATE INDEX IF NOT EXISTS idx_renewals_trigger ON renewals (trigger);
CREATE INDEX IF NOT EXISTS idx_renewals_created_at ON renewals (created_at);
CREATE INDEX IF NOT EXISTS idx_devices_key_id ON devices (key_id);
CREATE INDEX IF NOT EXISTS idx_keys_status ON keys (status);
