import json
from pathlib import Path

import pytest

try:
    from jsonschema import ValidationError, validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False
    ValidationError = Exception


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "intent_deferred_v1.json"


@pytest.fixture(scope="session")
def intent_deferred_schema():
    with open(SCHEMA_PATH, "r") as f:
        return json.load(f)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_legacy_payload_is_valid(intent_deferred_schema):
    validate(
        instance={
            "symbol": "BTCUSDT",
            "reason": "NRR-DATA-NOT-READY",
            "missing": "risk",
            "rid": "rid-123",
        },
        schema=intent_deferred_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_v1_payload_is_valid(intent_deferred_schema):
    validate(
        instance={
            "retry_key": "flip:BTCUSDT:1702500000000",
            "symbol": "BTCUSDT",
            "reason": "FLIP_CLOSE_PENDING",
            "next_allowed_ts": 1702500005000,
            "attempt": 1,
            "max_attempts": 5,
            "original_event": {
                "event_name": "EVT:MR_SIGNAL_PRODUCED",
                "payload_min": {"symbol": "BTCUSDT", "side": "BUY"},
            },
        },
        schema=intent_deferred_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_v1_payload_accepts_nested_price_ctx_object(intent_deferred_schema):
    validate(
        instance={
            "retry_key": "flip:BTCUSDT:1702500000000",
            "symbol": "BTCUSDT",
            "reason": "FLIP_CLOSE_PENDING",
            "next_allowed_ts": 1702500005000,
            "attempt": 1,
            "max_attempts": 5,
            "original_event": {
                "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
                "payload_min": {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "price_ctx": {
                        "entry_price": "25668.84",
                        "stop_price": "25540.50",
                        "target_price": "25925.53",
                    },
                },
            },
        },
        schema=intent_deferred_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_retry_key_payload_requires_v1_fields(intent_deferred_schema):
    with pytest.raises(ValidationError):
        validate(
            instance={
                "retry_key": "flip:BTCUSDT:1702500000000",
                "symbol": "BTCUSDT",
                "reason": "FLIP_CLOSE_PENDING",
            },
            schema=intent_deferred_schema,
        )

