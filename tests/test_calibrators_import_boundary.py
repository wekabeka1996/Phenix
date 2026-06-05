from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "apps" / "reference"


def _calibrator_import_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(RUNTIME_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(
            encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "calibrators" or alias.name.startswith("calibrators."):
                        violations.append(
                            f"{path.as_posix()}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "calibrators" or module.startswith("calibrators."):
                    violations.append(
                        f"{path.as_posix()}: from {module} import ...")
    return violations


def test_apps_reference_does_not_import_calibrators() -> None:
    violations = _calibrator_import_violations()
    assert not violations, "apps/reference must not import calibrators:\n" + \
        "\n".join(violations)
