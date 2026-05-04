"""Tests for bounded subagent orchestration."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.artifacts import ArtifactStore
from deepseek_terminal_agent.sessions.models import ArtifactFinding, ArtifactRecord, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore
from deepseek_terminal_agent.sessions.subagents import SubAgentManager


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, cmd, cwd=None, timeout_sec=None):
        self.calls.append({"cmd": cmd, "cwd": cwd, "timeout_sec": timeout_sec})
        return {
            "ok": True,
            "cmd": cmd,
            "cwd": cwd,
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
            "output_truncated": False,
        }


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def make_profile(**overrides) -> ModelProfile:
    payload = {
        "profile_id": "flash-scout",
        "name": "Flash Scout",
        "model_id": "deepseek-v4-flash",
        "thinking_type": "disabled",
        "reasoning_effort": "high",
        "temperature": 0.1,
        "top_p": 1.0,
        "max_tokens": 2048,
        "response_format": "text",
        "stream": False,
        "tool_mode": "auto",
        "max_iterations": 4,
        "command_timeout_sec": 30,
        "max_command_output_chars": 1200,
        "context_budget_chars": 10000,
        "memory_atom_budget": 4,
        "recent_turns_budget": 6,
        "tool_output_budget_chars": 3000,
    }
    payload.update(overrides)
    return ModelProfile(**payload)


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_spawn_returns_child_run_id_immediately_and_isolated_child_session(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(
        title="Parent", default_profile=make_profile())

    def worker(record, context_pack, cancel_event, executor):
        return ArtifactRecord(
            artifact_id="artifact-1",
            artifact_type="evidence_pack",
            parent_session_id=record["parent_session_id"],
            child_session_id=record["child_session_id"],
            role=record["role"],
            task=record["task"],
            summary="done",
            findings=[ArtifactFinding(
                claim="ok", evidence_refs=[], confidence=0.5)],
        )

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="Inspect repo",
        model_profile=make_profile(model_id="deepseek-v4-flash"),
        tool_policy="read_only",
        context_pack="repo context",
    )

    assert state["child_run_id"]
    assert state["child_session_id"] != parent.session_id
    assert wait_until(lambda: manager.get_subagent(
        state["child_run_id"])["status"] == "completed")


def test_model_override_applied(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(default_profile=make_profile())
    seen = {}

    def worker(record, context_pack, cancel_event, executor):
        seen["model_id"] = record["model_profile_snapshot"]["model_id"]
        return ArtifactRecord(
            artifact_id="artifact-2",
            artifact_type="evidence_pack",
            parent_session_id=record["parent_session_id"],
            child_session_id=record["child_session_id"],
            role=record["role"],
            task=record["task"],
            summary="done",
            findings=[ArtifactFinding(
                claim="ok", evidence_refs=[], confidence=0.5)],
        )

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="Inspect repo",
        model_profile=make_profile(model_id="deepseek-v4-pro"),
        tool_policy="read_only",
        context_pack="repo context",
    )

    assert wait_until(lambda: manager.get_subagent(
        state["child_run_id"])["status"] == "completed")
    assert seen["model_id"] == "deepseek-v4-pro"


def test_tool_policy_read_only_enforced(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(default_profile=make_profile())

    def worker(record, context_pack, cancel_event, executor):
        blocked = executor.execute("git commit -m bad")
        return ArtifactRecord(
            artifact_id="artifact-3",
            artifact_type="evidence_pack",
            parent_session_id=record["parent_session_id"],
            child_session_id=record["child_session_id"],
            role=record["role"],
            task=record["task"],
            summary=blocked["stderr"],
            findings=[ArtifactFinding(claim="blocked", evidence_refs=[
                                      blocked["stderr"]], confidence=1.0)],
        )

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="Attempt write",
        model_profile=make_profile(),
        tool_policy="read_only",
        context_pack="repo context",
    )

    assert wait_until(lambda: manager.get_subagent(
        state["child_run_id"])["status"] == "completed")
    artifact = manager.get_artifact(state["child_run_id"])
    assert artifact is not None
    assert "read-only" in artifact.summary


def test_timeout_and_cancel_supported(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(default_profile=make_profile())

    def slow_worker(record, context_pack, cancel_event, executor):
        while not cancel_event.is_set():
            time.sleep(0.02)
        raise RuntimeError("cancelled")

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=slow_worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="Wait",
        model_profile=make_profile(),
        tool_policy="read_only",
        context_pack="repo context",
        timeout_sec=1,
    )
    assert manager.cancel_subagent(state["child_run_id"]) is True
    assert wait_until(lambda: manager.get_subagent(state["child_run_id"])[
                      "status"] in {"cancelled", "failed", "timed_out"})


def test_artifact_written_parent_attach_and_untrusted(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(default_profile=make_profile())

    def worker(record, context_pack, cancel_event, executor):
        executor.execute("pwd")
        return ArtifactRecord(
            artifact_id="artifact-4",
            artifact_type="evidence_pack",
            parent_session_id=record["parent_session_id"],
            child_session_id=record["child_session_id"],
            role=record["role"],
            task=record["task"],
            summary="evidence ready",
            findings=[ArtifactFinding(claim="pwd executed", evidence_refs=[
                                      "command:pwd"], confidence=0.8)],
            trusted=False,
        )

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="Gather evidence",
        model_profile=make_profile(),
        tool_policy="read_only",
        context_pack="repo context",
    )

    assert wait_until(lambda: manager.get_subagent(
        state["child_run_id"])["status"] == "completed")
    artifact = manager.get_artifact(state["child_run_id"])
    assert artifact is not None
    assert artifact.trusted is False
    updated_parent = manager.attach_artifact_to_session(
        parent.session_id, artifact.artifact_id)
    assert artifact.artifact_id in updated_parent.metadata["attached_artifact_ids"]


def test_no_raw_reasoning_exposed_in_public_state(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(default_profile=make_profile())

    def worker(record, context_pack, cancel_event, executor):
        return ArtifactRecord(
            artifact_id="artifact-5",
            artifact_type="summary",
            parent_session_id=record["parent_session_id"],
            child_session_id=record["child_session_id"],
            role=record["role"],
            task=record["task"],
            summary="summary only",
            findings=[ArtifactFinding(
                claim="summary only", evidence_refs=[], confidence=0.1)],
        )

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="No reasoning",
        model_profile=make_profile(),
        tool_policy="none",
        context_pack="repo context",
    )

    assert wait_until(lambda: manager.get_subagent(
        state["child_run_id"])["status"] == "completed")
    public_state = manager.get_subagent(state["child_run_id"])
    assert "reasoning_content" not in str(public_state)


def test_default_worker_emits_single_assistant_tool_call_message_for_multiple_tools(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    manager = SubAgentManager(
        settings,
        session_store=store,
        artifact_store=artifacts,
        executor_factory=lambda: FakeExecutor(),
    )
    executor = manager._default_executor_factory()
    state = {
        "parent_session_id": "parent-1",
        "child_session_id": "child-1",
        "role": "ScoutAgent",
        "task": "Inspect dashboard docs",
        "tool_policy": "read_only",
        "model_profile_snapshot": make_profile().model_dump(),
    }

    response_with_tools = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            type="function",
                            function=SimpleNamespace(
                                name="run_terminal_cmd",
                                arguments=json.dumps({"cmd": "pwd"}),
                            ),
                        ),
                        SimpleNamespace(
                            id="call-2",
                            type="function",
                            function=SimpleNamespace(
                                name="run_terminal_cmd",
                                arguments=json.dumps({"cmd": "ls"}),
                            ),
                        ),
                    ],
                )
            )
        ]
    )
    final_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "summary": "done",
                            "findings": [{"claim": "ok", "evidence_refs": [], "confidence": 0.5}],
                        }
                    ),
                    tool_calls=[],
                )
            )
        ]
    )
    client = MagicMock()
    client.chat_completions.side_effect = [response_with_tools, final_response]

    with patch("deepseek_terminal_agent.sessions.subagents.DeepSeekClient", return_value=client):
        artifact = manager._default_worker(
            state, "ctx", threading.Event(), executor)

    assert artifact.summary == "done"
    second_messages = client.chat_completions.call_args_list[1].kwargs["messages"]
    assistant_messages = [
        message for message in second_messages if message["role"] == "assistant"]
    tool_messages = [
        message for message in second_messages if message["role"] == "tool"]
    assert len(assistant_messages) == 1
    assert len(assistant_messages[0]["tool_calls"]) == 2
    assert [message["tool_call_id"]
            for message in tool_messages] == ["call-1", "call-2"]


def test_missing_artifact_fails_closed_instead_of_crashing(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    parent = store.create_session(default_profile=make_profile())

    def worker(record, context_pack, cancel_event, executor):
        return None

    manager = SubAgentManager(settings, session_store=store, artifact_store=artifacts,
                              worker_factory=worker, executor_factory=lambda: FakeExecutor())
    state = manager.spawn_subagent(
        parent_session_id=parent.session_id,
        role="ScoutAgent",
        task="Return nothing",
        model_profile=make_profile(),
        tool_policy="none",
        context_pack="repo context",
    )

    assert wait_until(lambda: manager.get_subagent(
        state["child_run_id"])["status"] == "failed")
    public_state = manager.get_subagent(state["child_run_id"])
    assert public_state["error"] == "Subagent finished without an artifact"


def test_default_worker_reserves_final_round_for_no_tool_synthesis(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    manager = SubAgentManager(
        settings,
        session_store=store,
        artifact_store=artifacts,
        executor_factory=lambda: FakeExecutor(),
    )
    executor = manager._default_executor_factory()
    state = {
        "parent_session_id": "parent-1",
        "child_session_id": "child-1",
        "role": "ScoutAgent",
        "task": "Inspect dashboard docs",
        "tool_policy": "read_only",
        "model_profile_snapshot": make_profile(max_iterations=2).model_dump(),
    }

    response_with_tools = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            type="function",
                            function=SimpleNamespace(
                                name="run_terminal_cmd",
                                arguments=json.dumps({"cmd": "pwd"}),
                            ),
                        )
                    ],
                )
            )
        ]
    )
    final_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "summary": "done",
                            "findings": [{"claim": "ok", "evidence_refs": [], "confidence": 0.5}],
                        }
                    ),
                    tool_calls=[],
                )
            )
        ]
    )
    client = MagicMock()
    client.chat_completions.side_effect = [response_with_tools, final_response]

    with patch("deepseek_terminal_agent.sessions.subagents.DeepSeekClient", return_value=client):
        artifact = manager._default_worker(
            state, "ctx", threading.Event(), executor)

    assert artifact.summary == "done"
    assert client.chat_completions.call_args_list[0].kwargs["tools"] is not None
    assert client.chat_completions.call_args_list[1].kwargs["tools"] is None
