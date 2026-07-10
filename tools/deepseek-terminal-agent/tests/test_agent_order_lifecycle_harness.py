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
        "payload": {"ticker": "SOLUSDT", "qty": 0.5},
        "rationale": "test validation rationale",
    }



def test_harness_blocked_guard_rejections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command())

    # 1. Blocked due to missing capability descriptor
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=None,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert trace.fsm_status == "rejected_by_fsm"
    assert trace.adapter_status == "blocked_guard"
    assert trace.exchange_status == "none"

    # 2. Blocked due to non-testnet environment in descriptor
    cmd = AgentActionCommand(**get_base_command())
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
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert trace.fsm_status == "rejected_by_fsm"
    assert trace.adapter_status == "blocked_guard"


def test_harness_blocked_missing_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command())

    # Bypassing validation via model_construct to check harness handler behavior
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
    assert trace.adapter_status == "blocked_missing_config"


def test_harness_blocked_no_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command())

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
    # Passed FSM check (no_order_observation_mode=False), but blocked by P40A submit gate
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=False,
    )
    assert trace.fsm_status == "recorded"
    assert trace.adapter_status == "blocked_no_order"
    assert trace.exchange_status == "none"


def test_harness_testnet_proof_ack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command())

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
    # FSM check passed, gate allows submit, and ACL returns order_placed
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
        base_url="https://testnet.binance.vision",
    )
    assert trace.fsm_status == "recorded"
    assert trace.adapter_status == "submitted_testnet"
    assert trace.exchange_status == "exchange_ack"
    assert trace.lifecycle_ref.startswith("stub-")


def test_harness_url_double_guard_rejects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
    cmd = AgentActionCommand(**get_base_command())

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
    # Should reject due to production url double guard
    trace = harness.run_lifecycle_trace(
        cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True,
        base_url="https://api.binance.com",
    )
    assert trace.fsm_status == "rejected_by_fsm"
    assert trace.adapter_status == "blocked_guard"
    assert trace.exchange_status == "none"
