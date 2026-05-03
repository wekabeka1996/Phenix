"""Session-first chat runtime that assembles context locally per turn."""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Optional

from ..config import Settings
from ..deepseek_client import DeepSeekClient
from ..terminal_tool import TOOL_SCHEMA, TerminalExecutor
from .compressor import ContextCompressor
from .context_builder import ContextBuilder
from .models import ChatTurn, ModelProfile, SessionEvent, TokenUsage
from .store import SessionStore
from .subagents import SubAgentManager
from .task_router import SuggestedSubagent, TaskRouteDecision, TaskRouter


class SessionChatRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        session_store: SessionStore,
        context_builder: ContextBuilder,
        client: Optional[DeepSeekClient] = None,
        executor_factory: Optional[Callable[[
            ModelProfile], TerminalExecutor]] = None,
        compressor: Optional[ContextCompressor] = None,
        subagent_manager: Optional[SubAgentManager] = None,
        task_router: Optional[TaskRouter] = None,
    ) -> None:
        self.settings = settings
        self.session_store = session_store
        self.context_builder = context_builder
        self.client = client or DeepSeekClient(settings.deepseek)
        self.executor_factory = executor_factory or self._default_executor_factory
        self.compressor = compressor
        self.subagent_manager = subagent_manager
        self.task_router = task_router or TaskRouter()

    def send_message(self, *, session_id: str, user_message: str) -> dict[str, Any]:
        clean_message = str(user_message or "").strip()
        if not clean_message:
            raise ValueError("user_message must be non-empty")

        session = self.session_store.get_session(session_id)
        profile = session.active_profile
        route_decision = self.task_router.route(user_message=clean_message)
        routing_result = self._prepare_routed_context(
            session_id=session_id,
            user_message=clean_message,
            profile=profile,
            route_decision=route_decision,
        )
        context = self.context_builder.build(
            session_id=session_id,
            current_user_message=clean_message,
            selected_profile=profile,
            task_type=route_decision.task_type,
        )
        context_pack_path = self.session_store.write_context_pack(
            session_id, context["context_pack"])
        context_report_path = self.session_store.write_context_report(
            session_id, context)

        user_turn = ChatTurn(
            turn_id=uuid.uuid4().hex,
            session_id=session_id,
            role="user",
            visible_content=clean_message,
            model_id=profile.model_id,
            model_profile_snapshot=profile.snapshot(),
        )
        self.session_store.append_turn(session_id, user_turn)
        self._append_event(session_id, "user_message",
                           "Queued user message for model execution")

        session.status = "running"
        self.session_store.save_session(session)
        executor = self.executor_factory(profile)
        messages = list(context["messages"])
        assistant_turns: list[dict[str, Any]] = []
        parent_tools = self._parent_tools(
            profile=profile,
            routing_result=routing_result,
        )

        for iteration in range(profile.max_iterations):
            response = self.client.chat_completions(
                messages=list(messages),
                model_profile=profile,
                tools=parent_tools,
            )
            choice = response.choices[0]
            message = choice.message
            token_usage = getattr(response, "usage", None)
            usage = TokenUsage(
                prompt_tokens=getattr(token_usage, "prompt_tokens", None),
                completion_tokens=getattr(
                    token_usage, "completion_tokens", None),
                total_tokens=getattr(token_usage, "total_tokens", None),
            ) if token_usage is not None else None

            assistant_payload: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            tool_calls = []
            if getattr(message, "tool_calls", None):
                tool_calls = [
                    {
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in message.tool_calls
                ]
                assistant_payload["tool_calls"] = tool_calls
            reasoning_content = getattr(message, "reasoning_content", None)
            if isinstance(reasoning_content, str) and reasoning_content:
                assistant_payload["reasoning_content"] = reasoning_content
            messages.append(assistant_payload)

            assistant_turn = ChatTurn(
                turn_id=uuid.uuid4().hex,
                session_id=session_id,
                role="assistant",
                visible_content=message.content or "",
                internal_reasoning_content=reasoning_content if isinstance(
                    reasoning_content, str) else None,
                tool_calls=tool_calls,
                model_id=profile.model_id,
                model_profile_snapshot=profile.snapshot(),
                token_usage=usage,
            )
            self.session_store.append_turn(session_id, assistant_turn)
            assistant_turns.append(assistant_turn.to_public_dict())

            if choice.finish_reason == "stop" or not getattr(message, "tool_calls", None):
                session = self.session_store.get_session(session_id)
                session.status = "completed"
                self.session_store.save_session(session)
                self._append_event(session_id, "assistant_message",
                                   "Model produced a final answer")
                compression_result = self._maybe_auto_compress(
                    session_id=session_id)
                return {
                    "session": self.session_store.get_session(session_id).model_dump(),
                    "user_turn": user_turn.to_public_dict(),
                    "assistant_turn": assistant_turn.to_public_dict(),
                    "assistant_turns": assistant_turns,
                    "routing": routing_result,
                    "context_report": context["context_report"],
                    "context_pack_path": str(context_pack_path),
                    "context_report_path": str(context_report_path),
                    "compression": compression_result,
                }

            for tool_call in message.tool_calls:
                tool_result = self._dispatch_tool(tool_call, executor, profile)
                tool_turn = ChatTurn(
                    turn_id=uuid.uuid4().hex,
                    session_id=session_id,
                    role="tool",
                    visible_content=self._tool_preview(tool_result),
                    tool_results=[tool_result],
                    model_id=profile.model_id,
                    model_profile_snapshot=profile.snapshot(),
                )
                self.session_store.append_turn(session_id, tool_turn)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
                self._append_event(session_id, "tool_result", f"Executed {tool_call.function.name}", metadata={
                                   "cmd": tool_result.get("cmd")})

        session = self.session_store.get_session(session_id)
        session.status = "failed"
        self.session_store.save_session(session)
        raise RuntimeError(
            f"Session chat exceeded max_iterations={profile.max_iterations}")

    def _prepare_routed_context(
        self,
        *,
        session_id: str,
        user_message: str,
        profile: ModelProfile,
        route_decision: TaskRouteDecision,
    ) -> dict[str, Any]:
        route_payload = route_decision.model_dump()
        self._append_event(
            session_id,
            "route_decision",
            f"Task router selected {route_decision.route}",
            metadata=route_payload,
        )
        session = self.session_store.get_session(session_id)
        session.metadata["last_task_route"] = route_payload
        self.session_store.save_session(session)

        if route_decision.route == "direct" or self.subagent_manager is None:
            if route_decision.route == "orchestrated" and self.subagent_manager is None:
                route_payload["routing_warning"] = "subagent_manager_unavailable"
                session = self.session_store.get_session(session_id)
                session.metadata["last_task_route"] = route_payload
                self.session_store.save_session(session)
            return route_payload

        spawned_subagents: list[dict[str, Any]] = []
        artifact_ids: list[str] = []
        failures: list[dict[str, Any]] = []
        for suggestion in route_decision.suggested_subagents:
            child = self.subagent_manager.spawn_subagent(
                parent_session_id=session_id,
                role=suggestion.role,
                task=suggestion.task,
                model_profile=self._resolve_subagent_profile(
                    current_profile=profile,
                    suggestion=suggestion,
                ),
                tool_policy=suggestion.tool_policy,
                context_pack=self.context_builder.build(
                    session_id=session_id,
                    current_user_message=suggestion.task,
                    selected_profile=profile,
                    task_type=route_decision.task_type,
                )["context_pack"],
                timeout_sec=self.settings.subagents.default_timeout_sec,
            )
            child_run_id = child["child_run_id"]
            self._append_event(
                session_id,
                "subagent_spawned",
                f"Spawned {suggestion.role}",
                metadata={
                    "child_run_id": child_run_id,
                    "role": suggestion.role,
                    "tool_policy": suggestion.tool_policy,
                },
            )
            final_state = self.subagent_manager.wait_for_completion(
                child_run_id,
                timeout_sec=self.settings.subagents.default_timeout_sec + 1,
            )
            spawned = {
                "child_run_id": child_run_id,
                "role": suggestion.role,
                "tool_policy": suggestion.tool_policy,
                "status": final_state["status"],
                "artifact_id": final_state.get("artifact_id"),
                "attached": False,
            }
            if final_state["status"] == "completed" and final_state.get("artifact_id"):
                artifact = self.subagent_manager.get_artifact(child_run_id)
                if artifact is not None:
                    self.subagent_manager.attach_artifact_to_session(
                        session_id, artifact.artifact_id)
                    artifact_ids.append(artifact.artifact_id)
                    spawned["attached"] = True
                    self._append_event(
                        session_id,
                        "subagent_completed",
                        f"Completed {suggestion.role}",
                        metadata={
                            "child_run_id": child_run_id,
                            "artifact_id": artifact.artifact_id,
                            "summary": artifact.summary,
                        },
                    )
            else:
                failure = {
                    "child_run_id": child_run_id,
                    "role": suggestion.role,
                    "status": final_state["status"],
                    "error": final_state.get("error"),
                }
                failures.append(failure)
                self._append_event(
                    session_id,
                    "subagent_failed",
                    f"Subagent {suggestion.role} finished with {final_state['status']}",
                    metadata=failure,
                )
            spawned_subagents.append(spawned)

        route_payload["spawned_subagents"] = spawned_subagents
        route_payload["artifact_ids"] = artifact_ids
        route_payload["failures"] = failures
        session = self.session_store.get_session(session_id)
        session.metadata["last_task_route"] = route_payload
        self.session_store.save_session(session)
        return route_payload

    def _resolve_subagent_profile(
        self,
        *,
        current_profile: ModelProfile,
        suggestion: SuggestedSubagent,
    ) -> ModelProfile:
        if suggestion.profile_strategy == "current":
            base = current_profile.model_copy(deep=True)
            base.tool_mode = "auto"
            base.response_format = "json_object"
            return ModelProfile(**base.model_dump())

        base = current_profile.model_copy(deep=True)
        base.model_id = "deepseek-v4-flash"
        base.thinking_type = "disabled"
        base.reasoning_effort = "high"
        base.tool_mode = "auto"
        base.response_format = "json_object"
        base.max_tokens = min(base.max_tokens, 4096)
        base.max_iterations = 8 if suggestion.profile_strategy == "flash_scout" else 6
        base.command_timeout_sec = min(max(base.command_timeout_sec, 90), 120)
        base.max_command_output_chars = min(
            max(base.max_command_output_chars, 12000),
            20000,
        )
        base.context_budget_chars = min(base.context_budget_chars, 200000)
        base.recent_turns_budget = min(base.recent_turns_budget, 8)
        base.tool_output_budget_chars = min(
            max(base.tool_output_budget_chars, 24000), 40000)
        base.temperature = 0.1 if suggestion.profile_strategy == "flash_scout" else 0.2
        base.profile_id = f"{suggestion.profile_strategy}-runtime"
        base.name = f"{suggestion.role} Runtime"
        return ModelProfile(**base.model_dump())

    def _maybe_auto_compress(self, *, session_id: str) -> Optional[dict[str, Any]]:
        if not self.compressor or not self.settings.compression.enabled or not self.settings.compression.auto_enabled:
            return None
        return self.compressor.compress_session(session_id=session_id)

    def _dispatch_tool(self, tool_call, executor: TerminalExecutor, profile: ModelProfile) -> dict[str, Any]:
        if tool_call.function.name != "terminal_exec":
            return {"ok": False, "error": f"Unknown tool: {tool_call.function.name}"}
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"Invalid JSON in tool arguments: {exc}"}
        return executor.execute(
            cmd=arguments.get("cmd", ""),
            cwd=arguments.get("cwd"),
            timeout_sec=arguments.get(
                "timeout_sec") or profile.command_timeout_sec,
        )

    def _parent_tools(
        self,
        *,
        profile: ModelProfile,
        routing_result: dict[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        if profile.tool_mode == "none":
            return None
        # Once a routed child attaches evidence, the parent should synthesize
        # from that evidence instead of re-running the same repo scan.
        if routing_result.get("artifact_ids"):
            return None
        return [TOOL_SCHEMA]

    def _tool_preview(self, tool_result: dict[str, Any]) -> str:
        stdout = str(tool_result.get("stdout") or "").strip()
        stderr = str(tool_result.get("stderr") or "").strip()
        if stdout and stderr:
            return f"stdout:\n{stdout}\n\nstderr:\n{stderr}"
        return stdout or stderr or json.dumps(tool_result, ensure_ascii=False)

    def _append_event(
        self,
        session_id: str,
        event_type: str,
        message: str,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.session_store.append_event(
            session_id,
            SessionEvent(
                event_id=uuid.uuid4().hex,
                session_id=session_id,
                event_type=event_type,
                message=message,
                metadata=metadata or {},
            ),
        )

    def _default_executor_factory(self, profile: ModelProfile) -> TerminalExecutor:
        return TerminalExecutor(
            workspace_root=self.settings.terminal.workspace_root,
            default_timeout_sec=profile.command_timeout_sec,
            max_output_chars=profile.max_command_output_chars,
            require_approval_for_dangerous=self.settings.terminal.require_approval_for_dangerous,
            dry_run=False,
            interactive=False,
        )
