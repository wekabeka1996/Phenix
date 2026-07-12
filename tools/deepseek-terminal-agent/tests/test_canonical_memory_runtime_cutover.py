from __future__ import annotations

from pathlib import Path

import pytest

from deepseek_terminal_agent.sessions.canonical_memory_runtime import (
    CanonicalMemoryRuntime,
)
from deepseek_terminal_agent.sessions.collective_memory import (
    CanonicalMemoryStore,
    DuplicateMemoryRecordError,
)
from deepseek_terminal_agent.sessions.coordination_config import (
    load_coordination_config,
)


def _runtime(tmp_path: Path) -> CanonicalMemoryRuntime:
    return CanonicalMemoryRuntime(
        store=CanonicalMemoryStore(
            storage_root=tmp_path.resolve(),
            config=load_coordination_config(),
        )
    )


def _append_rationale(
    runtime: CanonicalMemoryRuntime,
    *,
    session_id: str = "session-1",
    agent_id: str = "api_agent_01",
    agent_number: int = 1,
    event_id: str = "event-1",
    command_id: str = "command-1",
    rationale: str = "30m rationale",
) -> dict:
    return runtime.append_rationale_event(
        session_id=session_id,
        agent_id=agent_id,
        agent_number=agent_number,
        event_id=event_id,
        command_id=command_id,
        rationale=rationale,
        instruction_version="manifest-v1",
        created_at="2026-07-12T00:00:00+00:00",
    )


def test_restart_recovery_and_append_continue_without_loss(tmp_path: Path) -> None:
    first = _runtime(tmp_path)
    _append_rationale(first)
    first.append_instruction_ack(
        session_id="session-1",
        agent_id="api_agent_01",
        agent_number=1,
        event_id="event-2",
        instruction_version="manifest-v2",
        created_at="2026-07-12T00:01:00+00:00",
    )
    expected = first.read_memory(
        session_id="session-1", agent_id="api_agent_01", agent_number=1
    )

    reopened = _runtime(tmp_path)
    assert reopened.read_memory(
        session_id="session-1", agent_id="api_agent_01", agent_number=1
    ) == expected
    assert reopened.finalize_session(
        session_id="session-1", agent_id="api_agent_01", agent_number=1
    ) == reopened.finalize_session(
        session_id="session-1", agent_id="api_agent_01", agent_number=1
    )
    reopened.append_fsm_decision(
        session_id="session-1",
        agent_id="api_agent_01",
        agent_number=1,
        event_id="event-3",
        command_id="command-3",
        accepted=False,
        reason="SSOT sizing unavailable",
        instruction_version="manifest-v2",
        created_at="2026-07-12T00:02:00+00:00",
    )
    assert len(reopened.store.read("session-1")) == 3


def test_identical_runtime_append_is_suppressed_but_conflict_fails(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    first = _append_rationale(runtime)
    assert _append_rationale(runtime) == first
    assert len(runtime.store.read("session-1")) == 1

    with pytest.raises(DuplicateMemoryRecordError):
        _append_rationale(runtime, rationale="conflicting rationale")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_id", ""),
        ("agent_id", ""),
        ("instruction_version", ""),
        ("created_at", ""),
    ],
)
def test_required_runtime_identity_fields_fail_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    kwargs = {
        "session_id": "session-1",
        "agent_id": "api_agent_01",
        "agent_number": 1,
        "event_id": "event-1",
        "command_id": "command-1",
        "rationale": "rationale",
        "instruction_version": "manifest-v1",
        "created_at": "2026-07-12T00:00:00+00:00",
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=field):
        _runtime(tmp_path).append_rationale_event(**kwargs)


def test_agents_and_sessions_do_not_share_private_views(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    _append_rationale(runtime)
    _append_rationale(
        runtime,
        agent_id="cli_agent_01",
        agent_number=2,
        event_id="event-2",
        command_id="command-2",
    )
    _append_rationale(
        runtime,
        session_id="session-2",
        event_id="event-3",
        command_id="command-3",
    )

    api_view = runtime.read_memory(
        session_id="session-1", agent_id="api_agent_01", agent_number=1
    )
    cli_view = runtime.read_memory(
        session_id="session-1", agent_id="cli_agent_01", agent_number=2
    )
    other_session = runtime.read_memory(
        session_id="session-2", agent_id="api_agent_01", agent_number=1
    )
    assert [row["event_ids"] for row in api_view["records"]] == [["event-1"]]
    assert [row["event_ids"] for row in cli_view["records"]] == [["event-2"]]
    assert [row["event_ids"] for row in other_session["records"]] == [["event-3"]]


def test_append_failure_has_no_legacy_fallback(tmp_path: Path, monkeypatch) -> None:
    runtime = _runtime(tmp_path)

    def fail_append(record):
        raise OSError("injected canonical append failure")

    monkeypatch.setattr(runtime.store, "append", fail_append)
    with pytest.raises(OSError, match="injected"):
        _append_rationale(runtime)

    assert not list(tmp_path.rglob("agent_trading_memory.json"))
    assert not list(tmp_path.rglob("agent_trading_memory.summary.json"))
    assert not list(tmp_path.rglob("agent_trading_session_carryover.md"))


def test_active_runtime_sources_do_not_construct_legacy_writer() -> None:
    project = Path(__file__).resolve().parents[1]
    active_sources = [
        project / "src/deepseek_terminal_agent/dashboard/app.py",
        project / "src/deepseek_terminal_agent/sessions/agent_order_lifecycle_harness.py",
        project / "src/deepseek_terminal_agent/sessions/canonical_memory_runtime.py",
    ]
    for path in active_sources:
        text = path.read_text(encoding="utf-8")
        assert "AgentMemoryLifecycle(" not in text
        assert "agent_trading_memory.json" not in text
