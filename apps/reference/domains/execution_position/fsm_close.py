"""
FSMP-P1-T02: Close Flow FSM for execution_position domain.

States: OPENED -> CLOSE_COND -> EMIT_DEC_CLOSE -> DONE
Rules (stubs): exit_by_rule (time/event-driven)
Output: DEC:CLOSE(reduce_only=true)

Shadow-mode: decisions only, no live closures.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.shadow_journal import (
    get_shadow_journal,
    snapshot_close_flow_state,
)
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
    This domain follows the "soldier" pattern - only executes explicit CMD:CLOSE.
    """

    def __init__(self):
        self.state = CloseState.FLAT
        self.position_open_ts: float = 0.0
        self.position_active = False
        self._shadow_journal: Optional[Any] = None
        self._metrics: Dict[str, int] = {
            "fsm_close_decisions_total": 0,
            "fsm_errors_total": 0,
        }

    def set_shadow_journal(self, journal: Any) -> None:
        self._shadow_journal = journal

    def hydrate(self, position_data: Dict[str, Any]):
        """
        Hydrate the FSM state from a position snapshot.
        """
        try:
            self.state = CloseState.OPENED
            self.position_active = True
            self.position_open_ts = float(
                position_data["open_ts"] if "open_ts" in position_data else get_clock().now_sec()
            )

            print(
                f"[CloseFlowFSM] Hydrated state for position: open_ts={self.position_open_ts}"
            )

        except Exception as e:
            self.state = CloseState.ERROR
            self._metrics["fsm_errors_total"] += 1
            print(
                f"[CloseFlowFSM] HYDRATION_ERROR: Failed to hydrate state: {e}"
            )

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:CLOSE if rules trigger.

        Args:
            msg: EVT:FILL|REJECTED|EXPIRED|UPD:* (including UPD:TICK for timer) or CMD:CLOSE

        Returns:
            DEC:CLOSE if rules trigger, None otherwise.
        """
        journal = get_shadow_journal(self)
        before = snapshot_close_flow_state(self) if journal is not None else None
        result: Optional[Message] = None
        try:
            if msg.op == "CMD" and msg.verb == "CLOSE":
                cmd_pld = msg.pld or {}
                result = self._emit_close(
                    msg,
                    "MANUAL_CLOSE",
                    {
                        "trigger": "CMD:CLOSE",
                        "reason": cmd_pld.get("reason"),
                        "qty": cmd_pld.get("qty"),
                        "trace": cmd_pld.get("trace"),
                    },
                )
                return result

            if msg.op not in ("EVT", "UPD"):
                return None

            if self.state == CloseState.FLAT and msg.verb in ("TRADE_EXECUTED", "PARTIAL_FILL"):
                pld = msg.pld or {}
                qty_raw = pld.get("qty", 0)
                qty = Decimal(str(qty_raw)) if qty_raw else Decimal("0")
                if qty > 0:
                    self.position_active = True
                    self.position_open_ts = get_clock().now_sec()
                    self.state = CloseState.OPENED
                    transition_reason = (
                        "PARTIAL_FILL" if msg.verb == "PARTIAL_FILL" else "TRADE_EXECUTED"
                    )
                    print(
                        f"[CloseFlowFSM] Transitioned to OPENED on {transition_reason}, qty={qty}"
                    )
                    result = self._check_close_conditions(msg)
                    return result

            if self.state == CloseState.OPENED:
                result = self._check_close_conditions(msg)
                return result

            return None
        finally:
            if journal is not None:
                notes = []
                if result is not None:
                    notes.append(f"result={result.op}:{result.verb}")
                journal.record_transition(
                    event_name=f"{msg.op}:{msg.verb}",
                    source_component="execution_position.fsm_close",
                    source_path="execution:close_flow_handle",
                    event_origin_type="execution",
                    truth_owner="CloseFlowFSM",
                    payload=msg.pld or {},
                    rid=getattr(msg, "rid", None),
                    before=before,
                    after=snapshot_close_flow_state(self),
                    notes=notes,
                )

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
            data_ref=msg.data_ref.copy() if msg.data_ref else [],
        )

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
