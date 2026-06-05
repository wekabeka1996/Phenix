"""Bounded subagent manager with isolated child sessions and evidence artifacts."""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..config import Settings
from ..deepseek_client import DeepSeekClient
from ..terminal_tool import TOOL_SCHEMA, TerminalExecutor
from .artifacts import ArtifactStore
from .models import ArtifactFinding, ArtifactRecord, ModelProfile, utc_now_iso
from .store import SessionStore
from .tool_policy import PolicyEnforcedExecutor, ToolPolicyName


@dataclass
class _SubAgentState:
    child_run_id: str
    parent_session_id: str
    child_session_id: str
    role: str
    task: str
    model_profile: ModelProfile
    tool_policy: ToolPolicyName
    timeout_sec: int
    max_output_chars: int
    max_context_chars: int
    context_pack: str
    status: str = "queued"
    created_at: str = field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    artifact_id: Optional[str] = None
    error: Optional[str] = None
    commands_run: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    depth: int = 0


class SubAgentManager:
    def __init__(
        self,
        settings: Settings,
        *,
        session_store: SessionStore,
        artifact_store: ArtifactStore,
        root_dir: str = ".",
        worker_factory: Optional[Callable[[
            dict[str, Any], str, threading.Event, PolicyEnforcedExecutor], ArtifactRecord]] = None,
        executor_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.settings = settings
        self.session_store = session_store
        self.artifact_store = artifact_store
        self.root_dir = root_dir
        self.worker_factory = worker_factory
        self.executor_factory = executor_factory or self._default_executor_factory
        self._states: dict[str, _SubAgentState] = {}
        self._lock = threading.RLock()

    def spawn_subagent(
        self,
        *,
        parent_session_id: str,
        role: str,
        task: str,
        model_profile: ModelProfile,
        tool_policy: ToolPolicyName,
        context_pack: str,
        timeout_sec: Optional[int] = None,
        max_output_chars: Optional[int] = None,
        max_context_chars: Optional[int] = None,
    ) -> dict[str, Any]:
        if not self.settings.subagents.enabled:
            raise ValueError("Subagents are disabled in config.")
        if tool_policy == "none" and model_profile.tool_mode == "required":
            raise ValueError(
                "tool_policy='none' is incompatible with model_profile.tool_mode='required'")
        if len(context_pack) > (max_context_chars or model_profile.context_budget_chars):
            raise ValueError(
                "context_pack exceeds the requested max_context_chars")

        parent_session = self.session_store.get_session(parent_session_id)
        depth = int(parent_session.metadata.get("subagent_depth", 0)) + 1
        if depth > self.settings.subagents.max_depth:
            raise ValueError("subagent max_depth exceeded")
        if self._active_subagent_count() >= self.settings.subagents.max_concurrent:
            raise ValueError("subagent max_concurrent limit reached")

        child_session = self.session_store.create_session(
            title=f"{role}: {task[:60]}", default_profile=model_profile)
        child_session.metadata.update(
            {
                "parent_session_id": parent_session_id,
                "subagent_role": role,
                "subagent_depth": depth,
            }
        )
        self.session_store.save_session(child_session)

        state = _SubAgentState(
            child_run_id=uuid.uuid4().hex,
            parent_session_id=parent_session_id,
            child_session_id=child_session.session_id,
            role=role,
            task=task,
            model_profile=model_profile,
            tool_policy=tool_policy,
            timeout_sec=timeout_sec or self.settings.subagents.default_timeout_sec,
            max_output_chars=max_output_chars or model_profile.max_command_output_chars,
            max_context_chars=max_context_chars or model_profile.context_budget_chars,
            context_pack=context_pack,
            depth=depth,
        )
        state.thread = threading.Thread(
            target=self._run_subagent, args=(state,), daemon=True)
        with self._lock:
            self._states[state.child_run_id] = state
        state.thread.start()
        return self.get_subagent(state.child_run_id)

    def list_subagents(self, parent_session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            states = [state for state in self._states.values(
            ) if state.parent_session_id == parent_session_id]
        states.sort(key=lambda item: item.created_at, reverse=True)
        return [self._serialize_state(state) for state in states]

    def get_subagent(self, child_run_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._states[child_run_id]
        return self._serialize_state(state)

    def wait_for_completion(
        self,
        child_run_id: str,
        *,
        timeout_sec: Optional[float] = None,
        poll_interval_sec: float = 0.05,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec if timeout_sec is not None else None
        while True:
            state = self.get_subagent(child_run_id)
            if state["status"] in {"completed", "failed", "cancelled", "timed_out"}:
                return state
            if deadline is not None and time.monotonic() >= deadline:
                return state
            time.sleep(poll_interval_sec)

    def cancel_subagent(self, child_run_id: str) -> bool:
        with self._lock:
            state = self._states[child_run_id]
        if state.status in {"completed", "failed", "cancelled", "timed_out"}:
            return False
        state.cancel_event.set()
        state.events.append({"ts": utc_now_iso(
        ), "type": "cancel_requested", "message": "Cancellation requested"})
        return True

    def get_artifact(self, child_run_id: str) -> Optional[ArtifactRecord]:
        with self._lock:
            state = self._states[child_run_id]
        if not state.artifact_id:
            return None
        return self.artifact_store.get_artifact(state.artifact_id)

    def attach_artifact_to_session(self, parent_session_id: str, artifact_id: str):
        session = self.session_store.get_session(parent_session_id)
        attached = list(session.metadata.get("attached_artifact_ids", []))
        if artifact_id not in attached:
            attached.append(artifact_id)
        session.metadata["attached_artifact_ids"] = attached
        return self.session_store.save_session(session)

    def _run_subagent(self, state: _SubAgentState) -> None:
        state.status = "running"
        state.started_at = utc_now_iso()
        state.events.append(
            {"ts": state.started_at, "type": "status", "message": "Running"})
        executor = PolicyEnforcedExecutor(
            self.executor_factory(), state.tool_policy)

        result_holder: dict[str, Any] = {}

        def invoke_worker() -> None:
            try:
                worker = self.worker_factory or self._default_worker
                result_holder["artifact"] = worker(self._serialize_state(
                    state), state.context_pack, state.cancel_event, executor)
            except Exception as exc:  # noqa: BLE001
                result_holder["error"] = str(exc)

        worker_thread = threading.Thread(target=invoke_worker, daemon=True)
        worker_thread.start()
        worker_thread.join(state.timeout_sec)

        if worker_thread.is_alive():
            state.cancel_event.set()
            state.status = "timed_out"
            state.error = "Subagent timed out"
            state.finished_at = utc_now_iso()
            state.events.append(
                {"ts": state.finished_at, "type": "error", "message": state.error})
            return
        if state.cancel_event.is_set() and "artifact" not in result_holder:
            state.status = "cancelled"
            state.finished_at = utc_now_iso()
            state.events.append(
                {"ts": state.finished_at, "type": "status", "message": "Cancelled"})
            return
        if "error" in result_holder:
            state.status = "failed"
            state.error = result_holder["error"]
            state.finished_at = utc_now_iso()
            state.events.append(
                {"ts": state.finished_at, "type": "error", "message": state.error})
            return

        artifact = result_holder.get("artifact")
        if not isinstance(artifact, ArtifactRecord):
            state.status = "failed"
            state.error = "Subagent finished without an artifact"
            state.finished_at = utc_now_iso()
            state.events.append(
                {"ts": state.finished_at, "type": "error", "message": state.error})
            return

        artifact.commands_run = [
            entry.get("cmd", "") for entry in executor.command_log if entry.get("cmd")]
        state.commands_run = artifact.commands_run
        self.artifact_store.write_artifact(artifact)
        state.artifact_id = artifact.artifact_id
        state.status = "completed"
        state.finished_at = utc_now_iso()
        state.events.append(
            {"ts": state.finished_at, "type": "artifact", "message": artifact.summary})

    def _default_worker(
        self,
        state: dict[str, Any],
        context_pack: str,
        cancel_event: threading.Event,
        executor: PolicyEnforcedExecutor,
    ) -> ArtifactRecord:
        model_profile = ModelProfile(**state["model_profile_snapshot"])
        client = DeepSeekClient(self.settings.deepseek)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"You are {state['role']}. Stay within tool policy {state['tool_policy']}. "
                    "Produce only JSON matching the evidence artifact schema. Do not write code or expose reasoning."
                ),
            },
            {
                "role": "user",
                "content": f"Task: {state['task']}\n\nContext Pack:\n{context_pack}",
            },
        ]

        tools = None if state["tool_policy"] == "none" else [TOOL_SCHEMA]
        for iteration in range(model_profile.max_iterations):
            if cancel_event.is_set():
                raise RuntimeError("cancelled")
            active_tools = tools if iteration < model_profile.max_iterations - 1 else None
            response = client.chat_completions(
                messages=messages, model_profile=model_profile, tools=active_tools)
            choice = response.choices[0]
            message = choice.message
            assistant_payload = {"role": "assistant",
                                 "content": message.content or ""}
            if getattr(message, "tool_calls", None):
                assistant_payload["tool_calls"] = []
                tool_messages: list[dict[str, Any]] = []
                for tool_call in message.tool_calls:
                    arguments = json.loads(tool_call.function.arguments)
                    result = executor.execute(
                        cmd=arguments.get("cmd", ""),
                        cwd=arguments.get("cwd"),
                        timeout_sec=arguments.get("timeout_sec"),
                    )
                    assistant_payload["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                    )
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result),
                        }
                    )
                messages.append(assistant_payload)
                messages.extend(tool_messages)
                continue
            return self._coerce_artifact(state, message.content or "")

        raise RuntimeError(
            "subagent reached max_iterations without final artifact")

    def _coerce_artifact(self, state: dict[str, Any], content: str) -> ArtifactRecord:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {
                "summary": "Subagent output was not valid JSON; treat as untrusted summary only.",
                "findings": [],
                "risks": ["invalid_json_output"],
                "open_questions": ["Why did the model not follow the artifact schema?"],
                "recommended_next_context": [],
                "commands_run": [],
                "files_read": [],
            }
        findings = [
            ArtifactFinding(
                claim=str(item.get("claim") or ""),
                evidence_refs=[str(ref)
                               for ref in item.get("evidence_refs", [])],
                confidence=float(item.get("confidence", 0.0)),
            )
            for item in payload.get("findings", [])
            if str(item.get("claim") or "").strip()
        ]
        if not findings:
            findings = [ArtifactFinding(claim=str(payload.get(
                "summary") or "No findings produced"), evidence_refs=[], confidence=0.0)]
        return ArtifactRecord(
            artifact_id=uuid.uuid4().hex,
            artifact_type=payload.get("artifact_type") or "evidence_pack",
            parent_session_id=state["parent_session_id"],
            child_session_id=state["child_session_id"],
            role=state["role"],
            task=state["task"],
            summary=str(payload.get("summary")
                        or "Subagent summary unavailable"),
            findings=findings,
            files_read=[str(path) for path in payload.get("files_read", [])],
            commands_run=[str(cmd) for cmd in payload.get("commands_run", [])],
            risks=[str(item) for item in payload.get("risks", [])],
            open_questions=[str(item)
                            for item in payload.get("open_questions", [])],
            recommended_next_context=[str(item) for item in payload.get(
                "recommended_next_context", [])],
            trusted=False,
        )

    def _default_executor_factory(self) -> TerminalExecutor:
        return TerminalExecutor(
            workspace_root=self.settings.terminal.workspace_root,
            default_timeout_sec=self.settings.terminal.default_timeout_sec,
            max_output_chars=self.settings.terminal.max_output_chars,
            require_approval_for_dangerous=False,
            interactive=False,
            dry_run=False,
        )

    def _active_subagent_count(self) -> int:
        with self._lock:
            return sum(1 for state in self._states.values() if state.status in {"queued", "running"})

    @staticmethod
    def _serialize_state(state: _SubAgentState) -> dict[str, Any]:
        return {
            "child_run_id": state.child_run_id,
            "parent_session_id": state.parent_session_id,
            "child_session_id": state.child_session_id,
            "role": state.role,
            "task": state.task,
            "model_profile_snapshot": state.model_profile.snapshot(),
            "tool_policy": state.tool_policy,
            "timeout_sec": state.timeout_sec,
            "max_output_chars": state.max_output_chars,
            "max_context_chars": state.max_context_chars,
            "status": state.status,
            "created_at": state.created_at,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "artifact_id": state.artifact_id,
            "error": state.error,
            "commands_run": list(state.commands_run),
            "files_read": list(state.files_read),
            "events": list(state.events),
            "depth": state.depth,
        }
