// 記憶體假 D1（TASK-033／TASK-035 共用）。
//
// **刻意建立在 `node:sqlite` 之上**：D1 就是 SQLite，因此這個假替身執行的是**真的 SQL**
// （真的建表語句、真的欄位名、真的 UNIQUE 與 CHECK 約束）。手寫一個「看起來像 SQL」的
// 字串比對替身會讓 `schema.sql` 的錯字與查詢的欄位錯誤都測不出來——那種替身通過的測試
// 沒有證據價值。與真實 D1 的差異（網路、`meta` 的細節、migration 行為）在 DELIVERY 明列。
//
// 介面刻意對齊 D1 的 `prepare().bind().first()/all()/run()`：
// - `first()` 回傳單列或 `null`
// - `all()` 回傳 `{ results, success }`
// - `run()` 回傳 `{ success, meta: { changes, last_row_id } }`
// 真實 D1 的這些方法是 async；本替身是同步，但 Worker 一律 `await`，兩邊都能用。

import { DatabaseSync } from "node:sqlite";

class FakeStatement {
  constructor(statement, sql, params = []) {
    this.statement = statement;
    this.sql = sql;
    this.params = params;
  }

  bind(...params) {
    return new FakeStatement(this.statement, this.sql, params);
  }

  first(column) {
    const row = this.statement.get(...this.params) ?? null;
    if (row === null || column === undefined) {
      return row;
    }
    return row[column] ?? null;
  }

  all() {
    return { results: this.statement.all(...this.params), success: true, meta: {} };
  }

  run() {
    const result = this.statement.run(...this.params);
    return {
      success: true,
      results: [],
      meta: { changes: result.changes, last_row_id: Number(result.lastInsertRowid) },
    };
  }
}

export class FakeD1 {
  constructor(sqlText) {
    this.db = new DatabaseSync(":memory:");
    if (sqlText) {
      this.db.exec(sqlText);
    }
  }

  exec(sql) {
    this.db.exec(sql);
    return { success: true };
  }

  prepare(sql) {
    return new FakeStatement(this.db.prepare(sql), sql);
  }

  batch(statements) {
    return statements.map((statement) => statement.run());
  }

  tableNames() {
    // SQLite 的內部表（`sqlite_*`）不算 schema 的一部分；真實 D1 也有自己的內部表。
    return this.db
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
      .all()
      .map((row) => row.name)
      .filter((name) => !name.startsWith("sqlite_"));
  }

  columns(table) {
    return this.db
      .prepare(`PRAGMA table_info(${table})`)
      .all()
      .map((row) => row.name);
  }

  close() {
    this.db.close();
  }
}

export function createFakeD1(sqlText) {
  return new FakeD1(sqlText);
}
