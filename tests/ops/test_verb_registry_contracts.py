from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError, validate

from vfoundation.core.fsm_core import FSMCore, InvalidMessagePayloadError
from vfoundation.core.schema_registry import init_global_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _registry_path() -> Path:
    return _repo_root() / "apps" / "reference" / "dictionaries" / "verb_registry_v1.yaml"


def _load_registry() -> dict:
    path = _registry_path()
    if not path.exists():
        raise AssertionError(f"Missing registry file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_cmd_process_strategy_registered() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (
            e
            for e in registry
            if isinstance(e, dict) and e.get("op") == "CMD" and e.get("verb") == "PROCESS_STRATEGY"
        ),
        None,
    )
    assert entry is not None, "Expected CMD:PROCESS_STRATEGY to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_cmd_open_registered_with_schema() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (e for e in registry if isinstance(e, dict) and e.get(
            "op") == "CMD" and e.get("verb") == "OPEN"),
        None,
    )
    assert entry is not None, "Expected CMD:OPEN to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/execution_position/schemas/cmd_open_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_dec_open_registered_with_schema() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (e for e in registry if isinstance(e, dict) and e.get(
            "op") == "DEC" and e.get("verb") == "OPEN"),
        None,
    )
    assert entry is not None, "Expected DEC:OPEN to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/execution_position/schemas/dec_open_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_order_placed_registered_with_schema() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (
            e
            for e in registry
            if isinstance(e, dict) and e.get("op") == "EVT" and e.get("verb") == "ORDER_PLACED"
        ),
        None,
    )
    assert entry is not None, "Expected EVT:ORDER_PLACED to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/execution_position/schemas/order_placed_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_trade_intent_proposed_registered_with_schema() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (
            e
            for e in registry
            if isinstance(e, dict) and e.get("op") == "EVT" and e.get("verb") == "TRADE_INTENT_PROPOSED"
        ),
        None,
    )
    assert entry is not None, "Expected EVT:TRADE_INTENT_PROPOSED to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/decision_making/schemas/trade_intent_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_decision_blocked_registered_with_schema() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (
            e
            for e in registry
            if isinstance(e, dict) and e.get("op") == "EVT" and e.get("verb") == "DECISION_BLOCKED"
        ),
        None,
    )
    assert entry is not None, "Expected EVT:DECISION_BLOCKED to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/decision_making/schemas/decision_blocked_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_tick_features_calculated_registered_with_schema() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (
            e
            for e in registry
            if isinstance(e, dict) and e.get("op") == "EVT" and e.get("verb") == "TICK_FEATURES_CALCULATED"
        ),
        None,
    )
    assert entry is not None, "Expected EVT:TICK_FEATURES_CALCULATED to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/feature_engineering/schemas/tick_features_calculated_v1.json"
    assert (_repo_root(
    ) / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_unknown_cmd_is_rejected() -> None:
    data = _load_registry()
    policies = data.get("policies")
    assert isinstance(policies, dict)
    wildcard = policies.get("wildcard")
    assert isinstance(wildcard, dict)
    assert wildcard.get(
        "CMD") is False, "Fail-closed policy regression: wildcard CMD must remain false"


def test_cmd_process_strategy_schema_has_minimal_contract() -> None:
    schema_path = (
        _repo_root()
        / "apps"
        / "reference"
        / "domains"
        / "feature_engineering"
        / "schemas"
        / "cmd_process_strategy_v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    required = schema.get("required")
    assert isinstance(required, list)
    for key in ("symbol", "tf_sec", "bar_close_ts", "bar", "features", "warmup", "regime"):
        assert key in required


def test_cmd_open_schema_fail_closed_limit_requires_tif_and_valid_for_ms() -> None:
    schema_path = (
        _repo_root()
        / "apps"
        / "reference"
        / "domains"
        / "execution_position"
        / "schemas"
        / "cmd_open_v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    valid_limit = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.01",
        "order_type": "LIMIT",
        "price": "42000.0",
        "tif": "GTX",
        "valid_for_ms": 60_000,
    }
    validate(valid_limit, schema)

    invalid_missing_tif = {**valid_limit, "tif": None}
    with pytest.raises(ValidationError):
        validate(invalid_missing_tif, schema)

    invalid_missing_valid_for = {
        k: v for k, v in valid_limit.items() if k != "valid_for_ms"}
    with pytest.raises(ValidationError):
        validate(invalid_missing_valid_for, schema)


def test_order_placed_schema_requires_execution_identity_and_correlation_fields() -> None:
    schema_path = (
        _repo_root()
        / "apps"
        / "reference"
        / "domains"
        / "execution_position"
        / "schemas"
        / "order_placed_v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    valid_payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.01",
        "order_type": "MARKET",
        "client_order_id": "ENTRY-BTC-1",
        "exchange_order_id": "900001",
        "order_id": "900001",
        "rid": "RID-ORDER-PLACED-1",
        "ts_ms": 1_700_000_000_789,
        "corr_id": "corr-order-placed-1",
        "regime": "TREND_UP",
        "regime_confidence": 0.87,
        "regime_provenance": {
            "source_kind": "detector_cache",
            "detector_event": {
                "event_name": "EVT:REGIME_DETECTED",
                "rid": "rid-detector-btc-proof",
                "ts_ms": 1_700_000_000_000,
                "last_update_ts_ms": 1_700_000_000_123,
                "structural_regime_ref": "structural:BTCUSDT:1700000000000",
                "changed": False,
                "regime": "TREND_UP",
                "confidence": "0.87",
                "raw_regime": "TREND_UP",
                "raw_confidence": "0.87"
            },
            "cache_snapshot": {
                "cache_write_ts_ms": 1_700_000_000_456,
                "regime": "TREND_UP",
                "confidence": 0.87
            }
        }
    }

    validate(valid_payload, schema)

    invalid_missing_corr_id = {k: v for k,
                               v in valid_payload.items() if k != "corr_id"}
    with pytest.raises(ValidationError):
        validate(invalid_missing_corr_id, schema)


def test_fsm_core_enforces_order_placed_schema_from_registry() -> None:
    init_global_registry(project_root=".")
    bus = FSMCore()

    valid_payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.01",
        "order_type": "MARKET",
        "client_order_id": "ENTRY-BTC-1",
        "exchange_order_id": "900001",
        "order_id": "900001",
        "rid": "RID-ORDER-PLACED-1",
        "ts_ms": 1_700_000_000_789,
        "corr_id": "corr-order-placed-1",
    }

    bus.emit("EVT:ORDER_PLACED", valid_payload,
             "contract_test", rid=valid_payload["rid"])

    invalid_payload = {k: v for k,
                       v in valid_payload.items() if k != "corr_id"}
    with pytest.raises(InvalidMessagePayloadError):
        bus.emit("EVT:ORDER_PLACED", invalid_payload,
                 "contract_test", rid=invalid_payload["rid"])
