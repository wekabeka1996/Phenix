"""FSM and Event-First Agent Invariant Auditing."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

CommandStatus = Literal[
    "recorded",
    "pending_fsm",
    "accepted_by_fsm",
    "rejected_by_fsm",
    "submitted_testnet",
    "exchange_ack",
    "exchange_reject",
    "lifecycle_closed",
]

ALLOWED_TRANSITIONS: dict[CommandStatus, set[CommandStatus]] = {
    "recorded": {"pending_fsm", "accepted_by_fsm", "rejected_by_fsm"},
    "pending_fsm": {"accepted_by_fsm", "rejected_by_fsm"},
    "accepted_by_fsm": {"submitted_testnet", "exchange_reject"},
    "rejected_by_fsm": {"lifecycle_closed"},
    "submitted_testnet": {"exchange_ack", "exchange_reject"},
    "exchange_ack": {"lifecycle_closed"},
    "exchange_reject": {"lifecycle_closed"},
    "lifecycle_closed": set(),
}


class AdapterCapability(BaseModel):
    """Explicit adapter capability descriptor."""
    model_config = ConfigDict(extra="forbid")

    adapter_id: str = Field(..., min_length=1)
    environment: Literal["testnet", "sandbox", "mainnet", "unknown"]
    order_submit_enabled: bool
    no_order_observation_mode: bool
    supports_cancel: bool
    supports_close: bool
    source_of_truth: str = Field(..., min_length=1)
    checked_at: str = Field(..., min_length=1)


AdapterCapabilityDescriptor = AdapterCapability


def log_rejection(command: AgentActionCommand, reason: str) -> None:
    """Persists rejection reason into session-specific and global auditable ledgers."""
    import json
    import pathlib

    timestamp = datetime.now(timezone.utc).isoformat()
    record = {
        "agent_id": command.agent_id or "unknown",
        "session_id": command.session_id or "unknown",
        "command_id": command.command_id or "unknown",
        "event_id": command.event_id or "unknown",
        "agent_number": command.agent_number,
        "rationale": command.rationale or "unknown",
        "reason": reason,
        "timestamp": timestamp,
    }

    session_id = command.session_id or "unknown"

    # Write to session-specific ledger
    try:
        session_dir = pathlib.Path(".agent_memory") / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        session_path = session_dir / "audit_rejections.jsonl"
        with open(session_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"Failed to write rejection to session ledger: {e}")

    # Write to global audit log
    try:
        global_dir = pathlib.Path(".agent_memory")
        global_dir.mkdir(parents=True, exist_ok=True)
        global_path = global_dir / "audit_rejections.jsonl"
        with open(global_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"Failed to write rejection to global ledger: {e}")


def verify_handoff_safety(
    command: AgentActionCommand,
    descriptor: Optional[AdapterCapability],
    no_order_observation_mode: Optional[bool] = None,
    base_url: Optional[str] = None,
) -> None:
    """Verifies FSM handoff safety parameters and capability descriptors."""
    try:
        # 1. Identity validation
        if (
            not command.agent_id or not str(command.agent_id).strip() or
            not command.session_id or not str(command.session_id).strip() or
            not command.command_id or not str(command.command_id).strip() or
            not command.event_id or not str(command.event_id).strip() or
            command.agent_number is None or command.agent_number < 0
        ):
            raise ValueError("command lacks identity fields")

        # 2. Missing descriptor
        if descriptor is None:
            raise ValueError("capability descriptor is missing")

        # 3. Environment validation
        if descriptor.environment not in ("testnet", "sandbox"):
            raise ValueError(f"invalid environment: {descriptor.environment}")

        # 4. Descriptor-owned adapter submit gates
        no_order_active = (
            descriptor.no_order_observation_mode
            if no_order_observation_mode is None
            else descriptor.no_order_observation_mode or no_order_observation_mode
        )
        if no_order_active:
            raise ValueError("no_order_observation_mode is active")

        if not descriptor.order_submit_enabled:
            raise ValueError("adapter capability disables order submit")

        # 5. Quantity / Notional validation for order submissions
        is_order_submit = command.command_kind.upper() in {"ENTRY", "ORDER", "FULL_CLOSE", "PARTIAL_CLOSE"} or any(
            x in command.command_kind.lower() for x in ("order_request", "close_request")
        )
        if is_order_submit:
            payload = command.payload or {}
            qty_val = None
            for k, v in payload.items():
                if k.lower() in ("qty", "quantity", "notional"):
                    qty_val = v
                    break

            if qty_val is None:
                raise ValueError("command lacks explicit configured quantity/notional")
            try:
                numeric_qty = float(qty_val)
                if numeric_qty <= 0:
                    raise ValueError("command lacks explicit configured quantity/notional")
            except (ValueError, TypeError):
                raise ValueError("command lacks explicit configured quantity/notional")

        # 6. Secondary URL checks
        if base_url:
            base_url_lower = base_url.lower()
            prod_domains = ("api.binance.com", "fapi.binance.com", "dapi.binance.com", "api-gcp.binance.com", "api.binance.us")
            if any(domain in base_url_lower for domain in prod_domains):
                raise ValueError("production URL detected in base_url")

    except ValueError as err:
        reason = str(err)
        if command.status in ("recorded", "pending_fsm"):
            try:
                transit_status(command, "rejected_by_fsm")
            except Exception:
                pass
        log_rejection(command, reason)
        raise



class AgentActionCommand(BaseModel):
    """Event-backed agent action command representing the attribution data."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(..., min_length=1)
    command_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    command_kind: str = Field(..., min_length=1)
    testnet_only: bool = True
    status: CommandStatus = "recorded"
    rationale: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("testnet_only")
    @classmethod
    def must_be_testnet(cls, value: bool) -> bool:
        """Enforces that all execution-intent commands are testnet only."""
        if not value:
            raise ValueError("testnet_only must be True. Mainnet/Live trading is prohibited.")
        return value

    @field_validator("payload")
    @classmethod
    def reject_forbidden_or_credentials(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Recursively checks and blocks credentials, secrets, or api key fields in payload."""
        cls._validate_no_secrets(value)
        return value

    @classmethod
    def _validate_no_secrets(cls, value: Any, path: str = "payload") -> None:
        if isinstance(value, dict):
            for k, val in value.items():
                k_lower = str(k).lower()
                child_path = f"{path}.{k_lower}" if path else k_lower
                # Reject credential keys
                if any(sec in k_lower for sec in ("api_key", "apikey", "secret", "private_key", "password", "token", "credential")):
                    raise ValueError(f"Forbidden credential/secret field detected: {child_path}")
                cls._validate_no_secrets(val, path=child_path)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                cls._validate_no_secrets(item, path=f"{path}[{idx}]")


def transit_status(command: AgentActionCommand, target: CommandStatus) -> None:
    """Transitions command status enforcing strict FSM state transitions."""
    current = command.status
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(
            f"Invalid state transition from '{current}' to '{target}'. "
            f"Allowed: {ALLOWED_TRANSITIONS[current]}"
        )
    command.status = target


class FSMAuditRegistry:
    """Validates FSM registrations for agent action command types."""

    def __init__(self, registered_kinds: Optional[set[str]] = None) -> None:
        self.registered_kinds = registered_kinds or {
            "ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE", "OBSERVE"
        }

    def verify_registration(self, command: AgentActionCommand) -> None:
        """Verifies if the command kind is registered. Fails closed on missing registration."""
        if command.command_kind not in self.registered_kinds:
            command.status = "pending_fsm"
            raise ValueError(
                f"FSM registration missing for command_kind '{command.command_kind}'. "
                f"Failing closed. Status updated to pending_fsm."
            )


class CommandAuditJournal:
    """Reconstructs sequence history for event-backed commands."""

    def __init__(self, registry: FSMAuditRegistry) -> None:
        self.registry = registry
        self.history: list[tuple[datetime, CommandStatus, str]] = []

    def record_request(self, command: AgentActionCommand, reason: str = "Requested") -> None:
        """Starts sequence tracking by verifying FSM registration."""
        self.history.append((datetime.now(timezone.utc), command.status, reason))
        try:
            self.registry.verify_registration(command)
        except ValueError as err:
            self.history.append((datetime.now(timezone.utc), command.status, f"Registration failed: {err}"))
            raise

    def process_fsm_decision(self, command: AgentActionCommand, accepted: bool, reason: str = "") -> None:
        """FSM evaluation stage."""
        target: CommandStatus = "accepted_by_fsm" if accepted else "rejected_by_fsm"
        transit_status(command, target)
        self.history.append((datetime.now(timezone.utc), command.status, reason or f"FSM decided: {target}"))

    def verify_handoff_safety(
        self,
        command: AgentActionCommand,
        descriptor: Optional[AdapterCapability],
        no_order_observation_mode: Optional[bool] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """Verifies safety parameters and records transition on failure."""
        try:
            verify_handoff_safety(command, descriptor, no_order_observation_mode, base_url)
        except ValueError as err:
            self.history.append((datetime.now(timezone.utc), command.status, f"Safety check failed: {err}"))
            raise

    def submit_to_exchange(self, command: AgentActionCommand, reason: str = "Submitted") -> None:
        """Testnet submission stage."""
        transit_status(command, "submitted_testnet")
        self.history.append((datetime.now(timezone.utc), command.status, reason))

    def record_exchange_response(self, command: AgentActionCommand, ack: bool, reason: str = "") -> None:
        """Exchange callback handling stage."""
        target: CommandStatus = "exchange_ack" if ack else "exchange_reject"
        transit_status(command, target)
        self.history.append((datetime.now(timezone.utc), command.status, reason or f"Exchange response: {target}"))

    def close_command(self, command: AgentActionCommand, reason: str = "Closed") -> None:
        """Terminal close stage."""
        transit_status(command, "lifecycle_closed")
        self.history.append((datetime.now(timezone.utc), command.status, reason))
