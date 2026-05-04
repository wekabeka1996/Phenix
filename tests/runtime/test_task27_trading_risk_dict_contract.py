import ast
from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_task27_trading_risk_is_dict_in_loaded_config() -> None:
    cfg = ConfigLoader().load_config()
    assert isinstance(cfg.trading.risk, dict)


def test_task27_no_trading_risk_object_attribute_access_in_runtime() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    apps_reference = repo_root / "apps" / "reference"

    offenders: list[str] = []

    for py in apps_reference.rglob("*.py"):
        if py.name.endswith(".bak"):
            continue
        rel = py.relative_to(repo_root).as_posix()
        src = py.read_text(encoding="utf-8", errors="replace")

        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Match attribute chain: <expr>.trading.risk.<something>
            if not isinstance(node, ast.Attribute):
                continue

            parent = node.value
            if not (isinstance(parent, ast.Attribute) and parent.attr == "risk"):
                continue

            grand = parent.value
            if not (isinstance(grand, ast.Attribute) and grand.attr == "trading"):
                continue

            offenders.append(f"{rel}:{node.lineno}")
            break

    assert offenders == [], "Forbidden `.trading.risk.<attr>` usage:\n" + "\n".join(offenders)

