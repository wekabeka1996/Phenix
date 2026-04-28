"""Async-safe shadow telemetry sink for immutable decision outcome ledger rows."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from apps.reference.domains.decision_making.schemas.control_decision import ControlDecisionAction
from apps.reference.domains.shadow_telemetry.schemas.decision_ledger_row import (
    DecisionOutcomeLedgerRow,
    ExecutionOutcome,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _payload_view(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        payload = event.get("payload") or event.get("pld")
        return dict(payload) if isinstance(payload, dict) else dict(event)
    payload = getattr(event, "pld", None)
    return dict(payload) if isinstance(payload, dict) else {}


def _to_jsonable(value: Any) -> Any:
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
        except Exception:
            return str(value)
    return str(value)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


@dataclass(slots=True)
class _PendingDecision:
    decision_id: str
    rid: str
    symbol: str
    decision_ts_ms: int
    causal_state_snapshot: dict[str, Any]
    neocortex_action: ControlDecisionAction
    fallback_reason: str | None
    data_quality_flags: dict[str, Any]
    expires_at_ms: int


class ShadowTelemetrySink:
    """Thread-backed event-bus sink that joins decisions with terminal outcomes."""

    def __init__(
        self,
        path: str | Path = "logs/shadow_telemetry/decision_ledger_v1.jsonl",
        *,
        pending_ttl_ms: int = 3_600_000,
        cleanup_interval_ms: int = 30_000,
        clock_ms_fn: Optional[Callable[[], int]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pending_ttl_ms = max(1, int(pending_ttl_ms))
        self._cleanup_interval_ms = max(100, int(cleanup_interval_ms))
        self._clock_ms = clock_ms_fn or _now_ms
        self.logger = logger or logging.getLogger(__name__)

        self._lock = threading.Lock()
        self._pending_by_decision_id: dict[str, _PendingDecision] = {}
        self._decision_id_by_rid: dict[str, str] = {}

        self._write_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._stop_event = threading.Event()
        self._writer_thread: threading.Thread | None = None
        self._cleanup_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return

        self._stop_event.clear()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="shadow-telemetry-ledger-writer",
            daemon=True,
        )
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="shadow-telemetry-ledger-cleanup",
            daemon=True,
        )
        self._writer_thread.start()
        self._cleanup_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.flush_expired()
        self.wait_until_idle(timeout_sec=2.0)
        self._write_queue.put(None)
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=2.0)
            self._cleanup_thread = None
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=2.0)
            self._writer_thread = None

    def register(self, fsm: Any) -> None:
        fsm.listen("SHADOW:NEOCORTEX_DECISION_LOGGED",
                   self._on_shadow_decision_logged)
        for event_name in (
            "EVT:TRADE_EXECUTED",
            "EVT:DECISION_BLOCKED",
            "EVT:EXECUTION_GUARD_BLOCKED",
            "EVT:ORDER_REJECTED",
        ):
            fsm.listen(
                event_name,
                lambda event, _event_name=event_name: self._on_terminal_event(
                    _event_name,
                    event,
                ),
            )

    def wait_until_idle(self, timeout_sec: float = 2.0) -> bool:
        deadline = time.time() + max(0.0, float(timeout_sec))
        while time.time() < deadline:
            if getattr(self._write_queue, "unfinished_tasks", 0) == 0:
                return True
            time.sleep(0.01)
        return getattr(self._write_queue, "unfinished_tasks", 0) == 0

    def flush_expired(self, *, now_ms: Optional[int] = None) -> int:
        current_ms = int(now_ms if now_ms is not None else self._clock_ms())
        expired: list[_PendingDecision] = []
        with self._lock:
            for decision_id, entry in list(self._pending_by_decision_id.items()):
                if entry.expires_at_ms > current_ms:
                    continue
                expired.append(entry)
                self._pending_by_decision_id.pop(decision_id, None)
                self._decision_id_by_rid.pop(entry.rid, None)

        for entry in expired:
            row = self._build_row(
                entry,
                execution_outcome=ExecutionOutcome.PENDING_TIMEOUT,
                realized_pnl_net=None,
                joined_by=None,
            )
            self._enqueue_row(row)
        return len(expired)

    def _cleanup_loop(self) -> None:
        while not self._stop_event.wait(self._cleanup_interval_ms / 1000.0):
            try:
                self.flush_expired()
            except Exception:
                self.logger.warning(
                    "Shadow telemetry cleanup sweep failed",
                    exc_info=True,
                )

    def _writer_loop(self) -> None:
        while True:
            item = self._write_queue.get()
            try:
                if item is None:
                    return
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(_to_jsonable(item),
                                   ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
            except Exception:
                self.logger.warning(
                    "Failed to append decision ledger row", exc_info=True)
            finally:
                self._write_queue.task_done()

    def _enqueue_row(self, row: DecisionOutcomeLedgerRow) -> None:
        self._write_queue.put(row.model_dump(mode="json"))

    def _on_shadow_decision_logged(self, event: Any) -> None:
        payload = _payload_view(event)
        decision_id = str(payload.get("decision_id") or "").strip()
        rid = str(payload.get("rid") or "").strip()
        symbol = str(payload.get("symbol") or "").strip().upper()
        if not decision_id or not rid or not symbol:
            return

        try:
            action = ControlDecisionAction(
                str(payload.get("action") or payload.get(
                    "neocortex_action") or "").upper()
            )
        except ValueError:
            action = ControlDecisionAction.FALLBACK

        try:
            decision_ts_ms = int(payload.get(
                "decision_ts_ms") or self._clock_ms())
        except (TypeError, ValueError):
            return

        raw_snapshot = payload.get("causal_state_snapshot")
        raw_flags = payload.get("data_quality_flags")
        entry = _PendingDecision(
            decision_id=decision_id,
            rid=rid,
            symbol=symbol,
            decision_ts_ms=decision_ts_ms,
            causal_state_snapshot=dict(raw_snapshot) if isinstance(
                raw_snapshot, dict) else {},
            neocortex_action=action,
            fallback_reason=payload.get("fallback_reason"),
            data_quality_flags=dict(raw_flags) if isinstance(
                raw_flags, dict) else {},
            expires_at_ms=decision_ts_ms + self._pending_ttl_ms,
        )

        with self._lock:
            self._pending_by_decision_id[decision_id] = entry
            self._decision_id_by_rid[rid] = decision_id

    def _on_terminal_event(self, event_name: str, event: Any) -> None:
        payload = _payload_view(event)
        entry, joined_by = self._pop_matching_entry(payload)
        if entry is None:
            return

        execution_outcome = self._map_execution_outcome(event_name)
        realized_pnl_net = self._extract_realized_pnl_net(event_name, payload)
        row = self._build_row(
            entry,
            execution_outcome=execution_outcome,
            realized_pnl_net=realized_pnl_net,
            joined_by=joined_by,
        )
        self._enqueue_row(row)

    def _pop_matching_entry(self, payload: dict[str, Any]) -> tuple[_PendingDecision | None, str | None]:
        decision_id = str(payload.get("decision_id") or payload.get(
            "control_decision_id") or "").strip()
        rid = str(payload.get("rid") or payload.get("corr_id") or "").strip()

        with self._lock:
            if decision_id and decision_id in self._pending_by_decision_id:
                entry = self._pending_by_decision_id.pop(decision_id)
                self._decision_id_by_rid.pop(entry.rid, None)
                return entry, "decision_id"
            if rid:
                matched_decision_id = self._decision_id_by_rid.pop(rid, None)
                if matched_decision_id is not None:
                    entry = self._pending_by_decision_id.pop(
                        matched_decision_id, None)
                    if entry is not None:
                        return entry, "rid"
        return None, None

    def _map_execution_outcome(self, event_name: str) -> ExecutionOutcome:
        if event_name == "EVT:TRADE_EXECUTED":
            return ExecutionOutcome.EXECUTED
        if event_name == "EVT:ORDER_REJECTED":
            return ExecutionOutcome.EXCHANGE_REJECTED
        return ExecutionOutcome.FSM_BLOCKED

    def _extract_realized_pnl_net(self, event_name: str, payload: dict[str, Any]) -> float | None:
        if event_name != "EVT:TRADE_EXECUTED":
            return None
        return _safe_float(
            payload.get("realized_pnl_net")
            or payload.get("net_pnl")
            or payload.get("realized_pnl")
        )

    def _build_row(
        self,
        entry: _PendingDecision,
        *,
        execution_outcome: ExecutionOutcome,
        realized_pnl_net: float | None,
        joined_by: str | None,
    ) -> DecisionOutcomeLedgerRow:
        flags = dict(entry.data_quality_flags)
        flags.setdefault("snapshot_missing", not bool(
            entry.causal_state_snapshot))
        flags.setdefault("supports_counterfactual_join", False)
        flags["terminal_event_missing"] = execution_outcome == ExecutionOutcome.PENDING_TIMEOUT
        flags["joined_by_decision_id"] = joined_by == "decision_id"
        flags["joined_by_rid"] = joined_by == "rid"
        flags["pnl_missing"] = realized_pnl_net is None

        return DecisionOutcomeLedgerRow(
            decision_id=entry.decision_id,
            rid=entry.rid,
            symbol=entry.symbol,
            decision_ts_ms=entry.decision_ts_ms,
            causal_state_snapshot=entry.causal_state_snapshot,
            neocortex_action=entry.neocortex_action,
            fallback_reason=entry.fallback_reason,
            execution_outcome=execution_outcome,
            realized_pnl_net=realized_pnl_net,
            data_quality_flags=flags,
        )
