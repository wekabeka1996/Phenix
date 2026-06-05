import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from apps.reference.core.time import get_clock
from vfoundation.core.fsm_emit_compat import Message
from apps.reference.telemetry.trade_lifecycle_logger import (
    append_trade_lifecycle_record,
    EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND,
)

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.bracket_ownership"
)


class BracketOwnership:
    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm
        self._bracket_owner_by_symbol: Dict[str, Dict[str, Any]] = {}

    def clear_bracket_owner(self, symbol: str) -> None:
        """Sanctioned accessor to remove bracket ownership cache."""
        symbol_key = str(symbol or "").strip().upper()
        self._bracket_owner_by_symbol.pop(symbol_key, None)

    def _strategy_assignments_for_symbol(self, symbol: str) -> List[str]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return []
        try:
            registry = getattr(self._fsm.config, "strategies_registry", None)
            assignments = getattr(registry, "assignments", None)
        except Exception:
            return []
        if not isinstance(assignments, dict):
            return []
        raw_assignments = assignments.get(symbol_key) or []
        if not isinstance(raw_assignments, list):
            return []
        result: List[str] = []
        for strategy_id in raw_assignments:
            normalized = str(strategy_id or "").strip()
            if normalized:
                result.append(normalized)
        return result

    def _strategy_profile_has_symbol(self, strategy_id: str, symbol: str) -> bool:
        strategy_key = str(strategy_id or "").strip()
        symbol_key = str(symbol or "").strip().upper()
        if not strategy_key or not symbol_key:
            return False
        try:
            strategies = getattr(self._fsm.config, "strategies", None)
            strategy_cfg = getattr(
                strategies, strategy_key, None) if strategies is not None else None
            assets = getattr(strategy_cfg, "assets",
                             None) if strategy_cfg is not None else None
        except Exception:
            return False
        return isinstance(assets, dict) and symbol_key in assets

    def resolve_bracket_strategy_owner(
        self,
        *,
        symbol: str,
        explicit_strategy_id: Optional[str] = None,
        explicit_source: str = "",
        allow_registry_fallback: bool = True,
    ) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        assignments = self._strategy_assignments_for_symbol(symbol_key)
        explicit = str(explicit_strategy_id or "").strip()
        if explicit.lower() == "none":
            explicit = ""

        explicit_invalid_detail = ""
        if explicit:
            assigned_ok = (not assignments) or (explicit in assignments)
            profile_ok = self._strategy_profile_has_symbol(
                explicit, symbol_key)
            if assigned_ok and profile_ok:
                return {
                    "strategy_id": explicit,
                    "strategy_source": explicit_source or "explicit",
                    "owner_status": "resolved",
                    "detail": "",
                    "assigned_strategies": assignments,
                }
            if not assigned_ok:
                explicit_invalid_detail = f"explicit_strategy_not_assigned:{explicit}"
            elif not profile_ok:
                explicit_invalid_detail = f"explicit_strategy_profile_missing:{explicit}"
            if not allow_registry_fallback:
                return {
                    "strategy_id": None,
                    "strategy_source": explicit_source or "explicit",
                    "owner_status": "unresolved",
                    "detail": explicit_invalid_detail,
                    "assigned_strategies": assignments,
                }

        if allow_registry_fallback:
            if len(assignments) == 1:
                candidate = assignments[0]
                if self._strategy_profile_has_symbol(candidate, symbol_key):
                    detail = explicit_invalid_detail
                    if detail:
                        detail = f"{detail};fallback_to_registry_assignment:{candidate}"
                    return {
                        "strategy_id": candidate,
                        "strategy_source": "registry_assignment",
                        "owner_status": "resolved",
                        "detail": detail,
                        "assigned_strategies": assignments,
                    }
                detail = f"assigned_strategy_profile_missing:{candidate}"
                if explicit_invalid_detail:
                    detail = f"{explicit_invalid_detail};{detail}"
                return {
                    "strategy_id": None,
                    "strategy_source": "registry_assignment",
                    "owner_status": "profile_missing",
                    "detail": detail,
                    "assigned_strategies": assignments,
                }
            if len(assignments) > 1:
                detail = "multiple_strategy_assignments"
                if explicit_invalid_detail:
                    detail = f"{explicit_invalid_detail};{detail}"
                return {
                    "strategy_id": None,
                    "strategy_source": explicit_source or "registry_assignment",
                    "owner_status": "ambiguous",
                    "detail": detail,
                    "assigned_strategies": assignments,
                }

        detail = explicit_invalid_detail or "strategy_owner_unresolved"
        return {
            "strategy_id": None,
            "strategy_source": explicit_source or "unresolved",
            "owner_status": "missing",
            "detail": detail,
            "assigned_strategies": assignments,
        }

    def resolve_strategy_owner_from_decision(
        self,
        *,
        symbol: str,
        decision: Message,
    ) -> Dict[str, Any]:
        payload = dict(getattr(decision, "pld", None) or {})
        raw_meta = payload.get("metadata")
        metadata = raw_meta if isinstance(raw_meta, dict) else {}
        candidates = (
            (metadata.get("strategy_id"), "decision_metadata"),
            (payload.get("strategy_id"), "decision_strategy_id"),
            (payload.get("strategy"), "decision_strategy"),
        )
        for strategy_id, source in candidates:
            normalized = str(strategy_id or "").strip()
            if normalized and normalized.lower() != "none":
                return self.resolve_bracket_strategy_owner(
                    symbol=symbol,
                    explicit_strategy_id=normalized,
                    explicit_source=source,
                    allow_registry_fallback=True,
                )
        return self.resolve_bracket_strategy_owner(
            symbol=symbol,
            explicit_strategy_id=None,
            explicit_source="",
            allow_registry_fallback=True,
        )

    def resolve_strategy_owner_for_recovery(self, *, symbol: str) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        cached_owner = self.resolve_bracket_strategy_owner(
            symbol=symbol_key,
            explicit_strategy_id=self._fsm._open_strategy_by_symbol.get(symbol_key),
            explicit_source="runtime_cache",
            allow_registry_fallback=True,
        )
        if cached_owner.get("owner_status") == "resolved":
            return cached_owner

        remembered = dict(self._bracket_owner_by_symbol.get(symbol_key) or {})
        remembered_strategy_id = str(
            remembered.get("strategy_id") or "").strip()
        if remembered_strategy_id:
            remembered_owner = self.resolve_bracket_strategy_owner(
                symbol=symbol_key,
                explicit_strategy_id=remembered_strategy_id,
                explicit_source="bracket_owner_cache",
                allow_registry_fallback=True,
            )
            if remembered_owner.get("owner_status") == "resolved":
                return remembered_owner
            remembered_detail = str(
                remembered_owner.get("detail") or "").strip()
            cached_detail = str(cached_owner.get("detail") or "").strip()
            if cached_detail and remembered_detail:
                cached_owner["detail"] = f"{cached_detail};{remembered_detail}"
            elif remembered_detail:
                cached_owner["detail"] = remembered_detail
        return cached_owner

    def remember_bracket_owner(
        self,
        *,
        symbol: str,
        strategy_id: Optional[str],
        strategy_source: Optional[str],
        owner_status: str,
        placement_path: str,
        detail: Optional[str] = None,
        assigned_strategies: Optional[List[str]] = None,
        rid: Optional[str] = None,
        corr_id: Optional[str] = None,
        entry_order_id: Optional[str] = None,
        entry_client_order_id: Optional[str] = None,
        lifecycle_active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return {}
        current = dict(self._bracket_owner_by_symbol.get(symbol_key) or {})
        current["symbol"] = symbol_key
        current["updated_ts_ms"] = get_clock().now_ms()
        strategy_value = str(strategy_id or "").strip()
        if strategy_value and strategy_value.lower() != "none":
            current["strategy_id"] = strategy_value
        if strategy_source:
            current["strategy_source"] = str(strategy_source)
        if owner_status:
            current["owner_status"] = str(owner_status)
        if detail:
            current["detail"] = str(detail)
        if assigned_strategies is not None:
            current["assigned_strategies"] = [
                str(item) for item in assigned_strategies if str(item or "").strip()
            ]
        current["placement_path"] = str(placement_path)
        if rid:
            current["rid"] = str(rid)
        if corr_id:
            current["corr_id"] = str(corr_id)
        if entry_order_id:
            current["entry_order_id"] = str(entry_order_id)
        if entry_client_order_id:
            current["entry_client_order_id"] = str(entry_client_order_id)
        if lifecycle_active is not None:
            current["lifecycle_active"] = bool(lifecycle_active)
        self._bracket_owner_by_symbol[symbol_key] = current
        return current

    def append_bracket_ownership_record(
        self,
        *,
        event_type: str,
        symbol: str,
        placement_path: str,
        strategy_id: Optional[str],
        strategy_source: Optional[str],
        owner_status: str,
        detail: Optional[str] = None,
        assigned_strategies: Optional[List[str]] = None,
        rid: Optional[str] = None,
        corr_id: Optional[str] = None,
        entry_order_id: Optional[str] = None,
        entry_client_order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        lifecycle_active: Optional[bool] = None,
    ) -> None:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return

        fingerprint = (
            str(event_type),
            str(placement_path),
            str(strategy_id or ""),
            str(strategy_source or ""),
            str(owner_status or ""),
            str(detail or ""),
            str(entry_order_id or ""),
            str(entry_client_order_id or ""),
            str(sl_order_id or ""),
            str(tp_order_id or ""),
            lifecycle_active,
        )
        current = dict(self._bracket_owner_by_symbol.get(symbol_key) or {})
        if current.get("last_record_fingerprint") == fingerprint:
            return
        current["last_record_fingerprint"] = fingerprint
        self._bracket_owner_by_symbol[symbol_key] = current

        record = {
            "record_kind": EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND,
            "event_type": event_type,
            "ts_ms": get_clock().now_ms(),
            "symbol": symbol_key,
            "placement_path": placement_path,
            "recovery_only": placement_path == "recovery",
            "strategy_id": strategy_id,
            "strategy_source": strategy_source,
            "owner_status": owner_status,
            "owner_detail": detail,
            "assigned_strategies": assigned_strategies,
            "rid": rid,
            "corr_id": corr_id,
            "entry_order_id": entry_order_id,
            "entry_client_order_id": entry_client_order_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "lifecycle_active": lifecycle_active,
        }
        filtered = {key: value for key,
                    value in record.items() if value is not None}
        append_trade_lifecycle_record(
            filtered,
            log_file=self._fsm._trade_lifecycle_log_path(),
        )
        self._fsm._emit_observability_event(event_type, filtered)
        self._fsm._persist_restore_artifact_snapshot(
            trigger=f"bracket_record:{event_type.lower()}",
            allow_empty=True,
        )
