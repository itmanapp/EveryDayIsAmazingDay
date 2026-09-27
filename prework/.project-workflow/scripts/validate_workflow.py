#!/usr/bin/env python3
"""Validate the bounded Markdown workflow contract using Python 3.10+ only."""

import argparse
import json
import re
import sys
from pathlib import Path


TASK_ID = re.compile(r"TASK-[0-9]{3,}\Z")
AC_ID = re.compile(r"AC-[0-9]{3,}\Z")
FIELD = re.compile(r"^- ([^：:]+)[：:]\s*(.*)$")
TASK_STATUSES = {"draft", "ready", "in_progress", "in_review", "blocked", "done", "cancelled"}
PHASES = {"discover", "spec", "tasks", "ready", "implement", "verify", "complete"}
GATED_PHASES = {"ready", "implement", "verify", "complete"}
TASK_FIELDS = {"id", "status", "spec_version", "ac_ids", "depends_on", "test_evidence", "review_evidence"}
TEST_FIELDS = {"task_id", "verification", "result", "checked_version", "alternative_reason"}
REVIEW_FIELDS = {"task_id", "spec_result", "quality_result", "blocking_count", "checked_version"}
PLACEHOLDERS = {"", "—", "-", "none", "null", "unknown", "pending", "not_run", "待填", "待盤點", "無", "未執行", "尚未執行", "尚未檢查"}


def prose_lines(text):
    """Skip fenced examples; the contract is ordinary, unindented Markdown."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if marker:
            run, tail = marker.groups()
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not tail.strip():
                fence = None
            continue
        if fence is None:
            yield number, line


class Validator:
    def __init__(self, project):
        self.project = project
        self.errors = []

    def error(self, path, message):
        try:
            label = path.relative_to(self.project).as_posix()
        except ValueError:
            label = str(path)
        self.errors.append(f"{label}: {message}")

    def local_path(self, reference, source, *, directory=False):
        """Resolve paths before reading, including symlinks in parent directories."""
        if (not reference or "\x00" in reference or "\\" in reference
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", reference)):
            self.error(source, f"路徑必須是專案根目錄相對路徑：{reference!r}")
            return None
        path = Path(reference)
        if path.is_absolute() or ".." in path.parts:
            self.error(source, f"拒絕絕對路徑或上層路徑：{reference!r}")
            return None
        try:
            resolved = (self.project / path).resolve(strict=True)
            if not resolved.is_relative_to(self.project):
                self.error(source, f"路徑越出專案（含 symlink）：{reference!r}")
                return None
            if not (resolved.is_dir() if directory else resolved.is_file()):
                self.error(source, f"路徑不是{'目錄' if directory else '一般檔案'}：{reference!r}")
                return None
        except (OSError, RuntimeError, ValueError) as error:
            self.error(source, f"路徑不存在或無法讀取：{reference!r}（{error}）")
            return None
        return resolved

    def read(self, path):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            self.error(path, f"無法讀取 UTF-8 文件：{error}")
            return ""
        if not text.strip():
            self.error(path, "文件不可為空")
        return text

    def fields(self, text, path, names):
        values = {}
        for number, line in prose_lines(text):
            match = FIELD.match(line)
            if match and match[1].strip() in names:
                key, value = match[1].strip(), match[2].strip()
                if key in values:
                    self.error(path, f"第 {number} 行重複欄位 {key}")
                else:
                    values[key] = value
        for key in sorted(names - values.keys()):
            if key != "alternative_reason":
                self.error(path, f"缺少欄位 {key}")
        return values

    def string_list(self, values, key, path, pattern=None):
        try:
            result = json.loads(values.get(key, ""))
        except (ValueError, TypeError):
            self.error(path, f"{key} 必須是 JSON 字串清單，例如 [] 或 [\"TASK-001\"]")
            return []
        if not isinstance(result, list) or any(not isinstance(item, str) or not item.strip() for item in result):
            self.error(path, f"{key} 必須是非空字串組成的 JSON 清單")
            return []
        if len(result) != len(set(result)):
            self.error(path, f"{key} 不可含重複值")
        if pattern and any(not pattern.fullmatch(item) for item in result):
            self.error(path, f"{key} 含不合法的穩定 ID")
        return result

    def acceptance_criteria(self, text, path):
        lines = list(prose_lines(text))
        criteria = {}
        tables = 0
        index = 0
        while index < len(lines):
            number, line = lines[index]
            cells = self.table_cells(line)
            if not cells or cells[0] not in {"AC", "AC ID"}:
                index += 1
                continue
            tables += 1
            if cells.count("status") != 1:
                self.error(path, f"第 {number} 行 AC 表格必須有唯一 status 欄（active／retired）")
                index += 1
                continue
            status_column = cells.index("status")
            width = len(cells)
            index += 1
            if index >= len(lines) or not self.is_separator(self.table_cells(lines[index][1]), width):
                self.error(path, f"第 {number} 行 AC 表格缺少 Markdown 分隔列")
                continue
            index += 1
            while index < len(lines):
                row_number, row = lines[index]
                parts = self.table_cells(row)
                if not parts:
                    break
                if len(parts) != width:
                    self.error(path, f"第 {row_number} 行 AC 表格欄數不符；儲存格內的 | 請寫成 \\|")
                elif not AC_ID.fullmatch(parts[0]):
                    self.error(path, f"第 {row_number} 行不合法 AC ID：{parts[0]!r}")
                else:
                    ac_id, status = parts[0], parts[status_column]
                    if ac_id in criteria:
                        self.error(path, f"重複 AC ID：{ac_id}")
                    if status not in {"active", "retired"}:
                        self.error(path, f"{ac_id} 的 status 必須是 active 或 retired")
                    criteria[ac_id] = status
                index += 1
        if tables != 1:
            self.error(path, f"SPEC 必須恰有一張 AC 權威表格；目前 {tables} 張")
        return criteria

    @staticmethod
    def table_cells(line):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return []
        return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]

    @staticmethod
    def is_separator(cells, width):
        return len(cells) == width and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)

    def evidence(self, reference, task_id, source, kind, require_pass):
        path = self.local_path(reference, source)
        if path is None:
            return None
        text = self.read(path)
        names = TEST_FIELDS if kind == "test" else REVIEW_FIELDS
        values = self.fields(text, path, names)
        if values.get("task_id") != task_id:
            self.error(path, f"task_id 必須對應 {task_id}")
        body = [line for _, line in prose_lines(text) if line.strip()
                and not line.startswith("#")
                and not (FIELD.match(line) and FIELD.match(line)[1].strip() in names)]
        if not body:
            self.error(path, "證據必須包含紀錄本文，不能只有標題與通過宣告")
        results = ("result",) if kind == "test" else ("spec_result", "quality_result")
        for key in results:
            if values.get(key) not in {"not_run", "passed", "failed"}:
                self.error(path, f"{key} 必須是 not_run、passed 或 failed")
            if require_pass and values.get(key) != "passed":
                self.error(path, f"done Task 的 {key} 必須宣告 passed，未執行不能作完成證據")
        if kind == "test":
            mode = values.get("verification")
            if mode not in {"tdd", "existing", "alternative"}:
                self.error(path, "verification 必須是 tdd、existing 或 alternative")
            if mode == "alternative" and values.get("alternative_reason", "").lower() in PLACEHOLDERS:
                self.error(path, "alternative 驗證必須有 alternative_reason")
        else:
            count = values.get("blocking_count", "")
            if count != "unknown" and not re.fullmatch(r"0|[1-9][0-9]*", count):
                self.error(path, "blocking_count 必須是 unknown 或非負整數")
            if require_pass and count != "0":
                self.error(path, "done Task 的 blocking_count 必須是 0")
        version = values.get("checked_version", "")
        if require_pass and version.lower() in PLACEHOLDERS:
            self.error(path, "done 證據的 checked_version 必須記錄被驗證版本／快照")
        return version

    def validate(self, workflow_dir):
        workflow = self.local_path(workflow_dir, self.project, directory=True)
        if workflow is None:
            return
        sources = {}
        for name in ("SPEC", "STATE"):
            path = self.local_path((workflow / f"{name}.md").relative_to(self.project).as_posix(), workflow)
            if path is not None:
                sources[name] = (path, self.read(path))
        if len(sources) != 2:
            return
        spec_path, spec_text = sources["SPEC"]
        state_path, state_text = sources["STATE"]
        spec = self.fields(spec_text, spec_path, {"Spec ID", "版本", "狀態"})
        state = self.fields(state_text, state_path, {"目前階段"})
        phase = state.get("目前階段")
        if phase not in PHASES:
            self.error(state_path, f"目前階段不合法：{phase!r}")
        if spec.get("狀態") not in {"draft", "ready", "superseded"}:
            self.error(spec_path, "狀態必須是 draft、ready 或 superseded（說明放在另行文字）")
        if not re.fullmatch(r"SPEC-[0-9]{3,}", spec.get("Spec ID", "")):
            self.error(spec_path, "Spec ID 必須使用 SPEC-001 形式")
        if spec.get("版本", "").lower() in PLACEHOLDERS:
            self.error(spec_path, "版本不可空白或使用待填值")
        criteria = self.acceptance_criteria(spec_text, spec_path)
        current_version = f"{spec.get('Spec ID')} v{spec.get('版本')}"
        tasks = {}
        task_dir = workflow / "tasks"
        if task_dir.exists() or task_dir.is_symlink():
            task_dir = self.local_path(task_dir.relative_to(self.project).as_posix(), workflow, directory=True)
            task_paths = sorted(task_dir.glob("*.md")) if task_dir else []
        else:
            task_paths = []
        for candidate in task_paths:
            path = self.local_path(candidate.relative_to(self.project).as_posix(), workflow)
            if path is None:
                continue
            values = self.fields(self.read(path), path, TASK_FIELDS)
            task_id = values.get("id", "")
            if not TASK_ID.fullmatch(task_id):
                self.error(path, "id 必須使用 TASK-001 形式")
            if task_id in tasks:
                self.error(path, f"重複 Task ID：{task_id}")
            status = values.get("status")
            if status not in TASK_STATUSES:
                self.error(path, f"status 不合法：{status!r}")
            if phase in GATED_PHASES and status != "cancelled" and values.get("spec_version") != current_version:
                self.error(path, f"spec_version 必須對應目前版本 {current_version}")
            values["ac_ids"] = self.string_list(values, "ac_ids", path, AC_ID)
            values["depends_on"] = self.string_list(values, "depends_on", path, TASK_ID)
            versions = []
            for field, kind in (("test_evidence", "test"), ("review_evidence", "review")):
                references = self.string_list(values, field, path)
                if status == "done" and not references:
                    self.error(path, f"done Task 必須有非空 {field} 本機證據引用")
                for reference in references:
                    version = self.evidence(reference, task_id, path, kind, status == "done")
                    if version is not None:
                        versions.append(version)
            if status == "done" and len(set(versions)) > 1:
                self.error(path, "done Task 的測試與 Review checked_version 必須一致")
            values["path"] = path
            tasks.setdefault(task_id, values)
        for task_id, task in tasks.items():
            for ac_id in task["ac_ids"]:
                if ac_id not in criteria:
                    self.error(task["path"], f"引用不存在的 AC：{ac_id}")
            for dependency in task["depends_on"]:
                if dependency not in tasks:
                    self.error(task["path"], f"depends_on 引用不存在的 Task：{dependency}")
                elif task["status"] != "cancelled" and tasks[dependency]["status"] == "cancelled":
                    self.error(task["path"], f"有效 Task 不可依賴 cancelled Task：{dependency}")
                elif task["status"] in {"in_progress", "in_review", "done"} and tasks[dependency]["status"] != "done":
                    self.error(task["path"], f"已開工／完成 Task 的依賴尚未 done：{dependency}")
        self.check_cycles(tasks)
        if phase in GATED_PHASES:
            if spec.get("狀態") != "ready":
                self.error(spec_path, "ready 及後續階段需要狀態為 ready 的 Spec")
            active_ac = {ac_id for ac_id, status in criteria.items() if status == "active"}
            active_tasks = [task for task in tasks.values() if task["status"] != "cancelled"]
            if not active_ac or not active_tasks:
                self.error(state_path, "ready 及後續階段至少需要一項 active AC 與一張未取消 Task")
            assigned = {ac_id for task in active_tasks for ac_id in task["ac_ids"]}
            for ac_id in sorted(active_ac - assigned):
                self.error(spec_path, f"active AC 尚未分配給未取消 Task：{ac_id}")
            if phase == "ready":
                for task in active_tasks:
                    if task["status"] == "draft":
                        self.error(task["path"], "ready 閘門不可留有 draft Task")
            if phase in {"verify", "complete"}:
                for task in active_tasks:
                    if task["status"] != "done":
                        self.error(task["path"], f"{phase} 不可留有未完成的範圍內 Task")

    def check_cycles(self, tasks):
        # Iterative DFS also handles long task lists without Python recursion limits.
        color = {}
        for root in tasks:
            if color.get(root):
                continue
            color[root] = 1
            stack = [(root, iter(tasks[root]["depends_on"]))]
            while stack:
                task_id, dependencies = stack[-1]
                dependency = next(dependencies, None)
                if dependency is None:
                    color[task_id] = 2
                    stack.pop()
                elif dependency in tasks:
                    if color.get(dependency) == 1:
                        self.error(tasks[task_id]["path"], f"depends_on 有循環：{task_id} → {dependency}")
                    elif not color.get(dependency):
                        color[dependency] = 1
                        stack.append((dependency, iter(tasks[dependency]["depends_on"])))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="目標專案根目錄")
    parser.add_argument("--workflow-dir", default="docs/workflow", help="相對於專案根的流程文件目錄")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        parser.error("project 必須是既有目錄")
    validator = Validator(project)
    validator.validate(args.workflow_dir)
    if validator.errors:
        print("\n".join(validator.errors), file=sys.stderr)
        return 1
    print("通過：流程文件結構與宣告一致；不代表測試實跑、Review 品質或實作授權已獲證明。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
