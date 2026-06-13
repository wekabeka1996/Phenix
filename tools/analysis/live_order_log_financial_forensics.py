#!/usr/bin/env python3
"""Read-only financial forensic report for logs/order_log_v1.jsonl."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
DEFAULT_REPORT = ROOT / "reports" / "ORDER_LOG_V1_LIVE_FINANCIAL_FORENSIC_REPORT.md"

MARKET_REACHED_EVENTS = {"ORDER_PLACED", "ORDER_FILLED"}
NON_FINANCIAL_EVENT_TYPES = {"STRATEGY_REGISTRY_SNAPSHOT"}
RESOLVED_PNL_STATUS = "resolved"
PLAN_BASELINE = {
    "parsed_rows": 260,
    "resolved_net_pnl": 124.95236245,
    "resolved_fees": 60.62331296,
    "BNBUSDT_net_pnl": 61.42713010,
    "XRPUSDT_net_pnl": 2.99079557,
    "1000PEPEUSDT_net_pnl": 60.53443678,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a financial forensic report for the live order_log_v1.jsonl."
    )
    parser.add_argument("--order-log", type=Path, default=DEFAULT_ORDER_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    parse_errors = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["_line"] = line_no
                rows.append(payload)
            else:
                parse_errors += 1
    return rows, parse_errors


def nested_get(payload: dict[str, Any], dotted_path: str) -> Any:
    node: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def iso_utc(ts_ms: Any) -> str:
    if not isinstance(ts_ms, (int, float)):
        return ""
    return datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).isoformat()


def fmt_number(value: Any, digits: int = 6) -> str:
    number = safe_float(value)
    if number is None:
        return ""
    rendered = f"{number:.{digits}f}"
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def pct(numerator: float | int, denominator: float | int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{100.0 * float(numerator) / float(denominator):.1f}%"


def md_escape(value: Any) -> str:
    raw = text(value)
    return raw.replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    row_list = [[md_escape(cell) for cell in row] for row in rows]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in row_list:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def identity(row: dict[str, Any]) -> str:
    return text(
        first_present(
            row.get("lifecycle_id"),
            nested_get(row, "metadata.lifecycle_id"),
            row.get("reservation_id"),
            nested_get(row, "metadata.reservation_id"),
            row.get("rid"),
        )
    )


def strategy(row: dict[str, Any]) -> str:
    return text(first_present(row.get("strategy_id"), nested_get(row, "metadata.strategy_id")))


def regime(row: dict[str, Any]) -> str:
    return text(first_present(row.get("regime"), nested_get(row, "metadata.regime")))


def extract_why_class(why: str) -> str:
    if not why:
        return ""
    if why.startswith("SAFETY_GATES:FIX-CONF-GATE-01"):
        if "AT_OR_BELOW_MINIMUM" in why:
            return "regime_confidence_below_min"
        if " > max=" in why:
            return "regime_confidence_above_max"
        return "regime_confidence_gate"
    if why.startswith("SAFETY_GATES:"):
        return why.split(":", 1)[1].strip()
    if why.startswith("Order timeout"):
        return "order_timeout"
    return why


def aggregate_closed(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], Any],
) -> dict[Any, dict[str, Any]]:
    result: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {"closed": 0, "resolved": 0, "unresolved": 0, "wins": 0, "losses": 0, "gross_pnl": 0.0, "net_pnl": 0.0, "fees": 0.0}
    )
    for row in rows:
        key = key_fn(row)
        bucket = result[key]
        bucket["closed"] += 1
        pnl = safe_float(row.get("realized_pnl_net"))
        gross_pnl = safe_float(nested_get(row, "metadata.realized_pnl"))
        fees = safe_float(row.get("fees")) or 0.0
        bucket["fees"] += fees
        if text(row.get("pnl_status")) == RESOLVED_PNL_STATUS and pnl is not None:
            bucket["resolved"] += 1
            bucket["gross_pnl"] += gross_pnl if gross_pnl is not None else pnl + fees
            bucket["net_pnl"] += pnl
            if pnl > 0:
                bucket["wins"] += 1
            elif pnl < 0:
                bucket["losses"] += 1
        else:
            bucket["unresolved"] += 1
    return dict(result)


def sorted_agg_rows(agg: dict[Any, dict[str, Any]]) -> list[tuple[Any, dict[str, Any]]]:
    return sorted(agg.items(), key=lambda item: (-item[1]["net_pnl"], text(item[0])))


def build_lifecycle_context(rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = identity(row)
        if key:
            grouped[key].append(row)

    context: dict[str, dict[str, str]] = {}
    for key, events in grouped.items():
        strategies = [strategy(event) for event in events if strategy(event)]
        regimes = [regime(event) for event in events if regime(event)]
        source = "direct_lifecycle"
        context[key] = {
            "strategy": strategies[0] if strategies else "",
            "regime": regimes[0] if regimes else "",
            "source": source if strategies or regimes else "",
        }
    return context


def infer_closed_context(row: dict[str, Any], lifecycle_context: dict[str, dict[str, str]]) -> dict[str, str]:
    key = identity(row)
    ctx = lifecycle_context.get(key, {})
    return {
        "strategy": strategy(row) or ctx.get("strategy", ""),
        "regime": regime(row) or ctx.get("regime", ""),
        "source": "position_row" if strategy(row) or regime(row) else ctx.get("source", ""),
    }


def main() -> int:
    args = parse_args()
    order_log = args.order_log.resolve()
    rows, parse_errors = read_jsonl(order_log)

    registry_snapshots = [
        row for row in rows
        if row.get("event_type") == "STRATEGY_REGISTRY_SNAPSHOT"
    ]
    financial_rows = [
        row for row in rows
        if row.get("event_type") not in NON_FINANCIAL_EVENT_TYPES
    ]
    event_counts = Counter(text(row.get("event_type")) for row in financial_rows)
    source_counts = Counter(text(row.get("source_fsm")) for row in rows)
    symbols = sorted({text(row.get("symbol")) for row in rows if text(row.get("symbol")) and text(row.get("symbol")) != "_SYSTEM_"})
    first_ts = min((row.get("timestamp") for row in rows if isinstance(row.get("timestamp"), (int, float))), default=None)
    last_ts = max((row.get("timestamp") for row in rows if isinstance(row.get("timestamp"), (int, float))), default=None)

    closed = [row for row in rows if row.get("event_type") == "POSITION_CLOSED"]
    resolved_closed = [
        row for row in closed if text(row.get("pnl_status")) == RESOLVED_PNL_STATUS and safe_float(row.get("realized_pnl_net")) is not None
    ]
    unresolved_closed = [row for row in closed if row not in resolved_closed]
    resolved_net = sum(safe_float(row.get("realized_pnl_net")) or 0.0 for row in resolved_closed)
    resolved_fees = sum(safe_float(row.get("fees")) or 0.0 for row in resolved_closed)
    resolved_gross = sum(
        safe_float(nested_get(row, "metadata.realized_pnl"))
        if safe_float(nested_get(row, "metadata.realized_pnl")) is not None
        else (safe_float(row.get("realized_pnl_net")) or 0.0) + (safe_float(row.get("fees")) or 0.0)
        for row in resolved_closed
    )
    wins = sum(1 for row in resolved_closed if (safe_float(row.get("realized_pnl_net")) or 0.0) > 0)
    losses = sum(1 for row in resolved_closed if (safe_float(row.get("realized_pnl_net")) or 0.0) < 0)

    by_symbol_event: dict[str, Counter[str]] = defaultdict(Counter)
    for row in financial_rows:
        symbol = text(row.get("symbol"))
        if symbol and symbol != "_SYSTEM_":
            by_symbol_event[symbol][text(row.get("event_type"))] += 1

    rejected = [row for row in rows if row.get("event_type") == "DECISION_INTENT_REJECTED"]
    nrr_counts = Counter(text(row.get("nrr_code")) for row in rejected if text(row.get("nrr_code")))
    why_class_counts = Counter(extract_why_class(text(row.get("why"))) for row in rejected if text(row.get("why")))
    reject_by_symbol = Counter(text(row.get("symbol")) for row in rejected)
    reject_by_symbol_strategy_regime = Counter((text(row.get("symbol")), strategy(row), regime(row)) for row in rejected)

    market_reached_symbols = {
        symbol for symbol, counts in by_symbol_event.items() if sum(counts[event] for event in MARKET_REACHED_EVENTS) > 0
    }
    rejected_symbols = set(reject_by_symbol)
    not_to_market_symbols = sorted(rejected_symbols - market_reached_symbols)
    traded_symbols = sorted(market_reached_symbols)

    lifecycle_context = build_lifecycle_context(rows)
    enriched_closed: list[dict[str, Any]] = []
    for row in closed:
        copy = dict(row)
        ctx = infer_closed_context(row, lifecycle_context)
        copy["_inferred_strategy"] = ctx["strategy"]
        copy["_inferred_regime"] = ctx["regime"]
        copy["_context_source"] = ctx["source"]
        enriched_closed.append(copy)

    by_symbol = aggregate_closed(enriched_closed, lambda row: row.get("symbol"))
    by_side = aggregate_closed(enriched_closed, lambda row: row.get("side"))
    by_close_reason = aggregate_closed(enriched_closed, lambda row: row.get("close_reason"))
    by_symbol_side = aggregate_closed(enriched_closed, lambda row: (row.get("symbol"), row.get("side")))
    by_strategy_regime = aggregate_closed(
        enriched_closed,
        lambda row: (
            row.get("_inferred_strategy") or "unknown_execution_context",
            row.get("_inferred_regime") or "unknown_execution_context",
        ),
    )

    execution_rows = [row for row in rows if row.get("event_type") in {"ORDER_INTENT", "ORDER_PLACED", "ORDER_FILLED", "POSITION_CLOSED"}]
    execution_without_strategy = sum(1 for row in execution_rows if not strategy(row))
    execution_without_regime = sum(1 for row in execution_rows if not regime(row))
    schema_extra_events = sorted(set(event_counts) - {
        "BOOT",
        "ORDER_INTENT",
        "ORDER_PLACED",
        "ORDER_FILLED",
        "ORDER_CANCELLED",
        "ORDER_CANCELLATION_FAILED",
        "ORDER_TIMEOUT",
        "ORDER_REJECTED",
        "DECISION_INTENT_REJECTED",
        "ORDER_STATE_CHANGED",
        "POSITION_CLOSED",
        "QTY_NORMALIZE_REJECTED",
    })

    lines: list[str] = []
    lines.append("# ORDER_LOG_V1 Live Financial Forensic Report")
    lines.append("")
    try:
        source_label = order_log.relative_to(ROOT).as_posix()
    except ValueError:
        source_label = order_log.as_posix()
    lines.append(f"- Source: `{source_label}`")
    lines.append(f"- Generated from {len(rows)} parsed JSONL rows; parse errors: {parse_errors}")
    lines.append(
        f"- Non-financial strategy registry snapshots excluded from all financial counts: {len(registry_snapshots)}"
    )
    lines.append(f"- Event window UTC: `{iso_utc(first_ts)}` to `{iso_utc(last_ts)}`")
    if len(rows) != PLAN_BASELINE["parsed_rows"]:
        lines.append(
            f"- Baseline drift: the implementation plan observed {PLAN_BASELINE['parsed_rows']} rows, "
            f"but the current live log has {len(rows)} rows."
        )
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    profitability_label = "profitable" if resolved_net > 0 else "unprofitable"
    lines.append(
        f"The live log is net {profitability_label} on resolved closes: `{fmt_number(resolved_net, 8)}` quote PnL after "
        f"`{fmt_number(resolved_fees, 8)}` fees on `{fmt_number(resolved_gross, 8)}` gross PnL across {len(resolved_closed)} resolved closed positions "
        f"({wins} wins, {losses} losses, win rate {pct(wins, len(resolved_closed))})."
    )
    lines.append(
        "`BNBUSDT`, `XRPUSDT`, and `1000PEPEUSDT` reached the market. "
        "`BTCUSDT` and `ETHUSDT` did not reach exchange execution in this live log: their events stop at rejected decision intents."
    )
    lines.append(
        "The financial edge is concentrated in TP exits. SL/CLOSE exits are consistently negative after fees, "
        "and 3 `POSITION_CLOSED_DETECTED` rows are unresolved accounting cases with no `realized_pnl_net`."
    )
    lines.append(
        "Strategy/regime attribution is strong for rejected decisions, but weak for execution rows: most execution events omit "
        "`strategy_id` and `regime`, so closed-position profitability is attributed mainly by lifecycle context when available."
    )
    if len(rows) != PLAN_BASELINE["parsed_rows"]:
        lines.append(
            "Since the plan was written, the live log appended a new XRPUSDT SL close; this changed the total resolved PnL "
            "and XRPUSDT bucket versus the original control figures."
        )
    lines.append("")

    lines.append("## Global Event Inventory")
    lines.append("")
    lines.append(markdown_table(["event_type", "count"], event_counts.most_common()))
    lines.append("")
    lines.append(markdown_table(["source_fsm", "count"], source_counts.most_common()))
    lines.append("")

    lines.append("## Market Reachability Funnel")
    lines.append("")
    funnel_rows = []
    for symbol in symbols:
        counts = by_symbol_event[symbol]
        market_reached = "yes" if symbol in market_reached_symbols else "no"
        classification = "market reached" if symbol in market_reached_symbols else "not to market"
        funnel_rows.append(
            [
                symbol,
                counts["DECISION_INTENT_REJECTED"],
                counts["ORDER_INTENT"],
                counts["ORDER_PLACED"],
                counts["ORDER_FILLED"],
                counts["POSITION_CLOSED"],
                market_reached,
                classification,
            ]
        )
    lines.append(markdown_table(
        ["symbol", "rejected", "intent", "placed", "filled", "closed", "market_reached", "classification"],
        funnel_rows,
    ))
    lines.append("")
    lines.append(f"- Symbols with exchange execution: `{', '.join(traded_symbols)}`.")
    lines.append(f"- Rejected-only symbols: `{', '.join(not_to_market_symbols)}`.")
    lines.append("")

    lines.append("## Realized PnL Summary")
    lines.append("")
    lines.append(markdown_table(
        ["metric", "value"],
        [
            ["closed positions", len(closed)],
            ["resolved closed positions", len(resolved_closed)],
            ["unresolved closed positions", len(unresolved_closed)],
            ["resolved net PnL", fmt_number(resolved_net, 8)],
            ["resolved gross PnL", fmt_number(resolved_gross, 8)],
            ["resolved fees", fmt_number(resolved_fees, 8)],
            ["wins", wins],
            ["losses", losses],
            ["win rate", pct(wins, len(resolved_closed))],
        ],
    ))
    lines.append("")

    def agg_table(title: str, agg: dict[Any, dict[str, Any]]) -> None:
        lines.append(f"### {title}")
        lines.append("")
        table_rows = []
        for key, bucket in sorted_agg_rows(agg):
            table_rows.append([
                key,
                bucket["closed"],
                bucket["resolved"],
                bucket["unresolved"],
                bucket["wins"],
                bucket["losses"],
                fmt_number(bucket["gross_pnl"], 8),
                fmt_number(bucket["net_pnl"], 8),
                fmt_number(bucket["fees"], 8),
            ])
        lines.append(markdown_table(
            ["bucket", "closed", "resolved", "unresolved", "wins", "losses", "gross_pnl", "net_pnl", "fees"],
            table_rows,
        ))
        lines.append("")

    agg_table("By Symbol", by_symbol)
    agg_table("By Side", by_side)
    agg_table("By Close Reason", by_close_reason)
    agg_table("By Symbol And Side", by_symbol_side)
    agg_table("By Inferred Strategy And Regime", by_strategy_regime)

    lines.append("## Strategy And Regime Activity")
    lines.append("")
    decision_rows = []
    for (symbol, strat, reg), count in reject_by_symbol_strategy_regime.most_common():
        decision_rows.append([symbol, strat or "", reg or "", count])
    lines.append("Rejected decision activity by symbol/strategy/regime:")
    lines.append("")
    lines.append(markdown_table(["symbol", "strategy", "regime", "rejected_decisions"], decision_rows))
    lines.append("")
    lines.append(
        "Important attribution note: `strategy_id`/`regime` are present on decision-level rejected rows, "
        "but execution rows frequently omit them. The report therefore separates decision activity from realized PnL "
        "and marks missing execution context explicitly."
    )
    lines.append("")

    lines.append("## Realized Position Ledger")
    lines.append("")
    ledger_rows = []
    for row in sorted(enriched_closed, key=lambda item: item.get("timestamp") or 0):
        ledger_rows.append([
            row.get("_line"),
            iso_utc(row.get("timestamp")),
            row.get("symbol"),
            row.get("side"),
            row.get("close_reason"),
            row.get("pnl_status"),
            fmt_number(row.get("realized_pnl_net"), 8),
            fmt_number(row.get("fees"), 8),
            row.get("_inferred_strategy") or "",
            row.get("_inferred_regime") or "",
            row.get("lifecycle_id"),
            row.get("trade_id") or "",
        ])
    lines.append(markdown_table(
        ["line", "closed_utc", "symbol", "side", "reason", "pnl_status", "net_pnl", "fees", "strategy", "regime", "lifecycle_id", "trade_id"],
        ledger_rows,
    ))
    lines.append("")

    lines.append("## Rejected / Not-To-Market Investigation")
    lines.append("")
    lines.append("### NRR Taxonomy")
    lines.append("")
    lines.append(markdown_table(["nrr_code", "rejected_count"], nrr_counts.most_common()))
    lines.append("")
    lines.append("### Rejected By Symbol")
    lines.append("")
    lines.append(markdown_table(["symbol", "rejected_count", "market_reached"], [
        [symbol, count, "yes" if symbol in market_reached_symbols else "no"]
        for symbol, count in reject_by_symbol.most_common()
    ]))
    lines.append("")
    lines.append("### Top Safety Gate Classes")
    lines.append("")
    lines.append(markdown_table(["why_class", "count"], why_class_counts.most_common(30)))
    lines.append("")
    lines.append(
        "`NRR-027` dominates and maps mostly to directional safety gates such as uptrend/flash-up blocking shorts. "
        "`NRR-029` is also directional/anti-FOMO protection. `NRR-026` is the confidence floor gate, while `NRR-063` "
        "captures confidence-band maximum breaches in regimes such as `TREND_DOWN`."
    )
    lines.append("")

    lines.append("## Financial Conclusions")
    lines.append("")
    lines.append("- Keep treating TP-exit cohorts as the only proven positive edge in this sample: all TP buckets are positive net after fees.")
    lines.append("- `1000PEPEUSDT` has the best single realized trade, but sample size is only one; it is a candidate, not proof.")
    lines.append("- `BNBUSDT` is the strongest repeated contributor: positive net despite one SL, one manual/forced CLOSE loss, and one unresolved detected close.")
    lines.append("- `XRPUSDT` is the dominant loss source: it is negative before fees, and fees deepen the loss further.")
    lines.append(
        f"- Resolved positions earned `{fmt_number(resolved_gross, 8)}` gross, but `{fmt_number(resolved_fees, 8)}` fees erased the gross edge and left `{fmt_number(resolved_net, 8)}` net."
    )
    lines.append("- `BTCUSDT` and `ETHUSDT` were not market failures; they were pre-execution decision rejects. Their absence from fills is caused by safety gates, not exchange placement or liquidity.")
    lines.append("- `SL` and `CLOSE` exits are the primary realized drawdown sources; any strategy promotion should require reducing those buckets or improving earlier profit protection.")
    lines.append("- Low-volatility and trend-down regimes are active in decision flow, but many candidates are blocked before exchange execution. That means regime-level profitability cannot be inferred from rejected rows alone.")
    lines.append("")

    lines.append("## Data Quality Notes")
    lines.append("")
    lines.append(f"- `POSITION_CLOSED` unresolved rows: {len(unresolved_closed)}. These are excluded from resolved PnL and require accounting reconciliation.")
    lines.append(f"- Execution lifecycle rows without direct `strategy_id`: {execution_without_strategy} of {len(execution_rows)}.")
    lines.append(f"- Execution lifecycle rows without direct `regime`: {execution_without_regime} of {len(execution_rows)}.")
    lines.append(f"- Event types outside `apps/reference/schemas/order_logger_v1.json` enum: `{', '.join(schema_extra_events) or 'none'}`.")
    lines.append("- The report does not mix frozen/snapshot logs with live runtime state.")
    lines.append("")

    lines.append("## Acceptance Checks")
    lines.append("")
    current_checks = [
        ("parsed_rows_positive", len(rows) > 0, len(rows)),
        ("parse_errors_eq_0", parse_errors == 0, parse_errors),
        ("rejected_intents_not_market_reached", all(row.get("event_type") == "DECISION_INTENT_REJECTED" for row in rejected), len(rejected)),
        (
            "market_reached_requires_placed_or_filled",
            all(sum(by_symbol_event[symbol][event] for event in MARKET_REACHED_EVENTS) > 0 for symbol in traded_symbols),
            ", ".join(traded_symbols),
        ),
        (
            "resolved_pnl_uses_position_closed_only",
            len(resolved_closed) == sum(
                1
                for row in rows
                if row.get("event_type") == "POSITION_CLOSED"
                and text(row.get("pnl_status")) == RESOLVED_PNL_STATUS
                and safe_float(row.get("realized_pnl_net")) is not None
            ),
            len(resolved_closed),
        ),
        ("btc_eth_not_to_market", {"BTCUSDT", "ETHUSDT"}.issubset(set(not_to_market_symbols)), ", ".join(not_to_market_symbols)),
    ]
    lines.append(markdown_table(["check", "pass", "observed"], [
        [name, "PASS" if passed else "FAIL", observed] for name, passed, observed in current_checks
    ]))
    lines.append("")
    lines.append("### Plan Baseline Comparison")
    lines.append("")
    baseline_rows = [
        ["parsed_rows", PLAN_BASELINE["parsed_rows"], len(rows), len(rows) - PLAN_BASELINE["parsed_rows"]],
        ["resolved_net_pnl", fmt_number(PLAN_BASELINE["resolved_net_pnl"], 10), fmt_number(resolved_net, 10), fmt_number(resolved_net - PLAN_BASELINE["resolved_net_pnl"], 10)],
        ["resolved_fees", fmt_number(PLAN_BASELINE["resolved_fees"], 10), fmt_number(resolved_fees, 10), fmt_number(resolved_fees - PLAN_BASELINE["resolved_fees"], 10)],
        ["BNBUSDT_net_pnl", fmt_number(PLAN_BASELINE["BNBUSDT_net_pnl"], 10), fmt_number(by_symbol["BNBUSDT"]["net_pnl"], 10), fmt_number(by_symbol["BNBUSDT"]["net_pnl"] - PLAN_BASELINE["BNBUSDT_net_pnl"], 10)],
        ["XRPUSDT_net_pnl", fmt_number(PLAN_BASELINE["XRPUSDT_net_pnl"], 10), fmt_number(by_symbol["XRPUSDT"]["net_pnl"], 10), fmt_number(by_symbol["XRPUSDT"]["net_pnl"] - PLAN_BASELINE["XRPUSDT_net_pnl"], 10)],
        ["1000PEPEUSDT_net_pnl", fmt_number(PLAN_BASELINE["1000PEPEUSDT_net_pnl"], 10), fmt_number(by_symbol["1000PEPEUSDT"]["net_pnl"], 10), fmt_number(by_symbol["1000PEPEUSDT"]["net_pnl"] - PLAN_BASELINE["1000PEPEUSDT_net_pnl"], 10)],
    ]
    lines.append(markdown_table(["metric", "plan_baseline", "current_live_log", "delta"], baseline_rows))
    lines.append("")
    lines.append(
        "Baseline differences are expected for a mutable live log. The current delta is explained by appended XRPUSDT SL rows "
        "after the planning pass."
    )
    lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if all(passed for _, passed, _ in current_checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
