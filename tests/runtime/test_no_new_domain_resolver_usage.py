import ast
from pathlib import Path


def test_domain_config_resolver_usage_is_frozen() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    apps_reference = repo_root / "apps" / "reference"

    allowed = {
        "apps/reference/__init__.py",
        "apps/reference/domain_config.py",
        "apps/reference/main.py",
        "apps/reference/domains/account_observer/account_observer.py",
        "apps/reference/domains/decision_making/aurora_config_loader.py",  # Phase 14A refactor
        # FIX-FROZEN-LIST: added during T2B refactor
        "apps/reference/domains/decision_making/aurora_handler.py",
        "apps/reference/domains/decision_making/decision_making.py",
        "apps/reference/domains/decision_making/core/config_spec.py",
        "apps/reference/domains/decision_making/core/facade.py",
        "apps/reference/domains/execution_position/exposure_guard.py",
        # SSOT: fail-closed brackets loading
        "apps/reference/domains/execution_position/fsm.py",
        "apps/reference/domains/feature_engineering/feature_engineering.py",
        "apps/reference/domains/feature_engineering/types.py",
        "apps/reference/domains/strategies/runtimes/aurora/config_loader.py",
        "apps/reference/domains/position_tracking/position_tracking.py",
        "apps/reference/domains/risk_management/risk_management.py",
    }

    offenders: list[str] = []
    for py in apps_reference.rglob("*.py"):
        rel = py.relative_to(repo_root).as_posix()
        src = py.read_text(encoding="utf-8-sig")
        tree = ast.parse(src)

        uses_resolver = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "DomainConfigResolver":
                uses_resolver = True
                break

        if uses_resolver and rel not in allowed:
            offenders.append(rel)

    assert offenders == [
    ], f"New DomainConfigResolver usage is forbidden; found in: {offenders}"
