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
        "p": "0.5",
        "payoff_ratio_r": "1.5",
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
            "kelly_fraction": "0.1666666666666666666666666667",
            "notional_cap_usd": "5000.0",
        },
        "order": {
            "qty": "0.01",
            "price_ref": "50000.0",
            "reduce_only": False,
            "order_type": "MARKET",
        },
        "regime_epoch_ref": "stable_epoch:BTCUSDT:1700000000000",
        "why": ["boundary_hardening"],
        "dto_version": "1.0.0",
        "schema_ref": "trade_intent_v1.json",
        "trace": {
            "objective": {"score": 0.42, "winner": "aurora"},
            "model": "aurora",
            "kelly_provenance": {
                "source_path": "config.strategies.aurora.decision.kelly",
                "kelly_fraction": {
                    "formula": "p - (1 - p) / payoff_ratio_r",
                    "value": "0.1666666666666666666666666667",
                },
            },
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
        "structural_regime": "TREND_UP",
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
        "structural_regime": "TREND_UP",
    }
    with pytest.raises(InvalidMessagePayloadError):
        fsm.emit("CMD:PROCESS_STRATEGY", payload=invalid_payload, why="test")


def test_fsm_emit_accepts_position_closed_attribution_fields() -> None:
    """Execution close truth must preserve strategy attribution additively."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:POSITION_CLOSED", lambda msg: observed.append(msg.pld))

    payload = {
        "event_type": "POSITION_CLOSED",
        "symbol": "BTCUSDT",
        "trade_id": "trade-1",
        "close_reason": "TP",
        "close_ts_ms": 1700000000000,
        "realized_pnl_net": 12.5,
        "fees": 0.5,
        "entry_regime_epoch_ref": "epoch:BTCUSDT:1",
        "side": "BUY",
        "lifecycle_id": "life-1",
        "entry_rid": "entry-rid-1",
        "strategy_id": "aurora",
        "decision_id": "decision-1",
        "intent_id": "intent-1",
        "regime": "TREND_UP",
        "realized_pnl": 13.0,
        "close_price": 51000.0,
        "pnl_status": "resolved",
        "pnl_source": "close_fill",
        "economic_close_detected": True,
        "economic_close_kind": "explicit_close_fill",
        "accounting_unresolved_reason": None,
    }

    fsm.emit("EVT:POSITION_CLOSED", payload=payload, why="test")

    assert observed == [payload]


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
    assert observed[0]["trace"]["kelly_provenance"]["source_path"] == "config.strategies.aurora.decision.kelly"


def test_fsm_emit_validates_trade_intent_proposed_with_authority_context() -> None:
    """Current runtime contract must accept IntentBuilder authority provenance."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))

    payload = _trade_intent_payload()
    payload["authority_context"] = {
        "decision_id": "decision-001",
        "authority_mode": "shadow",
        "action": "allow",
        "apply_result": "FAST_ALLOW",
        "fallback_reason": None,
        "idempotent_key": "decision-001",
    }

    fsm.emit("EVT:TRADE_INTENT_PROPOSED",
             payload=payload, why="authority_context_contract")

    assert observed
    assert observed[0]["authority_context"]["decision_id"] == "decision-001"
    assert observed[0]["authority_context"]["apply_result"] == "FAST_ALLOW"


def test_fsm_emit_validates_trade_intent_proposed_with_trust_disabled_authority_context() -> None:
    """Strategy gateway trust-disabled fallback context is additive provenance."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))

    payload = _trade_intent_payload()
    payload["authority_context"] = {
        "decision_id": None,
        "authority_mode": "shadow",
        "action": "fallback",
        "apply_result": "TRUST_DISABLED_FASTPATH",
        "reason_code": "TRUST_DISABLED",
        "reason_text": "Neocortex trust_enabled=false",
    }

    fsm.emit("EVT:TRADE_INTENT_PROPOSED",
             payload=payload, why="trust_disabled_authority_context_contract")

    assert observed
    assert observed[0]["authority_context"]["decision_id"] is None
    assert observed[0]["authority_context"]["reason_code"] == "TRUST_DISABLED"


def test_fsm_emit_validates_trade_intent_proposed_with_journal_only_authority_context() -> None:
    """Journal-only authority evidence fields must be accepted without relaxing the rest of the contract."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))

    payload = _trade_intent_payload()
    payload["authority_context"] = {
        "decision_id": "decision-002",
        "authority_mode": "shadow",
        "action": "allow",
        "apply_result": "SHADOW_RECORDED",
        "capture_mode": "journal_only",
        "authority_applied": False,
        "no_effect": True,
    }

    fsm.emit("EVT:TRADE_INTENT_PROPOSED",
             payload=payload, why="journal_only_authority_context_contract")

    assert observed
    authority_context = observed[0]["authority_context"]
    assert authority_context["capture_mode"] == "journal_only"
    assert authority_context["authority_applied"] is False
    assert authority_context["no_effect"] is True


def test_fsm_emit_validates_trade_intent_proposed_with_shadow_counterfactual_authority_context() -> None:
    """Shadow-counterfactual authority evidence fields must be accepted without relaxing the rest of the contract."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))

    payload = _trade_intent_payload()
    payload["authority_context"] = {
        "decision_id": "decision-004",
        "authority_mode": "shadow",
        "action": "deny",
        "apply_result": "SHADOW_RECORDED",
        "capture_mode": "shadow_counterfactual",
        "authority_applied": False,
        "no_effect": True,
        "returned_action": "allow",
        "supports_counterfactual_join": True,
        "counterfactual_evaluation": True,
    }

    fsm.emit("EVT:TRADE_INTENT_PROPOSED",
             payload=payload, why="shadow_counterfactual_authority_context_contract")

    assert observed
    authority_context = observed[0]["authority_context"]
    assert authority_context["capture_mode"] == "shadow_counterfactual"
    assert authority_context["returned_action"] == "allow"
    assert authority_context["supports_counterfactual_join"] is True
    assert authority_context["counterfactual_evaluation"] is True


def test_fsm_emit_rejects_trade_intent_proposed_with_unexpected_authority_context_field() -> None:
    """Strict authority_context additionalProperties must still reject unknown journal fields."""
    init_global_registry(project_root=".")
    fsm = FSMCore()

    payload = _trade_intent_payload()
    payload["authority_context"] = {
        "decision_id": "decision-003",
        "authority_mode": "shadow",
        "action": "allow",
        "apply_result": "SHADOW_RECORDED",
        "capture_mode": "journal_only",
        "authority_applied": False,
        "no_effect": True,
        "unexpected_inner": "boom",
    }

    with pytest.raises(InvalidMessagePayloadError, match="unexpected_inner"):
        fsm.emit("EVT:TRADE_INTENT_PROPOSED",
                 payload=payload, why="strict_authority_context")


def test_fsm_emit_validates_neocortex_authority_seam_decision_event() -> None:
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:NEOCORTEX_AUTHORITY_SEAM_DECISION",
               lambda msg: observed.append(msg.pld))

    payload = {
        "schema_version": "1.0.0",
        "ts_ms": 1_700_000_000_500,
        "rid": "rid-seam-1",
        "decision_id": "decision-seam-1",
        "symbol": "BTCUSDT",
        "strategy_id": "aurora",
        "config_snapshot": {
            "trust_enabled": False,
            "authority_mode": "shadow",
            "evidence_capture_mode": "journal_only",
            "collect_authority_request": True,
            "collect_authority_response": True,
            "emit_shadow_decision_logged": True,
        },
        "branch_selection": {
            "selected_branch": "journal_only",
            "selection_reason": "journal_only_mode_enabled",
            "trust_disabled": True,
            "journal_only_enabled": True,
            "shadow_counterfactual_enabled": False,
        },
        "request_response_persistence": {
            "authority_request_written": True,
            "authority_response_written": True,
            "request_write_error": None,
            "response_write_error": None,
        },
        "no_effect_safety": {
            "returned_action": "ALLOW",
            "authority_applied": False,
            "no_effect": True,
        },
        "result": {
            "apply_result": "SHADOW_RECORDED",
            "model_action": "ALLOW",
            "fallback_reason": None,
        },
    }

    fsm.emit("EVT:NEOCORTEX_AUTHORITY_SEAM_DECISION",
             payload=payload, why="authority_seam_observability")

    assert observed
    assert observed[0]["branch_selection"]["selected_branch"] == "journal_only"
    assert observed[0]["request_response_persistence"]["authority_response_written"] is True


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
    payload.pop("regime_epoch_ref", None)

    with pytest.raises(InvalidMessagePayloadError, match="trace"):
        fsm.emit("EVT:TRADE_INTENT_PROPOSED",
                 payload=payload, why="historical_regression")

    assert observed == []


def test_fsm_emit_validates_position_closed_contract() -> None:
    """Current runtime contract must accept EVT:POSITION_CLOSED with required fields."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:POSITION_CLOSED", lambda msg: observed.append(msg.pld))

    payload = {
        "symbol": "BTCUSDT",
        "trade_id": "10001",
        "close_reason": "POSITION_CLOSED_DETECTED",
        "close_ts_ms": 1700000000000,
        "realized_pnl_net": -1.25,
        "fees": 0.05,
        "entry_regime_epoch_ref": None,
        "pnl_status": "resolved",
    }

    fsm.emit("EVT:POSITION_CLOSED", payload=payload, why="close_contract")

    assert observed
    assert observed[0]["trade_id"] == "10001"


def test_fsm_emit_validates_unresolved_position_closed_contract() -> None:
    """Unresolved close accounting must validate without fake numeric PnL."""
    init_global_registry(project_root=".")
    fsm = FSMCore()
    observed: list[dict] = []
    fsm.listen("EVT:POSITION_CLOSED", lambda msg: observed.append(msg.pld))

    payload = {
        "symbol": "BTCUSDT",
        "trade_id": None,
        "close_reason": "CLOSE",
        "close_ts_ms": 1700000000000,
        "realized_pnl_net": None,
        "fees": None,
        "entry_regime_epoch_ref": None,
        "pnl_status": "unresolved",
        "pnl_source": "unresolved",
        "accounting_unresolved_reason": "missing_close_fill_truth",
    }

    fsm.emit("EVT:POSITION_CLOSED", payload=payload,
             why="close_contract_unresolved")

    assert observed
    assert observed[0]["pnl_status"] == "unresolved"


def test_fsm_emit_rejects_position_closed_without_entry_regime_epoch_ref_field() -> None:
    """entry_regime_epoch_ref is field-required even when explicit null is allowed."""
    init_global_registry(project_root=".")
    fsm = FSMCore()

    payload = {
        "symbol": "BTCUSDT",
        "trade_id": "10001",
        "close_reason": "POSITION_CLOSED_DETECTED",
        "close_ts_ms": 1700000000000,
        "realized_pnl_net": -1.25,
        "fees": 0.05,
        "pnl_status": "resolved",
    }

    with pytest.raises(InvalidMessagePayloadError, match="entry_regime_epoch_ref"):
        fsm.emit("EVT:POSITION_CLOSED", payload=payload,
                 why="close_contract_missing_epoch")
