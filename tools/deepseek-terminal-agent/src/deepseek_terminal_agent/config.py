"""Configuration loading: YAML base → env overrides → fail-fast validation."""
from __future__ import annotations

import os
import sys
import ipaddress
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator, model_validator

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
    canonical_sessions_root: Optional[str] = None
    retrieval_top_k: int = 8
    max_atom_chars: int = 1000

    @field_validator("path")
    @classmethod
    def memory_path_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)

    @field_validator("canonical_sessions_root")
    @classmethod
    def canonical_sessions_root_safe(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
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
    private_lan_enabled: bool = False
    container_internal_bind: bool = False
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "testserver"]
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8787",
            "http://localhost:8787",
        ]
    )
    environment_label: str = "BINANCE_FUTURES_TESTNET"
    startup_health_url: str = "http://127.0.0.1:8787/health"
    arena_config_path: str = "config/p42_dual_agent_mvp.yaml"
    arena_state_path: str = ".agent_memory/active_dual_agent_session.json"
    heartbeat_stale_after_sec: int = 30
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

    @field_validator("allowed_hosts", "allowed_origins")
    @classmethod
    def non_empty_access_lists(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError("must contain at least one explicit entry")
        if "*" in cleaned:
            raise ValueError("wildcard access entries are not allowed")
        return cleaned

    @field_validator("environment_label")
    @classmethod
    def environment_label_non_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("environment_label must be non-empty")
        return text

    @field_validator("arena_config_path", "arena_state_path")
    @classmethod
    def arena_paths_safe(cls, value: str) -> str:
        return _validate_relative_local_path(value)

    @field_validator("startup_health_url")
    @classmethod
    def health_url_is_local_or_private(cls, value: str) -> str:
        parsed = urlparse(str(value or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("startup_health_url must be an HTTP URL")
        if not _is_local_or_private_host(parsed.hostname):
            raise ValueError("startup_health_url must target localhost or a private address")
        return parsed.geturl()

    @field_validator("heartbeat_stale_after_sec")
    @classmethod
    def heartbeat_threshold_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("heartbeat_stale_after_sec must be > 0")
        return value

    @model_validator(mode="after")
    def require_explicit_private_lan_opt_in(self) -> "DashboardConfig":
        if (
            not _is_loopback_host(self.host)
            and not self.private_lan_enabled
            and not self.container_internal_bind
        ):
            raise ValueError(
                "non-loopback dashboard bind requires private_lan_enabled=true"
            )
        if self.private_lan_enabled and "private-lan" not in self.allowed_hosts:
            raise ValueError(
                "private LAN mode requires allowed_hosts to include 'private-lan'"
            )
        if self.private_lan_enabled and not _is_local_or_private_host(self.host):
            raise ValueError("private LAN mode cannot bind to a public address")
        return self

    @field_validator("max_prompt_chars", "max_output_chars", "recent_runs_limit")
    @classmethod
    def positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value


def _is_loopback_host(host: str) -> bool:
    text = str(host or "").strip().lower()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _is_local_or_private_host(host: str) -> bool:
    text = str(host or "").strip().lower()
    if text in {"localhost", "0.0.0.0"}:
        return True
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return text.endswith(".local")
    return address.is_loopback or address.is_private or address.is_unspecified


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
    _config_project_root: Optional[Path] = PrivateAttr(default=None)

    def bind_config_project_root(self, project_root: str | Path) -> None:
        resolved = Path(project_root)
        if not resolved.is_absolute():
            raise ValueError("config project root must be absolute")
        self._config_project_root = resolved.resolve()

    def canonical_memory_root(self, *, project_root: str | Path | None = None) -> Path:
        configured = self.memory.canonical_sessions_root
        if configured is None:
            raise RuntimeError("memory.canonical_sessions_root is required")
        anchor = Path(project_root) if project_root is not None else self._config_project_root
        if anchor is None:
            raise RuntimeError("canonical memory project root is not bound")
        if not anchor.is_absolute():
            raise ValueError("canonical memory project root must be absolute")
        return (anchor.resolve() / configured).resolve()


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

    config_parent = cfg_path.resolve().parent
    project_root = config_parent.parent if config_parent.name == "config" else config_parent
    settings.bind_config_project_root(project_root)
    _validate_required(settings)
    return settings


def load_dashboard_config(
    config_path: str = "config/agent.yaml",
    env_file: Optional[str] = ".env",
) -> DashboardConfig:
    """Load only dashboard configuration without requiring an API credential."""
    if env_file is not None and Path(env_file).exists():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)
    raw: dict = {}
    path = Path(config_path)
    if path.exists():
        with path.open(encoding="utf-8") as file_handle:
            raw = dict((yaml.safe_load(file_handle) or {}).get("dashboard", {}))
    _apply_dashboard_env(raw)
    return DashboardConfig(**raw)


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

    _apply_dashboard_env(dashboard)


def _apply_dashboard_env(dashboard: dict) -> None:
    env_get = os.environ.get
    if value := env_get("DASHBOARD_HOST"):
        dashboard["host"] = value
    if value := env_get("DASHBOARD_PORT"):
        dashboard["port"] = int(value)
    if value := env_get("DASHBOARD_PRIVATE_LAN_ENABLED"):
        dashboard["private_lan_enabled"] = value.lower() in ("1", "true", "yes")
    if value := env_get("DASHBOARD_CONTAINER_INTERNAL_BIND"):
        dashboard["container_internal_bind"] = value.lower() in ("1", "true", "yes")
    if value := env_get("DASHBOARD_ALLOWED_HOSTS"):
        dashboard["allowed_hosts"] = [item.strip() for item in value.split(",") if item.strip()]
    if value := env_get("DASHBOARD_ALLOWED_ORIGINS"):
        dashboard["allowed_origins"] = [item.strip() for item in value.split(",") if item.strip()]
    if value := env_get("DASHBOARD_ENVIRONMENT_LABEL"):
        dashboard["environment_label"] = value
    if value := env_get("DASHBOARD_STARTUP_HEALTH_URL"):
        dashboard["startup_health_url"] = value
    if value := env_get("P42_ARENA_CONFIG_PATH"):
        dashboard["arena_config_path"] = value
    if value := env_get("P42_ARENA_STATE_PATH"):
        dashboard["arena_state_path"] = value
    if value := env_get("P42_HEARTBEAT_STALE_AFTER_SEC"):
        dashboard["heartbeat_stale_after_sec"] = int(value)


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
