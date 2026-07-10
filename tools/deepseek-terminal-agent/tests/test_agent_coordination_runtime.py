"""Scheduler and registered tool contract tests for P41X."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.agent_tool_runtime import AgentToolRuntime
from deepseek_terminal_agent.sessions.collective_memory import CollectiveMemoryStore
from deepseek_terminal_agent.sessions.coordination_config import load_coordination_config
from deepseek_terminal_agent.sessions.coordination_scheduler import CoordinationScheduler
from deepseek_terminal_agent.sessions.models import ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(deepseek=DeepSeekConfig(api_key="test-key"))
    sessions = SessionStore(settings, root_dir=tmp_path)
    profile = ModelProfile(profile_id="p41x", name="P41X", model_id="deepseek-v4-pro")
    session = sessions.create_session(default_profile=profile)
    config = load_coordination_config()
    store = CollectiveMemoryStore(settings, root_dir=tmp_path, config=config, session_store=sessions)
    store.initialize_session(session.session_id)
    return AgentToolRuntime(config, store), CoordinationScheduler(config, store), store, session.session_id


def test_all_registered_tools_have_explicit_contracts(runtime):
    tools, _, _, _ = runtime
    contracts = tools.contracts()
    assert len(contracts) == 15
    assert {item.tool_name for item in contracts} == set(tools.config.tool_permissions)
    assert all(item.input_schema and item.output_schema for item in contracts)
    assert all(item.timeout_seconds > 0 for item in contracts)
    assert all(item.audit_fields and item.failure_classes for item in contracts)


def test_tool_runtime_records_typed_command_and_rejects_raw_or_wrong_symbol(runtime):
    tools, _, store, session_id = runtime
    result = tools.invoke(
        "REQUEST_ORDER",
        {
            "session_id": session_id,
            "agent_id": "api_agent_01",
            "agent_number": 1,
            "symbol": "ETHUSDT",
            "rationale": "15m review supports a testnet intent",
            "intent_ref": "intent://eth/tool/1",
            "sizing_ref": "config://llm_microstructure/execution",
            "command_id": "cmd-tool-1",
            "idempotency_key": "tool-order:1",
        },
    )
    assert result.status == "pending_fsm"
    assert result.audit["raw_exchange_client_exposed"] is False
    assert store.get_state(session_id).pending_commands["cmd-tool-1"].status == "pending_fsm"

    with pytest.raises(ValueError):
        tools.invoke(
            "REQUEST_ORDER",
            {
                "session_id": session_id,
                "agent_id": "api_agent_01",
                "agent_number": 1,
                "symbol": "ETHUSDT",
                "rationale": "invalid raw payload",
                "intent_ref": "intent://bad",
                "sizing_ref": "config://llm_microstructure/execution",
                "idempotency_key": "tool-order:bad",
                "raw_order": {"quantity": 1},
            },
        )
    with pytest.raises(ValueError, match="wrong-symbol"):
        tools.invoke(
            "REQUEST_ORDER",
            {
                "session_id": session_id,
                "agent_id": "api_agent_01",
                "agent_number": 1,
                "symbol": "BNBUSDT",
                "rationale": "wrong symbol",
                "intent_ref": "intent://bad-symbol",
                "sizing_ref": "config://llm_microstructure/execution",
                "idempotency_key": "tool-order:wrong-symbol",
            },
        )


def test_scheduler_uses_yaml_cadence_and_event_wakeups(runtime):
    _, scheduler, _, _ = runtime
    now = datetime.now(timezone.utc)
    previous = {
        task: (now - timedelta(seconds=10)).isoformat()
        for task in scheduler._cadences()
    }
    decisions = scheduler.due_tasks(last_run_at=previous, now=now)
    assert not any(item.due for item in decisions)
    event_decisions = scheduler.due_tasks(
        last_run_at=previous,
        now=now,
        event_wakeup="risk_warning",
    )
    due = {item.task for item in event_decisions if item.due}
    assert due == {"collective_sync", "decision_review"}
    assert scheduler.config.timers.tactical_analysis_seconds >= 300
    assert scheduler.config.timers.decision_review_seconds >= 900


def test_agent_tool_module_has_no_raw_exchange_client_import():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "deepseek_terminal_agent"
        / "sessions"
        / "agent_tool_runtime.py"
    ).read_text(encoding="utf-8")
    assert "BinanceAdapter" not in source
    assert "ExchangeACL" not in source
    assert "httpx" not in source
    assert "requests." not in source
