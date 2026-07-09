"""Pydantic schemas and contract validations for P37B Event-First Agent Arena."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now_iso() -> str:
    """Returns the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class AgentArenaCommandEnvelope(BaseModel):
    """Command/Event contract envelope for Agent Testnet actions."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(default_factory=lambda: f"event-{uuid.uuid4().hex}")
    command_id: str = Field(default_factory=lambda: f"cmd-{uuid.uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    created_at: str = Field(default_factory=utc_now_iso)
    received_at: Optional[str] = None
    symbol: Optional[str] = None
    command_kind: Literal[
        "AGENT_ARENA_COMMAND_REQUESTED",
        "AGENT_ARENA_COMMAND_REJECTED",
        "AGENT_ARENA_COMMAND_ACCEPTED",
        "AGENT_TESTNET_ORDER_REQUESTED",
        "AGENT_TESTNET_CANCEL_REQUESTED",
        "AGENT_TESTNET_CLOSE_REQUESTED",
        "AGENT_ARENA_RATIONALE_RECORDED",
        "AGENT_ARENA_SOS_EMITTED"
    ]
    rationale: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    testnet_only: Literal[True] = True
    execution_authority: Literal["agent_testnet_arena"] = "agent_testnet_arena"
    source: Literal["cockpit", "cli", "api", "subagent"]

    @model_validator(mode="after")
    def validate_arena_contract(self) -> AgentArenaCommandEnvelope:
        # Check 1: Forbidden live/mainnet flags recursively in payload
        def check_live_flags(val: Any):
            if isinstance(val, dict):
                for k, v in val.items():
                    k_lower = str(k).strip().lower()
                    if k_lower in ("mainnet", "live", "production", "prod", "real"):
                        if v is True or str(v).strip().lower() in ("true", "yes", "1", "live", "mainnet"):
                            raise ValueError("Forbidden field: live/mainnet trading flags are prohibited.")
                    check_live_flags(v)
            elif isinstance(val, list):
                for item in val:
                    check_live_flags(item)

        check_live_flags(self.payload)

        # Check 2: Forbidden raw exchange credentials recursively in payload
        forbidden_cred_keys = {
            "api_key", "secret", "api_secret", "passphrase", "token",
            "credentials", "password", "private_key", "secret_key"
        }
        def check_credentials(val: Any):
            if isinstance(val, dict):
                for k, v in val.items():
                    k_lower = str(k).strip().lower()
                    if k_lower in forbidden_cred_keys:
                        raise ValueError(f"Forbidden field: raw exchange credentials key '{k}' is prohibited.")
                    check_credentials(v)
            elif isinstance(val, list):
                for item in val:
                    check_credentials(item)

        check_credentials(self.payload)

        # Check 3: Symbol is mandatory depending on specific command
        if self.command_kind in (
            "AGENT_TESTNET_ORDER_REQUESTED",
            "AGENT_TESTNET_CLOSE_REQUESTED",
            "AGENT_TESTNET_CANCEL_REQUESTED"
        ):
            if not self.symbol or not self.symbol.strip():
                raise ValueError(f"Symbol is required for command kind: {self.command_kind}")

        # Check 4: Explicit quantities and prices for order requests (prevent defaults)
        if self.command_kind == "AGENT_TESTNET_ORDER_REQUESTED":
            qty = self.payload.get("quantity") if "quantity" in self.payload else self.payload.get("qty")
            notional = self.payload.get("notional")
            if qty is None and notional is None:
                raise ValueError("Implicit order defaults prohibited: either 'quantity' or 'notional' must be explicitly provided in payload.")
            if qty is not None:
                try:
                    qty_val = float(qty)
                except (TypeError, ValueError):
                    raise ValueError("Quantity must be a positive numeric value.")
                if qty_val <= 0:
                    raise ValueError("Quantity must be positive and non-zero.")
            if notional is not None:
                try:
                    notional_val = float(notional)
                except (TypeError, ValueError):
                    raise ValueError("Notional must be a positive numeric value.")
                if notional_val <= 0:
                    raise ValueError("Notional must be positive and non-zero.")

            # Ensure order type is explicit
            order_type = self.payload.get("order_type")
            if not order_type:
                raise ValueError("Implicit order defaults prohibited: 'order_type' must be explicitly specified in payload.")

            # If LIMIT order, price must be explicit and positive
            if str(order_type).upper() == "LIMIT":
                price = self.payload.get("price")
                if price is None:
                    raise ValueError("Implicit order defaults prohibited: 'price' is required for LIMIT orders.")
                try:
                    price_val = float(price)
                except (TypeError, ValueError):
                    raise ValueError("Price must be a positive numeric value for LIMIT orders.")
                if price_val <= 0:
                    raise ValueError("Price must be positive and non-zero for LIMIT orders.")

        # Check 5: Explicit cancel reference (cancel requested)
        if self.command_kind == "AGENT_TESTNET_CANCEL_REQUESTED":
            exch_id = self.payload.get("exchange_order_id")
            cli_id = self.payload.get("client_order_id")
            if not exch_id and not cli_id:
                raise ValueError("Cancel request must specify either 'exchange_order_id' or 'client_order_id' explicitly.")

        return self
