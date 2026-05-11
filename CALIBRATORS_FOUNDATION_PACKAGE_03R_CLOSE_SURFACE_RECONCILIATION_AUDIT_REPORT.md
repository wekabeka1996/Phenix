# AGENT_REPORT_V1

## Executive Summary
The 03R close-surface audit shows that the remaining 13 close-expected unmatched rows are primarily a runtime close-emission observability problem, not a builder-denominator problem: 8 rows have trade_lifecycle terminal-close proof with no canonical order_log POSITION_CLOSED, 2 rows emit alternative terminal order events instead of canonical close emission, 1 row is decision-ledger-realized-only, and 2 rows remain inconclusive.

## Proven Facts
- The frozen 03Q artifact denominator remained unchanged during this audit: close_expected_rows=17, close_matched_rows=4, close_unmatched_rows=13, execution_to_close_coverage_pct=23.5294, and legacy_total_decision_close_coverage_pct=4.3011.
- The 03R ledger at calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_EXPECTED_UNMATCHED_LEDGER.json parsed successfully and reported 13 close-expected unmatched rows.
- The 03R reconciliation matrix at calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_SURFACE_RECONCILIATION_MATRIX.json parsed successfully and reported bucket_counts={ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED: 8, ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT: 2, DECISION_LEDGER_REALIZED_ONLY: 1, INCONCLUSIVE: 2, all other requested buckets: 0}.
- The 03R order-versus-lifecycle audit at calibrators/datasets/close_surface_reconciliation_post_03r/ORDER_LOG_VS_TRADE_LIFECYCLE_CLOSE_AUDIT.md reported rows_with_exact_order_position_closed=0, rows_with_trade_lifecycle_terminal_close=10, rows_with_order_log_alternative_terminal_event=2, rows_with_decision_ledger_realized_fields=1, and rows_classified_runtime_logging_gap=0.
- The 03R decision-ledger realized-fields audit at calibrators/datasets/close_surface_reconciliation_post_03r/DECISION_LEDGER_REALIZED_FIELDS_AUDIT.md reported exactly 1 row with decision-ledger realized fields and 1 row in the DECISION_LEDGER_REALIZED_ONLY bucket.
- The 03N baseline report documented the legacy metric as eligible_decision_rows=93, matched_rows=4, unmatched_rows=89, match_coverage_pct=4.3011 on the same frozen post-03K cohort.
- Required validation passed: 22 tests succeeded across the new 03R auditor tests, existing realized_outcome_builder tests, existing runtime_close_coverage_audit tests, and the calibrators import boundary test.

## Inferred Findings
- The dominant unresolved surface is missing canonical runtime close emission on the authority order_log path, not denominator contamination and not a widespread narrow-bridge builder miss.
- Ten of the thirteen rows are already runtime-oriented without ambiguity: eight have trade_lifecycle terminal-close evidence while exact-rid order_log never emitted POSITION_CLOSED, and two replace canonical close emission with ORDER_CANCELLED or ORDER_TIMEOUT terminal patterns.
- The builder-bridge hypothesis is not the leading explanation for this cohort because the 03R audit found zero rows in LIFECYCLE_ID_BRIDGE_AVAILABLE, TRADE_ID_BRIDGE_AVAILABLE, and BUILDER_CANONICALIZATION_GAP.
- The decision-ledger-only realized row is real but minority evidence. It does not outweigh the larger runtime close-emission gap across the cohort.

## Contradictions / Evidence Gaps
- Two rows remain INCONCLUSIVE: aurora_ETHUSDT_1778428202947 and aurora_XRPUSDT_1778430903673. For both rows, the frozen snapshot shows only ORDER_INTENT and ORDER_PLACED on order_log and no terminal-close proof on trade_lifecycle.
- One row, aurora_BTCUSDT_1778429706498, carries realized_pnl_net and fees in the decision ledger while the frozen order_log and trade_lifecycle snapshots do not expose canonical close proof. That is a field-authority contradiction, but it affects only 1 / 13 rows.
- This package audited only the frozen 03Q snapshot surfaces. It does not prove whether the missing canonical close emission is a transient live-window issue or a durable runtime contract defect.

## Root Cause Candidates
- Primary root cause candidate: the runtime often closes positions without persisting a canonical POSITION_CLOSED row on the authority order_log surface even when trade_lifecycle later reflects terminal close.
- Secondary root cause candidate: some close paths emit alternative terminal order events such as ORDER_CANCELLED and ORDER_TIMEOUT instead of canonical close completion evidence.
- Tertiary root cause candidate: a minority decision-ledger authority drift allows realized fields to appear without matching canonical close evidence on retained runtime surfaces.

## Operational Risk
- Observability Gap
- Correctness

## Files / Areas Touched
- calibrators/datasets/audit_close_surface_reconciliation.py
- tests/calibrators/test_close_surface_reconciliation_audit.py
- calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_EXPECTED_UNMATCHED_LEDGER.json
- calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_EXPECTED_UNMATCHED_LEDGER.csv
- calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_EXPECTED_UNMATCHED_LEDGER.md
- calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_SURFACE_RECONCILIATION_MATRIX.json
- calibrators/datasets/close_surface_reconciliation_post_03r/CLOSE_SURFACE_RECONCILIATION_MATRIX.md
- calibrators/datasets/close_surface_reconciliation_post_03r/ORDER_LOG_VS_TRADE_LIFECYCLE_CLOSE_AUDIT.md
- calibrators/datasets/close_surface_reconciliation_post_03r/DECISION_LEDGER_REALIZED_FIELDS_AUDIT.md
- CALIBRATORS_FOUNDATION_PACKAGE_03R_CLOSE_SURFACE_RECONCILIATION_AUDIT_REPORT.md

## Validation Performed
- Ran c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_close_surface_reconciliation_audit.py -q and observed 2 / 2 passing.
- Ran c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_close_surface_reconciliation_audit.py tests/calibrators/test_realized_outcome_builder.py tests/calibrators/test_runtime_close_coverage_audit.py tests/test_calibrators_import_boundary.py -q and observed 22 / 22 passing.
- Ran c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m calibrators.datasets.audit_close_surface_reconciliation --realized-artifact-dir artifacts/calibration_datasets/_post_03k_realized_outcome_03q --out-dir calibrators/datasets/close_surface_reconciliation_post_03r and generated the required 03R artifacts.
- Parsed all generated JSON outputs successfully: CLOSE_EXPECTED_UNMATCHED_LEDGER.json and CLOSE_SURFACE_RECONCILIATION_MATRIX.json.

## Residual Risk
- The audit is descriptive only. It narrows the failure surface but does not restore the missing canonical close evidence.
- Two inconclusive rows still lack decisive close proof on retained snapshot surfaces, so any direct runtime-fix package should preserve a guardrail for ambiguous cases.
- The single decision-ledger-realized-only row remains unresolved and may still require later authority audit work after the dominant runtime close-emission gap is addressed.

## What Remains Unproven
- Whether the missing POSITION_CLOSED evidence is lost at emission time, dropped before retention, or replaced by another runtime event path upstream of order_log persistence.
- Whether the two inconclusive rows would become classifiable with a wider retained runtime surface or a fresh live-window capture.
- Whether the lone decision-ledger-realized-only row is an isolated anomaly or the first visible example of a broader decision-ledger authority drift.

## Minimal Safe Verdict
Package 03R is complete as a bounded forensic audit. The evidence supports exactly one next package: 03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR. The dominant 03R cohort is runtime-oriented, not builder-oriented: 10 / 13 rows already point to missing or non-canonical runtime close emission on the retained authority surfaces, while no rows currently justify taking 03S_REALIZED_BUILDER_NARROW_BRIDGE_REPAIR as the next step.
