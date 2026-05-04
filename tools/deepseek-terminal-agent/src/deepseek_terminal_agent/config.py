"""Configuration loading: YAML base → env overrides → fail-fast validation."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

ThinkingType = Literal["enabled", "disabled"]
ReasoningEffort = Literal["high", "max"]
ToolPolicyName = Literal["none", "read_only",
                         "tests_only", "full_agent_safety"]


def _validate_relative_local_path(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        raise ValueError("path must be non-empty")
    path = Path(text)
    if path.is_absolute():
        raise ValueError("path must be relative to the project root")
    if any(part == ".." for part in path.parts):
        raise ValueError("path traversal is not allowed")
    return text


class DeepSeekConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    request_timeout_sec: int = 300
    reasoning_enabled: bool = True
    reasoning_effort: ReasoningEffort = "high"
    temperature: float = 0.2
    top_p: float = 1.0
    max_tokens: int = 8192

    @field_validator("model", "base_url")
    @classmethod
    def non_empty_str(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("must be non-empty")
        return text

    @field_validator("temperature")
    @classmethod
    def temperature_range(cls, value: float) -> float:
        if not 0.0 <= value <= 2.0:
            raise ValueError("temperature must be within 0..2")
        return value

    @field_validator("top_p")
    @classmethod
    def top_p_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("top_p must be within 0..1")
        return value

    @field_validator("max_tokens")
    @classmethod
    def max_tokens_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_tokens must be > 0")
        return value

    @field_validator("request_timeout_sec")
    @classmethod
    def request_timeout_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("request_timeout_sec must be > 0")
        return value


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_cache_path: str = ".agent_memory/model_registry.dsmodels.json"
    static_fallback_models: list[str] = [
        "deepseek-v4-pro", "deepseek-v4-flash"]
    refresh_on_startup: bool = False

    @field_validator("registry_cache_path")
    @classmethod
    def cache_path_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)

    @field_validator("static_fallback_models")
    @classmethod
    def fallback_models_non_empty(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError(
                "static_fallback_models must contain at least one model id")
        return cleaned


class SessionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_dir: str = ".agent_memory/sessions"
    autosave: bool = True
    max_recent_sessions: int = 50

    @field_validator("root_dir")
    @classmethod
    def root_dir_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)

    @field_validator("max_recent_sessions")
    @classmethod
    def recent_sessions_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_recent_sessions must be > 0")
        return value


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    path: str = ".agent_memory/memory_atoms.dsmem.jsonl"
    retrieval_top_k: int = 8
    max_atom_chars: int = 1000

    @field_validator("path")
    @classmethod
    def memory_path_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)

    @field_validator("retrieval_top_k", "max_atom_chars")
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value


class ContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approximate_token_ratio: int = 4
    max_context_chars: int = 800000
    recent_turns_budget_chars: int = 80000
    memory_budget_chars: int = 20000
    artifact_budget_chars: int = 60000
    tool_output_budget_chars: int = 60000
    stable_prefix: bool = True

    @field_validator(
        "approximate_token_ratio",
        "max_context_chars",
        "recent_turns_budget_chars",
        "memory_budget_chars",
        "artifact_budget_chars",
        "tool_output_budget_chars",
    )
    @classmethod
    def context_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value


class CompressionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    auto_enabled: bool = False
    model_id: str = "deepseek-v4-flash"
    thinking_type: ThinkingType = "disabled"
    keep_recent_turns: int = 12
    max_source_turns: int = 80
    target_chars: int = 12000
    notify_user: bool = True

    @field_validator("model_id")
    @classmethod
    def compression_model_non_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("model_id must be non-empty")
        return text

    @field_validator("keep_recent_turns", "max_source_turns", "target_chars")
    @classmethod
    def compression_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value


class TerminalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_root: str = "/workspace/project"
    default_timeout_sec: int = 120
    max_output_chars: int = 20000
    shell: str = "bash"
    require_approval_for_dangerous: bool = True
    allow_network: bool = True

    @field_validator("workspace_root", "shell")
    @classmethod
    def terminal_non_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("must be non-empty")
        return text

    @field_validator("default_timeout_sec")
    @classmethod
    def timeout_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"default_timeout_sec must be > 0, got {value}")
        return value

    @field_validator("max_output_chars")
    @classmethod
    def output_chars_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"max_output_chars must be > 0, got {value}")
        return value


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = 20
    log_dir: str = ".agent_runs"
    system_prompt_path: str = "src/deepseek_terminal_agent/prompts/system.md"

    @field_validator("max_iterations")
    @classmethod
    def iterations_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"max_iterations must be > 0, got {value}")
        return value

    @field_validator("log_dir")
    @classmethod
    def log_dir_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)

    @field_validator("system_prompt_path")
    @classmethod
    def prompt_path_non_empty(cls, value: str) -> str:
        text = str(value or "").strip().replace("\\", "/")
        if not text:
            raise ValueError("system_prompt_path must be non-empty")
        return text


class SubAgentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    default_model_id: str = "deepseek-v4-flash"
    max_concurrent: int = 2
    max_depth: int = 1
    default_timeout_sec: int = 300
    default_tool_policy: ToolPolicyName = "read_only"

    @field_validator("default_model_id")
    @classmethod
    def subagent_model_non_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("default_model_id must be non-empty")
        return text

    @field_validator("max_concurrent", "default_timeout_sec")
    @classmethod
    def subagent_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    @field_validator("max_depth")
    @classmethod
    def subagent_depth_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_depth must be >= 0")
        return value


class DashboardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = 8787
    max_prompt_chars: int = 12000
    max_output_chars: int = 30000
    recent_runs_limit: int = 20
    chat_enabled: bool = True
    context_inspector_enabled: bool = True
    memory_panel_enabled: bool = True
    subagents_panel_enabled: bool = True

    @field_validator("host")
    @classmethod
    def host_non_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("host must be non-empty")
        return text

    @field_validator("port")
    @classmethod
    def port_valid(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError(f"port must be 1–65535, got {value}")
        return value

    @field_validator("max_prompt_chars", "max_output_chars", "recent_runs_limit")
    @classmethod
    def positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value


class ProjectCapsuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "config/project_capsule.yaml"

    @field_validator("path")
    @classmethod
    def path_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)


class PlaybooksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "config/playbooks.yaml"

    @field_validator("path")
    @classmethod
    def path_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)


class ToolRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "config/tool_registry.yaml"

    @field_validator("path")
    @classmethod
    def path_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deepseek: DeepSeekConfig = DeepSeekConfig()
    models: ModelsConfig = ModelsConfig()
    sessions: SessionsConfig = SessionsConfig()
    memory: MemoryConfig = MemoryConfig()
    context: ContextConfig = ContextConfig()
    compression: CompressionConfig = CompressionConfig()
    terminal: TerminalConfig = TerminalConfig()
    agent: AgentConfig = AgentConfig()
    subagents: SubAgentsConfig = SubAgentsConfig()
    dashboard: DashboardConfig = DashboardConfig()
    project_capsule: ProjectCapsuleConfig = ProjectCapsuleConfig()
    playbooks: PlaybooksConfig = PlaybooksConfig()
    tool_registry: ToolRegistryConfig = ToolRegistryConfig()


def load_settings(
    config_path: str = "config/agent.yaml",
    env_file: Optional[str] = ".env",
) -> Settings:
    """Load config: YAML base → env overrides → fail-fast validation.

    Priority (highest wins): env vars > YAML > defaults.
    Fails immediately with a clear message on missing/invalid required fields.
    """
    if env_file is not None and Path(env_file).exists():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)

    yaml_data: dict = {}
    cfg_path = Path(config_path)
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as file_handle:
            yaml_data = yaml.safe_load(file_handle) or {}

    deepseek_raw: dict = dict(yaml_data.get("deepseek", {}))
    models_raw: dict = dict(yaml_data.get("models", {}))
    sessions_raw: dict = dict(yaml_data.get("sessions", {}))
    memory_raw: dict = dict(yaml_data.get("memory", {}))
    context_raw: dict = dict(yaml_data.get("context", {}))
    compression_raw: dict = dict(yaml_data.get("compression", {}))
    terminal_raw: dict = dict(yaml_data.get("terminal", {}))
    agent_raw: dict = dict(yaml_data.get("agent", {}))
    subagents_raw: dict = dict(yaml_data.get("subagents", {}))
    dashboard_raw: dict = dict(yaml_data.get("dashboard", {}))
    project_capsule_raw: dict = dict(yaml_data.get("project_capsule", {}))
    playbooks_raw: dict = dict(yaml_data.get("playbooks", {}))
    tool_registry_raw: dict = dict(yaml_data.get("tool_registry", {}))

    _apply_env_to_dicts(
        deepseek_raw,
        terminal_raw,
        agent_raw,
        dashboard_raw,
    )

    try:
        settings = Settings(
            deepseek=DeepSeekConfig(**deepseek_raw),
            models=ModelsConfig(**models_raw),
            sessions=SessionsConfig(**sessions_raw),
            memory=MemoryConfig(**memory_raw),
            context=ContextConfig(**context_raw),
            compression=CompressionConfig(**compression_raw),
            terminal=TerminalConfig(**terminal_raw),
            agent=AgentConfig(**agent_raw),
            subagents=SubAgentsConfig(**subagents_raw),
            dashboard=DashboardConfig(**dashboard_raw),
            project_capsule=ProjectCapsuleConfig(**project_capsule_raw),
            playbooks=PlaybooksConfig(**playbooks_raw),
            tool_registry=ToolRegistryConfig(**tool_registry_raw),
        )
    except ValidationError as exc:
        _die(f"Invalid config: {exc}")

    _validate_required(settings)
    return settings


def _apply_env_to_dicts(
    deepseek: dict,
    terminal: dict,
    agent: dict,
    dashboard: dict,
) -> None:
    """Apply flat env var overrides into the raw config dicts."""
    env_get = os.environ.get

    if value := env_get("DEEPSEEK_API_KEY"):
        deepseek["api_key"] = value
    if value := env_get("DEEPSEEK_BASE_URL"):
        deepseek["base_url"] = value
    if value := env_get("DEEPSEEK_MODEL"):
        deepseek["model"] = value
    if value := env_get("DEEPSEEK_REQUEST_TIMEOUT_SEC"):
        deepseek["request_timeout_sec"] = int(value)
    if value := env_get("DEEPSEEK_REASONING_ENABLED"):
        deepseek["reasoning_enabled"] = value.lower() in ("1", "true", "yes")
    if value := env_get("DEEPSEEK_REASONING_EFFORT"):
        deepseek["reasoning_effort"] = value
    if value := env_get("DEEPSEEK_TEMPERATURE"):
        deepseek["temperature"] = float(value)
    if value := env_get("DEEPSEEK_TOP_P"):
        deepseek["top_p"] = float(value)
    if value := env_get("DEEPSEEK_MAX_TOKENS"):
        deepseek["max_tokens"] = int(value)

    if value := env_get("AGENT_WORKSPACE"):
        terminal["workspace_root"] = value
    if value := env_get("AGENT_COMMAND_TIMEOUT_SEC"):
        terminal["default_timeout_sec"] = int(value)
    if value := env_get("AGENT_MAX_COMMAND_OUTPUT_CHARS"):
        terminal["max_output_chars"] = int(value)
    if value := env_get("AGENT_REQUIRE_APPROVAL_FOR_DANGEROUS"):
        terminal["require_approval_for_dangerous"] = value.lower() in (
            "1", "true", "yes")
    if value := env_get("AGENT_ALLOW_NETWORK"):
        terminal["allow_network"] = value.lower() in ("1", "true", "yes")

    if value := env_get("AGENT_MAX_ITERATIONS"):
        agent["max_iterations"] = int(value)

    if value := env_get("DASHBOARD_HOST"):
        dashboard["host"] = value
    if value := env_get("DASHBOARD_PORT"):
        dashboard["port"] = int(value)


def _validate_required(settings: Settings) -> None:
    errors: list[str] = []

    if not settings.deepseek.api_key:
        errors.append(
            "DEEPSEEK_API_KEY is required but not set.\n"
            "  Add to .env:  DEEPSEEK_API_KEY=sk-your-key-here\n"
            "  See .env.example for all available options."
        )

    if errors:
        for error in errors:
            print(f"[CONFIG ERROR] {error}", file=sys.stderr)
        sys.exit(1)


def _die(message: str) -> None:
    print(f"[CONFIG ERROR] {message}", file=sys.stderr)
    sys.exit(1)
