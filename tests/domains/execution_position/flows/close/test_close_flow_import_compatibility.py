from __future__ import annotations

import importlib
from pathlib import Path


MODULES = [
    "fsm_close",
    "close_executor",
    "close_submission_adapter",
    "close_producer_bridge",
    "reconcile_close_cancel_bridge",
    "tracked_close_teardown_cancel_bridge",
]


def test_old_and_new_close_flow_import_paths_resolve_to_same_modules() -> None:
    for module_name in MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.flows.close.{module_name}"
        )

        assert old_module is new_module
        assert Path(new_module.__file__).name == f"{module_name}.py"
        assert Path(new_module.__file__).parent.name == "close"
        assert Path(new_module.__file__).parent.parent.name == "flows"
