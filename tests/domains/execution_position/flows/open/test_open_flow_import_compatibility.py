from __future__ import annotations

import importlib
from pathlib import Path


MODULES = [
    "fsm_open",
    "trade_intent_open_intake",
    "intent_router",
    "entry_manager",
    "open_executor",
    "open_submission_adapter",
    "open_dispatch_adapter",
]


def test_old_and_new_open_flow_import_paths_resolve_to_same_modules() -> None:
    for module_name in MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.flows.open.{module_name}"
        )

        assert old_module is new_module
        assert Path(new_module.__file__).name == f"{module_name}.py"
        assert Path(new_module.__file__).parent.name == "open"
        assert Path(new_module.__file__).parent.parent.name == "flows"
