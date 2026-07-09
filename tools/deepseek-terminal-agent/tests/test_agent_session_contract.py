from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.agent_session_contract import (
    CLIAgentSessionState,
    CLIAgentActionEnvelope,
    build_memory_refresh_action,
    build_sos_emit_action,
    build_proposal_submit_action,
    should_agent_session_continue,
    apply_timer_tick_to_session_state,
)


def test_action_envelope_rejects_forbidden_fields():
    # Valid envelope payload
    valid_env = CLIAgentActionEnvelope(
        action_kind="heartbeat",
        reason="Periodic ping",
        payload={"status": "running", "cpu": 12.5},
    )
    assert valid_env.action_kind == "heartbeat"

    # Reject forbidden order-like fields (order, sizing, leverage, quantity, notional)
    forbidden_payloads = [
        {"order": {"price": 10000, "side": "buy"}},
        {"sizing": {"percent": 5}},
        {"leverage": 3},
        {"quantity": 0.5},
        {"notional": 100},
        {"exchange_order_id": "1234"},
        {"client_order_id": "abc"},
    ]

    for payload in forbidden_payloads:
        with pytest.raises(ValidationError):
            CLIAgentActionEnvelope(
                action_kind="proposal_submit",
                reason="Should reject",
                payload=payload,
            )


def test_session_stop_condition():
    started = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
    state = CLIAgentSessionState(
        session_id="session-1",
        agent_id="agent-6",
        agent_number=6,
        max_runtime_seconds=60.0,
        max_iterations=10,
    )

    # 1. Bounded check - within limits
    assert should_agent_session_continue(started, started + timedelta(seconds=30), state, 5) is True

    # 2. Bounded check - iteration limit reached
    assert should_agent_session_continue(started, started + timedelta(seconds=30), state, 10) is False

    # 3. Bounded check - runtime limit reached
    assert should_agent_session_continue(started, started + timedelta(seconds=61), state, 5) is False


def test_sos_pending_and_state_transitions():
    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
    next_refresh = now + timedelta(minutes=60)
    
    state = CLIAgentSessionState(
        session_id="session-1",
        agent_id="agent-6",
        agent_number=6,
        next_refresh_at=now + timedelta(minutes=50),
        sos_pending=True,
        max_runtime_seconds=60.0,
        max_iterations=10,
        context_version=1,
    )

    # Apply tick without SOS and before scheduled refresh is due
    tick_time = now + timedelta(minutes=10)
    state_idle = apply_timer_tick_to_session_state(
        state, tick_time, next_refresh, sos_active=False
    )
    # Refresh should not occur
    assert state_idle.last_memory_refresh_at is None
    assert state_idle.sos_pending is True
    assert state_idle.context_version == 1

    # Apply tick with SOS active -> forces refresh immediately
    state_sos = apply_timer_tick_to_session_state(
        state, tick_time, next_refresh, sos_active=True
    )
    assert state_sos.last_memory_refresh_at == tick_time
    assert state_sos.next_refresh_at == next_refresh
    assert state_sos.sos_pending is False
    assert state_sos.context_version == 2

    # Apply tick when scheduled refresh is due (tick_time >= next_refresh_at)
    tick_due = now + timedelta(minutes=55)
    state_due = apply_timer_tick_to_session_state(
        state, tick_due, next_refresh, sos_active=False
    )
    assert state_due.last_memory_refresh_at == tick_due
    assert state_due.sos_pending is False
    assert state_due.context_version == 2


def test_proposal_submit_action_is_non_executable():
    action = build_proposal_submit_action(
        proposal_ref="proposal-1234",
        reason="Vol volatility note draft",
        payload={"analysis": "BTC vol index spiked, no trades proposed"},
    )
    assert action.action_kind == "proposal_submit"
    assert action.proposal_ref == "proposal-1234"
    assert "analysis" in action.payload

    # Rejects executable entries inside build payload
    with pytest.raises(ValidationError):
        build_proposal_submit_action(
            proposal_ref="proposal-1234",
            reason="Forbidden payload entry",
            payload={"sizing": 10},
        )
