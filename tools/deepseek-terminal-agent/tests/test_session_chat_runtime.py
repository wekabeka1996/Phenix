"""Tests for the session-first chat runtime."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.artifacts import ArtifactStore
from deepseek_terminal_agent.sessions.chat_runtime import SessionChatRuntime
from deepseek_terminal_agent.sessions.context_builder import ContextBuilder
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtomStore
from deepseek_terminal_agent.sessions.models import ArtifactFinding, ArtifactRecord, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore
from deepseek_terminal_agent.sessions.task_router import SuggestedSubagent, TaskRouteDecision


class FakeExecutor:
    def execute(self, cmd, cwd=None, timeout_sec=None):
        return {
            "ok": True,
            "cmd": cmd,
            "cwd": cwd,
            "exit_code": 0,
            "stdout": "/workspace/project\n",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
            "output_truncated": False,
        }


class FakeSubagentManager:
    def __init__(self, store: SessionStore, artifact_store: ArtifactStore) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.spawn_calls: list[dict[str, str]] = []
        self.states: dict[str, dict[str, str]] = {}
        self.artifacts: dict[str, ArtifactRecord] = {}

    def spawn_subagent(self, **kwargs):
        self.spawn_calls.append(kwargs)
        child_run_id = f"run-{len(self.spawn_calls)}"
        artifact = ArtifactRecord(
            artifact_id=f"artifact-{len(self.spawn_calls)}",
            artifact_type="evidence_pack",
            parent_session_id=kwargs["parent_session_id"],
            child_session_id="child-session",
            role=kwargs["role"],
            task=kwargs["task"],
            summary="Scout found dashboard evidence.",
            findings=[
                ArtifactFinding(
                    claim="/chat is the session-first workbench.",
                    evidence_refs=["path:README.md"],
                    confidence=0.8,
                )
            ],
            trusted=False,
        )
        self.artifact_store.write_artifact(artifact)
        self.artifacts[child_run_id] = artifact
        self.states[child_run_id] = {
            "child_run_id": child_run_id,
            "status": "completed",
            "artifact_id": artifact.artifact_id,
            "error": None,
        }
        return dict(self.states[child_run_id])

    def wait_for_completion(self, child_run_id: str, **kwargs):
        return dict(self.states[child_run_id])

    def get_artifact(self, child_run_id: str):
        return self.artifacts[child_run_id]

    def attach_artifact_to_session(self, parent_session_id: str, artifact_id: str):
        session = self.store.get_session(parent_session_id)
        attached = list(session.metadata.get("attached_artifact_ids", []))
        if artifact_id not in attached:
            attached.append(artifact_id)
        session.metadata["attached_artifact_ids"] = attached
        return self.store.save_session(session)


class FakeTaskRouter:
    def route(self, *, user_message: str) -> TaskRouteDecision:
        return TaskRouteDecision(
            task_type="repo_search",
            route="orchestrated",
            reason="Repository evidence should be gathered first.",
            suggested_subagents=[
                SuggestedSubagent(
                    role="ScoutAgent",
                    task=f"Search for evidence: {user_message}",
                    tool_policy="read_only",
                    profile_strategy="flash_scout",
                    reason="Collect evidence before the parent answer.",
                )
            ],
        )


def make_settings() -> Settings:
    settings = Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))
    settings.agent.system_prompt_path = "missing-system-prompt.md"
    return settings


def make_profile() -> ModelProfile:
    return ModelProfile(
        profile_id="profile-a",
        name="Profile A",
        model_id="deepseek-v4-pro",
        thinking_type="enabled",
        reasoning_effort="high",
        temperature=0.2,
        top_p=1.0,
        max_tokens=4096,
        response_format="text",
        stream=False,
        tool_mode="auto",
        max_iterations=4,
        command_timeout_sec=30,
        max_command_output_chars=1200,
        context_budget_chars=40000,
        memory_atom_budget=4,
        recent_turns_budget=3,
        tool_output_budget_chars=1500,
    )


def make_runtime(tmp_path: Path, client) -> tuple[SessionChatRuntime, SessionStore]:
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    builder = ContextBuilder(
        settings,
        session_store=store,
        memory_store=memory,
        artifact_store=artifacts,
        root_dir=tmp_path,
    )
    runtime = SessionChatRuntime(
        settings,
        session_store=store,
        context_builder=builder,
        client=client,
        executor_factory=lambda profile: FakeExecutor(),
    )
    return runtime, store


def test_send_message_stores_user_and_final_assistant_turn(tmp_path):
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = "Final answer"
    response.choices[0].message.tool_calls = []
    response.choices[0].message.reasoning_content = "private reasoning"
    response.usage = None
    client.chat_completions.return_value = response

    runtime, store = make_runtime(tmp_path, client)
    session = store.create_session(default_profile=make_profile())

    result = runtime.send_message(
        session_id=session.session_id, user_message="Hello")
    turns = store.list_turns(session.session_id, include_internal=False)
    internal_turns = store.list_turns(
        session.session_id, include_internal=True)

    assert result["assistant_turn"]["visible_content"] == "Final answer"
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert internal_turns[1]["internal_reasoning_content"] == "private reasoning"
    assert Path(result["context_report_path"]).exists()


def test_tool_call_flow_stores_assistant_and_tool_turns(tmp_path):
    tool_call = MagicMock()
    tool_call.id = "tc-1"
    tool_call.type = "function"
    tool_call.function.name = "terminal_exec"
    tool_call.function.arguments = json.dumps({"cmd": "pwd"})

    response_one = MagicMock()
    response_one.choices = [MagicMock()]
    response_one.choices[0].finish_reason = "tool_calls"
    response_one.choices[0].message.content = "Running tool"
    response_one.choices[0].message.tool_calls = [tool_call]
    response_one.choices[0].message.reasoning_content = None
    response_one.usage = None

    response_two = MagicMock()
    response_two.choices = [MagicMock()]
    response_two.choices[0].finish_reason = "stop"
    response_two.choices[0].message.content = "Done"
    response_two.choices[0].message.tool_calls = []
    response_two.choices[0].message.reasoning_content = None
    response_two.usage = None

    client = MagicMock()
    client.chat_completions.side_effect = [response_one, response_two]

    runtime, store = make_runtime(tmp_path, client)
    session = store.create_session(default_profile=make_profile())

    result = runtime.send_message(
        session_id=session.session_id, user_message="Run pwd")
    turns = store.list_turns(session.session_id, include_internal=False)

    assert [turn["role"] for turn in turns] == [
        "user", "assistant", "tool", "assistant"]
    assert result["assistant_turn"]["visible_content"] == "Done"
    assert client.chat_completions.call_args_list[0].kwargs["tools"] is not None


def test_public_result_hides_reasoning(tmp_path):
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = "Visible answer"
    response.choices[0].message.tool_calls = []
    response.choices[0].message.reasoning_content = "hidden"
    response.usage = None
    client.chat_completions.return_value = response

    runtime, store = make_runtime(tmp_path, client)
    session = store.create_session(default_profile=make_profile())
    result = runtime.send_message(
        session_id=session.session_id, user_message="Hello")

    assert "internal_reasoning_content" not in result["assistant_turn"]
    assert "hidden" not in json.dumps(result)


def test_orchestrated_route_attaches_artifact_and_includes_it_in_context(tmp_path):
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = "Here is the evidence-backed answer."
    response.choices[0].message.tool_calls = []
    response.choices[0].message.reasoning_content = None
    response.usage = None
    client.chat_completions.return_value = response

    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    builder = ContextBuilder(
        settings,
        session_store=store,
        memory_store=memory,
        artifact_store=artifacts,
        root_dir=tmp_path,
    )
    manager = FakeSubagentManager(store, artifacts)
    runtime = SessionChatRuntime(
        settings,
        session_store=store,
        context_builder=builder,
        client=client,
        executor_factory=lambda profile: FakeExecutor(),
        subagent_manager=manager,
        task_router=FakeTaskRouter(),
    )
    session = store.create_session(default_profile=make_profile())

    result = runtime.send_message(
        session_id=session.session_id,
        user_message="Find where the dashboard is described and give an evidence pack.",
    )

    assert result["routing"]["route"] == "orchestrated"
    assert result["routing"]["artifact_ids"] == ["artifact-1"]
    assert manager.spawn_calls[0]["tool_policy"] == "read_only"

    sent_messages = client.chat_completions.call_args.kwargs["messages"]
    assert any(
        "Scout found dashboard evidence." in message["content"]
        for message in sent_messages
        if message["role"] == "system"
    )
    assert client.chat_completions.call_args.kwargs["tools"] is None

    event_types = [event["event_type"]
                   for event in store.list_events(session.session_id)]
    assert "route_decision" in event_types
    assert "subagent_completed" in event_types
