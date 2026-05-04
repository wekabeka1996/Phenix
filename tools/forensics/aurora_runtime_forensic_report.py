#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[2]
LOGS = BASE / "logs"
REPORTS = BASE / "reports" / "forensics"

LOCAL_TZ_NAME = "Europe/Kiev"

TEXT_TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")
LOSS_LATCH_RE = re.compile(
    r"\[(?P<symbol>[A-Z0-9]+)\] REGIME_LOSS_EMBARGO loss_latched epoch=(?P<epoch>[^ ]+) pnl_net=(?P<pnl>[-0-9.]+) close_reason=(?P<reason>.+)$"
)
UNPROVEN_RE = re.compile(
    r"\[(?P<symbol>[A-Z0-9]+)\] REGIME_LOSS_EMBARGO unresolved_context current_epoch=(?P<epoch>[^ ]+) entry_epoch=(?P<entry>[^ ]+) pnl=(?P<pnl>.+)$"
)


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()


def _fmt(x: Any, digits: int = 6) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return ""
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _max_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    best = None
    best_key = None
    for row in rows:
        val = row.get(key)
        if val is None:
            continue
        if best is None or val >= best_key:
            best = row
            best_key = val
    return best


def _weighted_avg(values: list[tuple[float, float]]) -> float | None:
    total_qty = sum(q for q, _ in values if q is not None)
    if total_qty <= 0:
        return None
    total_px = sum(q * p for q, p in values if q is not None and p is not None)
    return total_px / total_qty if total_qty else None


def _normalize_side(side: Any) -> str:
    s = str(side or "").strip().upper()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return ""


def _regime_key(row: dict[str, Any]) -> tuple[str, str]:
    sym = str(row.get("symbol") or "")
    rid = str(row.get("rid") or "")
    return sym, rid


@dataclass
class OrderEntity:
    key: str
    order_id: str = ""
    exchange_order_id: str = ""
    client_order_id: str = ""
    rid: str = ""
    lifecycle_id: str = ""
    symbol: str = ""
    strategy_id: str = ""
    side: str = ""
    bracket_role: str = ""
    order_type: str = ""
    tif: str = ""
    reduce_only: bool | None = None
    role: str = ""
    source_event: str = ""
    source_component: str = ""
    source_path: str = ""
    open_ts_ms: int | None = None
    last_state_ts_ms: int | None = None
    final_status: str = ""
    placement_outcome: str = ""
    placed_qty: float | None = None
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    maker_like: str = ""
    reject_reason: str = ""
    timeout_flag: bool = False
    cancel_flag: bool = False
    reconcile_flag: bool = False
    divergence_flag: bool = False
    linkage_trade_id: str = ""
    linkage_position_id: str = ""
    regime: str = ""
    regime_confidence: float | None = None
    regime_epoch_ref: str = ""
    notes: list[str] = field(default_factory=list)
    fill_pairs: list[tuple[float, float]] = field(default_factory=list)

    def update_ts(self, ts_ms: int | None) -> None:
        if ts_ms is None:
            return
        if self.open_ts_ms is None or ts_ms < self.open_ts_ms:
            self.open_ts_ms = ts_ms
        if self.last_state_ts_ms is None or ts_ms > self.last_state_ts_ms:
            self.last_state_ts_ms = ts_ms

    def add_fill(self, qty: float | None, price: float | None) -> None:
        if qty is None or price is None:
            return
        self.fill_pairs.append((qty, price))
        self.filled_qty += qty
        self.avg_fill_price = _weighted_avg(self.fill_pairs)

    def classify_maker_like(self) -> str:
        if self.order_type in {"LIMIT"} and self.tif in {"GTX", "GTC"}:
            return "maker_like"
        if self.order_type in {"MARKET", "STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            return "taker_like"
        if self.order_type == "LIMIT" and self.tif in {"IOC", "FOK"}:
            return "taker_like"
        return "unknown"


def load_shadow_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        row["__file"] = "shadow"
        rows.append(row)
    rows.sort(key=lambda r: (_safe_int(r.get("ts_ms")) or 0, _safe_int(r.get("sequence")) or 0))
    return rows


def load_order_log() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "order_log_v1.jsonl"):
        row["__file"] = "order_log"
        rows.append(row)
    rows.sort(key=lambda r: _safe_int(r.get("timestamp")) or 0)
    return rows


def load_trade_lifecycle() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "trade_lifecycle.jsonl"):
        row["__file"] = "trade_lifecycle"
        rows.append(row)
    rows.sort(
        key=lambda r: (
            _safe_int(r.get("ts_ms"))
            or _safe_int(r.get("snapshot_ts_ms"))
            or _safe_int(r.get("updated_ts_ms"))
            or 0
        )
    )
    return rows


def load_text_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return [line.rstrip("\n") for line in fh if line.strip()]


def build_price_series() -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)

    # Prefer OHLC where present.
    bars_300 = LOGS / "mean_reversion" / "bars_300s.jsonl"
    if bars_300.exists():
        for row in _iter_jsonl(bars_300):
            sym = str(row.get("symbol") or "")
            ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
            close = _safe_float(row.get("close"))
            high = _safe_float(row.get("high"))
            low = _safe_float(row.get("low"))
            if sym and ts is not None and close is not None:
                series[sym].append(
                    {
                        "ts_ms": ts,
                        "close": close,
                        "high": high if high is not None else close,
                        "low": low if low is not None else close,
                        "source": "bars_300s.jsonl",
                    }
                )

    # Add close-only ta_features as a fallback / coverage extender.
    for path in sorted((LOGS / "ta_features").glob("*.jsonl")):
        for row in _iter_jsonl(path):
            sym = str(row.get("symbol") or path.stem)
            ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
            close = _safe_float(row.get("close"))
            if sym and ts is not None and close is not None:
                series[sym].append(
                    {
                        "ts_ms": ts,
                        "close": close,
                        "high": close,
                        "low": close,
                        "source": "ta_features",
                    }
                )

    for sym in list(series.keys()):
        series[sym].sort(key=lambda r: r["ts_ms"])
    return series


def bar_lookup(series: list[dict[str, Any]], ts_ms: int) -> dict[str, Any] | None:
    if not series:
        return None
    lo, hi = 0, len(series) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if series[mid]["ts_ms"] <= ts_ms:
            lo = mid
        else:
            hi = mid - 1
    if series[lo]["ts_ms"] <= ts_ms:
        return series[lo]
    return None


def build_orders(order_log: list[dict[str, Any]], shadow: list[dict[str, Any]], trade_lifecycle: list[dict[str, Any]]) -> dict[str, OrderEntity]:
    orders: dict[str, OrderEntity] = {}

    def get_or_create(key: str) -> OrderEntity:
        if key not in orders:
            orders[key] = OrderEntity(key=key)
        return orders[key]

    def update_common(order: OrderEntity, row: dict[str, Any], ts_ms: int | None, source: str) -> None:
        order.update_ts(ts_ms)
        order.source_event = order.source_event or str(row.get("event_type") or row.get("event_name") or "")
        order.source_component = order.source_component or str(row.get("source_fsm") or row.get("source_component") or "")
        order.source_path = order.source_path or str(row.get("source_path") or "")
        order.symbol = order.symbol or str(row.get("symbol") or "")
        order.strategy_id = order.strategy_id or str(row.get("strategy_id") or "")
        order.rid = order.rid or str(row.get("rid") or "")
        order.lifecycle_id = order.lifecycle_id or str(row.get("lifecycle_id") or "")

    # Order log entry-facing placements / exits.
    for row in order_log:
        et = str(row.get("event_type") or "")
        if et not in {"ORDER_PLACED", "ORDER_FILLED", "ORDER_TIMEOUT", "ORDER_CANCELLED", "ORDER_REJECTED", "POSITION_CLOSED"}:
            continue
        ts_ms = _safe_int(row.get("timestamp"))
        rid = str(row.get("rid") or "")
        order_id = str(row.get("order_id") or row.get("client_order_id") or rid or "")
        key = order_id if order_id else rid
        if not key:
            continue
        order = get_or_create(key)
        update_common(order, row, ts_ms, "order_log")

        if et == "ORDER_PLACED":
            order.order_id = order.order_id or str(row.get("order_id") or "")
            order.client_order_id = order.client_order_id or str(row.get("client_order_id") or "")
            order.placed_qty = _safe_float(row.get("quantity") or row.get("qty_raw") or row.get("qty"))
            adapter = row.get("adapter_response") if isinstance(row.get("adapter_response"), dict) else {}
            order.order_type = order.order_type or str((adapter or {}).get("type") or row.get("metadata", {}).get("order_type") or "")
            order.tif = order.tif or str((adapter or {}).get("timeInForce") or row.get("metadata", {}).get("tif") or "")
            order.reduce_only = order.reduce_only if order.reduce_only is not None else bool((adapter or {}).get("reduceOnly", row.get("reduce_only", False)))
            order.regime = order.regime or str(row.get("regime") or "")
            order.regime_confidence = order.regime_confidence if order.regime_confidence is not None else _safe_float(row.get("regime_confidence"))
            rp = row.get("regime_provenance") if isinstance(row.get("regime_provenance"), dict) else {}
            det = rp.get("detector_event") if isinstance(rp, dict) else {}
            order.regime_epoch_ref = order.regime_epoch_ref or str((det or {}).get("structural_regime_ref") or "")
            if not order.role:
                coid = str(row.get("client_order_id") or "")
                order.role = "entry" if coid.startswith("ENTRY-") else "unknown"
            if not order.order_type:
                order.order_type = "LIMIT" if order.role == "entry" else ""
            if not order.tif:
                order.tif = str((adapter or {}).get("timeInForce") or "")

        elif et == "ORDER_FILLED":
            order.add_fill(_safe_float(row.get("quantity")), _safe_float(row.get("price")))
            if not order.final_status:
                order.final_status = "FILLED"
            order.linkage_trade_id = order.linkage_trade_id or str((row.get("metadata") or {}).get("fill_trade_id") or row.get("trade_id") or "")
        elif et == "ORDER_TIMEOUT":
            order.timeout_flag = True
            order.final_status = "CANCELED"
            order.reject_reason = str(row.get("why") or row.get("nrr_code") or "ORDER_TIMEOUT")
            order.placement_outcome = "timeout"
        elif et == "ORDER_CANCELLED":
            order.cancel_flag = True
            order.final_status = "CANCELED"
            order.reject_reason = order.reject_reason or str(row.get("reason") or row.get("timeout_type") or "ORDER_CANCELLED")
            order.placement_outcome = "cancelled"
        elif et == "ORDER_REJECTED":
            order.final_status = "REJECTED"
            order.reject_reason = str(row.get("why") or row.get("reason") or "")
            order.placement_outcome = "rejected"
        elif et == "POSITION_CLOSED":
            order.linkage_trade_id = order.linkage_trade_id or str(row.get("trade_id") or "")
            if row.get("close_reason"):
                order.notes.append(f"close_reason={row.get('close_reason')}")
            if not order.final_status:
                order.final_status = "FILLED"

    # Shadow journal gives bracket closes and explicit execution terminals.
    for row in shadow:
        en = str(row.get("event_name") or "")
        if en not in {"EVT:ORDER_PLACED", "EVT:TRADE_EXECUTED", "EVT:ORDER_STATE_CHANGED", "ORDER_INDEX:MARK_TERMINAL"}:
            continue
        ts_ms = _safe_int(row.get("ts_ms"))
        rid = str(row.get("rid") or "")
        order_id = str(row.get("order_id") or "")
        client_order_id = str(row.get("client_order_id") or "")
        key = order_id or client_order_id or rid
        if not key:
            continue
        order = get_or_create(key)
        update_common(order, row, ts_ms, "shadow")
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        order.order_id = order.order_id or order_id or str(pf.get("orderId") or pf.get("order_id") or "")
        order.client_order_id = order.client_order_id or client_order_id or str(pf.get("clientOrderId") or pf.get("client_order_id") or "")
        order.symbol = order.symbol or str(row.get("symbol") or pf.get("symbol") or "")
        order.strategy_id = order.strategy_id or str(row.get("strategy_id") or pf.get("strategy_id") or "")
        order.side = order.side or str(row.get("side") or pf.get("side") or "")
        if "bracket_role" in row and not order.bracket_role:
            order.bracket_role = str(row.get("bracket_role") or "")
        if "order_kind" in pf and not order.role:
            order.role = str(pf.get("order_kind") or "").lower()
        if en == "EVT:ORDER_PLACED":
            order.placement_outcome = "placed"
            adapter = pf if isinstance(pf, dict) else {}
            order.order_type = order.order_type or str(adapter.get("order_type") or adapter.get("type") or "")
            order.tif = order.tif or str(adapter.get("tif") or adapter.get("timeInForce") or "")
            order.reduce_only = order.reduce_only if order.reduce_only is not None else bool(adapter.get("reduceOnly", adapter.get("reduce_only", False)))
            order.placed_qty = order.placed_qty or _safe_float(adapter.get("qty") or adapter.get("quantity") or row.get("qty"))
        elif en in {"EVT:TRADE_EXECUTED", "EVT:ORDER_STATE_CHANGED"}:
            status = str((pf or {}).get("status") or "").upper()
            if status:
                if status in {"FILLED", "PARTIALLY_FILLED", "NEW", "CANCELED", "CANCELLED", "REJECTED"}:
                    if status in {"CANCELED", "CANCELLED"}:
                        order.cancel_flag = True
                        order.final_status = "CANCELED"
                    elif status == "REJECTED":
                        order.final_status = "REJECTED"
                    else:
                        order.final_status = status
            qty = _safe_float((pf or {}).get("qty") or row.get("qty"))
            px = _safe_float((pf or {}).get("price") or row.get("price"))
            if qty is not None and px is not None:
                order.add_fill(qty, px)
            if order.order_type == "":
                order.order_type = str((pf or {}).get("order_type") or (pf or {}).get("orderType") or "")
            if (pf or {}).get("bracket_role") and not order.bracket_role:
                order.bracket_role = str((pf or {}).get("bracket_role") or "")
            if (pf or {}).get("terminal_non_fill") is True:
                order.final_status = order.final_status or "CANCELED"
        elif en in {"ORDER_INDEX:MARK_TERMINAL"}:
            status = "FILLED" if str(r.get("local_state_after") if (r := row) else "").find("terminal") >= 0 else ""
            if status and not order.final_status:
                order.final_status = status

    # Trade lifecycle gives the bracket-child placements and terminal exchange ids.
    for row in trade_lifecycle:
        et = str(row.get("event_type") or "")
        ts_ms = _safe_int(row.get("ts_ms") or row.get("snapshot_ts_ms") or row.get("updated_ts_ms"))
        rid = str(row.get("rid") or "")
        if et == "TRADE_LIFECYCLE_ORDERED":
            key = str(row.get("order_id") or rid)
            if not key:
                continue
            order = get_or_create(key)
            update_common(order, row, ts_ms, "trade_lifecycle")
            order.order_id = order.order_id or str(row.get("order_id") or "")
            order.client_order_id = order.client_order_id or str(row.get("rid") or "")
            order.symbol = order.symbol or str(row.get("symbol") or "")
            order.strategy_id = order.strategy_id or str(row.get("strategy_id") or "")
            order.side = order.side or str(row.get("side") or "")
            order.role = order.role or "entry"
            order.order_type = order.order_type or str(row.get("entry_type") or "")
            order.placement_outcome = order.placement_outcome or "ordered"
            order.final_status = order.final_status or str(row.get("status") or "ORDERED")
            order.regime = order.regime or str(row.get("regime") or "")
            order.regime_confidence = order.regime_confidence if order.regime_confidence is not None else _safe_float(row.get("regime_confidence"))
            rp = row.get("regime_provenance") if isinstance(row.get("regime_provenance"), dict) else {}
            det = rp.get("detector_event") if isinstance(rp, dict) else {}
            order.regime_epoch_ref = order.regime_epoch_ref or str((det or {}).get("structural_regime_ref") or "")
            order.placed_qty = order.placed_qty if order.placed_qty is not None else _safe_float(row.get("quantity") or row.get("qty"))
            order.notes.append(f"trade_lifecycle_status={row.get('status')}")
        elif et in {"EXECUTION_BRACKET_DEFERRED_STORED", "EXECUTION_BRACKET_DEFERRED_PLACED"}:
            for child_role, child_key, child_type in (
                ("SL", row.get("sl_order_id"), "STOP_MARKET"),
                ("TP", row.get("tp_order_id"), "TAKE_PROFIT_MARKET"),
            ):
                if not child_key:
                    continue
                key = str(child_key)
                order = get_or_create(key)
                update_common(order, row, ts_ms, "trade_lifecycle")
                order.order_id = order.order_id or str(child_key)
                order.exchange_order_id = order.exchange_order_id or str(row.get("exchange_order_id") or "")
                order.client_order_id = order.client_order_id or str(row.get("entry_client_order_id") or "")
                order.symbol = order.symbol or str(row.get("symbol") or "")
                order.strategy_id = order.strategy_id or str(row.get("strategy_id") or "")
                order.side = order.side or str(row.get("side") or "")
                order.bracket_role = order.bracket_role or child_role
                order.role = order.role or child_role.lower()
                order.order_type = order.order_type or child_type
                order.placement_outcome = order.placement_outcome or ("placed" if et == "EXECUTION_BRACKET_DEFERRED_PLACED" else "stored")
                order.final_status = order.final_status or ("OPEN" if bool(row.get("lifecycle_active")) else "PENDING")
                entry_oid = str(row.get("entry_order_id") or "")
                if entry_oid:
                    order.linkage_trade_id = order.linkage_trade_id or entry_oid
                if row.get("entry_client_order_id"):
                    order.notes.append(f"entry_client_order_id={row.get('entry_client_order_id')}")
                if row.get("recovery_only") is not None:
                    order.notes.append(f"recovery_only={bool(row.get('recovery_only'))}")
                if row.get("placement_path"):
                    order.notes.append(f"placement_path={row.get('placement_path')}")
                if row.get("assigned_strategies"):
                    order.notes.append(f"assigned_strategies={','.join(row.get('assigned_strategies') or [])}")
        elif et == "EXECUTION_WS_TERMINAL_CORRELATED":
            key = str(row.get("tracked_bracket_order_id") or row.get("exchange_order_id") or rid)
            if not key:
                continue
            order = get_or_create(key)
            update_common(order, row, ts_ms, "trade_lifecycle")
            order.exchange_order_id = order.exchange_order_id or str(row.get("exchange_order_id") or "")
            order.bracket_role = order.bracket_role or str(row.get("bracket_role") or "")
            order.role = order.role or (str(row.get("bracket_role") or "").lower())
            order.order_type = order.order_type or str(row.get("order_type") or "")
            order.final_status = str(row.get("status") or order.final_status or "")
            order.placement_outcome = order.placement_outcome or "terminal_correlated"
            order.notes.append(f"terminal_correlation_source={row.get('terminal_correlation_source')}")
        elif et == "EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS":
            key = str(row.get("tracked_bracket_order_id") or row.get("exchange_order_id") or rid)
            if not key:
                continue
            order = get_or_create(key)
            update_common(order, row, ts_ms, "trade_lifecycle")
            order.exchange_order_id = order.exchange_order_id or str(row.get("exchange_order_id") or "")
            order.order_type = order.order_type or str(row.get("order_type") or "")
            order.final_status = order.final_status or str(row.get("status") or "")
            order.notes.append("ws_bracket_child_orderindex_miss")

    # Normalize status and maker/taker.
    for order in orders.values():
        if not order.role:
            if order.bracket_role in {"SL", "TP"}:
                order.role = order.bracket_role.lower()
            elif order.client_order_id.startswith("ENTRY-"):
                order.role = "entry"
            else:
                order.role = "unknown"
        if not order.final_status:
            if order.filled_qty > 0:
                order.final_status = "FILLED"
            elif order.timeout_flag or order.cancel_flag:
                order.final_status = "CANCELED"
            else:
                order.final_status = "OPEN"
        order.maker_like = order.classify_maker_like()
    return orders


def build_regime_events(shadow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in shadow:
        if row.get("event_name") != "EVT:REGIME_DETECTED":
            continue
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        det_ts = _safe_int((pf or {}).get("ts_ms") or row.get("ts_ms"))
        rows.append(
            {
                "ts_ms": det_ts,
                "symbol": str(row.get("symbol") or pf.get("symbol") or ""),
                "regime": str(pf.get("regime") or ""),
                "raw_regime": str(pf.get("raw_regime") or pf.get("regime") or ""),
                "confidence": _safe_float(pf.get("confidence")),
                "stable_confidence": _safe_float(pf.get("stable_confidence")),
                "basis_tf_sec": _safe_int(pf.get("basis_tf_sec")),
                "uncertain_cutoff": _safe_float(pf.get("uncertain_cutoff")),
                "hysteresis_bars": _safe_int(pf.get("hysteresis_bars")),
                "hysteresis_confirm_count": _safe_int(pf.get("hysteresis_confirm_count")),
                "changed": bool(pf.get("changed")),
                "carried_previous_stable": bool(pf.get("carried_previous_stable")),
                "emitted_confidence_kind": str(pf.get("emitted_confidence_kind") or ""),
                "reason_summary": str(pf.get("reason_summary") or ""),
                "warmup_full_ready": bool((pf.get("warmup") or {}).get("full_ready")) if isinstance(pf.get("warmup"), dict) else None,
                "warmup_reasons": json.dumps((pf.get("warmup") or {}).get("reasons") or [], ensure_ascii=False) if isinstance(pf.get("warmup"), dict) else "[]",
                "structural_regime_ref": str(pf.get("structural_regime_ref") or ""),
                "bar_close_ts_ms": _safe_int(pf.get("bar_close_ts_ms")),
                "source_model": str(pf.get("source_model") or pf.get("pre_cutoff_source_model") or ""),
                "pre_cutoff_regime": str(pf.get("pre_cutoff_regime") or ""),
                "pre_cutoff_confidence": _safe_float(pf.get("pre_cutoff_confidence")),
                "demoted_to_uncertain": bool(pf.get("demoted_to_uncertain")),
                "payload": pf,
            }
        )
    rows.sort(key=lambda r: (r["symbol"], r["ts_ms"] or 0))
    return rows


def build_intents(shadow: list[dict[str, Any]], orders: dict[str, OrderEntity], trade_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    intents_by_rid: dict[str, dict[str, Any]] = {}
    for row in shadow:
        en = row.get("event_name")
        if en not in {"EVT:STRATEGY_SIGNAL_PRODUCED", "EVT:TRADE_INTENT_PROPOSED", "EVT:TRADE_INTENT_REJECTED"}:
            continue
        rid = str(row.get("rid") or "")
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        ts_ms = _safe_int((pf or {}).get("ts_ms") or row.get("ts_ms"))
        rec = intents_by_rid.setdefault(
            rid,
            {
                "rid": rid,
                "symbol": str(row.get("symbol") or pf.get("symbol") or ""),
                "strategy_id": str(row.get("strategy_id") or pf.get("strategy_id") or ""),
                "side": str((row.get("side") or pf.get("side") or "")).upper(),
                "signal_ts_ms": None,
                "intent_ts_ms": None,
                "event_name": "",
                "regime": "",
                "regime_confidence": None,
                "regime_epoch_ref": "",
                "signal_score": None,
                "signal_payload": {},
                "why_chain": [],
                "intent_outcome": "",
                "reject_reason_code": "",
                "reject_reason": "",
                "blocked_by": "",
                "order_placed": False,
                "filled": False,
                "final_outcome": "",
                "entry_order_id": "",
                "entry_client_order_id": "",
                "linked_trade_rid": "",
                "notes": [],
            },
        )
        if en == "EVT:STRATEGY_SIGNAL_PRODUCED":
            rec["signal_ts_ms"] = ts_ms
            rec["event_name"] = en
            rec["regime"] = str(pf.get("regime") or rec["regime"])
            rec["regime_confidence"] = _safe_float(pf.get("regime_confidence"))
            rec["regime_epoch_ref"] = str(pf.get("regime_epoch_ref") or rec["regime_epoch_ref"])
            rec["signal_score"] = _safe_float(pf.get("signal_score"))
            rec["signal_payload"] = pf
        elif en == "EVT:TRADE_INTENT_PROPOSED":
            rec["intent_ts_ms"] = ts_ms
            rec["event_name"] = en
            rec["regime"] = str(pf.get("regime") or rec["regime"])
            rec["regime_confidence"] = _safe_float(pf.get("regime_confidence")) if rec["regime_confidence"] is None else rec["regime_confidence"]
            rec["regime_epoch_ref"] = str(pf.get("regime_epoch_ref") or rec["regime_epoch_ref"])
            rec["intent_outcome"] = "ALLOW"
            rec["why_chain"] = list(pf.get("why_chain") or rec["why_chain"])
        elif en == "EVT:TRADE_INTENT_REJECTED":
            rec["intent_ts_ms"] = ts_ms
            rec["event_name"] = en
            rec["intent_outcome"] = "REJECT"
            rec["reject_reason_code"] = str(pf.get("reason_code") or "")
            rec["reject_reason"] = str(pf.get("why") or pf.get("context") or "")
            rec["blocked_by"] = str(pf.get("context") or pf.get("why") or "")
            rec["why_chain"] = list(pf.get("why_chain") or rec["why_chain"])

    # Enrich with order placement/fill linkage.
    by_rid = {rid: rec for rid, rec in intents_by_rid.items()}
    for rid, rec in by_rid.items():
        if rid in orders:
            o = orders[rid]
            rec["order_placed"] = o.final_status in {"FILLED", "PARTIALLY_FILLED", "OPEN", "CANCELED"} and bool(o.order_id or o.client_order_id)
            rec["filled"] = o.filled_qty > 0
            rec["entry_order_id"] = o.order_id
            rec["entry_client_order_id"] = o.client_order_id
            rec["linked_trade_rid"] = o.lifecycle_id or o.rid
            if o.final_status in {"FILLED", "PARTIALLY_FILLED"}:
                rec["final_outcome"] = "FILLED"
            elif o.timeout_flag:
                rec["final_outcome"] = "TIMEOUT"
            elif o.cancel_flag:
                rec["final_outcome"] = "CANCELLED"
            elif o.final_status == "REJECTED":
                rec["final_outcome"] = "REJECTED"
            else:
                rec["final_outcome"] = o.final_status
        elif rec["intent_outcome"] == "REJECT":
            rec["final_outcome"] = "REJECTED"

    # Match to trade closes by rid prefix.
    close_by_parent = {r["parent_rid"]: r for r in trade_rows if r.get("parent_rid")}
    for rec in intents_by_rid.values():
        if rec["rid"] in close_by_parent:
            rec["final_outcome"] = rec["final_outcome"] or "CLOSED"
            rec["linked_trade_rid"] = close_by_parent[rec["rid"]]["close_rid"]
        elif rec["filled"] and rec["final_outcome"] == "":
            rec["final_outcome"] = "OPEN"

    rows = list(intents_by_rid.values())
    rows.sort(key=lambda r: (r["signal_ts_ms"] or r["intent_ts_ms"] or 0, r["symbol"], r["rid"]))
    return rows


def infer_parent_entry_rid(close_rid: str, symbol: str, symbol_open_queue: deque[str]) -> str:
    if ":" in close_rid:
        return close_rid.split(":", 1)[0]
    if symbol_open_queue:
        return symbol_open_queue[0]
    return ""


def build_trades(order_log: list[dict[str, Any]], orders: dict[str, OrderEntity], regime_events: list[dict[str, Any]], price_series: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    # Track open entry orders by symbol in time order so terminal closes can be paired.
    entry_by_symbol: dict[str, deque[str]] = defaultdict(deque)
    entry_rows = []
    for order in orders.values():
        if order.role == "entry" and order.symbol and order.open_ts_ms is not None:
            entry_rows.append(order)
    entry_rows.sort(key=lambda o: o.open_ts_ms or 0)
    for order in entry_rows:
        entry_by_symbol[order.symbol].append(order.key)

    # Build close events from order log.
    closes = []
    for row in order_log:
        if row.get("event_type") != "POSITION_CLOSED":
            continue
        closes.append(row)
    closes.sort(key=lambda r: _safe_int(r.get("timestamp")) or 0)

    # Regime timeline lookup per symbol.
    regimes_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in regime_events:
        regimes_by_symbol[ev["symbol"]].append(ev)
    for sym in regimes_by_symbol:
        regimes_by_symbol[sym].sort(key=lambda r: r["ts_ms"] or 0)

    def regime_at(symbol: str, ts_ms: int | None) -> dict[str, Any]:
        if ts_ms is None:
            return {}
        series = regimes_by_symbol.get(symbol) or []
        if not series:
            return {}
        lo, hi = 0, len(series) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if (series[mid]["ts_ms"] or 0) <= ts_ms:
                lo = mid
            else:
                hi = mid - 1
        return series[lo] if (series[lo]["ts_ms"] or 0) <= ts_ms else {}

    trade_rows: list[dict[str, Any]] = []
    used_entries: set[str] = set()
    for close in closes:
        close_ts = _safe_int(close.get("timestamp"))
        symbol = str(close.get("symbol") or "")
        close_rid = str(close.get("rid") or "")
        close_reason = str(close.get("close_reason") or close.get("why") or "")
        pnl_net = _safe_float(close.get("realized_pnl_net"))
        fees = _safe_float(close.get("fees"))
        trade_id = str(close.get("trade_id") or "")
        side = _normalize_side(close.get("side"))
        parent_rid = infer_parent_entry_rid(close_rid, symbol, entry_by_symbol.get(symbol, deque()))
        if parent_rid and parent_rid in used_entries and ":" not in close_rid:
            # Do not re-use an entry for a later pre-window close if we have already paired it.
            parent_rid = ""
        if not parent_rid:
            parent_rid = infer_parent_entry_rid(close_rid, symbol, deque())
        entry_order = orders.get(parent_rid)
        if entry_order is None and symbol:
            # Fallback: nearest unmatched entry by symbol.
            queue = entry_by_symbol.get(symbol, deque())
            while queue and queue[0] in used_entries:
                queue.popleft()
            if queue:
                parent_rid = queue[0]
                entry_order = orders.get(parent_rid)
        if entry_order:
            used_entries.add(entry_order.key)
            if entry_by_symbol.get(symbol):
                try:
                    entry_by_symbol[symbol].remove(entry_order.key)
                except ValueError:
                    pass

        entry_ts = entry_order.open_ts_ms if entry_order else None
        entry_price = entry_order.avg_fill_price or entry_order.placed_qty and None
        if entry_order and entry_order.avg_fill_price is None and entry_order.placed_qty is not None and entry_order.fill_pairs:
            entry_price = _weighted_avg(entry_order.fill_pairs)
        if entry_order and entry_price is None:
            # Best-effort fallback to ordered price from order log if no fill-price is available.
            entry_price = None
        exit_price = _safe_float((close.get("metadata") or {}).get("close_price"))
        if exit_price is None:
            exit_price = _safe_float((close.get("metadata") or {}).get("realized_pnl"))

        entry_regime = regime_at(symbol, entry_ts or close_ts)
        exit_regime = regime_at(symbol, close_ts)
        regime_changed = bool(entry_regime and exit_regime and entry_regime.get("regime") != exit_regime.get("regime"))

        # Excursion proxy from available bars.
        bars = price_series.get(symbol) or []
        segment = [b for b in bars if (entry_ts or 0) <= b["ts_ms"] <= (close_ts or 0)]
        if not segment and entry_ts is not None and close_ts is not None:
            segment = [b for b in bars if entry_ts - 300000 <= b["ts_ms"] <= close_ts + 300000]
        mfe = None
        mae = None
        excursion_source = "unavailable"
        if segment and entry_price:
            if any(b["source"] == "bars_300s.jsonl" for b in segment):
                excursion_source = "ohlc_close_proxy"
            else:
                excursion_source = "ta_close_proxy"
            if side == "SHORT":
                mfe = max(((entry_price - float(b["low"])) / entry_price) * 100.0 for b in segment)
                mae = max(((float(b["high"]) - entry_price) / entry_price) * 100.0 for b in segment)
            else:
                mfe = max(((float(b["high"]) - entry_price) / entry_price) * 100.0 for b in segment)
                mae = max(((entry_price - float(b["low"])) / entry_price) * 100.0 for b in segment)

        duration_ms = (close_ts - entry_ts) if entry_ts and close_ts else None
        notional = (entry_price * (entry_order.filled_qty if entry_order and entry_order.filled_qty else (entry_order.placed_qty or 0))) if entry_price and entry_order else None
        pnl_pct = None
        if pnl_net is not None and notional:
            pnl_pct = (pnl_net / notional) * 100.0

        trade_rows.append(
            {
                "close_rid": close_rid,
                "parent_rid": parent_rid,
                "symbol": symbol,
                "strategy_id": entry_order.strategy_id if entry_order else "",
                "direction": side,
                "entry_ts_ms": entry_ts,
                "exit_ts_ms": close_ts,
                "hold_ms": duration_ms,
                "hold_bars_5m": (duration_ms / 300000.0) if duration_ms is not None else None,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "filled_qty": entry_order.filled_qty if entry_order else None,
                "placed_qty": entry_order.placed_qty if entry_order else None,
                "realized_pnl_abs": pnl_net,
                "realized_pnl_pct": pnl_pct,
                "fees": fees,
                "mfe_pct": mfe,
                "mae_pct": mae,
                "excursion_source": excursion_source,
                "exit_reason": close_reason,
                "close_path_source": "order_log:POSITION_CLOSED",
                "regime_at_entry": entry_regime.get("regime") if entry_regime else "",
                "regime_confidence_at_entry": entry_regime.get("confidence") if entry_regime else None,
                "regime_at_exit": exit_regime.get("regime") if exit_regime else "",
                "regime_confidence_at_exit": exit_regime.get("confidence") if exit_regime else None,
                "regime_changed_during_trade": regime_changed,
                "entry_order_id": entry_order.order_id if entry_order else "",
                "entry_client_order_id": entry_order.client_order_id if entry_order else "",
                "entry_role": entry_order.role if entry_order else "",
                "entry_order_type": entry_order.order_type if entry_order else "",
                "entry_tif": entry_order.tif if entry_order else "",
                "entry_maker_like": entry_order.maker_like if entry_order else "",
                "anomaly_flags": [],
                "trade_id": trade_id,
            }
        )

    trade_rows.sort(key=lambda r: (r["exit_ts_ms"] or 0, r["symbol"], r["close_rid"]))
    return trade_rows


def build_regime_segments(regime_events: list[dict[str, Any]], trade_rows: list[dict[str, Any]], intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in regime_events:
        by_symbol[ev["symbol"]].append(ev)
    for sym in by_symbol:
        by_symbol[sym].sort(key=lambda r: r["ts_ms"] or 0)

    intents_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in intents:
        intents_by_symbol[it["symbol"]].append(it)
    for sym in intents_by_symbol:
        intents_by_symbol[sym].sort(key=lambda r: (r["signal_ts_ms"] or r["intent_ts_ms"] or 0))

    segments: list[dict[str, Any]] = []
    for sym, rows in by_symbol.items():
        if not rows:
            continue
        seg_start = rows[0]["ts_ms"] or 0
        seg_label = rows[0]["regime"]
        seg_conf = rows[0]["confidence"]
        seg_raw = rows[0]["raw_regime"]
        seg_row0 = rows[0]
        for prev, cur in zip(rows, rows[1:]):
            if cur["regime"] != seg_label and cur["changed"]:
                segments.append(
                    {
                        "symbol": sym,
                        "regime_start_ts_ms": seg_start,
                        "regime_end_ts_ms": prev["ts_ms"],
                        "regime_label": seg_label,
                        "raw_regime": seg_raw,
                        "stable_vs_raw": "stable" if seg_label == seg_raw else "stable_transition",
                        "confidence": seg_conf,
                        "basis_tf_sec": seg_row0.get("basis_tf_sec"),
                        "changed": True,
                        "duration_ms": (prev["ts_ms"] - seg_start) if prev["ts_ms"] and seg_start else None,
                        "segment_payload": seg_row0,
                    }
                )
                seg_start = cur["ts_ms"] or seg_start
                seg_label = cur["regime"]
                seg_raw = cur["raw_regime"]
                seg_conf = cur["confidence"]
                seg_row0 = cur
        last = rows[-1]
        segments.append(
            {
                "symbol": sym,
                "regime_start_ts_ms": seg_start,
                "regime_end_ts_ms": last["ts_ms"],
                "regime_label": seg_label,
                "raw_regime": seg_raw,
                "stable_vs_raw": "stable" if seg_label == seg_raw else "stable_transition",
                "confidence": seg_conf,
                "basis_tf_sec": seg_row0.get("basis_tf_sec"),
                "changed": False,
                "duration_ms": (last["ts_ms"] - seg_start) if last["ts_ms"] and seg_start else None,
                "segment_payload": seg_row0,
            }
        )

    # Populate trade stats per segment.
    for seg in segments:
        start = seg["regime_start_ts_ms"] or 0
        end = seg["regime_end_ts_ms"] or start
        sym = seg["symbol"]
        seg_trades = [t for t in trade_rows if t["symbol"] == sym and t["entry_ts_ms"] is not None and start <= t["entry_ts_ms"] <= end]
        seg_intents = [i for i in intents_by_symbol.get(sym, []) if i.get("intent_ts_ms") is not None and start <= i["intent_ts_ms"] <= end]
        gross = sum((t["realized_pnl_abs"] or 0.0) for t in seg_trades if t["realized_pnl_abs"] is not None)
        wins = [t for t in seg_trades if (t["realized_pnl_abs"] or 0.0) > 0]
        losses = [t for t in seg_trades if (t["realized_pnl_abs"] or 0.0) < 0]
        win_rate = len(wins) / len(seg_trades) if seg_trades else None
        avg_hold = statistics.mean([t["hold_ms"] for t in seg_trades if t["hold_ms"] is not None]) if seg_trades else None
        mfe_vals = [t["mfe_pct"] for t in seg_trades if t["mfe_pct"] is not None]
        mae_vals = [t["mae_pct"] for t in seg_trades if t["mae_pct"] is not None]
        first_loss = min((t["exit_ts_ms"] for t in losses if t["exit_ts_ms"] is not None), default=None)
        continued_after_loss = False
        if first_loss is not None:
            continued_after_loss = any(i["intent_ts_ms"] and i["intent_ts_ms"] > first_loss and i.get("final_outcome") == "FILLED" for i in seg_intents)
        seg.update(
            {
                "trades_opened": len(seg_trades),
                "fills": len([i for i in seg_intents if i.get("filled")]),
                "gross_pnl": gross,
                "net_pnl": gross,
                "win_rate": win_rate,
                "avg_hold_ms": avg_hold,
                "avg_mfe_pct": statistics.mean(mfe_vals) if mfe_vals else None,
                "avg_mae_pct": statistics.mean(mae_vals) if mae_vals else None,
                "rejected_intents": len([i for i in seg_intents if i.get("intent_outcome") == "REJECT"]),
                "blocked_signals": len([i for i in seg_intents if i.get("intent_outcome") == "REJECT"]),
                "first_loss_ts_ms": first_loss,
                "continued_after_first_loss": continued_after_loss,
                "next_regime_ts_ms": None,
            }
        )

    segments.sort(key=lambda r: (r["symbol"], r["regime_start_ts_ms"] or 0))
    for sym in {s["symbol"] for s in segments}:
        sym_segs = [s for s in segments if s["symbol"] == sym]
        for prev, cur in zip(sym_segs, sym_segs[1:]):
            prev["next_regime_ts_ms"] = cur["regime_start_ts_ms"]
    return segments


def build_embargo_validation(order_log: list[dict[str, Any]], regime_events: list[dict[str, Any]], trade_rows: list[dict[str, Any]], intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regimes_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in regime_events:
        regimes_by_symbol[ev["symbol"]].append(ev)
    for sym in regimes_by_symbol:
        regimes_by_symbol[sym].sort(key=lambda r: r["ts_ms"] or 0)

    def regime_epoch_at(symbol: str, ts_ms: int | None) -> str:
        series = regimes_by_symbol.get(symbol) or []
        if not series or ts_ms is None:
            return ""
        best = None
        for ev in series:
            if (ev["ts_ms"] or 0) <= ts_ms:
                best = ev
            else:
                break
        if not best:
            return ""
        return str(best.get("structural_regime_ref") or "")

    close_events = [r for r in order_log if r.get("event_type") == "POSITION_CLOSED"]
    close_events.sort(key=lambda r: _safe_int(r.get("timestamp")) or 0)
    by_symbol = defaultdict(list)
    for c in close_events:
        by_symbol[str(c.get("symbol") or "")].append(c)

    intent_events = [i for i in intents if i.get("intent_ts_ms") is not None]
    intent_by_symbol = defaultdict(list)
    for i in intent_events:
        intent_by_symbol[i["symbol"]].append(i)
    for sym in intent_by_symbol:
        intent_by_symbol[sym].sort(key=lambda r: r["intent_ts_ms"] or r["signal_ts_ms"] or 0)

    rows: list[dict[str, Any]] = []
    for sym, closes in by_symbol.items():
        first_loss_by_epoch: dict[str, dict[str, Any]] = {}
        for close in closes:
            ts = _safe_int(close.get("timestamp"))
            pnl = _safe_float(close.get("realized_pnl_net"))
            if pnl is None and isinstance(close.get("metadata"), dict):
                pnl = _safe_float(close["metadata"].get("realized_pnl"))
            epoch = regime_epoch_at(sym, ts)
            if pnl is None or pnl >= 0:
                continue
            if epoch and epoch not in first_loss_by_epoch:
                first_loss_by_epoch[epoch] = {"close_ts_ms": ts, "close_reason": close.get("close_reason"), "pnl": pnl}

        for epoch, loss in first_loss_by_epoch.items():
            intents_in_epoch = [i for i in intent_by_symbol.get(sym, []) if regime_epoch_at(sym, i["intent_ts_ms"]) == epoch]
            after_loss = [i for i in intents_in_epoch if i["intent_ts_ms"] and i["intent_ts_ms"] > (loss["close_ts_ms"] or 0)]
            rows.append(
                {
                    "symbol": sym,
                    "epoch_ref": epoch,
                    "first_loss_ts_ms": loss["close_ts_ms"],
                    "first_loss_close_reason": loss["close_reason"],
                    "first_loss_pnl": loss["pnl"],
                    "intents_after_loss_same_epoch": len(after_loss),
                    "filled_after_loss_same_epoch": len([i for i in after_loss if i.get("final_outcome") == "FILLED"]),
                    "rejected_after_loss_same_epoch": len([i for i in after_loss if i.get("final_outcome") == "REJECTED"]),
                    "stopped_after_first_loss": len([i for i in after_loss if i.get("final_outcome") == "FILLED"]) == 0,
                    "next_epoch_ts_ms": None,
                }
            )

    rows.sort(key=lambda r: (r["symbol"], r["first_loss_ts_ms"] or 0))
    return rows


def detect_anomalies(orders: dict[str, OrderEntity], trade_rows: list[dict[str, Any]], intents: list[dict[str, Any]], regime_events: list[dict[str, Any]], embargo_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # Duplicate same-direction entries by symbol before prior close.
    last_entry_by_symbol: dict[str, dict[str, Any]] = {}
    for t in trade_rows:
        sym = t["symbol"]
        if not sym:
            continue
        prev = last_entry_by_symbol.get(sym)
        if prev and t["entry_ts_ms"] and prev.get("entry_ts_ms") and t["entry_ts_ms"] < (prev.get("exit_ts_ms") or 10**18):
            rows.append(
                {
                    "anomaly_type": "duplicate_same_symbol_overlap",
                    "severity": "medium",
                    "symbol": sym,
                    "ts_ms": t["entry_ts_ms"],
                    "rid": t["parent_rid"],
                    "details": json.dumps({"prior_rid": prev.get("parent_rid"), "prior_exit_ts_ms": prev.get("exit_ts_ms")}, ensure_ascii=False),
                }
            )
        last_entry_by_symbol[sym] = t

    # Close without lineage.
    for t in trade_rows:
        if not t["parent_rid"] or not t["entry_ts_ms"]:
            rows.append(
                {
                    "anomaly_type": "close_without_clear_open_lineage",
                    "severity": "medium",
                    "symbol": t["symbol"],
                    "ts_ms": t["exit_ts_ms"],
                    "rid": t["close_rid"],
                    "details": json.dumps({"close_reason": t["exit_reason"], "parent_rid": t["parent_rid"]}, ensure_ascii=False),
                }
            )

    # Loss-latched but later allowed entries in same epoch.
    for row in embargo_rows:
        if not row["stopped_after_first_loss"]:
            rows.append(
                {
                    "anomaly_type": "embargo_bypass_suspected",
                    "severity": "high",
                    "symbol": row["symbol"],
                    "ts_ms": row["first_loss_ts_ms"],
                    "rid": row["epoch_ref"],
                    "details": json.dumps(row, ensure_ascii=False),
                }
            )

    # Silent drops: signals with neither intent nor reject record.
    by_rid = {i["rid"]: i for i in intents}
    for row in [r for r in regime_events if r.get("signal_payload")]:
        pass

    rows.sort(key=lambda r: (r["symbol"], r["ts_ms"] or 0, r["anomaly_type"]))
    return rows


def summary_metrics(orders: dict[str, OrderEntity], trade_rows: list[dict[str, Any]], intents: list[dict[str, Any]], regime_events: list[dict[str, Any]], embargo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    placed_orders = [o for o in orders.values() if o.role == "entry" and o.order_id]
    bracket_orders = [o for o in orders.values() if o.role in {"sl", "tp"} or o.bracket_role in {"SL", "TP"}]
    fills = [o for o in orders.values() if o.filled_qty > 0]
    rejected_intents = [i for i in intents if i.get("intent_outcome") == "REJECT"]
    filled_intents = [i for i in intents if i.get("final_outcome") == "FILLED"]
    timeouts = [o for o in orders.values() if o.timeout_flag]
    cancels = [o for o in orders.values() if o.cancel_flag]

    pnl_values = [t["realized_pnl_abs"] for t in trade_rows if t["realized_pnl_abs"] is not None]
    wins = [p for p in pnl_values if p > 0]
    losses = [p for p in pnl_values if p < 0]
    gross_profit = sum(p for p in pnl_values if p > 0)
    gross_loss = abs(sum(p for p in pnl_values if p < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss else None
    expectancy = statistics.mean(pnl_values) if pnl_values else None

    by_symbol = defaultdict(list)
    for t in trade_rows:
        by_symbol[t["symbol"]].append(t)
    symbol_pnl = {sym: sum((t["realized_pnl_abs"] or 0.0) for t in trs) for sym, trs in by_symbol.items()}

    by_strategy = defaultdict(list)
    for t in trade_rows:
        by_strategy[t["strategy_id"]].append(t)
    strategy_pnl = {sid: sum((t["realized_pnl_abs"] or 0.0) for t in trs) for sid, trs in by_strategy.items()}

    by_regime = defaultdict(list)
    for t in trade_rows:
        by_regime[t["regime_at_entry"]].append(t)
    regime_pnl = {reg: sum((t["realized_pnl_abs"] or 0.0) for t in trs) for reg, trs in by_regime.items()}

    return {
        "files": {
            "order_log": str((LOGS / "order_log_v1.jsonl").resolve()),
            "trade_lifecycle": str((LOGS / "trade_lifecycle.jsonl").resolve()),
            "shadow_journal": str((LOGS / "shadow_critical_event_journal_v1.jsonl").resolve()),
            "domain_decision_making": str((LOGS / "domain_decision_making.log").resolve()),
            "aurora_trades": str((LOGS / "aurora_trades.log").resolve()),
        },
        "orders": {
            "entry_orders": len(placed_orders),
            "bracket_orders": len(bracket_orders),
            "fills": len(fills),
            "timeouts": len(timeouts),
            "cancels": len(cancels),
            "rejected_intents": len(rejected_intents),
            "fill_rate": (len(fills) / len(placed_orders)) if placed_orders else None,
            "reject_rate": (len(rejected_intents) / max(1, len(intents))) if intents else None,
        },
        "trades": {
            "realized_trades": len(trade_rows),
            "gross_pnl": sum(pnl_values) if pnl_values else None,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "win_rate": (len(wins) / len(pnl_values)) if pnl_values else None,
            "median_pnl": statistics.median(pnl_values) if pnl_values else None,
            "best_symbol": max(symbol_pnl.items(), key=lambda kv: kv[1])[0] if symbol_pnl else "",
            "worst_symbol": min(symbol_pnl.items(), key=lambda kv: kv[1])[0] if symbol_pnl else "",
            "best_strategy": max(strategy_pnl.items(), key=lambda kv: kv[1])[0] if strategy_pnl else "",
            "worst_strategy": min(strategy_pnl.items(), key=lambda kv: kv[1])[0] if strategy_pnl else "",
            "best_regime": max(regime_pnl.items(), key=lambda kv: kv[1])[0] if regime_pnl else "",
            "worst_regime": min(regime_pnl.items(), key=lambda kv: kv[1])[0] if regime_pnl else "",
        },
        "regime": {
            "events": len(regime_events),
            "loss_embargo_cases": len(embargo_rows),
            "embargo_stopped_after_first_loss": sum(1 for r in embargo_rows if r["stopped_after_first_loss"]),
        },
        "coverage": {
            "shadow_event_count": len(list(_iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"))),
            "order_log_count": len(list(_iter_jsonl(LOGS / "order_log_v1.jsonl"))),
            "trade_lifecycle_count": len(list(_iter_jsonl(LOGS / "trade_lifecycle.jsonl"))),
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def write_report_markdown(path: Path, summary: dict[str, Any], orders: dict[str, OrderEntity], trades: list[dict[str, Any]], intents: list[dict[str, Any]], segments: list[dict[str, Any]], embargo_rows: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Aurora Runtime Forensic Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(f"- Entry orders placed: {summary['orders']['entry_orders']}")
    lines.append(f"- Bracket orders inferred: {summary['orders']['bracket_orders']}")
    lines.append(f"- Realized trades closed: {summary['trades']['realized_trades']}")
    lines.append(f"- Regime-loss embargo cases: {summary['regime']['loss_embargo_cases']}")
    lines.append(f"- Embargo cases that stopped after first loss: {summary['regime']['embargo_stopped_after_first_loss']}")
    lines.append("")
    lines.append("## Facts / Inferences / Unknowns")
    lines.append("- Facts are taken from order_log_v1.jsonl, trade_lifecycle.jsonl, shadow_critical_event_journal_v1.jsonl, aurora_trades.log, and domain_decision_making.log.")
    lines.append("- Inferences are marked in CSV columns with `anomaly_flags` / `excursion_source` / `blocked_by`.")
    lines.append("- Unknowns remain where an entry or close lineage is not present in logs.")
    lines.append("")
    lines.append("## Regime Loss Embargo Verdict")
    lines.append(f"- Observed embargo rows: {len(embargo_rows)}")
    lines.append(f"- Observed anomalies tied to embargo bypass: {len([a for a in anomalies if a['anomaly_type'] == 'embargo_bypass_suspected'])}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("- orders_master.csv")
    lines.append("- trades_master.csv")
    lines.append("- intents_master.csv")
    lines.append("- regime_segments.csv")
    lines.append("- anomaly_cases.csv")
    lines.append("- regime_loss_embargo_validation.csv")
    lines.append("- summary_metrics.json")
    lines.append("")
    lines.append("## Notes")
    lines.append("- MFE/MAE is a close-price or OHLC proxy when no full candle surface exists for a symbol.")
    lines.append("- Some `position_close:*` rows lack entry lineage and are marked as inferred or incomplete.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a runtime forensic dataset for Aurora / Phenix.")
    ap.add_argument("--out-dir", default=str(REPORTS))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    order_log = load_order_log()
    trade_lifecycle = load_trade_lifecycle()
    shadow = load_shadow_events()
    regime_events = build_regime_events(shadow)
    price_series = build_price_series()

    orders = build_orders(order_log, shadow, trade_lifecycle)
    # Trade rows are derived from close events and entry order queues.
    trade_rows = build_trades(order_log, orders, regime_events, price_series)
    intents = build_intents(shadow, orders, trade_rows)
    segments = build_regime_segments(regime_events, trade_rows, intents)
    embargo_rows = build_embargo_validation(order_log, regime_events, trade_rows, intents)
    anomalies = detect_anomalies(orders, trade_rows, intents, regime_events, embargo_rows)
    summary = summary_metrics(orders, trade_rows, intents, regime_events, embargo_rows)

    # Write artifacts.
    order_rows = []
    for order in sorted(orders.values(), key=lambda o: (o.open_ts_ms or 0, o.symbol, o.key)):
        order_rows.append(
            {
                "symbol": order.symbol,
                "strategy_id": order.strategy_id,
                "side": order.side,
                "order_type": order.order_type,
                "tif": order.tif,
                "client_order_id": order.client_order_id,
                "order_id": order.order_id,
                "exchange_order_id": order.exchange_order_id,
                "rid": order.rid,
                "lifecycle_id": order.lifecycle_id,
                "source_event": order.source_event,
                "source_component": order.source_component,
                "source_path": order.source_path,
                "order_open_ts_ms": order.open_ts_ms,
                "last_state_ts_ms": order.last_state_ts_ms,
                "placement_outcome": order.placement_outcome,
                "final_status": order.final_status,
                "placed_qty": order.placed_qty,
                "filled_qty": order.filled_qty,
                "avg_fill_price": order.avg_fill_price,
                "reduce_only": order.reduce_only,
                "bracket_role": order.bracket_role or order.role,
                "maker_like": order.maker_like,
                "rejection_reason": order.reject_reason,
                "timeout_flag": order.timeout_flag,
                "cancel_flag": order.cancel_flag,
                "reconcile_flag": order.reconcile_flag,
                "divergence_flag": order.divergence_flag,
                "linkage_trade_id": order.linkage_trade_id,
                "linkage_position_id": order.linkage_position_id,
                "regime": order.regime,
                "regime_confidence": order.regime_confidence,
                "regime_epoch_ref": order.regime_epoch_ref,
                "notes": "|".join(order.notes),
            }
        )

    intent_fields = [
        "rid",
        "signal_ts_ms",
        "intent_ts_ms",
        "symbol",
        "strategy_id",
        "side",
        "regime",
        "regime_confidence",
        "regime_epoch_ref",
        "signal_score",
        "intent_outcome",
        "reject_reason_code",
        "reject_reason",
        "blocked_by",
        "order_placed",
        "filled",
        "final_outcome",
        "entry_order_id",
        "entry_client_order_id",
        "linked_trade_rid",
    ]
    trade_fields = [
        "close_rid",
        "parent_rid",
        "symbol",
        "strategy_id",
        "direction",
        "entry_ts_ms",
        "exit_ts_ms",
        "hold_ms",
        "hold_bars_5m",
        "entry_price",
        "exit_price",
        "filled_qty",
        "placed_qty",
        "realized_pnl_abs",
        "realized_pnl_pct",
        "fees",
        "mfe_pct",
        "mae_pct",
        "excursion_source",
        "exit_reason",
        "close_path_source",
        "regime_at_entry",
        "regime_confidence_at_entry",
        "regime_at_exit",
        "regime_confidence_at_exit",
        "regime_changed_during_trade",
        "entry_order_id",
        "entry_client_order_id",
        "entry_role",
        "entry_order_type",
        "entry_tif",
        "entry_maker_like",
        "anomaly_flags",
        "trade_id",
    ]
    segment_fields = [
        "symbol",
        "regime_start_ts_ms",
        "regime_end_ts_ms",
        "regime_label",
        "raw_regime",
        "stable_vs_raw",
        "confidence",
        "basis_tf_sec",
        "changed",
        "duration_ms",
        "trades_opened",
        "fills",
        "gross_pnl",
        "net_pnl",
        "win_rate",
        "avg_hold_ms",
        "avg_mfe_pct",
        "avg_mae_pct",
        "rejected_intents",
        "blocked_signals",
        "first_loss_ts_ms",
        "continued_after_first_loss",
        "next_regime_ts_ms",
    ]
    anomaly_fields = ["anomaly_type", "severity", "symbol", "ts_ms", "rid", "details"]
    embargo_fields = [
        "symbol",
        "epoch_ref",
        "first_loss_ts_ms",
        "first_loss_close_reason",
        "first_loss_pnl",
        "intents_after_loss_same_epoch",
        "filled_after_loss_same_epoch",
        "rejected_after_loss_same_epoch",
        "stopped_after_first_loss",
        "next_epoch_ts_ms",
    ]

    write_csv(out_dir / "orders_master.csv", order_rows, list(order_rows[0].keys()) if order_rows else [])
    write_csv(out_dir / "trades_master.csv", trade_rows, trade_fields)
    write_csv(out_dir / "intents_master.csv", intents, intent_fields)
    write_csv(out_dir / "regime_segments.csv", segments, segment_fields)
    write_csv(out_dir / "anomaly_cases.csv", anomalies, anomaly_fields)
    write_csv(out_dir / "regime_loss_embargo_validation.csv", embargo_rows, embargo_fields)
    (out_dir / "summary_metrics.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report_markdown(out_dir / "final_forensic_report.md", summary, orders, trade_rows, intents, segments, embargo_rows, anomalies)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
