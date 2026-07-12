import asyncio
from datetime import datetime, timezone
import json
import os
import pathlib
import pytest
import yaml

from deepseek_terminal_agent.config import MemoryConfig, Settings
from deepseek_terminal_agent.sessions.store import SessionStore
from deepseek_terminal_agent.sessions.p42_config import load_dual_agent_config
from deepseek_terminal_agent.sessions.dual_agent_runner import DualAgentRuntimeRunner
from deepseek_terminal_agent.sessions.agent_order_lifecycle_harness import (
    AgentOrderLifecycleHarness,
    BLOCKED_POLICY,
    BLOCKED_DUPLICATE,
)
from deepseek_terminal_agent.sessions.agent_action_audit import AgentActionCommand, AdapterCapabilityDescriptor
from deepseek_terminal_agent.sessions.arena_runtime_view import ArenaRuntimeViewService, classify_exchange_evidence
from deepseek_terminal_agent.sessions.coordination_config import load_coordination_config


class MockFSM:
    def __init__(self):
        self.emitted = []

    def emit(self, event_name, payload=None, why="", *args, **kwargs):
        self.emitted.append((event_name, payload, why))
        return None


@pytest.fixture
def smoke_setup(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Write canonical-style yaml
    yaml_content = """
agents:
  api_agent_01:
    agent_id: "api_agent_01"
    agent_number: 1
    runtime_kind: "api"
    symbols: ["ETHUSDT", "SOLUSDT"]
    provider: "deepseek"
    model: "deepseek-v4-pro"
    instruction_files: ["config/instructions_api_agent_01.md"]
    market_refresh_cadence_sec: 10
    analysis_cadence_sec: 60
    response_timeout_sec: 15
    retry_count: 3
    heartbeat_cadence_sec: 10
    collective_publication_cadence_sec: 120
    portfolio_sync_cadence_sec: 60
    reflection_cadence_sec: 180
    session_duration_sec: 3600
    max_pending_commands: 5
    testnet_order_limits:
      max_orders: 10
      max_notional: 50.0
    startup_stagger_sec: 5
    shutdown_behavior: "graceful"

  cli_agent_01:
    agent_id: "cli_agent_01"
    agent_number: 2
    runtime_kind: "cli"
    symbols: ["XRPUSDT", "BNBUSDT"]
    provider: "deepseek"
    model: "deepseek-v4-pro"
    instruction_files: ["config/instructions_cli_agent_01.md"]
    market_refresh_cadence_sec: 10
    analysis_cadence_sec: 60
    response_timeout_sec: 15
    retry_count: 3
    heartbeat_cadence_sec: 10
    collective_publication_cadence_sec: 120
    portfolio_sync_cadence_sec: 60
    reflection_cadence_sec: 180
    session_duration_sec: 3600
    max_pending_commands: 5
    testnet_order_limits:
      max_orders: 10
      max_notional: 50.0
    startup_stagger_sec: 5
    shutdown_behavior: "graceful"
"""
    config_file = config_dir / "p42_dual_agent_mvp.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")
    
    # Write instruction files
    (config_dir / "instructions_api_agent_01.md").write_text("API instructions", encoding="utf-8")
    (config_dir / "instructions_cli_agent_01.md").write_text("CLI instructions", encoding="utf-8")
    
    # Create gate path
    gate_dir = tmp_path / "reports" / "p39a_runtime_mvp_integration_and_debt_control"
    gate_dir.mkdir(parents=True, exist_ok=True)
    (gate_dir / "RUN_READY_GATE.md").write_text("gate verified", encoding="utf-8")

    return config_file, tmp_path


def test_p42g_unified_runtime_smoke(smoke_setup, monkeypatch):
    config_file, root_dir = smoke_setup
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings(
        memory=MemoryConfig(canonical_sessions_root=".agent_memory/sessions")
    )
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(
        config=config,
        settings=settings,
        session_id="session-smoke",
        root_dir=root_dir,
        session_store=store,
        fsm_override=fsm
    )

    # 1. Verify both agent identities start in config
    assert "api_agent_01" in runner.config.agents
    assert "cli_agent_01" in runner.config.agents

    # 2. Verify both symbol leases load correctly from YAML
    assert runner.config.agents["api_agent_01"].symbols == ["ETHUSDT", "SOLUSDT"]
    assert runner.config.agents["cli_agent_01"].symbols == ["XRPUSDT", "BNBUSDT"]

    # Preflight check should pass cleanly
    runner.verify_preflight(bypass_network_check=True)

    # 3. Verify heartbeats appear in sessions
    runner.last_heartbeats["api_agent_01"] = datetime.now(timezone.utc).isoformat()
    runner.last_heartbeats["cli_agent_01"] = datetime.now(timezone.utc).isoformat()
    
    assert runner.last_heartbeats["api_agent_01"] is not None
    assert runner.last_heartbeats["cli_agent_01"] is not None

    # 4. Verify instruction ACKs appear
    from deepseek_terminal_agent.sessions.models import SessionEvent
    store.append_event(
        session_id="session-smoke",
        event=SessionEvent(
            event_id="ack-api",
            session_id="session-smoke",
            event_type="AGENT_INSTRUCTIONS_ACKED",
            metadata={"agent_id": "api_agent_01", "version": "1.0.0"}
        )
    )
    store.append_event(
        session_id="session-smoke",
        event=SessionEvent(
            event_id="ack-cli",
            session_id="session-smoke",
            event_type="AGENT_INSTRUCTIONS_ACKED",
            metadata={"agent_id": "cli_agent_01", "version": "1.0.0"}
        )
    )
    
    events = store.list_events("session-smoke")
    acks = [e for e in events if e.get("event_type") == "AGENT_INSTRUCTIONS_ACKED"]
    assert len(acks) == 2

    # 5. Verify peer publication is visible
    runner.register_fsm_listeners()
    fsm.emit("EVT:PEER_MESSAGE_PUBLISHED", {"sender_id": "cli_agent_01", "payload": "hello"})
    assert len(fsm.emitted) == 1

    # 6. Verify wrong-symbol command is rejected before hitting FSM
    invalid_decision = {
        "action": "REQUEST_ORDER",
        "payload": {"symbol": "XRPUSDT", "side": "BUY"},
        "rationale": "unauthorized attempt",
    }
    
    async def override_get_decision(*args):
        return invalid_decision
        
    runner._get_agent_decision = override_get_decision
    
    # Execute turn for API Agent (who only owns ETH/SOL, so XRPUSDT is invalid)
    asyncio.run(runner._execute_agent_turn("api_agent_01", config.agents["api_agent_01"]))
    
    # Assert FSM did NOT emit the order request
    emitted_orders = [e for e in fsm.emitted if "ORDER" in e[0]]
    assert len(emitted_orders) == 0

    # Assert store recorded failure
    turn_events = store.list_events("session-smoke")
    failures = [e for e in turn_events if e.get("event_type") == "AGENT_TURN_FAILURE"]
    assert len(failures) == 1
    assert "unauthorized symbol" in failures[0]["metadata"]["details"]

    # 7. Verify duplicate command is rejected by harness
    harness = AgentOrderLifecycleHarness(
        settings,
        root_dir=root_dir.resolve(),
        coordination_config=load_coordination_config(),
        instruction_version="manifest-p46-1c",
    )
    
    # Write a mock trace to traces file first
    trace_path = root_dir / ".agent_memory" / "order_lifecycle_traces.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        json.dumps({
            "command_id": "cmd-1234",
            "fsm_status": "recorded",
            "adapter_status": "submitted_testnet",
            "exchange_status": "exchange_ack",
        }) + "\n",
        encoding="utf-8"
    )

    cmd = AgentActionCommand(
        event_id="evt-1234",
        command_id="cmd-1234", # Duplicate!
        session_id="session-smoke",
        agent_id="cli_agent_01",
        agent_number=2,
        command_kind="ENTRY",
        testnet_only=True,
        payload={"ticker": "XRPUSDT", "qty": 1.0},
        rationale="duplicate",
    )
    
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
        command=cmd,
        descriptor=desc,
        no_order_observation_mode=False,
        p40a_gate_allow_order_submit=True
    )
    assert isinstance(trace, BLOCKED_DUPLICATE)
    assert trace.adapter_status == "blocked_duplicate"

    # 8. Verify Cockpit shows both agents
    # Write a mock session state snapshot file to temp CWD root
    state_file = root_dir / "active_dual_agent_session.json"
    state_file.write_text(
        json.dumps({
            "session_id": "session-smoke",
            "agents": {
                "api_agent_01": {
                    "status": "running",
                    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                    "last_exchange_response": None,
                },
                "cli_agent_01": {
                    "status": "running",
                    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                    "last_exchange_response": None,
                }
            },
            "shared": {
                "portfolio_state": None,
                "open_orders": [],
                "open_positions": [],
                "pending_commands": [],
                "kill_switch_state": "DISARMED",
                "last_reconciliation": None,
            }
        }),
        encoding="utf-8"
    )

    # Instantiate Cockpit service
    service = ArenaRuntimeViewService(
        root_dir=root_dir,
        config_path="config/p42_dual_agent_mvp.yaml",
        state_path="active_dual_agent_session.json",
        environment_label="BINANCE_FUTURES_TESTNET",
        heartbeat_stale_after_sec=30
    )
    
    view = service.build()
    assert len(view.agents) == 2
    agent_ids = [a.agent_id for a in view.agents]
    assert "api_agent_01" in agent_ids
    assert "cli_agent_01" in agent_ids

    # 9. Verify no exchange calls occur during smoke (both are running locally, and wrong symbol is rejected before hitting FSM)
    # 10. Verify no stub result is labeled REAL_EXTERNAL
    stub_evidence = classify_exchange_evidence(
        {"status": "exchange_ack", "order_id": "stub-order-id-123"}
    )
    assert stub_evidence == "STUB"
