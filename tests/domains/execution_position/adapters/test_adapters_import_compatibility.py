from __future__ import annotations

import importlib
from pathlib import Path


MODULES = [
    "adapter_init",
    "async_scheduling",
    "config_resolver",
    "watchdog",
]


def test_old_and_new_adapter_import_paths_resolve_to_same_modules() -> None:
    for module_name in MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.adapters.{module_name}"
        )

        assert old_module is new_module
        assert Path(new_module.__file__).name == f"{module_name}.py"
        assert Path(new_module.__file__).parent.name == "adapters"
