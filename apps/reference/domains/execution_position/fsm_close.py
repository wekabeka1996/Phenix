"""
FSMP-P1-T02: Close Flow FSM for execution_position domain.

States: OPENED → CLOSE_COND → EMIT_DEC_CLOSE → DONE
Rules (stubs): exit_by_rule (time/event-driven)
Output: DEC:CLOSE(reduce_only=true)

Shadow-mode: decisions only, no live closures.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Dict, Any, Optional

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock

from vfoundation.core.protocol import Message


class CloseState(str, Enum):
    """FSM states for close flow."""

    FLAT = "FLAT"
    OPENED = "OPENED"
    CLOSE_COND = "CLOSE_COND"
    EMIT_DEC_CLOSE = "EMIT_DEC_CLOSE"
    DONE = "DONE"
    ERROR = "ERROR"


class CloseFlowFSM:
    """
    Close Flow FSM: monitors conditions and emits DEC:CLOSE.

    Role:
    1. Execution: Processes CMD:CLOSE from Decision Making.
    2. Technical: Handles REJECTED/EXPIRED events.
    
    Note: Autonomous failsafe closing (max_hold_sec) was removed in P2.
    This domain follows the "soldier" pattern — only executes explicit CMD:CLOSE.
    """

    def __init__(self):
        self.state = CloseState.FLAT
        self.position_open_ts: float = 0.0
        self.position_active = False
        self._metrics: Dict[str, int] = {
            "fsm_close_decisions_total": 0,
            "fsm_errors_total": 0,
        }

    def hydrate(self, position_data: Dict[str, Any]):
        """
        Hydrate the FSM state from a position snapshot.
        """
        try:
            # If a position exists, the FSM should be active.
            self.state = CloseState.OPENED
            self.position_active = True
            self.position_open_ts = float(
                position_data["open_ts"] if "open_ts" in position_data else get_clock().now_sec())

            print(
                f"[CloseFlowFSM] Hydrated state for position: open_ts={self.position_open_ts}"
            )

        except Exception as e:
            self.state = CloseState.ERROR
            self._metrics["fsm_errors_total"] += 1
            print(
                f"[CloseFlowFSM] HYDRATION_ERROR: Failed to hydrate state: {e}")

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:CLOSE if rules trigger.

        Args:
            msg: EVT:FILL|REJECTED|EXPIRED|UPD:* (including UPD:TICK for timer) or CMD:CLOSE

        Returns:
            DEC:CLOSE if rules trigger, None otherwise.
        """
        # Handle manual close commands
        if msg.op == "CMD" and msg.verb == "CLOSE":
            # Always emit DEC:CLOSE on CMD:CLOSE; actual position existence is verified
            # downstream (adapter/open-positions check) for idempotent safety.
            cmd_pld = msg.pld or {}
            return self._emit_close(
                msg,
                "MANUAL_CLOSE",
                {
                    "trigger": "CMD:CLOSE",
                    "reason": cmd_pld.get("reason"),
                    "qty": cmd_pld.get("qty"),
                    "trace": cmd_pld.get("trace"),
                },
            )

        if msg.op not in ("EVT", "UPD"):
            return None

        # State transition: FLAT → OPENED on FILL or PARTIAL_FILL
        if self.state == CloseState.FLAT and msg.verb in ("TRADE_EXECUTED", "PARTIAL_FILL"):
            # Check if this actually opened a position (qty > 0)
            pld = msg.pld or {}
            qty_raw = pld.get("qty", 0)
            qty = Decimal(str(qty_raw)) if qty_raw else Decimal("0")
            if qty > 0:
                self.position_active = True
                self.position_open_ts = get_clock().now_sec()
                self.state = CloseState.OPENED
                # Log the transition reason
                transition_reason = (
                    "PARTIAL_FILL" if msg.verb == "PARTIAL_FILL" else "TRADE_EXECUTED"
                )
                print(
                    f"[CloseFlowFSM] Transitioned to OPENED on {transition_reason}, qty={qty}"
                )
                # Immediately check close conditions on the fill event itself
                return self._check_close_conditions(msg)

        # Check close conditions in OPENED state
        if self.state == CloseState.OPENED:
            return self._check_close_conditions(msg)

        return None

    def _check_close_conditions(self, msg: Message) -> Optional[Message]:
        """
        Check stub close rules.
        
        NOTE: Autonomous closing rules (max_hold_sec, REJECTED, EXPIRED) are disabled
        per "soldier" pattern requirements. This domain only executes CMD:CLOSE.

        Returns:
            None (autonomous closing disabled).
        """
        return None

    def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:CLOSE with reduce_only=true and include symbol when available."""
        self.state = CloseState.CLOSE_COND
        self.state = CloseState.EMIT_DEC_CLOSE
        self._metrics["fsm_close_decisions_total"] += 1

        symbol = (msg.pld or {}).get("symbol")

        dec = Message(
            op="DEC",
            verb="CLOSE",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_{why}_{int(get_clock().now_sec())}",
            pld={
                "reduce_only": True,
                **({"symbol": symbol} if symbol else {}),
                **details,
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

        # Update state
        self.state = CloseState.DONE
        self.position_active = False
        return dec

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = CloseState.FLAT
        self.position_open_ts = 0.0
        self.position_active = False
