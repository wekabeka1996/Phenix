"""
Phase 14C: Schema Registry Activation tests.

Verifies:
1. init_global_registry() loads validators from verb_registry_v1.yaml
2. FSMCore.emit() validates CMD:PROCESS_STRATEGY payloads when registry active
3. FSMCore.emit() works gracefully when registry is not initialized (backward compat)
"""
from unittest.mock import patch

import pytest

from vfoundation.core.fsm_core import FSMCore, InvalidMessagePayloadError
from vfoundation.core.schema_registry import (
    VerbSchemaRegistry,
    get_global_registry,
    init_global_registry,
)


@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Reset the global registry before/after each test."""
    import vfoundation.core.schema_registry as mod
    original = mod._global_registry
    mod._global_registry = None
    yield
    mod._global_registry = original


def test_init_global_registry_loads_validators() -> None:
    """Registry must load at least 1 validator from verb_registry_v1.yaml."""
    registry = init_global_registry(project_root=".")
    assert isinstance(registry, VerbSchemaRegistry)
    assert registry.total_validators > 0


def test_global_registry_returns_none_without_init() -> None:
    """get_global_registry() returns None before init is called."""
    assert get_global_registry() is None


def test_fsm_emit_validates_cmd_process_strategy_valid() -> None:
    """Valid CMD:PROCESS_STRATEGY payload must not raise."""
    init_global_registry(project_root=".")
    fsm = FSMCore()

    valid_payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1700000000000,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "open": "50000.0",
            "high": "50100.0",
            "low": "49900.0",
            "close": "50050.0",
            "volume": "100.0",
        },
        "features": {},
        "warmup": {"full_ready": True, "ticks_seen": 500},
        "regime": None,
    }
    # Should not raise
    fsm.emit("CMD:PROCESS_STRATEGY", payload=valid_payload, why="test")


def test_fsm_emit_rejects_cmd_process_strategy_invalid_tf_sec() -> None:
    """CMD:PROCESS_STRATEGY with tf_sec=0 must raise InvalidMessagePayloadError."""
    init_global_registry(project_root=".")
    fsm = FSMCore()

    invalid_payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 0,  # Invalid: minimum is 60
        "bar_close_ts": 1700000000000,
        "bar": {
            "open": "50000.0",
            "high": "50100.0",
            "low": "49900.0",
            "close": "50050.0",
            "volume": "100.0",
        },
        "features": {},
        "warmup": {"full_ready": True, "ticks_seen": 500},
        "regime": None,
    }
    with pytest.raises(InvalidMessagePayloadError):
        fsm.emit("CMD:PROCESS_STRATEGY", payload=invalid_payload, why="test")


def test_fsm_emit_graceful_without_registry() -> None:
    """Without registry initialization, emit must work without validation."""
    assert get_global_registry() is None
    fsm = FSMCore()

    # Even an empty payload should not raise (no validation)
    fsm.emit("CMD:PROCESS_STRATEGY", payload={"symbol": "test"}, why="test")


def test_fsm_emit_accepts_digit_prefixed_intent_deferred_payload() -> None:
    """Real FSM emit path must accept 1000PEPEUSDT and deliver EVT:INTENT_DEFERRED."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:INTENT_DEFERRED", lambda msg: observed.append(msg.pld))

    payload = {
        "retry_key": "llm:1000PEPEUSDT:1702500200000",
        "symbol": "1000PEPEUSDT",
        "reason": "NRR-RISK-STALE",
        "next_allowed_ts": 1702500205000,
        "attempt": 1,
        "max_attempts": 3,
        "retry_policy": {
            "attempt": 1,
            "max_attempts": 3,
            "backoff_ms": 2000,
            "ttl_ms": 5000,
        },
        "original_event": {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "payload_min": {
                "symbol": "1000PEPEUSDT",
                "side": "SELL",
                "strategy_id": "llm_microstructure",
            },
        },
        "why_chain": ["risk_skew", "defer_count:1"],
        "created_ts": 1702500200000,
        "context": "strategy_signal_gateway:risk_skew",
    }

    fsm.emit("EVT:INTENT_DEFERRED", payload=payload, why="test")

    assert observed
    assert observed[0]["symbol"] == "1000PEPEUSDT"
    assert observed[0]["original_event"]["payload_min"]["symbol"] == "1000PEPEUSDT"
