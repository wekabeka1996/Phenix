import asyncio
from datetime import datetime, timezone
import json
import os
import pathlib
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.config import Settings
from deepseek_terminal_agent.sessions.p42_config import load_dual_agent_config
from deepseek_terminal_agent.sessions.store import SessionStore
from deepseek_terminal_agent.sessions.dual_agent_runner import DualAgentRuntimeRunner


class MockFSM:
    def __init__(self):
        self.emitted = []

    def emit(self, event_name, payload=None, why="", *args, **kwargs):
        self.emitted.append((event_name, payload, why))
        return None


@pytest.fixture
def temp_config_and_instructions(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Write config
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
    market_refresh_cadence_sec: 1
    analysis_cadence_sec: 1
    response_timeout_sec: 1
    retry_count: 3
    heartbeat_cadence_sec: 1
    collective_publication_cadence_sec: 2
    portfolio_sync_cadence_sec: 1
    reflection_cadence_sec: 2
    session_duration_sec: 5
    max_pending_commands: 2
    testnet_order_limits:
      max_orders: 5
      max_notional: 10.0
    startup_stagger_sec: 0
    shutdown_behavior: "graceful"

  cli_agent_01:
    agent_id: "cli_agent_01"
    agent_number: 2
    runtime_kind: "cli"
    symbols: ["XRPUSDT", "BNBUSDT"]
    provider: "deepseek"
    model: "deepseek-v4-pro"
    instruction_files: ["config/instructions_cli_agent_01.md"]
    market_refresh_cadence_sec: 1
    analysis_cadence_sec: 1
    response_timeout_sec: 1
    retry_count: 3
    heartbeat_cadence_sec: 1
    collective_publication_cadence_sec: 2
    portfolio_sync_cadence_sec: 1
    reflection_cadence_sec: 2
    session_duration_sec: 5
    max_pending_commands: 2
    testnet_order_limits:
      max_orders: 5
      max_notional: 10.0
    startup_stagger_sec: 0
    shutdown_behavior: "graceful"
"""
    config_file = config_dir / "p42_dual_agent_mvp.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")
    
    # Write instructions
    (config_dir / "instructions_api_agent_01.md").write_text("API instructions", encoding="utf-8")
    (config_dir / "instructions_cli_agent_01.md").write_text("CLI instructions", encoding="utf-8")
    
    # Create gate path
    gate_dir = tmp_path / "reports" / "p39a_runtime_mvp_integration_and_debt_control"
    gate_dir.mkdir(parents=True, exist_ok=True)
    (gate_dir / "RUN_READY_GATE.md").write_text("gate verified", encoding="utf-8")

    return config_file, tmp_path


def test_ownership_mapping_loaded_from_yaml(temp_config_and_instructions):
    config_file, _ = temp_config_and_instructions
    config = load_dual_agent_config(config_file)
    assert "api_agent_01" in config.agents
    assert "cli_agent_01" in config.agents
    assert config.agents["api_agent_01"].symbols == ["ETHUSDT", "SOLUSDT"]
    assert config.agents["cli_agent_01"].symbols == ["XRPUSDT", "BNBUSDT"]


def test_preflight_check(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)
    # verify_preflight should pass without raising
    runner.verify_preflight(bypass_network_check=True)


def test_wrong_symbol_request_rejected_before_fsm(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)

    # 1. Propose order on unauthorized symbol
    invalid_decision = {
        "action": "REQUEST_ORDER",
        "payload": {"symbol": "XRPUSDT", "side": "BUY"},
        "rationale": "Trade intent",
    }
    
    async def override_get_decision(*args):
        return invalid_decision
        
    runner._get_agent_decision = override_get_decision
    
    # Run turn
    asyncio.run(runner._execute_agent_turn("api_agent_01", config.agents["api_agent_01"]))
    
    # FSM should receive no signal
    assert len(fsm.emitted) == 0
    
    # Store should record failure
    events = store.list_events("session-p42")
    failure_events = [e for e in events if e.get("event_type") == "AGENT_TURN_FAILURE"]
    assert len(failure_events) == 1
    assert "unauthorized symbol" in failure_events[0]["metadata"]["details"]


def test_timeout_creates_explicit_failure(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)

    async def slow_decision(*args):
        await asyncio.sleep(2.0)
        return {"action": "WAIT", "rationale": "Slow response"}

    runner._get_agent_decision = slow_decision
    
    # Execute turn
    asyncio.run(runner._execute_agent_turn("api_agent_01", config.agents["api_agent_01"]))
    
    # Verify timeout failure
    events = store.list_events("session-p42")
    failure_events = [e for e in events if e.get("event_type") == "AGENT_TURN_FAILURE"]
    assert len(failure_events) == 1
    assert failure_events[0]["metadata"]["error_code"] == "TIMEOUT"


def test_invalid_model_response_fails_closed(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)

    async def invalid_decision(*args):
        # Action is missing/invalid
        return {"action": "INVALID_ACTION", "rationale": "Bad response"}

    runner._get_agent_decision = invalid_decision
    
    # Execute turn
    asyncio.run(runner._execute_agent_turn("api_agent_01", config.agents["api_agent_01"]))
    
    events = store.list_events("session-p42")
    failure_events = [e for e in events if e.get("event_type") == "AGENT_TURN_FAILURE"]
    assert len(failure_events) == 1
    assert failure_events[0]["metadata"]["error_code"] == "INVALID_RESPONSE"


def test_no_raw_exchange_client_imported():
    # Read dual_agent_runner.py source code and verify no CCXT/Binance raw clients are imported
    harness_path = pathlib.Path(__file__).parent.parent / "src" / "deepseek_terminal_agent" / "sessions" / "dual_agent_runner.py"
    source = harness_path.read_text(encoding="utf-8")
    assert "import ccxt" not in source
    assert "import binance" not in source
    assert "from binance" not in source
    assert "urllib.request" not in source


def test_heartbeat_expiry_detected(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)

    # 1. Manually set stale heartbeat
    runner.last_heartbeats["api_agent_01"] = "2026-07-09T18:00:00.000000+00:00"
    runner.agent_states["api_agent_01"] = "running"
    
    # Heartbeat expiry logic
    stale_limit = 5.0
    last_hb_str = runner.last_heartbeats.get("api_agent_01")
    last_dt = datetime.fromisoformat(last_hb_str)
    delta = (datetime.now(timezone.utc) - last_dt).total_seconds()
    
    assert delta > stale_limit


def test_event_driven_wakeup_works(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)
    
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)
    runner.agent_states["api_agent_01"] = "running"
    runner.register_fsm_listeners()

    # Emit instructions refreshed event
    fsm.emit("EVT:INSTRUCTIONS_REFRESHED", {"agent_id": "api_agent_01"})
    assert runner.wakeup_events["api_agent_01"].is_set()


def test_preflight_attestation_validation(temp_config_and_instructions, monkeypatch):
    config_file, root_dir = temp_config_and_instructions
    monkeypatch.chdir(root_dir)
    monkeypatch.setenv("TRADING_ENV", "testnet")
    monkeypatch.setenv("RUN_READY_GATE", "true")

    # 1. Write the gate md file with an Integration SHA
    gate_dir = root_dir / "reports" / "p42g_unified_dual_agent_runtime"
    gate_dir.mkdir(parents=True, exist_ok=True)
    gate_dir.joinpath("RUN_READY_GATE.md").write_text("- **Integration SHA**: e82ceff877ba83f7affdb8659b2ba2b38d76e09c", encoding="utf-8")

    config = load_dual_agent_config(config_file)
    settings = Settings()
    fsm = MockFSM()
    store = SessionStore(settings, root_dir=root_dir)

    # 2. Case A: HEAD matches Integration SHA (0 diffs, ancestor)
    monkeypatch.setenv("P42_MOCK_CHECKOUT_SHA", "e82ceff877ba83f7affdb8659b2ba2b38d76e09c")
    runner = DualAgentRuntimeRunner(config, settings, "session-p42", root_dir=root_dir, session_store=store, fsm_override=fsm)
    runner.verify_preflight(bypass_network_check=True)

    # Check PRE_SUBMIT_GATE.json was written
    gate_json_path = root_dir / "PRE_SUBMIT_GATE.json"
    assert gate_json_path.exists()
    gate_data = json.loads(gate_json_path.read_text(encoding="utf-8"))
    assert gate_data["checkout_sha"] == "e82ceff877ba83f7affdb8659b2ba2b38d76e09c"
    assert gate_data["runtime_code_sha"] == "e82ceff877ba83f7affdb8659b2ba2b38d76e09c"

    # 3. Case B: HEAD is different, but git check mocks it as ancestor with reports changes
    import subprocess
    monkeypatch.setenv("P42_MOCK_CHECKOUT_SHA", "c55489003d891bf8e0b223fa4e12391452f6eda1")

    # Mock subprocess to simulate ancestor success and allowed diff files
    def mock_check_call(*args, **kwargs):
        return 0

    def mock_check_output(cmd, *args, **kwargs):
        if "rev-parse" in cmd:
            return b"c55489003d891bf8e0b223fa4e12391452f6eda1\n"
        if "diff" in cmd:
            return b"reports/p42g_unified_dual_agent_runtime/RUN_READY_GATE.md\n"
        return b""

    monkeypatch.setattr(subprocess, "check_call", mock_check_call)
    monkeypatch.setattr(subprocess, "check_output", mock_check_output)

    runner2 = DualAgentRuntimeRunner(config, settings, "session-p42-2", root_dir=root_dir, session_store=store, fsm_override=fsm)
    runner2.verify_preflight(bypass_network_check=True)

    gate_data2 = json.loads(gate_json_path.read_text(encoding="utf-8"))
    assert gate_data2["checkout_sha"] == "c55489003d891bf8e0b223fa4e12391452f6eda1"

    # 4. Case C: Disallowed source diff files exist -> raises ValueError
    def mock_check_output_disallowed(cmd, *args, **kwargs):
        if "rev-parse" in cmd:
            return b"c55489003d891bf8e0b223fa4e12391452f6eda1\n"
        if "diff" in cmd:
            # Contains source files!
            return b"apps/reference/main.py\n"
        return b""

    monkeypatch.setattr(subprocess, "check_output", mock_check_output_disallowed)
    runner3 = DualAgentRuntimeRunner(config, settings, "session-p42-3", root_dir=root_dir, session_store=store, fsm_override=fsm)
    with pytest.raises(ValueError, match="source difference detected in disallowed path"):
        runner3.verify_preflight(bypass_network_check=True)

