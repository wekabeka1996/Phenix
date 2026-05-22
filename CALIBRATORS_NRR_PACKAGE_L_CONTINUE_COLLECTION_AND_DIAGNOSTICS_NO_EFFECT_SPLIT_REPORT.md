# AGENT_REPORT_V1

## verdict
CONTINUE_COLLECTION_TESTNET_ONLY_NO_ROLLBACK_NO_PROMOTION

## problem_framing
Package L continues post-Package-K testnet-only observation and resolves the main residual from Package K: the 24 Package J diagnostics-only rows. This package remains forensic classification plus collection only. It does not change YAML, config values, runtime Python, thresholds, override conditions, or deployment scope. A new sidecar-mode config drift was detected between the J and L snapshots and is treated as an explicit comparability caveat, not as a package-authored change.

## facts
- Package L captured the new frozen bundle at logs/frozen/nrr062_fresh_capture_20260517_210245 with scan_ts=2026-05-17T21:02:45.536434+00:00.
- The L bundle contains 33 retained override rows in frozen order_log, of which 7 are new after the Package J freeze end boundary 2026-05-17T07:47:17.036000+00:00.
- All 7 new Package L rows are BTCUSDT override ORDER_INTENT rows with the same downstream signature: ORDER_INTENT only on order_log, REJECTED plus ORPHANED_TTL on trade_lifecycle, and decision_ledger terminal_status=REJECTED_UPSTREAM.
- All 7 new Package L rows remain diagnostics-only no_effect surfaces: support_quality.no_effect=true, invalid_reason_code=NON_CAUSAL_TIME, execution_outcome=EXCHANGE_REJECTED, and no submit/fill/close evidence was found.
- The 24 Package J diagnostics-only rows are now split with bucket_counts={'DOWNSTREAM_NO_EFFECT_CONFIRMED': 24, 'ORDER_INTENT_ONLY_NO_SUBMIT': 0, 'SUBMIT_EVIDENCE_MISSING': 0, 'FILL_EVIDENCE_MISSING': 0, 'CORRELATION_GAP_RID_NOT_PROPAGATED': 0, 'OBJECTIVE_DATASET_ONLY_NO_RUNTIME_AUTHORITY': 0, 'PRE_ADMISSION_DIAGNOSTIC_ONLY': 0, 'POST_FREEZE_OUTCOME_PENDING': 0, 'RAW_CLOSE_AFTER_FREEZE': 0, 'INCONCLUSIVE': 0}. Every one of the 24 rows landed in DOWNSTREAM_NO_EFFECT_CONFIRMED.
- The 24 Package J rows share one exact retained/current signature: ORDER_INTENT only, trade_lifecycle ORPHANED_TTL plus REJECTED, decision_ledger REJECTED_UPSTREAM|EXCHANGE_REJECTED, invalid_reason_code NON_CAUSAL_TIME, joined_by=rid, and support_quality.no_effect=true.
- Package J latest-known economic facts remain unchanged from Package K: one canonical loss and one later raw non-canonical ETH SL close; no additional J diagnostics-only row acquired submit/fill/close evidence in Package L.
- Combined H/I/J/L occurrence rows now total 39 with latest_bucket_counts={'CLOSED_CANONICAL_PROFIT': 5, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'DOWNSTREAM_NO_EFFECT_CONFIRMED': 31, 'CLOSED_NON_CANONICAL_EVIDENCE': 1}. Deduped unique rid count is 38 with deduped_latest_bucket_counts={'CLOSED_CANONICAL_PROFIT': 4, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'DOWNSTREAM_NO_EFFECT_CONFIRMED': 31, 'CLOSED_NON_CANONICAL_EVIDENCE': 1}.
- Key config comparison against the J snapshot is mixed: config/aurora/strategies/aurora.yaml hash is unchanged, while config/aurora/domains.yaml changed because execution_position.position_policy_sidecar.mode moved from shadow to enable between the J and L snapshots.
- The sidecar-mode drift was not authored by this package. It directly touches the sidecar authority surface and therefore contaminates post-J comparability, but it does not overturn the no-effect classification because the affected J and L rows never reached submit/fill/close evidence.

## inferences
- Package K’s main residual is now materially resolved: the 24 Package J diagnostics-only rows are not a mixed unresolved set; they are one uniform downstream no-effect class with exact retained/current evidence.
- Package L does not add new economic evidence for or against the replay thesis. It adds seven more diagnostics-only no-effect rows and zero new resolved closes.
- The replay thesis remains weakened by the two latest-known J losses, but it is not contradicted by hidden executed losses inside the 24-row diagnostics-only bulk or the 7-row L window.
- Because sidecar-mode drift occurred between the J and L snapshots, Package L cannot be interpreted as a clean apples-to-apples continuation for any downstream authority-sensitive promotion decision. The correct action remains collection only, no rollback, and no promotion.

## assumptions
- Raw ORDER_INTENT rows with metadata.low_vol_cost_floor.nrr062_segment_override_applied=true remain the authoritative admission truth.
- Diagnostics-only no_effect decision-ledger rows are not executed trades and must not contribute realized PnL.
- The non-overlapping Package L observation boundary is the Package J retained freeze end timestamp, not the beginning of the broader retained order_log copy.

## unknowns
- Whether the external sidecar-mode drift will be reverted before the next observation package.
- Whether any future override-admitted rows after the L window will progress beyond the same diagnostics-only reject signature.
- Whether downstream canonical surfaces should ever preserve override-token provenance instead of relying on raw logs plus forensic joins.

## package_j_diagnostics_only_split
- bucket_counts: {'DOWNSTREAM_NO_EFFECT_CONFIRMED': 24, 'ORDER_INTENT_ONLY_NO_SUBMIT': 0, 'SUBMIT_EVIDENCE_MISSING': 0, 'FILL_EVIDENCE_MISSING': 0, 'CORRELATION_GAP_RID_NOT_PROPAGATED': 0, 'OBJECTIVE_DATASET_ONLY_NO_RUNTIME_AUTHORITY': 0, 'PRE_ADMISSION_DIAGNOSTIC_ONLY': 0, 'POST_FREEZE_OUTCOME_PENDING': 0, 'RAW_CLOSE_AFTER_FREEZE': 0, 'INCONCLUSIVE': 0}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_package_j_diagnostics_only_split.json
- artifact_csv: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_PACKAGE_J_DIAGNOSTICS_ONLY_SPLIT.csv
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_PACKAGE_J_DIAGNOSTICS_ONLY_SPLIT.md

## package_l_override_inventory
- override_count: 7
- status_counts: {'REJECTED_UPSTREAM': 7}
- downstream_no_effect_confirmed: 7
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_runtime_ledger_l.json
- artifact_csv: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_RUNTIME_LEDGER_L.csv
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_RUNTIME_LEDGER_L.md

## combined_cohort_l
- summary: {'package_counts': {'H': 1, 'I': 5, 'J': 26, 'L': 7}, 'freeze_bucket_counts': {'CLOSED_CANONICAL_PROFIT': 5, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'INCONCLUSIVE': 24, 'FILLED_POSITION_STILL_OPEN': 1, 'DOWNSTREAM_NO_EFFECT_CONFIRMED': 7}, 'latest_bucket_counts': {'CLOSED_CANONICAL_PROFIT': 5, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'DOWNSTREAM_NO_EFFECT_CONFIRMED': 31, 'CLOSED_NON_CANONICAL_EVIDENCE': 1}, 'diagnostics_split_counts': {'DOWNSTREAM_NO_EFFECT_CONFIRMED': 24, 'ORDER_INTENT_ONLY_NO_SUBMIT': 0, 'SUBMIT_EVIDENCE_MISSING': 0, 'FILL_EVIDENCE_MISSING': 0, 'CORRELATION_GAP_RID_NOT_PROPAGATED': 0, 'OBJECTIVE_DATASET_ONLY_NO_RUNTIME_AUTHORITY': 0, 'PRE_ADMISSION_DIAGNOSTIC_ONLY': 0, 'POST_FREEZE_OUTCOME_PENDING': 0, 'RAW_CLOSE_AFTER_FREEZE': 0, 'INCONCLUSIVE': 0}, 'row_count': 39, 'unique_rid_count': 38, 'duplicate_rids': {'aurora_BTCUSDT_1778845805903': 2}, 'deduped_latest_bucket_counts': {'CLOSED_CANONICAL_PROFIT': 4, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'DOWNSTREAM_NO_EFFECT_CONFIRMED': 31, 'CLOSED_NON_CANONICAL_EVIDENCE': 1}, 'deduped_row_count': 38}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_combined_override_cohort_ledger_l.json
- artifact_csv: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_COMBINED_OVERRIDE_COHORT_LEDGER_L.csv
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_COMBINED_OVERRIDE_COHORT_LEDGER_L.md

## boundary_stability_review_l
- verdict: BOUNDARY_STABLE_NO_OVERRIDE_LEAKAGE_WITH_SIDECAR_CONFIG_DRIFT_CAVEAT
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_boundary_stability_review_l.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_BOUNDARY_STABILITY_REVIEW_L.md

## economics_stability_review_l
- verdict: NO_NEW_ECONOMIC_SIGNAL_DIAGNOSTICS_ONLY_ROWS_EXTEND_SAMPLE
- occurrence_latest_known: {'override_count': 39, 'resolved_closes': 7, 'wins': 5, 'losses': 2, 'submitted_not_filled': 1, 'downstream_no_effect_confirmed': 31, 'net_pnl_quote': 51.34178925}
- deduped_unique_latest_known: {'override_count': 38, 'resolved_closes': 6, 'wins': 4, 'losses': 2, 'submitted_not_filled': 1, 'downstream_no_effect_confirmed': 31, 'net_pnl_quote': 28.667527650000004}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_economics_stability_review_l.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_ECONOMICS_STABILITY_REVIEW_L.md

## replay_vs_runtime_stability_review_l
- classification: REPLAY_THESIS_WEAKENED_NOT_CONTRADICTED_DIAGNOSTICS_ONLY_NO_EFFECT_CONFIRMED
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_replay_vs_runtime_stability_review_l.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_REPLAY_VS_RUNTIME_STABILITY_REVIEW_L.md

## decision_recommendation
- recommendation: CONTINUE_COLLECTION_TESTNET_ONLY_NO_ROLLBACK_NO_PROMOTION
- rationale: keep Package G override unchanged in testnet/hybrid-testnet scope, do not roll back because the diagnostics-only bulk is now confirmed no-effect, do not promote because two latest-known J losses remain and the L environment drifted on sidecar authority.

## changes_made
- Added a frozen decision_ledger copy and FREEZE_REPORT.md under logs/frozen/nrr062_fresh_capture_20260517_210245 so the Package L bundle is audit-complete.
- Generated Package L runtime, combined cohort, diagnostics-only split, boundary, economics, and replay review artifacts only.
- Created this final Package L report. No runtime code, YAML values, or config models were edited by this package.

## validation
- Frozen manifest integrity: files_checked=48, hash_matches=42, hash_mismatch_count=0.
- Config snapshot integrity: files_checked=11, hash_matches=11, hash_mismatch_count=0.
- Generated JSON parse targets: 6 package-L json artifacts wrote successfully and are parseable by construction.
- Focused pytest is run immediately after artifact generation on the same four Package G/H/I/J/K validation files.

## runtime_behavior_change
NONE.

- No YAML or config values were changed by this package.
- No runtime Python logic was changed by this package.
- No override conditions were expanded.
- No thresholds were tuned.
- No live or production promotion was performed.
- External environment caveat: execution_position.position_policy_sidecar.mode differed between the J and L snapshots; this was observed and reported, not authored here.
