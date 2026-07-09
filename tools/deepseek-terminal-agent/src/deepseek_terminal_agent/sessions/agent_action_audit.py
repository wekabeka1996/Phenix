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
            "ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE", "OBSERVE", "AGENT_TESTNET_ORDER_REQUESTED"
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


class FSMHandoffGateway:
    """Performs FSM handoff validations and coordinates testnet order execution."""

    def __init__(self, registry: FSMAuditRegistry, execution_adapter: Any = None) -> None:
        self.registry = registry
        self.execution_adapter = execution_adapter

    def validate_and_transit(self, command: AgentActionCommand, journal: CommandAuditJournal) -> None:
        """Validates incoming command and transitions status from pending_fsm to accepted or rejected."""
        # Auto-transition from recorded to pending_fsm
        if command.status == "recorded":
            transit_status(command, "pending_fsm")

        if command.status != "pending_fsm":
            raise ValueError(f"Command must be in 'pending_fsm' status to transit, got '{command.status}'")

        # 1. Missing registry check
        if self.registry is None:
            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing registry")
            return

        # 2. Unknown event kind (verify registration)
        try:
            self.registry.verify_registration(command)
        except ValueError as e:
            journal.process_fsm_decision(command, accepted=False, reason=f"REJECTED: unknown event kind ({e})")
            return

        # 3. Missing agent identity
        if not command.agent_id or not command.session_id or command.agent_number is None:
            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing agent identity")
            return

        # 4. Non-testnet flag (testnet_only must be True)
        if not command.testnet_only:
            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: non-testnet flag")
            return

        # 5. Missing or invalid side check
        if command.command_kind in {"ENTRY", "AGENT_TESTNET_ORDER_REQUESTED"}:
            side = command.payload.get("side")
            if not side or str(side).upper() not in {"BUY", "SELL"}:
                journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing or invalid side (must be BUY or SELL)")
                return

        # 6. Missing explicit quantity/notional where required
        if command.command_kind in {"ENTRY", "AGENT_TESTNET_ORDER_REQUESTED"}:
            payload = command.payload
            qty = payload.get("quantity") or payload.get("qty")
            notional = payload.get("notional")
            if not qty and not notional:
                journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing explicit quantity/notional")
                return
            # Validate positive values
            if qty:
                try:
                    if float(qty) <= 0:
                        journal.process_fsm_decision(command, accepted=False, reason="REJECTED: invalid quantity <= 0")
                        return
                except (ValueError, TypeError):
                    journal.process_fsm_decision(command, accepted=False, reason="REJECTED: quantity must be float-castable")
                    return
            if notional:
                try:
                    if float(notional) <= 0:
                        journal.process_fsm_decision(command, accepted=False, reason="REJECTED: invalid notional <= 0")
                        return
                except (ValueError, TypeError):
                    journal.process_fsm_decision(command, accepted=False, reason="REJECTED: notional must be float-castable")
                    return

        # 7. No execution adapter available
        if self.execution_adapter is None:
            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: no execution adapter available")
            return

        # Check adapter base URL to prove it is testnet
        is_simulated = self.execution_adapter.__class__.__name__ == "SimulatedAdapter"
        if not is_simulated:
            base_url = getattr(self.execution_adapter, "base_url", "") or getattr(self.execution_adapter, "rest_url", "")
            if not base_url or "testnet" not in base_url.lower():
                journal.process_fsm_decision(command, accepted=False, reason="REJECTED: adapter base URL does not prove testnet")
                return

        # Passed all checks!
        journal.process_fsm_decision(command, accepted=True, reason="ACCEPTED: FSM handoff validated successfully")

    async def execute_testnet_order(self, command: AgentActionCommand, journal: CommandAuditJournal) -> Any:
        """Submits the accepted command to the exchange via the adapter and records the outcome."""
        if command.status != "accepted_by_fsm":
            raise ValueError(f"Command must be accepted_by_fsm to execute, got '{command.status}'")

        journal.submit_to_exchange(command, "Routing command to execution adapter")

        payload = command.payload
        symbol = payload.get("symbol") or payload.get("ticker")
        side = payload.get("side")
        order_type = payload.get("order_type") or "MARKET"
        quantity = str(payload.get("quantity") or payload.get("qty") or "")
        price = payload.get("price")
        time_in_force = payload.get("time_in_force") or payload.get("tif") or "GTC"
        reduce_only = bool(payload.get("reduce_only") or payload.get("reduceOnly"))
        close_position = bool(payload.get("close_position") or payload.get("closePosition"))
        client_order_id = payload.get("client_order_id") or payload.get("newClientOrderId") or command.command_id
        position_side = payload.get("position_side") or payload.get("positionSide")
        stop_price = payload.get("stop_price") or payload.get("stopPrice")
        working_type = payload.get("working_type") or payload.get("workingType")

        # Map to ExchangeOrderParams
        from vfoundation.core.adapters.base import ExchangeOrderParams
        params = ExchangeOrderParams(
            symbol=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=quantity,
            price=price,
            time_in_force=time_in_force.upper(),
            reduce_only=reduce_only,
            close_position=close_position,
            client_order_id=client_order_id,
            position_side=position_side,
            stop_price=stop_price,
            working_type=working_type,
        )

        try:
            resp = await self.execution_adapter.create_order(params)
            # Log exchange response
            logger.info(f"Exchange response received: {resp}")
            # Record success (exchange_ack)
            journal.record_exchange_response(command, ack=True, reason=f"Exchange ACK: {resp.order_id}")
            # Record lifecycle reference in command payload
            command.payload["exchange_order_id"] = resp.order_id
            command.payload["exchange_status"] = resp.status
            journal.close_command(command, "FSM handoff execution lifecycle closed")
            return resp
        except Exception as e:
            logger.error(f"Exchange order submission failed: {e}")
            # Record failure (exchange_reject)
            journal.record_exchange_response(command, ack=False, reason=f"Exchange REJECT: {e}")
            journal.close_command(command, "FSM handoff execution lifecycle closed after rejection")
            raise

