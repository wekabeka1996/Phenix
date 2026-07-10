"""Read-only P42 dual-agent runtime projection for the Cockpit."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EvidenceClass = Literal[
    "REAL_EXTERNAL",
    "SHADOW",
    "STUB",
    "TEST",
    "BLOCKED",
    "UNKNOWN",
]
HeartbeatFreshness = Literal["FRESH", "STALE", "NEVER"]


class ArenaAgentSource(BaseModel):
    """Display subset consumed from the canonical P42 runtime YAML."""

    model_config = ConfigDict(extra="allow", frozen=True)

    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    runtime_kind: Literal["api", "cli"]
    symbols: list[str] = Field(..., min_length=1)
    heartbeat_cadence_sec: int = Field(..., ge=1)


class ArenaSourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    agents: dict[str, ArenaAgentSource] = Field(..., min_length=2)

    @model_validator(mode="after")
    def unique_agents_and_symbols(self) -> "ArenaSourceConfig":
        agent_ids = [agent.agent_id for agent in self.agents.values()]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent_id values must be unique")
        symbols = [symbol for agent in self.agents.values() for symbol in agent.symbols]
        if len(symbols) != len(set(symbols)):
            raise ValueError("symbol ownership must be non-overlapping")
        return self


class AgentRuntimeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_number: int
    runtime_kind: Literal["API", "CLI"]
    heartbeat_freshness: HeartbeatFreshness
    last_heartbeat: Optional[str]
    owned_symbols: list[str]
    current_state: str
    last_instruction_ack: Optional[dict[str, Any]]
    last_analysis_time: Optional[str]
    last_publication: Optional[dict[str, Any]]
    last_command_request: Optional[dict[str, Any]]
    last_fsm_result: Optional[dict[str, Any]]
    last_exchange_response: Optional[dict[str, Any]]
    exchange_evidence: EvidenceClass
    timeout_degraded_state: str


class SharedRuntimeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_session: Optional[str]
    testnet_environment: str
    portfolio_state: Optional[dict[str, Any]]
    open_orders: Optional[list[dict[str, Any]]]
    open_positions: Optional[list[dict[str, Any]]]
    pending_commands: Optional[list[dict[str, Any]]]
    symbol_ownership: dict[str, str]
    kill_switch_state: str
    last_reconciliation: Optional[dict[str, Any]]
    collective_publication_stream: list[dict[str, Any]]
    current_integration_sha: str
    exchange_evidence: EvidenceClass
    
    # P43A collective memory fields
    collective_state_version: int = 0
    symbol_leases: dict[str, Any] = Field(default_factory=dict)
    publication_cursors: dict[str, Any] = Field(default_factory=dict)
    last_checkpoint_id: Optional[str] = None
    recovery_state: str = "not_recovered"
    compression_statistics: Optional[dict[str, Any]] = None
    private_memory_status: dict[str, Any] = Field(default_factory=dict)


class ArenaRuntimeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str
    environment_label: str
    read_only: Literal[True] = True
    blocked_reasons: list[str]
    agents: list[AgentRuntimeView]
    shared: SharedRuntimeView


class ArenaControlRequest(BaseModel):
    """Identity-complete registered control request; never exchange authority."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    command_id: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    created_at: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    instruction_version: str = Field(..., min_length=1)
    collective_state_version: Optional[str] = None

    @field_validator("created_at")
    @classmethod
    def created_at_is_timezone_aware(cls, value: str) -> str:
        parsed = _parse_timestamp(value)
        if parsed is None:
            raise ValueError("created_at must be an ISO-8601 timestamp with timezone")
        return value


def load_arena_source_config(path: str | Path) -> ArenaSourceConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ArenaSourceConfig(**raw)


class ArenaRuntimeViewService:
    def __init__(
        self,
        *,
        root_dir: str | Path,
        config_path: str | Path,
        state_path: str | Path,
        environment_label: str,
        heartbeat_stale_after_sec: int,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.config_path = self.root_dir / config_path
        self.state_path = self.root_dir / state_path
        self.environment_label = environment_label
        self.heartbeat_stale_after_sec = heartbeat_stale_after_sec

    def build(self, *, events: Optional[list[dict[str, Any]]] = None) -> ArenaRuntimeView:
        now = datetime.now(timezone.utc)
        blocked: list[str] = []
        source: Optional[ArenaSourceConfig] = None
        state: dict[str, Any] = {}

        try:
            source = load_arena_source_config(self.config_path)
        except FileNotFoundError:
            blocked.append(f"runtime config missing: {self.config_path.as_posix()}")
        except Exception as exc:
            blocked.append(f"runtime config invalid: {exc}")

        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            blocked.append(f"runtime state missing: {self.state_path.as_posix()}")
        except Exception as exc:
            blocked.append(f"runtime state invalid: {exc}")

        event_rows = events or []
        agent_views: list[AgentRuntimeView] = []
        ownership: dict[str, str] = {}
        if source is not None:
            for key, agent in source.agents.items():
                ownership.update({symbol: agent.agent_id for symbol in agent.symbols})
                agent_state = (state.get("agents") or {}).get(key) or {}
                heartbeat = _optional_text(
                    agent_state.get("last_heartbeat") or agent_state.get("heartbeat_at")
                )
                freshness = _heartbeat_freshness(
                    heartbeat,
                    now=now,
                    stale_after_sec=self.heartbeat_stale_after_sec,
                )
                matching_events = _events_for_agent(event_rows, agent.agent_id)
                last_ack = _last_event(matching_events, {"INSTRUCTIONS_ACKED"})
                last_analysis = _last_event_matching(matching_events, "ANALYSIS")
                last_publication = _last_event_matching(matching_events, "PUBLICATION")
                last_command = _last_command_event(matching_events)
                last_fsm = _last_event_matching(matching_events, "FSM", "COMMAND_REJECTED", "COMMAND_CLOSED")
                last_exchange = _last_event_matching(matching_events, "EXCHANGE")
                if agent_state.get("last_exchange_response"):
                    last_exchange = _as_record(agent_state.get("last_exchange_response"))
                evidence = classify_exchange_evidence(last_exchange)
                degraded = str(agent_state.get("degraded_state") or "UNKNOWN")
                if freshness == "STALE":
                    degraded = "DEGRADED_STALE_HEARTBEAT"
                elif freshness == "NEVER" and not state:
                    degraded = "BLOCKED_NO_RUNTIME_STATE"
                agent_views.append(
                    AgentRuntimeView(
                        agent_id=agent.agent_id,
                        agent_number=agent.agent_number,
                        runtime_kind=agent.runtime_kind.upper(),
                        heartbeat_freshness=freshness,
                        last_heartbeat=heartbeat,
                        owned_symbols=list(agent.symbols),
                        current_state=str(agent_state.get("status") or "UNKNOWN"),
                        last_instruction_ack=_event_summary(last_ack),
                        last_analysis_time=_event_time(last_analysis),
                        last_publication=_event_summary(last_publication),
                        last_command_request=_event_summary(last_command),
                        last_fsm_result=_event_summary(last_fsm),
                        last_exchange_response=last_exchange,
                        exchange_evidence=evidence,
                        timeout_degraded_state=degraded,
                    )
                )

        shared = state.get("shared") or {}
        collective = [
            summary
            for event in event_rows
            if "PUBLICATION" in str(event.get("event_type") or "").upper()
            if (summary := _event_summary(event)) is not None
        ]
        all_evidence = [agent.exchange_evidence for agent in agent_views]
        shared_evidence = _strongest_evidence(all_evidence)
        return ArenaRuntimeView(
            generated_at=now.isoformat(),
            environment_label=self.environment_label,
            blocked_reasons=blocked,
            agents=agent_views,
            shared=SharedRuntimeView(
                active_session=_optional_text(state.get("session_id")),
                testnet_environment=(
                    "testnet"
                    if "TESTNET" in self.environment_label.upper()
                    else "UNKNOWN"
                ),
                portfolio_state=_as_optional_record(shared.get("portfolio_state")),
                open_orders=_as_optional_record_list(shared.get("open_orders")),
                open_positions=_as_optional_record_list(shared.get("open_positions")),
                pending_commands=_as_optional_record_list(shared.get("pending_commands")),
                symbol_ownership=ownership,
                kill_switch_state=str(shared.get("kill_switch_state") or "UNKNOWN"),
                last_reconciliation=_as_optional_record(shared.get("last_reconciliation")),
                collective_publication_stream=collective[-20:],
                current_integration_sha=_integration_sha(self.root_dir),
                exchange_evidence=shared_evidence,
                collective_state_version=int(state.get("collective_state_version", 0)),
                symbol_leases=dict(state.get("symbol_leases", {})),
                publication_cursors=dict(state.get("publication_cursors", {})),
                last_checkpoint_id=state.get("last_checkpoint_id"),
                recovery_state=str(state.get("recovery_state", "not_recovered")),
                compression_statistics=state.get("compression_statistics"),
                private_memory_status=dict(state.get("private_memory_status", {})),
            ),
        )


def classify_exchange_evidence(value: Any) -> EvidenceClass:
    if value is None:
        return "UNKNOWN"
    record = _as_record(value)
    text = json.dumps(record, ensure_ascii=False).lower()
    if record.get("external_verified") is True and not any(
        marker in text for marker in ("stub", "shadow", "synthetic", "mock", "test fixture")
    ):
        return "REAL_EXTERNAL"
    if "shadow" in text:
        return "SHADOW"
    if "stub" in text or "synthetic" in text:
        return "STUB"
    if "blocked" in text or "rejected_before_submit" in text:
        return "BLOCKED"
    if "mock" in text or "test fixture" in text or record.get("test_only") is True:
        return "TEST"
    return "UNKNOWN"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    text = _optional_text(value)
    if not text or text.lower() == "none":
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _heartbeat_freshness(value: Any, *, now: datetime, stale_after_sec: int) -> HeartbeatFreshness:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "NEVER"
    return "FRESH" if (now - parsed).total_seconds() <= stale_after_sec else "STALE"


def _events_for_agent(events: list[dict[str, Any]], agent_id: str) -> list[dict[str, Any]]:
    matching: list[dict[str, Any]] = []
    for event in events:
        metadata = event.get("metadata") or {}
        command = metadata.get("arena_command") or {}
        if metadata.get("agent_id") == agent_id or command.get("agent_id") == agent_id:
            matching.append(event)
    return matching


def _last_event(events: list[dict[str, Any]], event_types: set[str]) -> Optional[dict[str, Any]]:
    matches = [event for event in events if str(event.get("event_type")) in event_types]
    return matches[-1] if matches else None


def _last_event_matching(events: list[dict[str, Any]], *markers: str) -> Optional[dict[str, Any]]:
    upper_markers = tuple(marker.upper() for marker in markers)
    matches = [
        event
        for event in events
        if any(marker in str(event.get("event_type") or "").upper() for marker in upper_markers)
    ]
    return matches[-1] if matches else None


def _last_command_event(events: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    matches = [
        event
        for event in events
        if str(event.get("event_type") or "").startswith("agent_arena.")
        or "COMMAND" in str(event.get("event_type") or "").upper()
    ]
    return matches[-1] if matches else None


def _event_summary(event: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if event is None:
        return None
    metadata = event.get("metadata") or {}
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "created_at": event.get("created_at"),
        "status": metadata.get("status") or (metadata.get("arena_command") or {}).get("status"),
        "command_id": metadata.get("command_id") or (metadata.get("arena_command") or {}).get("command_id"),
        "instruction_version": metadata.get("manifest_version") or (metadata.get("arena_command") or {}).get("instruction_version"),
    }


def _event_time(event: Optional[dict[str, Any]]) -> Optional[str]:
    return _optional_text(event.get("created_at")) if event else None


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {"value": value}


def _as_optional_record(value: Any) -> Optional[dict[str, Any]]:
    return None if value is None else _as_record(value)


def _as_optional_record_list(value: Any) -> Optional[list[dict[str, Any]]]:
    if value is None:
        return None
    if not isinstance(value, list):
        return [{"value": value}]
    return [_as_record(item) for item in value]


def _optional_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _strongest_evidence(values: list[EvidenceClass]) -> EvidenceClass:
    for candidate in ("REAL_EXTERNAL", "SHADOW", "STUB", "TEST", "BLOCKED"):
        if candidate in values:
            return candidate  # type: ignore[return-value]
    return "UNKNOWN"


def _integration_sha(root_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    return result.stdout.strip() or "UNKNOWN"
