from __future__ import annotations

import importlib
from pathlib import Path


MODULES = [
    "terminal_order_contracts",
    "trade_executed_contracts",
    "trade_intent_reject_contracts",
]


def test_old_and_new_contract_helper_import_paths_resolve_to_same_modules() -> None:
    for module_name in MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.contract_layer.{module_name}"
        )

        assert old_module is new_module
        assert Path(new_module.__file__).name == f"{module_name}.py"
        assert Path(new_module.__file__).parent.name == "contract_layer"
