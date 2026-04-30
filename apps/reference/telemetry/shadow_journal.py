from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from unittest import mock

from apps.reference.core.time import get_clock
from pydantic import BaseModel, ConfigDict, Field

LOG = logging.getLogger(__name__)

DEFAULT_CRITICAL_EVENTS = (
    "EVT:QUADRATIC_DECISION_TRACE",
    "EVT:STRATEGY_SIGNAL_PRODUCED",
    "EVT:GATE_CHAIN_TRACE",
    "EVT:DECISION_TRACE_EMITTED",
    "EVT:TRADE_INTENT_PROPOSED",
    "EVT:TRADE_INTENT_REJECTED",
    "EVT:INTENT_DEFERRED",
    "EVT:DECISION_BLOCKED",
    "EVT:REGIME_DETECTED",
    "EVT:STRATEGY_DECISION_BLOCKED",
    "CMD:OPEN",
    "DEC:OPEN",
    "DEC:ADJUST",
    "DEC:PLACE_ORDER",
    "DEC:CANCEL_ORDER",
    "EVT:ORDER_ACK",
    "EVT:ORDER_REJECTED",
    "EVT:ORDER_STATE_CHANGED",
    "EVT:ORDER_PLACED",
    "EVT:TRADE_EXECUTED",
    "EVT:MANAGE_SKIPPED",
    "EVT:EXIT_MATCH_ATTEMPTED",
    "EVT:EXIT_MATCH_FAILED",
    "EVT:EXECUTION_GUARD_BLOCKED",
    "EVT:EXECUTION_DIVERGENCE_DETECTED",
    "EVT:EXECUTION_TIDY_PERFORMED",
    "EVT:EXECUTION_CLOSE_RECONCILED",
    "DEC:BATCH",
    "CMD:CLOSE",
    "DEC:CLOSE",
    "EVT:PORTFOLIO_STATE_UPDATED",
    "EVT:EXPOSURE_SUMMARY_UPDATED",
    "RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD",
    "RESTORE:EXECUTION_POSITION_HYDRATE",
    "ORDER_INDEX:RESERVE_ENTRY",
    "ORDER_INDEX:UPSERT_OPEN",
    "ORDER_INDEX:ATTACH_EXCHANGE_ID",
    "ORDER_INDEX:MARK_TERMINAL",
    "ORDER_INDEX:CANCEL_RESERVATION",
    "HARDENING:TRADE_EXECUTED_SUPPRESSED",
    "HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED",
    "HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_HIT",
    "HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_MISS",
    "HARDENING:CMD_CLOSE_SUPPRESSED",
    "HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED",
    "RESTORE:EXECUTION_TRUTH_HARDENING_RESET",
    "CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_LOADED",
    "CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_EMPTY",
    "CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_LOAD_FAILED",
)


def _to_jsonable(value: Any, *, _seen: set[int] | None = None, _depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, mock.Mock):
        return str(value)
    if _seen is None:
        _seen = set()
    if _depth > 20:
        return str(value)
    obj_id = id(value)
    if obj_id in _seen:
        return "<cycle>"
    _seen.add(obj_id)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(k): _to_jsonable(v, _seen=_seen, _depth=_depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v, _seen=_seen, _depth=_depth + 1) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _to_jsonable(value.model_dump(), _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _to_jsonable(value.dict(), _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            maybe = value.to_dict()
            if isinstance(maybe, dict):
                return _to_jsonable(maybe, _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    if is_dataclass(value):
        try:
            return _to_jsonable(asdict(value), _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dict(dumped)
        except Exception:
            return {}
    return {}


def _is_placeholder_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() == "unknown"


def _coerce_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or _is_placeholder_text(text):
        return None
    return text


def _read_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _read_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _read_str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return DEFAULT_CRITICAL_EVENTS
    out = [str(item) for item in value if isinstance(item, str) and item]
    return tuple(out) if out else DEFAULT_CRITICAL_EVENTS


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_event_name(event_name: str) -> tuple[str, str]:
    if ":" in event_name:
        op, verb = event_name.split(":", 1)
        return str(op), str(verb)
    return "EVT", str(event_name)


class ShadowJournalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    instrumentation_version: str
    record_type: str
    ts_ms: int
    sequence: int
    event_name: str
    op: str
    verb: str
    source_component: str
    source_path: str
    event_origin_type: str
    rid: Optional[str] = None
    causation_rid: Optional[str] = None
    symbol: Optional[str] = None
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    position_id: Optional[str] = None
    lifecycle_id: Optional[str] = None
    strategy_id: Optional[str] = None
    side: Optional[str] = None
    qty: Optional[str] = None
    price: Optional[str] = None
    truth_owner: Optional[str] = None
    local_state_before: Optional[Dict[str, Any]] = None
    local_state_after: Optional[Dict[str, Any]] = None
    restore_marker: bool = False
    suspected_duplicate: bool = False
    duplicate_kind: Optional[str] = None
    duplicate_heuristic: bool = False
    repeated_close: bool = False
    partial_identity: bool = False
    instrumentation_failure: Optional[str] = None
    payload_fragment: Dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ShadowJournalSink:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def write(self, record: ShadowJournalRecord) -> None:
        line = json.dumps(record.model_dump(), ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")


class ShadowCriticalEventJournal:
    def __init__(
        self,
        *,
        path: str,
        schema_version: str = "1.0.0",
        instrumentation_version: str = "1.0.0",
        critical_events: Iterable[str] = DEFAULT_CRITICAL_EVENTS,
    ) -> None:
        self.schema_version = schema_version
        self.instrumentation_version = instrumentation_version
        self.critical_events = set(critical_events)
        self.sink = ShadowJournalSink(path)
        self._seq = 0
        self._lock = threading.RLock()
        self._recent_duplicates: Dict[str, Dict[str, Any]] = {}
        self._recent_closes: Dict[str, float] = {}
        self._pending_failures: list[str] = []

    def should_capture(self, event_name: str) -> bool:
        return event_name in self.critical_events

    def record_bus_emit(
        self,
        *,
        event_name: str,
        payload: Optional[Dict[str, Any]],
        why: str,
        data_ref: Optional[list[Any]] = None,
        rid: Optional[str] = None,
    ) -> None:
        if not self.should_capture(event_name):
            return
        payload = payload or {}
        op, verb = parse_event_name(event_name)
        identity = extract_identity(payload, rid=rid, data_ref=data_ref)
        source_component, source_path, origin_type = infer_emit_source(
            event_name=event_name,
            why=why,
            payload=payload,
        )
        suspected_duplicate, duplicate_kind, duplicate_heuristic = self._detect_duplicate(
            event_name=event_name,
            origin_type=origin_type,
            identity=identity,
        )
        repeated_close = self._detect_repeated_close(
            event_name=event_name, identity=identity)
        partial_identity = detect_partial_identity(identity)
        notes: list[str] = []
        if duplicate_heuristic:
            notes.append("duplicate_marker_heuristic")
        if repeated_close:
            notes.append("repeated_close_marker_heuristic")
        record = ShadowJournalRecord(
            schema_version=self.schema_version,
            instrumentation_version=self.instrumentation_version,
            record_type="event",
            ts_ms=now_ms(),
            sequence=self._next_sequence(),
            event_name=event_name,
            op=op,
            verb=verb,
            source_component=source_component,
            source_path=source_path,
            event_origin_type=origin_type,
            rid=identity["rid"],
            causation_rid=identity["causation_rid"],
            symbol=identity["symbol"],
            order_id=identity["order_id"],
            client_order_id=identity["client_order_id"],
            position_id=identity["position_id"],
            lifecycle_id=identity["lifecycle_id"],
            strategy_id=identity["strategy_id"],
            side=identity["side"],
            qty=identity["qty"],
            price=identity["price"],
            restore_marker=(origin_type == "restore"),
            suspected_duplicate=suspected_duplicate,
            duplicate_kind=duplicate_kind,
            duplicate_heuristic=duplicate_heuristic,
            repeated_close=repeated_close,
            partial_identity=partial_identity,
            payload_fragment=build_payload_fragment(payload),
            notes=notes,
        )
        self._write_record(record)

    def record_transition(
        self,
        *,
        event_name: str,
        source_component: str,
        source_path: str,
        event_origin_type: str,
        truth_owner: str,
        payload: Optional[Dict[str, Any]] = None,
        rid: Optional[str] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        restore_marker: bool = False,
        notes: Optional[list[str]] = None,
    ) -> None:
        if not self.should_capture(event_name):
            return
        payload = payload or {}
        identity = extract_identity(payload, rid=rid)
        suspected_duplicate, duplicate_kind, duplicate_heuristic = self._detect_duplicate(
            event_name=event_name,
            origin_type=event_origin_type,
            identity=identity,
        )
        repeated_close = self._detect_repeated_close(
            event_name=event_name, identity=identity)
        partial_identity = detect_partial_identity(identity)
        op, verb = parse_event_name(event_name)
        record = ShadowJournalRecord(
            schema_version=self.schema_version,
            instrumentation_version=self.instrumentation_version,
            record_type="restore" if restore_marker else "transition",
            ts_ms=now_ms(),
            sequence=self._next_sequence(),
            event_name=event_name,
            op=op,
            verb=verb,
            source_component=source_component,
            source_path=source_path,
            event_origin_type=event_origin_type,
            rid=identity["rid"],
            causation_rid=identity["causation_rid"],
            symbol=identity["symbol"],
            order_id=identity["order_id"],
            client_order_id=identity["client_order_id"],
            position_id=identity["position_id"],
            lifecycle_id=identity["lifecycle_id"],
            strategy_id=identity["strategy_id"],
            side=identity["side"],
            qty=identity["qty"],
            price=identity["price"],
            truth_owner=truth_owner,
            local_state_before=_to_jsonable(
                before) if before is not None else None,
            local_state_after=_to_jsonable(
                after) if after is not None else None,
            restore_marker=restore_marker,
            suspected_duplicate=suspected_duplicate,
            duplicate_kind=duplicate_kind,
            duplicate_heuristic=duplicate_heuristic,
            repeated_close=repeated_close,
            partial_identity=partial_identity,
            payload_fragment=build_payload_fragment(payload),
            notes=list(notes or []),
        )
        self._write_record(record)

    def _next_sequence(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _detect_duplicate(
        self,
        *,
        event_name: str,
        origin_type: str,
        identity: Dict[str, Optional[str]],
    ) -> tuple[bool, Optional[str], bool]:
        if event_name not in ("EVT:TRADE_EXECUTED", "EVT:ORDER_STATE_CHANGED"):
            return False, None, False
        if origin_type not in ("websocket", "watchdog"):
            return False, None, False
        key = (
            f"{event_name}:{identity['symbol']}:{identity['order_id']}:{identity['client_order_id']}"
            if identity["order_id"] or identity["client_order_id"]
            else None
        )
        if key is None:
            return False, None, False
        prev = self._recent_duplicates.get(key)
        self._recent_duplicates[key] = {
            "origin_type": origin_type,
            "ts_ms": now_ms(),
        }
        if prev and prev.get("origin_type") != origin_type:
            return True, "cross_origin_duplicate_exposure", True
        return False, None, False

    def _detect_repeated_close(
        self,
        *,
        event_name: str,
        identity: Dict[str, Optional[str]],
    ) -> bool:
        if event_name not in ("CMD:CLOSE", "DEC:CLOSE"):
            return False
        key = identity["rid"] or identity["symbol"] or identity["order_id"] or identity["client_order_id"]
        if not key:
            return False
        now = time.time()
        previous = self._recent_closes.get(f"{event_name}:{key}")
        self._recent_closes[f"{event_name}:{key}"] = now
        return previous is not None and (now - previous) <= 60.0

    def _write_record(self, record: ShadowJournalRecord) -> None:
        if self._pending_failures and not record.instrumentation_failure:
            record.instrumentation_failure = " | ".join(self._pending_failures)
            self._pending_failures.clear()
        try:
            self.sink.write(record)
        except Exception as exc:
            msg = f"shadow_journal_write_failed:{type(exc).__name__}:{exc}"
            self._pending_failures.append(msg)
            LOG.exception("Shadow journal write failed: %s", exc)


def detect_partial_identity(identity: Dict[str, Optional[str]]) -> bool:
    return bool(
        identity.get("symbol")
        and not identity.get("order_id")
        and (identity.get("rid") or identity.get("client_order_id"))
    )


def build_payload_fragment(payload: Dict[str, Any]) -> Dict[str, Any]:
    keep = (
        "symbol",
        "instrument",
        "regime",
        "confidence",
        "regime_confidence",
        "changed",
        "raw_regime",
        "raw_confidence",
        "stable_confidence",
        "structural_regime_ref",
        "regime_layer",
        "regime_scope",
        "regime_clock",
        "regime_owner",
        "last_update_ts_ms",
        "calc_lag_ms",
        "hysteresis_confirm_count",
        "cache_write_ts_ms",
        "orderId",
        "order_id",
        "clientOrderId",
        "client_order_id",
        "tradeId",
        "trade_id",
        "status",
        "event_ts_ms",
        "terminal_non_fill",
        "terminal_state_kind",
        "origin_class",
        "identity_quality",
        "canonical_identity_key",
        "stage",
        "why",
        "context",
        "why_chain",
        "reason",
        "trigger",
        "block_reason",
        "current_local_state",
        "local_manage_state",
        "portfolio_truth_state",
        "portfolio_state",
        "divergence_detected",
        "has_active_lifecycle",
        "closing_position",
        "position_qty",
        "position_entry_price",
        "position_open_ts",
        "entry_order_id",
        "entry_client_order_id",
        "sl_order_id",
        "tp_order_id",
        "tp1_order_id",
        "tp2_order_id",
        "matched",
        "match_reason",
        "inferred_role",
        "normalized_client_order_id",
        "local_expected_ids",
        "local_expected_ids_after",
        "position_qty_before",
        "position_qty_after",
        "partial_close",
        "requested_qty",
        "business_close_reconciled",
        "tidy_reason",
        "current_rid",
        "tracked_rid",
        "elapsed_sec",
        "max_hold_sec",
        "hold_duration_sec",
        "reject_reason",
        "reject_reason_normalized",
        "reject_reason_source",
        "reason_code",
        "compatibility_aliases_retained",
        "strategy",
        "strategy_id",
        "reduce_only",
        "idempotent_key",
        "lifecycle_id",
        "position_id",
        "qty",
        "quantity",
        "price",
        "ts_ms",
        "side",
        "source",
        "trace",
        "warmup",
        "data_quality",
        "regime_provenance",
        "restore_marker",
    )
    fragment = {key: payload.get(key) for key in keep if key in payload}
    # Strip bare "unknown" placeholders from attribution-critical fields.
    # These fields drive forensic attribution; a bare "unknown" is a placeholder
    # from upstream (e.g. missing close_reason), not a meaningful domain value.
    # Legitimate compound values like "unknown_disappearance" survive because
    # _is_placeholder_text only matches the exact word "unknown".
    _attribution_critical = (
        "reason",
        "trigger",
        "block_reason",
        "reject_reason",
        "reject_reason_normalized",
        "reject_reason_source",
        "reason_code",
        "tidy_reason",
        "match_reason",
        "close_reason",
        "side",
        "source",
        "strategy",
        "strategy_id",
        "inferred_role",
    )
    for field in _attribution_critical:
        if field in fragment and _is_placeholder_text(fragment[field]):
            fragment[field] = None
    return _safe_dict(_to_jsonable(fragment))


def extract_identity(
    payload: Dict[str, Any],
    *,
    rid: Optional[str] = None,
    data_ref: Optional[list[Any]] = None,
) -> Dict[str, Optional[str]]:
    order = _safe_dict(payload.get("order"))
    symbol = _coerce_text(payload.get("symbol") or payload.get(
        "instrument") or order.get("symbol"))
    resolved_rid = _coerce_text(payload.get("rid") or rid)
    causation_rid = _coerce_text(
        payload.get("causation_rid")
        or payload.get("parent_rid")
        or order.get("parent_rid")
    )
    if causation_rid is None and data_ref:
        for item in data_ref:
            if isinstance(item, str) and "rid" in item.lower():
                causation_rid = _coerce_text(item)
                break
    qty = _coerce_text(payload.get("qty") or payload.get(
        "quantity") or order.get("qty") or order.get("quantity"))
    price = _coerce_text(payload.get("price") or order.get("price"))
    return {
        "rid": resolved_rid,
        "causation_rid": causation_rid,
        "symbol": symbol,
        "order_id": _first_str(payload, "orderId", "order_id"),
        "client_order_id": _first_str(payload, "clientOrderId", "client_order_id"),
        "position_id": _first_str(payload, "positionId", "position_id"),
        "lifecycle_id": _first_str(payload, "lifecycleId", "lifecycle_id", "idempotent_key"),
        "strategy_id": _first_str(payload, "strategyId", "strategy_id", "strategy") or _first_str(order, "strategyId", "strategy_id"),
        "side": _first_str(payload, "side") or _first_str(order, "side"),
        "qty": qty,
        "price": price,
    }


def _first_str(mapping: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = mapping.get(key)
        coerced = _coerce_text(value)
        if coerced is not None:
            return coerced
    return None


def infer_emit_source(
    *,
    event_name: str,
    why: str,
    payload: Dict[str, Any],
) -> tuple[str, str, str]:
    why_l = (why or "").lower()
    if event_name.startswith("RESTORE:") or "restore" in why_l or payload.get("restore_marker") is True:
        return ("restore_manager", "restore:startup", "restore")
    if why.startswith("WS_") or "websocket" in why_l or "raw_ws_data" in payload:
        return ("binance_ws_client", "websocket:user_data_stream", "websocket")
    if "polling" in why_l or "watchdog" in why_l:
        return ("execution_position.watchdog", "watchdog:rest_poll", "watchdog")
    if event_name == "EVT:TRADE_INTENT_PROPOSED":
        return ("decision_making.intent_builder", "decision:intent_builder", "decision")
    if event_name == "EVT:TRADE_INTENT_REJECTED":
        stage = str(payload.get("stage") or "").upper()
        if stage == "EXECUTION":
            return ("execution_position", "execution:trade_intent_reject", "execution")
        return ("decision_making", "decision:trade_intent_reject", "decision")
    if event_name == "EVT:INTENT_DEFERRED":
        return ("decision_making", "decision:intent_deferred", "decision")
    if event_name in ("EVT:DECISION_BLOCKED", "EVT:STRATEGY_DECISION_BLOCKED"):
        return ("decision_making", "decision:blocked_truth", "decision")
    if event_name == "EVT:QUADRATIC_DECISION_TRACE":
        return ("decision_making.aurora", "decision:quadratic_trace", "decision")
    if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
        return ("decision_making.aurora", "decision:strategy_signal", "decision")
    if event_name == "EVT:GATE_CHAIN_TRACE":
        return ("decision_making.strategy_gateway", "decision:gate_chain_trace", "decision")
    if event_name == "EVT:DECISION_TRACE_EMITTED":
        return ("decision_making.intent_builder", "decision:decision_trace", "decision")
    if event_name in ("EVT:PORTFOLIO_STATE_UPDATED", "EVT:EXPOSURE_SUMMARY_UPDATED"):
        return ("position_tracking", "portfolio:state_update", "portfolio")
    if event_name.startswith("CMD:"):
        return ("execution_position.intent_router", "router:intent_router", "router")
    if event_name.startswith("DEC:"):
        return ("execution_position", "execution:decision", "execution")
    if event_name.startswith("EVT:ORDER_") or event_name == "EVT:TRADE_EXECUTED":
        return ("execution_position", "execution:event_bus", "execution")
    if event_name in (
        "EVT:MANAGE_SKIPPED",
        "EVT:EXIT_MATCH_ATTEMPTED",
        "EVT:EXIT_MATCH_FAILED",
    ):
        return ("execution_position.fsm_manage", "execution:manage_flow", "execution")
    if event_name in (
        "EVT:EXECUTION_GUARD_BLOCKED",
        "EVT:EXECUTION_DIVERGENCE_DETECTED",
    ):
        return ("execution_position.fsm", "execution:guard", "execution")
    if event_name in (
        "EVT:EXECUTION_TIDY_PERFORMED",
        "EVT:EXECUTION_CLOSE_RECONCILED",
    ):
        return ("execution_position.order_guardian", "guardian:cleanup", "execution")
    return ("unknown", "unknown", "unknown")


def resolve_shadow_journal_config(config: Any) -> Optional[dict[str, Any]]:
    observability = getattr(config, "observability", None)
    if observability is None:
        return None
    shadow_cfg = getattr(observability, "shadow_journal", None)
    if shadow_cfg is None:
        return None
    enabled_raw = getattr(shadow_cfg, "enabled", None)
    path_raw = getattr(shadow_cfg, "path", None)
    if isinstance(shadow_cfg, mock.Mock) and not isinstance(enabled_raw, bool) and not isinstance(path_raw, str):
        return None
    enabled = _read_bool(enabled_raw, True)
    if not enabled:
        return None
    return {
        "path": _read_str(
            path_raw,
            "logs/shadow_critical_event_journal_v1.jsonl",
        ),
        "schema_version": _read_str(
            getattr(shadow_cfg, "schema_version", None),
            "1.0.0",
        ),
        "instrumentation_version": _read_str(
            getattr(shadow_cfg, "instrumentation_version", None),
            "1.0.0",
        ),
        "critical_events": _read_str_list(
            getattr(shadow_cfg, "critical_events", None),
        ),
    }


def attach_shadow_journal(fsm: Any, config: Any) -> Optional[ShadowCriticalEventJournal]:
    existing = getattr(fsm, "_shadow_journal", None)
    if isinstance(existing, ShadowCriticalEventJournal):
        _attach_order_index(existing, getattr(fsm, "order_index", None))
        return existing
    resolved = resolve_shadow_journal_config(config)
    if resolved is None:
        return None
    journal = ShadowCriticalEventJournal(**resolved)
    setattr(fsm, "_shadow_journal", journal)
    _attach_order_index(journal, getattr(fsm, "order_index", None))
    return journal


def _attach_order_index(journal: ShadowCriticalEventJournal, order_index: Any) -> None:
    if order_index is None:
        return
    attach_fn = getattr(order_index, "attach_shadow_journal", None)
    if callable(attach_fn):
        try:
            attach_fn(journal)
        except Exception:
            LOG.debug(
                "Failed to attach shadow journal to OrderIndex", exc_info=True)


def get_shadow_journal(owner: Any) -> Optional[ShadowCriticalEventJournal]:
    direct = getattr(owner, "_shadow_journal", None)
    if isinstance(direct, ShadowCriticalEventJournal):
        return direct
    for attr in ("fsm", "_fsm"):
        parent = getattr(owner, attr, None)
        direct = getattr(parent, "_shadow_journal", None)
        if isinstance(direct, ShadowCriticalEventJournal):
            return direct
    return None


def snapshot_execpos_state(fsm: Any, symbol: Optional[str]) -> Dict[str, Any]:
    manage_flow = fsm.manage_flows.get(symbol) if symbol else None
    close_flow = fsm.close_flows.get(symbol) if symbol else None
    portfolio_state = None
    if symbol and hasattr(fsm, "_get_portfolio_state_for_symbol"):
        try:
            portfolio_state = fsm._get_portfolio_state_for_symbol(symbol)
        except Exception:
            portfolio_state = None
    return _safe_dict(_to_jsonable({
        "symbol": symbol,
        "manage_state": _state_value(manage_flow),
        "close_state": _state_value(close_flow),
        "portfolio_state": portfolio_state,
        "closing_position": bool(getattr(manage_flow, "_closing_position", False)) if manage_flow else False,
        "open_flows": len(getattr(fsm, "open_flows", {})),
        "manage_flows": len(getattr(fsm, "manage_flows", {})),
        "close_flows": len(getattr(fsm, "close_flows", {})),
    }))


def snapshot_manage_flow_state(flow: Any) -> Dict[str, Any]:
    position_open_ts = getattr(flow, "position_open_ts", 0.0)
    return _safe_dict(_to_jsonable({
        "state": _state_value(flow),
        "symbol": getattr(flow, "symbol", None),
        "position_qty": getattr(flow, "position_qty", None),
        "position_entry_price": getattr(flow, "position_entry_price", None),
        "position_open_ts": position_open_ts,
        "position_hold_sec": _position_hold_sec(position_open_ts),
        "position_side": getattr(flow, "position_side", None),
        "closing_position": getattr(flow, "_closing_position", False),
        "closing_position_ts": getattr(flow, "_closing_position_ts", 0.0),
        "entry_order_id": getattr(flow, "entry_order_id", None),
        "entry_client_order_id": getattr(flow, "entry_client_order_id", None),
        "sl_order_id": getattr(flow, "sl_order_id", None),
        "tp_order_id": getattr(flow, "tp_order_id", None),
        "tp1_order_id": getattr(flow, "tp1_order_id", None),
        "tp2_order_id": getattr(flow, "tp2_order_id", None),
        "sl_price": getattr(flow, "sl_price", None),
        "tp_price": getattr(flow, "tp_price", None),
        "tp1_price": getattr(flow, "tp1_price", None),
        "tp2_price": getattr(flow, "tp2_price", None),
        "partial_exit_pct": getattr(flow, "partial_exit_pct", None),
        "trailing_activated": getattr(flow, "trailing_activated", False),
        "last_trailing_ts": getattr(flow, "last_trailing_ts", 0.0),
        "peak_price": getattr(flow, "peak_price", None),
    }))


def snapshot_close_flow_state(flow: Any) -> Dict[str, Any]:
    position_open_ts = getattr(flow, "position_open_ts", 0.0)
    return _safe_dict(_to_jsonable({
        "state": _state_value(flow),
        "position_active": getattr(flow, "position_active", False),
        "position_open_ts": position_open_ts,
        "position_hold_sec": _position_hold_sec(position_open_ts),
        "position_qty": getattr(flow, "position_qty", None),
        "position_side": getattr(flow, "position_side", None),
        "last_close_reason": getattr(flow, "last_close_reason", None),
        "last_close_qty": getattr(flow, "last_close_qty", None),
        "last_close_symbol": getattr(flow, "last_close_symbol", None),
    }))


def snapshot_position_tracking_state(owner: Any, symbol: Optional[str]) -> Dict[str, Any]:
    position = None
    if symbol and isinstance(getattr(owner, "_positions", None), dict):
        position = owner._positions.get(symbol)
    return _safe_dict(_to_jsonable({
        "positions_count": len(getattr(owner, "_positions", {})),
        "symbol": symbol,
        "position": position,
        "equity": getattr(owner, "_equity", None),
        "realized_pnl": getattr(owner, "_realized_pnl", None),
    }))


def _state_value(owner: Any) -> Optional[str]:
    if owner is None:
        return None
    state = getattr(owner, "state", None)
    return str(getattr(state, "value", state)) if state is not None else None


def _position_hold_sec(position_open_ts: Any) -> Optional[float]:
    try:
        open_ts = float(position_open_ts)
    except Exception:
        return None
    if open_ts <= 0:
        return None
    try:
        return max(0.0, float(get_clock().now_sec()) - open_ts)
    except Exception:
        return None
