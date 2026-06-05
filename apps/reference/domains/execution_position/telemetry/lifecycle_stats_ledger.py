"""Execution-owned lifecycle path stats ledger.

The ledger is append-only and owned by execution_position. It persists
provisional open-lifecycle snapshots and final closed-lifecycle rows without
delegating ownership to sidecar telemetry.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from apps.reference.core.time import get_clock

RECORD_KIND = "execution_lifecycle_stats"
SCHEMA_VERSION = "execution_lifecycle_stats_v1"
PROVISIONAL_ROW_STATUS = "PROVISIONAL"
FINAL_ROW_STATUS = "FINAL"


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_side(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"BUY", "LONG"}:
        return "BUY"
    if normalized in {"SELL", "SHORT"}:
        return "SELL"
    raise ValueError(f"Unsupported lifecycle side: {value!r}")


def _side_sign(side: str) -> int:
    return 1 if _normalize_side(side) == "BUY" else -1


def _compute_bps(value_usdt: float, entry_price: float, qty: float) -> float:
    notional = abs(entry_price * qty)
    if notional <= 0.0:
        return 0.0
    return (value_usdt / notional) * 10_000.0


def iter_execution_lifecycle_stats_rows(
    *,
    log_file: str = "logs/execution_lifecycle_stats_v1.jsonl",
) -> Iterator[dict[str, Any]]:
    target = Path(log_file)
    if not target.exists():
        return
    with target.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("record_kind") != RECORD_KIND:
                continue
            yield record


def load_latest_execution_lifecycle_row(
    *,
    lifecycle_id: Optional[str] = None,
    entry_rid: Optional[str] = None,
    log_file: str = "logs/execution_lifecycle_stats_v1.jsonl",
) -> Optional[dict[str, Any]]:
    if not lifecycle_id and not entry_rid:
        raise ValueError("lifecycle_id or entry_rid is required")
    latest: Optional[dict[str, Any]] = None
    for row in iter_execution_lifecycle_stats_rows(log_file=log_file):
        if lifecycle_id and row.get("lifecycle_id") == lifecycle_id:
            latest = row
        elif entry_rid and row.get("entry_rid") == entry_rid:
            latest = row
    return latest


@dataclass
class ExecutionLifecycleStatsRow:
    record_kind: str = RECORD_KIND
    schema_version: str = SCHEMA_VERSION
    owner: str = "execution_position"
    row_status: str = PROVISIONAL_ROW_STATUS
    provisional_status: Optional[str] = None
    provenance_source: Optional[str] = None
    recorded_ts_ms: int = 0

    lifecycle_id: str = ""
    entry_rid: str = ""
    symbol: str = ""
    side: str = ""
    entry_ts_ms: Optional[int] = None
    entry_price: Optional[float] = None
    qty: Optional[float] = None

    best_price_in_trade_direction: Optional[float] = None
    worst_price_against_trade: Optional[float] = None
    mfe_usdt: Optional[float] = None
    mae_usdt: Optional[float] = None
    mfe_bps: Optional[float] = None
    mae_bps: Optional[float] = None
    first_positive_pnl_ts_ms: Optional[int] = None
    peak_edge_usd: Optional[float] = None
    peak_giveback_usd: Optional[float] = None
    peak_giveback_pct: Optional[float] = None
    current_unrealized_at_close_request: Optional[float] = None

    close_ts_ms: Optional[int] = None
    close_actor: Optional[str] = None
    close_reason: Optional[str] = None
    gross_pnl: Optional[float] = None
    fees: Optional[float] = None
    net_pnl: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionLifecycleStatsLedger:
    def __init__(
        self,
        log_file: str = "logs/execution_lifecycle_stats_v1.jsonl",
        *,
        clock_ms_fn: Optional[Callable[[], int]] = None,
    ) -> None:
        self._log_file = Path(log_file)
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._clock_ms_fn = clock_ms_fn or (lambda: int(get_clock().now_ms()))
        self._latest_by_lifecycle: dict[str, ExecutionLifecycleStatsRow] = {}
        self._latest_by_entry_rid: dict[str, str] = {}
        self._fingerprints_by_lifecycle: dict[str, tuple[Any, ...]] = {}

    def _now_ms(self) -> int:
        return int(self._clock_ms_fn())

    def _fingerprint(self, row: ExecutionLifecycleStatsRow) -> tuple[Any, ...]:
        return (
            row.row_status,
            row.provisional_status,
            row.provenance_source,
            row.lifecycle_id,
            row.entry_rid,
            row.symbol,
            row.side,
            row.entry_ts_ms,
            row.entry_price,
            row.qty,
            row.best_price_in_trade_direction,
            row.worst_price_against_trade,
            row.mfe_usdt,
            row.mae_usdt,
            row.mfe_bps,
            row.mae_bps,
            row.first_positive_pnl_ts_ms,
            row.peak_edge_usd,
            row.peak_giveback_usd,
            row.peak_giveback_pct,
            row.current_unrealized_at_close_request,
            row.close_ts_ms,
            row.close_actor,
            row.close_reason,
            row.gross_pnl,
            row.fees,
            row.net_pnl,
        )

    def _append_row(self, row: ExecutionLifecycleStatsRow) -> ExecutionLifecycleStatsRow:
        persisted = replace(row, recorded_ts_ms=self._now_ms())
        with self._log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(persisted.to_dict(),
                         ensure_ascii=False) + "\n")
        self._latest_by_lifecycle[persisted.lifecycle_id] = persisted
        self._latest_by_entry_rid[persisted.entry_rid] = persisted.lifecycle_id
        self._fingerprints_by_lifecycle[persisted.lifecycle_id] = self._fingerprint(
            persisted
        )
        return persisted

    def _append_if_changed(
        self,
        row: ExecutionLifecycleStatsRow,
    ) -> Optional[ExecutionLifecycleStatsRow]:
        fingerprint = self._fingerprint(row)
        if self._fingerprints_by_lifecycle.get(row.lifecycle_id) == fingerprint:
            return None
        return self._append_row(row)

    def get_latest(
        self,
        *,
        lifecycle_id: Optional[str] = None,
        entry_rid: Optional[str] = None,
    ) -> Optional[ExecutionLifecycleStatsRow]:
        resolved_lifecycle_id = lifecycle_id
        if resolved_lifecycle_id is None and entry_rid is not None:
            resolved_lifecycle_id = self._latest_by_entry_rid.get(entry_rid)
        if resolved_lifecycle_id is None:
            return None
        return self._latest_by_lifecycle.get(resolved_lifecycle_id)

    def seed_entry(
        self,
        *,
        lifecycle_id: str,
        entry_rid: str,
        symbol: str,
        side: str,
        entry_ts_ms: int,
        entry_price: float,
        qty: float,
        fees: Optional[float] = None,
        source: str = "order_fill",
    ) -> Optional[ExecutionLifecycleStatsRow]:
        normalized_price = _to_float(entry_price)
        normalized_qty = _to_float(qty)
        if normalized_price is None or normalized_qty is None:
            raise ValueError(
                "entry_price and qty are required for lifecycle seed")
        row = ExecutionLifecycleStatsRow(
            row_status=PROVISIONAL_ROW_STATUS,
            provisional_status="entry_filled",
            provenance_source=source,
            lifecycle_id=str(lifecycle_id),
            entry_rid=str(entry_rid),
            symbol=str(symbol).strip().upper(),
            side=_normalize_side(side),
            entry_ts_ms=int(entry_ts_ms),
            entry_price=normalized_price,
            qty=normalized_qty,
            best_price_in_trade_direction=normalized_price,
            worst_price_against_trade=normalized_price,
            mfe_usdt=0.0,
            mae_usdt=0.0,
            mfe_bps=0.0,
            mae_bps=0.0,
            first_positive_pnl_ts_ms=None,
            peak_edge_usd=0.0,
            peak_giveback_usd=0.0,
            peak_giveback_pct=0.0,
            fees=_to_float(fees),
        )
        return self._append_if_changed(row)

    def update_open(
        self,
        *,
        lifecycle_id: str,
        mark_price: Optional[float],
        observed_ts_ms: Optional[int] = None,
        unrealized_pnl: Optional[float] = None,
        source: str = "portfolio_state_updated",
        provisional_status: str = "open_live",
    ) -> Optional[ExecutionLifecycleStatsRow]:
        current = self.get_latest(lifecycle_id=lifecycle_id)
        if current is None:
            raise KeyError(
                f"Unknown lifecycle_id for provisional update: {lifecycle_id}")
        normalized_mark = _to_float(mark_price)
        if normalized_mark is None or current.entry_price is None or current.qty is None:
            return None
        observed_ts_ms = int(observed_ts_ms or self._now_ms())
        qty = abs(current.qty)
        sign = _side_sign(current.side)
        best_price = current.best_price_in_trade_direction or current.entry_price
        worst_price = current.worst_price_against_trade or current.entry_price

        if sign > 0:
            best_price = max(best_price, normalized_mark)
            worst_price = min(worst_price, normalized_mark)
            mfe_usdt = max((best_price - current.entry_price) * qty, 0.0)
            mae_usdt = max((current.entry_price - worst_price) * qty, 0.0)
            computed_unrealized = (normalized_mark - current.entry_price) * qty
        else:
            best_price = min(best_price, normalized_mark)
            worst_price = max(worst_price, normalized_mark)
            mfe_usdt = max((current.entry_price - best_price) * qty, 0.0)
            mae_usdt = max((worst_price - current.entry_price) * qty, 0.0)
            computed_unrealized = (current.entry_price - normalized_mark) * qty

        active_unrealized = _to_float(unrealized_pnl)
        if active_unrealized is None:
            active_unrealized = computed_unrealized

        peak_edge = max(current.peak_edge_usd or 0.0, active_unrealized)
        if peak_edge > 0.0:
            peak_giveback_usd = max(peak_edge - active_unrealized, 0.0)
            peak_giveback_pct = (peak_giveback_usd / peak_edge) * 100.0
        else:
            peak_giveback_usd = 0.0
            peak_giveback_pct = 0.0

        first_positive_pnl_ts_ms = current.first_positive_pnl_ts_ms
        if first_positive_pnl_ts_ms is None and active_unrealized > 0.0:
            first_positive_pnl_ts_ms = observed_ts_ms

        row = replace(
            current,
            row_status=PROVISIONAL_ROW_STATUS,
            provisional_status=provisional_status,
            provenance_source=source,
            best_price_in_trade_direction=best_price,
            worst_price_against_trade=worst_price,
            mfe_usdt=mfe_usdt,
            mae_usdt=mae_usdt,
            mfe_bps=_compute_bps(mfe_usdt, current.entry_price, qty),
            mae_bps=_compute_bps(mae_usdt, current.entry_price, qty),
            first_positive_pnl_ts_ms=first_positive_pnl_ts_ms,
            peak_edge_usd=peak_edge,
            peak_giveback_usd=peak_giveback_usd,
            peak_giveback_pct=peak_giveback_pct,
        )
        return self._append_if_changed(row)

    def mark_close_requested(
        self,
        *,
        lifecycle_id: str,
        current_unrealized: Optional[float],
        close_actor: Optional[str] = None,
        source: str = "close_request",
    ) -> Optional[ExecutionLifecycleStatsRow]:
        current = self.get_latest(lifecycle_id=lifecycle_id)
        if current is None:
            raise KeyError(
                f"Unknown lifecycle_id for close request: {lifecycle_id}")
        row = replace(
            current,
            row_status=PROVISIONAL_ROW_STATUS,
            provisional_status="close_requested",
            provenance_source=source,
            current_unrealized_at_close_request=_to_float(current_unrealized),
            close_actor=str(close_actor).strip().upper(
            ) if close_actor else current.close_actor,
        )
        return self._append_if_changed(row)

    def finalize_close(
        self,
        *,
        lifecycle_id: str,
        close_ts_ms: int,
        close_actor: Optional[str],
        close_reason: Optional[str],
        gross_pnl: Optional[float],
        fees: Optional[float],
        net_pnl: Optional[float],
        source: str = "position_closed",
    ) -> Optional[ExecutionLifecycleStatsRow]:
        current = self.get_latest(lifecycle_id=lifecycle_id)
        if current is None:
            raise KeyError(
                f"Unknown lifecycle_id for close finalize: {lifecycle_id}")
        row = replace(
            current,
            row_status=FINAL_ROW_STATUS,
            provisional_status=None,
            provenance_source=source,
            close_ts_ms=int(close_ts_ms),
            close_actor=str(close_actor).strip().upper(
            ) if close_actor else current.close_actor,
            close_reason=str(close_reason).strip().upper(
            ) if close_reason else current.close_reason,
            gross_pnl=_to_float(gross_pnl),
            fees=_to_float(fees),
            net_pnl=_to_float(net_pnl),
        )
        return self._append_if_changed(row)
