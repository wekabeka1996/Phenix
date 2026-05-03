from __future__ import annotations

import importlib
from pathlib import Path


MODULES = [
    "fsm_manage",
    "bracket_manager",
    "bracket_math",
    "bracket_health",
    "bracket_ownership",
    "pending_brackets_wal",
    "manage_max_hold_close_bridge",
]


def test_old_and_new_manage_flow_import_paths_resolve_to_same_modules() -> None:
    for module_name in MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.flows.manage.{module_name}"
        )

        assert old_module is new_module
        assert Path(new_module.__file__).name == f"{module_name}.py"
        assert Path(new_module.__file__).parent.name == "manage"
        assert Path(new_module.__file__).parent.parent.name == "flows"
