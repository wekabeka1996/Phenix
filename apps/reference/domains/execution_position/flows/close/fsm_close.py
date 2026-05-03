"""
FSMP-P1-T02: Close Flow FSM for execution_position domain.

States: OPENED -> CLOSE_COND -> EMIT_DEC_CLOSE -> DONE
Rules (stubs): exit_by_rule (time/event-driven)
Output: DEC:CLOSE(reduce_only=true)

Shadow-mode: decisions only, no live closures.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from apps.reference.core.time import get_clock
from .close_producer_bridge import (
    CLOSE_PRODUCER_BRIDGE_CONTRACT,
    CLOSE_PRODUCER_BRIDGE_PATH,
    CloseProducerBridgeError,
    adapt_cmd_close_to_dec_close,
    build_close_producer_bridge_trace_ref,
)
from apps.reference.telemetry.shadow_journal import (
    get_shadow_journal,
    snapshot_close_flow_state,
)
from vfoundation.core.protocol import Message


LOG = logging.getLogger("apps.reference.domains.execution_position.fsm_close")


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
        self.last_close_reason: Optional[str] = None
        self.last_close_qty: Optional[str] = None
        self.last_close_symbol: Optional[str] = None
        self._shadow_journal: Optional[Any] = None
        self._metrics: Dict[str, int] = {
            "fsm_close_decisions_total": 0,
            "fsm_errors_total": 0,
            "fsm_close_bridge_rejects_total": 0,
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
                position_data["open_ts"] if "open_ts" in position_data else get_clock(
                ).now_sec()
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

    def _handle_cmd_close_producer_branch(self, msg: Message) -> Optional[Message]:
        """Pure producer branch for explicit CMD:CLOSE -> DEC:CLOSE adaptation."""
        try:
            intake, emission, result = adapt_cmd_close_to_dec_close(msg)
        except CloseProducerBridgeError as exc:
            reject_ref = build_close_producer_bridge_trace_ref(
                status="reject",
                qty_present=False,
                preserved_idempotent_key=False,
                preserved_command_trigger=False,
                reason="intake_validation",
            )
            existing_refs = list(getattr(msg, "data_ref", None) or [])
            if reject_ref not in existing_refs:
                existing_refs.append(reject_ref)
                try:
                    msg.data_ref = existing_refs
                except Exception:
                    pass
            self._metrics["fsm_errors_total"] += 1
            self._metrics["fsm_close_bridge_rejects_total"] += 1
            LOG.error(
                "CLOSE_PRODUCER_BRIDGE_REJECT: contract=%s path=%s rid=%s reason=%s details=%s",
                CLOSE_PRODUCER_BRIDGE_CONTRACT,
                CLOSE_PRODUCER_BRIDGE_PATH,
                getattr(msg, "rid", None),
                "intake_validation",
                exc,
            )
            return None

        self.state = CloseState.CLOSE_COND
        self.state = CloseState.EMIT_DEC_CLOSE
        self._metrics["fsm_close_decisions_total"] += 1
        self.last_close_reason = emission.reason
        self.last_close_qty = emission.qty
        self.last_close_symbol = emission.symbol
        LOG.info(
            "CLOSE_PRODUCER_BRIDGE_SUCCESS: contract=%s path=%s rid=%s symbol=%s trigger=%s idempotent_key=%s",
            CLOSE_PRODUCER_BRIDGE_CONTRACT,
            CLOSE_PRODUCER_BRIDGE_PATH,
            getattr(msg, "rid", None),
            emission.symbol,
            intake.trigger,
            emission.idempotent_key,
        )
        self.state = CloseState.DONE
        self.position_active = False
        return result

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:CLOSE if rules trigger.

        Args:
            msg: EVT:FILL|REJECTED|EXPIRED|UPD:* (including UPD:TICK for timer) or CMD:CLOSE

        Returns:
            DEC:CLOSE if rules trigger, None otherwise.
        """
        journal = get_shadow_journal(self)
        before = snapshot_close_flow_state(
            self) if journal is not None else None
        result: Optional[Message] = None
        try:
            if msg.op == "CMD" and msg.verb == "CLOSE":
                result = self._handle_cmd_close_producer_branch(msg)
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
                after = snapshot_close_flow_state(self)
                if result is not None:
                    # OUTPUT record: authoritative state-change record
                    journal.record_transition(
                        event_name=f"{result.op}:{result.verb}",
                        source_component="execution_position.fsm_close",
                        source_path="execution:close_flow_output",
                        event_origin_type="execution",
                        truth_owner="CloseFlowFSM",
                        payload=result.pld or {},
                        rid=getattr(result, "rid", None) or getattr(
                            msg, "rid", None),
                        before=before,
                        after=after,
                        notes=[f"input={msg.op}:{msg.verb}"],
                    )
                # INPUT record: triggering event context only (no transition window)
                notes = ["record_role=input"]
                if result is not None:
                    notes.append(f"result={result.op}:{result.verb}")
                journal.record_transition(
                    event_name=f"{msg.op}:{msg.verb}",
                    source_component="execution_position.fsm_close",
                    source_path="execution:close_flow_input",
                    event_origin_type="execution",
                    truth_owner="CloseFlowFSM",
                    payload=msg.pld or {},
                    rid=getattr(msg, "rid", None),
                    before=None,
                    after=None,
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

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def reset(self):
        """Reset the close flow to a flat, reusable runtime state."""
        self.state = CloseState.FLAT
        self.position_open_ts = 0.0
        self.position_active = False
        self.last_close_reason = None
        self.last_close_qty = None
        self.last_close_symbol = None
