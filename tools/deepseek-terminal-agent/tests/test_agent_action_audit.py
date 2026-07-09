from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.agent_action_audit import (
    AgentActionCommand,
    FSMAuditRegistry,
    CommandAuditJournal,
    transit_status,
    FSMHandoffGateway,
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


class MockTestnetAdapter:
    def __init__(self, base_url: str = "https://testnet.binancefuture.com"):
        self.base_url = base_url
        self.orders = []

    async def create_order(self, params):
        from vfoundation.core.adapters.base import ExchangeOrderResponse
        import time
        self.orders.append(params)
        if params.symbol == "FAIL":
            raise RuntimeError("API Error")
        return ExchangeOrderResponse(
            order_id="order-999",
            client_order_id=params.client_order_id,
            symbol=params.symbol,
            side=params.side,
            quantity=params.quantity,
            filled_qty=params.quantity,
            price=params.price,
            status="FILLED",
            timestamp_ms=int(time.time() * 1000)
        )


@pytest.mark.asyncio
async def test_fsm_handoff_gateway_validations_and_execution():
    registry = FSMAuditRegistry()
    adapter = MockTestnetAdapter()
    gateway = FSMHandoffGateway(registry, adapter)
    journal = CommandAuditJournal(registry)

    # 1. Invalid kind rejection
    data = get_base_command()
    data["command_kind"] = "UNKNOWN_KIND"
    cmd_invalid_kind = AgentActionCommand(**data)
    gateway.validate_and_transit(cmd_invalid_kind, journal)
    assert cmd_invalid_kind.status == "rejected_by_fsm"
    assert "unknown event kind" in journal.history[-1][2].lower()

    # 2. Missing/invalid side rejection
    data = get_base_command()
    data["command_kind"] = "AGENT_TESTNET_ORDER_REQUESTED"
    data["payload"] = {"quantity": "0.5"}  # no side
    cmd_missing_side = AgentActionCommand(**data)
    gateway.validate_and_transit(cmd_missing_side, journal)
    assert cmd_missing_side.status == "rejected_by_fsm"
    assert "missing or invalid side" in journal.history[-1][2].lower()

    # 3. Missing explicit quantity/notional rejection
    data = get_base_command()
    data["command_kind"] = "AGENT_TESTNET_ORDER_REQUESTED"
    data["payload"] = {"side": "BUY"}  # Empty quantity
    cmd_missing_qty = AgentActionCommand(**data)
    gateway.validate_and_transit(cmd_missing_qty, journal)
    assert cmd_missing_qty.status == "rejected_by_fsm"
    assert "missing explicit quantity/notional" in journal.history[-1][2].lower()

    # 4. Invalid quantity <= 0 rejection
    data = get_base_command()
    data["command_kind"] = "AGENT_TESTNET_ORDER_REQUESTED"
    data["payload"] = {"side": "BUY", "quantity": "0"}
    cmd_invalid_qty = AgentActionCommand(**data)
    gateway.validate_and_transit(cmd_invalid_qty, journal)
    assert cmd_invalid_qty.status == "rejected_by_fsm"
    assert "invalid quantity <= 0" in journal.history[-1][2].lower()

    # 5. Missing adapter rejection
    data = get_base_command()
    data["payload"] = {"side": "BUY", "quantity": "1.0"}
    cmd_no_adapter = AgentActionCommand(**data)
    gateway_no_adapter = FSMHandoffGateway(registry, None)
    gateway_no_adapter.validate_and_transit(cmd_no_adapter, journal)
    assert cmd_no_adapter.status == "rejected_by_fsm"
    assert "no execution adapter available" in journal.history[-1][2].lower()

    # 6. Non-testnet base URL adapter rejection
    data = get_base_command()
    data["payload"] = {"side": "BUY", "quantity": "1.0"}
    cmd_non_testnet = AgentActionCommand(**data)
    live_adapter = MockTestnetAdapter(base_url="https://fapi.binance.com")
    gateway_non_testnet = FSMHandoffGateway(registry, live_adapter)
    gateway_non_testnet.validate_and_transit(cmd_non_testnet, journal)
    assert cmd_non_testnet.status == "rejected_by_fsm"
    assert "url does not prove testnet" in journal.history[-1][2].lower()

    # 7. Valid handoff and successful execution
    data = get_base_command()
    data["payload"] = {"side": "BUY", "quantity": "0.5", "price": "100.0"}
    cmd_valid = AgentActionCommand(**data)
    
    # Validation step
    gateway.validate_and_transit(cmd_valid, journal)
    assert cmd_valid.status == "accepted_by_fsm"

    # Execution step
    resp = await gateway.execute_testnet_order(cmd_valid, journal)
    assert resp.order_id == "order-999"
    assert cmd_valid.status == "lifecycle_closed"
    assert cmd_valid.payload["exchange_order_id"] == "order-999"

    # 8. Valid handoff but execution failure
    data = get_base_command()
    data["payload"] = {"side": "BUY", "quantity": "0.5", "symbol": "FAIL"}
    cmd_fail = AgentActionCommand(**data)
    
    gateway.validate_and_transit(cmd_fail, journal)
    assert cmd_fail.status == "accepted_by_fsm"

    with pytest.raises(RuntimeError, match="API Error"):
        await gateway.execute_testnet_order(cmd_fail, journal)
    assert cmd_fail.status == "lifecycle_closed"
    assert "Exchange REJECT" in journal.history[-2][2]


def test_verify_handoff_safety_non_testnet_descriptor_rejects():
    from deepseek_terminal_agent.sessions.agent_action_audit import (
        verify_handoff_safety,
        AdapterCapabilityDescriptor,
        AgentActionCommand,
    )
    cmd = AgentActionCommand(**get_base_command())
    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="mainnet",
        supports_order_submit=True,
        supports_no_order_observation=False,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    with pytest.raises(ValueError, match="invalid environment: mainnet"):
        verify_handoff_safety(cmd, desc, no_order_observation_mode=False)
    assert cmd.status == "rejected_by_fsm"


def test_verify_handoff_safety_missing_descriptor_rejects():
    from deepseek_terminal_agent.sessions.agent_action_audit import (
        verify_handoff_safety,
        AgentActionCommand,
    )
    cmd = AgentActionCommand(**get_base_command())
    with pytest.raises(ValueError, match="capability descriptor is missing"):
        verify_handoff_safety(cmd, None, no_order_observation_mode=False)
    assert cmd.status == "rejected_by_fsm"


def test_verify_handoff_safety_no_order_observation_mode_blocks():
    from deepseek_terminal_agent.sessions.agent_action_audit import (
        verify_handoff_safety,
        AdapterCapabilityDescriptor,
        AgentActionCommand,
    )
    cmd = AgentActionCommand(**get_base_command())
    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        supports_order_submit=True,
        supports_no_order_observation=False,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    with pytest.raises(ValueError, match="no_order_observation_mode is active"):
        verify_handoff_safety(cmd, desc, no_order_observation_mode=True)
    assert cmd.status == "rejected_by_fsm"


def test_verify_handoff_safety_url_string_alone_insufficient():
    from deepseek_terminal_agent.sessions.agent_action_audit import (
        verify_handoff_safety,
        AgentActionCommand,
    )
    cmd = AgentActionCommand(**get_base_command())
    # Even if base_url is testnet, missing descriptor must reject
    with pytest.raises(ValueError, match="capability descriptor is missing"):
        verify_handoff_safety(cmd, None, no_order_observation_mode=False, base_url="https://testnet.binance.vision")
    assert cmd.status == "rejected_by_fsm"


def test_verify_handoff_safety_valid_passes():
    from deepseek_terminal_agent.sessions.agent_action_audit import (
        verify_handoff_safety,
        AdapterCapabilityDescriptor,
        AgentActionCommand,
    )
    data = get_base_command()
    data["payload"] = {"ticker": "BTCUSDT", "qty": 0.5}
    cmd = AgentActionCommand(**data)
    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        supports_order_submit=True,
        supports_no_order_observation=False,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    # Valid testnet passes handoff validation without submitting real order
    verify_handoff_safety(cmd, desc, no_order_observation_mode=False, base_url="https://testnet.binance.vision")
    assert cmd.status == "recorded"


def test_verify_handoff_safety_rejection_log_preserves_fields(tmp_path, monkeypatch):
    from deepseek_terminal_agent.sessions.agent_action_audit import (
        verify_handoff_safety,
        AgentActionCommand,
    )
    import json
    import pathlib

    # Redirect .agent_memory to tmp_path
    monkeypatch.chdir(tmp_path)

    cmd = AgentActionCommand(**get_base_command())

    with pytest.raises(ValueError):
        verify_handoff_safety(cmd, None, no_order_observation_mode=False)

    # Read rejection log
    log_file = pathlib.Path(".agent_memory") / "sessions" / cmd.session_id / "audit_rejections.jsonl"
    assert log_file.exists()

    with open(log_file, "r") as f:
        line = f.readline()
        data = json.loads(line)

    assert data["agent_id"] == cmd.agent_id
    assert data["session_id"] == cmd.session_id
    assert data["command_id"] == cmd.command_id
    assert data["event_id"] == cmd.event_id
    assert data["reason"] == "capability descriptor is missing"
    assert "timestamp" in data
