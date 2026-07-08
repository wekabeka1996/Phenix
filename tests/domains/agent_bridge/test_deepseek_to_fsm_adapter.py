import time
import pytest
from pydantic import ValidationError
from apps.reference.domains.agent_bridge.contracts_p26 import AgentTradeDecisionV0
from apps.reference.domains.agent_bridge.deepseek_to_fsm_adapter import AgentTradeDecisionToSignalMapper

def get_valid_decision_data() -> dict:
    return {
        "schema_version": "agent-trade-decision/v0",
        "agent_id": "deepseek_agent_p26",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "packet_ref": "agent-feed://packet/afp_abc123",
        "symbol": "BTCUSDT",
        "horizon": "micro",
        "action": "TESTNET_OPEN_LONG",
        "side": "BUY",
        "confidence": 0.85,
        "thesis": "Test thesis that is long enough to pass validation.",
        "invalidation": "Test invalidation that is long enough to pass.",
        "expected_scenarios": ["S01_TEST"],
        "evidence_refs": ["close_price"],
        "acknowledged_warnings": [],
        "risk_note": "Risk note that is long enough to pass validation.",
        "testnet_only": True,
    }

def test_open_long_mapping():
    data = get_valid_decision_data()
    data["action"] = "TESTNET_OPEN_LONG"
    data["side"] = "BUY"
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert payload["intent_kind"] == "ENTRY"
    assert payload["side"] == "BUY"
    assert payload["symbol"] == "BTCUSDT"

def test_open_short_mapping():
    data = get_valid_decision_data()
    data["action"] = "TESTNET_OPEN_SHORT"
    data["side"] = "SELL"
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert payload["intent_kind"] == "ENTRY"
    assert payload["side"] == "SELL"

def test_close_mapping():
    data = get_valid_decision_data()
    data["action"] = "TESTNET_CLOSE"
    data["side"] = "SELL"
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert payload["intent_kind"] == "FULL_CLOSE"
    assert payload["side"] == "SELL"

def test_reduce_mapping():
    data = get_valid_decision_data()
    data["action"] = "TESTNET_REDUCE"
    data["side"] = "BUY"
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert payload["intent_kind"] == "PARTIAL_CLOSE"
    assert payload["side"] == "BUY"

def test_passive_actions_do_not_emit_executable_signals():
    for action in ("WAIT", "OBSERVE", "NO_ACTION"):
        data = get_valid_decision_data()
        data["action"] = action
        data["side"] = "NONE"
        decision = AgentTradeDecisionV0.model_validate(data)
        payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
        assert payload["intent_kind"] == "OBSERVE"
        assert payload["side"] == "NONE"

def test_symbol_preservation():
    data = get_valid_decision_data()
    data["symbol"] = "ETHUSDT"
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert payload["symbol"] == "ETHUSDT"

def test_agent_id_mapping():
    data = get_valid_decision_data()
    data["agent_id"] = "custom_deepseek_agent"
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert payload["strategy_id"] == "custom_deepseek_agent"
    assert payload["agent_id"] == "custom_deepseek_agent"
    assert payload["source"] == "deepseek_agent"

def test_thesis_maps_to_why_chain():
    data = get_valid_decision_data()
    thesis_text = "Specific market microstructure pattern identified."
    data["thesis"] = thesis_text
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    assert thesis_text in payload["why_chain"]

def test_correlation_ids_preservation():
    data = get_valid_decision_data()
    decision = AgentTradeDecisionV0.model_validate(data)
    dec_id = "test-decision-id-1234"
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision, decision_id=dec_id)
    assert payload["rid"] == dec_id
    assert payload["decision_id"] == dec_id
    assert payload["packet_ref"] == decision.packet_ref

def test_strict_exclusions_not_present():
    data = get_valid_decision_data()
    decision = AgentTradeDecisionV0.model_validate(data)
    payload = AgentTradeDecisionToSignalMapper.map_decision(decision)
    excluded = {
        "qty", "quantity", "notional", "max_notional_per_order",
        "leverage", "target_leverage", "margin_mode", "step_size",
        "tick_size", "min_qty", "min_notional", "order_type", "tif",
        "time_in_force"
    }
    for k in excluded:
        assert k not in payload

def test_invalid_action_side_combinations_fail_closed():
    # Model-level validation handles mismatch
    data = get_valid_decision_data()
    data["action"] = "TESTNET_OPEN_LONG"
    data["side"] = "SELL"
    with pytest.raises(ValidationError):
        AgentTradeDecisionV0.model_validate(data)

    data = get_valid_decision_data()
    data["action"] = "TESTNET_CLOSE"
    data["side"] = "NONE"
    with pytest.raises(ValidationError):
        AgentTradeDecisionV0.model_validate(data)


def test_deepseek_events_validation():
    from vfoundation.core.schema_registry import init_global_registry
    
    registry = init_global_registry()
    
    # 1. Test DEEPSEEK_AGENT_DECISION_RECEIVED
    validator_dec = registry.get_validator("EVT", "DEEPSEEK_AGENT_DECISION_RECEIVED")
    assert validator_dec is not None, "DEEPSEEK_AGENT_DECISION_RECEIVED validator not loaded"
    
    valid_dec = get_valid_decision_data()
    # This should pass without raising ValidationError
    validator_dec.validate(valid_dec)
    
    # 2. Test DEEPSEEK_AGENT_SESSION_STOPPED
    validator_stop = registry.get_validator("EVT", "DEEPSEEK_AGENT_SESSION_STOPPED")
    assert validator_stop is not None, "DEEPSEEK_AGENT_SESSION_STOPPED validator not loaded"
    
    valid_stop = {
        "session_id": "test-session-123"
    }
    validator_stop.validate(valid_stop)
