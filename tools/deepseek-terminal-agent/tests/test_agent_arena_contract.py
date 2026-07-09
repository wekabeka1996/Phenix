"""Tests for P37B Event-First Agent Arena contract constraints and registry validations."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.agent_arena_contract import AgentArenaCommandEnvelope


def test_valid_arena_command_envelope():
    # Valid general command
    env = AgentArenaCommandEnvelope(
        session_id="session-123",
        agent_id="agent-abc",
        agent_number=2,
        command_kind="AGENT_ARENA_COMMAND_REQUESTED",
        rationale="Analyzing signal for entry.",
        source="cockpit",
        payload={"param": 42}
    )
    assert env.schema_version == 1
    assert env.execution_authority == "agent_testnet_arena"
    assert env.testnet_only is True

    # Valid order command
    env_order = AgentArenaCommandEnvelope(
        session_id="session-123",
        agent_id="agent-abc",
        agent_number=2,
        command_kind="AGENT_TESTNET_ORDER_REQUESTED",
        rationale="Order entry on VWAP support.",
        symbol="BTC-USDT",
        source="cockpit",
        payload={
            "quantity": 0.5,
            "order_type": "LIMIT",
            "price": 95500.0
        }
    )
    assert env_order.symbol == "BTC-USDT"


def test_missing_required_fields():
    # Missing session_id
    with pytest.raises(ValidationError):
        AgentArenaCommandEnvelope(
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            rationale="Rationale",
            source="cockpit"
        )

    # Missing agent_id
    with pytest.raises(ValidationError):
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            rationale="Rationale",
            source="cockpit"
        )

    # Missing rationale
    with pytest.raises(ValidationError):
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            source="cockpit"
        )


def test_forbidden_live_trading_flags():
    # Flat live/mainnet keys in payload
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            rationale="Rationale",
            source="cockpit",
            payload={"mainnet": True}
        )
    assert "live/mainnet trading flags are prohibited" in str(exc.value)

    # Nested live/mainnet keys in payload
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            rationale="Rationale",
            source="cockpit",
            payload={"options": {"nested": {"live": "true"}}}
        )
    assert "live/mainnet trading flags are prohibited" in str(exc.value)


def test_forbidden_exchange_credentials():
    # Credentials inside payload (api_key)
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            rationale="Rationale",
            source="cockpit",
            payload={"api_key": "some-secret-key"}
        )
    assert "raw exchange credentials" in str(exc.value)

    # Nested credentials (secret_key)
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_ARENA_COMMAND_REQUESTED",
            rationale="Rationale",
            source="cockpit",
            payload={"auth": {"nested": {"secret": "secret-pass"}}}
        )
    assert "raw exchange credentials" in str(exc.value)


def test_explicit_order_defaults_enforcement():
    # Missing quantity/notional
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_ORDER_REQUESTED",
            rationale="Rationale",
            symbol="BTC-USDT",
            source="cockpit",
            payload={"order_type": "MARKET"}
        )
    assert "either 'quantity' or 'notional' must be explicitly provided" in str(exc.value)

    # Non-positive quantity
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_ORDER_REQUESTED",
            rationale="Rationale",
            symbol="BTC-USDT",
            source="cockpit",
            payload={"quantity": 0, "order_type": "MARKET"}
        )
    assert "Quantity must be positive and non-zero" in str(exc.value)

    # Missing order type
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_ORDER_REQUESTED",
            rationale="Rationale",
            symbol="BTC-USDT",
            source="cockpit",
            payload={"quantity": 10}
        )
    assert "order_type' must be explicitly specified" in str(exc.value)

    # Limit order missing price
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_ORDER_REQUESTED",
            rationale="Rationale",
            symbol="BTC-USDT",
            source="cockpit",
            payload={"quantity": 10, "order_type": "LIMIT"}
        )
    assert "price' is required for LIMIT orders" in str(exc.value)

    # Limit order non-positive price
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_ORDER_REQUESTED",
            rationale="Rationale",
            symbol="BTC-USDT",
            source="cockpit",
            payload={"quantity": 10, "order_type": "LIMIT", "price": -5}
        )
    assert "Price must be positive and non-zero" in str(exc.value)


def test_explicit_cancel_reference_enforcement():
    # Missing exchange_order_id and client_order_id
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_CANCEL_REQUESTED",
            rationale="Rationale",
            symbol="BTC-USDT",
            source="cockpit",
            payload={}
        )
    assert "must specify either 'exchange_order_id' or 'client_order_id' explicitly" in str(exc.value)


def test_symbol_mandatory_for_trade_actions():
    # Missing symbol on order requested
    with pytest.raises(ValidationError) as exc:
        AgentArenaCommandEnvelope(
            session_id="session-123",
            agent_id="agent-abc",
            agent_number=2,
            command_kind="AGENT_TESTNET_ORDER_REQUESTED",
            rationale="Rationale",
            source="cockpit",
            payload={"quantity": 10, "order_type": "MARKET"}
        )
    assert "Symbol is required" in str(exc.value)


def test_registry_entries_validation():
    # Resolve project root registry path
    test_dir = Path(__file__).resolve().parent
    agent_root = test_dir.parent
    project_root = agent_root.parent.parent
    registry_path = project_root / "apps/reference/dictionaries/verb_registry_v1.yaml"
    
    assert registry_path.exists(), f"Registry file not found at {registry_path}"
    
    with open(registry_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    verbs = {item["verb"]: item for item in data.get("registry", []) if isinstance(item, dict) and "verb" in item}
    
    required_verbs = [
        "AGENT_ARENA_COMMAND_REQUESTED",
        "AGENT_ARENA_COMMAND_REJECTED",
        "AGENT_ARENA_COMMAND_ACCEPTED",
        "AGENT_TESTNET_ORDER_REQUESTED",
        "AGENT_TESTNET_CANCEL_REQUESTED",
        "AGENT_TESTNET_CLOSE_REQUESTED",
        "AGENT_ARENA_RATIONALE_RECORDED",
        "AGENT_ARENA_SOS_EMITTED"
    ]
    
    for v in required_verbs:
        assert v in verbs, f"Required verb {v} is missing from verb_registry_v1.yaml"
        entry = verbs[v]
        assert entry["owner"] == "agent_bridge", f"Owner for verb {v} must be agent_bridge"
        assert entry["status"] == "active", f"Status for verb {v} must be active"
