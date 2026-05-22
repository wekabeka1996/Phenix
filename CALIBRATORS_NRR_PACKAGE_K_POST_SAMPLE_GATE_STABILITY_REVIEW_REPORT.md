# AGENT_REPORT_V1

## verdict
PROMOTION_BLOCKED_COLLECT_MORE

## problem_framing
Package K is a post-sample-gate stability review only. It must explain the low close count observed in Package J without changing YAML, config values, runtime Python, thresholds, override scope, sidecar authority, or deployment scope. The central question is whether the sparse J canonical close surface is driven by open positions, unfilled orders, close observability gaps, short holding horizon, or genuinely weak economics.

## facts
- Package K pre-review baseline was captured on branch main at commit 34a3b0cce8db834a6550e8087478cf6327d2df9d with runtime_running=True and order_log window 2026-05-16T10:40:02.063000+00:00 -> 2026-05-17T18:32:21.295000+00:00.
- Combined H/I/J admitted override cohort size is 32 rids: package_counts={'H': 1, 'I': 5, 'J': 26}.
- Package H remains one admitted override rid, one canonical profitable close, net +22.6742616, and sidecar observed downstream without authority change.
- Package I remains five admitted override rids, four canonical profitable closes, one submitted-not-filled row, zero losses, and net +70.33973751.
- Package J freeze authority remains 26 admitted override rids, one canonical close, one canonical loss, and 25 unresolved rows in the retained J window.
- Exact current raw-log correlation upgrades Package J latest-known status to latest_bucket_counts={'INCONCLUSIVE': 24, 'CLOSED_NON_CANONICAL_EVIDENCE': 1, 'CLOSED_CANONICAL_LOSS': 1} while freeze_bucket_counts remain {'INCONCLUSIVE': 24, 'FILLED_POSITION_STILL_OPEN': 1, 'CLOSED_CANONICAL_LOSS': 1}.
- The only Package J freeze-boundary open-position case is aurora_ETHUSDT_1778942102182. It was filled before freeze end and closed by raw SL evidence at 2026-05-17T10:04:46Z, about 2h17m after the J freeze end.
- The two Package J INVALID_FOR_DATASET rows are diagnostics-only decision-ledger rows with execution_outcome=PENDING_TIMEOUT and invalid_reason_code=TERMINAL_EVENT_MISSING; both are no_effect=true.
- The remaining 24 Package J rows are decision-ledger terminal_status=REJECTED_UPSTREAM with execution_outcome=EXCHANGE_REJECTED, invalid_reason_code=NON_CAUSAL_TIME, joined_by=rid, and support_no_effect=true for all 24 rows.
- No Package H/I/J surface shows BUY/LONG leakage, dual-failure leakage, geometry leakage, live/production leakage, or override widening beyond the Package G contract.
- Latest-known combined economics remain positive even after the second J loss: combined_i_plus_j_latest_known_net_quote=28.66752765000001, combined_h_i_j_latest_known_net_quote=51.34178925000002.

## inferences
- Package J low canonical close count at freeze was not caused by a large pool of open positions. The retained freeze boundary supports one filled-open row, one canonical close, and twenty-four diagnostics-only rows with no downstream execution evidence.
- Package J low close count was also not caused by submitted-but-unfilled orders inside the retained window. None of the 24 bulk unresolved rows show ORDER_PLACED or TRADE_LIFECYCLE_ORDERED evidence.
- The ETH row demonstrates a short-horizon effect: one valid J override remained open past the freeze boundary and closed later with a loss. That weakens the thesis, but it does not explain the other 24 rows.
- The 24-row REJECTED_UPSTREAM bulk is better interpreted as a diagnostics-only execution/observability ambiguity surface than as evidence of realized losing trades, because every row is tagged no_effect=true and NON_CAUSAL_TIME in the decision ledger.
- Runtime evidence therefore weakens the replay thesis but does not yet contradict it. The resolved H/I/J sample remains net positive and leakage remains zero.

## assumptions
- Package H/I/J retained windows remain non-overlapping for current combined cohort accounting.
- Raw ORDER_INTENT rows with metadata.low_vol_cost_floor.nrr062_segment_override_applied=true remain the authoritative override admission truth.
- Package J canonical realized rows remain the authoritative freeze-window close-count surface, while current raw logs are used only for latest-known status and post-freeze classification.

## unknowns
- Whether the 24 diagnostics-only no-effect J rows will ever acquire downstream execution evidence in a later retained bundle.
- Whether additional latest-known J closes will remain loss-heavy or rebalance as the runtime continues beyond the Package J freeze.
- Whether canonical downstream surfaces should eventually preserve override-token provenance rather than relying on raw logs as the permanent authority surface.

## combined_cohort
- summary: {'package_counts': {'H': 1, 'I': 5, 'J': 26}, 'latest_bucket_counts': {'CLOSED_CANONICAL_PROFIT': 5, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'INCONCLUSIVE': 24, 'CLOSED_NON_CANONICAL_EVIDENCE': 1}, 'freeze_bucket_counts': {'CLOSED_CANONICAL_PROFIT': 5, 'SUBMITTED_NOT_FILLED': 1, 'CLOSED_CANONICAL_LOSS': 1, 'INCONCLUSIVE': 24, 'FILLED_POSITION_STILL_OPEN': 1}, 'row_count': 32}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_combined_override_cohort_ledger.json
- artifact_csv: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_COMBINED_OVERRIDE_COHORT_LEDGER.csv
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_COMBINED_OVERRIDE_COHORT_LEDGER.md

## package_j_classification
- freeze_bucket_counts: {'INCONCLUSIVE': 24, 'FILLED_POSITION_STILL_OPEN': 1, 'CLOSED_CANONICAL_LOSS': 1}
- latest_bucket_counts: {'INCONCLUSIVE': 24, 'CLOSED_NON_CANONICAL_EVIDENCE': 1, 'CLOSED_CANONICAL_LOSS': 1}
- decision_ledger_semantics: {'terminal_execution_counts': {'REJECTED_UPSTREAM|EXCHANGE_REJECTED': 25, 'INVALID_FOR_DATASET|PENDING_TIMEOUT': 2}, 'invalid_reason_counts': {'NON_CAUSAL_TIME': 25, 'TERMINAL_EVENT_MISSING': 2}, 'support_no_effect_counts': {'True': 27}, 'joined_by_counts': {'rid': 25, 'None': 2}}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_package_j_unresolved_classification.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_PACKAGE_J_UNRESOLVED_CLASSIFICATION.md

## close_coverage_audit
- freeze_counts: {'canonical_closed': 1, 'closed_non_canonical_evidence': 0, 'filled_position_still_open': 1, 'submitted_not_filled': 0, 'inconclusive': 24}
- latest_counts: {'canonical_closed': 1, 'closed_non_canonical_evidence': 1, 'filled_position_still_open': 0, 'submitted_not_filled': 0, 'inconclusive': 24}
- classification_answer: {'primary_driver': 'one still-open filled position at freeze plus twenty-four diagnostics-only no-effect rows with no downstream execution evidence', 'open_positions_at_freeze': 1, 'unfilled_orders_at_freeze': 0, 'same_window_noncanonical_close_gap': 0, 'short_horizon_cases': 1, 'latest_known_noncanonical_closes_after_freeze': 1, 'actual_weak_economic_cases_latest_known': 2, 'decision_ledger_rows_are_no_effect': True}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_close_coverage_audit.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_CLOSE_COVERAGE_AUDIT.md

## economics_stability_review
- package_f_replay: {'candidate_rows': 79, 'tp': 25, 'sl': 2, 'timeout': 52, 'estimated_net_pnl_quote': 825.2672997047, 'profit_factor': 4.92434390438585}
- package_h_runtime: {'override_count': 1, 'resolved_closes': 1, 'wins': 1, 'losses': 0, 'net_pnl_quote': 22.6742616}
- package_i_runtime: {'override_count': 5, 'resolved_closes': 4, 'wins': 4, 'losses': 0, 'net_pnl_quote': 70.33973751}
- package_j_freeze_runtime: {'override_count': 26, 'resolved_closes': 1, 'wins': 0, 'losses': 1, 'net_pnl_quote': -13.08771079}
- package_j_latest_known: {'resolved_closes': 2, 'wins': 0, 'losses': 2, 'net_pnl_quote': -41.672209859999995}
- combined_i_plus_j_freeze: {'override_count': 31, 'resolved_closes': 5, 'wins': 4, 'losses': 1, 'net_pnl_quote': 57.25202672}
- combined_i_plus_j_latest_known: {'override_count': 31, 'resolved_closes': 6, 'wins': 4, 'losses': 2, 'net_pnl_quote': 28.66752765000001}
- combined_h_i_j_latest_known: {'override_count': 32, 'resolved_closes': 7, 'wins': 5, 'losses': 2, 'net_pnl_quote': 51.34178925000002}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_economics_stability_review.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_ECONOMICS_STABILITY_REVIEW.md

## boundary_stability_review
- boundary_summary: {'package_h': {'leakage_detected': False, 'override_count': 1, 'sidecar_observed_rids': 1}, 'package_i': {'leakage_detected': False, 'override_count': 5, 'submitted_count': 5, 'filled_count': 4, 'closed_count': 4}, 'package_j': {'leakage_detected': False, 'override_count': 26, 'decision_ledger_status_counts': {'REJECTED_UPSTREAM': 24, 'INVALID_FOR_DATASET': 2}, 'freeze_boundary_contrast_sets_zero': True}, 'package_k_baseline': {'branch': 'main', 'commit_sha': '34a3b0cce8db834a6550e8087478cf6327d2df9d', 'runtime_running': True, 'runtime_process_count': 2, 'order_log_window': {'path': 'logs/order_log_v1.jsonl', 'rows': 542, 'malformed_rows': 0, 'min_ts_utc': '2026-05-16T10:40:02.063000+00:00', 'max_ts_utc': '2026-05-17T18:32:21.295000+00:00'}, 'decision_ledger_window': {'path': 'logs/shadow_telemetry/decision_ledger_v1.jsonl', 'rows': 606, 'malformed_rows': 0, 'min_ts_utc': '2026-05-09T22:15:03.634000+00:00', 'max_ts_utc': '2026-05-17T18:30:01.586000+00:00'}, 'trade_lifecycle_window': {'path': 'logs/trade_lifecycle.jsonl', 'rows': 169141, 'malformed_rows': 1, 'min_ts_utc': '2026-05-16T10:29:20.477000+00:00', 'max_ts_utc': '2026-05-17T20:57:10.860000+00:00'}}, 'verdict': 'BOUNDARY_STABLE_NO_OVERRIDE_LEAKAGE_KEEP_TESTNET_ONLY'}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_boundary_stability_review.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_BOUNDARY_STABILITY_REVIEW.md

## replay_vs_runtime_stability_review
- classification: REPLAY_THESIS_WEAKENED_BY_J
- supporting_metrics: {'replay_candidate_net_quote': 825.2672997047, 'replay_profit_factor': 4.92434390438585, 'combined_i_plus_j_freeze_net_quote': 57.25202672, 'combined_i_plus_j_latest_known_net_quote': 28.66752765000001, 'combined_h_i_j_latest_known_net_quote': 51.34178925000002}
- artifact_json: calibrators/datasets/nrr062_testnet_override_runtime/nrr062_replay_vs_runtime_stability_review.json
- artifact_md: calibrators/datasets/nrr062_testnet_override_runtime/NRR062_REPLAY_VS_RUNTIME_STABILITY_REVIEW.md

## decision_recommendation
- recommendation: PROMOTION_BLOCKED_COLLECT_MORE
- rationale: Keep the Package G override unchanged in hybrid/testnet-only enforced scope, do not roll back, do not promote, and continue collecting because J weakens the thesis but does not yet overturn a still-positive resolved H/I/J runtime sample.

## changes_made
- Created combined cohort ledger artifacts in JSON, CSV, and Markdown under calibrators/datasets/nrr062_testnet_override_runtime.
- Created Package J unresolved classification artifacts in JSON and Markdown under calibrators/datasets/nrr062_testnet_override_runtime.
- Created close coverage, economics stability, boundary stability, and replay-vs-runtime stability review artifacts in JSON and Markdown under calibrators/datasets/nrr062_testnet_override_runtime.
- Created this Package K root report only. No YAML, config, or runtime Python files were changed.

## validation
- Pending focused validation is run immediately after artifact generation: JSON parse, cohort/count reconciliation, git surface check, and focused pytest.

## runtime_behavior_change
NONE.

- No YAML or config values were changed.
- No runtime Python logic was changed.
- No override conditions were expanded.
- No thresholds were tuned.
- No sidecar authority was changed.
- No live or production promotion was performed.

## next_recommended_package
CONTINUE_TESTNET_ONLY_COLLECTION_WITH_PROMOTION_BLOCKED
