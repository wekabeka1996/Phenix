from __future__ import annotations

import csv
import json
import subprocess
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "reports" / "runtime_forensics" / "T6B_post_t5b_trace_retention"
SCHEMA_PATH = ROOT / "schemas" / "decision_trace_emitted_v1.json"

REPORT_PATH = REPORT_DIR / "T6B_POST_T5B_TRACE_RETENTION_REPORT.md"
INVENTORY_PATH = REPORT_DIR / "post_t5b_accepted_trace_inventory.csv"
COVERAGE_PATH = REPORT_DIR / "post_t5b_replay_field_coverage.csv"
FAILURES_PATH = REPORT_DIR / "decision_trace_schema_failures_post_t5b.csv"

ALLOWED_VERDICTS = {
    "RUNTIME_RETENTION_VERIFIED",
    "PARTIAL_RETENTION",
    "BLOCKED_OLD_RUNTIME_WINDOW",
    "RETENTION_STILL_BROKEN",
}

LOCAL_TS_RE = r"(?P<local_ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
STARTUP_DONE_RE = re.compile(
    rf"^{LOCAL_TS_RE} .*? BOOTSTRAP_LIFECYCLE STARTUP_BASIS_EXECUTOR_DONE (?P<payload>\{{.*\}})$"
)
WARMUP_REPORT_RE = re.compile(
    rf"^{LOCAL_TS_RE} .*? STARTUP_WARMUP_REPORT (?P<payload>\{{.*\}})$"
)
EMIT_FAIL_RE = re.compile(
    rf"^{LOCAL_TS_RE} .*? \[(?P<symbol>[^\]]+)\] OBSERVABILITY: EVT:DECISION_TRACE_EMITTED emit failed\. "
    rf"RID=(?P<rid>\S+)\. reason=(?P<reason>.*)$"
)
PAYLOAD_FAIL_RE = re.compile(
    rf"^{LOCAL_TS_RE} .*? Payload validation failed for EVT:DECISION_TRACE_EMITTED: (?P<reason>.*)$"
)

FIELD_SPECS: dict[str, list[tuple[str, ...]]] = {
    "regime": [("regime",), ("payload_fragment", "regime")],
    "regime_confidence": [("regime_confidence",), ("payload_fragment", "regime_confidence")],
    "regime_confidence_gate_verdict": [
        ("metadata", "regime_confidence_gate_verdict"),
        ("payload_fragment", "regime_confidence_gate_verdict"),
    ],
    "trend_dir": [("trend_dir",), ("payload_fragment", "trend_dir")],
    "trend_confidence": [("trend_confidence",), ("payload_fragment", "trend_confidence")],
    "trend_run_length": [("trend_run_length",), ("payload_fragment", "trend_run_length")],
    "pm_norm_10s": [("pm_norm_10s",), ("payload_fragment", "pm_norm_10s")],
    "pm_norm_60s": [("pm_norm_60s",), ("payload_fragment", "pm_norm_60s")],
    "pm_norm_300s": [("pm_norm_300s",), ("payload_fragment", "pm_norm_300s")],
    "price_motion_context": [
        ("metadata", "price_motion_context"),
        ("payload_fragment", "price_motion_context"),
    ],
    "missing_inputs": [("missing_inputs",), ("payload_fragment", "missing_inputs")],
    "safety_gate_snapshot": [
        ("safety_gate_snapshot",),
        ("payload_fragment", "safety_gate_snapshot"),
    ],
    "low_vol_cost_floor": [
        ("low_vol_cost_floor",),
        ("metadata", "low_vol_cost_floor"),
        ("payload_fragment", "low_vol_cost_floor"),
    ],
    "nrr026": [("nrr026",), ("metadata", "nrr026"), ("payload_fragment", "nrr026")],
    "nrr027": [("nrr027",), ("metadata", "nrr027"), ("payload_fragment", "nrr027")],
    "nrr028": [("nrr028",), ("metadata", "nrr028"), ("payload_fragment", "nrr028")],
    "nrr029": [("nrr029",), ("metadata", "nrr029"), ("payload_fragment", "nrr029")],
    "nrr030": [("nrr030",), ("metadata", "nrr030"), ("payload_fragment", "nrr030")],
    "nrr063": [("nrr063",), ("metadata", "nrr063"), ("payload_fragment", "nrr063")],
}


@dataclass(frozen=True)
class GitRepairInfo:
    commit_hash: str
    commit_ts_iso: str
    commit_subject: str
    commit_ts_ms: int


@dataclass(frozen=True)
class StartupMarker:
    ts_ms: int
    local_ts: str
    source_file: str
    source_line: int
    raw_line: str


@dataclass(frozen=True)
class WarmupMarker:
    ts_ms: int
    local_ts: str
    source_file: str
    source_line: int
    raw_line: str


@dataclass
class Session:
    start_ts_ms: int
    start_local_ts: str
    start_source_file: str
    start_source_line: int
    start_raw_line: str
    end_ts_ms: int | None = None
    warmup_ts_ms: int | None = None
    warmup_local_ts: str | None = None
    warmup_source_file: str | None = None
    warmup_source_line: int | None = None
    warmup_raw_line: str | None = None
    decision_intent_count: int = 0
    allow_count: int = 0
    bypass_count: int = 0
    other_gate_count: int = 0

    @property
    def end_ts_ms_effective(self) -> int:
        return self.end_ts_ms if self.end_ts_ms is not None else 2**63 - 1


@dataclass
class DecisionIntent:
    rid: str
    ts_ms: int
    source_line: int
    symbol: str
    side: str
    regime: Any
    regime_confidence: Any
    gate_verdict: str | None
    threshold_verdict: str | None
    threshold_reason: str | None
    payload: dict[str, Any]


@dataclass
class TraceRecord:
    rid: str
    ts_ms: int
    source_line: int
    source_file: str
    payload: dict[str, Any]


@dataclass
class FailureRecord:
    ts_local: str
    source_file: str
    source_line: int
    symbol: str | None
    rid: str | None
    failure_type: str
    reason: str


def iter_text_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            yield line_number, raw_line.rstrip("\n")


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            text = raw_line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield line_number, payload


def current_log_files(prefix: str) -> list[Path]:
    return sorted(
        path
        for path in LOGS_DIR.iterdir()
        if path.is_file() and path.name == prefix or path.is_file() and path.name.startswith(prefix + ".")
    )


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def epoch_ms_to_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def session_local_to_utc_offset(session: Session) -> Any:
    local_naive = datetime.strptime(
        session.start_local_ts, "%Y-%m-%d %H:%M:%S,%f")
    start_utc = datetime.fromtimestamp(
        session.start_ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
    return start_utc - local_naive


def parse_git_repair_info() -> GitRepairInfo:
    relative_schema = SCHEMA_PATH.relative_to(ROOT)
    result = subprocess.run(
        [
            "git",
            "-c",
            "i18n.logOutputEncoding=utf-8",
            "log",
            "-1",
            "--format=%H%n%cI%n%s",
            "--",
            str(relative_schema),
        ],
        cwd=ROOT,
        capture_output=True,
        text=False,
        check=False,
    )
    stdout_text = result.stdout.decode(
        "utf-8", errors="replace") if result.stdout else ""
    lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
    if result.returncode != 0 or len(lines) < 3:
        mtime_utc = datetime.fromtimestamp(
            SCHEMA_PATH.stat().st_mtime, tz=timezone.utc)
        return GitRepairInfo(
            commit_hash="UNKNOWN",
            commit_ts_iso=mtime_utc.isoformat().replace("+00:00", "Z"),
            commit_subject="UNKNOWN",
            commit_ts_ms=int(mtime_utc.timestamp() * 1000),
        )

    commit_dt = datetime.fromisoformat(
        lines[1].replace("Z", "+00:00")).astimezone(timezone.utc)
    return GitRepairInfo(
        commit_hash=lines[0],
        commit_ts_iso=commit_dt.isoformat().replace("+00:00", "Z"),
        commit_subject=lines[2],
        commit_ts_ms=int(commit_dt.timestamp() * 1000),
    )


def scan_startup_markers() -> tuple[list[StartupMarker], list[WarmupMarker]]:
    startup_markers: list[StartupMarker] = []
    warmup_markers: list[WarmupMarker] = []

    for path in current_log_files("aurora_core.log"):
        for line_number, line in iter_text_lines(path):
            startup_match = STARTUP_DONE_RE.match(line)
            if startup_match:
                payload = json.loads(startup_match.group("payload"))
                ts_ms = parse_int(payload.get("ts_ms"))
                if ts_ms is not None and str(payload.get("outcome", "")) == "completed":
                    startup_markers.append(
                        StartupMarker(
                            ts_ms=ts_ms,
                            local_ts=startup_match.group("local_ts"),
                            source_file=path.name,
                            source_line=line_number,
                            raw_line=line,
                        )
                    )
                continue

            warmup_match = WARMUP_REPORT_RE.match(line)
            if warmup_match:
                payload = json.loads(warmup_match.group("payload"))
                ts_ms = parse_int(payload.get("updated_at"))
                if ts_ms is not None:
                    warmup_markers.append(
                        WarmupMarker(
                            ts_ms=ts_ms,
                            local_ts=warmup_match.group("local_ts"),
                            source_file=path.name,
                            source_line=line_number,
                            raw_line=line,
                        )
                    )

    startup_markers.sort(key=lambda item: item.ts_ms)
    warmup_markers.sort(key=lambda item: item.ts_ms)
    return startup_markers, warmup_markers


def build_sessions(startup_markers: list[StartupMarker], warmup_markers: list[WarmupMarker]) -> list[Session]:
    sessions: list[Session] = []
    warmup_index = 0

    for index, marker in enumerate(startup_markers):
        end_ts_ms = startup_markers[index + 1].ts_ms if index + \
            1 < len(startup_markers) else None
        session = Session(
            start_ts_ms=marker.ts_ms,
            start_local_ts=marker.local_ts,
            start_source_file=marker.source_file,
            start_source_line=marker.source_line,
            start_raw_line=marker.raw_line,
            end_ts_ms=end_ts_ms,
        )

        while warmup_index < len(warmup_markers) and warmup_markers[warmup_index].ts_ms < session.start_ts_ms:
            warmup_index += 1

        if warmup_index < len(warmup_markers):
            warmup = warmup_markers[warmup_index]
            if session.end_ts_ms is None or warmup.ts_ms < session.end_ts_ms:
                session.warmup_ts_ms = warmup.ts_ms
                session.warmup_local_ts = warmup.local_ts
                session.warmup_source_file = warmup.source_file
                session.warmup_source_line = warmup.source_line
                session.warmup_raw_line = warmup.raw_line

        sessions.append(session)

    return sessions


def find_session_index(session_starts: list[int], sessions: list[Session], ts_ms: int) -> int | None:
    index = bisect_right(session_starts, ts_ms) - 1
    if index < 0:
        return None
    session = sessions[index]
    if ts_ms >= session.end_ts_ms_effective:
        return None
    return index


def classify_gate_verdict(record: dict[str, Any]) -> str | None:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        verdict = metadata.get("regime_confidence_gate_verdict")
        if isinstance(verdict, str) and verdict.strip():
            return verdict.strip().upper()
    return None


def parse_order_intents(sessions: list[Session]) -> dict[int, dict[str, DecisionIntent]]:
    session_starts = [session.start_ts_ms for session in sessions]
    decision_intents_by_session: dict[int, dict[str, DecisionIntent]] = {
        index: {} for index, _session in enumerate(sessions)
    }

    for line_number, record in iter_jsonl(LOGS_DIR / "order_log_v1.jsonl"):
        if record.get("event_type") != "ORDER_INTENT":
            continue
        if record.get("source_fsm") != "DecisionMaking":
            continue
        if record.get("strategy_id") != "aurora":
            continue

        ts_ms = parse_int(record.get("timestamp"))
        if ts_ms is None:
            continue
        session_index = find_session_index(session_starts, sessions, ts_ms)
        if session_index is None:
            continue

        gate_verdict = classify_gate_verdict(record)
        session = sessions[session_index]
        session.decision_intent_count += 1
        if gate_verdict == "ALLOW":
            session.allow_count += 1
        elif gate_verdict == "BYPASS":
            session.bypass_count += 1
        else:
            session.other_gate_count += 1

        metadata = record.get("metadata") if isinstance(
            record.get("metadata"), dict) else {}
        rid = str(record.get("rid", "")).strip()
        if not rid:
            continue

        decision_intents_by_session[session_index][rid] = DecisionIntent(
            rid=rid,
            ts_ms=ts_ms,
            source_line=line_number,
            symbol=str(record.get("symbol", "")),
            side=str(record.get("side", "")),
            regime=record.get("regime"),
            regime_confidence=record.get("regime_confidence"),
            gate_verdict=gate_verdict,
            threshold_verdict=(
                str(metadata.get("threshold_verdict", "")).upper(
                ) if metadata.get("threshold_verdict") else None
            ),
            threshold_reason=(
                str(metadata.get("threshold_reason")) if metadata.get(
                    "threshold_reason") is not None else None
            ),
            payload=record,
        )

    return decision_intents_by_session


def select_audit_session(sessions: list[Session], repair_info: GitRepairInfo) -> Session | None:
    eligible_sessions = [
        session for session in sessions if session.start_ts_ms > repair_info.commit_ts_ms]
    if not eligible_sessions:
        return None

    sessions_with_allow = [
        session for session in eligible_sessions if session.allow_count > 0]
    if sessions_with_allow:
        return sessions_with_allow[-1]

    sessions_with_activity = [
        session for session in eligible_sessions if session.decision_intent_count > 0]
    if sessions_with_activity:
        return sessions_with_activity[-1]

    return eligible_sessions[-1]


def scan_shadow_traces(session: Session) -> dict[str, TraceRecord]:
    traces: dict[str, TraceRecord] = {}

    for line_number, record in iter_jsonl(LOGS_DIR / "shadow_critical_event_journal_v1.jsonl"):
        if record.get("event_name") != "EVT:DECISION_TRACE_EMITTED":
            continue
        if record.get("strategy_id") != "aurora":
            continue

        ts_ms = parse_int(record.get("ts_ms"))
        if ts_ms is None or ts_ms < session.start_ts_ms or ts_ms >= session.end_ts_ms_effective:
            continue

        rid = str(record.get("rid", "")).strip()
        if not rid:
            continue

        traces[rid] = TraceRecord(
            rid=rid,
            ts_ms=ts_ms,
            source_line=line_number,
            source_file="shadow_critical_event_journal_v1.jsonl",
            payload=record,
        )

    return traces


def scan_failures(session: Session) -> list[FailureRecord]:
    failures: list[FailureRecord] = []
    seen_keys: set[tuple[str, int]] = set()
    local_offset = session_local_to_utc_offset(session)

    for prefix in ("aurora_core.log", "domain_decision_making.log"):
        for path in current_log_files(prefix):
            for line_number, line in iter_text_lines(path):
                emit_match = EMIT_FAIL_RE.match(line)
                if emit_match:
                    failure = FailureRecord(
                        ts_local=emit_match.group("local_ts"),
                        source_file=path.name,
                        source_line=line_number,
                        symbol=emit_match.group("symbol"),
                        rid=emit_match.group("rid"),
                        failure_type="emit_failed",
                        reason=emit_match.group("reason").strip(),
                    )
                    failure_ts_ms = infer_local_timestamp_ms(
                        failure.ts_local, local_offset)
                    if failure_ts_ms is None:
                        continue
                    if failure_ts_ms < session.start_ts_ms or failure_ts_ms >= session.end_ts_ms_effective:
                        continue
                    key = (failure.source_file, failure.source_line)
                    if key not in seen_keys:
                        failures.append(failure)
                        seen_keys.add(key)
                    continue

                payload_match = PAYLOAD_FAIL_RE.match(line)
                if payload_match:
                    failure_ts_ms = infer_local_timestamp_ms(
                        payload_match.group("local_ts"), local_offset)
                    if failure_ts_ms is None:
                        continue
                    if failure_ts_ms < session.start_ts_ms or failure_ts_ms >= session.end_ts_ms_effective:
                        continue
                    key = (path.name, line_number)
                    if key not in seen_keys:
                        failures.append(
                            FailureRecord(
                                ts_local=payload_match.group("local_ts"),
                                source_file=path.name,
                                source_line=line_number,
                                symbol=None,
                                rid=None,
                                failure_type="payload_validation_failed",
                                reason=payload_match.group("reason").strip(),
                            )
                        )
                        seen_keys.add(key)

    failures.sort(key=lambda item: (
        item.ts_local, item.source_file, item.source_line))
    return failures


def infer_local_timestamp_ms(local_ts: str, local_offset: Any) -> int | None:
    try:
        naive = datetime.strptime(local_ts, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None
    adjusted = naive + local_offset
    return int(adjusted.replace(tzinfo=timezone.utc).timestamp() * 1000)


def accepted_failure_summary(
    accepted_allow: dict[str, DecisionIntent],
    failures: list[FailureRecord],
) -> tuple[int, dict[str, set[str]]]:
    reasons_by_rid: dict[str, set[str]] = {}
    for failure in failures:
        if not failure.rid or failure.rid not in accepted_allow:
            continue
        reasons_by_rid.setdefault(failure.rid, set()).add(failure.reason)
    return len(reasons_by_rid), reasons_by_rid


def get_nested(data: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def value_is_non_null(value: Any) -> bool:
    return value is not None and value != ""


def field_presence(record: dict[str, Any], field_name: str) -> tuple[bool, bool, Any]:
    for path in FIELD_SPECS[field_name]:
        present, value = get_nested(record, path)
        if present:
            return True, value_is_non_null(value), value
    return False, False, None


def write_inventory(
    session: Session,
    accepted_allow: dict[str, DecisionIntent],
    traces: dict[str, TraceRecord],
    failures: list[FailureRecord],
) -> None:
    failures_by_rid: dict[str, list[FailureRecord]] = {}
    for failure in failures:
        if failure.rid:
            failures_by_rid.setdefault(failure.rid, []).append(failure)

    fieldnames = [
        "session_start_ts_utc",
        "session_end_ts_utc",
        "order_intent_ts_utc",
        "rid",
        "symbol",
        "side",
        "regime",
        "regime_confidence",
        "gate_verdict",
        "threshold_verdict",
        "threshold_reason",
        "decision_trace_found",
        "decision_trace_ts_utc",
        "decision_trace_source_file",
        "decision_trace_source_line",
    ]
    for field_name in FIELD_SPECS:
        fieldnames.append(f"trace_has_{field_name}")
    fieldnames.extend(
        [
            "failure_found",
            "failure_count",
            "failure_reason_sample",
        ]
    )

    with INVENTORY_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rid, intent in sorted(accepted_allow.items(), key=lambda item: (item[1].ts_ms, item[0])):
            trace = traces.get(rid)
            failure_rows = failures_by_rid.get(rid, [])
            unique_failure_reasons = sorted(
                {failure.reason for failure in failure_rows})
            row: dict[str, Any] = {
                "session_start_ts_utc": epoch_ms_to_utc(session.start_ts_ms),
                "session_end_ts_utc": epoch_ms_to_utc(session.end_ts_ms),
                "order_intent_ts_utc": epoch_ms_to_utc(intent.ts_ms),
                "rid": rid,
                "symbol": intent.symbol,
                "side": intent.side,
                "regime": intent.regime,
                "regime_confidence": intent.regime_confidence,
                "gate_verdict": intent.gate_verdict,
                "threshold_verdict": intent.threshold_verdict,
                "threshold_reason": intent.threshold_reason,
                "decision_trace_found": bool(trace),
                "decision_trace_ts_utc": epoch_ms_to_utc(trace.ts_ms) if trace else "",
                "decision_trace_source_file": trace.source_file if trace else "",
                "decision_trace_source_line": trace.source_line if trace else "",
                "failure_found": bool(failure_rows),
                "failure_count": len(unique_failure_reasons),
                "failure_reason_sample": unique_failure_reasons[0] if unique_failure_reasons else "",
            }

            for field_name in FIELD_SPECS:
                if trace is None:
                    row[f"trace_has_{field_name}"] = False
                    continue
                present, _non_null, _value = field_presence(
                    trace.payload, field_name)
                row[f"trace_has_{field_name}"] = present

            writer.writerow(row)


def write_field_coverage(
    accepted_allow: dict[str, DecisionIntent],
    traces: dict[str, TraceRecord],
) -> None:
    with COVERAGE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "field_name",
                "accepted_allow_rid_count",
                "decision_trace_present_count",
                "decision_trace_field_present_count",
                "decision_trace_field_non_null_count",
                "order_log_fallback_present_count",
                "order_log_fallback_non_null_count",
                "sample_decision_trace_rids",
                "sample_order_log_rids",
                "notes",
            ],
        )
        writer.writeheader()

        accepted_total = len(accepted_allow)
        trace_present_count = sum(1 for rid in accepted_allow if rid in traces)

        for field_name in FIELD_SPECS:
            decision_trace_present_count = 0
            decision_trace_non_null_count = 0
            order_log_present_count = 0
            order_log_non_null_count = 0
            trace_samples: list[str] = []
            order_samples: list[str] = []

            for rid, intent in accepted_allow.items():
                trace = traces.get(rid)
                if trace is not None:
                    present, non_null, _value = field_presence(
                        trace.payload, field_name)
                    if present:
                        decision_trace_present_count += 1
                        if len(trace_samples) < 5:
                            trace_samples.append(rid)
                    if non_null:
                        decision_trace_non_null_count += 1

                present, non_null, _value = field_presence(
                    intent.payload, field_name)
                if present:
                    order_log_present_count += 1
                    if len(order_samples) < 5:
                        order_samples.append(rid)
                if non_null:
                    order_log_non_null_count += 1

            notes: list[str] = []
            if decision_trace_present_count == 0 and order_log_present_count > 0:
                notes.append("fallback_only")
            if decision_trace_present_count > 0:
                notes.append("durable_trace_present")
            if not notes:
                notes.append("not_observed")

            writer.writerow(
                {
                    "field_name": field_name,
                    "accepted_allow_rid_count": accepted_total,
                    "decision_trace_present_count": trace_present_count,
                    "decision_trace_field_present_count": decision_trace_present_count,
                    "decision_trace_field_non_null_count": decision_trace_non_null_count,
                    "order_log_fallback_present_count": order_log_present_count,
                    "order_log_fallback_non_null_count": order_log_non_null_count,
                    "sample_decision_trace_rids": ";".join(trace_samples),
                    "sample_order_log_rids": ";".join(order_samples),
                    "notes": ";".join(notes),
                }
            )


def write_failures(
    session: Session,
    accepted_allow: dict[str, DecisionIntent],
    failures: list[FailureRecord],
) -> None:
    with FAILURES_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "session_start_ts_utc",
                "session_end_ts_utc",
                "failure_ts_local",
                "source_file",
                "source_line",
                "failure_type",
                "symbol",
                "rid",
                "accepted_allow_path_rid",
                "mentions_missing_inputs_signal_score",
                "reason",
            ],
        )
        writer.writeheader()
        for failure in failures:
            writer.writerow(
                {
                    "session_start_ts_utc": epoch_ms_to_utc(session.start_ts_ms),
                    "session_end_ts_utc": epoch_ms_to_utc(session.end_ts_ms),
                    "failure_ts_local": failure.ts_local,
                    "source_file": failure.source_file,
                    "source_line": failure.source_line,
                    "failure_type": failure.failure_type,
                    "symbol": failure.symbol or "",
                    "rid": failure.rid or "",
                    "accepted_allow_path_rid": failure.rid in accepted_allow if failure.rid else False,
                    "mentions_missing_inputs_signal_score": "missing_inputs.signal_score" in failure.reason,
                    "reason": failure.reason,
                }
            )


def choose_verdict(
    accepted_allow_count: int,
    accepted_trace_count: int,
    total_aurora_trace_count: int,
    failure_count: int,
    accepted_failure_rid_count: int,
    blocked: bool,
) -> str:
    if blocked:
        return "BLOCKED_OLD_RUNTIME_WINDOW"
    if accepted_allow_count > 0 and accepted_trace_count == accepted_allow_count and accepted_failure_rid_count == 0:
        return "RUNTIME_RETENTION_VERIFIED"
    if accepted_allow_count > 0 and accepted_trace_count == 0 and accepted_failure_rid_count > 0:
        return "RETENTION_STILL_BROKEN"
    if accepted_trace_count > 0 or total_aurora_trace_count > 0 or failure_count == 0:
        return "PARTIAL_RETENTION"
    return "RETENTION_STILL_BROKEN"


def write_report(
    repair_info: GitRepairInfo,
    sessions: list[Session],
    session: Session | None,
    decision_intents_by_session: dict[int, dict[str, DecisionIntent]],
    traces: dict[str, TraceRecord],
    accepted_allow: dict[str, DecisionIntent],
    failures: list[FailureRecord],
) -> str:
    blocked = session is None or session.start_ts_ms <= repair_info.commit_ts_ms
    accepted_failure_rid_count, accepted_failure_reasons = accepted_failure_summary(
        accepted_allow, failures)
    accepted_trace_count = sum(1 for rid in accepted_allow if rid in traces)
    total_aurora_trace_count = len(traces)
    verdict = choose_verdict(
        accepted_allow_count=len(accepted_allow),
        accepted_trace_count=accepted_trace_count,
        total_aurora_trace_count=total_aurora_trace_count,
        failure_count=len(failures),
        accepted_failure_rid_count=accepted_failure_rid_count,
        blocked=blocked,
    )
    assert verdict in ALLOWED_VERDICTS

    if blocked:
        selected_window_lines = [
            "- No post-T5B runtime session with aurora DecisionMaking activity was found.",
        ]
        allow_assumption_lines = [
            "- The audit could not establish a post-T5B runtime window, so allow-path classification was not applied.",
        ]
        proven_facts = [
            f"- T5B schema last-touch commit for schemas/decision_trace_emitted_v1.json: {repair_info.commit_hash} at {repair_info.commit_ts_iso}.",
            "- No eligible post-T5B aurora runtime session could be selected from current logs/aurora_core.log*.",
        ]
        inferred_findings = [
            "- Fresh-runtime retention cannot be verified until a post-T5B aurora session is observable in current logs.",
        ]
        contradictions = [
            "- Current evidence is insufficient for the requested fresh-window proof.",
        ]
        root_causes = [
            "- No post-T5B session selection was possible from the retained current logs.",
        ]
        residual = [
            "- The retention contract remains unproven for accepted allow-path decisions.",
        ]
        unproven = [
            "- Whether accepted allow-path EVT:DECISION_TRACE_EMITTED persists durably after T5B in a fresh runtime window.",
        ]
    else:
        session_index = next(index for index, candidate in enumerate(
            sessions) if candidate is session)
        session_intents = decision_intents_by_session[session_index]
        denied_trace_count = total_aurora_trace_count - accepted_trace_count
        missing_inputs_signal_score_failures = sum(
            1 for failure in failures if "missing_inputs.signal_score" in failure.reason
        )
        accepted_failure_reason_text = "; ".join(
            sorted({reason for reasons in accepted_failure_reasons.values()
                   for reason in reasons})
        )

        field_highlights: list[str] = []
        for field_name in FIELD_SPECS:
            present_count = 0
            for rid in accepted_allow:
                trace = traces.get(rid)
                if trace is None:
                    continue
                present, _non_null, _value = field_presence(
                    trace.payload, field_name)
                if present:
                    present_count += 1
            if field_name in {"regime", "regime_confidence", "regime_confidence_gate_verdict", "price_motion_context", "missing_inputs", "safety_gate_snapshot", "low_vol_cost_floor"}:
                field_highlights.append(
                    f"- {field_name}: present on {present_count}/{len(accepted_allow)} accepted allow-path durable traces."
                )

        accepted_samples = [
            rid for rid in sorted(accepted_allow, key=lambda current_rid: accepted_allow[current_rid].ts_ms)[:5]
        ]
        trace_samples = [rid for rid in accepted_samples if rid in traces]

        selected_window_lines = [
            f"- T5B schema last-touch commit for schemas/decision_trace_emitted_v1.json: {repair_info.commit_hash} at {repair_info.commit_ts_iso}.",
            f"- Selected post-T5B runtime session start: {session.start_local_ts} from {session.start_source_file}:{session.start_source_line}.",
            f"- Selected post-T5B runtime session end: {epoch_ms_to_utc(session.end_ts_ms) if session.end_ts_ms is not None else 'open-ended current session'}.",
            (
                f"- Attached startup warmup marker: {session.warmup_local_ts} from "
                f"{session.warmup_source_file}:{session.warmup_source_line}."
                if session.warmup_local_ts and session.warmup_source_file and session.warmup_source_line
                else "- No separate STARTUP_WARMUP_REPORT marker was attached to the selected session."
            ),
        ]
        allow_assumption_lines = [
            "- Accepted allow-path was interpreted as current logs/order_log_v1.jsonl DecisionMaking ORDER_INTENT rows with strategy_id=aurora and metadata.regime_confidence_gate_verdict=ALLOW.",
            f"- BYPASS rows were excluded from the primary allow-path population; current selected session contained {session.bypass_count} BYPASS DecisionMaking ORDER_INTENT rows.",
        ]
        proven_facts = [
            *selected_window_lines,
            *allow_assumption_lines,
            f"- Selected session aurora DecisionMaking ORDER_INTENT rows: {session.decision_intent_count} total, {session.allow_count} ALLOW, {session.bypass_count} BYPASS, {session.other_gate_count} other/unknown.",
            f"- Accepted allow-path ORDER_INTENT rows in the selected session: {len(accepted_allow)}.",
            f"- Durable current-session aurora EVT:DECISION_TRACE_EMITTED rows in logs/shadow_critical_event_journal_v1.jsonl: {total_aurora_trace_count}.",
            f"- Durable accepted allow-path EVT:DECISION_TRACE_EMITTED rows: {accepted_trace_count}/{len(accepted_allow)}.",
            f"- Durable current-session traces not tied to accepted allow-path RIDs: {denied_trace_count}.",
            f"- Current-session EVT:DECISION_TRACE_EMITTED failure rows in current top-level aurora/domain logs: {len(failures)}.",
            f"- Current-session failure rows mentioning missing_inputs.signal_score: {missing_inputs_signal_score_failures}.",
            f"- Accepted allow-path RIDs with current-session emit-failed evidence: {accepted_failure_rid_count}/{len(accepted_allow)}.",
            (
                f"- Accepted allow-path failure signature: {accepted_failure_reason_text}."
                if accepted_failure_reason_text
                else "- No accepted allow-path failure signature was observed."
            ),
            f"- Accepted allow-path sample RIDs: {'; '.join(accepted_samples) if accepted_samples else 'none'}.",
            f"- Accepted allow-path sample durable trace RIDs: {'; '.join(trace_samples) if trace_samples else 'none'}.",
        ]

        inferred_findings = []
        if accepted_trace_count == len(accepted_allow) and len(accepted_allow) > 0:
            inferred_findings.append(
                "- Every accepted allow-path DecisionMaking ORDER_INTENT in the selected post-T5B session had a durable EVT:DECISION_TRACE_EMITTED record."
            )
        elif accepted_trace_count == 0 and total_aurora_trace_count > 0:
            inferred_findings.append(
                "- Durable EVT:DECISION_TRACE_EMITTED persistence exists in the selected post-T5B session, but the observed durable traces are confined to non-allow-path aurora decisions rather than the accepted allow-path population."
            )
        elif accepted_trace_count == 0:
            inferred_findings.append(
                "- No durable EVT:DECISION_TRACE_EMITTED was found for accepted allow-path decisions in the selected post-T5B session."
            )
        else:
            inferred_findings.append(
                "- Accepted allow-path durable retention is present for part of the selected session population but not for all accepted decisions."
            )
        if missing_inputs_signal_score_failures == 0:
            inferred_findings.append(
                "- The old missing_inputs.signal_score schema-failure signature does not appear in the selected current-session failure surface."
            )
        else:
            inferred_findings.append(
                "- The old missing_inputs.signal_score schema-failure signature is still present in the selected current-session failure surface."
            )
        if accepted_failure_rid_count > 0:
            inferred_findings.append(
                "- Accepted allow-path emit failures are still occurring in the selected post-T5B session, but the active schema rejection has shifted from the old missing_inputs.signal_score signature to unexpected additional properties on the emitted payload."
            )
        inferred_findings.extend(field_highlights)
        inferred_findings.append(
            "- Evidence is strong enough for accepted-path retention only if accepted allow-path durable traces are present; otherwise T3D/T4B replay rerun remains unsafe for this contract."
        )

        contradictions = []
        if accepted_trace_count == 0 and total_aurora_trace_count > 0:
            contradictions.append(
                "- Current runtime contradicts the older fully-broken baseline because durable decision traces now exist, but it does not yet prove accepted allow-path retention if the accepted inventory still lacks durable matches."
            )
        if not failures and accepted_trace_count < len(accepted_allow):
            contradictions.append(
                "- The selected session can show accepted allow-path gaps without reproducing the old emit-failed log signature, so absence of current failures is not sufficient by itself to prove allow-path durability."
            )
        if not contradictions:
            contradictions.append(
                "- No material contradictions were found inside the selected current-session evidence set.")

        root_causes = []
        if accepted_trace_count == len(accepted_allow) and len(accepted_allow) > 0:
            root_causes.append(
                "- T5B schema acceptance plus current runtime retention appear sufficient for the selected accepted allow-path population."
            )
        elif accepted_trace_count == 0 and accepted_failure_rid_count > 0:
            root_causes.append(
                "- Accepted allow-path persistence is still blocked by a current post-T5B schema rejection: unexpected additional properties on EVT:DECISION_TRACE_EMITTED payloads."
            )
        elif accepted_trace_count == 0 and total_aurora_trace_count > 0:
            root_causes.append(
                "- The selected runtime shows a path-class split: EVT:DECISION_TRACE_EMITTED persists for some aurora decisions, but accepted allow-path persistence remains absent or unproven."
            )
        elif accepted_trace_count == 0 and failures:
            root_causes.append(
                "- Accepted allow-path persistence still appears blocked by current-session emit or payload-validation failures."
            )
        else:
            root_causes.append(
                "- Accepted allow-path retention is only partially evidenced in the selected current session."
            )

        residual = [
            "- Durable accepted allow-path retention is only as strong as the selected session and retained logs; future fresh sessions can still regress.",
        ]
        if accepted_trace_count < len(accepted_allow):
            residual.append(
                "- Replay-critical downstream work should remain blocked until accepted allow-path durable traces and field coverage are fully observed in a fresh runtime session."
            )

        unproven = [
            "- Whether the accepted allow-path contract stays durable across later post-T5B restarts beyond the selected session.",
        ]
        if accepted_trace_count < len(accepted_allow):
            unproven.append(
                "- Whether replay-critical fields absent from accepted allow-path durable traces are now attached elsewhere or are still missing at emit time."
            )

    report_lines = [
        "# AGENT_REPORT_V1",
        "",
        "## Executive Summary",
        (
            f"{verdict}: selected post-T5B runtime evidence "
            + (
                "proves durable accepted allow-path EVT:DECISION_TRACE_EMITTED retention."
                if verdict == "RUNTIME_RETENTION_VERIFIED"
                else "does not yet fully prove durable accepted allow-path EVT:DECISION_TRACE_EMITTED retention."
            )
        ),
        "",
        "## Proven Facts",
        *proven_facts,
        "",
        "## Inferred Findings",
        *inferred_findings,
        "",
        "## Contradictions / Evidence Gaps",
        *contradictions,
        "",
        "## Root Cause Candidates",
        *root_causes,
        "",
        "## Operational Risk",
        "- Observability Gap" if blocked or verdict != "RUNTIME_RETENTION_VERIFIED" else "- Runtime",
        "",
        "## Files / Areas Touched",
        "- tools/runtime_forensics_tmp/t6b_post_t5b_trace_retention_audit.py",
        "- reports/runtime_forensics/T6B_post_t5b_trace_retention/post_t5b_accepted_trace_inventory.csv",
        "- reports/runtime_forensics/T6B_post_t5b_trace_retention/post_t5b_replay_field_coverage.csv",
        "- reports/runtime_forensics/T6B_post_t5b_trace_retention/decision_trace_schema_failures_post_t5b.csv",
        "- reports/runtime_forensics/T6B_post_t5b_trace_retention/T6B_POST_T5B_TRACE_RETENTION_REPORT.md",
        "",
        "## Validation Performed",
        "- Parsed current top-level logs/aurora_core.log* startup markers and selected a post-T5B aurora runtime session.",
        "- Parsed current logs/order_log_v1.jsonl DecisionMaking ORDER_INTENT rows and classified ALLOW vs BYPASS.",
        "- Parsed current logs/shadow_critical_event_journal_v1.jsonl EVT:DECISION_TRACE_EMITTED rows for the selected session.",
        "- Parsed current top-level logs/aurora_core.log* and logs/domain_decision_making.log* for EVT:DECISION_TRACE_EMITTED failure signatures.",
        "",
        "## Residual Risk",
        *residual,
        "",
        "## What Remains Unproven",
        *unproven,
        "",
        "## Minimal Safe Verdict",
        f"- {verdict}",
    ]

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return verdict


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    repair_info = parse_git_repair_info()
    startup_markers, warmup_markers = scan_startup_markers()
    sessions = build_sessions(startup_markers, warmup_markers)
    decision_intents_by_session = parse_order_intents(sessions)
    session = select_audit_session(sessions, repair_info)

    if session is None or session.start_ts_ms <= repair_info.commit_ts_ms:
        traces: dict[str, TraceRecord] = {}
        accepted_allow: dict[str, DecisionIntent] = {}
        failures: list[FailureRecord] = []
        with INVENTORY_PATH.open("w", encoding="utf-8", newline="") as inventory_handle:
            writer = csv.writer(inventory_handle)
            writer.writerow(["blocked", "reason"])
            writer.writerow(
                [True, "No post-T5B session with aurora DecisionMaking activity was selectable."])
        with COVERAGE_PATH.open("w", encoding="utf-8", newline="") as coverage_handle:
            writer = csv.writer(coverage_handle)
            writer.writerow(["blocked", "reason"])
            writer.writerow(
                [True, "No post-T5B session with aurora DecisionMaking activity was selectable."])
        with FAILURES_PATH.open("w", encoding="utf-8", newline="") as failure_handle:
            writer = csv.writer(failure_handle)
            writer.writerow(["blocked", "reason"])
            writer.writerow(
                [True, "No post-T5B session with aurora DecisionMaking activity was selectable."])
        verdict = write_report(repair_info, sessions, session,
                               decision_intents_by_session, traces, accepted_allow, failures)
        print(f"selected_session_start_utc=")
        print("selected_session_allow_count=0")
        print("selected_session_accepted_trace_count=0")
        print("selected_session_failure_count=0")
        print(f"verdict={verdict}")
        return

    session_index = next(index for index, candidate in enumerate(
        sessions) if candidate is session)
    session_intents = decision_intents_by_session[session_index]
    accepted_allow = {
        rid: intent for rid, intent in session_intents.items() if intent.gate_verdict == "ALLOW"
    }
    traces = scan_shadow_traces(session)
    failures = scan_failures(session)

    write_inventory(session, accepted_allow, traces, failures)
    write_field_coverage(accepted_allow, traces)
    write_failures(session, accepted_allow, failures)
    verdict = write_report(
        repair_info=repair_info,
        sessions=sessions,
        session=session,
        decision_intents_by_session=decision_intents_by_session,
        traces=traces,
        accepted_allow=accepted_allow,
        failures=failures,
    )

    accepted_trace_count = sum(1 for rid in accepted_allow if rid in traces)
    print(f"selected_session_start_utc={epoch_ms_to_utc(session.start_ts_ms)}")
    print(f"selected_session_end_utc={epoch_ms_to_utc(session.end_ts_ms)}")
    print(f"selected_session_allow_count={len(accepted_allow)}")
    print(f"selected_session_bypass_count={session.bypass_count}")
    print(f"selected_session_accepted_trace_count={accepted_trace_count}")
    print(f"selected_session_aurora_trace_count={len(traces)}")
    print(f"selected_session_failure_count={len(failures)}")
    print(f"verdict={verdict}")


if __name__ == "__main__":
    main()
