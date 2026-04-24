"""Rewrite Python imports for the decision_making split.

Input: artifacts/rename_plan.json or dm_move_map.csv.
Output: rewritten .py files and optional unified diff.
Side effects: modifies Python files unless --dry-run is passed.
"""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path

import libcst as cst

from dm_split_lib import ARTIFACTS, OLD_PREFIX, ROOT, build_rename_plan, iter_python_files, load_move_map


def dotted_to_expr(dotted: str) -> cst.BaseExpression:
    expr: cst.BaseExpression | None = None
    for part in dotted.split("."):
        name = cst.Name(part)
        expr = name if expr is None else cst.Attribute(value=expr, attr=name)
    assert expr is not None
    return expr


def expr_to_dotted(expr: cst.CSTNode | None) -> str | None:
    if expr is None:
        return None
    if isinstance(expr, cst.Name):
        return expr.value
    if isinstance(expr, cst.Attribute):
        left = expr_to_dotted(expr.value)
        return f"{left}.{expr.attr.value}" if left else expr.attr.value
    return None


def relative_to_absolute(current_old_module: str, node: cst.ImportFrom) -> str | None:
    if not node.relative:
        return expr_to_dotted(node.module)
    level = len(node.relative)
    package_parts = current_old_module.split(".")[:-1]
    if level > len(package_parts) + 1:
        return None
    base_parts = package_parts[: len(package_parts) - level + 1]
    module = expr_to_dotted(node.module)
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


class ImportRewriter(cst.CSTTransformer):
    def __init__(self, plan: dict[str, str], current_old_module: str | None) -> None:
        self.plan = sorted(plan.items(), key=lambda item: -len(item[0]))
        self.current_old_module = current_old_module

    def rewrite(self, dotted: str | None) -> str | None:
        if dotted is None:
            return None
        for old, new in self.plan:
            if dotted == old or dotted.startswith(old + "."):
                return new + dotted[len(old):]
        return None

    def leave_ImportFrom(self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom) -> cst.ImportFrom:
        was_relative = bool(original_node.relative)
        if original_node.relative and self.current_old_module:
            dotted = relative_to_absolute(
                self.current_old_module, original_node)
        else:
            dotted = expr_to_dotted(updated_node.module)
        rewritten = self.rewrite(dotted)
        if not rewritten and not (was_relative and dotted and dotted.startswith(OLD_PREFIX)):
            return updated_node
        rewritten = rewritten or dotted
        return updated_node.with_changes(module=dotted_to_expr(rewritten), relative=())

    def leave_ImportAlias(self, original_node: cst.ImportAlias, updated_node: cst.ImportAlias) -> cst.ImportAlias:
        dotted = expr_to_dotted(updated_node.name)
        rewritten = self.rewrite(dotted)
        if not rewritten:
            return updated_node
        return updated_node.with_changes(name=dotted_to_expr(rewritten))

    def leave_SimpleString(self, original_node: cst.SimpleString, updated_node: cst.SimpleString) -> cst.SimpleString:
        try:
            value = updated_node.evaluated_value
        except Exception:
            return updated_node
        if not isinstance(value, str):
            return updated_node
        rewritten = self.rewrite(value)
        if not rewritten:
            return updated_node
        quote = updated_node.value[:1]
        if updated_node.value.startswith(('"""', "'''")):
            quote = updated_node.value[:3]
        return updated_node.with_changes(value=f"{quote}{rewritten}{quote}")


def load_plan(plan_path: Path | None = None, move_map_path: Path | None = None) -> dict[str, str]:
    path = plan_path or ARTIFACTS / "rename_plan.json"
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
        return {entry["old"]: entry["new"] for entry in entries}
    return build_rename_plan(load_move_map(move_map_path) if move_map_path else load_move_map())


def current_old_module(path: Path, target_to_old: dict[str, str]) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    if rel in target_to_old:
        return target_to_old[rel]
    if rel.startswith("apps/reference/domains/decision_making/"):
        return rel[:-3].replace("/", ".")
    return None


def rewrite_file(path: Path, plan: dict[str, str], target_to_old: dict[str, str]) -> str | None:
    source = path.read_text(encoding="utf-8-sig")
    module = cst.parse_module(source)
    updated = module.visit(ImportRewriter(
        plan, current_old_module(path, target_to_old))).code
    return updated if updated != source else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-diff")
    parser.add_argument("--plan-file")
    parser.add_argument("--move-map")
    args = parser.parse_args()
    plan_path = Path(args.plan_file) if args.plan_file else None
    if plan_path and not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    move_map_path = Path(args.move_map) if args.move_map else None
    if move_map_path and not move_map_path.is_absolute():
        move_map_path = ROOT / move_map_path
    rows = load_move_map(move_map_path) if move_map_path else load_move_map()
    plan = load_plan(plan_path, move_map_path)
    target_to_old = {row.target_path: row.old_module for row in rows}
    diffs: list[str] = []
    changed = 0
    for path in iter_python_files():
        try:
            updated = rewrite_file(path, plan, target_to_old)
        except Exception as exc:
            raise SystemExit(
                f"libcst failed for {path.relative_to(ROOT).as_posix()}: {exc}") from exc
        if updated is None:
            continue
        changed += 1
        rel = path.relative_to(ROOT).as_posix()
        original = path.read_text(encoding="utf-8")
        diffs.extend(difflib.unified_diff(
            original.splitlines(True),
            updated.splitlines(True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        ))
        if not args.dry_run:
            path.write_text(updated, encoding="utf-8")
    if args.write_diff:
        diff_path = ROOT / args.write_diff
        if diff_path.suffix:
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text("".join(diffs), encoding="utf-8")
        else:
            diff_path.mkdir(parents=True, exist_ok=True)
            (diff_path / "rewrite.diff").write_text("".join(diffs), encoding="utf-8")
    print(f"changed_files={changed}")


if __name__ == "__main__":
    main()
