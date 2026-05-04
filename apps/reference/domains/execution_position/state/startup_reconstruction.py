"""
Startup Reconstruction (Package 6C).

Owns bracket truth reconstruction from guardian-proven exchange state.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Set

from .restore_artifact import (
    TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
)

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.startup_reconstruction"
)


class StartupReconstruction:
    """
    Startup reconstruction contour owner.

    Takes fresh open orders after guardian links them, resolves bracket roles
    using guardian proof, and reconstructs runtime bracket truth into FSM state.
    """

    def __init__(self, fsm: "ExecPosFSM") -> None:
        """Initialize with back-reference to FSM composition root."""
        self._fsm = fsm

    def reconstruct(self, open_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Reconstruct bracket truth from exchange state + guardian proof.
        """
        order_index = self._fsm._runtime_order_index()
        if self._fsm.order_guardian is None or order_index is None:
            return {
                "summary": {
                    "symbols_reconstructed": 0,
                    "order_index_registrations": 0,
                    "unresolved_symbols": 0,
                },
                "records": [],
            }

        resolved_orders: Dict[str, Dict[str, str]] = {}
        unresolved_reasons: Dict[str, List[str]] = {}
        duplicate_roles: Dict[str, Set[str]] = {}
        order_index_registrations = 0
        order_index_registrations_by_symbol: Dict[str, int] = {}
        runtime_truth_records: List[Dict[str, Any]] = []

        def _note_unresolved(symbol_key: str, reason: str) -> None:
            unresolved_reasons.setdefault(symbol_key, []).append(reason)

        for raw_order in open_orders:
            order = raw_order if isinstance(raw_order, dict) else {}
            symbol_key = str(order.get("symbol") or "").strip().upper()
            exchange_order_id = str(
                order.get("orderId") or order.get("order_id") or ""
            ).strip()
            client_order_id = str(
                order.get("clientOrderId") or order.get("client_order_id") or ""
            ).strip()
            if not symbol_key or not exchange_order_id:
                continue

            context = self._fsm.order_guardian.resolve_terminal_bracket_context(
                client_order_id=client_order_id or None,
                exchange_order_id=exchange_order_id,
                symbol=symbol_key,
            )
            if context is None:
                continue

            role = str(context.get("bracket_role") or "").strip().upper()
            tracked_order_id = str(
                context.get("tracked_bracket_order_id") or exchange_order_id or ""
            ).strip()
            tracked_client_order_id = str(
                context.get("tracked_client_order_id") or client_order_id or ""
            ).strip()
            
            if role not in {"SL", "TP", "TP1", "TP2"}:
                _note_unresolved(symbol_key, f"unsupported_role:{role or 'missing'}")
                continue
            if not tracked_order_id:
                _note_unresolved(
                    symbol_key, f"missing_tracked_order_id:{exchange_order_id}"
                )
                continue
            if not tracked_client_order_id:
                _note_unresolved(
                    symbol_key, f"missing_tracked_client_order_id:{tracked_order_id}"
                )
                continue

            order_kind = "SL" if role == "SL" else "TP"
            resolved_for_symbol = resolved_orders.setdefault(symbol_key, {})
            existing_order_id = resolved_for_symbol.get(order_kind)
            
            if existing_order_id and existing_order_id != tracked_order_id:
                duplicate_roles.setdefault(symbol_key, set()).add(order_kind)
                _note_unresolved(
                    symbol_key,
                    f"duplicate_{order_kind.lower()}:{existing_order_id},{tracked_order_id}",
                )
            else:
                resolved_for_symbol[order_kind] = tracked_order_id

            if order_index.get(exchangeOrderId=tracked_order_id) is None:
                try:
                    order_index.register_bracket_child(
                        rid=str(context.get("rid") or tracked_order_id),
                        idempotent_key=None,
                        clientOrderId=tracked_client_order_id,
                        exchangeOrderId=tracked_order_id,
                        symbol=symbol_key,
                        side=str(order.get("side") or "").upper(),
                        order_type=str(
                            order.get("type")
                            or order.get("order_type")
                            or context.get("order_type")
                            or ""
                        ),
                        order_kind=order_kind,
                    )
                    order_index_registrations += 1
                    order_index_registrations_by_symbol[symbol_key] = (
                        order_index_registrations_by_symbol.get(symbol_key, 0) + 1
                    )
                except Exception as exc:
                    _note_unresolved(
                        symbol_key,
                        f"order_index_registration_failed:{type(exc).__name__}",
                    )

        symbols_reconstructed = 0
        unresolved_symbols = 0
        
        for symbol_key in sorted(
            set(resolved_orders.keys()) | set(unresolved_reasons.keys())
        ):
            duplicate_for_symbol = duplicate_roles.get(symbol_key, set())
            sl_order_id = None
            tp_order_id = None
            manage_truth_source = self._fsm._manage_truth_source_for(symbol_key)
            
            if symbol_key in resolved_orders:
                if "SL" not in duplicate_for_symbol:
                    sl_order_id = resolved_orders[symbol_key].get("SL")
                if "TP" not in duplicate_for_symbol:
                    tp_order_id = resolved_orders[symbol_key].get("TP")

            if sl_order_id or tp_order_id:
                self._fsm._set_symbol_brackets_snapshot(
                    symbol_key,
                    sl_order_id=sl_order_id,
                    tp_order_id=tp_order_id,
                    truth_source=TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
                )
                manage_flow = self._fsm.manage_flows.get(symbol_key)
                if manage_flow is not None and self._fsm._manage_state_value(
                    manage_flow
                ) not in {"", "FLAT"}:
                    manage_flow.set_bracket_ids(
                        sl_order_id=sl_order_id,
                        tp_order_id=tp_order_id,
                    )
                symbols_reconstructed += 1
                self._fsm._startup_truth_orchestrator._append_restart_truth_record(
                    event_type="EXECUTION_RESTART_RUNTIME_TRUTH_RECONSTRUCTED",
                    symbol=symbol_key,
                    sl_order_id=sl_order_id,
                    tp_order_id=tp_order_id,
                    order_index_registrations=order_index_registrations_by_symbol.get(
                        symbol_key, 0
                    ),
                    unresolved_reasons=unresolved_reasons.get(symbol_key),
                )
                runtime_truth_records.append(
                    {
                        "symbol": symbol_key,
                        "status": "reconstructed",
                        "sl_order_id": sl_order_id,
                        "tp_order_id": tp_order_id,
                        "bracket_truth_source": self._fsm._symbol_bracket_truth_source_for(
                            symbol_key
                        ),
                        "manage_truth_source": manage_truth_source,
                        "order_index_registrations": order_index_registrations_by_symbol.get(
                            symbol_key, 0
                        ),
                        "unresolved_reasons": list(
                            unresolved_reasons.get(symbol_key) or []
                        ),
                    }
                )
            elif unresolved_reasons.get(symbol_key):
                self._fsm._clear_symbol_brackets(symbol_key)
                self._fsm._startup_truth_orchestrator._append_restart_truth_record(
                    event_type="EXECUTION_RESTART_RUNTIME_TRUTH_UNRESOLVED",
                    symbol=symbol_key,
                    sl_order_id=None,
                    tp_order_id=None,
                    order_index_registrations=0,
                    unresolved_reasons=unresolved_reasons.get(symbol_key),
                )
                runtime_truth_records.append(
                    {
                        "symbol": symbol_key,
                        "status": "unresolved",
                        "sl_order_id": None,
                        "tp_order_id": None,
                        "bracket_truth_source": self._fsm._symbol_bracket_truth_source_for(
                            symbol_key
                        ),
                        "manage_truth_source": manage_truth_source,
                        "order_index_registrations": 0,
                        "unresolved_reasons": list(
                            unresolved_reasons.get(symbol_key) or []
                        ),
                    }
                )

            if unresolved_reasons.get(symbol_key):
                unresolved_symbols += 1

        summary = {
            "symbols_reconstructed": symbols_reconstructed,
            "order_index_registrations": order_index_registrations,
            "unresolved_symbols": unresolved_symbols,
        }
        self._fsm._emit_observability_event(
            "RESTORE:EXECUTION_POSITION_RUNTIME_TRUTH_RECONCILED",
            summary,
        )
        return {
            "summary": summary,
            "records": runtime_truth_records,
        }
