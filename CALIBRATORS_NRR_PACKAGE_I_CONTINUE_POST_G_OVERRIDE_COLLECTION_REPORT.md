# AGENT_REPORT_V1

## verdict
CONTINUE_COLLECTION_TESTNET_ONLY_NO_ROLLBACK_NO_PROMOTION

## problem_framing
- Objective: continue post-deploy runtime collection for the Package G NRR-062 LOW_VOL short-direction-only raw-signal override and test whether the first positive Package H observation remains directionally supported over a larger retained sample.
- Scope: frozen-bundle capture validation, override inventory, safety-boundary audit, canonical realized and objective propagation audit, runtime outcome analysis, rollback-gate evaluation, and focused validation only.
- Hard constraints respected: no YAML edits, no config value changes, no runtime logic changes, no threshold tuning, no override widening, no sidecar authority changes, no live or production promotion, and no use of sample size 1 as proof.

## facts
- Frozen bundle root: logs/frozen/nrr062_fresh_capture_20260516_101448.
- Freeze report state: branch=main, commit_sha=34a3b0cce8db834a6550e8087478cf6327d2df9d, dirty_worktree=true, dirty_config_paths=4, decision_ledger_frozen=true.
- Post-boot observation boundary for leakage audit: order_log line 1734 at 2026-05-15T10:55:08.184000+00:00.
- Observation runtime window: 2026-05-15T10:55:08.184000+00:00 to 2026-05-16T10:10:03.371000+00:00, duration_seconds=83695, duration_hours=23.2486, restarts_after_boundary=3.
- Active symbols inside the post-boot retained window: BNBUSDT, BTCUSDT, XRPUSDT, ETHUSDT, DOGEUSDT.
- Frozen mode surface in the observed tail: hybrid_live_data_testnet_exec only.
- Raw override truth: order_log override rows=5, shadow_journal override rows=5, accepted LOW_VOL ORDER_INTENT rows=5.
- Override rid cohort: aurora_BTCUSDT_1778845805903, aurora_BTCUSDT_1778874602993, aurora_ETHUSDT_1778874602066, aurora_ETHUSDT_1778875209803, aurora_XRPUSDT_1778875503239.
- Safety audit scope: nrr062_total_rows=308, post_boot_nrr062_surface_rows=11, post_boot candidate_contract_rows=5, candidate_contract_without_override=0, historical_pre_boot_candidate_contract_rows_excluded=0.
- Boundary contrast counts in the post-boot tail: BUY/LONG direction-only=3, dual_failure=3, geometry_invalid=0, live_or_production_candidate_like=0, missing_selected_metadata=0, SELL direction-only noncandidate=0; override leakage across all contrast sets=0.
- Runtime outcome summary: override_count=5, submitted_count=5, filled_count=4, closed_count=4, exact_roundtrip_rows=4, wins=4, losses=0, unresolved=1.
- Override economics: net_pnl_quote=70.33973751, gross_pnl_quote=78.38716, fees_quote=8.04742249, fee_drag_ratio_of_gross=0.10266250863023997.
- Realized close labels for the four closed rows are all closed_win. No SL or soft-close rows were observed in the retained override cohort.
- Canonical propagation summary: objective_rows_for_override_rids=5, canonical_override_closes=4, exact_roundtrip_override_rows=4.
- Canonical datasets remain diagnostics-only and not promotion-grade: realized coverage_grade=PARTIAL_DIAGNOSTIC with match_coverage_pct=41.4634; objective coverage_grade=PARTIAL_DIAGNOSTIC with the same coverage percentage.
- Override token propagation remains raw-log-only: objective_rows_preserve_override_token=false and decision_ledger_preserves_override_token=false.
- Frozen-bundle limitations are explicit: authority request and response journals are absent from the frozen bundle; recorder_coverage_sufficient=false because XRPUSDT required horizon coverage is incomplete.
- Trade lifecycle data quality caveat persists: FREEZE_REPORT documents 8 malformed fragment lines; the realized builder warning still reports TRADE_LIFECYCLE_JSON_ERRORS:7.
- Explicit validation completed: manifest_files_checked=1931 with all hashes matching, config_copies_checked=11 with all hashes matching, artifact_json_files_checked=5 with all parses succeeding, schema-validated rows=34 package_i_realized, 532 package_i_objective_decisions, 34 package_i_objective_realized.
- Relevant runtime and config git status at report time matches the capture snapshot exactly for apps/reference/* and config/aurora/*, so this package introduced no runtime or YAML surface mutations.
- Focused pytest validation result: 102 passed, 0 failed, runtime 7.21s.

## inferences
- Package I materially strengthens the Package H observation: the override cohort increased from 1 admitted rid to 5 admitted rids while preserving zero observed boundary leakage.
- The runtime signal remains directionally aligned with the Package F replay thesis: positive net economics, four profitable realized closes, zero losses, and no observed leakage into disallowed contrast surfaces.
- The sample is still too small for calibration or rollout claims. Relative to the Package F replay cohort of 79 candidate rows, Package I has observed only 5 / 79 = 0.06329113924050633 of the candidate volume.
- The correct Package I runtime classification is RUNTIME_WEAKLY_SUPPORTS_SEGMENT_THESIS, not production readiness. The evidence is supportive and still observational.
- Because objective rows and decision-ledger rows do not preserve the override token, raw order_log and shadow journal remain the authoritative proof surfaces for override admission.
- XRP recorder insufficiency and the 8-versus-7 malformed-line discrepancy are bounded evidence-quality caveats; they do not overturn the observed positive runtime cohort, but they do limit promotion-grade interpretation.

## assumptions
- closed_win on canonical realized rows is treated as authoritative positive closed-outcome evidence even though the retained canonical row does not classify the close as TP-specific.
- The post-last-BOOT boundary before the first retained override remains the correct authority boundary for leakage auditing in a multi-day frozen bundle.
- Absence of explicit override-token propagation into objective and decision-ledger surfaces is an observability limitation, not evidence that the raw override admission itself failed to occur.
- No sidecar authority change is inferred from this package because the task scope was collection and validation only and the relevant runtime/config git surfaces are unchanged versus the capture snapshot.

## unknowns
- Whether the current positive 5-row runtime sample will remain positive as the cohort grows beyond observation scale.
- Whether future retained windows will resolve the XRPUSDT recorder horizon insufficiency without any runtime or config intervention.
- Why FREEZE_REPORT documents 8 malformed trade_lifecycle fragments while the realized builder warning surfaces only 7 JSON errors.
- Whether downstream canonical surfaces should ever preserve the override token or whether raw logs remain the intended permanent authority surface for override admission proof.

## frozen_bundle
| field | value |
| --- | --- |
| bundle_root | logs/frozen/nrr062_fresh_capture_20260516_101448 |
| freeze_ts_utc | 2026-05-16T10:14:48.804999+00:00 |
| branch | main |
| commit_sha | 34a3b0cce8db834a6550e8087478cf6327d2df9d |
| dirty_worktree | true |
| order_log_window | 2026-05-11T15:10:03.413000+00:00 -> 2026-05-16T10:10:03.371000+00:00 |
| order_log_boot_rows | 14 |
| order_log_override_rows | 5 |
| shadow_journal_override_rows | 5 |
| decision_ledger_terminal_counts | EXECUTED_AND_CLOSED=40, INVALID_FOR_DATASET=71, REJECTED_UPSTREAM=421 |
| trade_lifecycle_malformed_lines_skipped | 8 |
| config_snapshot_required_present | 8 / 8 |
| config_snapshot_parse_status_counts | PARSED_MAPPING=11 |
| recorder_coverage_sufficient | false |
| recorder_coverage_limit | XRPUSDT required horizon end not fully covered |

## override_inventory
| rid | ts_utc | symbol | original_direction_confidence | original_regime_confidence | submitted | filled | closed | close_reason | net_quote | fees_quote | exact_roundtrip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_BTCUSDT_1778845805903 | 2026-05-15T11:50:06.875000+00:00 | BTCUSDT | 0.00450884 | 0.4071842674741224 | True | True | True | closed_win | 22.6742616 | 1.9257384 | True |
| aurora_BTCUSDT_1778874602993 | 2026-05-15T19:50:03.544000+00:00 | BTCUSDT | 0.00527924 | 0.40309351855782344 | True | True | True | closed_win | 16.35869414 | 1.93960586 | True |
| aurora_ETHUSDT_1778874602066 | 2026-05-15T19:50:02.691000+00:00 | ETHUSDT | 0.00250449 | 0.7328551939357536 | True | False | False |  |  |  | False |
| aurora_ETHUSDT_1778875209803 | 2026-05-15T20:00:10.595000+00:00 | ETHUSDT | 0.00250449 | 0.8173906092180151 | True | True | True | closed_win | 22.795140229999998 | 2.45903977 | True |
| aurora_XRPUSDT_1778875503239 | 2026-05-15T20:05:03.529000+00:00 | XRPUSDT | 0.02179594 | 0.7801197859362246 | True | True | True | closed_win | 8.511641540000001 | 1.7230384600000002 | True |

## safety_boundary
| surface | post_boot_rows | override_applied_rows | expected_behavior | verdict |
| --- | --- | --- | --- | --- |
| authoritative_candidate_contract | 5 | 5 | should be admitted | PASS |
| candidate_contract_without_override | 0 | 0 | should remain zero | PASS |
| buy_or_long_direction_only | 3 | 0 | no leakage allowed | PASS |
| dual_failure | 3 | 0 | no leakage allowed | PASS |
| geometry_invalid | 0 | 0 | no leakage allowed | PASS |
| live_or_production_candidate_like | 0 | 0 | no leakage allowed | PASS |
| missing_selected_metadata | 0 | 0 | fail closed | PASS |
| sell_direction_only_noncandidate | 0 | 0 | no leakage allowed | PASS |

## outcome_summary
| metric | value | notes |
| --- | --- | --- |
| override_count | 5 | distinct admitted override rids |
| submitted_count | 5 | every admitted rid reached downstream order submission evidence |
| filled_count | 4 | four admitted rids reached canonical realized close evidence |
| closed_count | 4 | canonical realized rows |
| exact_roundtrip_rows | 4 | all four closed rows are exact roundtrips |
| wins_losses_unresolved | 4 / 0 / 1 | one ETH row remained not filled |
| net_pnl_quote | 70.33973751 | aggregate override-cohort net |
| gross_pnl_quote | 78.38716 | aggregate override-cohort gross |
| fees_quote | 8.04742249 | aggregate override-cohort fees |
| fee_drag_ratio_of_gross | 0.10266250863023997 | fees stayed well below gross |
| close_distribution | OVERRIDE_CLOSED_OTHER=4, OVERRIDE_ORDER_SUBMITTED_NOT_FILLED=1 | canonical close rows all carry close_reason=closed_win |
| runtime_verdict | RUNTIME_WEAKLY_SUPPORTS_SEGMENT_THESIS | positive directional support, still observation-grade |
| outcome_verdict | POSITIVE_BUT_SAMPLE_STILL_SMALL | economics positive, sample insufficient for promotion |

## canonical_propagation
| metric | value | interpretation |
| --- | --- | --- |
| nrr062_reject_rows_order_log | 303 | raw rejected NRR-062 rows remain the larger background cohort |
| override_rows_order_log | 5 | raw admitted override cohort |
| accepted_low_vol_order_intents | 5 | every admitted override row is a LOW_VOL ORDER_INTENT |
| objective_rows_for_override_rids | 5 | canonical trade decision rows exist for the full override cohort |
| canonical_override_closes | 4 | realized dataset captured four closed override rows |
| exact_roundtrip_override_rows | 4 | all four captured closes are exact roundtrips |
| realized_match_coverage_pct | 41.4634 | diagnostics-only, not promotion-grade |
| realized_coverage_grade | PARTIAL_DIAGNOSTIC | insufficient realized coverage |
| objective_coverage_grade | PARTIAL_DIAGNOSTIC | source realized dataset not promotion-grade |
| objective_rows_preserve_override_token | false | canonical objective rows do not preserve raw override truth |
| decision_ledger_preserves_override_token | false | frozen decision ledger also does not preserve the token |
| objective_warnings | authority_request_journal absent; authority_response_journal absent | frozen-bundle limitation, not runtime logic change |
| realized_warning | TRADE_LIFECYCLE_JSON_ERRORS:7 | differs from FREEZE_REPORT malformed_lines=8 |

## replay_vs_runtime
| metric | package_f_replay | package_h_runtime | package_i_runtime |
| --- | --- | --- | --- |
| cohort_size | 79 candidate rows | 1 admitted override rid | 5 admitted override rids |
| realized_or_terminal_outcomes | TP=25, SL=2, TIMEOUT=52 | 1 exact roundtrip close | 4 exact roundtrip closes, 1 submitted-not-filled |
| net_quote | 825.2672997047 estimated replay net | 22.6742616 | 70.33973751 |
| leakage | BUY and dual-failure cohorts excluded offline | 0 | 0 |
| sample_fraction_vs_package_f | 1.0 | 1 / 79 = 0.012658227848101266 | 5 / 79 = 0.06329113924050633 |
| directional_read | positive offline segment thesis | positive first runtime observation | positive follow-up runtime observation |
| decision | replay authority for segment thesis | continue collection | continue collection |

## rollback_gate
| condition | value | interpretation |
| --- | --- | --- |
| verdict | NO_ROLLBACK_SIGNAL_TESTNET_ONLY_CONTINUE_COLLECTION | no rollback trigger fired |
| override_observed | true | runtime cohort exists |
| boundary_leak_detected | false | no leakage in post-boot contrast surfaces |
| override_outside_testnet_hybrid | false | no live or production leakage |
| realized_positive | true | aggregate net remains positive |
| sl_or_adverse_close_dominates | false | no SL or soft-close dominance |
| sidecar_fee_drag_spike | false | no fee-drag rollback signal |
| metadata_missing_blocks_audit | false | required override metadata remained present |
| sample_size_sufficient_for_promotion | false | still below any promotion-grade sample bar |
| objective_rows_preserve_override_token | false | observability limitation only |
| decision_ledger_preserves_override_token | false | observability limitation only |
| sidecar_authority_changed | false | no authority change in scope |
| production_scope_changed | false | no rollout widening |

Recommended action: keep the Package G override unchanged in hybrid_live_data_testnet_exec only, continue runtime collection, do not promote to live or production, and do not tune thresholds or widen conditions from this evidence set.

## changes_made
- Captured and froze the new authoritative runtime bundle at logs/frozen/nrr062_fresh_capture_20260516_101448.
- Augmented the frozen bundle after capture with frozen decision_ledger_v1.jsonl and FREEZE_REPORT.md so the bundle is audit-ready without modifying runtime or YAML behavior.
- Built the canonical realized dataset at calibrators/datasets/nrr062_testnet_override_runtime/package_i_realized_dataset.
- Built the canonical objective dataset at calibrators/datasets/nrr062_testnet_override_runtime/package_i_objective_dataset.
- Generated the Package I runtime artifacts under calibrators/datasets/nrr062_testnet_override_runtime: runtime ledger I, safety boundary audit I, canonical dataset propagation audit, outcome analysis I, and rollback gate I in JSON, CSV, and Markdown forms as applicable.
- Added this final Package I report.

## validation
- Frozen manifest integrity: 1931 frozen files re-hashed, 1931 / 1931 matched recorded sha256 values.
- Config snapshot integrity: 11 copied config files re-hashed, 11 / 11 matched recorded sha256 values.
- Generated artifact JSON parse: 5 / 5 files parsed successfully.
- Schema validation via calibrators.datasets.schema_registry.validate_row: package_i_realized=34 rows, package_i_objective_decisions=532 rows, package_i_objective_realized=34 rows.
- Runtime/config git surfaces unchanged since capture snapshot: true for the relevant apps/reference/* and config/aurora/* status set.
- Focused pytest command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_low_vol_cost_floor_gate.py tests/domains/decision_making/test_low_vol_direction_confidence_contract.py tests/config/test_decision_making_contracts.py tests/test_calibrators_import_boundary.py
- Pytest result: 102 passed, 0 failed, runtime 7.21s.
- Note: the VS Code runTests tool did not execute these files despite valid paths, so focused pytest was run directly to complete the required validation.

## runtime_behavior_change
NONE.

- No YAML or config values were changed.
- No Python runtime logic was changed.
- No override conditions were expanded.
- No thresholds were tuned.
- No sidecar authority was changed.
- No live or production promotion was performed.
- Relevant runtime/config git status matches the capture snapshot exactly.

## next_recommended_package
Recommended next package: CALIBRATORS_NRR_PACKAGE_J_CONTINUE_POST_G_OVERRIDE_COLLECTION.

Proposed Package J objective: continue hybrid_live_data_testnet_exec-only runtime collection until either the override cohort reaches a more decision-useful size, such as at least 10 admitted override rids with at least 5 canonical closes, or a rollback condition appears. Package J should remain collection-and-validation only: no YAML edits, no threshold tuning, no runtime logic changes, no scope widening, and no production promotion.
