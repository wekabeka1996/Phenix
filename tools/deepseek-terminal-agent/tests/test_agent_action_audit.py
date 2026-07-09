from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.agent_action_audit import (
    AgentActionCommand,
    FSMAuditRegistry,
    CommandAuditJournal,
    transit_status,
)


def get_base_command() -> dict:
    return {
        "event_id": "evt-1234",
        "command_id": "cmd-5678",
        "session_id": "session-xyz",
        "agent_id": "deepseek-agent-6",
        "agent_number": 6,
        "command_kind": "ENTRY",
        "testnet_only": True,
        "payload": {"ticker": "BTCUSDT"},
    }


def test_action_command_rejects_non_testnet():
    # Valid testnet
    cmd = AgentActionCommand(**get_base_command())
    assert cmd.testnet_only is True

    # Mainnet/Live is forbidden
    data = get_base_command()
    data["testnet_only"] = False
    with pytest.raises(ValidationError):
        AgentActionCommand(**data)


def test_action_command_rejects_credentials_recursively():
    forbidden_payloads = [
        {"api_key": "12345"},
        {"secret": "my-secret"},
        {"sub_payload": {"private_key": "secret-key"}},
        {"creds": [{"password": "abc"}]},
    ]

    for payload in forbidden_payloads:
        data = get_base_command()
        data["payload"] = payload
        with pytest.raises(ValidationError):
            AgentActionCommand(**data)


def test_action_command_missing_fsm_fails_closed():
    registry = FSMAuditRegistry()
    
    # 1. Registered kind succeeds
    cmd_ok = AgentActionCommand(**get_base_command())
    registry.verify_registration(cmd_ok)
    assert cmd_ok.status == "recorded"

    # 2. Unregistered kind fails closed and transitions status to pending_fsm
    data = get_base_command()
    data["command_kind"] = "UNREGISTERED_ACTION_KIND"
    cmd_err = AgentActionCommand(**data)
    
    with pytest.raises(ValueError, match="FSM registration missing"):
        registry.verify_registration(cmd_err)
    assert cmd_err.status == "pending_fsm"


def test_audit_sequence_reconstruction():
    registry = FSMAuditRegistry()
    journal = CommandAuditJournal(registry)
    cmd = AgentActionCommand(**get_base_command())

    # Sequence step 1: Request recorded
    journal.record_request(cmd, "Recording incoming request")
    assert cmd.status == "recorded"
    assert len(journal.history) == 1

    # Sequence step 2: FSM accepts request
    journal.process_fsm_decision(cmd, accepted=True, reason="FSM validation check passed")
    assert cmd.status == "accepted_by_fsm"

    # Reject invalid sequence transitions (e.g. going back to recorded)
    with pytest.raises(ValueError):
        transit_status(cmd, "recorded")

    # Sequence step 3: Submission to testnet
    journal.submit_to_exchange(cmd, "Routing to testnet API")
    assert cmd.status == "submitted_testnet"

    # Sequence step 4: Exchange ACK response
    journal.record_exchange_response(cmd, ack=True, reason="Received order confirmation")
    assert cmd.status == "exchange_ack"

    # Sequence step 5: Close command lifecycle
    journal.close_command(cmd, "Archiving finished command context")
    assert cmd.status == "lifecycle_closed"

    # Confirm chronological audit history matches sequence
    expected_status_sequence = [
        "recorded",
        "accepted_by_fsm",
        "submitted_testnet",
        "exchange_ack",
        "lifecycle_closed",
    ]
    actual_sequence = [step[1] for step in journal.history if "Registration failed" not in step[2]]
    assert actual_sequence == expected_status_sequence
