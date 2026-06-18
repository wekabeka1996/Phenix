#!/usr/bin/env python3
"""Runtime trading-session forensic report.

Reads retained ``order_log_v1`` rotations and selected side logs, then writes a
small report bundle: Markdown summary, JSON metrics, CSV tables, and SVG charts.
The script is intentionally streaming-first so large logs do not need to fit in
memory.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SIGNAL_EVENT = "STRATEGY_SIGNAL_PRODUCED"
TERMINAL_EVENTS = {
    "STRATEGY_DECISION_BLOCKED",
    "DECISION_INTENT_REJECTED",
    "INTENT_BUILD_REJECTED",
    "ORDER_INTENT",
    "ORDER_REJECTED",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "ORDER_TIMEOUT",
    "ORDER_CANCELLED",
    "POSITION_CLOSED",
}


def _as_ms(row: dict[str, Any]) -> int | None:
    for key in ("timestamp", "ts_ms", "ts", "bar_close_ts", "bar_close_ts_ms"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            continue
        if parsed <= 0:
            continue
        return parsed // 1000 if parsed > 10_000_000_000_000 else parsed
    return None


def _iso(ms: int | None) -> str:
    if ms is None:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _event(row: dict[str, Any]) -> str:
    return str(row.get("event_type") or row.get("event") or row.get("type") or "")


def _read_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield line_no, value
    except FileNotFoundError:
        return


def _order_log_paths(root: Path) -> list[Path]:
    log_dir = root / "logs"
    return sorted(log_dir.glob("order_log_v1*.jsonl"), key=lambda p: (p.stat().st_mtime, p.name))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _bar_svg(path: Path, title: str, labels: list[str], values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1100
    row_h = 26
    top = 52
    left = 260
    height = max(120, top + row_h * len(labels) + 30)
    max_v = max(values) if values else 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;font-size:12px} .title{font-size:18px;font-weight:600}</style>',
        f'<text class="title" x="20" y="28">{title}</text>',
    ]
    for idx, (label, value) in enumerate(zip(labels, values)):
        y = top + idx * row_h
        bar_w = 0 if max_v <= 0 else int((width - left - 80) * (value / max_v))
        parts.append(f'<text x="20" y="{y + 15}">{label[:38]}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_w}" height="18" fill="#4c78a8"/>')
        parts.append(f'<text x="{left + bar_w + 6}" y="{y + 14}">{value:g}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


@dataclass
class PlacedOrder:
    ts_ms: int | None
    rid: str
    symbol: str
    side: str
    strategy_id: str
    order_id: str
    client_order_id: str
    quantity: Any
    order_type: str
    status: str = "OPEN_OR_UNKNOWN"
    terminal_event: str = ""
    terminal_ts_ms: int | None = None


@dataclass
class RuntimeForensics:
    root: Path
    event_counts: Counter[str] = field(default_factory=Counter)
    event_by_day: Counter[tuple[str, str]] = field(default_factory=Counter)
    strategy_event: Counter[tuple[str, str]] = field(default_factory=Counter)
    strategy_symbol_event: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    reason_counts: Counter[tuple[str, str, str, str]] = field(default_factory=Counter)
    regime_counts: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    nrr_counts: Counter[tuple[str, str, str, str]] = field(default_factory=Counter)
    signals: dict[str, dict[str, Any]] = field(default_factory=dict)
    signal_terminals: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    placed: dict[str, PlacedOrder] = field(default_factory=dict)
    placed_by_order_id: dict[str, str] = field(default_factory=dict)
    placed_by_client_id: dict[str, str] = field(default_factory=dict)
    pending_terminals: dict[str, tuple[str, int | None]] = field(default_factory=dict)
    fills: list[dict[str, Any]] = field(default_factory=list)
    closes: list[dict[str, Any]] = field(default_factory=list)
    registry_snapshots: list[dict[str, Any]] = field(default_factory=list)
    first_ts_ms: int | None = None
    last_ts_ms: int | None = None
    rows: int = 0
    malformed: int = 0
    source_files: list[dict[str, Any]] = field(default_factory=list)

    def ingest_order_logs(self, paths: list[Path]) -> None:
        for path in paths:
            file_rows = 0
            before = self.rows
            for _line_no, row in _read_jsonl(path):
                file_rows += 1
                self.rows += 1
                self._ingest_row(row)
            stat = path.stat()
            self.source_files.append({
                "path": str(path),
                "bytes": stat.st_size,
                "rows": self.rows - before,
                "mtime_utc": _iso(int(stat.st_mtime * 1000)),
            })

    def _ingest_row(self, row: dict[str, Any]) -> None:
        et = _event(row)
        ts_ms = _as_ms(row)
        if ts_ms is not None:
            self.first_ts_ms = ts_ms if self.first_ts_ms is None else min(self.first_ts_ms, ts_ms)
            self.last_ts_ms = ts_ms if self.last_ts_ms is None else max(self.last_ts_ms, ts_ms)
            day = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
            self.event_by_day[(day, et)] += 1
        self.event_counts[et] += 1
        strategy = str(row.get("strategy_id") or "")
        symbol = str(row.get("symbol") or "")
        if strategy:
            self.strategy_event[(strategy, et)] += 1
        if strategy or symbol:
            self.strategy_symbol_event[(strategy, symbol, et)] += 1
        reason = str(row.get("reason_code") or row.get("nrr_code") or "")
        regime = str(row.get("regime") or "")
        if reason:
            self.reason_counts[(strategy, symbol, reason, regime)] += 1
        if regime:
            self.regime_counts[(strategy, symbol, regime)] += 1
        nrr = str(row.get("nrr_code") or "")
        if nrr:
            self.nrr_counts[(strategy, symbol, nrr, str(row.get("side") or ""))] += 1

        rid = str(row.get("rid") or "")
        if et == SIGNAL_EVENT and rid:
            self.signals[rid] = row
        elif rid and et in TERMINAL_EVENTS:
            self.signal_terminals[rid].append(row)

        if et == "ORDER_PLACED":
            self._ingest_order_placed(row, ts_ms)
        elif et in {"ORDER_FILLED", "ORDER_CANCELLED", "ORDER_TIMEOUT", "ORDER_REJECTED", "ORDER_CANCELLATION_FAILED"}:
            self._mark_order_terminal(row, et, ts_ms)
        if et == "ORDER_FILLED":
            self.fills.append(row)
        if et == "POSITION_CLOSED":
            self.closes.append(row)
        if et == "STRATEGY_REGISTRY_SNAPSHOT":
            self.registry_snapshots.append(row)

    def _ingest_order_placed(self, row: dict[str, Any], ts_ms: int | None) -> None:
        order_id = str(row.get("order_id") or (row.get("adapter_response") or {}).get("orderId") or "")
        client_id = str(row.get("client_order_id") or (row.get("adapter_response") or {}).get("clientOrderId") or "")
        key = order_id or client_id or str(row.get("rid") or f"placed:{len(self.placed)}")
        placed = PlacedOrder(
            ts_ms=ts_ms,
            rid=str(row.get("rid") or ""),
            symbol=str(row.get("symbol") or ""),
            side=str(row.get("side") or ""),
            strategy_id=str(row.get("strategy_id") or ""),
            order_id=order_id,
            client_order_id=client_id,
            quantity=row.get("quantity") or row.get("qty_raw"),
            order_type=str(row.get("order_type") or (row.get("adapter_response") or {}).get("type") or ""),
        )
        self.placed[key] = placed
        if order_id:
            self.placed_by_order_id[order_id] = key
        if client_id:
            self.placed_by_client_id[client_id] = key
        for identity in (order_id, client_id, placed.rid):
            if identity and identity in self.pending_terminals:
                terminal_event, terminal_ts_ms = self.pending_terminals[identity]
                placed.status = terminal_event
                placed.terminal_event = terminal_event
                placed.terminal_ts_ms = terminal_ts_ms
                break

    def _mark_order_terminal(self, row: dict[str, Any], et: str, ts_ms: int | None) -> None:
        candidates = [
            str(row.get("order_id") or ""),
            str(row.get("client_order_id") or ""),
            str(row.get("rid") or ""),
        ]
        key = ""
        for candidate in candidates:
            if not candidate:
                continue
            key = self.placed_by_order_id.get(candidate) or self.placed_by_client_id.get(candidate) or ""
            if key:
                break
        if key and key in self.placed:
            self.placed[key].status = et
            self.placed[key].terminal_event = et
            self.placed[key].terminal_ts_ms = ts_ms
        else:
            for candidate in candidates:
                if candidate:
                    self.pending_terminals[candidate] = (et, ts_ms)

    def rows_for_counter(self, counter: Counter, names: tuple[str, ...], limit: int | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, value in counter.most_common(limit):
            if not isinstance(key, tuple):
                key = (key,)
            row = {name: key[idx] if idx < len(key) else "" for idx, name in enumerate(names)}
            row["count"] = value
            rows.append(row)
        return rows

    def signal_coverage(self) -> dict[str, Any]:
        missing = []
        terminal_counts = Counter()
        for rid, signal in self.signals.items():
            terminals = self.signal_terminals.get(rid, [])
            if not terminals:
                missing.append(signal)
                continue
            terminal_counts[_event(terminals[-1])] += 1
        total = len(self.signals)
        covered = total - len(missing)
        return {
            "signals": total,
            "covered": covered,
            "missing": len(missing),
            "coverage_pct": round((covered / total * 100.0), 4) if total else 100.0,
            "terminal_counts": dict(terminal_counts),
            "missing_examples": missing[:20],
        }

    def financial_summary(self) -> dict[str, Any]:
        fill_count = len(self.fills)
        entry_fills = 0
        close_fills = 0
        commission = 0.0
        realized = 0.0
        realized_seen = 0
        by_symbol = defaultdict(lambda: {"fills": 0, "commission": 0.0, "realized_pnl": 0.0, "realized_seen": 0})
        by_strategy = defaultdict(lambda: {"fills": 0, "commission": 0.0, "realized_pnl": 0.0, "realized_seen": 0})
        for row in self.fills:
            kind = str(row.get("order_kind") or "").upper()
            if kind == "ENTRY":
                entry_fills += 1
            elif kind in {"CLOSE", "SL", "TP", "TAKE_PROFIT", "STOP_LOSS"}:
                close_fills += 1
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            c = _float(meta.get("commission") or row.get("commission"))
            pnl = _float(meta.get("realized_pnl") or row.get("realized_pnl"))
            if c is not None:
                commission += c
            if pnl is not None:
                realized += pnl
                realized_seen += 1
            symbol = str(row.get("symbol") or "")
            strategy = str(row.get("strategy_id") or "")
            for bucket in (by_symbol[symbol], by_strategy[strategy]):
                bucket["fills"] += 1
                if c is not None:
                    bucket["commission"] += c
                if pnl is not None:
                    bucket["realized_pnl"] += pnl
                    bucket["realized_seen"] += 1
        unresolved_closes = [row for row in self.closes if str(row.get("pnl_status") or "").lower() != "resolved"]
        return {
            "fill_count": fill_count,
            "entry_fills": entry_fills,
            "close_fills": close_fills,
            "commission_sum": round(commission, 8),
            "realized_pnl_sum_from_fills": round(realized, 8),
            "realized_pnl_seen_rows": realized_seen,
            "position_closed_rows": len(self.closes),
            "position_closed_unresolved": len(unresolved_closes),
            "by_symbol": _counter_rows_from_map(by_symbol),
            "by_strategy": _counter_rows_from_map(by_strategy),
        }

    def open_orders(self) -> list[dict[str, Any]]:
        rows = []
        for order in self.placed.values():
            if order.status in {
                "ORDER_FILLED",
                "ORDER_CANCELLED",
                "ORDER_REJECTED",
                "ORDER_TIMEOUT",
                "ORDER_CANCELLATION_FAILED",
            }:
                continue
            rows.append({
                "placed_utc": _iso(order.ts_ms),
                "age_min": _age_min(order.ts_ms, self.last_ts_ms),
                "rid": order.rid,
                "symbol": order.symbol,
                "side": order.side,
                "strategy_id": order.strategy_id,
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "status": order.status,
                "terminal_event": order.terminal_event,
            })
        return sorted(rows, key=lambda r: (r.get("symbol") or "", r.get("placed_utc") or ""))

    def timed_out_orders(self) -> list[dict[str, Any]]:
        rows = []
        for order in self.placed.values():
            if order.status not in {"ORDER_TIMEOUT", "ORDER_CANCELLATION_FAILED"}:
                continue
            rows.append({
                "placed_utc": _iso(order.ts_ms),
                "terminal_utc": _iso(order.terminal_ts_ms),
                "age_to_terminal_min": _age_min(order.ts_ms, order.terminal_ts_ms),
                "rid": order.rid,
                "symbol": order.symbol,
                "side": order.side,
                "strategy_id": order.strategy_id,
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "status": order.status,
                "terminal_event": order.terminal_event,
            })
        return sorted(rows, key=lambda r: (r.get("terminal_utc") or "", r.get("symbol") or ""))

    def active_lifecycles(self) -> list[dict[str, Any]]:
        closed_lifecycles = {
            str(row.get("lifecycle_id") or row.get("rid") or "")
            for row in self.closes
            if row.get("lifecycle_id") or row.get("rid")
        }
        entry_fills: dict[str, dict[str, Any]] = {}
        for row in self.fills:
            if str(row.get("order_kind") or "").upper() != "ENTRY":
                continue
            lifecycle = str(row.get("lifecycle_id") or "")
            if lifecycle:
                entry_fills[lifecycle] = row
        active = []
        for lifecycle, row in entry_fills.items():
            if lifecycle in closed_lifecycles:
                continue
            active.append({
                "entry_utc": _iso(_as_ms(row)),
                "age_min": _age_min(_as_ms(row), self.last_ts_ms),
                "lifecycle_id": lifecycle,
                "rid": row.get("rid"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "strategy_id": row.get("strategy_id"),
                "quantity": row.get("quantity"),
                "price": row.get("price"),
                "commission": (row.get("metadata") or {}).get("commission") if isinstance(row.get("metadata"), dict) else None,
            })
        return sorted(active, key=lambda r: (r.get("symbol") or "", r.get("entry_utc") or ""))


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _age_min(start_ms: int | None, end_ms: int | None) -> float | None:
    if start_ms is None or end_ms is None:
        return None
    return round(max(0, end_ms - start_ms) / 60000.0, 2)


def _counter_rows_from_map(mapping: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for key, value in sorted(mapping.items()):
        row = {"key": key}
        row.update({k: round(v, 8) if isinstance(v, float) else v for k, v in value.items()})
        rows.append(row)
    return rows


def _latest_portfolio_from_lifecycle(path: Path, max_bytes: int) -> dict[str, Any]:
    if not path.exists():
        return {}
    size = path.stat().st_size
    offset = max(0, size - max_bytes)
    latest: dict[str, Any] = {}
    with path.open("rb") as handle:
        handle.seek(offset)
        if offset:
            handle.readline()
        for raw in handle:
            try:
                row = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if not symbol:
                continue
            if "position_snapshot" in row or row.get("record_kind") == "position_policy_sidecar":
                latest[str(symbol)] = row
    return latest


def _render_markdown(report: RuntimeForensics, out_dir: Path, lifecycle_latest: dict[str, Any]) -> str:
    coverage = report.signal_coverage()
    financial = report.financial_summary()
    open_orders = report.open_orders()
    timed_out_orders = report.timed_out_orders()
    active_lifecycles = report.active_lifecycles()
    latest_registry = report.registry_snapshots[-1] if report.registry_snapshots else {}
    lines = [
        "# Runtime Trading Session Forensic Report",
        "",
        f"- Generated UTC: {_iso(int(datetime.now(tz=timezone.utc).timestamp() * 1000))}",
        f"- Order-log window UTC: {_iso(report.first_ts_ms)} -> {_iso(report.last_ts_ms)}",
        f"- Parsed order-log rows: {report.rows}",
        f"- Source files: {len(report.source_files)}",
        "",
        "## Executive Findings",
    ]
    if active_lifecycles:
        lines.append(f"- Active lifecycle candidates from order_log: **{len(active_lifecycles)}**. See `active_lifecycles.csv`.")
    else:
        lines.append("- Active lifecycle candidates from order_log: **0**.")
    lines.extend([
        f"- Open/unknown placed orders from order_log: **{len(open_orders)}**. See `open_orders.csv`.",
        f"- Timed-out/cancel-failed placed orders from order_log: **{len(timed_out_orders)}**. See `timed_out_orders.csv`.",
        f"- Strategy signal terminal coverage: **{coverage['coverage_pct']}%** ({coverage['covered']}/{coverage['signals']}).",
        f"- Fills: **{financial['fill_count']}** total, entry={financial['entry_fills']}, close={financial['close_fills']}.",
        f"- Commission sum from fill metadata: **{financial['commission_sum']} USDT**.",
        f"- POSITION_CLOSED rows unresolved: **{financial['position_closed_unresolved']} / {financial['position_closed_rows']}**.",
        "",
        "## Strategy Runtime Surface",
    ])
    if latest_registry:
        for item in latest_registry.get("strategies", []):
            lines.append(
                f"- `{item.get('strategy_id')}` mode={item.get('mode')} status={item.get('status')} "
                f"financially_reachable={item.get('financially_reachable')} blockers={item.get('financial_blockers')}"
            )
    else:
        lines.append("- No STRATEGY_REGISTRY_SNAPSHOT found in retained order_log.")
    lines.extend([
        "",
        "## Mean Reversion Diagnosis",
    ])
    mr_reasons = [
        row for row in report.rows_for_counter(report.reason_counts, ("strategy_id", "symbol", "reason_code", "regime"))
        if row["strategy_id"] == "mean_reversion"
    ]
    mr_signals = sum(
        count for (strategy, event), count in report.strategy_event.items()
        if strategy == "mean_reversion" and event == SIGNAL_EVENT
    )
    mr_orders = sum(
        count for (strategy, event), count in report.strategy_event.items()
        if strategy == "mean_reversion" and event in {"ORDER_INTENT", "ORDER_PLACED", "ORDER_FILLED"}
    )
    mr_shadow = sum(
        row["count"] for row in mr_reasons if row["reason_code"] == "AUTHORITY_MODE_SHADOW"
    )
    lines.extend([
        f"- mean_reversion strategy signals produced: **{mr_signals}**.",
        f"- mean_reversion financial order events (`ORDER_INTENT/ORDER_PLACED/ORDER_FILLED`): **{mr_orders}**.",
        f"- mean_reversion signals shadow-blocked by authority: **{mr_shadow}**.",
        "- Top mean_reversion blockers:",
    ])
    for row in mr_reasons[:15]:
        lines.append(
            f"  - {row['symbol']} {row['reason_code']} regime={row['regime']}: {row['count']}"
        )
    lines.extend([
        "",
        "Interpretation: if `AUTHORITY_MODE_SHADOW` equals produced signals, MR can generate candidates but is not allowed to route financial intents. "
        "`REGIME_UNCERTAIN` and `REGIME_NOT_FLAT` are normal terminal blocks for a flat/mean-reversion strategy when structural regime is missing or trending. "
        "Any remaining `REGIME_MAPPING_NONE` indicates old-runtime rows before canonical regime propagation or a producer still emitting without canonical structural_regime.",
        "",
        "## Financial Tables",
        "- `strategy_event_matrix.csv`",
        "- `reason_matrix.csv`",
        "- `nrr_matrix.csv`",
        "- `open_orders.csv`",
        "- `active_lifecycles.csv`",
        "- `fills_by_symbol.csv`",
        "",
        "## Charts",
        "- `event_counts.svg`",
        "- `strategy_signal_blocks.svg`",
        "- `mean_reversion_reasons.svg`",
    ])
    if lifecycle_latest:
        lines.extend(["", "## Latest Lifecycle/Sidecar Portfolio Hints"])
        for symbol, row in sorted(lifecycle_latest.items()):
            snap = row.get("position_snapshot") if isinstance(row.get("position_snapshot"), dict) else {}
            lines.append(
                f"- {symbol}: snapshot_status={snap.get('portfolio_snapshot_status')} "
                f"manage_state={snap.get('manage_state')} position_signature="
                f"{(row.get('portfolio_correlation') or {}).get('position_signature') if isinstance(row.get('portfolio_correlation'), dict) else None}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--lifecycle-tail-mb", type=int, default=256)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir) if args.out_dir else root / "reports" / f"runtime_forensic_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = RuntimeForensics(root=root)
    paths = _order_log_paths(root)
    report.ingest_order_logs(paths)
    lifecycle_latest = _latest_portfolio_from_lifecycle(
        root / "logs" / "trade_lifecycle.jsonl",
        max_bytes=max(1, args.lifecycle_tail_mb) * 1024 * 1024,
    )

    metrics = {
        "window": {"first_utc": _iso(report.first_ts_ms), "last_utc": _iso(report.last_ts_ms)},
        "source_files": report.source_files,
        "event_counts": dict(report.event_counts),
        "signal_coverage": report.signal_coverage(),
        "financial": report.financial_summary(),
        "open_orders_count": len(report.open_orders()),
        "timed_out_orders_count": len(report.timed_out_orders()),
        "active_lifecycles_count": len(report.active_lifecycles()),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "REPORT.md").write_text(_render_markdown(report, out_dir, lifecycle_latest), encoding="utf-8")

    _write_csv(out_dir / "event_counts.csv", report.rows_for_counter(report.event_counts, ("event_type",)))
    _write_csv(out_dir / "strategy_event_matrix.csv", report.rows_for_counter(report.strategy_event, ("strategy_id", "event_type")))
    _write_csv(out_dir / "strategy_symbol_event_matrix.csv", report.rows_for_counter(report.strategy_symbol_event, ("strategy_id", "symbol", "event_type")))
    _write_csv(out_dir / "reason_matrix.csv", report.rows_for_counter(report.reason_counts, ("strategy_id", "symbol", "reason_code", "regime")))
    _write_csv(out_dir / "nrr_matrix.csv", report.rows_for_counter(report.nrr_counts, ("strategy_id", "symbol", "nrr_code", "side")))
    _write_csv(out_dir / "open_orders.csv", report.open_orders())
    _write_csv(out_dir / "timed_out_orders.csv", report.timed_out_orders())
    _write_csv(out_dir / "active_lifecycles.csv", report.active_lifecycles())
    _write_csv(out_dir / "fills_by_symbol.csv", report.financial_summary()["by_symbol"])
    _write_csv(out_dir / "fills_by_strategy.csv", report.financial_summary()["by_strategy"])

    events = report.rows_for_counter(report.event_counts, ("event_type",), limit=20)
    _bar_svg(out_dir / "event_counts.svg", "Order Log Event Counts", [r["event_type"] for r in events], [r["count"] for r in events])
    strategy_blocks = [
        r for r in report.rows_for_counter(report.strategy_event, ("strategy_id", "event_type"))
        if r["event_type"] in {SIGNAL_EVENT, "STRATEGY_DECISION_BLOCKED", "DECISION_INTENT_REJECTED", "ORDER_PLACED", "ORDER_FILLED"}
    ][:30]
    _bar_svg(
        out_dir / "strategy_signal_blocks.svg",
        "Strategy Funnel Events",
        [f"{r['strategy_id']}:{r['event_type']}" for r in strategy_blocks],
        [r["count"] for r in strategy_blocks],
    )
    mr = [
        r for r in report.rows_for_counter(report.reason_counts, ("strategy_id", "symbol", "reason_code", "regime"))
        if r["strategy_id"] == "mean_reversion"
    ][:25]
    _bar_svg(
        out_dir / "mean_reversion_reasons.svg",
        "Mean Reversion Top Block Reasons",
        [f"{r['symbol']}:{r['reason_code']}:{r['regime']}" for r in mr],
        [r["count"] for r in mr],
    )

    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
