import importlib


ROOT_MODULES = (
    "order_index",
    "order_ledger",
    "ledger_store_adapter",
    "restore_artifact",
    "authoritative_restore_apply",
    "startup_reconstruction",
    "startup_truth_orchestrator",
    "truth_hardening",
)

INFRA_MODULES = (
    "order_ledger",
    "ledger_store_adapter",
)


def test_state_package_imports_resolve():
    package = importlib.import_module(
        "apps.reference.domains.execution_position.state"
    )
    assert package.__file__.endswith("state\\__init__.py")


def test_root_and_state_imports_resolve_to_same_module_objects():
    for module_name in ROOT_MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.state.{module_name}"
        )
        assert old_module is new_module


def test_infra_compatibility_imports_still_resolve():
    for module_name in INFRA_MODULES:
        old_module = importlib.import_module(
            f"apps.reference.domains.execution_position.infra.{module_name}"
        )
        new_module = importlib.import_module(
            f"apps.reference.domains.execution_position.state.{module_name}"
        )
        assert old_module is new_module
