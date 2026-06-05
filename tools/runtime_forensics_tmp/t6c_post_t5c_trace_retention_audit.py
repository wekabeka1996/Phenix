from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SCRIPT_PATH = Path(__file__).with_name(
    "t6b_post_t5b_trace_retention_audit.py"
)
REPORT_DIR = ROOT / "reports" / "runtime_forensics" / "T6C_post_t5c_trace_retention"
REPORT_PATH = REPORT_DIR / "T6C_POST_T5C_TRACE_RETENTION_REPORT.md"
INVENTORY_PATH = REPORT_DIR / "post_t5c_accepted_trace_inventory.csv"
COVERAGE_PATH = REPORT_DIR / "post_t5c_replay_field_coverage.csv"
FAILURES_PATH = REPORT_DIR / "decision_trace_schema_failures_post_t5c.csv"

ANTI_PEAK_SIGNATURE_TOKENS = (
    "anti_peak_observability",
    "anti_flat_sigma_value_source",
    "anti_fomo_sigma_value_source",
    "window_sec_value_source",
)
REPLAY_CRITICAL_FIELDS = (
    "regime",
    "regime_confidence",
    "regime_confidence_gate_verdict",
    "pm_norm_10s",
    "pm_norm_60s",
    "pm_norm_300s",
    "price_motion_context",
    "missing_inputs",
    "safety_gate_snapshot",
    "low_vol_cost_floor",
)


def load_base_module():
    spec = importlib.util.spec_from_file_location(
        "t6b_post_t5b_trace_retention_audit_base", BASE_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load base audit script: {BASE_SCRIPT_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_output_paths(module) -> None:
    module.REPORT_DIR = REPORT_DIR
    module.REPORT_PATH = REPORT_PATH
    module.INVENTORY_PATH = INVENTORY_PATH
    module.COVERAGE_PATH = COVERAGE_PATH
    module.FAILURES_PATH = FAILURES_PATH


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def parse_int(value: str | None) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def filtered_inventory_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("rid")]


def rewrite_report_labels(text: str) -> str:
    replacements = [
        (
            "tools/runtime_forensics_tmp/t6b_post_t5b_trace_retention_audit.py",
            "tools/runtime_forensics_tmp/t6c_post_t5c_trace_retention_audit.py",
        ),
        (
            "reports/runtime_forensics/T6B_post_t5b_trace_retention",
            "reports/runtime_forensics/T6C_post_t5c_trace_retention",
        ),
        (
            "T6B_POST_T5B_TRACE_RETENTION_REPORT.md",
            "T6C_POST_T5C_TRACE_RETENTION_REPORT.md",
        ),
        (
            "post_t5b_accepted_trace_inventory.csv",
            "post_t5c_accepted_trace_inventory.csv",
        ),
        (
            "post_t5b_replay_field_coverage.csv",
            "post_t5c_replay_field_coverage.csv",
        ),
        (
            "decision_trace_schema_failures_post_t5b.csv",
            "decision_trace_schema_failures_post_t5c.csv",
        ),
        ("post-T5B", "post-T5C"),
        ("post_t5b", "post_t5c"),
        ("T5B", "T5C"),
        ("T6B", "T6C"),
    ]

    for old, new in replacements:
        text = text.replace(old, new)
    return text


def build_requested_answers(
    inventory_rows: list[dict[str, str]],
    coverage_rows: list[dict[str, str]],
    failure_rows: list[dict[str, str]],
) -> list[str]:
    accepted_rows = filtered_inventory_rows(inventory_rows)
    accepted_count = len(accepted_rows)
    accepted_trace_count = sum(
        1 for row in accepted_rows if is_truthy(row.get("decision_trace_found"))
    )
    accepted_failure_count = sum(
        1 for row in accepted_rows if is_truthy(row.get("failure_found"))
    )
    anti_peak_count = sum(
        1
        for row in failure_rows
        if any(token in (row.get("reason") or "") for token in ANTI_PEAK_SIGNATURE_TOKENS)
    )
    missing_inputs_count = sum(
        1
        for row in failure_rows
        if "missing_inputs.signal_score" in (row.get("reason") or "")
    )

    coverage_by_field = {
        row.get("field_name", ""): row
        for row in coverage_rows
        if row.get("field_name")
    }
    replay_field_summaries: list[str] = []
    replay_field_gaps: list[str] = []
    for field_name in REPLAY_CRITICAL_FIELDS:
        row = coverage_by_field.get(field_name)
        if row is None:
            replay_field_gaps.append(f"{field_name}=0/0")
            continue
        present_count = parse_int(
            row.get("decision_trace_field_present_count"))
        trace_present_count = parse_int(
            row.get("decision_trace_present_count"))
        notes = row.get("notes") or ""
        replay_field_summaries.append(
            f"{field_name} {present_count}/{trace_present_count} notes={notes or 'none'}"
        )
        if trace_present_count > 0 and present_count < trace_present_count:
            replay_field_gaps.append(
                f"{field_name}={present_count}/{trace_present_count}")

    if accepted_count == 0:
        replay_verdict = (
            "No. No accepted allow-path population was selected in the post-T5C window, so T3D/T4B rerun readiness remains unproven."
        )
    elif accepted_trace_count != accepted_count:
        replay_verdict = (
            f"No. Accepted durable trace coverage is incomplete at {accepted_trace_count}/{accepted_count}."
        )
    elif accepted_failure_count > 0:
        replay_verdict = (
            f"No. Accepted allow-path still shows {accepted_failure_count} RID-level failure surfaces in current top-level logs."
        )
    elif replay_field_gaps:
        replay_verdict = (
            "No. Durable accepted traces exist for every accepted RID, but replay-critical field gaps remain: "
            + "; ".join(replay_field_gaps)
            + "."
        )
    else:
        replay_verdict = (
            "Yes. Every accepted allow-path RID has a durable trace, no accepted RID shows current-session schema failures, and the audited replay-critical fields are present on the accepted durable traces."
        )

    durable_answer = (
        f"Yes. {accepted_trace_count}/{accepted_count} accepted allow-path RIDs produced durable EVT:DECISION_TRACE_EMITTED rows."
        if accepted_count > 0 and accepted_trace_count == accepted_count
        else f"Partial. {accepted_trace_count}/{accepted_count} accepted allow-path RIDs produced durable EVT:DECISION_TRACE_EMITTED rows."
        if accepted_count > 0
        else "Unproven. No accepted allow-path RIDs were selected for the post-T5C session."
    )
    accepted_failure_answer = (
        "No. No accepted allow-path RID produced a current-session schema validation failure in the audited top-level logs."
        if accepted_failure_count == 0
        else f"Yes. {accepted_failure_count} accepted allow-path RIDs still show current-session failure evidence."
    )
    anti_peak_answer = (
        "Yes. The T6B anti_peak failure signature is absent from the audited current-session top-level failure surface."
        if anti_peak_count == 0
        else f"No. {anti_peak_count} current-session failure rows still mention the T6B anti_peak signature."
    )
    missing_inputs_answer = (
        "Yes. The old missing_inputs.signal_score failure signature remains absent in the audited current-session top-level failure surface."
        if missing_inputs_count == 0
        else f"No. {missing_inputs_count} current-session failure rows still mention missing_inputs.signal_score."
    )
    replay_fields_answer = (
        "Replay-critical field coverage by durable accepted trace: "
        + "; ".join(replay_field_summaries)
        if replay_field_summaries
        else "Replay-critical field coverage could not be established from the generated coverage CSV."
    )

    return [
        "## Requested Answers",
        f"- Durable accepted allow-path retention: {durable_answer}",
        f"- Accepted RID schema validation failures: {accepted_failure_answer}",
        f"- T6B anti_peak signature disappearance: {anti_peak_answer}",
        f"- Old missing_inputs.signal_score signature: {missing_inputs_answer}",
        f"- Replay-critical fields: {replay_fields_answer}",
        f"- T3D/T4B rerun readiness on this window: {replay_verdict}",
    ]


def postprocess_outputs() -> None:
    inventory_rows = load_csv_rows(INVENTORY_PATH)
    coverage_rows = load_csv_rows(COVERAGE_PATH)
    failure_rows = load_csv_rows(FAILURES_PATH)

    report_text = REPORT_PATH.read_text(encoding="utf-8")
    report_text = rewrite_report_labels(report_text).rstrip()
    requested_answers = build_requested_answers(
        inventory_rows=inventory_rows,
        coverage_rows=coverage_rows,
        failure_rows=failure_rows,
    )
    report_text = "\n".join([report_text, "", *requested_answers, ""])
    REPORT_PATH.write_text(report_text, encoding="utf-8")


def main() -> None:
    module = load_base_module()
    configure_output_paths(module)
    module.main()
    postprocess_outputs()


if __name__ == "__main__":
    main()
