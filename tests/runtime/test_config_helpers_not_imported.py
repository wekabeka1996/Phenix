import ast
from pathlib import Path


def test_config_helpers_removed_and_not_imported() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "apps" / "reference" / "config_helpers.py"
    assert not module_path.exists(), "apps/reference/config_helpers.py must be removed in strict config mode"

    apps_reference = repo_root / "apps" / "reference"
    offenders: list[str] = []
    for py in apps_reference.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.endswith("config_helpers"):
                        offenders.append(str(py))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.endswith("config_helpers"):
                    offenders.append(str(py))

    assert offenders == [], f"config_helpers must not be imported; found in: {offenders}"

