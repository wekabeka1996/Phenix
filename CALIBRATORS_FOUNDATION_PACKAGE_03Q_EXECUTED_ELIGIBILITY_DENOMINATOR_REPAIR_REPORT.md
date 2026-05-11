# AGENT_REPORT_V1

## Executive Summary
Offline realized-outcome coverage semantics were repaired for the frozen post-03K cohort so rejected or not-executed decision rows no longer dilute executed-position close coverage; the same snapshot that previously read as 4 / 93 = 4.3011% now reads as 4 / 17 = 23.5294% for close-expected coverage.

## Proven Facts
- The 03N baseline report recorded eligible_decision_rows=93, matched_rows=4, unmatched_rows=89, and match_coverage_pct=4.3011 using the total decision cohort as the coverage denominator.
- The rebuilt 03Q realized artifact at artifacts/calibration_datasets/_post_03k_realized_outcome_03q/dataset_manifest.json reports total_decision_rows=93, rejected_or_not_executed_rows=75, execution_eligible_rows=18, close_expected_rows=17, close_matched_rows=4, exact_roundtrip_rows=3, and execution_to_close_coverage_pct=23.5294.
- The builder denominator audit at artifacts/calibration_datasets/_post_03k_realized_outcome_03q/denominator_audit.json reports the same repaired denominator counts and also preserves legacy_total_decision_close_coverage_pct=4.3011 for comparison.
- The runtime close coverage audit at calibrators/datasets/runtime_close_coverage_post_03q/denominator_audit.json matches the builder exactly: total_decision_rows=93, rejected_or_not_executed_rows=75, close_expected_rows=17, close_matched_rows=4, execution_to_close_coverage_pct=23.5294.
- The unmatched classification audit at calibrators/datasets/runtime_close_coverage_post_03q/unmatched_classification.json reports classification_counts={NOT_EXECUTED_OR_REJECTED: 75, CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY: 12, CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED: 1, INCONCLUSIVE: 1}.
- Focused validation passed after the repair: 47 targeted tests passed across realized_outcome_builder, runtime_close_coverage_audit, downstream dataset builders, and calibrator import boundary checks.

## Inferred Findings
- The old 4.3011% figure was a denominator semantics problem, not proof that 89 executed positions were all missing close outcomes.
- On the frozen post-03K cohort, 75 of the 93 decision rows belong in a reject or not-executed cohort and should stay visible for rejection calibration, but they should not count against executed-position close coverage.
- The repaired coverage denominator is the close-expected cohort. On this snapshot that cohort is 17 rows, so the same 4 matched realized rows produce 23.5294% close coverage instead of 4.3011%.
- After the denominator repair, the remaining gap is concentrated in rows with close evidence already visible in trade_lifecycle rather than in rows with no execution evidence at all.

## Contradictions / Evidence Gaps
- A validation rerun exposed one contradictory row where a realized matched close still carried a reject terminal label. The denominator logic was tightened so concrete execution evidence overrides stale reject labels for offline coverage accounting.
- The repair changes measurement semantics only. It does not recover the 13 close-expected rows that still fail to emit realized rows in the frozen snapshot.
- This package validates frozen-snapshot offline semantics. It does not by itself prove that a fresh post-03Q live runtime window will produce the same denominator split.

## Root Cause Candidates
- Primary root cause: the previous coverage metric used the total decision cohort as the denominator, mixing rejected or never-executed rows with rows that actually became close-eligible.
- Secondary root cause: stale reject terminal labels could outrank stronger runtime execution evidence, which temporarily undercounted the repaired denominator until evidence-priority handling was added.
- Remaining unmatched close-expected rows are most consistent with a runtime surface mismatch between order_log POSITION_CLOSED evidence and trade_lifecycle terminal close evidence, not with blanket non-execution.

## Operational Risk
- Correctness
- Observability Gap

## Files / Areas Touched
- calibrators/datasets/builders/realized_outcome_builder.py
- calibrators/datasets/audit_runtime_close_coverage.py
- tests/calibrators/test_realized_outcome_builder.py
- tests/calibrators/test_runtime_close_coverage_audit.py
- CALIBRATORS_FOUNDATION_PACKAGE_03Q_EXECUTED_ELIGIBILITY_DENOMINATOR_REPAIR_REPORT.md

## Validation Performed
- Ran c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_realized_outcome_builder.py tests/calibrators/test_runtime_close_coverage_audit.py -q and observed 19 / 19 passing.
- Ran c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_realized_outcome_builder.py tests/calibrators/test_runtime_close_coverage_audit.py tests/calibrators/test_dataset_builders.py tests/test_calibrators_import_boundary.py -q and observed 47 / 47 passing.
- Rebuilt the frozen snapshot artifact with c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m calibrators.datasets.build_realized_outcome_dataset --decision-ledger artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/decision_ledger_v1.jsonl --order-log artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/order_log_v1.jsonl --trade-lifecycle artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/trade_lifecycle.jsonl --out-dir artifacts/calibration_datasets/_post_03k_realized_outcome_03q.
- Recomputed the audit with c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m calibrators.datasets.audit_runtime_close_coverage --realized-artifact-dir artifacts/calibration_datasets/_post_03k_realized_outcome_03q --out-dir calibrators/datasets/runtime_close_coverage_post_03q.
- Verified that builder and audit denominator_audit outputs agree exactly on 75 rejected_or_not_executed rows, 17 close_expected rows, 4 close_matched rows, and 23.5294% execution_to_close_coverage_pct.

## Residual Risk
- The denominator is now semantically aligned to executed close coverage, but the realized dataset remains diagnostics-only because only 4 / 17 close-expected rows emit realized outcomes and only 3 are exact roundtrips.
- The remaining 13 unmatched close-expected rows are still an operational observability problem and may require separate close-surface reconciliation work.
- Any future report that quotes legacy total-decision coverage without the repaired denominator fields could reintroduce the same interpretation error.

## What Remains Unproven
- Whether the 13 unmatched close-expected rows can be recovered safely by additional close canonicalization or source alignment without widening false matches.
- Whether a fresh live runtime window after this offline semantics repair will preserve the same 75 / 17 / 4 cohort split.
- Whether downstream consumers outside the currently validated builder and audit surfaces rely on the old total-decision interpretation in documentation or operator workflows.

## Minimal Safe Verdict
Package 03Q is complete as a bounded offline semantics repair. For the frozen post-03K snapshot, the old 4 / 93 = 4.3011% figure should no longer be interpreted as executed-position close coverage; the repaired and evidence-backed close-expected metric is 4 / 17 = 23.5294%, with 75 rows explicitly identified as rejected or not executed.