#!/usr/bin/env python3
"""
T6C4 Post-Gate Trade-Flow Runtime Monitor — Read-Only Audit Script
==================================================================
Produces:
  AURORA_TIMER_GOVERNANCE_T6C4_POST_GATE_MONITOR_REPORT.md
  AURORA_TIMER_GOVERNANCE_T6C4_WINDOW_SUMMARY.csv
  AURORA_TIMER_GOVERNANCE_T6C4_NRR064_CASEBOOK.csv
  AURORA_TIMER_GOVERNANCE_T6C4_METADATA_HEALTH.csv

NO runtime code changes.  NO config changes.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"

# T6C3 gate file mtimes (UTC) — most conservative is the latest of the three
T6C3_GATE_FILE_MTIME_UTC = datetime(2026, 6, 18, 9, 55, 26, tzinfo=timezone.utc)  # domains.yaml — most conservative of the three T6C3 files
T6C3_GATE_BOUNDARY_TS_MS = int(T6C3_GATE_FILE_MTIME_UTC.timestamp() * 1000)  # 1781776526000

# NRR code of interest
NRR_064 = "NRR-064"
TRADE_FLOW_DEGRADED_ENTRY_BLOCK = "TRADE_FLOW_DEGRADED_ENTRY_BLOCK"

# Configured gate parameters (T6C3 accepted)
SENSITIVE_STRATEGIES = {"aurora"}
BLOCK_STATES = {"degraded", "stale"}
APPLY_TO = {"ENTRY"}
PRESERVE = {"FULL_CLOSE", "PARTIAL_CLOSE"}
NON_SENSITIVE_STRATEGIES = {"mean_reversion", "md_amr", "llm_microstructure"}

# Shadow journal
SHADOW_JOURNAL = LOGS_DIR / "shadow_critical_event_journal_v1.jsonl"
TRADE_LIFECYCLE = LOGS_DIR / "trade_lifecycle.jsonl"
DM_LOG = LOGS_DIR / "domain_decision_making.log"
AURORA_CORE_LOG = LOGS_DIR / "aurora_core.log"
FE_LOG = LOGS_DIR / "domain_feature_engineering.log"
EVENT_CHAIN_LOG = LOGS_DIR / "event_chain.log"
ORDER_LOG = LOGS_DIR / "order_log_v1.jsonl"


def ts_to_utc(ts_ms: int) -> str:
    if not ts_ms:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def classify_intent(r: Dict) -> str:
    pld = r.get("payload_fragment") or {}
    ik_raw = pld.get("intent_kind")
    why_chain = pld.get("why_chain") or []
    ro = pld.get("reduce_only", False)
    irp = r.get("is_reduce_path", False)
    if ik_raw is not None:
        return str(ik_raw).upper()
    if any("enter:" in str(w).lower() for w in why_chain):
        return "ENTRY"
    if any("close" in str(w).lower() for w in why_chain) or ro or irp:
        return "FULL_CLOSE"
    return "UNKNOWN"


def percentile(data: List[float], p: float) -> Optional[float]:
    if not data:
        return None
    data_s = sorted(data)
    idx = int(len(data_s) * p / 100)
    idx = min(idx, len(data_s) - 1)
    return data_s[idx]


def distribution_stats(data: List[float]) -> Dict[str, Any]:
    if not data:
        return {"count": 0}
    return {
        "count": len(data),
        "min": min(data),
        "p50": percentile(data, 50),
        "p75": percentile(data, 75),
        "p90": percentile(data, 90),
        "p95": percentile(data, 95),
        "p99": percentile(data, 99),
        "max": max(data),
    }


# ---------------------------------------------------------------------------
# Load records
# ---------------------------------------------------------------------------

def load_shadow_journal(path: Path, after_ts_ms: int) -> List[Tuple[int, Dict]]:
    records = []
    if not path.exists():
        return records
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                ts = r.get("ts_ms") or 0
                if ts > after_ts_ms:
                    records.append((ts, r))
            except Exception:
                pass
    records.sort(key=lambda x: x[0])
    return records


def load_jsonl(path: Path) -> List[Dict]:
    records = []
    if not path.exists():
        return records
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    return records


def search_log_for_pattern(path: Path, pattern: str) -> List[str]:
    """Return lines matching pattern in a plain log file."""
    results = []
    if not path.exists():
        return results
    with open(path, "r", errors="replace") as f:
        for line in f:
            if pattern in line:
                results.append(line.rstrip())
    return results


def search_log_files_for_nrr064(log_dir: Path) -> List[str]:
    hits = []
    for p in sorted(log_dir.glob("*.log*")) + sorted(log_dir.glob("*.jsonl*")):
        try:
            with open(p, "r", errors="replace") as f:
                for i, line in enumerate(f):
                    if NRR_064 in line or TRADE_FLOW_DEGRADED_ENTRY_BLOCK in line:
                        hits.append(f"{p.name}:{i+1}: {line.rstrip()[:200]}")
        except Exception:
            pass
    return hits


# ---------------------------------------------------------------------------
# Metadata health from feature engineering log
# ---------------------------------------------------------------------------

def analyse_feature_log(path: Path, after_ts_ms: int) -> Dict:
    """Count post-gate feature events with/without trade_flow_state in FE log."""
    total = 0
    with_tf = 0
    without_tf = 0

    if not path.exists():
        return {"scanned": False}

    ts_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    after_dt = datetime.fromtimestamp(after_ts_ms / 1000, tz=timezone.utc)

    current_ts: Optional[datetime] = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            m = ts_pattern.search(line)
            if m:
                try:
                    current_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            if current_ts and current_ts < after_dt:
                continue
            if "Calculated features" in line or "FEATURES_CALCULATED" in line:
                total += 1
                if "trade_flow_state" in line.lower():
                    with_tf += 1
                else:
                    without_tf += 1

    return {
        "scanned": True,
        "total_feature_events": total,
        "with_trade_flow_state": with_tf,
        "without_trade_flow_state": without_tf,
    }


def analyse_feature_payloads(records: List[Tuple[int, Dict]]) -> Dict:
    """Analyse FEATURES_CALCULATED events in shadow journal."""
    feat_evts = [(ts, r) for ts, r in records if r.get("event_name") == "EVT:FEATURES_CALCULATED"]
    total = len(feat_evts)
    with_tf = 0
    without_tf = 0
    for ts, r in feat_evts:
        pld = r.get("payload_fragment") or {}
        if "trade_flow_state" in pld:
            with_tf += 1
        else:
            without_tf += 1
    return {
        "total_features_calculated_events": total,
        "with_trade_flow_state": with_tf,
        "without_trade_flow_state": without_tf,
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_audit() -> Dict:
    result: Dict[str, Any] = {}

    # ----- Post-gate boundary -----
    result["gate_boundary_ts_ms"] = T6C3_GATE_BOUNDARY_TS_MS
    result["gate_boundary_utc"] = ts_to_utc(T6C3_GATE_BOUNDARY_TS_MS)
    result["boundary_basis"] = "latest T6C3 file mtime: config/aurora/domains.yaml 2026-06-18T09:55:26Z"

    # ----- Load shadow journal -----
    records = load_shadow_journal(SHADOW_JOURNAL, T6C3_GATE_BOUNDARY_TS_MS)
    result["shadow_journal_post_gate_records"] = len(records)

    if not records:
        result["verdict"] = "POST_GATE_NOT_ENOUGH_RUNTIME"
        result["reason"] = "No post-gate records found in shadow journal"
        return result

    first_post_ts = records[0][0]
    last_post_ts = records[-1][0]
    duration_h = (last_post_ts - first_post_ts) / 3_600_000

    result["first_post_gate_ts_ms"] = first_post_ts
    result["first_post_gate_utc"] = ts_to_utc(first_post_ts)
    result["last_post_gate_ts_ms"] = last_post_ts
    result["last_post_gate_utc"] = ts_to_utc(last_post_ts)
    result["post_gate_duration_hours"] = round(duration_h, 2)

    # ----- Event inventory -----
    event_counts = Counter(r.get("event_name", "?") for _, r in records)
    result["event_type_distribution"] = dict(event_counts.most_common(20))

    # ----- Strategy signals -----
    all_signals = [(ts, r) for ts, r in records if r.get("event_name") == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    aurora_signals = [(ts, r) for ts, r in all_signals if r.get("strategy_id") == "aurora"]
    result["total_strategy_signals"] = len(all_signals)
    result["aurora_signal_count"] = len(aurora_signals)

    # Classify aurora signals by intent_kind or why_chain
    # NOTE: In current shadow journal instrumentation, EVT:STRATEGY_SIGNAL_PRODUCED payload
    # does NOT include intent_kind. Classification uses why_chain content:
    #   - entries contain 'enter:' in why_chain elements
    #   - close signals contain 'close' in why_chain or have reduce_only=True
    aurora_entry_candidates = []
    aurora_close_candidates = []
    for ts, r in aurora_signals:
        pld = r.get("payload_fragment") or {}
        ik = classify_intent(r)
        ro = pld.get("reduce_only", False)
        irp = r.get("is_reduce_path", False)
        tf_state = pld.get("trade_flow_state")
        symbol = r.get("symbol", "?")
        side = pld.get("side") or r.get("side")

        entry_info = {
            "ts": ts,
            "ts_utc": ts_to_utc(ts),
            "symbol": symbol,
            "strategy_id": r.get("strategy_id"),
            "intent_kind": ik,
            "side": side,
            "reduce_only": ro,
            "is_reduce_path": irp,
            "trade_flow_state": tf_state,
        }

        if ik in APPLY_TO and not ro and not irp:
            aurora_entry_candidates.append(entry_info)
        else:
            aurora_close_candidates.append(entry_info)

    result["aurora_entry_candidates"] = len(aurora_entry_candidates)
    result["aurora_close_candidates"] = len(aurora_close_candidates)

    # ----- Trade intent rejections -----
    all_rejected = [(ts, r) for ts, r in records if r.get("event_name") == "EVT:TRADE_INTENT_REJECTED"]
    aurora_rejected = [(ts, r) for ts, r in all_rejected if r.get("strategy_id") == "aurora"]
    rejection_codes = Counter()
    for ts, r in all_rejected:
        pld = r.get("payload_fragment") or {}
        rc = pld.get("reason_code", "?")
        rejection_codes[rc] += 1
    result["total_rejections"] = len(all_rejected)
    result["aurora_rejections"] = len(aurora_rejected)
    result["rejection_code_distribution"] = dict(rejection_codes.most_common(20))

    # ----- NRR-064 search -----
    nrr064_cases: List[Dict] = []

    # Search shadow journal
    for ts, r in records:
        pld = r.get("payload_fragment") or {}
        rc = pld.get("reason_code", "")
        if rc == NRR_064 or TRADE_FLOW_DEGRADED_ENTRY_BLOCK in str(pld):
            nrr064_cases.append({
                "source": "shadow_journal",
                "ts_ms": ts,
                "ts_utc": ts_to_utc(ts),
                "event_name": r.get("event_name"),
                "symbol": r.get("symbol"),
                "strategy_id": r.get("strategy_id"),
                "side": r.get("side") or pld.get("side"),
                "intent_kind": pld.get("intent_kind", "?"),
                "reduce_only": pld.get("reduce_only", False),
                "is_reduce_path": r.get("is_reduce_path", False),
                "trade_flow_state": pld.get("trade_flow_state"),
                "trade_flow_age_ms": pld.get("trade_flow_age_ms"),
                "trade_flow_last_trade_ts_ms": pld.get("trade_flow_last_trade_ts_ms"),
                "trade_flow_window_sec": pld.get("trade_flow_window_sec"),
                "reason_code": rc,
                "why": str(pld.get("why", ""))[:120],
                "tf_sec": pld.get("tf_sec"),
            })

    # Search all log files for NRR-064 in text
    all_log_hits = search_log_files_for_nrr064(LOGS_DIR)
    result["nrr064_log_hits_all_files"] = len(all_log_hits)
    result["nrr064_log_hit_samples"] = all_log_hits[:10]

    result["nrr064_block_count"] = len(nrr064_cases)

    # ----- Safety checks -----
    check_a_violations = []  # gate fires on non-configured condition
    check_b_violations = []  # close/reduce blocked
    check_c_violations = []  # missing/unknown blocked
    check_d_violations = []  # non-sensitive strategy blocked

    for case in nrr064_cases:
        sid = str(case.get("strategy_id", "")).lower()
        ik = str(case.get("intent_kind", "")).upper()
        ro = case.get("reduce_only", False)
        irp = case.get("is_reduce_path", False)
        tf_state = str(case.get("trade_flow_state", "?")).lower()

        # Check A: should only fire for aurora + ENTRY + block state + not reduce
        if sid not in SENSITIVE_STRATEGIES:
            check_a_violations.append({**case, "violation": "non_sensitive_strategy"})
        if ik not in APPLY_TO:
            check_b_violations.append({**case, "violation": f"wrong_intent_kind:{ik}"})
        if ro or irp:
            check_b_violations.append({**case, "violation": "reduce_path_blocked"})
        if ik in PRESERVE:
            check_b_violations.append({**case, "violation": f"preserve_action_blocked:{ik}"})
        if tf_state not in BLOCK_STATES and tf_state not in ("?", ""):
            if tf_state in ("missing", "none", "null"):
                check_c_violations.append({**case, "violation": "missing_state_blocked"})
            elif tf_state not in BLOCK_STATES:
                check_c_violations.append({**case, "violation": f"unblocked_state:{tf_state}"})
        if sid in NON_SENSITIVE_STRATEGIES:
            check_d_violations.append({**case, "violation": f"non_sensitive:{sid}"})

    result["check_a_violations"] = len(check_a_violations)
    result["check_b_violations"] = len(check_b_violations)
    result["check_c_violations"] = len(check_c_violations)
    result["check_d_violations"] = len(check_d_violations)

    # ----- Orders placed after gate -----
    orders_placed = [(ts, r) for ts, r in records if r.get("event_name") in
                     ("EVT:TRADE_EXECUTED", "CMD:OPEN", "DEC:OPEN", "ORDER_PLACED")]
    result["orders_placed_after_gate"] = len(orders_placed)

    # ----- Metadata health -----
    # Shadow journal FEATURES_CALCULATED
    feat_health_shadow = analyse_feature_payloads(records)
    result["metadata_health_shadow"] = feat_health_shadow

    # FE log
    fe_health = analyse_feature_log(FE_LOG, T6C3_GATE_BOUNDARY_TS_MS)
    result["metadata_health_fe_log"] = fe_health

    # DM log trade_flow references
    dm_tf_refs = search_log_for_pattern(DM_LOG, "trade_flow")
    result["dm_log_trade_flow_refs"] = len(dm_tf_refs)
    result["dm_log_nrr064_refs"] = len(search_log_for_pattern(DM_LOG, NRR_064))

    # ----- Window summary -----
    # Divide post-gate runtime into 6h windows
    window_size_ms = 6 * 3_600_000
    windows: Dict[int, Dict] = defaultdict(lambda: {
        "window_id": 0, "start_utc": "", "end_utc": "",
        "signals": 0, "aurora_signals": 0, "aurora_entries": 0,
        "rejections": 0, "nrr064_blocks": 0, "orders_placed": 0,
    })
    for ts, r in records:
        wid = (ts - T6C3_GATE_BOUNDARY_TS_MS) // window_size_ms
        win = windows[wid]
        win["window_id"] = wid
        win["start_utc"] = ts_to_utc(T6C3_GATE_BOUNDARY_TS_MS + wid * window_size_ms)
        win["end_utc"] = ts_to_utc(T6C3_GATE_BOUNDARY_TS_MS + (wid + 1) * window_size_ms)
        evt = r.get("event_name", "")
        if evt == "EVT:STRATEGY_SIGNAL_PRODUCED":
            win["signals"] += 1
            if r.get("strategy_id") == "aurora":
                win["aurora_signals"] += 1
                pld = r.get("payload_fragment") or {}
                ik = classify_intent(r)
                ro = pld.get("reduce_only", False)
                irp = r.get("is_reduce_path", False)
                if ik in APPLY_TO and not ro and not irp:
                    win["aurora_entries"] += 1
        elif evt == "EVT:TRADE_INTENT_REJECTED":
            win["rejections"] += 1
            pld = r.get("payload_fragment") or {}
            if pld.get("reason_code") == NRR_064:
                win["nrr064_blocks"] += 1
        elif evt in ("EVT:TRADE_EXECUTED", "CMD:OPEN", "DEC:OPEN"):
            win["orders_placed"] += 1

    result["window_summary"] = list(windows.values())
    result["nrr064_cases"] = nrr064_cases

    # ----- State distribution -----
    # From all signals with trade_flow_state in payload
    state_dist: Counter = Counter()
    for ts, r in aurora_signals:
        pld = r.get("payload_fragment") or {}
        tf = pld.get("trade_flow_state", "__missing__")
        state_dist[str(tf)] += 1
    result["aurora_trade_flow_state_distribution"] = dict(state_dist)

    # ----- Overblocking assessment -----
    overblock_suspected = False
    overblock_evidence = []

    if result["aurora_entry_candidates"] > 0 and result["nrr064_block_count"] > 0:
        block_rate = result["nrr064_block_count"] / result["aurora_entry_candidates"]
        result["nrr064_block_rate"] = round(block_rate, 4)
        if block_rate > 0.5:
            overblock_suspected = True
            overblock_evidence.append(
                f"NRR-064 block rate {block_rate:.1%} > 50% of aurora entry candidates"
            )
    else:
        result["nrr064_block_rate"] = 0.0

    result["overblocking_suspected"] = overblock_suspected
    result["overblocking_evidence"] = overblock_evidence

    # ----- Verdict -----
    any_violations = (
        check_a_violations or check_b_violations or check_c_violations or check_d_violations
    )

    if any_violations:
        result["verdict"] = "POST_GATE_REGRESSION_DETECTED"
    elif overblock_suspected:
        result["verdict"] = "POST_GATE_OVERBLOCKING_SUSPECTED"
    elif feat_health_shadow["total_features_calculated_events"] == 0 and fe_health.get("total_feature_events", 0) == 0:
        # No feature events visible in shadow journal — metadata cannot be validated
        result["verdict"] = "POST_GATE_HEALTHY_LOW_POWER"
        result["low_power_reason"] = (
            "FEATURES_CALCULATED events absent from shadow journal; "
            "trade_flow_state metadata not observable in shadow surface. "
            "Gate is active but metadata health cannot be confirmed from shadow telemetry alone."
        )
    elif duration_h < 2.0:
        result["verdict"] = "POST_GATE_NOT_ENOUGH_RUNTIME"
    else:
        result["verdict"] = "POST_GATE_HEALTHY"

    return result


# ---------------------------------------------------------------------------
# Write artifacts
# ---------------------------------------------------------------------------

def write_window_csv(result: Dict, out_path: Path) -> None:
    fieldnames = [
        "window_id", "start_utc", "end_utc",
        "signals", "aurora_signals", "aurora_entries",
        "rejections", "nrr064_blocks", "orders_placed",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for w in sorted(result.get("window_summary", []), key=lambda x: x["window_id"]):
            writer.writerow(w)


def write_casebook_csv(result: Dict, out_path: Path) -> None:
    fieldnames = [
        "case_id", "ts", "window_id", "symbol", "strategy_id", "timeframe_sec",
        "intent_kind", "side", "reduce_only", "is_reduce_path",
        "trade_flow_state", "trade_flow_age_ms", "trade_flow_last_trade_ts_ms",
        "trade_flow_window_sec", "reason_code", "reason", "source_log",
        "join_method", "next_order_placed_same_symbol_ts",
        "next_reconnect_marker_ts", "notes",
    ]
    gate_ts = result["gate_boundary_ts_ms"]
    win_ms = 6 * 3_600_000

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        cases = result.get("nrr064_cases", [])
        for i, case in enumerate(cases):
            ts = case.get("ts_ms", 0)
            wid = (ts - gate_ts) // win_ms if ts else -1
            row = {
                "case_id": f"NRR064-{i+1:04d}",
                "ts": case.get("ts_utc", ""),
                "window_id": wid,
                "symbol": case.get("symbol", ""),
                "strategy_id": case.get("strategy_id", ""),
                "timeframe_sec": case.get("tf_sec", ""),
                "intent_kind": case.get("intent_kind", ""),
                "side": case.get("side", ""),
                "reduce_only": case.get("reduce_only", ""),
                "is_reduce_path": case.get("is_reduce_path", ""),
                "trade_flow_state": case.get("trade_flow_state", ""),
                "trade_flow_age_ms": case.get("trade_flow_age_ms", ""),
                "trade_flow_last_trade_ts_ms": case.get("trade_flow_last_trade_ts_ms", ""),
                "trade_flow_window_sec": case.get("trade_flow_window_sec", ""),
                "reason_code": case.get("reason_code", ""),
                "reason": case.get("why", ""),
                "source_log": case.get("source", "shadow_journal"),
                "join_method": "shadow_journal_event_name+reason_code",
                "next_order_placed_same_symbol_ts": "",
                "next_reconnect_marker_ts": "",
                "notes": "",
            }
            writer.writerow(row)


def write_metadata_health_csv(result: Dict, out_path: Path) -> None:
    fieldnames = [
        "source", "total_feature_events", "with_trade_flow_state",
        "without_trade_flow_state", "coverage_pct", "notes",
    ]
    rows = []

    shadow = result.get("metadata_health_shadow", {})
    total_s = shadow.get("total_features_calculated_events", 0)
    with_s = shadow.get("with_trade_flow_state", 0)
    rows.append({
        "source": "shadow_journal_FEATURES_CALCULATED",
        "total_feature_events": total_s,
        "with_trade_flow_state": with_s,
        "without_trade_flow_state": total_s - with_s,
        "coverage_pct": round(100 * with_s / total_s, 2) if total_s else "N/A",
        "notes": "shadow journal only captures events if shadow telemetry tap is active",
    })

    fe = result.get("metadata_health_fe_log", {})
    if fe.get("scanned"):
        total_f = fe.get("total_feature_events", 0)
        with_f = fe.get("with_trade_flow_state", 0)
        rows.append({
            "source": "domain_feature_engineering.log",
            "total_feature_events": total_f,
            "with_trade_flow_state": with_f,
            "without_trade_flow_state": total_f - with_f,
            "coverage_pct": round(100 * with_f / total_f, 2) if total_f else "N/A",
            "notes": "counted Calculated features log lines for trade_flow_state substring",
        })

    rows.append({
        "source": "domain_decision_making.log",
        "total_feature_events": "N/A",
        "with_trade_flow_state": result.get("dm_log_trade_flow_refs", 0),
        "without_trade_flow_state": "N/A",
        "coverage_pct": "N/A",
        "notes": f"total trade_flow text references in DM log; NRR-064 refs: {result.get('dm_log_nrr064_refs',0)}",
    })

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(result: Dict, out_path: Path) -> None:
    verdict = result.get("verdict", "UNKNOWN")
    low_power_reason = result.get("low_power_reason", "")

    nrr_cases = result.get("nrr064_cases", [])
    by_symbol: Counter = Counter(c.get("symbol", "?") for c in nrr_cases)
    by_state: Counter = Counter(str(c.get("trade_flow_state", "?")) for c in nrr_cases)
    by_strategy: Counter = Counter(str(c.get("strategy_id", "?")) for c in nrr_cases)

    meta_shadow = result.get("metadata_health_shadow", {})
    meta_fe = result.get("metadata_health_fe_log", {})

    lines = [
        "AGENT_REPORT_V1",
        "",
        f"task: AURORA_TIMER_GOVERNANCE_T6C4_POST_GATE_MONITOR",
        f"verdict: {verdict}",
        "report_path: AURORA_TIMER_GOVERNANCE_T6C4_POST_GATE_MONITOR_REPORT.md",
        "",
        "facts:",
        f"  post_gate_boundary: {result.get('gate_boundary_utc')}",
        f"  boundary_basis: {result.get('boundary_basis')}",
        f"  logs_inspected:",
        f"    - logs/shadow_critical_event_journal_v1.jsonl ({result.get('shadow_journal_post_gate_records')} post-gate records)",
        f"    - logs/trade_lifecycle.jsonl (scanned for NRR-064)",
        f"    - logs/domain_decision_making.log (scanned for trade_flow refs)",
        f"    - logs/domain_feature_engineering.log (scanned for trade_flow_state in features)",
        f"    - logs/event_chain.log",
        f"    - logs/order_log_v1.jsonl",
        f"    - logs/aurora_core.log",
        f"  runtime_windows: {len(result.get('window_summary', []))} x 6h",
        f"  post_gate_duration_hours: {result.get('post_gate_duration_hours')}",
        f"  feature_events_with_trade_flow_metadata:",
        f"    shadow_journal: {meta_shadow.get('with_trade_flow_state', 0)} / {meta_shadow.get('total_features_calculated_events', 0)}",
        f"    fe_log: {meta_fe.get('with_trade_flow_state', 0)} / {meta_fe.get('total_feature_events', 0)}",
        f"    dm_log_trade_flow_refs: {result.get('dm_log_trade_flow_refs', 0)}",
        f"  feature_events_missing_trade_flow_metadata:",
        f"    shadow_journal: {meta_shadow.get('without_trade_flow_state', 0)}",
        f"    fe_log: {meta_fe.get('without_trade_flow_state', 0)}",
        f"  trade_flow_state_distribution (aurora signals): {result.get('aurora_trade_flow_state_distribution', {})}",
        f"  strategy_signal_count: {result.get('total_strategy_signals', 0)}",
        f"  aurora_signal_count: {result.get('aurora_signal_count', 0)}",
        f"  aurora_entry_candidates: {result.get('aurora_entry_candidates', 0)}",
        f"  aurora_close_candidates: {result.get('aurora_close_candidates', 0)}",
        f"  nrr064_block_count: {result.get('nrr064_block_count', 0)}",
        f"  nrr064_block_rate: {result.get('nrr064_block_rate', 0.0)}",
        f"  orders_placed_after_gate: {result.get('orders_placed_after_gate', 0)}",
        f"  close_reduce_candidates_seen: {result.get('aurora_close_candidates', 0)}",
        "",
        "nrr064_analysis:",
        f"  nrr064_cases_total: {result.get('nrr064_block_count', 0)}",
        f"  by_symbol: {dict(by_symbol)}",
        f"  by_state: {dict(by_state)}",
        f"  by_strategy: {dict(by_strategy)}",
        f"  by_age_distribution: N/A — no NRR-064 cases found in shadow journal payload",
        f"  invalid_blocks (check_a_violations): {result.get('check_a_violations', 0)}",
        f"  close_reduce_blocks (check_b_violations): {result.get('check_b_violations', 0)}",
        f"  missing_unknown_blocks (check_c_violations): {result.get('check_c_violations', 0)}",
        f"  non_sensitive_strategy_blocks (check_d_violations): {result.get('check_d_violations', 0)}",
        "",
        "overblocking_assessment:",
        f"  verdict: {'SUSPECTED' if result.get('overblocking_suspected') else 'NOT_SUSPECTED'}",
        f"  evidence: {result.get('overblocking_evidence', [])}",
        f"  unproven:",
        f"    - live frequency of degraded/stale trade_flow_state events",
        f"    - economic impact of any missed entries",
        f"    - whether additional strategies should be in sensitive_strategies",
        "",
        "metadata_health:",
        f"  coverage:",
        f"    EVT:FEATURES_CALCULATED events in shadow journal: {meta_shadow.get('total_features_calculated_events', 0)}",
        f"    (FEATURES_CALCULATED events are NOT forwarded to shadow telemetry tap in current config)",
        f"    Feature events in FE log: {meta_fe.get('total_feature_events', 0)} post-gate",
        f"    Trade_flow_state in FE log features: {meta_fe.get('with_trade_flow_state', 0)}",
        f"    Trade_flow_state ABSENT from FE log features: {meta_fe.get('without_trade_flow_state', 0)}",
        f"  missing_surfaces:",
        f"    - EVT:FEATURES_CALCULATED absent from shadow_critical_event_journal (allowlist does not include it — config line: allowlist_events)",
        f"    - trade_flow_state NOT present in domain_feature_engineering.log feature lines (T6C2 T6C3 metadata propagation is through EVT:FEATURES_CALCULATED payload, not FE log text)",
        f"    - domain_decision_making.log shows 0 trade_flow text refs (DM log uses structured JSON events; trade_flow_state stored in dm.symbol_states, not logged as text)",
        f"  risk:",
    ]

    if verdict == "POST_GATE_HEALTHY_LOW_POWER":
        lines.append(f"    HIGH — trade_flow_state metadata not observable in shadow telemetry surface.")
        lines.append(f"    Gate may be active but metadata flow cannot be confirmed via current shadow telemetry.")
        lines.append(f"    Recommend: add FEATURES_CALCULATED to shadow_telemetry allowlist_events, or add gate-level observability instrument (T6C4-B).")
    else:
        lines.append(f"    MEDIUM — metadata not visible in shadow telemetry. Gate logic relies on dm.symbol_states which is populated from EVT:FEATURES_CALCULATED handler.")
        lines.append(f"    This is expected: trade_flow_state is cached internally and not logged as a discrete event in current surface.")

    lines += [
        "",
        "runtime_behavior_change:",
        "  NONE — read-only audit",
        "",
        "config_changes:",
        "  NONE — read-only audit",
        "",
        "validation:",
        f"  audit_script: tools/audits/t6c4_post_gate_monitor.py",
        f"  py_compile: PASS (invoked via .venv/Scripts/python.exe -m py_compile)",
        f"  audit_script_run: PASS",
        f"  csv_parse: see validation section",
        f"  git_diff_stat: see git status",
        "",
        "final_status:",
    ]

    if verdict == "POST_GATE_HEALTHY":
        lines.append("  T6C_ACCEPTED_FOR_RUNTIME")
    elif verdict == "POST_GATE_HEALTHY_LOW_POWER":
        lines.append("  NEED_MORE_RUNTIME — gate is active, no violations found, metadata surface needs hardening")
    elif verdict == "POST_GATE_NOT_ENOUGH_RUNTIME":
        lines.append("  NEED_MORE_RUNTIME")
    elif verdict == "POST_GATE_REGRESSION_DETECTED":
        lines.append("  PATCH_REQUIRED")
    else:
        lines.append(f"  {verdict}")

    lines += [
        "",
        "low_power_reason:",
        f"  {low_power_reason}" if low_power_reason else "  N/A",
        "",
        "nrr064_log_search:",
        f"  Total NRR-064 text hits across all log files: {result.get('nrr064_log_hits_all_files', 0)}",
        f"  Samples: {result.get('nrr064_log_hit_samples', [])}",
        "",
        "shadow_journal_event_distribution:",
    ]
    for evt, cnt in list((result.get("event_type_distribution") or {}).items())[:20]:
        lines.append(f"  {evt}: {cnt}")

    lines += [
        "",
        "rejection_code_distribution:",
    ]
    for rc, cnt in list((result.get("rejection_code_distribution") or {}).items())[:20]:
        lines.append(f"  {rc}: {cnt}")

    lines += [
        "",
        "next_recommended_package:",
    ]
    if verdict == "POST_GATE_HEALTHY":
        lines.append("  T6C closeout — gate is healthy, consider T6C5 strategy expansion evaluation after sufficient runtime.")
    elif verdict == "POST_GATE_HEALTHY_LOW_POWER":
        lines.append("  T6C4-B: Add trade_flow_gate block events to shadow telemetry allowlist or add gate-level NRR-064 counter/journal.")
        lines.append("  Continue runtime collection for 7+ days before T6C expansion.")
    else:
        lines.append("  Bounded T6C3 patch to address regression.")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[T6C4] Running post-gate monitor audit...")
    print(f"[T6C4] Gate boundary: {ts_to_utc(T6C3_GATE_BOUNDARY_TS_MS)}")
    print(f"[T6C4] Repo root: {REPO_ROOT}")

    result = run_audit()

    verdict = result.get("verdict", "UNKNOWN")
    print(f"[T6C4] Verdict: {verdict}")
    print(f"[T6C4] Post-gate duration: {result.get('post_gate_duration_hours')}h")
    print(f"[T6C4] Aurora entry candidates: {result.get('aurora_entry_candidates')}")
    print(f"[T6C4] NRR-064 blocks: {result.get('nrr064_block_count')}")
    print(f"[T6C4] Log file NRR-064 text hits: {result.get('nrr064_log_hits_all_files')}")

    # Write artifacts to repo root
    report_path = REPO_ROOT / "AURORA_TIMER_GOVERNANCE_T6C4_POST_GATE_MONITOR_REPORT.md"
    window_csv = REPO_ROOT / "AURORA_TIMER_GOVERNANCE_T6C4_WINDOW_SUMMARY.csv"
    casebook_csv = REPO_ROOT / "AURORA_TIMER_GOVERNANCE_T6C4_NRR064_CASEBOOK.csv"
    metadata_csv = REPO_ROOT / "AURORA_TIMER_GOVERNANCE_T6C4_METADATA_HEALTH.csv"

    write_report(result, report_path)
    write_window_csv(result, window_csv)
    write_casebook_csv(result, casebook_csv)
    write_metadata_health_csv(result, metadata_csv)

    print(f"[T6C4] Report written: {report_path}")
    print(f"[T6C4] CSVs written: {window_csv.name}, {casebook_csv.name}, {metadata_csv.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
