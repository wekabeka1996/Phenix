"""
Phase 14C: Schema Registry Activation tests.

Verifies:
1. init_global_registry() loads validators from verb_registry_v1.yaml
2. FSMCore.emit() validates CMD:PROCESS_STRATEGY payloads when registry active
3. FSMCore.emit() works gracefully when registry is not initialized (backward compat)
"""
from copy import deepcopy
from unittest.mock import patch

import pytest
from jsonschema.validators import Draft7Validator

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


def _trade_intent_payload() -> dict:
    return {
        "instrument": "BTCUSDT",
        "side": "BUY",
        "p": "0.75",
        "payoff_ratio_r": "2.0",
        "tca_budget": {
            "max_slippage_bps": "10",
            "max_latency_ms": 100,
            "maker_preference": "False",
        },
        "risk_budget": {
            "trade_cvar95_max_bps": "50",
            "session_cvar95_max_bps": "100",
        },
        "size": {
            "kelly_fraction": "0.10",
            "notional_cap_usd": "5000.0",
        },
        "order": {
            "qty": "0.01",
            "price_ref": "50000.0",
            "reduce_only": False,
            "order_type": "MARKET",
        },
        "why": ["boundary_hardening"],
        "dto_version": "1.0.0",
        "schema_ref": "trade_intent_v1.json",
        "trace": {
            "objective": {"score": 0.42, "winner": "aurora"},
            "model": "aurora",
        },
    }


def _old_style_trade_intent_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "instrument": {"type": "string"},
            "side": {"type": "string"},
            "p": {"type": "string"},
            "payoff_ratio_r": {"type": "string"},
            "tca_budget": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "max_slippage_bps": {"type": "string"},
                    "max_latency_ms": {"type": "integer"},
                    "maker_preference": {"type": "string"},
                },
                "required": [
                    "max_slippage_bps",
                    "max_latency_ms",
                    "maker_preference",
                ],
            },
            "risk_budget": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "trade_cvar95_max_bps": {"type": "string"},
                    "session_cvar95_max_bps": {"type": "string"},
                },
                "required": [
                    "trade_cvar95_max_bps",
                    "session_cvar95_max_bps",
                ],
            },
            "size": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kelly_fraction": {"type": "string"},
                    "notional_cap_usd": {"type": "string"},
                },
                "required": ["kelly_fraction", "notional_cap_usd"],
            },
            "order": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "qty": {"type": "string"},
                    "price_ref": {"type": "string"},
                    "reduce_only": {"type": "boolean"},
                    "order_type": {"type": "string"},
                },
                "required": [
                    "qty",
                    "price_ref",
                    "reduce_only",
                    "order_type",
                ],
            },
            "why": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "dto_version": {"type": "string"},
            "schema_ref": {"type": "string"},
        },
        "required": [
            "instrument",
            "side",
            "p",
            "payoff_ratio_r",
            "tca_budget",
            "risk_budget",
            "size",
            "order",
            "why",
            "dto_version",
            "schema_ref",
        ],
    }


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
        "reason_code": "NRR-RISK-STALE",
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


def test_fsm_emit_validates_trade_intent_proposed_with_trace() -> None:
    """Current runtime contract must accept optional top-level trace."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))

    payload = _trade_intent_payload()

    fsm.emit("EVT:TRADE_INTENT_PROPOSED",
             payload=payload, why="trace_contract")

    assert observed
    assert observed[0]["trace"]["objective"]["score"] == 0.42
    assert observed[0]["trace"]["model"] == "aurora"


def test_fsm_emit_rejects_trade_intent_proposed_with_unexpected_top_level_field() -> None:
    """Strict root additionalProperties must still reject unknown top-level fields."""
    init_global_registry(project_root=".")
    fsm = FSMCore()

    payload = _trade_intent_payload()
    payload["unexpected_top_level"] = "boom"

    with pytest.raises(InvalidMessagePayloadError, match="unexpected_top_level"):
        fsm.emit("EVT:TRADE_INTENT_PROPOSED",
                 payload=payload, why="strict_root")


def test_fsm_emit_rejects_trade_intent_proposed_with_tf_sec_top_level_field() -> None:
    """tf_sec is not part of the live trade-intent schema and must fail at the bus boundary."""
    init_global_registry(project_root=".")
    fsm = FSMCore()

    payload = _trade_intent_payload()
    payload["tf_sec"] = 300

    with pytest.raises(InvalidMessagePayloadError, match="tf_sec"):
        fsm.emit("EVT:TRADE_INTENT_PROPOSED",
                 payload=payload, why="strict_tf_sec")


def test_old_style_trade_intent_contract_rejects_trace_before_listener_dispatch() -> None:
    """Historical mismatch class: payload with trace must fail before listeners run."""
    import vfoundation.core.schema_registry as schema_registry_mod

    registry = VerbSchemaRegistry(project_root=".")
    registry._validators[("EVT", "TRADE_INTENT_PROPOSED")] = Draft7Validator(
        _old_style_trade_intent_schema()
    )
    schema_registry_mod._global_registry = registry

    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))

    payload = deepcopy(_trade_intent_payload())

    with pytest.raises(InvalidMessagePayloadError, match="trace"):
        fsm.emit("EVT:TRADE_INTENT_PROPOSED",
                 payload=payload, why="historical_regression")

    assert observed == []
