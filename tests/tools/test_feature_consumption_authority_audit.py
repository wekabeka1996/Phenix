from pathlib import Path

from tools.audits.feature_consumption_authority_audit import (
    VERDICTS,
    build_report,
    determine_verdict,
    write_report,
    build_report_rows,
    build_evidence_rows,
    write_audit_bundle,
)


def test_feature_authority_audit_report_contains_required_sections() -> None:
    report = build_report()
    assert "## Source Inventory" in report
    assert "## Feature Matrix" in report
    assert "## Live Decision Consumer Map" in report
    assert "## Shadow-only / Diagnostic-only Inventory" in report
    assert "## Dead Config Inventory" in report
    assert "## Circular Logic Risks" in report
    assert "## Missing Join Keys" in report
    assert "## Recommended Promotion Candidates" in report
    assert "## Forbidden Promotion Candidates" in report
    assert "## Next Exact Package Recommendation" in report


def test_feature_authority_audit_verdict_is_valid() -> None:
    verdict = determine_verdict(build_report_rows(build_evidence_rows()))
    assert verdict in VERDICTS


def test_feature_authority_audit_includes_live_shadow_and_unused_claims() -> None:
    rows = build_evidence_rows()
    claim_classes = {str(row["claim_class"]) for row in rows}
    usage_types = {str(row["usage_type"]) for row in rows}
    assert "live_authoritative" in claim_classes
    assert "shadow_only" in claim_classes
    assert "unused" in usage_types


def test_feature_authority_audit_writes_output(tmp_path: Path) -> None:
    out = tmp_path / "FEATURE_CONSUMPTION_AUTHORITY_AUDIT_V1.md"
    evidence = tmp_path / "feature_authority" / "FEATURE_CONSUMPTION_AUTHORITY_EVIDENCE_ROWS_V1.jsonl"
    rows, _ = write_audit_bundle(report_path=out, evidence_path=evidence)
    text = out.read_text(encoding="utf-8")
    evidence_lines = evidence.read_text(encoding="utf-8").strip().splitlines()
    assert "Verdict:" in text
    assert "| feature name |" in text
    assert len(rows) == len(evidence_lines)
    first = __import__("json").loads(evidence_lines[0])
    assert {"feature_name", "producer_path", "payload_key", "consumer_path", "usage_type", "evidence_method", "confidence", "claim_class", "decision_effect"} <= set(first)
