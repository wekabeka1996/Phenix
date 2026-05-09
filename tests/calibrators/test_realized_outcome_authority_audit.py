from pathlib import Path

from calibrators.datasets.audit_realized_outcome_authority import (
    _classify_code_ref,
    _decide_authority_status,
    _infer_invocation_mode,
    _recommend_canonical_source,
)


def test_classify_code_ref_marks_writer_reader_and_docs() -> None:
    assert _classify_code_ref(
        Path("scripts/forensics/build_order_flow_master.py"),
        'df.to_csv(REPORTS_DIR / "executed_trades_master.csv", index=False)',
    ) == "active_writer"
    assert _classify_code_ref(
        Path("scripts/forensics/generate_business_report.py"),
        'trades = pd.read_csv(REPORTS_DIR / "executed_trades_master.csv")',
    ) == "reader"
    assert _classify_code_ref(
        Path("CALIBRATORS_FOUNDATION_PACKAGE_03D_JOIN_KEY_COVERAGE_AUDIT_REPORT.md"),
        "reports/executed_trades_master.csv exists, has header fields only, and has 0 rows.",
    ) == "historical_report"


def test_decide_authority_status_manual_writer_is_convenience_report() -> None:
    assert _decide_authority_status(
        report_rows=0,
        invocation_mode="manual_cli_only_unreferenced",
        report_stale_vs_runtime=True,
        active_writer_count=1,
    ) == "DERIVED_CONVENIENCE_REPORT_ONLY"


def test_recommend_source_prefers_bridge_when_master_not_canonical() -> None:
    assert _recommend_canonical_source(
        authority_status="DERIVED_CONVENIENCE_REPORT_ONLY",
        decision_orderlog_exact_bridge=True,
    ) == "BUILD_BRIDGE_DATASET_DECISION_LEDGER_TO_ORDER_LOG"


def test_infer_invocation_mode_ignores_non_runtime_self_mentions() -> None:
    refs = {
        "executed_trades_master.csv": [
            {
                "path": "scripts/forensics/build_order_flow_master.py",
                "snippet": 'df.to_csv(REPORTS_DIR / "executed_trades_master.csv", index=False)',
            }
        ],
        "rejected_attempts_master.csv": [],
        "order_attempts_master.csv": [],
    }
    assert _infer_invocation_mode(refs) == "manual_cli_only_unreferenced"
