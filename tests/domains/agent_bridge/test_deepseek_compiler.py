from __future__ import annotations

import time
import pytest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from pydantic import ValidationError

from apps.reference.domains.agent_bridge.contracts_p26 import (
    AgentTradeDecisionV0,
    AgentAuthorityDeepseekTestnetConfig,
)
from apps.reference.domains.agent_bridge.deepseek_compiler import (
    compile_decision_to_intent_payload,
    DeepSeekCompilerError,
    load_pilot_config,
)

# Helper function to get valid config dict
def get_valid_config_data() -> Dict[str, Any]:
    return {
        "enabled": True,
        "profile": "deepseek_agent_only_testnet",
        "environment": "testnet",
        "session_id": "test_session_123",
        "agent_id": "deepseek_agent_p26",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "allowed_symbols": ["BTCUSDT", "ETHUSDT"],
        "allowed_horizons": ["micro", "scalp"],
        "allowed_actions": [
            "TESTNET_OPEN_LONG",
            "TESTNET_OPEN_SHORT",
            "TESTNET_CLOSE",
            "TESTNET_REDUCE",
            "WAIT",
            "OBSERVE",
            "NO_ACTION",
        ],
        "max_session_duration_sec": 1800,
        "max_orders_per_session": 3,
        "max_orders_per_symbol": 2,
        "max_open_positions_total": 1,
        "max_open_positions_per_symbol": 1,
        "max_notional_per_order": 25.0,
        "max_total_notional": 100.0,
        "min_seconds_between_orders": 180,
        "duplicate_decision_window_sec": 60,
        "default_order_type": "LIMIT",
        "default_time_in_force": "GTC",
        "decision_timeout_sec": 60,
        "provider_timeout_sec": 45,
        "stop_on_first_execution_error": True,
        "stop_on_unmatched_fill": True,
        "stop_on_lifecycle_divergence": True,
        "kill_switch_enabled": True,
        "record_all_decisions": True,
        "record_all_rejections": True,
        "record_all_orders": True,
    }


def get_valid_decision_data() -> Dict[str, Any]:
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


def test_config_model_valid() -> None:
    data = get_valid_config_data()
    cfg = AgentAuthorityDeepseekTestnetConfig.model_validate(data)
    assert cfg.enabled is True
    assert cfg.profile == "deepseek_agent_only_testnet"
    assert cfg.max_notional_per_order == 25.0


def test_config_model_missing_fields_fail_closed() -> None:
    data = get_valid_config_data()
    del data["max_notional_per_order"]
    with pytest.raises(ValidationError):
        AgentAuthorityDeepseekTestnetConfig.model_validate(data)


def test_decision_model_valid() -> None:
    data = get_valid_decision_data()
    decision = AgentTradeDecisionV0.model_validate(data)
    assert decision.side == "BUY"
    assert decision.action == "TESTNET_OPEN_LONG"


def test_decision_model_passive_actions_require_none() -> None:
    data = get_valid_decision_data()
    data["action"] = "WAIT"
    data["side"] = "BUY"  # Invalid! WAIT requires NONE
    with pytest.raises(ValidationError, match="Passive actions require side NONE"):
        AgentTradeDecisionV0.model_validate(data)

    data["side"] = "NONE"
    decision = AgentTradeDecisionV0.model_validate(data)
    assert decision.side == "NONE"


def test_decision_model_open_long_requires_buy() -> None:
    data = get_valid_decision_data()
    data["action"] = "TESTNET_OPEN_LONG"
    # First, test pydantic literal validation:
    data["side"] = "LONG"
    with pytest.raises(ValidationError, match="Input should be 'BUY', 'SELL' or 'NONE'"):
        AgentTradeDecisionV0.model_validate(data)

    # Next, test custom validation mismatch:
    data["side"] = "SELL"
    with pytest.raises(ValidationError, match="Open long requires side BUY"):
        AgentTradeDecisionV0.model_validate(data)


def test_decision_model_open_short_requires_sell() -> None:
    data = get_valid_decision_data()
    data["action"] = "TESTNET_OPEN_SHORT"
    # First, test pydantic literal validation:
    data["side"] = "SHORT"
    with pytest.raises(ValidationError, match="Input should be 'BUY', 'SELL' or 'NONE'"):
        AgentTradeDecisionV0.model_validate(data)

    # Next, test custom validation mismatch:
    data["side"] = "BUY"
    with pytest.raises(ValidationError, match="Open short requires side SELL"):
        AgentTradeDecisionV0.model_validate(data)


def test_decision_model_close_reduce_requires_active_side() -> None:
    data = get_valid_decision_data()
    data["action"] = "TESTNET_CLOSE"
    data["side"] = "NONE"  # Invalid! Must be BUY or SELL
    with pytest.raises(ValidationError, match="Close/Reduce actions require active side"):
        AgentTradeDecisionV0.model_validate(data)


def test_decision_model_invalid_symbol_action() -> None:
    data = get_valid_decision_data()
    data["symbol"] = "btcusdt"  # Must be uppercase
    with pytest.raises(ValidationError):
        AgentTradeDecisionV0.model_validate(data)


def test_decision_model_missing_evidence_refs() -> None:
    data = get_valid_decision_data()
    data["evidence_refs"] = []
    with pytest.raises(ValidationError):
        AgentTradeDecisionV0.model_validate(data)


def test_decision_model_testnet_only_false_rejected() -> None:
    data = get_valid_decision_data()
    data["testnet_only"] = False
    with pytest.raises(ValidationError):
        AgentTradeDecisionV0.model_validate(data)


def test_compiler_success() -> None:
    config = AgentAuthorityDeepseekTestnetConfig.model_validate(get_valid_config_data())
    decision = AgentTradeDecisionV0.model_validate(get_valid_decision_data())
    
    now_ms = int(time.time() * 1000)
    packet = {
        "packet_id": "afp_abc123",
        "produced_ts_ms": now_ms - 5000,
        "symbol_markets": [
            {"symbol": "BTCUSDT", "close_price": "100000.0"}
        ]
    }
    
    instrument = SimpleNamespace(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("10.0"),
        tick_size=Decimal("0.01"),
    )
    
    # Floor to 0.001 results in 0.000 (since 25/100000 = 0.00025), raising QTY_BELOW_MINIMUM
    with pytest.raises(DeepSeekCompilerError, match="below instrument minimum") as exc:
        compile_decision_to_intent_payload(
            decision, packet, config, instrument, now_ms
        )
    assert exc.value.reason_code == "QTY_BELOW_MINIMUM"
    
    # Let's adjust max_notional_per_order to 250.0 to get valid qty
    config_dict = get_valid_config_data()
    config_dict["max_notional_per_order"] = 250.0
    config = AgentAuthorityDeepseekTestnetConfig.model_validate(config_dict)
    
    payload = compile_decision_to_intent_payload(
        decision, packet, config, instrument, now_ms
    )
    # 250.0 / 100000 = 0.0025. Floor to 0.001 step size is 0.002
    assert payload["order"]["qty"] == "0.002"
    assert payload["order"]["price"] == "100000.00"
    assert payload["trace"]["session_id"] == "test_session_123"


def test_compiler_stale_packet_rejected() -> None:
    config = AgentAuthorityDeepseekTestnetConfig.model_validate(get_valid_config_data())
    decision = AgentTradeDecisionV0.model_validate(get_valid_decision_data())
    
    now_ms = int(time.time() * 1000)
    packet = {
        "packet_id": "afp_abc123",
        "produced_ts_ms": now_ms - 70000,  # 70s ago, limit is 60s
        "symbol_markets": [
            {"symbol": "BTCUSDT", "close_price": "100000.0"}
        ]
    }
    
    instrument = SimpleNamespace(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("10.0"),
        tick_size=Decimal("0.01"),
    )
    
    with pytest.raises(DeepSeekCompilerError, match="stale") as exc:
        compile_decision_to_intent_payload(
            decision, packet, config, instrument, now_ms
        )
    assert exc.value.reason_code == "PACKET_STALE"


def test_compiler_price_unresolved() -> None:
    config = AgentAuthorityDeepseekTestnetConfig.model_validate(get_valid_config_data())
    decision = AgentTradeDecisionV0.model_validate(get_valid_decision_data())
    
    now_ms = int(time.time() * 1000)
    packet = {
        "packet_id": "afp_abc123",
        "produced_ts_ms": now_ms - 5000,
        "symbol_markets": [
            {"symbol": "ETHUSDT", "close_price": "3000.0"}  # BTCUSDT missing!
        ]
    }
    
    instrument = SimpleNamespace(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("10.0"),
        tick_size=Decimal("0.01"),
    )
    
    with pytest.raises(DeepSeekCompilerError, match="Could not resolve close price") as exc:
        compile_decision_to_intent_payload(
            decision, packet, config, instrument, now_ms
        )
    assert exc.value.reason_code == "PRICE_UNRESOLVED"


def test_compiler_qty_below_minimum() -> None:
    config = AgentAuthorityDeepseekTestnetConfig.model_validate(get_valid_config_data())
    decision = AgentTradeDecisionV0.model_validate(get_valid_decision_data())
    
    now_ms = int(time.time() * 1000)
    packet = {
        "packet_id": "afp_abc123",
        "produced_ts_ms": now_ms - 5000,
        "symbol_markets": [
            {"symbol": "BTCUSDT", "close_price": "100000.0"}
        ]
    }
    
    # min_qty is 0.01, but max_notional_per_order is 25.0, so qty is 25/100000 = 0.00025, which is floored to 0.000
    instrument = SimpleNamespace(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.01"),
        min_notional=Decimal("10.0"),
        tick_size=Decimal("0.01"),
    )
    
    with pytest.raises(DeepSeekCompilerError, match="below instrument minimum") as exc:
        compile_decision_to_intent_payload(
            decision, packet, config, instrument, now_ms
        )
    assert exc.value.reason_code == "QTY_BELOW_MINIMUM"


def test_compiler_lifecycle_validation() -> None:
    config_dict = get_valid_config_data()
    config_dict["max_notional_per_order"] = 300.0
    config = AgentAuthorityDeepseekTestnetConfig.model_validate(config_dict)
    
    decision_dict = get_valid_decision_data()
    decision_dict["action"] = "TESTNET_CLOSE"
    decision_dict["side"] = "SELL"  # We want to close/reduce a LONG position (executing SELL)
    decision = AgentTradeDecisionV0.model_validate(decision_dict)
    
    now_ms = int(time.time() * 1000)
    
    # Scenario A: active position is LONG. The decision side is SELL. This matches!
    packet = {
        "packet_id": "afp_abc123",
        "produced_ts_ms": now_ms - 5000,
        "symbol_markets": [
            {"symbol": "BTCUSDT", "close_price": "100000.0"}
        ],
        "position_life": {
            "positions": [
                {"symbol": "BTCUSDT", "side": "LONG", "qty": "0.01"}
            ]
        }
    }
    
    instrument = SimpleNamespace(
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("10.0"),
        tick_size=Decimal("0.01"),
    )
    
    payload = compile_decision_to_intent_payload(
        decision, packet, config, instrument, now_ms
    )
    assert payload["side"] == "SELL"
    assert payload["reduce_only"] is True

    # Scenario B: active position is LONG but decision side is BUY. Mismatch error!
    decision_dict_err = get_valid_decision_data()
    decision_dict_err["action"] = "TESTNET_CLOSE"
    decision_dict_err["side"] = "BUY"
    decision_err = AgentTradeDecisionV0.model_validate(decision_dict_err)
    with pytest.raises(DeepSeekCompilerError, match="does not match active position side") as exc:
        compile_decision_to_intent_payload(
            decision_err, packet, config, instrument, now_ms
        )
    assert exc.value.reason_code == "LIFECYCLE_UNKNOWN"

    # Scenario C: no active position found, fallback to decision side
    packet_no_pos = {
        "packet_id": "afp_abc123",
        "produced_ts_ms": now_ms - 5000,
        "symbol_markets": [
            {"symbol": "BTCUSDT", "close_price": "100000.0"}
        ],
        "position_life": {
            "positions": []
        }
    }
    payload_fallback = compile_decision_to_intent_payload(
        decision, packet_no_pos, config, instrument, now_ms
    )
    assert payload_fallback["side"] == "SELL"
    assert payload_fallback["reduce_only"] is True


def test_secrets_redaction() -> None:
    import os
    from scripts.run_deepseek_testnet_pilot import redact
    
    # Store old key to restore later
    old_key = os.environ.get("DEEPSEEK_API_KEY")
    os.environ["DEEPSEEK_API_KEY"] = "sk-super-secret-key-12345"
    try:
        sample_log = "Error calling deepseek with key sk-super-secret-key-12345: timeout"
        redacted = redact(sample_log)
        assert "sk-super-secret-key-12345" not in redacted
        assert "REDACTED" in redacted
    finally:
        if old_key is not None:
            os.environ["DEEPSEEK_API_KEY"] = old_key
        else:
            del os.environ["DEEPSEEK_API_KEY"]
