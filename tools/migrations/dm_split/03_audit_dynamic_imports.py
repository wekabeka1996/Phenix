"""Audit risky dynamic or string-based decision_making imports.

Input: repository text files under apps, tests, tools, and scripts.
Output: artifacts/audit_report.md.
Side effects: writes the audit report unless --dry-run is passed.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from dm_split_lib import ARTIFACTS, OLD_PREFIX, ROOT, build_rename_plan, load_move_map

SEARCH_ROOTS = ("apps", "tests", "tools", "scripts")
ALLOWLIST = (
    "tools/migrations/dm_split/03_audit_dynamic_imports.py",
    "tools/migrations/dm_split/08_verify.py",
)


def _dynamic_findings(path: Path, rel_path: str, text: str, plan: dict[str, str]) -> tuple[list[str], list[str]]:
    if path.suffix != ".py":
        return [], []
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError as exc:
        return [f"- {rel_path}:{exc.lineno or 0}: BLOCKED unparsable Python"], []
    findings: list[str] = []
    controlled: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_import_module = (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
        )
        is_dunder_import = isinstance(func, ast.Name) and func.id == "__import__"
        if not (is_import_module or is_dunder_import):
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            if OLD_PREFIX in first_arg.value:
                if first_arg.value in plan:
                    controlled.append(f"- {rel_path}:{node.lineno}: `{first_arg.value}` -> `{plan[first_arg.value]}`")
                else:
                    findings.append(f"- {rel_path}:{node.lineno}: BLOCKED unmanaged `{first_arg.value}`")
        elif isinstance(first_arg, ast.JoinedStr):
            findings.append(f"- {rel_path}:{node.lineno}: BLOCKED f-string dynamic import")
    return findings, controlled


def audit() -> str:
    findings: list[str] = []
    controlled: list[str] = []
    plan = build_rename_plan(load_move_map())
    for rel in SEARCH_ROOTS:
        root = ROOT / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_dir() or path.suffix not in {".py", ".yaml", ".yml", ".json", ".md"}:
                continue
            rel_path = path.relative_to(ROOT).as_posix()
            if rel_path in ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            if "apps.reference.domains.decision_making" not in text:
                continue
            blocked, managed = _dynamic_findings(path, rel_path, text, plan)
            findings.extend(blocked)
            controlled.extend(managed)
    lines = ["# Dynamic Import Audit", ""]
    if findings:
        lines.append("BLOCKED: dynamic decision_making references require manual review.")
        lines.extend(findings)
    else:
        lines.append("No dynamic decision_making imports found.")
    if controlled:
        lines.append("")
        lines.append("Controlled string module references covered by rename_plan:")
        lines.extend(controlled)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.dry_run:
        print(report)
    else:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / "audit_report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
