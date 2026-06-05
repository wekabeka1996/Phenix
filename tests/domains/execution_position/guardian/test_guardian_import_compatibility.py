import importlib
from pathlib import Path

import pytest


_MODULES = (
    "order_guardian",
    "idempotent_cancel",
    "cancel_submission_adapter",
    "cancel_bridge_utils",
    "guardian_reconcile_cancel_bridge",
    "guardian_background_orphan_cancel_bridge",
    "guardian_old_bracket_cleanup_bridge",
    "guardian_pre_close_cleanup_bridge",
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
        f"apps.reference.domains.execution_position.guardian.{module_name}"
    )

    assert old_module is new_module
    assert "guardian" in Path(new_module.__file__).parts
