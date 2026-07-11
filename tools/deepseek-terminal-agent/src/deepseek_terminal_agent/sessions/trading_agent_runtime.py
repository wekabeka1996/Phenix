"""P43B model-runtime boundaries for API and restricted CLI trading agents.

This module stops at a validated trading response. It never calls an exchange,
FSM, repository tool, shell, or collective-memory writer.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config import DeepSeekConfig
from .p42_config import AgentRuntimeConfig

TradingAction = Literal[
    "WAIT",
    "SKIP",
    "PUBLISH_OBSERVATION",
    "PUBLISH_RISK_WARNING",
    "REQUEST_ORDER",
    "REQUEST_CANCEL",
    "REQUEST_CLOSE",
    "REQUEST_REVIEW",
    "EMIT_SOS",
]
RequestedTool = Literal[
    "none",
    "publish_observation",
    "publish_risk_warning",
    "request_order",
    "request_cancel",
    "request_close",
    "request_review",
    "emit_sos",
]
ProviderState = Literal[
    "OK",
    "PROVIDER_FAILURE",
    "INVALID_RESPONSE",
    "CLI_FAILURE",
    "CANCELLED",
]

TOOL_FOR_ACTION: dict[str, str] = {
    "WAIT": "none",
    "SKIP": "none",
    "PUBLISH_OBSERVATION": "publish_observation",
    "PUBLISH_RISK_WARNING": "publish_risk_warning",
    "REQUEST_ORDER": "request_order",
    "REQUEST_CANCEL": "request_cancel",
    "REQUEST_CLOSE": "request_close",
    "REQUEST_REVIEW": "request_review",
    "EMIT_SOS": "emit_sos",
}
ALLOWED_RESPONSE_TOOLS = set(TOOL_FOR_ACTION.values()) - {"none"}
FORBIDDEN_RUNTIME_FIELDS = {
    "api_key",
    "api_secret",
    "secret",
    "signature",
    "signed_payload",
    "raw_exchange_payload",
    "exchange_request",
    "shell",
    "command_line",
    "filesystem_path",
    "git_command",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)

    @model_validator(mode="after")
    def total_is_consistent(self) -> "TokenUsage":
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens cannot be below prompt plus completion tokens")
        return self


class TradingResponse(BaseModel):
    """Only response shape that may leave an agent model boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: TradingAction
    agent_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    turn_id: str = Field(..., min_length=1)
    based_on_collective_version: str = Field(..., min_length=1)
    instruction_version: str = Field(..., min_length=1)
    owned_symbol: str = Field(..., min_length=1)
    rationale_summary: str = Field(..., min_length=3, max_length=2000)
    requested_tool: RequestedTool
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)
    token_usage: Optional[TokenUsage] = None
    provider_state: ProviderState = "OK"
    error_code: Optional[str] = None
    response_id: Optional[str] = None

    @field_validator("agent_id", "session_id", "turn_id", "owned_symbol")
    @classmethod
    def safe_ids(cls, value: str) -> str:
        text = value.strip()
        if not text or any(part in text for part in ("..", "/", "\\")):
            raise ValueError("runtime identifiers must be local safe strings")
        return text

    @field_validator("payload")
    @classmethod
    def reject_forbidden_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_forbidden_fields(value)
        return value

    @model_validator(mode="after")
    def action_tool_pair_is_explicit(self) -> "TradingResponse":
        expected = TOOL_FOR_ACTION[self.action]
        if self.requested_tool != expected:
            raise ValueError(
                f"requested_tool '{self.requested_tool}' does not match action '{self.action}'"
            )
        return self


class TradingTurnContext(BaseModel):
    """Bounded turn context; raw durable memory is never inserted wholesale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(..., min_length=1)
    turn_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    owned_symbols: list[str] = Field(..., min_length=1)
    owned_symbol: str = Field(..., min_length=1)
    current_market_context: dict[str, Any]
    portfolio_state: dict[str, Any]
    own_positions_orders: dict[str, Any]
    peer_publications: list[dict[str, Any]]
    instruction_versions: dict[str, str]
    instruction_version: str = Field(..., min_length=1)
    current_checkpoint_summary: str = Field(..., max_length=6000)
    recent_private_reflection_summaries: list[str] = Field(default_factory=list)
    available_tools: list[str]
    deadline: str = Field(..., min_length=1)
    current_collective_state_version: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def owned_symbol_is_owned(self) -> "TradingTurnContext":
        if self.owned_symbol not in self.owned_symbols:
            raise ValueError("owned_symbol must be included in owned_symbols")
        if len(set(self.owned_symbols)) != len(self.owned_symbols):
            raise ValueError("owned_symbols must be unique")
        return self

    def compact_payload(self, *, max_chars: int = 24000) -> dict[str, Any]:
        payload = {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "agent_id": self.agent_id,
            "agent_number": self.agent_number,
            "owned_symbols": self.owned_symbols,
            "owned_symbol": self.owned_symbol,
            "current_market_context": _clip_json(self.current_market_context, 5000),
            "portfolio_state": _clip_json(self.portfolio_state, 3000),
            "own_positions_orders": _clip_json(self.own_positions_orders, 4000),
            "peer_publications": [_clip_json(item, 1800) for item in self.peer_publications[-8:]],
            "instruction_versions": self.instruction_versions,
            "instruction_version": self.instruction_version,
            "current_checkpoint_summary": self.current_checkpoint_summary[:6000],
            "recent_private_reflection_summaries": [
                text[:1200] for text in self.recent_private_reflection_summaries[-6:]
            ],
            "available_tools": self.available_tools,
            "deadline": self.deadline,
            "current_collective_state_version": self.current_collective_state_version,
        }
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        if len(encoded) <= max_chars:
            return payload
        payload["recent_private_reflection_summaries"] = []
        payload["peer_publications"] = payload["peer_publications"][-3:]
        payload["current_checkpoint_summary"] = payload["current_checkpoint_summary"][:2500]
        return payload


class RuntimeHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    session_id: Optional[str]
    runtime_kind: Literal["api", "cli"]
    state: str
    provider_state: ProviderState
    last_heartbeat: Optional[str]
    active_turn_ids: list[str]
    last_error_code: Optional[str]
    clean_shutdown: bool


class TradingAgentRuntime(Protocol):
    async def start_session(self, session_id: str) -> RuntimeHealth: ...

    async def submit_turn(self, context: TradingTurnContext) -> TradingResponse: ...

    async def cancel_turn(self, turn_id: str) -> bool: ...

    async def health(self) -> RuntimeHealth: ...

    async def shutdown(self) -> None: ...


class TradingAgentRuntimeBase(ABC):
    runtime_kind: Literal["api", "cli"]

    def __init__(self, agent_config: AgentRuntimeConfig) -> None:
        self.agent_config = agent_config
        self._session_id: Optional[str] = None
        self._state = "NEW"
        self._provider_state: ProviderState = "OK"
        self._last_heartbeat: Optional[str] = None
        self._last_error_code: Optional[str] = None
        self._active_turns: dict[str, asyncio.Task[Any]] = {}
        self._clean_shutdown = False

    async def start_session(self, session_id: str) -> RuntimeHealth:
        if not session_id.strip():
            self._state = "BLOCKED_INVALID_SESSION"
            self._last_error_code = "INVALID_SESSION"
            return await self.health()
        if self._session_id and self._session_id != session_id:
            self._state = "BLOCKED_SESSION_ALREADY_BOUND"
            self._last_error_code = "SESSION_ALREADY_BOUND"
            return await self.health()
        self._session_id = session_id
        self._state = "READY"
        self._clean_shutdown = False
        self._touch_heartbeat()
        return await self.health()

    async def submit_turn(self, context: TradingTurnContext) -> TradingResponse:
        validation_error = self._validate_context(context)
        if validation_error:
            return self._failure_response(context, "INVALID_TURN_CONTEXT", validation_error)
        if self._state in {"NEW", "SHUTDOWN"}:
            return self._failure_response(context, "SESSION_NOT_STARTED", "runtime session is not active")
        if self._state.startswith("BLOCKED"):
            return self._failure_response(
                context,
                self._last_error_code or "RUNTIME_BLOCKED",
                "runtime is explicitly blocked",
            )
        task = asyncio.current_task()
        if task is not None:
            self._active_turns[context.turn_id] = task
        try:
            return await self._submit_turn_impl(context)
        except asyncio.CancelledError:
            self._state = "CANCELLED"
            self._provider_state = "CANCELLED"
            self._last_error_code = "TURN_CANCELLED"
            raise
        finally:
            self._active_turns.pop(context.turn_id, None)

    async def cancel_turn(self, turn_id: str) -> bool:
        task = self._active_turns.get(turn_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            agent_id=self.agent_config.agent_id,
            session_id=self._session_id,
            runtime_kind=self.runtime_kind,
            state=self._state,
            provider_state=self._provider_state,
            last_heartbeat=self._last_heartbeat,
            active_turn_ids=sorted(self._active_turns),
            last_error_code=self._last_error_code,
            clean_shutdown=self._clean_shutdown,
        )

    async def shutdown(self) -> None:
        for task in list(self._active_turns.values()):
            if not task.done():
                task.cancel()
        self._active_turns.clear()
        self._state = "SHUTDOWN"
        self._clean_shutdown = True

    @abstractmethod
    async def _submit_turn_impl(self, context: TradingTurnContext) -> TradingResponse:
        raise NotImplementedError

    def _validate_context(self, context: TradingTurnContext) -> Optional[str]:
        if context.agent_id != self.agent_config.agent_id:
            return "agent_id does not match runtime configuration"
        if context.agent_number != self.agent_config.agent_number:
            return "agent_number does not match runtime configuration"
        if tuple(context.owned_symbols) != tuple(self.agent_config.symbols):
            return "owned_symbols do not match runtime configuration"
        if context.owned_symbol not in self.agent_config.symbols:
            return "owned_symbol is not owned by runtime configuration"
        if self._session_id and context.session_id != self._session_id:
            return "context session_id does not match runtime session"
        return None

    def _validate_response(
        self,
        context: TradingTurnContext,
        raw: dict[str, Any],
        *,
        token_usage: Optional[TokenUsage] = None,
    ) -> TradingResponse:
        candidate = dict(raw)
        candidate.setdefault("agent_id", context.agent_id)
        candidate.setdefault("session_id", context.session_id)
        candidate.setdefault("turn_id", context.turn_id)
        candidate.setdefault("created_at", utc_now_iso())
        if token_usage is not None:
            candidate["token_usage"] = token_usage
        try:
            response = TradingResponse.model_validate(candidate)
        except Exception:
            return self._failure_response(context, "MALFORMED_STRUCTURED_RESPONSE", "response schema rejected")
        if response.agent_id != context.agent_id or response.session_id != context.session_id:
            return self._failure_response(context, "IDENTITY_MISMATCH", "response identity rejected")
        if response.turn_id != context.turn_id:
            return self._failure_response(context, "TURN_ID_MISMATCH", "response turn_id rejected")
        if response.based_on_collective_version != context.current_collective_state_version:
            return self._failure_response(context, "STALE_COLLECTIVE_VERSION", "collective state version is stale")
        if response.instruction_version != context.instruction_version:
            return self._failure_response(context, "STALE_INSTRUCTION_VERSION", "instruction version is stale")
        if response.owned_symbol not in self.agent_config.symbols:
            return self._failure_response(context, "WRONG_SYMBOL_REJECTION", "response symbol is not owned")
        if response.requested_tool != "none" and response.requested_tool not in context.available_tools:
            return self._failure_response(context, "UNAUTHORIZED_TOOL", "requested tool is not available")
        payload_symbol = response.payload.get("symbol")
        if payload_symbol is not None and payload_symbol != response.owned_symbol:
            return self._failure_response(context, "WRONG_SYMBOL_REJECTION", "payload symbol is not response symbol")
        self._provider_state = "OK"
        self._state = "READY"
        self._touch_heartbeat()
        return response

    def _failure_response(
        self,
        context: TradingTurnContext,
        code: str,
        detail: str,
        *,
        provider_state: ProviderState = "PROVIDER_FAILURE",
        token_usage: Optional[TokenUsage] = None,
    ) -> TradingResponse:
        self._last_error_code = code
        self._provider_state = provider_state
        self._state = code
        return TradingResponse(
            action="REQUEST_REVIEW",
            agent_id=context.agent_id,
            session_id=context.session_id,
            turn_id=context.turn_id,
            based_on_collective_version=context.current_collective_state_version,
            instruction_version=context.instruction_version,
            owned_symbol=context.owned_symbol,
            rationale_summary=f"{code}: {detail}"[:2000],
            requested_tool="request_review",
            confidence=0.0,
            payload={},
            token_usage=token_usage,
            provider_state=provider_state,
            error_code=code,
        )

    def _touch_heartbeat(self) -> None:
        self._last_heartbeat = utc_now_iso()


class OpenAICompatibleTradingAgentRuntime(TradingAgentRuntimeBase):
    """OpenAI/DeepSeek-compatible provider adapter with no model fallback."""

    runtime_kind: Literal["api"] = "api"

    def __init__(
        self,
        agent_config: AgentRuntimeConfig,
        provider_config: DeepSeekConfig,
        *,
        client: Any = None,
    ) -> None:
        super().__init__(agent_config)
        self.provider_config = provider_config
        self._client = client
        self._init_error: Optional[str] = None
        if self._client is None:
            if not provider_config.api_key:
                self._init_error = "MISSING_PROVIDER_CREDENTIAL"
            else:
                try:
                    from openai import AsyncOpenAI

                    self._client = AsyncOpenAI(
                        api_key=provider_config.api_key,
                        base_url=provider_config.base_url,
                    )
                except Exception:
                    self._init_error = "PROVIDER_CLIENT_UNAVAILABLE"

    async def start_session(self, session_id: str) -> RuntimeHealth:
        health = await super().start_session(session_id)
        if health.state != "READY":
            return health
        if self._init_error:
            self._state = "BLOCKED_" + self._init_error
            self._provider_state = "PROVIDER_FAILURE"
            self._last_error_code = self._init_error
        return await self.health()

    async def _submit_turn_impl(self, context: TradingTurnContext) -> TradingResponse:
        if self._init_error or self._client is None:
            return self._failure_response(
                context,
                self._init_error or "PROVIDER_CLIENT_UNAVAILABLE",
                "configured API provider is unavailable",
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "Return one JSON trading response only. Never call exchange APIs, shell, "
                    "filesystem, git, or repository tools. Respect owned_symbol and versions."
                ),
            },
            {"role": "user", "content": json.dumps(context.compact_payload(), ensure_ascii=True)},
        ]
        tools = _provider_tools(context.available_tools)
        attempts = self.agent_config.retry_count + 1
        token_usage: Optional[TokenUsage] = None
        for attempt in range(attempts):
            try:
                request = self._client.chat.completions.create(
                    model=self.agent_config.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    tools=tools or None,
                    timeout=self.agent_config.response_timeout_sec,
                )
                response = await asyncio.wait_for(
                    request if inspect.isawaitable(request) else _completed(request),
                    timeout=self.agent_config.response_timeout_sec,
                )
                token_usage = _token_usage_from_response(response)
                raw, error_code = _extract_provider_response(response)
                if error_code:
                    return self._failure_response(
                        context,
                        error_code,
                        "provider response was rejected",
                        token_usage=token_usage,
                    )
                return self._validate_response(context, raw, token_usage=token_usage)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                if attempt + 1 == attempts:
                    return self._failure_response(context, "PROVIDER_TIMEOUT", "provider deadline exceeded")
            except Exception:
                if attempt + 1 == attempts:
                    return self._failure_response(context, "PROVIDER_REQUEST_FAILED", "provider request failed")
        return self._failure_response(context, "PROVIDER_REQUEST_FAILED", "provider retry budget exhausted")


class RestrictedCLITradingAgentRuntime(TradingAgentRuntimeBase):
    """Long-lived JSON-lines CLI adapter with a deliberately narrow protocol."""

    runtime_kind: Literal["cli"] = "cli"

    def __init__(
        self,
        agent_config: AgentRuntimeConfig,
        *,
        command: Optional[Sequence[str]] = None,
        working_dir: Optional[str | Path] = None,
        approved_paths: Optional[Sequence[str | Path]] = None,
    ) -> None:
        super().__init__(agent_config)
        self.command = list(command) if command is not None else agent_config.cli_command
        self.working_dir = Path(working_dir or agent_config.cli_working_dir) if (working_dir or agent_config.cli_working_dir) else None
        configured_paths = approved_paths if approved_paths is not None else agent_config.approved_session_paths
        self.approved_paths = [Path(path).resolve() for path in configured_paths]
        self._process: Optional[asyncio.subprocess.Process] = None
        self._io_lock = asyncio.Lock()
        self._seen_response_ids: set[str] = set()

    async def start_session(self, session_id: str) -> RuntimeHealth:
        health = await super().start_session(session_id)
        if health.state != "READY":
            return health
        validation_error = self._validate_process_configuration()
        if validation_error:
            self._state = "BLOCKED_" + validation_error
            self._provider_state = "CLI_FAILURE"
            self._last_error_code = validation_error
            return await self.health()
        try:
            environment = _safe_cli_environment(self.agent_config.agent_id, self.approved_paths)
            self._process = await asyncio.create_subprocess_exec(
                *(self.command or ()),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(self.working_dir),
                env=environment,
            )
        except Exception:
            self._state = "BLOCKED_CLI_PROCESS_START"
            self._provider_state = "CLI_FAILURE"
            self._last_error_code = "CLI_PROCESS_START_FAILED"
            return await self.health()
        self._state = "READY"
        self._provider_state = "OK"
        self._touch_heartbeat()
        return await self.health()

    async def _submit_turn_impl(self, context: TradingTurnContext) -> TradingResponse:
        process = self._process
        if process is None or process.returncode is not None or process.stdin is None or process.stdout is None:
            return self._failure_response(
                context,
                "CLI_PROCESS_UNAVAILABLE",
                "restricted CLI process is not running",
                provider_state="CLI_FAILURE",
            )
        request = {
            "protocol": "p43b-trading-json-v1",
            "type": "turn",
            "session_id": context.session_id,
            "turn_id": context.turn_id,
            "agent_id": context.agent_id,
            "agent_number": context.agent_number,
            "context": context.compact_payload(),
        }
        async with self._io_lock:
            try:
                process.stdin.write((json.dumps(request, ensure_ascii=True) + "\n").encode("utf-8"))
                await asyncio.wait_for(process.stdin.drain(), self.agent_config.response_timeout_sec)
                line = await asyncio.wait_for(process.stdout.readline(), self.agent_config.response_timeout_sec)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                await self._terminate_process()
                return self._failure_response(
                    context,
                    "CLI_TURN_TIMEOUT",
                    "CLI response deadline exceeded",
                    provider_state="CLI_FAILURE",
                )
            except Exception:
                return self._failure_response(
                    context,
                    "CLI_PROCESS_IO_FAILURE",
                    "CLI process I/O failed",
                    provider_state="CLI_FAILURE",
                )
        if not line:
            return self._failure_response(
                context,
                "CLI_PROCESS_CRASH",
                "CLI process returned no response",
                provider_state="CLI_FAILURE",
            )
        try:
            raw = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure_response(
                context,
                "CORRUPTED_CLI_RESPONSE",
                "CLI response was not one JSON object",
                provider_state="CLI_FAILURE",
            )
        if not isinstance(raw, dict):
            return self._failure_response(context, "CORRUPTED_CLI_RESPONSE", "CLI response was not an object", provider_state="CLI_FAILURE")
        response_id = str(raw.get("response_id") or "").strip()
        if not response_id:
            return self._failure_response(context, "MISSING_RESPONSE_ID", "CLI response_id is required", provider_state="CLI_FAILURE")
        if response_id in self._seen_response_ids:
            return self._failure_response(context, "DUPLICATE_RESPONSE", "CLI response_id was already seen", provider_state="CLI_FAILURE")
        self._seen_response_ids.add(response_id)
        if raw.get("turn_id") != context.turn_id:
            return self._failure_response(context, "TURN_ID_MISMATCH", "CLI response turn_id rejected", provider_state="CLI_FAILURE")
        self._touch_heartbeat()
        return self._validate_response(context, raw)

    async def shutdown(self) -> None:
        process = self._process
        if process is not None and process.returncode is None:
            try:
                if process.stdin is not None:
                    process.stdin.write(b'{"protocol":"p43b-trading-json-v1","type":"shutdown"}\n')
                    await asyncio.wait_for(process.stdin.drain(), 1.0)
                await asyncio.wait_for(process.wait(), 1.0)
            except Exception:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 1.0)
                except Exception:
                    process.kill()
                    await process.wait()
        await super().shutdown()

    async def _terminate_process(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 1.0)
        except Exception:
            process.kill()
            await process.wait()

    async def health(self) -> RuntimeHealth:
        if self._process is not None and self._process.returncode is not None and self._state == "READY":
            self._state = "CLI_PROCESS_EXITED"
            self._provider_state = "CLI_FAILURE"
            self._last_error_code = "CLI_PROCESS_EXITED"
        return await super().health()

    def _validate_process_configuration(self) -> Optional[str]:
        if not self.command:
            return "CLI_NOT_CONFIGURED"
        if not self.approved_paths:
            return "CLI_APPROVED_PATHS_MISSING"
        if self.working_dir is None:
            return "CLI_WORKING_DIR_MISSING"
        if not _path_under_any(self.working_dir.resolve(), self.approved_paths):
            return "CLI_WORKING_DIR_OUTSIDE_APPROVED_PATH"
        if any(not path.exists() for path in self.approved_paths):
            return "CLI_APPROVED_PATH_MISSING"
        tokens = [str(token) for token in self.command]
        command_name = Path(tokens[0]).name.lower()
        forbidden_names = {"git", "powershell", "pwsh", "cmd", "bash", "sh", "zsh", "fish"}
        if command_name in forbidden_names:
            return "CLI_FORBIDDEN_EXECUTABLE"
        forbidden_fragments = ("&&", ";", "|", ">", "<", "$", "`")
        if any(fragment in token for token in tokens for fragment in forbidden_fragments):
            return "CLI_SHELL_SYNTAX_REJECTED"
        if any(token.lower() in {"-c", "--command", "-command", "/c", "/k"} for token in tokens):
            return "CLI_ARBITRARY_COMMAND_REJECTED"
        for token in tokens[1:]:
            candidate = Path(token)
            if candidate.is_absolute() and candidate.exists() and not _path_under_any(candidate.resolve(), self.approved_paths):
                if Path(tokens[0]).name.lower().startswith(("python", "python3")):
                    continue
                return "CLI_PATH_OUTSIDE_APPROVED_PATH"
        return None


def build_trading_agent_runtime(
    agent_config: AgentRuntimeConfig,
    *,
    provider_config: Optional[DeepSeekConfig] = None,
    client: Any = None,
    command: Optional[Sequence[str]] = None,
    working_dir: Optional[str | Path] = None,
    approved_paths: Optional[Sequence[str | Path]] = None,
) -> TradingAgentRuntime:
    """Build exactly the configured runtime kind; never fall back silently."""
    if agent_config.runtime_kind == "api":
        if provider_config is None:
            raise ValueError("API runtime requires explicit provider configuration")
        return OpenAICompatibleTradingAgentRuntime(
            agent_config,
            provider_config,
            client=client,
        )
    if agent_config.runtime_kind == "cli":
        return RestrictedCLITradingAgentRuntime(
            agent_config,
            command=command,
            working_dir=working_dir,
            approved_paths=approved_paths,
        )
    raise ValueError(f"Unsupported runtime kind: {agent_config.runtime_kind}")


async def _completed(value: Any) -> Any:
    return value


def _reject_forbidden_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_RUNTIME_FIELDS:
                raise ValueError(f"forbidden runtime field: {key}")
            _reject_forbidden_fields(child)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_fields(item)


def _clip_json(value: Any, max_chars: int) -> Any:
    encoded = json.dumps(value, ensure_ascii=True, default=str)
    if len(encoded) <= max_chars:
        return value
    return {"truncated": True, "summary": encoded[: max_chars - 32]}


def _provider_tools(available_tools: Sequence[str]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name in available_tools:
        if name not in ALLOWED_RESPONSE_TOOLS:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Request registered {name} handling; never call an exchange.",
                    "parameters": {"type": "object", "additionalProperties": True},
                },
            }
        )
    return tools


def _extract_provider_response(response: Any) -> tuple[dict[str, Any], Optional[str]]:
    choices = _get(response, "choices", [])
    if not choices:
        return {}, "MALFORMED_PROVIDER_RESPONSE"
    message = _get(choices[0], "message", {})
    tool_calls = _get(message, "tool_calls", []) or []
    if len(tool_calls) > 1:
        return {}, "MULTIPLE_TOOL_CALLS_REJECTED"
    tool_name: Optional[str] = None
    data: dict[str, Any] = {}
    if tool_calls:
        tool = tool_calls[0]
        function = _get(tool, "function", {})
        tool_name = str(_get(function, "name", "")).strip()
        if tool_name not in ALLOWED_RESPONSE_TOOLS:
            return {}, "UNAUTHORIZED_TOOL"
        arguments = _get(function, "arguments", "")
        try:
            data = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}, "MALFORMED_TOOL_ARGUMENTS"
        if not isinstance(data, dict):
            return {}, "MALFORMED_TOOL_ARGUMENTS"
    else:
        content = _get(message, "content", "")
        try:
            data = json.loads(content) if isinstance(content, str) else dict(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}, "MALFORMED_JSON"
        if not isinstance(data, dict):
            return {}, "MALFORMED_JSON"
    if tool_name:
        data.setdefault("requested_tool", tool_name)
        data.setdefault("action", next(action for action, tool in TOOL_FOR_ACTION.items() if tool == tool_name))
    return data, None


def _token_usage_from_response(response: Any) -> Optional[TokenUsage]:
    usage = _get(response, "usage", None)
    if usage is None:
        return None
    try:
        return TokenUsage(
            prompt_tokens=int(_get(usage, "prompt_tokens", 0)),
            completion_tokens=int(_get(usage, "completion_tokens", 0)),
            total_tokens=int(_get(usage, "total_tokens", 0)),
        )
    except (TypeError, ValueError):
        return None


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _path_under_any(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _safe_cli_environment(agent_id: str, approved_paths: Sequence[Path]) -> dict[str, str]:
    environment = dict(os.environ)
    for key in list(environment):
        if "API_KEY" in key or "API_SECRET" in key or "PASSWORD" in key or "TOKEN" in key:
            environment.pop(key, None)
    environment.update(
        {
            "PHENIX_TRADING_MODE": "1",
            "P42_AGENT_ID": agent_id,
            "P42_ALLOWED_SESSION_PATHS": os.pathsep.join(str(path) for path in approved_paths),
        }
    )
    return environment
