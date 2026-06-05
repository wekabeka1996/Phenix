import importlib
from pathlib import Path

import pytest


_ROOT_MODULES = (
    "exposure_guard",
    "exposure_manager",
    "soft_clip",
    "qty_normalizer",
    "leverage_config",
    "leverage_service",
)


@pytest.mark.parametrize("module_name", _ROOT_MODULES)
def test_old_flat_path_stub_file_exists(module_name: str) -> None:
    stub_path = Path("apps/reference/domains/execution_position") / f"{module_name}.py"
    assert stub_path.exists()


@pytest.mark.parametrize("module_name", _ROOT_MODULES)
def test_old_and_new_import_paths_resolve_to_same_module(module_name: str) -> None:
    old_module = importlib.import_module(
        f"apps.reference.domains.execution_position.{module_name}"
    )
    new_module = importlib.import_module(
        f"apps.reference.domains.execution_position.guards.{module_name}"
    )

    assert old_module is new_module
    assert "guards" in Path(new_module.__file__).parts


def test_old_and_new_bootstrapping_import_paths_resolve_to_same_module() -> None:
    old_module = importlib.import_module(
        "apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper"
    )
    new_module = importlib.import_module(
        "apps.reference.domains.execution_position.guards.bootstrapping.leverage_bootstrapper"
    )

    assert old_module is new_module
    assert "guards" in Path(new_module.__file__).parts


def test_old_bootstrapping_stub_file_exists() -> None:
    stub_path = Path(
        "apps/reference/domains/execution_position/bootstrapping/leverage_bootstrapper.py"
    )
    assert stub_path.exists()
