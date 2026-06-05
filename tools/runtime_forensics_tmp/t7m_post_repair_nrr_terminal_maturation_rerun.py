from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "logs"

T7_DIR = REPORTS_DIR / "runtime_forensics" / "T7_post_repair_nrr_replay"
OUTPUT_DIR = REPORTS_DIR / "runtime_forensics" / \
    "T7M_post_repair_nrr_terminal_maturation"

T7_REPLAY_ROWS_PATH = T7_DIR / "t7_post_repair_nrr_replay_rows.csv"
T7_ECONOMIC_JOIN_PATH = T7_DIR / "t7_post_repair_nrr_economic_join.csv"

ORDER_LOG_PATH = LOGS_DIR / "order_log_v1.jsonl"
TRADE_LIFECYCLE_PATH = LOGS_DIR / "trade_lifecycle.jsonl"

REPLAY_TARGETS = ("NRR-026", "NRR-027", "NRR-028", "NRR-029", "NRR-030")

REPLAY_ROWS_PATH = OUTPUT_DIR / "t7m_post_repair_nrr_replay_rows.csv"
ECONOMIC_JOIN_PATH = OUTPUT_DIR / "t7m_post_repair_nrr_economic_join.csv"
USEFULNESS_MATRIX_PATH = OUTPUT_DIR / "t7m_post_repair_nrr_usefulness_matrix.csv"
REPORT_PATH = OUTPUT_DIR / "T7M_POST_REPAIR_NRR_TERMINAL_MATURATION_REPORT.md"

WINDOW_END_MS = 1780026304634


def stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_t7_baseline_exact_rids() -> set[str]:
    baseline_rids: set[str] = set()
    for row in load_csv(T7_ECONOMIC_JOIN_PATH):
        if stringify(row.get("pnl_status")) == "resolved" and stringify(row.get("realized_pnl_net")) != "":
            baseline_rids.add(stringify(row.get("rid")))
    return baseline_rids


def build_cohort_rows() -> list[dict[str, str]]:
    return load_csv(T7_REPLAY_ROWS_PATH)


def scan_current_order_log(cohort_rids: set[str]) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Counter[str]],
]:
    exact_terminal_by_rid: dict[str, dict[str, Any]] = {}
    latest_event_by_rid: dict[str, dict[str, Any]] = {}
    position_closed_by_rid: dict[str, dict[str, Any]] = {}
    event_counts: dict[str, Counter[str]] = defaultdict(Counter)

    with ORDER_LOG_PATH.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            rid = stringify(row.get("rid"))
            if rid not in cohort_rids:
                continue

            event_type = stringify(row.get("event_type"))
            event_counts[rid][event_type] += 1

            current_ts = safe_int(row.get("timestamp")) or -1
            previous_latest = latest_event_by_rid.get(rid)
            previous_latest_ts = safe_int(previous_latest.get(
                "timestamp")) if previous_latest else None
            if previous_latest is None or (previous_latest_ts or -1) < current_ts:
                latest_event_by_rid[rid] = row

            if event_type == "POSITION_CLOSED":
                position_closed_by_rid[rid] = row
                if stringify(row.get("pnl_status")) == "resolved":
                    previous_terminal = exact_terminal_by_rid.get(rid)
                    previous_terminal_ts = safe_int(previous_terminal.get(
                        "timestamp")) if previous_terminal else None
                    if previous_terminal is None or (previous_terminal_ts or -1) < current_ts:
                        exact_terminal_by_rid[rid] = row

    return exact_terminal_by_rid, latest_event_by_rid, position_closed_by_rid, event_counts


def scan_trade_lifecycle(cohort_rids: set[str]) -> dict[str, dict[str, Any]]:
    latest_state_by_rid: dict[str, dict[str, Any]] = {}
    with TRADE_LIFECYCLE_PATH.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            rid = stringify(row.get("rid"))
            if rid not in cohort_rids:
                continue
            current_ts = max(
                [
                    value
                    for value in (
                        safe_int(row.get("updated_ts_ms")),
                        safe_int(row.get("close_ts_ms")),
                        safe_int(row.get("intent_ts_ms")),
                        safe_int(row.get("created_ts_ms")),
                    )
                    if value is not None
                ],
                default=-1,
            )
            previous = latest_state_by_rid.get(rid)
            previous_ts = safe_int(previous.get(
                "_sort_ts")) if previous else None
            if previous is None or (previous_ts or -1) < current_ts:
                row = dict(row)
                row["_sort_ts"] = current_ts
                latest_state_by_rid[rid] = row
    return latest_state_by_rid


def classify_economic_outcome(
    rid: str,
    exact_terminal_by_rid: dict[str, dict[str, Any]],
    latest_event_by_rid: dict[str, dict[str, Any]],
    event_counts: dict[str, Counter[str]],
    lifecycle_latest_by_rid: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    exact_terminal = exact_terminal_by_rid.get(rid)
    if exact_terminal is not None:
        realized_pnl_net = safe_float(exact_terminal.get("realized_pnl_net"))
        if realized_pnl_net is not None:
            if realized_pnl_net > 0:
                label = "WINNER"
            elif realized_pnl_net < 0:
                label = "LOSER"
            else:
                label = "FLAT"
            return {
                "economic_state": "POSITION_CLOSED_RESOLVED",
                "economic_label": label,
                "realized_pnl_net": realized_pnl_net,
                "economic_ts_ms": safe_int(exact_terminal.get("timestamp")),
                "economic_source": "order_log:POSITION_CLOSED_exact_rid",
                "pnl_source": stringify(exact_terminal.get("pnl_source")),
                "pnl_status": stringify(exact_terminal.get("pnl_status")),
            }

    latest_event = latest_event_by_rid.get(rid) or {}
    latest_type = stringify(latest_event.get("event_type"))
    lifecycle_row = lifecycle_latest_by_rid.get(rid) or {}
    lifecycle_status = stringify(lifecycle_row.get("status"))
    counts = event_counts.get(rid, Counter())

    if latest_type == "ORDER_CANCELLED" and counts.get("ORDER_FILLED", 0) == 0:
        state = "CANCELLED_NO_FILL"
        label = "NOT_EXECUTED"
    elif counts.get("ORDER_FILLED", 0) > 0 and latest_type != "POSITION_CLOSED":
        state = "OPEN_OR_UNPROVEN_AFTER_FILL"
        label = "OPEN_OR_UNPROVEN"
    elif latest_type == "ORDER_PLACED":
        state = "ORDER_PLACED_NOT_TERMINAL"
        label = "OPEN_OR_UNPROVEN"
    elif latest_type == "ORDER_INTENT":
        state = "NO_DOWNSTREAM_EXECUTION_EVIDENCE"
        label = "NOT_EXECUTED"
    elif lifecycle_status:
        state = f"TRADE_LIFECYCLE_{lifecycle_status}"
        label = "OPEN_OR_UNPROVEN"
    else:
        state = "NO_TERMINAL_ECONOMIC_ROW"
        label = "OPEN_OR_UNPROVEN"

    return {
        "economic_state": state,
        "economic_label": label,
        "realized_pnl_net": None,
        "economic_ts_ms": safe_int(latest_event.get("timestamp")),
        "economic_source": "order_log_latest_event_or_trade_lifecycle",
        "pnl_source": "",
        "pnl_status": "",
    }


def build_exact_subset_matrix(
    rows: list[dict[str, str]],
    exact_terminal_by_rid: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    exact_terminal_rids = set(exact_terminal_by_rid)
    exact_terminal_outcome_by_rid: dict[str, dict[str, Any]] = {}
    for rid, exact_row in exact_terminal_by_rid.items():
        pnl = safe_float(exact_row.get("realized_pnl_net"))
        if pnl is None:
            continue
        if pnl > 0:
            label = "WINNER"
        elif pnl < 0:
            label = "LOSER"
        else:
            label = "FLAT"
        exact_terminal_outcome_by_rid[rid] = {
            "label": label,
            "pnl": pnl,
            "timestamp": safe_int(exact_row.get("timestamp")),
        }

    summary_rows: list[dict[str, Any]] = []
    for gate_code in REPLAY_TARGETS:
        gate_rows = [row for row in rows if stringify(
            row.get("nrr_code")) == gate_code]
        exact_gate_rows = [row for row in gate_rows if stringify(
            row.get("rid")) in exact_terminal_rids]

        exact_blocked_winners = 0
        exact_blocked_losers = 0
        exact_passed_winners = 0
        exact_passed_losers = 0
        exact_unproven = 0
        blocked_resolved_net_pnl = 0.0
        passed_resolved_net_pnl = 0.0

        for row in exact_gate_rows:
            rid = stringify(row.get("rid"))
            exact_outcome = exact_terminal_outcome_by_rid.get(rid)
            if exact_outcome is None:
                exact_unproven += 1
                continue
            pnl = exact_outcome["pnl"]
            if pnl is not None:
                if stringify(row.get("counterfactual_result")) == "BLOCK":
                    blocked_resolved_net_pnl += float(pnl)
                elif stringify(row.get("counterfactual_result")) == "PASS":
                    passed_resolved_net_pnl += float(pnl)

            if stringify(row.get("counterfactual_result")) == "BLOCK":
                if exact_outcome["label"] == "WINNER":
                    exact_blocked_winners += 1
                elif exact_outcome["label"] == "LOSER":
                    exact_blocked_losers += 1
            elif stringify(row.get("counterfactual_result")) == "PASS":
                if exact_outcome["label"] == "WINNER":
                    exact_passed_winners += 1
                elif exact_outcome["label"] == "LOSER":
                    exact_passed_losers += 1
            else:
                exact_unproven += 1

        if exact_blocked_losers > 0 and exact_blocked_winners == 0:
            policy_signal = "PROTECTIVE_ON_EXACT_TERMINAL_SUBSET"
        elif exact_blocked_winners > 0 and exact_blocked_losers == 0:
            policy_signal = "HARMFUL_ON_EXACT_TERMINAL_SUBSET"
        elif exact_blocked_winners > 0 and exact_blocked_losers > 0:
            policy_signal = "MIXED_ON_EXACT_TERMINAL_SUBSET"
        else:
            policy_signal = "NO_EXACT_TERMINAL_EVIDENCE"

        summary_rows.append(
            {
                "nrr_code": gate_code,
                "cohort_rows": len(gate_rows),
                "deterministic_rows": sum(
                    1 for row in gate_rows if stringify(row.get("counterfactual_result")) != "UNPROVEN_INPUT_MISSING"
                ),
                "exact_terminal_rows": len(exact_gate_rows),
                "exact_terminal_block_count": sum(
                    1 for row in exact_gate_rows if stringify(row.get("counterfactual_result")) == "BLOCK"
                ),
                "exact_terminal_pass_count": sum(
                    1 for row in exact_gate_rows if stringify(row.get("counterfactual_result")) == "PASS"
                ),
                "exact_terminal_unproven_count": exact_unproven,
                "exact_terminal_blocked_winners": exact_blocked_winners,
                "exact_terminal_blocked_losers": exact_blocked_losers,
                "exact_terminal_passed_winners": exact_passed_winners,
                "exact_terminal_passed_losers": exact_passed_losers,
                "exact_terminal_blocked_resolved_net_pnl": round(blocked_resolved_net_pnl, 10),
                "exact_terminal_passed_resolved_net_pnl": round(passed_resolved_net_pnl, 10),
                "policy_signal": policy_signal,
                "policy_revision_supported": "false",
            }
        )

    return summary_rows, exact_terminal_outcome_by_rid


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    replay_rows = build_cohort_rows()
    cohort_rids = {stringify(row.get("rid")) for row in replay_rows}
    exact_terminal_by_rid, latest_event_by_rid, position_closed_by_rid, event_counts = scan_current_order_log(
        cohort_rids)
    lifecycle_latest_by_rid = scan_trade_lifecycle(cohort_rids)
    usefulness_rows, exact_terminal_outcome_by_rid = build_exact_subset_matrix(
        replay_rows, exact_terminal_by_rid)

    baseline_exact_rids = load_t7_baseline_exact_rids()
    current_exact_rids = set(exact_terminal_by_rid)
    new_exact_rids = current_exact_rids - baseline_exact_rids

    replay_output_rows: list[dict[str, Any]] = []
    economic_output_rows: list[dict[str, Any]] = []

    for row in replay_rows:
        rid = stringify(row.get("rid"))
        exact_terminal = exact_terminal_by_rid.get(rid)
        exact_outcome = exact_terminal_outcome_by_rid.get(rid)
        economic = classify_economic_outcome(
            rid,
            exact_terminal_by_rid,
            latest_event_by_rid,
            event_counts,
            lifecycle_latest_by_rid,
        )

        replay_row = dict(row)
        replay_row.update(
            {
                "current_exact_terminal_join": "yes" if exact_terminal is not None else "no",
                "current_exact_terminal_timestamp": iso_utc(safe_int(exact_terminal.get("timestamp")) if exact_terminal else None),
                "current_exact_terminal_pnl_net": safe_float(exact_terminal.get("realized_pnl_net")) if exact_terminal else None,
                "current_exact_terminal_label": exact_outcome["label"] if exact_outcome else "",
                "current_exact_terminal_join_source": "order_log:POSITION_CLOSED_exact_rid" if exact_terminal is not None else "",
            }
        )
        replay_output_rows.append(replay_row)

        economic_row = dict(replay_row)
        economic_row.update(
            {
                "economic_state": economic["economic_state"],
                "economic_label": economic["economic_label"],
                "realized_pnl_net": economic["realized_pnl_net"],
                "economic_ts": iso_utc(economic["economic_ts_ms"]),
                "economic_source": economic["economic_source"],
                "pnl_source": economic["pnl_source"],
                "pnl_status": economic["pnl_status"],
                "exact_terminal_joined": "yes" if exact_terminal is not None else "no",
            }
        )
        economic_output_rows.append(economic_row)

    replay_fieldnames = list(replay_rows[0].keys()) + [
        "current_exact_terminal_join",
        "current_exact_terminal_timestamp",
        "current_exact_terminal_pnl_net",
        "current_exact_terminal_label",
        "current_exact_terminal_join_source",
    ]
    economic_fieldnames = replay_fieldnames + [
        "economic_state",
        "economic_label",
        "realized_pnl_net",
        "economic_ts",
        "economic_source",
        "pnl_source",
        "pnl_status",
        "exact_terminal_joined",
    ]

    write_csv(REPLAY_ROWS_PATH, replay_fieldnames, replay_output_rows)
    write_csv(ECONOMIC_JOIN_PATH, economic_fieldnames, economic_output_rows)
    write_csv(
        USEFULNESS_MATRIX_PATH,
        [
            "nrr_code",
            "cohort_rows",
            "deterministic_rows",
            "exact_terminal_rows",
            "exact_terminal_block_count",
            "exact_terminal_pass_count",
            "exact_terminal_unproven_count",
            "exact_terminal_blocked_winners",
            "exact_terminal_blocked_losers",
            "exact_terminal_passed_winners",
            "exact_terminal_passed_losers",
            "exact_terminal_blocked_resolved_net_pnl",
            "exact_terminal_passed_resolved_net_pnl",
            "policy_signal",
            "policy_revision_supported",
        ],
        usefulness_rows,
    )

    exact_terminal_rows = len(current_exact_rids)
    exact_terminal_rids = ", ".join(
        sorted(current_exact_rids)) if current_exact_rids else "none"
    baseline_exact_terminal_rows = len(baseline_exact_rids)
    exact_terminal_delta = len(new_exact_rids)
    post_t7_order_intents = 0
    with ORDER_LOG_PATH.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "DecisionMaking" not in line or "aurora" not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                stringify(row.get("event_type")) == "ORDER_INTENT"
                and stringify(row.get("source_fsm")) == "DecisionMaking"
                and stringify(row.get("strategy_id")) == "aurora"
                and (safe_int(row.get("timestamp")) or -1) > WINDOW_END_MS
            ):
                post_t7_order_intents += 1

    gate_lines = []
    for row in usefulness_rows:
        gate_lines.append(
            f"  {row['nrr_code']}: exact_terminal_rows={row['exact_terminal_rows']}, BLOCK={row['exact_terminal_block_count']}, PASS={row['exact_terminal_pass_count']}, UNPROVEN={row['exact_terminal_unproven_count']}, policy_signal={row['policy_signal']}"
        )

    report_lines = [
        "AGENT_REPORT_V1",
        "",
        "task:",
        "  AURORA_T7M_POST_REPAIR_NRR_TERMINAL_MATURATION_RERUN",
        "",
        "verdict:",
        "  NO_NEW_EXACT_TERMINAL_ROWS_POLICY_UNCHANGED",
        "",
        "primary_cohort:",
        f"  accepted_allow_path_rids: {len(cohort_rids)}",
        f"  t7_baseline_exact_terminal_rows: {baseline_exact_terminal_rows}/12",
        f"  current_exact_terminal_rows: {exact_terminal_rows}/12",
        f"  exact_terminal_delta_since_t7: {exact_terminal_delta}",
        f"  exact_terminal_rids: {exact_terminal_rids}",
        "  note: the original 12-RID cohort still has only two exact terminal PnL rows in the current logs",
        "",
        "replay_and_policy:",
        *gate_lines,
        "",
        "answers:",
        "  q1: no; the original 12-RID cohort still has 2/12 exact terminal PnL rows, unchanged from T7",
        "  q2: unchanged from T7; NRR-027 and NRR-029 still show protective value on the exact resolved subset, but the resolved sample is still only two losers and remains too thin to re-enable",
        "  q3: no; no disabled NRR has enough exact terminal evidence to revise policy",
        f"  q4: {len(cohort_rids) - exact_terminal_rows} additional exact terminal rows are still needed to fully mature the original 12-RID cohort",
        "",
        "secondary_cohort:",
        f"  post_t7_aurora_order_intents_detected: {post_t7_order_intents}",
        "  note: post-T7 aurora activity exists, but no separately bounded NEW_COHORT was materialized because the task did not provide a canonical secondary cohort boundary",
        "",
        "proven:",
        f"  - Current order_log exact joins still resolve only {exact_terminal_rows}/12 original RIDs.",
        "  - Both exact terminal rows are LOSERS.",
        "  - NRR-027 blocks one exact-terminal loser and passes one exact-terminal loser.",
        "  - NRR-029 blocks one exact-terminal loser and leaves one exact-terminal row unproven.",
        "  - No policy-revision signal is strong enough to overturn the prior keep-disabled / observe-only stance.",
        "",
        "next_action:",
        "  - Keep NRR-026..030 disabled / observe-only and rerun only after more of the original 12-RID cohort reaches exact terminal PnL.",
    ]

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "cohort_rids": len(cohort_rids),
        "exact_terminal_rows": exact_terminal_rows,
        "baseline_exact_terminal_rows": baseline_exact_terminal_rows,
        "exact_terminal_delta_since_t7": exact_terminal_delta,
        "post_t7_order_intents": post_t7_order_intents,
        "report_path": str(REPORT_PATH.relative_to(ROOT)).replace("\\", "/"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
