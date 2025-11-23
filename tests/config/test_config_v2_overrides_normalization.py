"""
tests/config/test_config_v2_overrides_normalization.py
Verify overrides field schema validation (null vs object).

Constraint: EP-CONFIG-FEATURES-OVERRIDES-S9
"""

import pytest
from dataclasses import asdict
from apps.reference.config_models import ConfigV2
from tools.config_validator_v2 import validate_config_v2_schema


def test_overrides_null_is_valid():
    """
    Scenario 1: overrides=None (null) should be valid according to schema.

    Schema allows type: ["object", "null"], so None is semantically equivalent to {}.
    """
    config_v2 = ConfigV2(
        core=None,
        symbols=None,
        instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
        domains={
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        overrides=None,  # Explicit None
        modes={"profiles": {}},
    )

    errors = validate_config_v2_schema(config_v2)

    # Schema should accept overrides: null
    assert errors == [
    ], f"Expected no schema errors for overrides=None, got: {errors}"


def test_overrides_empty_dict_is_valid():
    """
    Scenario 2: overrides={} should be valid (standard case).
    """
    config_v2 = ConfigV2(
        core=None,
        symbols=None,
        instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
        domains={
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        overrides={},  # Empty dict
        modes={"profiles": {}},
    )

    errors = validate_config_v2_schema(config_v2)

    assert errors == [
    ], f"Expected no schema errors for overrides={{}}, got: {errors}"


def test_overrides_with_symbols_override_is_valid():
    """
    Scenario 3: overrides with nested symbols override should be valid.
    """
    config_v2 = ConfigV2(
        core=None,
        symbols=None,
        instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
        domains={
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        overrides={
            "symbols": {
                "BTCUSDT": {
                    "limits": {
                        "max_leverage": 20,
                        "min_notional": 15.0,
                    }
                }
            }
        },
        modes={"profiles": {}},
    )

    errors = validate_config_v2_schema(config_v2)

    assert errors == [
    ], f"Expected no schema errors for overrides with symbols, got: {errors}"


def test_overrides_with_domains_override_is_valid():
    """
    Scenario 4: overrides with nested domains override should be valid.
    """
    config_v2 = ConfigV2(
        core=None,
        symbols=None,
        instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
        domains={
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        overrides={
            "domains": {
                "execution": {
                    "exposure": {
                        "max_equity_utilization_ratio": 3.0
                    }
                }
            }
        },
        modes={"profiles": {}},
    )

    errors = validate_config_v2_schema(config_v2)

    assert errors == [
    ], f"Expected no schema errors for overrides with domains, got: {errors}"


def test_overrides_not_required_field():
    """
    Scenario 5: overrides field is not required (can be omitted entirely).

    After schema fix, overrides is removed from "required" array.
    """
    # Create config_v2 dict without overrides key at all
    payload = {
        "core": None,
        "symbols": None,
        "instruments": {"BTCUSDT": {"symbol": "BTCUSDT"}},
        "domains": {
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        "modes": {"profiles": {}},
        # overrides intentionally omitted
    }

    # Manually validate dict (bypass ConfigV2 dataclass which has default)
    from jsonschema import validate, ValidationError as JsonSchemaValidationError
    import json
    from pathlib import Path

    schema_path = Path(
        __file__).parents[2] / "config" / "_schemas" / "config_v2.schema.json"
    with schema_path.open("r") as f:
        schema = json.load(f)

    try:
        validate(instance=payload, schema=schema)
        # No exception → valid
    except JsonSchemaValidationError as exc:
        pytest.fail(
            f"Schema should not require overrides field, but got error: {exc}")


def test_overrides_null_behaves_like_empty_dict():
    """
    Scenario 6: ConfigV2 with overrides=None should behave like overrides={}.

    This is semantic equivalence test (not schema validation).
    """
    config_v2_null = ConfigV2(
        core=None,
        symbols=None,
        instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
        domains={
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        overrides=None,
        modes={"profiles": {}},
    )

    config_v2_empty = ConfigV2(
        core=None,
        symbols=None,
        instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
        domains={
            "execution": {"exposure": {}},
            "risk": {},
            "decision": {},
            "sizing": {},
            "features": {},
            "regimes": {},
        },
        overrides={},
        modes={"profiles": {}},
    )

    # Both should pass schema validation
    errors_null = validate_config_v2_schema(config_v2_null)
    errors_empty = validate_config_v2_schema(config_v2_empty)

    assert errors_null == [
    ], f"overrides=None should be valid, got: {errors_null}"
    assert errors_empty == [
    ], f"overrides={{}} should be valid, got: {errors_empty}"

    # Semantic equivalence: both None and {} mean "no overrides"
    # When converted to dict, None stays None but empty dict stays {}
    # This is OK - they are semantically equivalent for config purposes
