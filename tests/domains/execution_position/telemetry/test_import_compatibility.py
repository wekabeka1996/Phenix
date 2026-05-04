import importlib
from pathlib import Path

import pytest


_MODULES = (
    "aurora_log_adapter",
    "metrics_collector",
    "metrics_aggregator",
    "health_metrics",
    "drift_monitor",
    "intent_boundary_audit",
)


@pytest.mark.parametrize("module_name", _MODULES)
def test_old_flat_path_stub_file_exists(module_name: str) -> None:
    stub_path = Path("apps/reference/domains/execution_position") / f"{module_name}.py"
    assert stub_path.exists()


@pytest.mark.parametrize("module_name", _MODULES)
def test_old_and_new_import_paths_resolve_to_same_module(module_name: str) -> None:
    old_module = importlib.import_module(
        f"apps.reference.domains.execution_position.{module_name}"
    )
    new_module = importlib.import_module(
        f"apps.reference.domains.execution_position.telemetry.{module_name}"
    )

    assert old_module is new_module
    assert "telemetry" in Path(new_module.__file__).parts
