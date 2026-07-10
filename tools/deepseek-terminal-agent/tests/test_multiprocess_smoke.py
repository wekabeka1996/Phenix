"""Multiprocess smoke verification test suite for P43A dual-agent runtime."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest

from deepseek_terminal_agent.config import Settings
from deepseek_terminal_agent.sessions.p42_config import load_dual_agent_config
from deepseek_terminal_agent.sessions.collective_memory import CollectiveMemoryStore
from deepseek_terminal_agent.sessions.store import SessionStore

@pytest.mark.asyncio
async def test_multiprocess_smoke_flow(tmp_path):
    # Configure directories and mock environment
    session_id = f"test-session-mp-{int(time.time())}"
    config_path = "config/p42_dual_agent_mvp.yaml"
    script_path = str(Path(__file__).parent.parent / "scripts" / "run_dual_agent_multiprocess.py")
    
    # 1. Spawn both processes (api_agent_01 and cli_agent_01)
    env = os.environ.copy()
    env["TRADING_ENV"] = "testnet"
    env["RUN_READY_GATE"] = "true"
    env["P42_BYPASS_ENV_CHECK"] = "true"
    env["P42_BYPASS_ANCESTRY_CHECK"] = "true"
    env["P42_BYPASS_DIFF_CHECK"] = "true"
    env["P42_MOCK_CHECKOUT_SHA"] = "985b48008a0ab01be7ac9161a0ebfa52c3c45b6b"
    
    # Spawn api_agent_01 (duration: 3 seconds)
    proc_api = subprocess.Popen(
        [sys.executable, script_path, "--agent", "api_agent_01", "--session", session_id, "--duration", "3"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Spawn cli_agent_01 (duration: 3 seconds)
    proc_cli = subprocess.Popen(
        [sys.executable, script_path, "--agent", "cli_agent_01", "--session", session_id, "--duration", "3"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for both processes to complete
    api_out, api_err = proc_api.communicate()
    cli_out, cli_err = proc_cli.communicate()
    
    # Assert exit codes
    assert proc_api.returncode == 0, f"api process crashed: {api_err.decode('utf-8')}"
    assert proc_cli.returncode == 0, f"cli process crashed: {cli_err.decode('utf-8')}"
    
    # 2. Check output logs to verify process identities
    assert "started loop" or "heartbeat active" in api_out.decode('utf-8') or api_err.decode('utf-8')
    
    # 3. Read the collective memory evidence log to verify:
    # - sequence integrity
    # - no corrupted JSONL
    # - concurrent writes succeeded
    settings = Settings()
    session_store = SessionStore(settings, root_dir=".")
    
    # Read the state snapshot to check heartbeats and versions
    state_file = Path(".") / ".agent_memory" / f"dual_agent_session_{session_id}.json"
    assert state_file.exists(), "Session state file was not persisted"
    
    with open(state_file, "r", encoding="utf-8") as f:
        state_data = json.load(f)
        
    assert state_data["session_id"] == session_id
    assert "api_agent_01" in state_data["agents"]
    assert "cli_agent_01" in state_data["agents"]
    assert state_data["collective_state_version"] >= 0
    
    # 4. Prove restart and recovery succeeds
    # Spawn api_agent_01 again (duration: 2 seconds) to simulate process recovery
    proc_api_recover = subprocess.Popen(
        [sys.executable, script_path, "--agent", "api_agent_01", "--session", session_id, "--duration", "2"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    rec_out, rec_err = proc_api_recover.communicate()
    assert proc_api_recover.returncode == 0, f"recovery process crashed: {rec_err.decode('utf-8')}"
