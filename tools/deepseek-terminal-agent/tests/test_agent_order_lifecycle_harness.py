from datetime import datetime, timezone
import json
import pathlib
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.config import Settings
from deepseek_terminal_agent.sessions.agent_action_audit import (
    AgentActionCommand,
    AdapterCapabilityDescriptor,
)
from deepseek_terminal_agent.sessions.agent_order_lifecycle_harness import (
    AgentOrderLifecycleHarness,
    OrderLifecycleTrace,
    EXTERNAL_ACK,
    EXTERNAL_FILL,
    EXTERNAL_REJECT,
    BLOCKED_CONFIG,
    BLOCKED_POLICY,
    BLOCKED_DUPLICATE,
    BLOCKED_ENVIRONMENT,
)


def get_base_command(agent_number=2, agent_id="cli_agent_01", symbol="XRPUSDT", command_id="cmd-5678") -> dict:
    return {
        "event_id": f"evt-{command_id}",
        "command_id": command_id,
        "session_id": "session-xyz",
        "agent_id": agent_id,
        "agent_number": agent_number,
        "command_kind": "ENTRY",
        "testnet_only": True,
        "payload": {"ticker": symbol, "qty": 0.5},
        "rationale": "test validation rationale",
    }


def test_harness_blocked_guard_rejections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)

    # 1. Blocked due to missing capability descriptor
    cmd = AgentActionCommand(**get_base_command(command_id="cmd-1"))
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=None,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert isinstance(trace, BLOCKED_ENVIRONMENT)
    assert trace.fsm_status == "rejected_by_fsm"
    assert trace.adapter_status == "blocked_guard"
    assert trace.exchange_status == "none"

    # 2. Blocked due to non-testnet environment in descriptor
    cmd2 = AgentActionCommand(**get_base_command(command_id="cmd-2"))
    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="mainnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    trace = harness.run_lifecycle_trace(
        cmd2,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert isinstance(trace, BLOCKED_ENVIRONMENT)
    assert trace.fsm_status == "rejected_by_fsm"
    assert trace.adapter_status == "blocked_guard"


def test_harness_blocked_missing_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command(command_id="cmd-3"))

    desc = AdapterCapabilityDescriptor.model_construct(
        adapter_id="",  # Missing adapter_id
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
    )
    assert isinstance(trace, BLOCKED_CONFIG)
    assert trace.adapter_status == "blocked_missing_config"


def test_harness_blocked_no_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command(command_id="cmd-4"))

    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert isinstance(trace, BLOCKED_POLICY)
    assert trace.fsm_status == "recorded"
    assert trace.adapter_status == "blocked_no_order"
    assert trace.exchange_status == "none"


def test_harness_testnet_proof_ack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command(agent_number=2, agent_id="cli_agent_01", symbol="XRPUSDT", command_id="cmd-5"))

    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )

    # Set dummy credentials to bypass the credentials check
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "dummy_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "dummy_secret")

    # Mock the real BinanceAdapter placement methods to verify they get hit
    from apps.reference.adapters.binance_adapter import BinanceAdapter
    
    called_mock = {}
    async def mock_place_market_entry(self, symbol, side, quantity, new_client_order_id=None):
        called_mock["place_market_entry"] = True
        return {
            "orderId": "999888777",
            "clientOrderId": new_client_order_id,
            "status": "NEW",
        }
    monkeypatch.setattr(BinanceAdapter, "place_market_entry", mock_place_market_entry)

    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
        base_url="https://testnet.binance.vision",
    )
    assert isinstance(trace, EXTERNAL_ACK)
    assert trace.fsm_status == "recorded"
    assert trace.adapter_status == "submitted_testnet"
    assert trace.exchange_status == "exchange_ack"
    assert trace.lifecycle_ref == "999888777"
    assert called_mock.get("place_market_entry") is True


def test_harness_url_double_guard_rejects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command(command_id="cmd-6"))

    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
        base_url="https://api.binance.com",
    )
    assert isinstance(trace, BLOCKED_ENVIRONMENT)
    assert trace.fsm_status == "rejected_by_fsm"
    assert trace.adapter_status == "blocked_guard"
    assert trace.exchange_status == "none"


def test_harness_agent_1_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command(agent_number=1, agent_id="api_agent_01", symbol="SOLUSDT", command_id="cmd-7"))

    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "dummy_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "dummy_secret")

    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
    )
    assert isinstance(trace, BLOCKED_POLICY)
    assert trace.adapter_status == "blocked_policy"
    assert "Agent 1 is prohibited" in trace.reason


def test_harness_wrong_symbol_owner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    # CLI Agent 2 tries to trade SOLUSDT (owned by Agent 1)
    cmd = AgentActionCommand(**get_base_command(agent_number=2, agent_id="cli_agent_01", symbol="SOLUSDT", command_id="cmd-8"))

    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
    )
    assert isinstance(trace, BLOCKED_POLICY)
    assert trace.adapter_status == "blocked_policy"
    assert "Wrong symbol owner" in trace.reason


def test_harness_duplicate_command_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    
    desc = AdapterCapabilityDescriptor(
        adapter_id="binance_acl",
        environment="testnet",
        order_submit_enabled=True,
        no_order_observation_mode=False,
        supports_cancel=True,
        supports_close=True,
        source_of_truth="config",
        checked_at="2026-07-09T18:00:00Z",
    )
    
    # Run once
    cmd1 = AgentActionCommand(**get_base_command(command_id="cmd-dup-9"))
    trace1 = harness.run_lifecycle_trace(
        cmd1,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert isinstance(trace1, BLOCKED_POLICY)

    # Run again with same command ID
    cmd2 = AgentActionCommand(**get_base_command(command_id="cmd-dup-9"))
    trace2 = harness.run_lifecycle_trace(
        cmd2,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert isinstance(trace2, BLOCKED_DUPLICATE)
    assert trace2.adapter_status == "blocked_duplicate"
