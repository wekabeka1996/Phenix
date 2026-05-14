# AGENT_REPORT_V1

## Executive Summary
03U froze and validated a fresh post-03T multi-day runtime evidence layer. It is sufficient for read-only descriptive economics and runtime/NRR forensics, but it does not prove promotion-grade canonical close coverage or config-authoritative gate-state readiness.

## Proven Facts
- Frozen runtime bundle logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z spans 2026-05-09T22:15:03.634000+00:00 to 2026-05-13T19:04:06.723000+00:00, duration 3d 20h 49m 3s, with 3 BOOT rows in order_log and 3 inferable process-session segments.
- The fresh window contains 761 order_log rows, 334 decision_ledger rows, and 232021 trade_lifecycle rows with 1 parse error.
- The canonical realized dataset at artifacts/calibration_datasets/_post_03t_multiday_realized_outcome emitted 12 realized rows and 11 exact roundtrips, with execution_to_close_coverage_pct=33.3333 on builder denominator close_expected_rows=36, diagnostics_only=true, and promotion_grade=false.
- The runtime close coverage audit at calibrators/datasets/runtime_close_coverage_post_03t_multiday reported close_expected_rows=56, close_matched_rows=12, exact_roundtrip_rows=11, and execution_to_close_coverage_pct=21.4286.
- Runtime unmatched classification counts are 14 CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED, 20 CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY, 3 CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED, 4 LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED, 12 REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY, 3 SOURCE_LOGGING_GAP, 3 INCONCLUSIVE, and 263 NOT_EXECUTED_OR_REJECTED.
- Close-surface reconciliation reduces the 24 close-expected unmatched rows to 16 ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED, 7 ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT, 1 DECISION_LEDGER_REALIZED_ONLY, 0 BUILDER_CANONICALIZATION_GAP, and 0 RUNTIME_LOGGING_GAP.
- Accepted closed trade economics show gross_pnl=171.06727, net_pnl=139.18404117, and fees=31.88322883 across 12 canonical closes. close_reason_counts are TP=9, SL=1, and CLOSE=2.
- Sidecar read-only artifacts show 15 sidecar recommendations, 15 close requests, 15 observed order_log POSITION_CLOSED rows tied to sidecar runtime ids, observed_position_closed_net_pnl=-92.86671668, observed_position_closed_fees=39.27871668, and canonical_realized_sidecar_closes=0.
- NRR runtime inventory shows no observed runtime rejects for NRR-027, NRR-028, NRR-029, or NRR-030 in this frozen window. NRR-062 shows 153 observed order_log rejects, 234 why-chain mentions, and structured selected_source/selected_scale/threshold_family presence on all 153 structured rows.
- Source snapshot validation succeeded with missing_required_sources=[] and warnings=[], and SHA256 hashes matched for retained decision_ledger, order_log, and trade_lifecycle sources.
- Targeted pytest passed 26/26 tests.
- Repo state at capture time was branch main at commit e837f16ff8b6c2fd3fd41a3812c78237cc3a1427. Live repo-scoped Python processes were still running for apps.reference.main, shadow_telemetry.main, uvicorn, and editor Python services. All report claims are anchored to the frozen bundle, not live logs.

## Inferred Findings
- Fresh post-03T evidence proves that canonical close emission exists in the new runtime window, but the evidence layer remains sparse and below promotion thresholds. 03T did not yield a promotion-grade canonical POSITION_CLOSED coverage surface by itself.
- The current post-03T calibration layer is ready for read-only descriptive economics on the accepted closed cohort, because the canonical realized dataset, objective stack, and derived economics artifacts are parse-valid, schema-valid where registered, and hash-backed by the retained source snapshot.
- The sidecar layer is useful only as an observational surface in this window. There is still no canonical realized sidecar close cohort, so avoided-loss, cut-winner, and too-early claims remain unprovable.
- NRR-062 is the only requested NRR family with meaningful runtime evidence in this window. NRR-027/028/029/030 do not have observed reject cohorts here, so there is no equivalent read-only reject inventory to analyze for those gates.
- The dominant residual close-coverage problem remains runtime-surface observability, not builder canonicalization, because 23 of 24 close-expected unmatched rows are still runtime-surface buckets while builder canonicalization gap is 0.

## Contradictions / Evidence Gaps
- The 03U freeze bundle does not retain a config snapshot. The NRR inventory helper derives configured_enabled metadata from the live workspace file config/aurora/domains.yaml.
- The current worktree is dirty in config/aurora/domains.yaml, config/aurora/observability.yaml, config/aurora/strategies.yaml, and config/aurora/trading.yaml. Therefore gate enabled/disabled conclusions are conditional on current workspace YAML, not frozen runtime-proof. Observed reject counts remain authoritative because they come from frozen order_log and decision_ledger surfaces.
- Multi-day post-03T coverage improvement cannot be stated as a normalized percentage improvement against pre-03T packages, because the earlier packages used different windows and denominators. What is proved here is current-state readiness, not a like-for-like A/B delta.
- Manual log deletion is not inferable from BOOT rows and log ranges alone. The evidence supports multiple restarts and segmented sessions, but not a deletion claim.
- A metadata-only rerun of artifacts/_tmp/phenix_03u_inventory.py after adding the NRR config provenance caveat was interrupted twice by terminal-level KeyboardInterrupt while traversing the 2.2GB trade_lifecycle file. The underlying 03U metrics remain from the last successful builder run at 2026-05-13T21:18:32Z; the NRR provenance caveat was synchronized directly into the generated NRR JSON/MD artifacts and JSON-validated afterward.

## Root Cause Candidates
- Primary residual runtime gap: canonical POSITION_CLOSED is still missing for a material subset of closed trades even when trade_lifecycle already proves closure.
- Secondary residual runtime gap: some close paths still surface as alternative terminal order events instead of canonical POSITION_CLOSED.
- Secondary evidence gap: NRR config authority is not frozen with the 03U bundle, so config-state claims are weaker than runtime reject-count claims.

## Operational Risk
Observability Gap

## Files / Areas Touched
- artifacts/_tmp/phenix_03u_inventory.py
- calibrators/datasets/runtime_inventory_03u/
- calibrators/datasets/economics_post_03t_multiday/
- calibrators/datasets/nrr_inventory_post_03t_multiday/
- CALIBRATORS_FOUNDATION_PACKAGE_03U_MULTI_DAY_POST_03T_RUNTIME_CAPTURE_VALIDATION_REPORT.md
- No runtime behavior, threshold, or enforcement code/config surfaces were changed by the 03U slice; touched surfaces were helper, generated artifacts, and report only.

## Validation Performed
- Ran targeted pytest: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_realized_outcome_builder.py tests/calibrators/test_runtime_close_coverage_audit.py tests/calibrators/test_close_surface_reconciliation_audit.py tests/test_calibrators_import_boundary.py tests/domains/execution_position/test_close_fill_truth_propagation.py -q
- Pytest result: 26 passed in 2.96s.
- Ran a custom Python validation pass that parsed 15 JSON artifacts across realized/objective/runtime/economics/NRR/audit outputs.
- Schema-validated 12 realized rows against calibration_realized_trade_dataset_v1.
- Schema-validated 334 objective trade-decision rows against calibration_trade_decision_dataset_v1.
- Schema-validated 12 objective realized rows against calibration_realized_trade_dataset_v1.
- Verified source_snapshot SHA256 parity for decision_ledger, order_log, and trade_lifecycle.
- Re-read economics and sidecar outputs after the sidecar join repair and confirmed close_reason_counts populated as TP=9, SL=1, CLOSE=2, observed_position_closed_rows=15, observed_position_closed_net_pnl=-92.86671668, and observed_position_closed_fees=39.27871668.
- JSON-validated the patched NRR artifact after adding config provenance metadata.
- Editor diagnostics for artifacts/_tmp/phenix_03u_inventory.py reported no errors.

## Residual Risk
- Read-only economics is based on only 12 canonical realized closes and 11 exact roundtrips, so distributional conclusions are fragile.
- Runtime close coverage is still low on the wider runtime denominator at 21.4286%, so the economics view is descriptive and incomplete rather than operationally authoritative.
- NRR gate-state interpretation remains conditional until the runtime bundle also freezes the config surface used to evaluate gate enablement.
- Sidecar usefulness remains observational only because the window does not provide a canonical realized sidecar close cohort or a counterfactual baseline.

## What Remains Unproven
- A like-for-like post-03T percentage improvement against pre-03T coverage.
- Whether the remaining 16 missing POSITION_CLOSED cases and 7 alternative terminal-event cases should be repaired by further runtime packages, or whether some belong to a deliberate non-realized policy boundary.
- Whether the dirty current workspace config matches the config that produced the frozen runtime window.
- Any causal claim that NRR-062 rejects or sidecar closes improved or worsened downstream PnL.

## Minimal Safe Verdict
03U successfully freezes and validates a fresh multi-day post-03T evidence layer. The layer is ready for read-only descriptive economics and runtime/NRR forensics, but it is not promotion-grade, not config-authoritative for gate-state claims, and not sufficient for enforcement changes or causal counterfactual analysis.
