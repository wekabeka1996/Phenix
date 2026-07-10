"""Tests for registered Cockpit agent arena event commands."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.agent_events import (
    AGENT_ARENA_EVENT_REGISTRY,
    AgentArenaEventCommand,
    build_agent_arena_event_command,
)


def test_registry_contains_required_agent_event_actions():
    assert set(AGENT_ARENA_EVENT_REGISTRY.events) == {
        "rationale",
        "sos",
        "testnet_order_request",
        "testnet_cancel_request",
        "testnet_close_request",
        "pause_agent",
        "resume_agent",
        "stop_agent",
        "stop_session",
        "trigger_analysis",
        "request_instruction_refresh",
        "emergency_stop",
    }
    assert AGENT_ARENA_EVENT_REGISTRY.events["rationale"].default_status == "recorded"
    assert AGENT_ARENA_EVENT_REGISTRY.events["testnet_order_request"].default_status == "pending_fsm"


def test_build_agent_arena_event_command_generates_ids_and_is_testnet_only():
    event = build_agent_arena_event_command(
        session_id="session-1",
        action="testnet_order_request",
        agent_id="agent-3",
        agent_number=3,
        rationale="Request FSM evaluation for testnet order.",
        payload={"symbol": "BTCUSDT", "side_bias": "long"},
    )

    assert event.event_id.startswith("event-")
    assert event.command_id.startswith("command-")
    assert event.created_at
    assert event.status == "pending_fsm"
    assert event.environment == "testnet"
    assert event.exchange_submitted is False


@pytest.mark.parametrize(
    "payload",
    [
        {"mainnet": True},
        {"live": True},
        {"api_key": "secret"},
        {"raw_exchange_payload": {"endpoint": "/fapi/v1/order"}},
        {"nested": {"raw_order": {"symbol": "BTCUSDT"}}},
    ],
)
def test_agent_arena_event_rejects_forbidden_payload_fields(payload):
    with pytest.raises(ValueError):
        AgentArenaEventCommand(
            session_id="session-1",
            agent_id="agent-3",
            agent_number=3,
            action="testnet_order_request",
            event_type="agent_arena.testnet_order_requested",
            rationale="reject",
            status="pending_fsm",
            payload=payload,
        )
