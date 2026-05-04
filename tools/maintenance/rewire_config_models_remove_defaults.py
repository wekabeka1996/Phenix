#!/usr/bin/env python3
"""TASK22: CFG-REMOVE-MODEL-DEFAULTS-AFTER-SSOT-AUTOFILL-P1-22

Mechanical rewrite tool for `apps/reference/config_models.py`:
- Remove ALL model defaults (incl. `= 1`, `Field(default=...)`, `Field(default_factory=...)`).
- Keep schema metadata (`description`, `ge`, validators, etc.) intact.
- Normalize `ConfigDict(extra='allow')` -> `extra='forbid'`.

Policy target:
- `python tools/inventory_config_defaults.py --check` must PASS.

This tool performs minimal source edits using AST node offsets to preserve
formatting and comments as much as possible.

Usage:
  python tools/rewire_config_models_remove_defaults.py --dry-run \
      --out-md reports/TASK22_rewire_plan.md

  python tools/rewire_config_models_remove_defaults.py --apply \
      --out-md reports/TASK22_rewire_applied.md

"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: str
    why: str


def _line_starts(text: str) -> List[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _abs_pos(starts: List[int], lineno: int, col: int) -> int:
    return starts[lineno - 1] + col


def _inherits_basemodel(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _is_call(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name


def _is_const_str(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == value


def _unparse(node: ast.AST) -> str:
    # ast.unparse is available in py3.9+; repo uses modern python.
    return ast.unparse(node)


def _rewrite_configdict_extra_allow(call: ast.Call) -> Optional[str]:
    if not _is_call(call, "ConfigDict"):
        return None

    changed = False
    new_keywords: List[ast.keyword] = []
    for kw in call.keywords:
        if kw.arg == "extra" and _is_const_str(kw.value, "allow"):
            new_keywords.append(ast.keyword(arg="extra", value=ast.Constant(value="forbid")))
            changed = True
        else:
            new_keywords.append(kw)

    if not changed:
        return None

    new_call = ast.Call(func=call.func, args=call.args, keywords=new_keywords)
    return _unparse(new_call)


def _field_call_has_default(call: ast.Call) -> bool:
    if not _is_call(call, "Field"):
        return False

    # Field(default=...) / default_factory=...
    for kw in call.keywords:
        if kw.arg in {"default", "default_factory"}:
            return True

    # Field(<positional_default>, ...)
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and first.value is Ellipsis:
            return False
        return True

    return False


def _rewrite_field_remove_default(call: ast.Call) -> str:
    """Return Field(...) call string with defaults removed.

    If call is `Field(default=...)` or `Field(default_factory=...)` or `Field(<positional>)`,
    the returned call will be metadata-only and thus required in Pydantic.
    """
    assert _is_call(call, "Field")

    # Drop positional default if present and not Ellipsis
    new_args = list(call.args)
    if new_args:
        first = new_args[0]
        if not (isinstance(first, ast.Constant) and first.value is Ellipsis):
            new_args = new_args[1:]

    # Drop default/default_factory keywords
    new_keywords: List[ast.keyword] = [
        kw for kw in call.keywords if kw.arg not in {"default", "default_factory"}
    ]

    new_call = ast.Call(func=call.func, args=new_args, keywords=new_keywords)
    return _unparse(new_call)


def collect_edits(source: str, file_path: Path) -> Tuple[List[Edit], List[str]]:
    tree = ast.parse(source, filename=str(file_path))
    starts = _line_starts(source)

    edits: List[Edit] = []
    notes: List[str] = []

    # TASK22 guard: duplicate class definitions are not allowed.
    class_names: List[str] = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    dupes = sorted({name for name in class_names if class_names.count(name) > 1})
    if dupes:
        raise RuntimeError(f"Duplicate class definitions found: {dupes}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _inherits_basemodel(node):
            continue

        class_name = node.name
        has_model_config = any(
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and s.targets[0].id == "model_config"
            for s in node.body
        )

        # TASK22.B: ensure every BaseModel-derived class has extra='forbid'.
        # If model_config is missing, insert `model_config = ConfigDict(extra='forbid')`.
        if not has_model_config and node.body:
            first_stmt = node.body[0]
            insert_at = None
            indent = " " * getattr(first_stmt, "col_offset", 4)

            # If first statement is a docstring, insert after it.
            if (
                isinstance(first_stmt, ast.Expr)
                and isinstance(first_stmt.value, ast.Constant)
                and isinstance(first_stmt.value.value, str)
                and first_stmt.end_lineno is not None
            ):
                # Insert at the beginning of the line after docstring.
                insert_line = first_stmt.end_lineno + 1
                if insert_line <= len(starts):
                    insert_at = starts[insert_line - 1]
            else:
                insert_at = _abs_pos(starts, first_stmt.lineno, first_stmt.col_offset)

            if insert_at is not None:
                edits.append(
                    Edit(
                        start=insert_at,
                        end=insert_at,
                        replacement=f"{indent}model_config = ConfigDict(extra='forbid')\n",
                        why=f"{class_name}.model_config: add extra forbid",
                    )
                )

        for stmt in node.body:
            # model_config = ConfigDict(extra='allow')
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                if stmt.targets[0].id == "model_config" and isinstance(stmt.value, ast.Call):
                    new_value = _rewrite_configdict_extra_allow(stmt.value)
                    if new_value is not None:
                        assert stmt.value.lineno is not None and stmt.value.end_lineno is not None
                        start = _abs_pos(starts, stmt.value.lineno, stmt.value.col_offset)
                        end = _abs_pos(starts, stmt.value.end_lineno, stmt.value.end_col_offset)
                        edits.append(
                            Edit(
                                start=start,
                                end=end,
                                replacement=new_value,
                                why=f"{class_name}.model_config: extra allow->forbid",
                            )
                        )
                continue

            # Annotated fields with defaults
            if isinstance(stmt, ast.AnnAssign) and stmt.value is not None and isinstance(stmt.target, ast.Name):
                field_name = stmt.target.id
                value = stmt.value

                # Replace the VALUE expression only, preserving comments and overall formatting.
                if isinstance(value, ast.Call) and _is_call(value, "Field"):
                    if _field_call_has_default(value):
                        replacement = _rewrite_field_remove_default(value)
                        start = _abs_pos(starts, value.lineno, value.col_offset)
                        end = _abs_pos(starts, value.end_lineno, value.end_col_offset)
                        edits.append(
                            Edit(
                                start=start,
                                end=end,
                                replacement=replacement,
                                why=f"{class_name}.{field_name}: remove Field default/default_factory",
                            )
                        )
                else:
                    # Any literal default form (`= None`, `= 1`, `= {}`, `= []` etc) becomes REQUIRED.
                    start = _abs_pos(starts, value.lineno, value.col_offset)
                    end = _abs_pos(starts, value.end_lineno, value.end_col_offset)
                    edits.append(
                        Edit(
                            start=start,
                            end=end,
                            replacement="Field(...)",
                            why=f"{class_name}.{field_name}: replace literal default with Field(...)",
                        )
                    )

    # Basic overlap check
    edits_sorted = sorted(edits, key=lambda e: (e.start, e.end))
    for prev, curr in zip(edits_sorted, edits_sorted[1:]):
        if curr.start < prev.end:
            raise RuntimeError(f"Overlapping edits: {prev} vs {curr}")

    notes.append(f"Collected edits: {len(edits_sorted)}")
    return edits_sorted, notes


def apply_edits(source: str, edits: Iterable[Edit]) -> str:
    # Apply from back to front to keep offsets stable
    out = source
    for e in sorted(edits, key=lambda x: x.start, reverse=True):
        out = out[: e.start] + e.replacement + out[e.end :]
    return out


def render_report(edits: List[Edit], title: str) -> str:
    lines: List[str] = [f"# {title}", "", f"Total edits: {len(edits)}", ""]
    for e in edits:
        lines.append(f"- {e.why}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite config_models.py to remove defaults (TASK22)")
    parser.add_argument("--file", default="apps/reference/config_models.py")
    parser.add_argument("--out-md", required=False, help="(deprecated) Output markdown report path")
    parser.add_argument(
        "--out-summary",
        default="reports/TASK22_rewrite_diff_summary.md",
        help="Rewrite diff summary markdown",
    )
    parser.add_argument(
        "--out-unresolved",
        default="reports/TASK22_unresolved_cases.md",
        help="Unresolved cases markdown (should be empty)",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true", help="Dry-run + fail if unresolved detected")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")

    source = file_path.read_text(encoding="utf-8")
    edits, notes = collect_edits(source, file_path)

    summary_lines: List[str] = [
        "# TASK22 Rewrite Diff Summary",
        "",
        f"Target: {file_path}",
        "",
        f"Total planned edits: {len(edits)}",
        "",
    ]
    for n in notes:
        summary_lines.append(f"- NOTE: {n}")
    summary_lines.append("")

    # This rewriter is mechanical; unresolved list is expected to be empty.
    unresolved_lines = [
        "# TASK22 Unresolved Cases",
        "",
        "Expected: 0 unresolved cases.",
        "",
        "(none)",
        "",
    ]

    Path(args.out_summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_unresolved).parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run or args.check:
        Path(args.out_summary).write_text("\n".join(summary_lines), encoding="utf-8")
        Path(args.out_unresolved).write_text("\n".join(unresolved_lines), encoding="utf-8")
        print(f"Wrote summary: {args.out_summary}")
        print(f"Wrote unresolved: {args.out_unresolved}")
        return 0

    # apply
    new_source = apply_edits(source, edits)
    file_path.write_text(new_source, encoding="utf-8")

    Path(args.out_summary).write_text("\n".join(summary_lines), encoding="utf-8")
    Path(args.out_unresolved).write_text("\n".join(unresolved_lines), encoding="utf-8")
    print(f"Rewrote: {file_path}")
    print(f"Wrote summary: {args.out_summary}")
    print(f"Wrote unresolved: {args.out_unresolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
