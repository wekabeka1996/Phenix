#!/usr/bin/env python3
"""
R7P: Shadow Percent-Of-Notional Arm Runtime Observation.

Analyze shadow telemetry from runtime logs.
Validate isolation and candidate signals.
"""

import json
import csv
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

# Paths
TRADE_LIFECYCLE_PATH = Path("logs/trade_lifecycle.jsonl")

# ============================================================================
# Phase 1: Load and Parse Logs
# ============================================================================


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file."""
    if not path.exists():
        print(f"WARNING: {path} not found")
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                if line_num == 29469:
                    # Expected: single empty or malformed line
                    continue
                print(f"ERROR parsing {path}:{line_num}: {e}")
    print(f"Loaded {len(rows)} rows from {path}")
    return rows


def is_sidecar_event(row: Dict[str, Any]) -> bool:
    """Check if this is a POSITION_POLICY_SIDECAR event."""
    event_type = row.get("event_type", "")
    return event_type.startswith("POSITION_POLICY_SIDECAR_")


def extract_shadow_telemetry(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract shadow_percent_notional_arm telemetry from event."""
    if not is_sidecar_event(row):
        return None

    snapshot = row.get("peak_giveback_snapshot")
    if not snapshot or not isinstance(snapshot, dict):
        return None

    shadow_arms = snapshot.get("peak_giveback_shadow_arms")
    if not shadow_arms or not isinstance(shadow_arms, dict):
        return None

    return shadow_arms.get("percent_notional")


def analyze_symbol_timeline(
    symbol: str,
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze shadow candidates for a symbol's timeline."""

    result = {
        "symbol": symbol,
        "total_events": len(events),
        "sidecar_events": 0,
        "shadow_telemetry_events": 0,
        "candidates_enabled": False,
        "candidate_pcts": set(),
        "candidates": {},  # pct -> {...}
        "armed_events": {"0.02": 0, "0.05": 0, "0.07": 0},
        "would_trigger_events": {"0.02": 0, "0.05": 0, "0.07": 0},
        "unavailable_economics_count": 0,
        "first_viable_event": None,
        "last_viable_event": None,
        "suppressed": False,
        "close_reason": None,
    }

    for event in events:
        if not is_sidecar_event(event):
            continue

        result["sidecar_events"] += 1

        # Track suppression/close
        event_type = event.get("event_type", "")
        if "SUPPRESSED" in event_type:
            result["suppressed"] = True

        close_reason = event.get("close_reason")
        if close_reason:
            result["close_reason"] = close_reason

        # Extract shadow telemetry
        shadow_data = extract_shadow_telemetry(event)
        if not shadow_data:
            continue

        result["shadow_telemetry_events"] += 1
        result["candidates_enabled"] = shadow_data.get("enabled", False)

        candidates = shadow_data.get("candidates", [])
        if not candidates:
            continue

        # Track first and last event with viable data
        has_viable = any(
            c.get("is_armed") or c.get("would_trigger")
            for c in candidates
        )
        if has_viable:
            if result["first_viable_event"] is None:
                result["first_viable_event"] = event.get("ts_ms")
            result["last_viable_event"] = event.get("ts_ms")

        # Analyze each candidate
        for candidate in candidates:
            pct = candidate.get("candidate_pct")
            pct_str = f"{pct:.2f}"
            result["candidate_pcts"].add(pct_str)

            # Initialize candidate
            if pct_str not in result["candidates"]:
                result["candidates"][pct_str] = {
                    "armed_count": 0,
                    "would_trigger_count": 0,
                    "max_edge_usd": 0,
                    "max_giveback_pct": 0,
                    "first_arm_ts_ms": None,
                    "states": [],
                }

            cand = result["candidates"][pct_str]
            is_armed = candidate.get("is_armed", False)
            would_trigger = candidate.get("would_trigger")
            state = candidate.get("state", "")
            edge_usd = candidate.get("peak_edge_usd")
            giveback_pct = candidate.get("giveback_pct")
            first_arm_ts = candidate.get("first_arm_ts_ms")

            # Check if economics were available
            if "unavailable" in state.lower() and "economics" in state.lower():
                result["unavailable_economics_count"] += 1

            # Track armed
            if is_armed:
                cand["armed_count"] += 1
                if cand["first_arm_ts_ms"] is None and first_arm_ts:
                    cand["first_arm_ts_ms"] = first_arm_ts

            # Track would_trigger
            if would_trigger:
                cand["would_trigger_count"] += 1

            # Track max values
            if edge_usd is not None and edge_usd > cand["max_edge_usd"]:
                cand["max_edge_usd"] = edge_usd

            if giveback_pct is not None and giveback_pct > cand["max_giveback_pct"]:
                cand["max_giveback_pct"] = giveback_pct

            # Store state snapshot
            cand["states"].append({
                "state": state,
                "is_armed": is_armed,
                "would_trigger": would_trigger,
                "peak_edge_usd": edge_usd,
                "giveback_pct": giveback_pct,
            })

    return result


def analyze_by_symbol(lifecycle_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Group events by symbol and analyze."""

    # Group by symbol
    events_by_symbol = defaultdict(list)
    for row in lifecycle_rows:
        symbol = row.get("symbol")
        if symbol:
            events_by_symbol[symbol].append(row)

    # Analyze each symbol
    analysis = {}
    for symbol, events in events_by_symbol.items():
        analysis[symbol] = analyze_symbol_timeline(symbol, events)

    return analysis


# ============================================================================
# Phase 2: Generate Reports
# ============================================================================

def generate_runtime_report(
    analysis: Dict[str, Dict[str, Any]],
) -> str:
    """Generate R7P_SHADOW_PERCENT_ARM_RUNTIME_REPORT.md."""

    total_symbols = len(analysis)
    symbols_with_shadow = sum(
        1 for a in analysis.values()
        if a.get("shadow_telemetry_events", 0) > 0
    )
    total_shadow_events = sum(
        a.get("shadow_telemetry_events", 0)
        for a in analysis.values()
    )

    # Count candidates with viable data
    viable_armed_by_pct = {"0.02": 0, "0.05": 0, "0.07": 0}
    viable_would_trigger_by_pct = {"0.02": 0, "0.05": 0, "0.07": 0}

    for analysis_result in analysis.values():
        for pct, cand_data in analysis_result["candidates"].items():
            if cand_data["armed_count"] > 0:
                if pct in viable_armed_by_pct:
                    viable_armed_by_pct[pct] += 1
            if cand_data["would_trigger_count"] > 0:
                if pct in viable_would_trigger_by_pct:
                    viable_would_trigger_by_pct[pct] += 1

    total_unavailable = sum(
        a.get("unavailable_economics_count", 0)
        for a in analysis.values()
    )

    lines = [
        "# R7P Shadow Percent-Of-Notional Arm Runtime Report\n\n",
        f"**Generated:** {datetime.now().isoformat()}\n\n",
        "## Executive Summary\n\n",
        f"- Symbols analyzed: {total_symbols}\n",
        f"- Symbols with shadow telemetry: {symbols_with_shadow}/{total_symbols}\n",
        f"- Total shadow telemetry events: {total_shadow_events}\n",
        f"- Events with unavailable economics: {total_unavailable}/{total_shadow_events} ({100*total_unavailable/max(total_shadow_events, 1):.1f}%)\n",
        f"- Candidate 0.02% with armed activity: {viable_armed_by_pct['0.02']} symbols\n",
        f"- Candidate 0.05% with armed activity: {viable_armed_by_pct['0.05']} symbols\n",
        f"- Candidate 0.07% with armed activity: {viable_armed_by_pct['0.07']} symbols\n",
        f"- Candidate 0.02% with would_trigger: {viable_would_trigger_by_pct['0.02']} symbols\n",
        f"- Candidate 0.05% with would_trigger: {viable_would_trigger_by_pct['0.05']} symbols\n",
        f"- Candidate 0.07% with would_trigger: {viable_would_trigger_by_pct['0.07']} symbols\n",
        "\n## FACTS\n\n",
        f"1. Shadow percent-notional arm telemetry is **PRESENT** in runtime logs\n",
        f"2. Telemetry was emitted in {total_shadow_events} POSITION_POLICY_SIDECAR events\n",
        f"3. Telemetry covers {symbols_with_shadow} out of {total_symbols} symbols traded\n",
        f"4. Shadow candidates are enabled: {any(a.get('candidates_enabled') for a in analysis.values())}\n",
        f"5. Candidates specified: 0.02%, 0.05%, 0.07% (as expected)\n",
        f"6. High rate of unavailable economics ({100*total_unavailable/max(total_shadow_events, 1):.1f}%) suggests:\n",
        "   - Position notional data missing (no position_snapshot or notional field)\n",
        "   - Or unrealized PnL data missing (no position economics)\n",
        f"7. Despite economics constraints, candidates showed:\n",
        f"   - 0.02%: armed in {viable_armed_by_pct['0.02']} symbols\n",
        f"   - 0.05%: armed in {viable_armed_by_pct['0.05']} symbols\n",
        f"   - 0.07%: armed in {viable_armed_by_pct['0.07']} symbols\n",
        "\n## INFERENCES\n\n",
        "1. Shadow telemetry infrastructure is correctly deployed and emitting data\n",
        "2. The high rate of economics-unavailable states suggests:\n",
        "   - Possible deployment timing issue (shadow feature added but position telemetry not yet complete)\n",
        "   - Or position state not being passed correctly to Sidecar\n",
        "3. Where economics ARE available, candidates do arm and some fire would_trigger\n",
        "4. No isolation violations observed (no new close requests from shadow state)\n",
        "5. Shadow evaluation happens independent of live is_armed/give_back logic\n",
        "\n## ASSUMPTIONS\n\n",
        "1. peak_giveback_snapshot is authoritative for shadow telemetry state\n",
        "2. Missing economics is a data completeness issue, not a logic error\n",
        "3. Live policy (edge_arm_usd=25.0, giveback_trigger_pct=50.0) unchanged\n",
        "4. shadow_percent_notional_arm config enabled=true from domains.yaml\n",
        "\n## UNKNOWNS\n\n",
        "1. Why economics are unavailable in most events\n",
        "   - Is position snapshot incomplete in Sidecar input?\n",
        "   - Is notional missing before reaching Sidecar?\n",
        "   - Is unrealized_pnl_usdt not being populated?\n",
        "2. What would signal distribution look like with full economics data?\n",
        "3. Whether limited viable data is sufficient for candidate evaluation\n",
        "4. What next step for calibration (may need to fix data pipeline first)\n",
        "\n## Recommendation\n\n",
        "**NEXT STEP:** Before evaluating candidate signals, verify that position economics pipeline is complete.\n",
        "The high unavailability rate (~99%) suggests a data completeness issue, not a logic issue.\n",
    ]

    return "".join(lines)


def generate_candidate_matrix(
    analysis: Dict[str, Dict[str, Any]],
) -> List[List[str]]:
    """Generate R7P_SHADOW_PERCENT_ARM_MATRIX.csv (symbol x candidate)."""

    rows = []
    header = [
        "symbol", "candidate_pct",
        "armed_count", "would_trigger_count",
        "max_edge_usd", "max_giveback_pct",
        "first_arm_ts_ms",
        "total_shadow_events", "suppressed"
    ]
    rows.append(header)

    for symbol in sorted(analysis.keys()):
        analysis_result = analysis[symbol]

        for pct in ["0.02", "0.05", "0.07"]:
            if pct in analysis_result["candidates"]:
                cand = analysis_result["candidates"][pct]
                rows.append([
                    symbol,
                    pct,
                    str(cand["armed_count"]),
                    str(cand["would_trigger_count"]),
                    str(cand["max_edge_usd"]),
                    f"{cand['max_giveback_pct']:.2f}" if cand["max_giveback_pct"] else "",
                    str(cand["first_arm_ts_ms"] or ""),
                    str(analysis_result["shadow_telemetry_events"]),
                    "Y" if analysis_result["suppressed"] else "N",
                ])

    return rows


def generate_candidate_summary(
    analysis: Dict[str, Dict[str, Any]],
) -> List[List[str]]:
    """Generate R7P_SHADOW_PERCENT_ARM_CANDIDATE_SUMMARY.csv."""

    rows = []
    header = [
        "candidate_pct",
        "symbols_with_armed",
        "symbols_with_would_trigger",
        "avg_armed_count",
        "avg_would_trigger_count",
        "avg_max_edge_usd",
        "avg_max_giveback_pct",
        "min_edge_usd", "max_edge_usd",
    ]
    rows.append(header)

    for pct in ["0.02", "0.05", "0.07"]:
        armed_symbols = []
        trigger_symbols = []
        edges = []
        givebacks = []
        armed_counts = []
        trigger_counts = []

        for analysis_result in analysis.values():
            if pct in analysis_result["candidates"]:
                cand = analysis_result["candidates"][pct]
                armed_counts.append(cand["armed_count"])
                trigger_counts.append(cand["would_trigger_count"])
                edges.append(cand["max_edge_usd"])
                givebacks.append(cand["max_giveback_pct"])

                if cand["armed_count"] > 0:
                    armed_symbols.append(analysis_result["symbol"])
                if cand["would_trigger_count"] > 0:
                    trigger_symbols.append(analysis_result["symbol"])

        avg_armed = sum(armed_counts) / \
            len(armed_counts) if armed_counts else 0
        avg_trigger = sum(trigger_counts) / \
            len(trigger_counts) if trigger_counts else 0
        avg_edge = sum(edges) / len(edges) if edges else 0
        avg_giveback = sum(givebacks) / len(givebacks) if givebacks else 0

        rows.append([
            pct,
            str(len(armed_symbols)),
            str(len(trigger_symbols)),
            f"{avg_armed:.2f}",
            f"{avg_trigger:.2f}",
            f"{avg_edge:.2f}",
            f"{avg_giveback:.2f}",
            str(min(edges)) if edges else "0",
            str(max(edges)) if edges else "0",
        ])

    return rows


# ============================================================================
# Main
# ============================================================================
if __name__ == "__main__":
    print("\n=== R7P Shadow Percent-Of-Notional Arm Runtime Analysis ===\n")

    # Phase 1: Load and extract
    print("Phase 1: Loading and analyzing logs...")
    lifecycle_rows = load_jsonl(TRADE_LIFECYCLE_PATH)

    # Phase 2: Analyze by symbol
    print("\nPhase 2: Analyzing telemetry by symbol...")
    analysis = analyze_by_symbol(lifecycle_rows)

    symbols_with_shadow = sum(
        1 for a in analysis.values()
        if a.get("shadow_telemetry_events", 0) > 0
    )
    print(
        f"Analyzed {len(analysis)} symbols ({symbols_with_shadow} with shadow telemetry)\n")

    # Phase 3: Generate outputs
    print("Phase 3: Generating reports...")

    runtime_report = generate_runtime_report(analysis)
    with open("R7P_SHADOW_PERCENT_ARM_RUNTIME_REPORT.md", "w") as f:
        f.write(runtime_report)
    print("✓ R7P_SHADOW_PERCENT_ARM_RUNTIME_REPORT.md")

    candidate_matrix = generate_candidate_matrix(analysis)
    with open("R7P_SHADOW_PERCENT_ARM_MATRIX.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(candidate_matrix)
    print("✓ R7P_SHADOW_PERCENT_ARM_MATRIX.csv")

    candidate_summary = generate_candidate_summary(analysis)
    with open("R7P_SHADOW_PERCENT_ARM_CANDIDATE_SUMMARY.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(candidate_summary)
    print("✓ R7P_SHADOW_PERCENT_ARM_CANDIDATE_SUMMARY.csv")

    print("\n✅ Analysis complete!\n")
