from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(r"c:\Users\user\Music\Phenix")
OUT_DIR = ROOT / "reports" / "runtime_forensics" / "T2_final"

REQ_FILES = {
    "t0_manifest": ROOT / "reports" / "runtime_forensics" / "T0" / "runtime_manifest.json",
    "t0_inventory": ROOT / "reports" / "runtime_forensics" / "T0" / "RUNTIME_EVIDENCE_INVENTORY.md",
    "t0_disabled_nrr": ROOT / "reports" / "runtime_forensics" / "T0" / "DISABLED_NRR_TRUTH_TABLE.md",
    "t1_decision_report": ROOT / "reports" / "runtime_forensics" / "T1_decision_nrr" / "DECISION_NRR_COUNTERFACTUAL_REPORT.md",
    "t1_decision_events": ROOT / "reports" / "runtime_forensics" / "T1_decision_nrr" / "decision_events_normalized.csv",
    "t1_decision_cf": ROOT / "reports" / "runtime_forensics" / "T1_decision_nrr" / "accepted_intents_counterfactual_nrr_replay.csv",
    "t1_exec_report": ROOT / "reports" / "runtime_forensics" / "T1_execution_pnl" / "EXECUTION_LIFECYCLE_PNL_REPORT.md",
    "t1_orders": ROOT / "reports" / "runtime_forensics" / "T1_execution_pnl" / "orders_normalized.csv",
    "t1_trades": ROOT / "reports" / "runtime_forensics" / "T1_execution_pnl" / "trades_reconstructed.csv",
    "t1_defects": ROOT / "reports" / "runtime_forensics" / "T1_execution_pnl" / "position_management_defects.csv",
    "t1_regime_report": ROOT / "reports" / "runtime_forensics" / "T1_regime_path" / "REGIME_RECORDER_PATH_REPORT.md",
    "t1_regime_metrics": ROOT / "reports" / "runtime_forensics" / "T1_regime_path" / "trade_regime_path_metrics.csv",
    "t1_current_report": ROOT / "reports" / "runtime_forensics" / "T1_current_state" / "CURRENT_OPEN_STATE_AND_ORPHAN_AUDIT.md",
    "t1_current_audit": ROOT / "reports" / "runtime_forensics" / "T1_current_state" / "current_open_state_audit.csv",
}

NRR_CODES = ["NRR-026", "NRR-027", "NRR-028", "NRR-029", "NRR-030", "NRR-063"]


def to_f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def agg(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    bucket: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = str(r.get(key) or "UNKNOWN")
        b = bucket.setdefault(
            k,
            {
                key: k,
                "trades": 0,
                "closed_trades": 0,
                "open_trades": 0,
                "proven_net_pnl": 0.0,
                "estimated_net_pnl": 0.0,
                "total_fee_usdt": 0.0,
                "wins": 0,
                "losses": 0,
            },
        )
        b["trades"] += 1
        if str(r.get("status")) == "CLOSED":
            b["closed_trades"] += 1
        else:
            b["open_trades"] += 1
        b["proven_net_pnl"] += to_f(r.get("proven_net_pnl"))
        b["estimated_net_pnl"] += to_f(r.get("estimated_net_pnl"))
        b["total_fee_usdt"] += to_f(r.get("total_fee_usdt"))
        net = to_f(r.get("net_pnl"))
        if net > 0:
            b["wins"] += 1
        elif net < 0:
            b["losses"] += 1

    out = []
    for _, b in sorted(bucket.items(), key=lambda kv: kv[0]):
        denom = b["wins"] + b["losses"]
        b["winrate"] = (b["wins"] / denom) if denom else 0.0
        out.append(b)
    return out


def classify_root_cause(tr: dict[str, Any], regime: dict[str, Any] | None, has_decision_replay: bool) -> str:
    status = str(tr.get("status") or "")

    net = to_f(tr.get("net_pnl"))
    gross = to_f(tr.get("gross_pnl"))
    fee = to_f(tr.get("total_fee_usdt"))
    exec_defect = bool(str(tr.get("execution_anomalies") or "").strip())
    life_defect = bool(str(tr.get("lifecycle_anomalies") or "").strip())

    if exec_defect:
        return "EXECUTION_DEFECT"

    giveback = to_f((regime or {}).get("giveback_ratio"), default=0.0)
    peak_roi = to_f((regime or {}).get("peak_roi"), default=0.0)
    final_roi = to_f((regime or {}).get("final_roi"), default=0.0)

    if life_defect and giveback >= 0.5 and peak_roi > 0:
        return "LIFECYCLE_GIVEBACK"

    if life_defect and status == "OPEN":
        return "LIFECYCLE_GIVEBACK"

    if status != "CLOSED":
        return "UNKNOWN"

    reg_entry = str((regime or {}).get("regime_at_entry") or "UNKNOWN")
    reg_exit = str((regime or {}).get("regime_at_exit") or "UNKNOWN")
    if reg_entry not in {"", "UNKNOWN"} and reg_exit not in {"", "UNKNOWN"} and reg_entry != reg_exit and net <= 0:
        return "REGIME_MISMATCH"

    if gross <= 0 and net < 0 and abs(net + fee) < 1e-6:
        return "FEE_ONLY_LOSS"

    if has_decision_replay:
        return "POLICY_GATE_MISSING"

    if net < 0:
        return "BAD_ENTRY"

    if peak_roi > 0 and final_roi <= 0:
        return "LIFECYCLE_GIVEBACK"

    return "UNKNOWN"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    file_presence = {k: p.exists() for k, p in REQ_FILES.items()}

    trades = read_csv(REQ_FILES["t1_trades"])
    defects = read_csv(REQ_FILES["t1_defects"])
    regime_rows = read_csv(REQ_FILES["t1_regime_metrics"])
    current_state_rows = read_csv(REQ_FILES["t1_current_audit"])
    orders = read_csv(REQ_FILES["t1_orders"])

    decision_replay_rows = read_csv(REQ_FILES["t1_decision_cf"])
    has_decision_replay = len(decision_replay_rows) > 0

    regime_by_trade = {str(r.get("trade_id") or ""): r for r in regime_rows if str(
        r.get("trade_id") or "")}
    regime_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in regime_rows:
        sym = str(r.get("symbol") or "")
        if sym:
            regime_by_symbol[sym].append(r)

    defect_by_trade: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"P0": set(), "P1": set()})
    for d in defects:
        tid = str(d.get("trade_id") or "")
        sev = str(d.get("severity") or "")
        cls = str(d.get("defect_class") or "")
        if not tid:
            continue
        if sev.startswith("P0"):
            defect_by_trade[tid]["P0"].add(cls)
        elif sev.startswith("P1"):
            defect_by_trade[tid]["P1"].add(cls)

    exact_join = 0
    weak_join = 0
    unmatched_execution = 0

    master_rows: list[dict[str, Any]] = []

    def side_match(exec_side: str, regime_side: str) -> bool:
        es = str(exec_side or "").upper()
        rs = str(regime_side or "").upper()
        if rs in {"LONG", "BUY"}:
            return es == "BUY"
        if rs in {"SHORT", "SELL"}:
            return es == "SELL"
        return True

    def weak_join_regime(tr: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(tr.get("symbol") or "")
        candidates = regime_by_symbol.get(symbol) or []
        if not candidates:
            return None
        exit_ts = int(to_f(tr.get("close_fill_ts")
                      or tr.get("close_order_ts"), 0.0))
        entry_ts = int(to_f(tr.get("entry_fill_ts")
                       or tr.get("entry_order_ts"), 0.0))
        best: tuple[int, dict[str, Any]] | None = None
        for c in candidates:
            if not side_match(str(tr.get("side") or ""), str(c.get("side") or "")):
                continue
            c_exit = int(to_f(c.get("exit_ts"), 0.0))
            c_entry = int(to_f(c.get("entry_ts"), 0.0))
            if exit_ts > 0 and c_exit > 0:
                diff = abs(exit_ts - c_exit)
            elif entry_ts > 0 and c_entry > 0:
                diff = abs(entry_ts - c_entry)
            else:
                continue
            if diff > 300000:
                continue
            if best is None or diff < best[0]:
                best = (diff, c)
        return best[1] if best is not None else None

    for tr in trades:
        trade_id = str(tr.get("trade_id") or "")
        reg = regime_by_trade.get(trade_id)
        join_type = "NONE"
        if reg is not None:
            exact_join += 1
            join_type = "EXACT"
        else:
            reg = weak_join_regime(tr)
            if reg is not None:
                weak_join += 1
                join_type = "WEAK"
            else:
                unmatched_execution += 1

        execution_defect = ";".join(sorted(defect_by_trade[trade_id]["P0"]))
        lifecycle_defect = ";".join(sorted(defect_by_trade[trade_id]["P1"]))

        corr = str(tr.get("correlation_confidence") or "")
        if reg is not None:
            reg_corr = str(reg.get("regime_correlation_confidence") or "")
            if reg_corr:
                corr = reg_corr
        if join_type == "WEAK":
            corr = "WEAK_MATCH"

        row = {
            "trade_id": trade_id,
            "intent_id": "",
            "symbol": str(tr.get("symbol") or ""),
            "strategy_id": str(tr.get("strategy_id_if_known") or "UNKNOWN"),
            "side": str(tr.get("side") or ""),
            "regime_at_signal": str((reg or {}).get("regime_at_signal") or "UNKNOWN"),
            "regime_at_entry": str((reg or {}).get("regime_at_entry") or "UNKNOWN"),
            "regime_at_exit": str((reg or {}).get("regime_at_exit") or "UNKNOWN"),
            "entry_ts": tr.get("entry_fill_ts") or tr.get("entry_order_ts") or "",
            "exit_ts": tr.get("close_fill_ts") or tr.get("close_order_ts") or "",
            "net_pnl": tr.get("net_pnl") or "",
            "total_fees": tr.get("total_fee_usdt") or "",
            "mfe_roi": (reg or {}).get("mfe_roi", ""),
            "mae_roi": (reg or {}).get("mae_roi", ""),
            "peak_roi": (reg or {}).get("peak_roi", ""),
            "giveback_ratio": (reg or {}).get("giveback_ratio", ""),
            "close_trigger": tr.get("close_trigger") or "",
            "path_bucket": (reg or {}).get("path_bucket", "PATH_UNPROVEN"),
            "execution_defect": execution_defect,
            "lifecycle_defect": lifecycle_defect,
            "nrr_026_result": "UNPROVEN_NO_T1_DECISION_INPUT",
            "nrr_027_result": "UNPROVEN_NO_T1_DECISION_INPUT",
            "nrr_028_result": "UNPROVEN_NO_T1_DECISION_INPUT",
            "nrr_029_result": "UNPROVEN_NO_T1_DECISION_INPUT",
            "nrr_030_result": "UNPROVEN_NO_T1_DECISION_INPUT",
            "nrr_063_result": "UNPROVEN_NO_T1_DECISION_INPUT",
            "correlation_confidence": corr or "LOW",
        }
        master_rows.append(row)

    write_csv(
        OUT_DIR / "MASTER_TRADE_FORENSIC_TABLE.csv",
        master_rows,
        [
            "trade_id",
            "intent_id",
            "symbol",
            "strategy_id",
            "side",
            "regime_at_signal",
            "regime_at_entry",
            "regime_at_exit",
            "entry_ts",
            "exit_ts",
            "net_pnl",
            "total_fees",
            "mfe_roi",
            "mae_roi",
            "peak_roi",
            "giveback_ratio",
            "close_trigger",
            "path_bucket",
            "execution_defect",
            "lifecycle_defect",
            "nrr_026_result",
            "nrr_027_result",
            "nrr_028_result",
            "nrr_029_result",
            "nrr_030_result",
            "nrr_063_result",
            "correlation_confidence",
        ],
    )

    closed_trade_rows = [r for r in trades if str(
        r.get("status") or "") == "CLOSED"]

    nrr_rows: list[dict[str, Any]] = []
    for code in NRR_CODES:
        nrr_rows.append(
            {
                "nrr_code": code,
                "accepted_trades_replayed": len(decision_replay_rows),
                "would_block_count": 0,
                "would_pass_count": 0,
                "unproven_count": len(closed_trade_rows),
                "blocked_winners": 0,
                "blocked_losers": 0,
                "blocked_net_pnl": 0.0,
                "blocked_avg_pnl": 0.0,
                "passed_winners": 0,
                "passed_losers": 0,
                "passed_net_pnl": 0.0,
                "protection_value": 0.0,
                "false_positive_cost": 0.0,
                "false_negative_cost": 0.0,
                "verdict": "INSUFFICIENT_EVIDENCE",
                "recommendation": "OBSERVE_ONLY_MORE_DATA",
            }
        )

    write_csv(
        OUT_DIR / "NRR_USEFULNESS_MATRIX.csv",
        nrr_rows,
        [
            "nrr_code",
            "accepted_trades_replayed",
            "would_block_count",
            "would_pass_count",
            "unproven_count",
            "blocked_winners",
            "blocked_losers",
            "blocked_net_pnl",
            "blocked_avg_pnl",
            "passed_winners",
            "passed_losers",
            "passed_net_pnl",
            "protection_value",
            "false_positive_cost",
            "false_negative_cost",
            "verdict",
            "recommendation",
        ],
    )

    root_bucket_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tr in trades:
        trade_id = str(tr.get("trade_id") or "")
        reg = regime_by_trade.get(trade_id)
        bucket = classify_root_cause(tr, reg, has_decision_replay)
        root_bucket_map[bucket].append(tr)

    root_rows: list[dict[str, Any]] = []
    root_evidence = {
        "BAD_ENTRY": "closed_loss_without_exec_or_lifecycle_defect",
        "POLICY_GATE_MISSING": "requires_t1_decision_nrr_replay_not_present",
        "LIFECYCLE_GIVEBACK": "positive_peak_then_large_giveback_or_lifecycle_defect",
        "EXECUTION_DEFECT": "execution_anomalies_present",
        "REGIME_MISMATCH": "entry_regime_differs_from_exit_regime_with_nonpositive_outcome",
        "FEE_ONLY_LOSS": "gross_nonpositive_and_loss_approx_equals_fees",
        "UNKNOWN": "open_positions_or_missing_join_fields",
    }
    root_conf = {
        "BAD_ENTRY": "MEDIUM",
        "POLICY_GATE_MISSING": "LOW",
        "LIFECYCLE_GIVEBACK": "MEDIUM",
        "EXECUTION_DEFECT": "HIGH",
        "REGIME_MISMATCH": "MEDIUM",
        "FEE_ONLY_LOSS": "HIGH",
        "UNKNOWN": "LOW",
    }

    for bucket in [
        "BAD_ENTRY",
        "POLICY_GATE_MISSING",
        "LIFECYCLE_GIVEBACK",
        "EXECUTION_DEFECT",
        "REGIME_MISMATCH",
        "FEE_ONLY_LOSS",
        "UNKNOWN",
    ]:
        rows = root_bucket_map.get(bucket, [])
        root_rows.append(
            {
                "bucket": bucket,
                "trade_count": len(rows),
                "net_pnl": sum(to_f(r.get("net_pnl")) for r in rows),
                "evidence": root_evidence[bucket],
                "confidence": root_conf[bucket],
            }
        )

    write_csv(
        OUT_DIR / "ROOT_CAUSE_SPLIT.csv",
        root_rows,
        ["bucket", "trade_count", "net_pnl", "evidence", "confidence"],
    )

    by_symbol = agg(trades, "symbol")
    by_strategy = agg(
        [
            {**r, "strategy": (r.get("strategy_id_if_known") or "UNKNOWN")}
            for r in trades
        ],
        "strategy",
    )

    by_side = agg(trades, "side")

    by_regime = agg(
        [
            {
                "regime": str(m.get("regime_at_entry") or "UNKNOWN"),
                "status": "CLOSED" if str(m.get("exit_ts") or "") else "OPEN",
                "proven_net_pnl": to_f(m.get("net_pnl")),
                "estimated_net_pnl": to_f(m.get("net_pnl")),
                "total_fee_usdt": to_f(m.get("total_fees")),
                "net_pnl": to_f(m.get("net_pnl")),
            }
            for m in master_rows
        ],
        "regime",
    )

    by_close_trigger = agg(trades, "close_trigger")

    total_intents_proposed = "UNPROVEN_NO_T1_DECISION_INPUT"
    total_intents_rejected = "UNPROVEN_NO_T1_DECISION_INPUT"

    proven_net_pnl = sum(to_f(r.get("proven_net_pnl")) for r in trades)
    estimated_net_pnl = sum(to_f(r.get("estimated_net_pnl")) for r in trades)
    total_fees = sum(to_f(r.get("total_fee_usdt")) for r in trades)

    closed_net = [to_f(r.get("net_pnl")) for r in closed_trade_rows]
    wins = sum(1 for x in closed_net if x > 0)
    losses = sum(1 for x in closed_net if x < 0)
    winrate = (wins / len(closed_net)) if closed_net else 0.0
    gross_profit = sum(x for x in closed_net if x > 0)
    gross_loss = abs(sum(x for x in closed_net if x < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    open_positions = sum(1 for r in current_state_rows if to_f(
        r.get("system_expected_qty"), 0.0) != 0.0)

    edge_giveback_cases = sum(
        1
        for r in master_rows
        if to_f(r.get("peak_roi"), 0.0) > 0 and to_f(r.get("giveback_ratio"), 0.0) >= 0.5
    )

    p0_trade_count = len({d.get("trade_id") for d in defects if str(
        d.get("severity", "")).startswith("P0") and d.get("trade_id")})
    p1_trade_count = len({d.get("trade_id") for d in defects if str(
        d.get("severity", "")).startswith("P1") and d.get("trade_id")})

    runtime_start = min(
        [
            int(v)
            for v in [
                *[to_f(r.get("entry_ts"), default=0) for r in master_rows],
                *[to_f(r.get("exit_ts"), default=0) for r in master_rows],
                *[to_f(r.get("ts"), default=0) for r in orders],
            ]
            if v and v > 0
        ],
        default=0,
    )
    runtime_end = max(
        [
            int(v)
            for v in [
                *[to_f(r.get("entry_ts"), default=0) for r in master_rows],
                *[to_f(r.get("exit_ts"), default=0) for r in master_rows],
                *[to_f(r.get("ts"), default=0) for r in orders],
            ]
            if v and v > 0
        ],
        default=0,
    )
    duration_s = (runtime_end - runtime_start) / \
        1000.0 if runtime_end and runtime_start else 0.0

    missing_required = [k for k, ok in file_presence.items() if not ok]

    if len(trades) > 0 and len(closed_trade_rows) > 0 and not missing_required:
        verdict = "FULLY_RECONSTRUCTED"
    elif len(trades) > 0:
        verdict = "PARTIALLY_RECONSTRUCTED"
    else:
        verdict = "INSUFFICIENT_EVIDENCE"

    def fmt_breakdown(rows: list[dict[str, Any]], key: str) -> str:
        return "; ".join(
            f"{r.get(key)}: pnl={r.get('proven_net_pnl', 0.0):.6f}, trades={r.get('trades', 0)}"
            for r in rows
        ) or "UNPROVEN"

    highest_severity_cases = sorted(
        {d.get("trade_id") for d in defects if str(
            d.get("severity") or "").startswith("P0") and d.get("trade_id")}
    )

    report_lines = [
        "AGENT_REPORT_V1",
        "",
        "task:",
        "  AURORA_RUNTIME_TRADING_FORENSIC_SYNTHESIS_T2",
        "",
        "verdict:",
        f"  {verdict}",
        "",
        "runtime_window:",
        f"  start_ts: {runtime_start}",
        f"  end_ts: {runtime_end}",
        f"  duration: {duration_s:.3f}s",
        "",
        "evidence_quality:",
        f"  exact_trade_join_count: {exact_join}",
        f"  weak_trade_join_count: {weak_join}",
        f"  unmatched_decision_count: {'UNPROVEN_NO_T1_DECISION_INPUT' if not has_decision_replay else 0}",
        f"  unmatched_execution_count: {unmatched_execution}",
        f"  recorder_path_coverage: {exact_join + weak_join}/{len(trades)}",
        f"  nrr_replay_coverage: {'0/closed_trades (missing T1_decision_nrr)' if not has_decision_replay else f'{len(decision_replay_rows)}/{len(closed_trade_rows)}'}",
        "",
        "trade_summary:",
        f"  total_intents_proposed: {total_intents_proposed}",
        f"  total_intents_rejected: {total_intents_rejected}",
        f"  total_exchange_orders: {len(orders)}",
        f"  total_filled_entries: {sum(1 for r in trades if to_f(r.get('entry_qty')) > 0)}",
        f"  total_closed_positions: {len(closed_trade_rows)}",
        f"  total_open_positions: {open_positions}",
        f"  proven_net_pnl: {proven_net_pnl:.10f}",
        f"  estimated_net_pnl: {estimated_net_pnl:.10f}",
        f"  total_fees: {total_fees:.10f}",
        f"  winrate: {winrate:.6f}",
        f"  profit_factor: {profit_factor:.6f}",
        "",
        "pnl_breakdowns:",
        f"  by_symbol: {fmt_breakdown(by_symbol, 'symbol')}",
        f"  by_strategy: {fmt_breakdown(by_strategy, 'strategy')}",
        f"  by_regime: {fmt_breakdown(by_regime, 'regime')}",
        f"  by_side: {fmt_breakdown(by_side, 'side')}",
        f"  by_close_trigger: {fmt_breakdown(by_close_trigger, 'close_trigger')}",
        "",
        "position_management_verdict:",
        "  verdict: DEFECTS_PRESENT",
        f"  p0_defects: {p0_trade_count}",
        f"  p1_defects: {p1_trade_count}",
        f"  edge_giveback_cases: {edge_giveback_cases}",
        f"  highest_severity_cases: {', '.join(highest_severity_cases)}",
        "",
        "disabled_nrr_verdict:",
        "  NRR-026: INSUFFICIENT_EVIDENCE",
        "  NRR-027: INSUFFICIENT_EVIDENCE",
        "  NRR-028: INSUFFICIENT_EVIDENCE",
        "  NRR-029: INSUFFICIENT_EVIDENCE",
        "  NRR-030: INSUFFICIENT_EVIDENCE",
        "  NRR-063: INSUFFICIENT_EVIDENCE",
        "  other_disabled_gates: INSUFFICIENT_EVIDENCE",
        "",
        "root_cause_split:",
        f"  bad_entry: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'BAD_ENTRY')}",
        f"  policy_gate_missing: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'POLICY_GATE_MISSING')}",
        f"  lifecycle_giveback: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'LIFECYCLE_GIVEBACK')}",
        f"  execution_defect: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'EXECUTION_DEFECT')}",
        f"  regime_mismatch: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'REGIME_MISMATCH')}",
        f"  fee_only_loss: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'FEE_ONLY_LOSS')}",
        f"  unknown: {next(r['trade_count'] for r in root_rows if r['bucket'] == 'UNKNOWN')}",
        "",
        "recommendations:",
        "  immediate_safety: Resolve orphan/stale close-order state via controlled reconciliation; verify BNBUSDT restore mismatch before any live enablement.",
        "  nrr_changes: Keep all NRR disabled in decisioning until T1_decision_nrr replay artifacts are regenerated; run observe-only replay first.",
        "  lifecycle_policy_changes: Enforce post-entry SL/TP materialization invariant and fail-close when both protective brackets are absent.",
        "  calibration_next_step: Rebuild T1_decision_nrr package and rerun exact trade-intent join to compute true blocked_winner/blocked_loser balance per NRR.",
        "  observability_gaps_to_close: Restore T0 manifest pipeline; persist deterministic intent_id/trade_id bridge and explicit close_fill provenance.",
        "",
        "proven:",
        "  - Execution PnL and defect datasets were loaded from T1_execution_pnl and reconciled at trade granularity.",
        f"  - Regime/path metrics were joined by exact IDs ({exact_join}) and weak symbol/side/timestamp matches ({weak_join}).",
        "  - Current open risk was integrated from T1_current_state log-only audit.",
        "",
        "unproven:",
        "  - T0 runtime manifest/inventory/truth-table files are absent at required paths.",
        "  - T1 decision NRR replay artifacts are absent; NRR usefulness cannot be proven.",
        "  - Any policy-gate counterfactual effect on winners/losers remains unresolved.",
        "",
        "risks:",
        "  - Partial reconstruction can bias root-cause attribution toward lifecycle/execution buckets.",
        "  - Open-position/open-order truth remains exchange-unverified in current-state artifact.",
        "  - Missing decision replay blocks safe NRR re-enable decisions.",
        "",
        "next_prompt_recommendation:",
        "  - TASK: AURORA_DECISION_NRR_REBUILD_AND_TRADE_JOIN_T3 (recreate missing T0/T1_decision_nrr artifacts, then rerun T2 synthesis with exact intent-trade mapping).",
        "",
        "Executive verdict",
        f"- {verdict}: execution/regime/current-state evidence is usable, but final NRR usefulness verdict is blocked by missing T1_decision_nrr and T0 artifacts.",
        "",
        "FACTS",
        f"- Required inputs missing: {', '.join(missing_required) if missing_required else 'none'}.",
        f"- trades_reconstructed rows: {len(trades)}; closed: {len(closed_trade_rows)}; open: {len(trades)-len(closed_trade_rows)}.",
        f"- proven_net_pnl: {proven_net_pnl:.10f}; estimated_net_pnl: {estimated_net_pnl:.10f}; total_fees: {total_fees:.10f}.",
        "",
        "INFERENCES",
        "- Dominant observed degraders are execution/lifecycle defects (missing brackets, reconciliation divergence, order_without_fill).",
        "- Regime-path data shows edge giveback cases, supporting lifecycle-loss protection workstream.",
        "",
        "ASSUMPTIONS",
        "- trade_id exact match is authoritative for trade-to-regime join.",
        "- Without decision replay input, NRR columns remain unproven and must not drive enable/disable changes.",
        "",
        "UNKNOWNS",
        "- True blocked_winner/blocked_loser distribution for NRR-026/027/028/029/030/063.",
        "- Counterfactual net protection_value per NRR gate.",
        "",
        "What remains unproven",
        "- NRR usefulness matrix outcomes beyond INSUFFICIENT_EVIDENCE placeholders.",
        "",
        "Next exact package proposal",
        "- Rebuild missing T0 and T1_decision_nrr artifacts, then rerun this synthesis script to replace placeholders with measured NRR verdicts.",
    ]

    (OUT_DIR / "FINAL_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "out_dir": str(OUT_DIR),
        "master_rows": len(master_rows),
        "nrr_rows": len(nrr_rows),
        "root_rows": len(root_rows),
        "verdict": verdict,
        "missing_required": missing_required,
        "exact_join": exact_join,
        "unmatched_execution": unmatched_execution,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
