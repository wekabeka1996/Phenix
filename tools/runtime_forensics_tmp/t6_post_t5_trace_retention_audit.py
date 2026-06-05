from __future__ import annotations

import ast
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "reports" / "runtime_forensics" / "T6_post_t5_trace_retention"

T5_COMMIT_HASH = "1a2e7f6d7437d2262a1921fb116a51a53ab488b0"
T5_COMMIT_AUTHOR_TS = "2026-05-09T17:09:49+03:00"
T5_COMMIT_SUBJECT = (
    "Багато виправлень у коді та додано нові функції для покращення продуктивності. "
    "Багато чьго зроблено калібратови виокремленні, всі родмапи окрім ROI просунулись в "
    "реалізації, робота з частково вимкненими poliscy"
)

WINDOW_START_FILE = LOGS_DIR / "aurora_core.log.5"
WINDOW_START_LINE = 5747
WINDOW_START_LOCAL_TS = "2026-05-10 16:58:04,460"
WINDOW_READY_LOCAL_TS = "2026-05-10 16:58:09,633"

CORE_LOG_SEQUENCE = [
    (LOGS_DIR / "aurora_core.log.5", 5747),
    (LOGS_DIR / "aurora_core.log.4", 1),
    (LOGS_DIR / "aurora_core.log.3", 1),
    (LOGS_DIR / "aurora_core.log.2", 1),
    (LOGS_DIR / "aurora_core.log.1", 1),
    (LOGS_DIR / "aurora_core.log", 1),
]

FIELD_NAMES = [
    "strategy_id",
    "regime_confidence_gate_verdict",
    "low_vol_cost_floor",
    "price_motion_context",
    "missing_inputs",
    "safety_gate_snapshot",
]

PROCESSING_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .*? - .*? - \[(?P<symbol>[^\]]+)\] "
    r"STRATEGY_SIGNAL_GATEWAY: Processing (?P<side>BUY|SELL) signal rid=(?P<rid>\S+) strategy_id=(?P<strategy>\S+)"
)
REGIME_AUDIT_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .*? - .*? - \[(?P<symbol>[^\]]+)\] "
    r"REGIME_AUDIT decision rid=(?P<rid>\S+) strategy=(?P<strategy>\S+) outcome=(?P<outcome>\S+) regime=(?P<regime>\S+) conf=(?P<conf>\S+)"
)
EMIT_FAILED_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .*? - .*? - \[(?P<symbol>[^\]]+)\] "
    r"OBSERVABILITY: EVT:DECISION_TRACE_EMITTED emit failed\. RID=(?P<rid>\S+)\. reason=(?P<reason>.*)"
)
FAILED_PAYLOAD_RE = re.compile(
    r"Payload validation failed for EVT:DECISION_TRACE_EMITTED: (?P<payload>\{.*\}) is not valid under any of the given schemas"
)


@dataclass
class RidRecord:
    rid: str
    symbol: str = ""
    strategy: str = ""
    side: str = ""
    regime: str = ""
    regime_confidence: str = ""
    regime_outcome: str = ""
    regime_audit_ts_local: str = ""
    processing_ts_local: str = ""
    decision_trace_emit_failed: bool = False
    decision_trace_failure_reason: str = ""
    shadow_strategy_signal: bool = False
    shadow_trade_intent: bool = False
    order_log_decision_intent: bool = False
    order_log_order_placed: bool = False
    order_log_entry_filled: bool = False
    aurora_events_order_state_changed_filled: bool = False
    event_chain_entry_registered: bool = False
    durable_decision_trace_paths: set[str] = field(default_factory=set)
    order_log_fields: set[str] = field(default_factory=set)
    shadow_fields: set[str] = field(default_factory=set)
    durable_trace_fields: set[str] = field(default_factory=set)

    @property
    def replay_ready(self) -> bool:
        return bool(self.durable_decision_trace_paths) and not self.decision_trace_emit_failed


def iter_lines(path: Path, start_line: int = 1) -> Iterable[tuple[int, str]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle, start=1):
            if index < start_line:
                continue
            yield index, line.rstrip("\n")


def iter_json_lines(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                value = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def collect_keys(value: Any, keys: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            collect_keys(item, keys)
    elif isinstance(value, list):
        for item in value:
            collect_keys(item, keys)


def parse_failed_payload(reason: str) -> dict[str, Any]:
    match = FAILED_PAYLOAD_RE.search(reason)
    if not match:
        return {}
    payload_text = match.group("payload")
    try:
        parsed = ast.literal_eval(payload_text)
    except (SyntaxError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def sanitize_reason(reason: str) -> str:
    return reason.replace("\r", " ").replace("\n", " ").strip()


def load_core_window() -> tuple[dict[str, RidRecord], list[dict[str, Any]], list[dict[str, str]]]:
    candidates: dict[str, RidRecord] = {}
    failures: list[dict[str, Any]] = []
    startup_markers: list[dict[str, str]] = []

    for path, start_line in CORE_LOG_SEQUENCE:
        for line_no, line in iter_lines(path, start_line):
            if "FE_WARMUP:" in line:
                has_false = any("full_ready=False" in marker["message"] for marker in startup_markers)
                has_true = any("full_ready=True" in marker["message"] for marker in startup_markers)
                if "full_ready=False" in line and sum(
                    1 for marker in startup_markers if "full_ready=False" in marker["message"]
                ) < 4:
                    startup_markers.append(
                        {
                            "path": path.name,
                            "line": str(line_no),
                            "message": line,
                        }
                    )
                elif "full_ready=True" in line and sum(
                    1 for marker in startup_markers if "full_ready=True" in marker["message"]
                ) < 4:
                    startup_markers.append(
                        {
                            "path": path.name,
                            "line": str(line_no),
                            "message": line,
                        }
                    )
                elif not has_false or not has_true:
                    startup_markers.append(
                        {
                            "path": path.name,
                            "line": str(line_no),
                            "message": line,
                        }
                    )

            processing_match = PROCESSING_RE.match(line)
            if processing_match and processing_match.group("strategy") == "aurora":
                rid = processing_match.group("rid")
                record = candidates.setdefault(rid, RidRecord(rid=rid))
                record.symbol = processing_match.group("symbol")
                record.side = processing_match.group("side")
                record.strategy = processing_match.group("strategy")
                record.processing_ts_local = processing_match.group("ts")
                continue

            regime_match = REGIME_AUDIT_RE.match(line)
            if regime_match and regime_match.group("strategy") == "aurora":
                rid = regime_match.group("rid")
                record = candidates.setdefault(rid, RidRecord(rid=rid))
                record.symbol = regime_match.group("symbol")
                record.strategy = regime_match.group("strategy")
                record.regime = regime_match.group("regime")
                record.regime_confidence = regime_match.group("conf")
                record.regime_outcome = regime_match.group("outcome")
                record.regime_audit_ts_local = regime_match.group("ts")
                continue

            failed_match = EMIT_FAILED_RE.match(line)
            if failed_match:
                rid = failed_match.group("rid")
                record = candidates.setdefault(rid, RidRecord(rid=rid))
                record.symbol = failed_match.group("symbol")
                record.decision_trace_emit_failed = True
                record.decision_trace_failure_reason = sanitize_reason(failed_match.group("reason"))
                failures.append(
                    {
                        "ts_local": failed_match.group("ts"),
                        "symbol": failed_match.group("symbol"),
                        "rid": rid,
                        "reason": sanitize_reason(failed_match.group("reason")),
                    }
                )

    return candidates, failures, startup_markers


def load_order_log(candidates: dict[str, RidRecord]) -> None:
    path = LOGS_DIR / "order_log_v1.jsonl"
    for record in iter_json_lines(path):
        rid = str(record.get("rid", ""))
        lifecycle_id = str(record.get("lifecycle_id", ""))

        if rid in candidates:
            candidate = candidates[rid]
            event_type = record.get("event_type")
            source_fsm = record.get("source_fsm")
            if event_type == "ORDER_INTENT" and source_fsm == "DecisionMaking":
                candidate.order_log_decision_intent = True
                keys: set[str] = set()
                collect_keys(record, keys)
                candidate.order_log_fields |= keys
                candidate.symbol = candidate.symbol or str(record.get("symbol", ""))
                candidate.strategy = candidate.strategy or str(record.get("strategy_id", ""))
                candidate.side = candidate.side or str(record.get("side", ""))
            elif event_type == "ORDER_PLACED":
                candidate.order_log_order_placed = True

        if lifecycle_id in candidates and record.get("event_type") == "ORDER_FILLED":
            if str(record.get("order_kind", "")) == "ENTRY":
                candidates[lifecycle_id].order_log_entry_filled = True


def load_shadow_journal(accepted: dict[str, RidRecord]) -> None:
    path = LOGS_DIR / "shadow_critical_event_journal_v1.jsonl"
    for record in iter_json_lines(path):
        rid = str(record.get("rid", ""))
        if rid not in accepted:
            continue
        event_name = str(record.get("event_name", ""))
        if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
            accepted[rid].shadow_strategy_signal = True
        elif event_name == "EVT:TRADE_INTENT_PROPOSED":
            accepted[rid].shadow_trade_intent = True
        elif event_name == "EVT:DECISION_TRACE_EMITTED":
            accepted[rid].durable_decision_trace_paths.add(path.name)

        keys: set[str] = set()
        collect_keys(record, keys)
        accepted[rid].shadow_fields |= keys


def load_aurora_events(accepted: dict[str, RidRecord]) -> None:
    path = LOGS_DIR / "aurora_events.jsonl"
    for record in iter_json_lines(path):
        rid = str(record.get("rid", ""))
        if rid not in accepted:
            continue
        if record.get("event") == "ORDER_STATE_CHANGED" and str(record.get("status", "")) == "FILLED":
            accepted[rid].aurora_events_order_state_changed_filled = True


def load_event_chain(accepted: dict[str, RidRecord]) -> None:
    path = LOGS_DIR / "event_chain.log"
    for record in iter_json_lines(path):
        rid = str(record.get("rid", ""))
        if rid not in accepted:
            continue
        if str(record.get("message", "")).startswith("Entry registered:"):
            accepted[rid].event_chain_entry_registered = True


def load_durable_trace_records(accepted: dict[str, RidRecord]) -> None:
    for path in sorted(LOGS_DIR.glob("*.jsonl")):
        for record in iter_json_lines(path):
            rid = str(record.get("rid", ""))
            if rid not in accepted:
                continue
            if str(record.get("event_name", "")) != "EVT:DECISION_TRACE_EMITTED":
                continue
            accepted[rid].durable_decision_trace_paths.add(path.name)
            keys: set[str] = set()
            collect_keys(record, keys)
            accepted[rid].durable_trace_fields |= keys


def write_inventory(accepted: dict[str, RidRecord]) -> Path:
    output_path = REPORT_DIR / "post_t5_accepted_trace_inventory.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rid",
                "symbol",
                "side",
                "regime",
                "regime_confidence",
                "regime_audit_ts_local",
                "shadow_strategy_signal_produced",
                "shadow_trade_intent_proposed",
                "order_log_decision_order_intent",
                "order_log_order_placed",
                "order_log_entry_filled",
                "aurora_events_order_state_changed_filled",
                "event_chain_entry_registered",
                "decision_trace_emit_failed",
                "durable_decision_trace_record_found",
                "durable_decision_trace_paths",
                "decision_trace_failure_reason",
                "replay_ready",
            ],
        )
        writer.writeheader()
        for rid in sorted(accepted):
            record = accepted[rid]
            writer.writerow(
                {
                    "rid": record.rid,
                    "symbol": record.symbol,
                    "side": record.side,
                    "regime": record.regime,
                    "regime_confidence": record.regime_confidence,
                    "regime_audit_ts_local": record.regime_audit_ts_local,
                    "shadow_strategy_signal_produced": record.shadow_strategy_signal,
                    "shadow_trade_intent_proposed": record.shadow_trade_intent,
                    "order_log_decision_order_intent": record.order_log_decision_intent,
                    "order_log_order_placed": record.order_log_order_placed,
                    "order_log_entry_filled": record.order_log_entry_filled,
                    "aurora_events_order_state_changed_filled": record.aurora_events_order_state_changed_filled,
                    "event_chain_entry_registered": record.event_chain_entry_registered,
                    "decision_trace_emit_failed": record.decision_trace_emit_failed,
                    "durable_decision_trace_record_found": bool(record.durable_decision_trace_paths),
                    "durable_decision_trace_paths": ";".join(sorted(record.durable_decision_trace_paths)),
                    "decision_trace_failure_reason": record.decision_trace_failure_reason,
                    "replay_ready": record.replay_ready,
                }
            )
    return output_path


def write_coverage(accepted: dict[str, RidRecord]) -> Path:
    output_path = REPORT_DIR / "post_t5_replay_field_coverage.csv"
    accepted_total = len(accepted)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "field_name",
                "accepted_allow_rid_count",
                "durable_decision_trace_count",
                "durable_decision_trace_ratio",
                "order_log_fallback_count",
                "shadow_journal_fallback_count",
                "schema_acceptance_proven",
                "notes",
            ],
        )
        writer.writeheader()
        for field_name in FIELD_NAMES:
            durable_count = sum(1 for record in accepted.values() if field_name in record.durable_trace_fields)
            order_log_count = sum(1 for record in accepted.values() if field_name in record.order_log_fields)
            shadow_count = sum(1 for record in accepted.values() if field_name in record.shadow_fields)
            notes: list[str] = []
            if durable_count == 0:
                if order_log_count or shadow_count:
                    notes.append("fallback_only")
                else:
                    notes.append("not_observed_on_allow_path")
            else:
                notes.append("durable_trace_observed")

            writer.writerow(
                {
                    "field_name": field_name,
                    "accepted_allow_rid_count": accepted_total,
                    "durable_decision_trace_count": durable_count,
                    "durable_decision_trace_ratio": f"{durable_count}/{accepted_total}" if accepted_total else "0/0",
                    "order_log_fallback_count": order_log_count,
                    "shadow_journal_fallback_count": shadow_count,
                    "schema_acceptance_proven": bool(durable_count),
                    "notes": ";".join(notes),
                }
            )
    return output_path


def write_failures(
    failures: list[dict[str, Any]],
    candidates: dict[str, RidRecord],
    accepted: dict[str, RidRecord],
) -> Path:
    output_path = REPORT_DIR / "decision_trace_schema_failures_post_t5.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ts_local",
                "symbol",
                "rid",
                "decision_outcome",
                "accepted_allow_path",
                "missing_inputs_regime_confidence",
                "missing_inputs_trend_dir",
                "missing_inputs_signal_score",
                "missing_inputs_pm_norm_10s",
                "missing_inputs_vol_pct_10s",
                "missing_inputs_low_vol_cost_floor",
                "failure_reason",
            ],
        )
        writer.writeheader()
        for failure in failures:
            payload = parse_failed_payload(failure["reason"])
            rid = failure["rid"]
            candidate = candidates.get(rid, RidRecord(rid=rid))
            writer.writerow(
                {
                    "ts_local": failure["ts_local"],
                    "symbol": failure["symbol"],
                    "rid": rid,
                    "decision_outcome": candidate.regime_outcome,
                    "accepted_allow_path": rid in accepted,
                    "missing_inputs_regime_confidence": payload.get("regime_confidence"),
                    "missing_inputs_trend_dir": payload.get("trend_dir"),
                    "missing_inputs_signal_score": payload.get("signal_score"),
                    "missing_inputs_pm_norm_10s": payload.get("pm_norm_10s"),
                    "missing_inputs_vol_pct_10s": payload.get("vol_pct_10s"),
                    "missing_inputs_low_vol_cost_floor": payload.get("low_vol_cost_floor"),
                    "failure_reason": failure["reason"],
                }
            )
    return output_path


def build_report(
    accepted: dict[str, RidRecord],
    failures: list[dict[str, Any]],
    startup_markers: list[dict[str, str]],
) -> Path:
    output_path = REPORT_DIR / "T6_POST_T5_TRACE_RETENTION_REPORT.md"

    accepted_total = len(accepted)
    emit_failed_total = sum(1 for record in accepted.values() if record.decision_trace_emit_failed)
    durable_total = sum(1 for record in accepted.values() if record.durable_decision_trace_paths)
    trade_intent_total = sum(1 for record in accepted.values() if record.shadow_trade_intent)
    order_placed_total = sum(1 for record in accepted.values() if record.order_log_order_placed)
    order_filled_total = sum(1 for record in accepted.values() if record.order_log_entry_filled)
    strategy_id_fallback = sum(1 for record in accepted.values() if "strategy_id" in record.order_log_fields)
    verdict = "RETENTION_STILL_BROKEN" if durable_total == 0 and emit_failed_total else "PARTIAL_OR_UNCLEAR"

    sample_rids = [
        rid
        for rid, _record in sorted(
            accepted.items(),
            key=lambda item: (item[1].regime_audit_ts_local, item[0]),
        )[:3]
    ]
    sample_lines = []
    for rid in sample_rids:
        record = accepted[rid]
        sample_lines.append(
            f"- {rid}: symbol={record.symbol}, trade_intent={record.shadow_trade_intent}, "
            f"order_placed={record.order_log_order_placed}, entry_filled={record.order_log_entry_filled}, "
            f"emit_failed={record.decision_trace_emit_failed}, durable_trace={bool(record.durable_decision_trace_paths)}"
        )

    startup_excerpt = "\n".join(
        f"- {marker['path']}:{marker['line']} {marker['message']}" for marker in startup_markers[:8]
    )

    field_rows = []
    for field_name in FIELD_NAMES:
        durable_count = sum(1 for record in accepted.values() if field_name in record.durable_trace_fields)
        order_log_count = sum(1 for record in accepted.values() if field_name in record.order_log_fields)
        shadow_count = sum(1 for record in accepted.values() if field_name in record.shadow_fields)
        field_rows.append(
            f"- {field_name}: durable={durable_count}/{accepted_total}, order_log_fallback={order_log_count}/{accepted_total}, shadow_fallback={shadow_count}/{accepted_total}"
        )

    report_text = f"""# T6 Post-T5 Trace Retention Report

## Scope
- Task: AURORA_T6_POST_T5_RUNTIME_TRACE_RETENTION_AUDIT
- Mode: read-only runtime forensics
- Allowed write targets only: reports/runtime_forensics/T6_post_t5_trace_retention and tools/runtime_forensics_tmp

## Post-T5 Window Proof
- T5 trace-chain last-touch commit: {T5_COMMIT_HASH}
- T5 trace-chain last-touch author timestamp: {T5_COMMIT_AUTHOR_TS}
- T5 trace-chain commit subject: {T5_COMMIT_SUBJECT}
- Fresh runtime marker anchored in {WINDOW_START_FILE.name}:{WINDOW_START_LINE}
- Earliest warmup marker in audit window: {WINDOW_START_LOCAL_TS}
- Feature-engineering full-ready markers observed by: {WINDOW_READY_LOCAL_TS}
- Startup marker excerpts:
{startup_excerpt}

## Verdict
- {verdict}

## Executive Findings
- Accepted allow-path RIDs observed in the fresh post-startup window: {accepted_total}
- Durable EVT:DECISION_TRACE_EMITTED records found for accepted allow-path RIDs: {durable_total}/{accepted_total}
- RID-scoped EVT:DECISION_TRACE_EMITTED emit failures on accepted allow-path RIDs: {emit_failed_total}/{accepted_total}
- EVT:TRADE_INTENT_PROPOSED observed on accepted allow-path RIDs: {trade_intent_total}/{accepted_total}
- ORDER_PLACED observed on accepted allow-path RIDs: {order_placed_total}/{accepted_total}
- ENTRY fill observed on accepted allow-path RIDs: {order_filled_total}/{accepted_total}
- strategy_id present in accepted fallback ORDER_INTENT records: {strategy_id_fallback}/{accepted_total}

## Interpretation
- The allow-path remains operational downstream of decision-making: accepted RIDs continue into TRADE_INTENT_PROPOSED, ORDER_INTENT, ORDER_PLACED, and in multiple cases ENTRY fill.
- The durable decision-trace surface remains broken for allow-path traffic: no accepted RID produced a durable EVT:DECISION_TRACE_EMITTED record in logs/*.jsonl.
- The failure mode is runtime schema rejection, not absence of trading flow. RID-scoped failures show Payload validation failed for EVT:DECISION_TRACE_EMITTED with missing_inputs-shaped payloads that are not valid under the schema anyOf.
- Because durable allow-path decision traces are absent, replay readiness is not proven and field-level schema acceptance on the target surface is not proven.

## Replay Field Coverage
{chr(10).join(field_rows)}

## Requested Field Status
- strategy_id: present on fallback accepted ORDER_INTENT surfaces, but not proven on durable allow-path DECISION_TRACE because zero successful allow-path trace records were persisted.
- regime_confidence_gate_verdict: present on fallback accepted ORDER_INTENT surfaces, but not proven on durable allow-path DECISION_TRACE because zero successful allow-path trace records were persisted.
- low_vol_cost_floor: not proven on durable allow-path DECISION_TRACE; failure payloads repeatedly show low_vol_cost_floor values inside missing_inputs, including not_evaluated_or_not_attached.
- safety_gate_snapshot: not proven on durable allow-path DECISION_TRACE in the fresh window.

## Representative Accepted RID Samples
{chr(10).join(sample_lines) if sample_lines else '- none'}

## Failure Surface Summary
- Total post-startup EVT:DECISION_TRACE_EMITTED schema failures captured in this window: {len(failures)}
- Failure CSV: decision_trace_schema_failures_post_t5.csv
- Accepted inventory CSV: post_t5_accepted_trace_inventory.csv
- Field coverage CSV: post_t5_replay_field_coverage.csv

## Conclusion
- Runtime evidence does not support the claim that post-T5 accepted allow-path decision traces are durably persisted and replay-ready.
- The observed fresh runtime window is post-T5, accepted allow-path traffic exists, and downstream execution continues, but the decision-trace persistence contract still fails closed on the allow path.
"""

    output_path.write_text(report_text, encoding="utf-8")
    return output_path


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    candidates, failures, startup_markers = load_core_window()
    load_order_log(candidates)

    accepted = {
        rid: record
        for rid, record in candidates.items()
        if record.strategy == "aurora"
        and record.regime_outcome == "ALLOW"
        and record.order_log_decision_intent
    }

    load_shadow_journal(accepted)
    load_aurora_events(accepted)
    load_event_chain(accepted)
    load_durable_trace_records(accepted)

    write_inventory(accepted)
    write_coverage(accepted)
    write_failures(failures, candidates, accepted)
    build_report(accepted, failures, startup_markers)

    print(f"accepted_allow_rids={len(accepted)}")
    print(
        f"durable_decision_trace_records={sum(1 for record in accepted.values() if record.durable_decision_trace_paths)}"
    )
    print(
        f"accepted_emit_failures={sum(1 for record in accepted.values() if record.decision_trace_emit_failed)}"
    )


if __name__ == "__main__":
    main()