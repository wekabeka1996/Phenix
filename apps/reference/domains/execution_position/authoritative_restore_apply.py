"""
Package 6B — Authoritative Restore Apply

Owns the mutating authoritative-apply contour for execution position restore.
Receives a parsed ExecutionPositionRestoreLifecycleRecord (produced by 6A read/parse)
and writes authoritative restore truth into live FSM runtime state.

Boundary contract:
- 6A (startup_truth_orchestrator) reads, parses, compares, persists — does NOT mutate runtime.
- 6B (this module) applies each parsed record into live manage_flow / close_flow /
  truth-source / bracket state.
- 6C (future) handles guardian reconcile and bracket reconstruction AFTER 6B apply.

This module must NOT:
- read or parse the artifact file (that is 6A's domain),
- perform guardian reconcile or bracket reconstruction (that is 6C),
- absorb the runtime dual-use close reset (_apply_authoritative_local_close_reset stays in FSM),
- absorb generic shell helpers (_set_manage_truth_source, _clear_manage_truth_source stay in FSM).
"""

import logging
from typing import TYPE_CHECKING

from apps.reference.domains.execution_position.restore_artifact import (
    BRACKET_STATE_DEFERRED_PENDING_WAL,
    BRACKET_STATE_LINKED_ACTIVE,
    BRACKET_STATE_PARTIAL_LINKAGE,
    BRACKET_STATE_UNKNOWN,
    RESTORE_PHASE_UNKNOWN,
    ExecutionPositionRestoreAuthoritativeSymbolStatus,
    ExecutionPositionRestoreLifecycleRecord,
    TRUTH_SOURCE_RESTORE_ARTIFACT,
)
from .fsm_manage import ManageState
from .fsm_close import CloseState

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(__name__)


class AuthoritativeRestoreApply:
    """Package 6B: applies authoritative restore records into live FSM runtime state.

    Each call to `apply_record` takes one lifecycle record (provided by 6A after
    reading and parsing the restore artifact) and writes the authoritative truth
    for that symbol into live manage_flow, close_flow, truth-source, and bracket state.

    This class is a pure mutating applier. It accesses FSM state exclusively through
    the FSM's sanctioned shell helpers (_get_or_create_manage_flow,
    _get_or_create_close_flow, _set_manage_truth_source, _clear_symbol_brackets,
    _pending_brackets read-only). It introduces no new private-state sprawl.
    """

    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm

    def apply_record(
        self,
        record: ExecutionPositionRestoreLifecycleRecord,
    ) -> ExecutionPositionRestoreAuthoritativeSymbolStatus:
        """Apply one authoritative restore lifecycle record into live FSM state.

        Mutates:
          - manage_flow.state (ManageState)
          - manage_flow.symbol
          - _symbol_manage_truth_source[symbol] → TRUTH_SOURCE_RESTORE_ARTIFACT
          - close_flow.state (CloseState)
          - close_flow.position_active
          - _symbol_brackets[symbol] (cleared before adoption)
          - _symbol_bracket_truth_source[symbol] (cleared before adoption)

        Reads (no mutation):
          - _pending_brackets (WAL cross-check for DEFERRED_PENDING_WAL)

        Returns ExecutionPositionRestoreAuthoritativeSymbolStatus with exact/unknown
        restore status per field.
        """
        symbol_key = str(record.symbol or "").strip().upper()
        symbol_status = ExecutionPositionRestoreAuthoritativeSymbolStatus(
            symbol=symbol_key,
            manage_phase_value=RESTORE_PHASE_UNKNOWN,
            close_phase_value=RESTORE_PHASE_UNKNOWN,
            bracket_state_value=BRACKET_STATE_UNKNOWN,
            live_reconcile_required=bool(record.live_reconcile_required),
            deferred_entry_order_id=(
                str(record.deferred_bracket_ref.entry_order_id).strip()
                if record.deferred_bracket_ref is not None
                else None
            ),
        )

        # --- Manage phase apply ---
        manage_phase = str(record.manage_phase or "").strip().upper() or RESTORE_PHASE_UNKNOWN
        if manage_phase == RESTORE_PHASE_UNKNOWN:
            symbol_status.manage_phase_value = RESTORE_PHASE_UNKNOWN
            symbol_status.manage_phase_restore_status = "unknown"
        else:
            try:
                manage_state = ManageState(manage_phase)
            except Exception:
                symbol_status.unresolved_reasons.append(
                    f"unsupported_manage_phase:{manage_phase}"
                )
            else:
                manage_flow = self._fsm._get_or_create_manage_flow(symbol_key)
                manage_flow.state = manage_state
                manage_flow.symbol = symbol_key
                self._fsm._set_manage_truth_source(
                    symbol_key, TRUTH_SOURCE_RESTORE_ARTIFACT
                )
                symbol_status.manage_phase_value = manage_state.value
                symbol_status.manage_phase_restore_status = "exact"

        # --- Close phase apply ---
        close_phase = str(record.close_phase or "").strip().upper() or RESTORE_PHASE_UNKNOWN
        if close_phase == RESTORE_PHASE_UNKNOWN:
            symbol_status.close_phase_value = RESTORE_PHASE_UNKNOWN
            symbol_status.close_phase_restore_status = "unknown"
        else:
            try:
                close_state = CloseState(close_phase)
            except Exception:
                symbol_status.unresolved_reasons.append(
                    f"unsupported_close_phase:{close_phase}"
                )
            else:
                close_flow = self._fsm._get_or_create_close_flow(symbol_key)
                close_flow.state = close_state
                close_flow.position_active = close_state not in {
                    CloseState.FLAT,
                    CloseState.DONE,
                }
                symbol_status.close_phase_value = close_state.value
                symbol_status.close_phase_restore_status = "exact"

        # --- Bracket state apply ---
        # Always clear existing bracket state before adopting authoritative truth.
        # 6C (_startup_reconstruct_runtime_bracket_truth) will overwrite with fresher
        # guardian-proven bracket state. This clear must precede 6C reconstruction.
        bracket_state = str(record.bracket_state or "").strip().upper() or BRACKET_STATE_UNKNOWN
        self._fsm._clear_symbol_brackets(symbol_key)

        if bracket_state == BRACKET_STATE_DEFERRED_PENDING_WAL:
            # Cross-check the WAL: only adopt DEFERRED if the pending entry is present
            # in _pending_brackets for this symbol. Read-only access to WAL.
            deferred_entry_order_id = (
                str(record.deferred_bracket_ref.entry_order_id).strip()
                if record.deferred_bracket_ref is not None
                else ""
            )
            pending = self._fsm._pending_brackets.get(deferred_entry_order_id)
            pending_symbol = (
                str(pending.get("symbol") or "").strip().upper()
                if isinstance(pending, dict)
                else ""
            )
            if deferred_entry_order_id and pending_symbol == symbol_key:
                symbol_status.bracket_state_value = BRACKET_STATE_DEFERRED_PENDING_WAL
                symbol_status.bracket_state_restore_status = "exact"
            else:
                symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
                symbol_status.bracket_state_restore_status = "unknown"
                symbol_status.unresolved_reasons.append(
                    "deferred_pending_missing_in_wal"
                )
        elif bracket_state == BRACKET_STATE_UNKNOWN:
            symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
            symbol_status.bracket_state_restore_status = "unknown"
        elif bracket_state in {BRACKET_STATE_LINKED_ACTIVE, BRACKET_STATE_PARTIAL_LINKAGE}:
            # Linked/partial bracket lineage is not restorable from the envelope alone;
            # 6C reconstruction will establish bracket truth from live guardian proof.
            symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
            symbol_status.bracket_state_restore_status = "unknown"
            symbol_status.unresolved_reasons.append(
                "bracket_lineage_not_restorable_from_envelope"
            )
        else:
            symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
            symbol_status.bracket_state_restore_status = "unknown"
            symbol_status.unresolved_reasons.append(
                f"unsupported_bracket_state:{bracket_state}"
            )

        return symbol_status
