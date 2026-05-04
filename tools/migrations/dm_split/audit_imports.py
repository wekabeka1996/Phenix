"""Audit static import-graph invariants for the Package 3 DM split.

Input: a Python package root such as apps/reference/domains/decision_making.
Output: a markdown report describing the Step 2 dependency-graph sanity checks.
Side effects: writes the report unless --dry-run is passed.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from dm_split_lib import ARTIFACTS, OLD_PREFIX, ROOT, main_guard

CONFIG_MODELS_MODULE = "apps.reference.config_models"


def module_name_for_path(root: Path, path: Path, root_module: str) -> str:
    rel_parts = path.relative_to(root).with_suffix("").parts
    if rel_parts and rel_parts[-1] == "__init__":
        rel_parts = rel_parts[:-1]
    suffix = ".".join(rel_parts)
    return root_module if not suffix else f"{root_module}.{suffix}"


def resolve_from_import(current_module: str, module: str | None, level: int) -> str | None:
    if level == 0:
        return module
    package_parts = current_module.split(".")[:-1]
    if level > len(package_parts) + 1:
        return None
    base_parts = package_parts[: len(package_parts) - level + 1]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def parse_imports(path: Path, root: Path, root_module: str) -> set[str]:
    current_module = module_name_for_path(root, path, root_module)
    tree = ast.parse(path.read_text(encoding="utf-8-sig"),
                     filename=path.as_posix())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = resolve_from_import(
                current_module, node.module, node.level)
            if resolved:
                imports.add(resolved)
    return imports


def is_stdlib_module(module_name: str) -> bool:
    top_level = module_name.split(".")[0]
    return top_level == "__future__" or top_level in sys.stdlib_module_names


def is_allowed_shared_infra_import(module_name: str) -> bool:
    if is_stdlib_module(module_name):
        return True
    if module_name == CONFIG_MODELS_MODULE or module_name.startswith(f"{CONFIG_MODELS_MODULE}."):
        return True
    return module_name.startswith(("apps.reference.core.", "vfoundation."))


def is_allowed_shield_import(module_name: str, root_module: str) -> bool:
    if is_allowed_shared_infra_import(module_name):
        return True
    allowed_prefixes = (
        f"{root_module}.primitives.",
        "apps.reference.shared.decision_primitives.",
    )
    return module_name.startswith(allowed_prefixes)


def is_allowed_shared_tree_import(module_name: str, root_module: str) -> bool:
    if is_allowed_shared_infra_import(module_name):
        return True
    return module_name.startswith(f"{root_module}.")


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _check_shared_tree(root: Path, root_module: str) -> dict[str, object]:
    violations: list[str] = []
    shared_tree_violations: list[str] = []
    shared_root_files = sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    ) if root.exists() else []
    shield_files = sorted((root / "shields").rglob("*.py")
                          ) if (root / "shields").exists() else []
    shared_non_shield_files = [
        path for path in shared_root_files if "shields" not in path.relative_to(root).parts
    ]
    if not shared_root_files:
        violations.append(
            f"BLOCKED: missing shared decision primitives tree under {_display_path(root)}")
    else:
        for path in shared_root_files:
            imports = sorted(parse_imports(path, root, root_module))
            for module_name in imports:
                if is_allowed_shared_tree_import(module_name, root_module):
                    continue
                shared_tree_violations.append(
                    f"BLOCKED: {_display_path(path)} imports {module_name}"
                )
        violations.extend(shared_tree_violations)

    return {
        "root": _display_path(root),
        "shared_files": [_display_path(path) for path in shared_non_shield_files],
        "shield_files": [_display_path(path) for path in shield_files],
        "violations": violations,
        "checks": {
            "shared_shields_allowed_prefixes": not any(
                violation.startswith(f"BLOCKED: {_display_path(path)} imports")
                for path in shield_files
                for violation in shared_tree_violations
            ),
            "shared_tree_allowed_prefixes": not shared_tree_violations,
        },
    }


def inspect_import_graph(root: Path, root_module: str = OLD_PREFIX) -> dict[str, object]:
    if (root / "scoring_kernel.py").exists():
        return _check_shared_tree(root, root_module)

    violations: list[str] = []

    scoring_kernel = root / "primitives" / "scoring_kernel.py"
    scoring_imports: list[str] = []
    missing_scoring_imports: list[str] = []
    expected_scoring_imports = [
        f"{root_module}.primitives.aurora_math",
        f"{root_module}.primitives.aurora_policy",
    ]
    if not scoring_kernel.exists():
        violations.append(f"BLOCKED: missing {_display_path(scoring_kernel)}")
    else:
        scoring_imports = sorted(parse_imports(
            scoring_kernel, root, root_module))
        missing_scoring_imports = [
            module_name for module_name in expected_scoring_imports if module_name not in scoring_imports
        ]
        for module_name in missing_scoring_imports:
            violations.append(
                f"BLOCKED: {_display_path(scoring_kernel)} missing import {module_name}"
            )

    shields_dir = root / "primitives" / "shields"
    shield_violations: list[str] = []
    shield_files = sorted(shields_dir.rglob(
        "*.py")) if shields_dir.exists() else []
    if not shield_files:
        violations.append(
            f"BLOCKED: missing shields package under {_display_path(shields_dir)}")
    else:
        for path in shield_files:
            imports = sorted(parse_imports(path, root, root_module))
            for module_name in imports:
                if is_allowed_shield_import(module_name, root_module):
                    continue
                shield_violations.append(
                    f"BLOCKED: {_display_path(path)} imports {module_name}"
                )
        violations.extend(shield_violations)

    handler_files = sorted(root.glob("strategies/*/handler.py"))
    handler_missing_primitives: list[str] = []
    handler_forbidden_imports: list[str] = []
    if not handler_files:
        violations.append(
            f"BLOCKED: missing strategy handlers under {_display_path(root / 'strategies')}")
    else:
        for path in handler_files:
            imports = sorted(parse_imports(path, root, root_module))
            if not any(module_name.startswith(f"{root_module}.primitives") for module_name in imports):
                handler_missing_primitives.append(
                    f"BLOCKED: {_display_path(path)} imports no {root_module}.primitives.* modules"
                )
            for module_name in imports:
                if module_name == f"{root_module}.core.facade":
                    handler_forbidden_imports.append(
                        f"BLOCKED: {_display_path(path)} imports {module_name}"
                    )
                elif module_name == f"{root_module}.gateway" or module_name.startswith(f"{root_module}.gateway."):
                    handler_forbidden_imports.append(
                        f"BLOCKED: {_display_path(path)} imports {module_name}"
                    )
        violations.extend(handler_missing_primitives)
        violations.extend(handler_forbidden_imports)

    return {
        "root": _display_path(root),
        "scoring_imports": scoring_imports,
        "shield_files": [_display_path(path) for path in shield_files],
        "handler_files": [_display_path(path) for path in handler_files],
        "violations": violations,
        "checks": {
            "scoring_kernel_pair": not missing_scoring_imports,
            "shields_primitives_only": not shield_violations,
            "handlers_import_primitives": not handler_missing_primitives,
            "handlers_no_facade_or_gateway": not handler_forbidden_imports,
        },
    }


def render_report(result: dict[str, object]) -> str:
    checks = result["checks"]
    lines = [
        "# Package 3 Pre-Audit",
        "",
        f"- root: {result['root']}",
        "",
        "## Checks",
    ]
    if "scoring_kernel_pair" in checks:
        lines.extend([
            f"- [{'x' if checks['scoring_kernel_pair'] else ' '}] scoring_kernel imports aurora_math and aurora_policy together.",
            f"- [{'x' if checks['shields_primitives_only'] else ' '}] shields/* imports only allowed shared-infra prefixes.",
            f"- [{'x' if checks['handlers_import_primitives'] else ' '}] strategy handlers import primitives.*.",
            f"- [{'x' if checks['handlers_no_facade_or_gateway'] else ' '}] no strategy handler imports core.facade or gateway.* directly.",
            "",
            "## Details",
            f"- scoring_kernel imports: {', '.join(result['scoring_imports']) or 'none'}",
            f"- shield files checked: {', '.join(result['shield_files']) or 'none'}",
            f"- strategy handlers checked: {', '.join(result['handler_files']) or 'none'}",
        ])
    else:
        lines.extend([
            f"- [{'x' if checks['shared_shields_allowed_prefixes'] else ' '}] shared shields import only shared/core/config_models/vfoundation/stdlib.",
            f"- [{'x' if checks['shared_tree_allowed_prefixes'] else ' '}] shared decision primitives import only shared/core/config_models/vfoundation/stdlib.",
            "",
            "## Details",
            f"- shared files checked: {', '.join(result['shared_files']) or 'none'}",
            f"- shared shield files checked: {', '.join(result['shield_files']) or 'none'}",
        ])
    violations = result["violations"]
    if violations:
        lines.extend(["", "## BLOCKED"])
        lines.extend(f"- {entry}" for entry in violations)
    else:
        lines.extend(["", "## Result", "- Pre-audit passed."])
    return "\n".join(lines) + "\n"


def main() -> None:
    main_guard()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", default="apps/reference/domains/decision_making")
    parser.add_argument("--root-module", default=OLD_PREFIX)
    parser.add_argument(
        "--out", default=str(ARTIFACTS / "package3_pre_audit.md"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root_path = Path(args.root)
    if not root_path.is_absolute():
        root_path = ROOT / root_path
    result = inspect_import_graph(root_path, args.root_module)
    report = render_report(result)

    if args.dry_run:
        print(report)
    else:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")

    if result["violations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
