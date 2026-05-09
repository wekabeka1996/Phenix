"""Thread-backed Phase 6 decision outcome ledger sink."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal, Protocol

from apps.reference.domains.neocortex.contracts.causal_time import DatasetVisibility
from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
    JsonValue,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    coerce_causal_time_provenance,
    is_causal_time_provenance,
)
from apps.reference.telemetry.metrics import (
    inc_neocortex_async_forced_stop,
    inc_neocortex_dataset_invalid,
    inc_neocortex_ledger_queue_dropped,
    inc_neocortex_ledger_shutdown_undrained,
    inc_neocortex_ledger_write_failed,
    set_neocortex_ledger_queue_depth,
)


JsonObject = dict[str, JsonValue]


class _EventLike(Protocol):
    pld: object


class _FSMLike(Protocol):
    def listen(self, event_name: str, handler: Callable[[object], None]) -> None:
        ...


def _now_ms() -> int:
    return int(time.time() * 1000)


def _payload_view(event: Mapping[str, object] | _EventLike | object) -> JsonObject:
    if isinstance(event, dict):
        payload = event.get("payload") or event.get("pld")
        return dict(payload) if isinstance(payload, dict) else dict(event)
    payload = getattr(event, "pld", None)
    return dict(payload) if isinstance(payload, dict) else {}


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _to_jsonable(item) for key, item in value.items()}


def _to_jsonable(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _to_jsonable(value.model_dump(mode="json"))
        except (AttributeError, TypeError, ValueError):
            return str(value)
    return str(value)


def _safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def _safe_int(value: object) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, (str, bytes, bytearray)):
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off", ""}:
            return False
    return default


def _normalize_action(value: object) -> str:
    normalized = str(value or "FALLBACK").strip().upper()
    if normalized == "DENY":
        return "BLOCK"
    return normalized or "FALLBACK"


def _normalize_authority_mode(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "enforce":
        return "gated"
    if normalized:
        return normalized
    return "unknown"


def _string_alias(payload: Mapping[str, object], *aliases: str) -> str | None:
    for alias in aliases:
        if alias not in payload:
            continue
        value = payload.get(alias)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _explicit_timestamp_present(payload: Mapping[str, object], key: str) -> bool:
    return _safe_int(payload.get(key)) is not None


def _observation_time_support(snapshot: Mapping[str, object]) -> JsonObject:
    provenance_raw: object | None = None
    for key in (
        "event_time_source",
        "event_time_provenance",
        "time_provenance",
        "feature_time_provenance",
    ):
        if key not in snapshot:
            continue
        candidate = snapshot.get(key)
        if candidate is None:
            continue
        provenance_raw = candidate
        break

    provenance = coerce_causal_time_provenance(provenance_raw)
    observation_event_ts_ms = None
    for key in (
        "event_ts_ms",
        "decision_basis_ts_ms",
        "decision_basis_ts",
        "feature_event_ts_ms",
    ):
        timestamp = _safe_int(snapshot.get(key))
        if timestamp is None or timestamp < 1:
            continue
        observation_event_ts_ms = timestamp
        break
    observation_event_ts_present = observation_event_ts_ms is not None
    raw_visibility = snapshot.get("dataset_visibility")
    dataset_visibility = None
    if isinstance(raw_visibility, str):
        text = raw_visibility.strip()
        if text:
            dataset_visibility = text

    return {
        "observation_provenance_present": provenance_raw is not None,
        "observation_provenance_causal": bool(
            observation_event_ts_present
            and provenance_raw is not None
            and is_causal_time_provenance(provenance)
        ),
        "observation_time_source": provenance.value,
        "observation_time_is_causal": bool(
            observation_event_ts_present and snapshot.get(
                "event_time_is_causal") is True
        ),
        "observation_trainable": bool(
            observation_event_ts_present and snapshot.get("trainable") is True
        ),
        "observation_dataset_visibility": dataset_visibility,
        "observation_event_ts_present": observation_event_ts_present,
        "observation_event_ts_ms": observation_event_ts_ms,
    }


@dataclass(slots=True)
class _PendingDecision:
    decision_id: str
    rid: str
    symbol: str
    authority_mode: str
    request_ts_ms: int
    response_ts_ms: int
    apply_result: str | None
    fallback_reason: str | None
    causal_state_snapshot: JsonObject
    neocortex_action: str
    data_quality_flags: JsonObject
    stress_metrics: JsonObject
    support_quality: JsonObject
    expires_at_ms: int
    downstream_rid: str | None = None
    lifecycle_id: str | None = None
    trade_id: str | None = None
    rid_aliases: set[str] = field(default_factory=set)
    lifecycle_aliases: set[str] = field(default_factory=set)
    trade_aliases: set[str] = field(default_factory=set)


class DecisionOutcomeLedgerSink:
    """Join decision-time facts with execution close truth under neocortex ownership."""

    def __init__(
        self,
        path: str | Path = "logs/shadow_telemetry/decision_ledger_v1.jsonl",
        *,
        queue_maxsize: int,
        overflow_policy: Literal["fail_closed"],
        enqueue_timeout_ms: int,
        shutdown_timeout_ms: int,
        pending_ttl_ms: int = 3_600_000,
        cleanup_interval_ms: int = 30_000,
        clock_ms_fn: Callable[[], int] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._queue_maxsize = int(queue_maxsize)
        if self._queue_maxsize < 1:
            raise ValueError("queue_maxsize must be >= 1")
        self._overflow_policy = str(overflow_policy).strip().lower()
        if self._overflow_policy != "fail_closed":
            raise ValueError(
                "Decision outcome ledger overflow_policy must be 'fail_closed'")
        self._enqueue_timeout_ms = int(enqueue_timeout_ms)
        if self._enqueue_timeout_ms < 0:
            raise ValueError("enqueue_timeout_ms must be >= 0")
        self._shutdown_timeout_ms = int(shutdown_timeout_ms)
        if self._shutdown_timeout_ms < 1:
            raise ValueError("shutdown_timeout_ms must be >= 1")
        self._pending_ttl_ms = max(1, int(pending_ttl_ms))
        self._cleanup_interval_ms = max(100, int(cleanup_interval_ms))
        self._clock_ms = clock_ms_fn or _now_ms
        self.logger = logger or logging.getLogger(__name__)

        self._lock = threading.Lock()
        self._pending_by_decision_id: dict[str, _PendingDecision] = {}
        self._decision_id_by_rid: dict[str, str] = {}
        self._decision_id_by_lifecycle_id: dict[str, str] = {}
        self._decision_id_by_trade_id: dict[str, str] = {}

        self._write_queue: queue.Queue[JsonObject | None] = queue.Queue(
            maxsize=self._queue_maxsize
        )
        self._update_queue_depth_metric()
        self._stop_event = threading.Event()
        self._writer_thread: threading.Thread | None = None
        self._cleanup_thread: threading.Thread | None = None
        self._stop_lock = threading.Lock()

    def start(self) -> None:
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return

        self._stop_event.clear()
        self._writer_thread = threading.Thread(
            target=self._run_writer_loop,
            name="neocortex-decision-ledger-writer",
            daemon=True,
        )
        self._cleanup_thread = threading.Thread(
            target=self._run_cleanup_loop,
            name="neocortex-decision-ledger-cleanup",
            daemon=True,
        )
        self._writer_thread.start()
        self._cleanup_thread.start()

    def stop(self) -> None:
        with self._stop_lock:
            self._stop_event.set()
            self.flush_expired()

            timeout_sec = self._shutdown_timeout_ms / 1000.0
            deadline = time.monotonic() + timeout_sec
            self.wait_until_idle(timeout_sec=timeout_sec)

            writer_alive = self._join_thread_until_deadline(
                self._writer_thread, deadline)
            cleanup_alive = self._join_thread_until_deadline(
                self._cleanup_thread, deadline)

            unfinished = self._unfinished_queue_items()
            if unfinished > 0 or writer_alive or cleanup_alive:
                self._record_unclean_shutdown(
                    unfinished_queue_items=unfinished,
                    writer_alive=writer_alive,
                    cleanup_alive=cleanup_alive,
                )

            if self._writer_thread is not None and not self._writer_thread.is_alive():
                self._writer_thread = None
            if self._cleanup_thread is not None and not self._cleanup_thread.is_alive():
                self._cleanup_thread = None

            if self._unfinished_queue_items() == 0 and self._write_queue.qsize() == 0:
                set_neocortex_ledger_queue_depth(0)
            else:
                self._update_queue_depth_metric()

    def _unfinished_queue_items(self) -> int:
        return int(getattr(self._write_queue, "unfinished_tasks", 0))

    def _join_thread_until_deadline(
        self,
        thread: threading.Thread | None,
        deadline: float,
    ) -> bool:
        if thread is None or not thread.is_alive():
            return False
        remaining = max(0.0, deadline - time.monotonic())
        thread.join(timeout=remaining)
        return thread.is_alive()

    def _record_unclean_shutdown(
        self,
        *,
        unfinished_queue_items: int,
        writer_alive: bool,
        cleanup_alive: bool,
    ) -> None:
        if unfinished_queue_items > 0:
            inc_neocortex_ledger_shutdown_undrained(
                reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN.value,
                count=unfinished_queue_items,
            )
        if writer_alive or cleanup_alive:
            inc_neocortex_async_forced_stop(
                component="decision_outcome_ledger",
                reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN.value,
            )
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            FailureReasonCode.UNCLEAN_SHUTDOWN,
            location="logic/ledger/decision_outcome_ledger.py:stop",
            message="Decision outcome ledger shutdown incomplete",
            detail={
                "unfinished_queue_items": unfinished_queue_items,
                "writer_alive": writer_alive,
                "cleanup_alive": cleanup_alive,
            },
        )
        self.logger.warning(
            "Decision outcome ledger shutdown incomplete unfinished=%s writer_alive=%s cleanup_alive=%s",
            unfinished_queue_items,
            writer_alive,
            cleanup_alive,
        )

    def _update_queue_depth_metric(self) -> None:
        set_neocortex_ledger_queue_depth(self._write_queue.qsize())

    def register(self, fsm: _FSMLike) -> None:
        fsm.listen(
            "SHADOW:NEOCORTEX_DECISION_LOGGED",
            self._on_shadow_decision_logged,
        )
        fsm.listen("EVT:TRADE_INTENT_PROPOSED", self._on_trade_intent_proposed)
        fsm.listen("EVT:TRADE_EXECUTED",
                   self._make_execution_handler("EVT:TRADE_EXECUTED"))
        for event_name in (
            "EVT:POSITION_CLOSED",
            "EVT:DECISION_BLOCKED",
            "EVT:EXECUTION_GUARD_BLOCKED",
            "EVT:TRADE_INTENT_REJECTED",
            "EVT:ORDER_REJECTED",
        ):
            fsm.listen(event_name, self._make_terminal_handler(event_name))

    def _make_execution_handler(self, event_name: str) -> Callable[[object], None]:
        def _handler(event: object) -> None:
            self._on_execution_enrichment(event_name, event)

        return _handler

    def _make_terminal_handler(self, event_name: str) -> Callable[[object], None]:
        def _handler(event: object) -> None:
            self._on_terminal_event(event_name, event)

        return _handler

    def wait_until_idle(self, timeout_sec: float = 2.0) -> bool:
        deadline = time.time() + max(0.0, float(timeout_sec))
        while time.time() < deadline:
            if getattr(self._write_queue, "unfinished_tasks", 0) == 0:
                return True
            time.sleep(0.01)
        return getattr(self._write_queue, "unfinished_tasks", 0) == 0

    def flush_expired(self, *, now_ms: int | None = None) -> int:
        current_ms = int(now_ms if now_ms is not None else self._clock_ms())
        expired: list[_PendingDecision] = []
        with self._lock:
            for decision_id, entry in list(self._pending_by_decision_id.items()):
                if entry.expires_at_ms > current_ms:
                    continue
                expired.append(self._remove_entry_locked(decision_id))

        for entry in expired:
            row = self._build_row(
                entry,
                terminal_status=DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
                invalid_reason_code="TERMINAL_EVENT_MISSING",
                realized_pnl_net=None,
                fees=None,
                joined_by=None,
            )
            self._enqueue_row(row)
        return len(expired)

    def _cleanup_loop(self) -> None:
        while not self._stop_event.wait(self._cleanup_interval_ms / 1000.0):
            try:
                self.flush_expired()
            except (OSError, TypeError, ValueError) as exc:
                record_failure_outcome(
                    FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                    FailureReasonCode.TELEMETRY_FLUSH_FAILED,
                    location="logic/ledger/decision_outcome_ledger.py:_cleanup_loop",
                    message="Decision outcome ledger cleanup sweep failed",
                    detail=str(exc),
                )
                self.logger.warning(
                    "Decision outcome ledger cleanup sweep failed",
                    exc_info=True,
                )

    def _run_cleanup_loop(self) -> None:
        try:
            self._cleanup_loop()
        except (AssertionError, AttributeError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                FailureReasonCode.HANDLER_FAILURE,
                location="logic/ledger/decision_outcome_ledger.py:_run_cleanup_loop",
                message="Decision outcome ledger cleanup thread crashed",
                detail=type(exc).__name__,
            )
            self.logger.exception(
                "Decision outcome ledger cleanup thread crashed",
                exc_info=exc,
            )

    def _writer_loop(self) -> None:
        while True:
            try:
                item = self._write_queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    return
                continue
            self._update_queue_depth_metric()
            try:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(_to_jsonable(item),
                                   ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
            except (OSError, TypeError, ValueError) as exc:
                inc_neocortex_ledger_write_failed(
                    reason_code=FailureReasonCode.TELEMETRY_FLUSH_FAILED.value,
                )
                record_failure_outcome(
                    FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                    FailureReasonCode.TELEMETRY_FLUSH_FAILED,
                    location="logic/ledger/decision_outcome_ledger.py:_writer_loop",
                    message="Failed to append decision outcome ledger row",
                    detail=str(exc),
                )
                self.logger.warning(
                    "Failed to append decision outcome ledger row",
                    exc_info=True,
                )
            finally:
                self._write_queue.task_done()

    def _run_writer_loop(self) -> None:
        try:
            self._writer_loop()
        except (AssertionError, AttributeError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                FailureReasonCode.HANDLER_FAILURE,
                location="logic/ledger/decision_outcome_ledger.py:_run_writer_loop",
                message="Decision outcome ledger writer thread crashed",
                detail=type(exc).__name__,
            )
            self.logger.exception(
                "Decision outcome ledger writer thread crashed",
                exc_info=exc,
            )

    def _record_queue_overflow(self, row: DecisionOutcomeLedgerRow) -> None:
        reason_code = FailureReasonCode.TELEMETRY_FLUSH_FAILED
        inc_neocortex_ledger_queue_dropped(
            policy=self._overflow_policy,
            reason_code=reason_code.value,
        )
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            reason_code,
            location="logic/ledger/decision_outcome_ledger.py:_enqueue_row",
            message="Decision outcome ledger queue full; row not enqueued",
            detail=row.decision_id,
        )
        self.logger.warning(
            "Decision outcome ledger queue full policy=%s depth=%s maxsize=%s decision_id=%s",
            self._overflow_policy,
            self._write_queue.qsize(),
            self._queue_maxsize,
            row.decision_id,
        )

    def _enqueue_row(self, row: DecisionOutcomeLedgerRow) -> bool:
        payload = row.model_dump(mode="json")
        try:
            if self._enqueue_timeout_ms == 0:
                self._write_queue.put_nowait(payload)
            else:
                self._write_queue.put(
                    payload,
                    timeout=self._enqueue_timeout_ms / 1000.0,
                )
            self._update_queue_depth_metric()
            return True
        except queue.Full:
            self._update_queue_depth_metric()
            self._record_queue_overflow(row)
            return False

    def _on_shadow_decision_logged(self, event: Mapping[str, object] | _EventLike | object) -> None:
        payload = _payload_view(event)
        decision_id = _string_alias(payload, "decision_id")
        rid = _string_alias(payload, "rid", "corr_id")
        symbol = _string_alias(payload, "symbol")
        if decision_id is None or rid is None or symbol is None:
            return

        raw_flags = payload.get("data_quality_flags")
        flags = _json_object(raw_flags)
        request_ts_ms = self._coerce_request_ts_ms(payload)
        response_ts_ms = self._coerce_response_ts_ms(payload, request_ts_ms)
        raw_snapshot = payload.get("causal_state_snapshot")
        snapshot = _json_object(raw_snapshot)
        support_quality = self._build_support_quality(flags, payload, snapshot)
        stress_metrics = _json_object(snapshot.get("stress_metrics"))

        entry = _PendingDecision(
            decision_id=decision_id,
            rid=rid,
            symbol=symbol.upper(),
            authority_mode=self._resolve_authority_mode(payload, flags),
            request_ts_ms=request_ts_ms,
            response_ts_ms=response_ts_ms,
            apply_result=_string_alias(
                payload, "apply_result") or _string_alias(flags, "apply_result"),
            fallback_reason=_string_alias(payload, "fallback_reason"),
            causal_state_snapshot=snapshot,
            neocortex_action=_normalize_action(
                payload.get("action") or payload.get("neocortex_action")
            ),
            data_quality_flags=flags,
            stress_metrics=stress_metrics,
            support_quality=support_quality,
            expires_at_ms=response_ts_ms + self._pending_ttl_ms,
        )

        with self._lock:
            self._pending_by_decision_id[decision_id] = entry
            self._register_alias_locked(entry, rid=rid)

    def _on_trade_intent_proposed(self, event: Mapping[str, object] | _EventLike | object) -> None:
        payload = _payload_view(event)
        authority_context = payload.get("authority_context")
        authority_payload = (
            dict(authority_context) if isinstance(
                authority_context, dict) else {}
        )
        entry, _ = self._find_matching_entry(payload, pop=False)
        if entry is None and authority_payload:
            entry = self._get_pending_by_decision_id(
                _string_alias(authority_payload, "decision_id")
            )
        if entry is None:
            return

        lifecycle_id = _string_alias(
            payload,
            "lifecycle_id",
            "idempotent_key",
            "reservation_id",
        )
        downstream_rid = _string_alias(payload, "rid", "corr_id")

        with self._lock:
            current = self._pending_by_decision_id.get(entry.decision_id)
            if current is None:
                return
            if authority_payload:
                authority_mode = _string_alias(
                    authority_payload, "authority_mode")
                if authority_mode is not None:
                    current.authority_mode = _normalize_authority_mode(
                        authority_mode)
                apply_result = _string_alias(authority_payload, "apply_result")
                if apply_result is not None:
                    current.apply_result = apply_result
                action = _string_alias(authority_payload, "action")
                if action is not None:
                    current.neocortex_action = _normalize_action(action)
                fallback_reason = _string_alias(
                    authority_payload, "fallback_reason")
                if fallback_reason is not None:
                    current.fallback_reason = fallback_reason
            self._register_alias_locked(
                current,
                rid=downstream_rid,
                lifecycle_id=lifecycle_id,
            )

    def _on_execution_enrichment(
        self,
        event_name: str,
        event: Mapping[str, object] | _EventLike | object,
    ) -> None:
        if event_name != "EVT:TRADE_EXECUTED":
            return
        payload = _payload_view(event)
        entry, _ = self._find_matching_entry(payload, pop=False)
        if entry is None:
            return
        trade_id = _string_alias(payload, "trade_id", "tradeId")
        lifecycle_id = _string_alias(payload, "lifecycle_id", "idempotent_key")
        downstream_rid = _string_alias(payload, "rid", "corr_id")
        with self._lock:
            current = self._pending_by_decision_id.get(entry.decision_id)
            if current is None:
                return
            self._register_alias_locked(
                current,
                rid=downstream_rid,
                lifecycle_id=lifecycle_id,
                trade_id=trade_id,
            )

    def _on_terminal_event(
        self,
        event_name: str,
        event: Mapping[str, object] | _EventLike | object,
    ) -> None:
        payload = _payload_view(event)
        entry, joined_by = self._find_matching_entry(payload, pop=True)
        if entry is None:
            return

        terminal_status, invalid_reason_code = self._classify_terminal_event(
            event_name,
            payload,
            entry,
        )
        realized_pnl_net, fees = self._extract_terminal_values(
            event_name,
            payload,
            entry,
            terminal_status,
        )
        row = self._build_row(
            entry,
            terminal_status=terminal_status,
            invalid_reason_code=invalid_reason_code,
            realized_pnl_net=realized_pnl_net,
            fees=fees,
            joined_by=joined_by,
        )
        self._enqueue_row(row)

    def _coerce_request_ts_ms(self, payload: Mapping[str, object]) -> int:
        for key in ("request_ts_ms", "decision_ts_ms", "response_ts_ms"):
            numeric_value = _safe_int(payload.get(key))
            if numeric_value is not None:
                return numeric_value
        return int(self._clock_ms())

    def _coerce_response_ts_ms(
        self,
        payload: Mapping[str, object],
        request_ts_ms: int,
    ) -> int:
        for key in ("response_ts_ms", "decision_ts_ms", "request_ts_ms"):
            numeric_value = _safe_int(payload.get(key))
            if numeric_value is not None:
                return max(numeric_value, request_ts_ms)
        return request_ts_ms

    def _resolve_authority_mode(
        self,
        payload: Mapping[str, object],
        flags: Mapping[str, object],
    ) -> str:
        for candidate in (
            payload.get("authority_mode"),
            flags.get("authority_mode"),
            flags.get("neocortex_enforcement_mode"),
        ):
            normalized = _normalize_authority_mode(candidate)
            if normalized != "unknown":
                return normalized
        capture_mode = _string_alias(payload, "capture_mode") or _string_alias(
            flags, "capture_mode"
        )
        if capture_mode == "journal_only":
            return "shadow"
        apply_result = _string_alias(
            payload, "apply_result") or _string_alias(flags, "apply_result")
        if apply_result is not None:
            upper = apply_result.strip().upper()
            if upper.startswith("GATED_") or upper.startswith("ENFORCE_"):
                return "gated"
            if upper.startswith("ADVISORY_"):
                return "advisory"
            if upper.startswith("SHADOW_"):
                return "shadow"
        return "unknown"

    def _build_support_quality(
        self,
        flags: Mapping[str, object],
        payload: Mapping[str, object],
        snapshot: Mapping[str, object],
    ) -> JsonObject:
        support_quality: JsonObject = {
            "supports_counterfactual_join": bool(
                flags.get("supports_counterfactual_join", False)
            ),
            "snapshot_missing": bool(flags.get("snapshot_missing", False)),
            "snapshot_provider_configured": bool(
                flags.get("snapshot_provider_configured", False)
            ),
            "has_nan": bool(flags.get("has_nan", False)),
            "is_stale": bool(flags.get("is_stale", False)),
            "capture_mode": _string_alias(flags, "capture_mode"),
            "authority_applied": _coerce_bool(
                flags.get("authority_applied"), default=True
            ),
            "no_effect": _coerce_bool(flags.get("no_effect"), default=False),
            "counterfactual_evaluation": _coerce_bool(
                flags.get("counterfactual_evaluation"), default=False
            ),
            "returned_action_present": _string_alias(
                flags, "returned_action"
            ) is not None,
            "explicit_request_ts_present": _explicit_timestamp_present(
                payload, "request_ts_ms"
            ),
            "explicit_response_ts_present": _explicit_timestamp_present(
                payload, "response_ts_ms"
            ),
        }
        support_quality.update(_observation_time_support(snapshot))
        return support_quality

    def _classify_terminal_event(
        self,
        event_name: str,
        payload: Mapping[str, object],
        entry: _PendingDecision,
    ) -> tuple[DecisionOutcomeTerminalStatus, str | None]:
        if event_name == "EVT:POSITION_CLOSED":
            lifecycle_id = _string_alias(
                payload,
                "lifecycle_id",
                "idempotent_key",
                "reservation_id",
            )
            trade_id = _string_alias(payload, "trade_id", "tradeId")
            if lifecycle_id is None or trade_id is None:
                return (
                    DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
                    "UNJOINABLE_LIFECYCLE",
                )
            pnl_status = _string_alias(payload, "pnl_status")
            realized_pnl_net = _safe_float(
                payload.get("realized_pnl_net")
                or payload.get("net_pnl")
                or payload.get("realized_pnl")
            )
            if (
                (pnl_status is not None and pnl_status.strip().lower() != "resolved")
                or realized_pnl_net is None
            ):
                return (
                    DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
                    "TERMINAL_PNL_MISSING",
                )
            if self._is_fallback(entry):
                return DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED, None
            return DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED, None

        if event_name == "EVT:DECISION_BLOCKED":
            reason_code = _string_alias(payload, "reason_code", "block_reason")
            if str(reason_code or "").strip().upper() == "NEOCORTEX_VETO":
                return DecisionOutcomeTerminalStatus.VETOED, None

        if self._is_fallback(entry):
            return DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_NO_EXECUTION, None

        return DecisionOutcomeTerminalStatus.REJECTED_UPSTREAM, None

    def _extract_terminal_values(
        self,
        event_name: str,
        payload: Mapping[str, object],
        entry: _PendingDecision,
        terminal_status: DecisionOutcomeTerminalStatus,
    ) -> tuple[float | None, float | None]:
        lifecycle_id = _string_alias(
            payload,
            "lifecycle_id",
            "idempotent_key",
            "reservation_id",
        )
        trade_id = _string_alias(payload, "trade_id", "tradeId")
        downstream_rid = _string_alias(payload, "rid", "corr_id")
        if downstream_rid is not None:
            normalized_rid = downstream_rid.strip()
            if normalized_rid and (
                entry.downstream_rid is None or entry.downstream_rid == entry.rid
            ):
                entry.downstream_rid = normalized_rid
        if lifecycle_id is not None:
            normalized_lifecycle_id = lifecycle_id.strip()
            if normalized_lifecycle_id and entry.lifecycle_id is None:
                entry.lifecycle_id = normalized_lifecycle_id
        if trade_id is not None:
            normalized_trade_id = trade_id.strip()
            if normalized_trade_id and entry.trade_id is None:
                entry.trade_id = normalized_trade_id

        if event_name != "EVT:POSITION_CLOSED":
            return None, None
        realized_pnl_net = _safe_float(
            payload.get("realized_pnl_net")
            or payload.get("net_pnl")
            or payload.get("realized_pnl")
        )
        fees = _safe_float(payload.get("fees"))
        if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
            return None, fees
        return realized_pnl_net, fees

    def _dataset_visibility(
        self,
        entry: _PendingDecision,
        terminal_status: DecisionOutcomeTerminalStatus,
        invalid_reason_code: str | None,
    ) -> DatasetVisibility:
        if invalid_reason_code is not None or entry.authority_mode == "unknown":
            return "diagnostics_only"
        if entry.support_quality.get("capture_mode") == "journal_only":
            return "diagnostics_only"
        if not entry.support_quality.get("authority_applied", True):
            return "diagnostics_only"
        if entry.support_quality.get("no_effect", False):
            return "diagnostics_only"
        if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
            return "diagnostics_only"
        if not entry.support_quality.get("supports_counterfactual_join", False):
            return "diagnostics_only"
        if entry.support_quality.get("snapshot_missing", False):
            return "diagnostics_only"
        if entry.support_quality.get("has_nan", False):
            return "diagnostics_only"
        if entry.support_quality.get("is_stale", False):
            return "diagnostics_only"
        return "trainable"

    def _resolve_trainable_invalid_reason(
        self,
        entry: _PendingDecision,
        invalid_reason_code: str | None,
    ) -> str | None:
        if invalid_reason_code is not None:
            return invalid_reason_code
        if not entry.support_quality.get("explicit_request_ts_present", False):
            return FailureReasonCode.MISSING_REQUIRED_STATE.value
        if not entry.support_quality.get("explicit_response_ts_present", False):
            return FailureReasonCode.MISSING_REQUIRED_STATE.value
        if not entry.support_quality.get("observation_provenance_present", False):
            return FailureReasonCode.MISSING_REQUIRED_STATE.value
        if not entry.support_quality.get("observation_event_ts_present", False):
            return FailureReasonCode.MISSING_REQUIRED_STATE.value
        if not entry.support_quality.get("observation_provenance_causal", False):
            return FailureReasonCode.NON_CAUSAL_TIME.value
        if not entry.support_quality.get("observation_time_is_causal", False):
            return FailureReasonCode.NON_CAUSAL_TIME.value
        if not entry.support_quality.get("observation_trainable", False):
            return FailureReasonCode.MISSING_REQUIRED_STATE.value
        if entry.support_quality.get("observation_dataset_visibility") != "trainable":
            return FailureReasonCode.MISSING_REQUIRED_STATE.value
        return None

    def _counterfactual_support(
        self,
        entry: _PendingDecision,
        terminal_status: DecisionOutcomeTerminalStatus,
        invalid_reason_code: str | None,
    ) -> str:
        if invalid_reason_code is not None or entry.authority_mode == "unknown":
            return "unsupported"
        if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
            return "unsupported"
        if entry.support_quality.get("capture_mode") == "journal_only":
            return "unsupported"
        if not entry.support_quality.get("supports_counterfactual_join", False):
            return "unsupported"
        if entry.support_quality.get("snapshot_missing", False):
            return "unsupported"
        if entry.support_quality.get("has_nan", False):
            return "unsupported"
        if entry.support_quality.get("is_stale", False):
            return "unsupported"
        if not entry.support_quality.get("explicit_request_ts_present", False):
            return "unsupported"
        if not entry.support_quality.get("explicit_response_ts_present", False):
            return "unsupported"
        if not entry.support_quality.get("observation_provenance_present", False):
            return "unsupported"
        if not entry.support_quality.get("observation_event_ts_present", False):
            return "unsupported"
        if not entry.support_quality.get("observation_provenance_causal", False):
            return "unsupported"
        if not entry.support_quality.get("observation_time_is_causal", False):
            return "unsupported"
        if not entry.support_quality.get("observation_trainable", False):
            return "unsupported"
        if entry.support_quality.get("observation_dataset_visibility") != "trainable":
            return "unsupported"
        if entry.support_quality.get("no_effect", False):
            if not entry.support_quality.get("counterfactual_evaluation", False):
                return "unsupported"
            if not entry.support_quality.get("returned_action_present", False):
                return "unsupported"
        return "supported"

    def _build_row(
        self,
        entry: _PendingDecision,
        *,
        terminal_status: DecisionOutcomeTerminalStatus,
        invalid_reason_code: str | None,
        realized_pnl_net: float | None,
        fees: float | None,
        joined_by: str | None,
    ) -> DecisionOutcomeLedgerRow:
        flags = dict(entry.data_quality_flags)
        flags.setdefault("snapshot_missing", not bool(
            entry.causal_state_snapshot))
        flags.setdefault("supports_counterfactual_join", False)
        flags["terminal_event_missing"] = (
            terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET
            and invalid_reason_code == "TERMINAL_EVENT_MISSING"
        )
        flags["joined_by_decision_id"] = joined_by == "decision_id"
        flags["joined_by_rid"] = joined_by == "rid"
        flags["joined_by_lifecycle_id"] = joined_by == "lifecycle_id"
        flags["joined_by_trade_id"] = joined_by == "trade_id"
        flags["pnl_missing"] = realized_pnl_net is None
        flags["request_ts_missing"] = not bool(
            entry.support_quality.get("explicit_request_ts_present", False)
        )
        flags["response_ts_missing"] = not bool(
            entry.support_quality.get("explicit_response_ts_present", False)
        )
        flags["observation_causal_proof_missing"] = not bool(
            entry.support_quality.get("observation_provenance_present", False)
        )
        flags["observation_non_causal"] = bool(
            entry.support_quality.get("observation_provenance_present", False)
            and not entry.support_quality.get("observation_provenance_causal", False)
        )

        support_quality = dict(entry.support_quality)
        support_quality["joined_by"] = joined_by
        support_quality["terminal_status"] = terminal_status.value
        effective_invalid_reason_code = self._resolve_trainable_invalid_reason(
            entry,
            invalid_reason_code,
        )
        counterfactual_support = self._counterfactual_support(
            entry,
            terminal_status,
            effective_invalid_reason_code,
        )
        support_quality["counterfactual_support"] = counterfactual_support
        if effective_invalid_reason_code is not None:
            inc_neocortex_dataset_invalid(effective_invalid_reason_code)

        return DecisionOutcomeLedgerRow(
            decision_id=entry.decision_id,
            rid=entry.rid,
            symbol=entry.symbol,
            authority_mode=entry.authority_mode,
            request_ts_ms=entry.request_ts_ms,
            response_ts_ms=entry.response_ts_ms,
            apply_result=entry.apply_result,
            fallback_reason=entry.fallback_reason,
            downstream_rid=entry.downstream_rid,
            lifecycle_id=entry.lifecycle_id,
            trade_id=entry.trade_id,
            terminal_status=terminal_status,
            realized_pnl_net=realized_pnl_net,
            fees=fees,
            stress_metrics=dict(entry.stress_metrics),
            support_quality=support_quality,
            dataset_visibility=self._dataset_visibility(
                entry,
                terminal_status,
                effective_invalid_reason_code,
            ),
            counterfactual_support=counterfactual_support,
            invalid_reason_code=effective_invalid_reason_code,
            causal_state_snapshot=dict(entry.causal_state_snapshot),
            neocortex_action=entry.neocortex_action,
            data_quality_flags=flags,
        )

    def _is_fallback(self, entry: _PendingDecision) -> bool:
        apply_result = str(entry.apply_result or "").strip().upper()
        return (
            entry.neocortex_action == "FALLBACK"
            or bool(entry.fallback_reason)
            or apply_result.startswith("FALLBACK")
        )

    def _get_pending_by_decision_id(
        self,
        decision_id: str | None,
    ) -> _PendingDecision | None:
        if decision_id is None:
            return None
        with self._lock:
            return self._pending_by_decision_id.get(decision_id)

    def _find_matching_entry(
        self,
        payload: Mapping[str, object],
        *,
        pop: bool,
    ) -> tuple[_PendingDecision | None, str | None]:
        decision_id = _string_alias(
            payload, "decision_id", "control_decision_id")
        rid = _string_alias(payload, "rid", "corr_id", "downstream_rid")
        lifecycle_id = _string_alias(
            payload,
            "lifecycle_id",
            "idempotent_key",
            "reservation_id",
        )
        trade_id = _string_alias(payload, "trade_id", "tradeId")

        with self._lock:
            if decision_id and decision_id in self._pending_by_decision_id:
                entry = (
                    self._remove_entry_locked(decision_id)
                    if pop
                    else self._pending_by_decision_id.get(decision_id)
                )
                return entry, "decision_id"

            if rid:
                matched_decision_id = self._decision_id_by_rid.get(rid)
                if matched_decision_id is not None:
                    if matched_decision_id not in self._pending_by_decision_id:
                        self._decision_id_by_rid.pop(rid, None)
                        matched_decision_id = None
                if matched_decision_id is not None:
                    entry = (
                        self._remove_entry_locked(matched_decision_id)
                        if pop
                        else self._pending_by_decision_id.get(matched_decision_id)
                    )
                    return entry, "rid"

            if lifecycle_id:
                matched_decision_id = self._decision_id_by_lifecycle_id.get(
                    lifecycle_id)
                if matched_decision_id is not None:
                    if matched_decision_id not in self._pending_by_decision_id:
                        self._decision_id_by_lifecycle_id.pop(
                            lifecycle_id, None)
                        matched_decision_id = None
                if matched_decision_id is not None:
                    entry = (
                        self._remove_entry_locked(matched_decision_id)
                        if pop
                        else self._pending_by_decision_id.get(matched_decision_id)
                    )
                    return entry, "lifecycle_id"

            if trade_id:
                matched_decision_id = self._decision_id_by_trade_id.get(
                    trade_id)
                if matched_decision_id is not None:
                    if matched_decision_id not in self._pending_by_decision_id:
                        self._decision_id_by_trade_id.pop(trade_id, None)
                        matched_decision_id = None
                if matched_decision_id is not None:
                    entry = (
                        self._remove_entry_locked(matched_decision_id)
                        if pop
                        else self._pending_by_decision_id.get(matched_decision_id)
                    )
                    return entry, "trade_id"
        return None, None

    def _register_alias_locked(
        self,
        entry: _PendingDecision,
        *,
        rid: str | None = None,
        lifecycle_id: str | None = None,
        trade_id: str | None = None,
    ) -> None:
        if rid is not None:
            normalized_rid = rid.strip()
            if normalized_rid:
                entry.rid_aliases.add(normalized_rid)
                self._decision_id_by_rid[normalized_rid] = entry.decision_id
                if entry.downstream_rid is None or entry.downstream_rid == entry.rid:
                    entry.downstream_rid = normalized_rid
        if lifecycle_id is not None:
            normalized_lifecycle_id = lifecycle_id.strip()
            if normalized_lifecycle_id:
                entry.lifecycle_aliases.add(normalized_lifecycle_id)
                self._decision_id_by_lifecycle_id[normalized_lifecycle_id] = (
                    entry.decision_id
                )
                if entry.lifecycle_id is None:
                    entry.lifecycle_id = normalized_lifecycle_id
        if trade_id is not None:
            normalized_trade_id = trade_id.strip()
            if normalized_trade_id:
                entry.trade_aliases.add(normalized_trade_id)
                self._decision_id_by_trade_id[normalized_trade_id] = entry.decision_id
                if entry.trade_id is None:
                    entry.trade_id = normalized_trade_id

    def _remove_entry_locked(self, decision_id: str) -> _PendingDecision:
        entry = self._pending_by_decision_id.pop(decision_id)
        for rid in entry.rid_aliases:
            self._decision_id_by_rid.pop(rid, None)
        for lifecycle_id in entry.lifecycle_aliases:
            self._decision_id_by_lifecycle_id.pop(lifecycle_id, None)
        for trade_id in entry.trade_aliases:
            self._decision_id_by_trade_id.pop(trade_id, None)
        return entry


__all__ = ["DecisionOutcomeLedgerSink"]
