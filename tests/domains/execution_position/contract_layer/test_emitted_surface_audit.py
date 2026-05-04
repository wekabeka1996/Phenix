import importlib
import importlib.util
import json
from pathlib import Path

from apps.reference.domains.execution_position.contract_layer.emitted_surface_audit import (
    DOMAIN_DIR,
    audit_emitted_surfaces,
    load_domain_dict_surfaces,
)
from apps.reference.domains.execution_position.contract_layer.event_names import (
    OWNED_EVENT_NAMES,
)


def test_old_contracts_import_still_resolves_to_legacy_module() -> None:
    spec = importlib.util.find_spec(
        "apps.reference.domains.execution_position.contracts"
    )
    assert spec is not None
    assert spec.submodule_search_locations is None
    assert spec.origin is not None
    assert Path(spec.origin).name == "contracts.py"

    module = importlib.import_module(
        "apps.reference.domains.execution_position.contracts"
    )
    assert module.OrderStatus.__module__.endswith(".contracts")


def test_new_contract_layer_import_resolves_to_package() -> None:
    spec = importlib.util.find_spec(
        "apps.reference.domains.execution_position.contract_layer"
    )
    assert spec is not None
    assert spec.origin is not None
    assert Path(spec.origin).name == "__init__.py"
    assert spec.submodule_search_locations is not None


def test_emitted_surface_audit_matches_current_runtime_contracts() -> None:
    result = audit_emitted_surfaces()

    assert "CMD:OPEN" in result.emitted_surfaces
    assert "EVT:EXECUTION_GUARD_BLOCKED" in result.emitted_surfaces
    assert not result.missing_from_domain_dict
    assert not result.missing_from_registry
    assert all("contract_layer" not in path.parts for path in result.scanned_files)


def test_event_name_inventory_stays_within_domain_dict_surface_set() -> None:
    domain_dict_surfaces = load_domain_dict_surfaces()
    assert set(OWNED_EVENT_NAMES).issubset(domain_dict_surfaces)


def test_common_contract_schemas_load_as_json_schema_objects() -> None:
    common_dir = DOMAIN_DIR / "contract_layer" / "schemas" / "common"
    expected = {
        "base_order_identity_v1.json",
        "peak_giveback_snapshot_v1.json",
    }

    actual = {path.name for path in common_dir.glob("*.json")}
    assert actual == expected

    for filename in sorted(expected):
        payload = json.loads((common_dir / filename).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert "$schema" in payload
        assert "type" in payload
