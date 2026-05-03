"""Phase 9A root-anchor freeze guardrails for execution_position.

These tests intentionally freeze the accepted root-level public API/facade
surface after Phase 8 physical migration:
- ``fsm.py`` remains root-level because it is a high-risk orchestration anchor.
- ``contracts.py`` remains root-level because ``contract_layer`` is additive and
  must not shadow the legacy contracts module path.
- ``reasons.py`` remains root-level as the canonical reason-constant surface.
- ``utils.py`` remains root-level because creating ``execution_position/utils/``
  would shadow the existing module import path.

The root is now an intentional public API/facade surface, not unfinished
migration debt.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


EP_ROOT = Path("apps/reference/domains/execution_position")
ROOT_ANCHORS = {
    "fsm": EP_ROOT / "fsm.py",
    "contracts": EP_ROOT / "contracts.py",
    "reasons": EP_ROOT / "reasons.py",
    "utils": EP_ROOT / "utils.py",
}
FORBIDDEN_PACKAGES = (
    EP_ROOT / "contracts",
    EP_ROOT / "utils",
)


def test_root_anchor_modules_resolve_to_root_files_and_not_packages() -> None:
    for module_name, expected_path in ROOT_ANCHORS.items():
        spec = importlib.util.find_spec(
            f"apps.reference.domains.execution_position.{module_name}"
        )

        assert spec is not None
        assert spec.origin is not None
        assert Path(spec.origin).resolve() == expected_path.resolve()
        assert spec.submodule_search_locations is None


def test_root_anchor_files_physically_exist_at_root() -> None:
    for path in ROOT_ANCHORS.values():
        assert path.exists()
        assert path.is_file()


def test_forbidden_shadowing_package_paths_do_not_exist() -> None:
    for path in FORBIDDEN_PACKAGES:
        assert not path.exists()


def test_contract_layer_remains_separate_package_from_contracts_module() -> None:
    contracts_spec = importlib.util.find_spec(
        "apps.reference.domains.execution_position.contracts"
    )
    contract_layer_spec = importlib.util.find_spec(
        "apps.reference.domains.execution_position.contract_layer"
    )

    assert contracts_spec is not None
    assert contracts_spec.origin is not None
    assert Path(contracts_spec.origin).name == "contracts.py"
    assert contracts_spec.submodule_search_locations is None

    assert contract_layer_spec is not None
    assert contract_layer_spec.origin is not None
    assert Path(contract_layer_spec.origin).name == "__init__.py"
    assert contract_layer_spec.submodule_search_locations is not None

    contract_layer_dir = EP_ROOT / "contract_layer"
    assert Path(contract_layer_spec.origin).resolve().parent == contract_layer_dir.resolve()
    assert contract_layer_dir.is_dir()
