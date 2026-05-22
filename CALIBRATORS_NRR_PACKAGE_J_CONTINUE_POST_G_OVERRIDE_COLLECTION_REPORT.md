# AGENT_REPORT_V1

## verdict
SAMPLE_GATE_REACHED_KEEP_TESTNET_ONLY_NO_ROLLBACK_NO_PROMOTION

## problem_framing
- Objective: continue post-deploy runtime collection for the Package G NRR-062 LOW_VOL short-direction-only raw-signal override and determine whether the current total retained sample has reached the user-defined decision-useful gate without changing runtime behavior.
- Scope: frozen-bundle capture validation, override inventory, safety-boundary audit, canonical realized and objective propagation audit, runtime outcome analysis, rollback-gate evaluation, and focused validation only.
- Hard constraints respected: no YAML edits, no config value changes, no runtime logic changes, no threshold tuning, no override widening, no sidecar authority changes, no live or production promotion, and no use of judge confidence live.

## facts
- Frozen bundle root: logs/frozen/nrr062_fresh_capture_20260517_080431.
- Freeze report state: branch=main, commit_sha=34a3b0cce8db834a6550e8087478cf6327d2df9d, dirty_worktree=true, dirty_config_paths=4, decision_ledger_frozen=true.
- Retained observation boundary for Package J uses order_log line 1 at 2026-05-16T10:40:02.063000+00:00 because an explicit BOOT boundary was not localized inside the retained J bundle tail.
- Observation runtime window: 2026-05-16T10:40:02.063000+00:00 to 2026-05-17T07:47:17.036000+00:00, duration_seconds=76034.973, duration_hours=21.1208, restarts_after_boundary=NOT_LOCALIZED_FROM_RETAINED_TAIL.
- Active symbols inside the retained J window: BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, XRPUSDT.
- Frozen mode surface in the observed tail: hybrid_live_data_testnet_exec only.
- Raw override truth: order_log override rows=26, shadow_journal override rows=26, accepted LOW_VOL ORDER_INTENT rows=26.
- Override rid cohort size: 26 distinct admitted override rids. First rid=aurora_BTCUSDT_1778936098521; last rid=aurora_XRPUSDT_1778934901815.
- Safety audit scope: nrr062_total_rows=51, post_boot_nrr062_surface_rows=26, candidate_contract_rows=26, candidate_contract_without_override=0, historical_pre_boot_candidate_contract_rows_excluded=0.
- Boundary contrast counts in the retained J surface: BUY/LONG direction-only=0, dual_failure=0, geometry_invalid=0, live_or_production_candidate_like=0, missing_selected_metadata=0, SELL direction-only noncandidate=0; override leakage across all contrast sets=0.
- Runtime outcome summary for Package J only: override_count=26, canonical_closed_count=1, exact_roundtrip_rows=1, wins=0, losses=1, unresolved=25.
- Package J override economics: net_pnl_quote=-13.08771079, gross_pnl_quote=-11.28317, fees_quote=1.80454079, fee_drag_ratio_of_abs_gross=0.15993207493993264.
- Package J decision-ledger status mix for override rids: INVALID_FOR_DATASET=2, REJECTED_UPSTREAM=24.
- Current total sample across non-overlapping Package I and Package J retained windows: admitted_override_rids=31, canonical_closes=5, combined_net_quote=57.25202672.
- Canonical datasets remain diagnostics-only and not promotion-grade: realized coverage_grade=SPARSE_DIAGNOSTIC with match_coverage_pct=12.9032; objective coverage_grade=SPARSE_DIAGNOSTIC with the same coverage percentage.
- Override token propagation remains raw-log-only: objective_rows_preserve_override_token=false and decision_ledger_preserves_override_token=false.
- Frozen-bundle limitations are explicit: authority request and response journals are absent from the frozen bundle; recorder_coverage_sufficient=false because BTCUSDT required horizon coverage is incomplete.
- Trade lifecycle data quality caveat persists: FREEZE_REPORT documents 1 malformed fragment line and the realized builder warning surfaces TRADE_LIFECYCLE_JSON_ERRORS:1.
- Explicit validation completed: manifest_files_checked=1953 with all hashes matching, config_copies_checked=11 with all hashes matching, artifact_json_files_checked=5 with all parses succeeding, schema-validated rows=4 package_j_realized, 588 package_j_objective_decisions, 4 package_j_objective_realized.
- Relevant runtime and config git surfaces were not edited in this package; Package J changes are frozen-bundle and reporting artifacts only.

## inferences
- Package J materially enlarges the admitted override cohort from 5 retained rids in Package I to 26 new retained admitted rids, and the combined I+J retained sample reaches the user-defined gate of at least 10 admitted rids and at least 5 canonical closes.
- Package J alone does not provide enough resolved closes to classify the runtime as confirming or contradicting the segment thesis. The correct J-only runtime classification is RUNTIME_INSUFFICIENT_CLOSES because only one canonical override close is retained in this window.
- The one resolved Package J canonical override close is a loss, so the Package I positive thesis is no longer monotonically strengthening. The new signal is adverse, but it is not yet dominant at the current total sample level because combined I+J net remains positive and combined wins still exceed losses.
- The correct decision-gate outcome is SAMPLE_GATE_REACHED_KEEP_TESTNET_ONLY: the operational sample gate is reached, but canonical datasets remain diagnostics-only, the new J close is adverse, recorder coverage is still incomplete for BTCUSDT, and nothing in this evidence supports promotion or threshold tuning.
- Because objective rows and decision-ledger rows do not preserve the override token, raw order_log override ORDER_INTENT rows and the frozen shadow journal remain the authoritative proof surfaces for admission.

## assumptions
- Package I and Package J retained windows are treated as non-overlapping for current-total sample accounting because the Package I order_log window ends before the Package J order_log window begins.
- The first retained order_log line in Package J is treated as the leakage-audit boundary because the explicit BOOT boundary was not localized inside the retained J bundle tail.
- Canonical realized rows are treated as the authoritative close surface for sample-gate close counting in Package J even when decision-ledger terminal rows remain diagnostics-only.
- Absence of override-token propagation into objective and decision-ledger rows is treated as an observability limitation, not evidence that the raw override admission failed.

## unknowns
- Whether the adverse single-close signal in Package J will remain isolated or broaden into a loss-dominant pattern in the next retained testnet-only window.
- Whether future retained windows will resolve the BTCUSDT recorder horizon insufficiency without any runtime or config intervention.
- Why the single realized Package J override close is recoverable canonically while 24 override rids remain REJECTED_UPSTREAM and one remains INVALID_FOR_DATASET.
- Whether downstream canonical surfaces should eventually preserve the override token or whether raw logs remain the intended permanent authority surface for override admission proof.

## frozen_bundle
| field | value |
| --- | --- |
| bundle_root | logs/frozen/nrr062_fresh_capture_20260517_080431 |
| freeze_ts_utc | 2026-05-17T08:04:31.402016+00:00 |
| branch | main |
| commit_sha | 34a3b0cce8db834a6550e8087478cf6327d2df9d |
| dirty_worktree | true |
| order_log_window | 2026-05-16T10:40:02.063000+00:00 -> 2026-05-17T07:47:17.036000+00:00 |
| order_log_boot_rows | NOT_LOCALIZED_FROM_RETAINED_TAIL |
| order_log_override_rows | 26 |
| shadow_journal_override_rows | 26 |
| decision_ledger_terminal_counts | EXECUTED_AND_CLOSED=40, INVALID_FOR_DATASET=77, REJECTED_UPSTREAM=471 |
| trade_lifecycle_malformed_lines_skipped | 1 |
| config_snapshot_required_present | 8 / 8 |
| config_snapshot_parse_status_counts | PARSED_MAPPING=11 |
| recorder_coverage_sufficient | false |
| recorder_coverage_limit | BTCUSDT required horizon end not fully covered |

## override_inventory
| rid | ts_utc | symbol | original_direction_confidence | original_regime_confidence | decision_ledger_terminal_status | canonical_closed | close_reason | net_quote | fees_quote | exact_roundtrip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_BTCUSDT_1778936098521 | 2026-05-16T12:54:58.583000+00:00 | BTCUSDT | 0.01243838 | 0.524493564511 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778936699616 | 2026-05-16T13:04:59.673000+00:00 | BTCUSDT | 0.00323664 | 0.581876884695 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778937300900 | 2026-05-16T13:15:00.961000+00:00 | BTCUSDT | 0.00323664 | 0.583326306691 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778955599428 | 2026-05-16T18:19:59.546000+00:00 | BTCUSDT | 0.00363644 | 0.658527713532 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778956200544 | 2026-05-16T18:30:00.652000+00:00 | BTCUSDT | 0.00363644 | 0.549819961907 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778959201469 | 2026-05-16T19:20:01.587000+00:00 | BTCUSDT | 0.00066851 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778959802578 | 2026-05-16T19:30:02.704000+00:00 | BTCUSDT | 0.00066851 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778961003822 | 2026-05-16T19:50:03.934000+00:00 | BTCUSDT | 0.00098811 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778961605077 | 2026-05-16T20:00:05.184000+00:00 | BTCUSDT | 0.00098811 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778962205306 | 2026-05-16T20:10:05.424000+00:00 | BTCUSDT | 0.00336123 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778964603346 | 2026-05-16T20:50:03.458000+00:00 | BTCUSDT | 0.00392487 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778965504445 | 2026-05-16T21:05:04.506000+00:00 | BTCUSDT | 0.00392934 | 0.85 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778971802990 | 2026-05-16T22:50:03.064000+00:00 | BTCUSDT | 0.00352128 | 0.581562444581 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778972404161 | 2026-05-16T23:00:04.232000+00:00 | BTCUSDT | 0.00352128 | 0.642672644338 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778973004867 | 2026-05-16T23:10:04.931000+00:00 | BTCUSDT | 0.00727881 | 0.475570228499 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778974802809 | 2026-05-16T23:40:02.878000+00:00 | BTCUSDT | 0.00374543 | 0.546239908312 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778975403742 | 2026-05-16T23:50:03.815000+00:00 | BTCUSDT | 0.00548932 | 0.60212742561 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778976004910 | 2026-05-17T00:00:04.979000+00:00 | BTCUSDT | 0.00548932 | 0.586592485453 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778978102794 | 2026-05-17T00:35:02.867000+00:00 | BTCUSDT | 0.00528608 | 0.547324990925 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778978703848 | 2026-05-17T00:45:03.924000+00:00 | BTCUSDT | 0.00528608 | 0.406464213115 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778979304446 | 2026-05-17T00:55:04.524000+00:00 | BTCUSDT | 0.01066508 | 0.415762567753 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778991305469 | 2026-05-17T04:15:05.554000+00:00 | BTCUSDT | 0.01146745 | 0.556693802197 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_BTCUSDT_1778991900853 | 2026-05-17T04:25:00.948000+00:00 | BTCUSDT | 0.00763462 | 0.414037744027 | REJECTED_UPSTREAM | False |  |  |  | False |
| aurora_ETHUSDT_1778942102182 | 2026-05-16T14:35:02.281000+00:00 | ETHUSDT | 0.00165936 | 0.393710651691 | INVALID_FOR_DATASET | False |  |  |  | False |
| aurora_XRPUSDT_1778933700563 | 2026-05-16T12:15:00.632000+00:00 | XRPUSDT | 0.01995096 | 0.540410298943 | INVALID_FOR_DATASET | True | closed_loss | -13.08771079 | 1.80454079 | True |
| aurora_XRPUSDT_1778934901815 | 2026-05-16T12:35:01.888000+00:00 | XRPUSDT | 0.02243592 | 0.658187348576 | REJECTED_UPSTREAM | False |  |  |  | False |

## safety_boundary
| surface | post_boot_rows | override_applied_rows | expected_behavior | verdict |
| --- | --- | --- | --- | --- |
| authoritative_candidate_contract | 26 | 26 | should be admitted | PASS |
| candidate_contract_without_override | 0 | 0 | should remain zero | PASS |
| buy_or_long_direction_only | 0 | 0 | no leakage allowed | PASS |
| dual_failure | 0 | 0 | no leakage allowed | PASS |
| geometry_invalid | 0 | 0 | no leakage allowed | PASS |
| live_or_production_candidate_like | 0 | 0 | no leakage allowed | PASS |
| missing_selected_metadata | 0 | 0 | fail closed | PASS |
| sell_direction_only_noncandidate | 0 | 0 | no leakage allowed | PASS |

## outcome_summary
| metric | value | notes |
| --- | --- | --- |
| override_count | 26 | distinct admitted override rids in Package J |
| decision_ledger_status_mix | INVALID_FOR_DATASET=2, REJECTED_UPSTREAM=24 | authoritative downstream status mix for J override rids |
| canonical_closed_rows | 1 | canonical realized override rows in Package J |
| exact_roundtrip_rows | 1 | exact roundtrips among Package J canonical override closes |
| wins_losses_unresolved | 0 / 1 / 25 | Package J only |
| net_pnl_quote | -13.08771079 | aggregate Package J canonical override net |
| gross_pnl_quote | -11.28317 | aggregate Package J canonical override gross |
| fees_quote | 1.80454079 | aggregate Package J canonical override fees |
| fee_drag_ratio_of_abs_gross | 0.15993207494 | fees divided by absolute gross because Package J gross is negative |
| current_total_sample_i_plus_j | override=31, canonical_closes=5, net=57.25202672 | user-defined sample gate is reached at the current total sample |
| runtime_verdict | RUNTIME_INSUFFICIENT_CLOSES | J-only runtime remains close-sparse |
| outcome_verdict | NEGATIVE_J_WINDOW_SINGLE_CANONICAL_CLOSE | the only resolved Package J override close is a loss |

## canonical_propagation
| metric | value | interpretation |
| --- | --- | --- |
| nrr062_reject_rows_order_log | 25 | raw rejected NRR-062 rows remain the larger background cohort in J |
| override_rows_order_log | 26 | raw admitted override ORDER_INTENT rows |
| accepted_low_vol_order_intents | 26 | every admitted override row is a LOW_VOL ORDER_INTENT |
| objective_rows_for_override_rids | 26 | canonical trade decision rows exist for the full override cohort |
| canonical_override_closes | 1 | realized dataset captured one closed override row |
| exact_roundtrip_override_rows | 1 | that single captured close is an exact roundtrip |
| realized_match_coverage_pct | 12.9032 | diagnostics-only, not promotion-grade |
| realized_coverage_grade | SPARSE_DIAGNOSTIC | insufficient realized coverage |
| objective_coverage_grade | SPARSE_DIAGNOSTIC | source realized dataset not promotion-grade |
| objective_rows_preserve_override_token | false | canonical objective rows do not preserve raw override truth |
| decision_ledger_preserves_override_token | false | frozen decision ledger also does not preserve the token |
| objective_warnings | authority_request_journal absent; authority_response_journal absent | frozen-bundle limitation, not runtime logic change |
| realized_warning | TRADE_LIFECYCLE_JSON_ERRORS:1 | matches the retained one-line malformed trade_lifecycle caveat |

## replay_vs_runtime
| metric | package_f_replay | package_h_runtime | package_i_runtime | package_j_runtime | current_total_i_plus_j |
| --- | --- | --- | --- | --- | --- |
| cohort_size | 79 candidate rows | 1 admitted override rid | 5 admitted override rids | 26 admitted override rids | 31 admitted override rids |
| realized_or_terminal_outcomes | TP=25, SL=2, TIMEOUT=52 | 1 exact roundtrip close | 4 exact roundtrip closes, 1 submitted-not-filled | 1 exact roundtrip closed_loss, 25 unresolved terminal rows | 5 canonical closes total |
| net_quote | 825.2672997047 estimated replay net | 22.6742616 | 70.33973751 | -13.08771079 | 57.25202672 |
| leakage | BUY and dual-failure cohorts excluded offline | 0 | 0 | 0 | 0 |
| sample_fraction_vs_package_f | 1.0 | 1 / 79 = 0.012658227848101266 | 5 / 79 = 0.06329113924050633 | 26 / 79 = 0.3291139240506329 | 31 / 79 = 0.3924050632911392 |
| directional_read | positive offline segment thesis | positive first runtime observation | positive follow-up runtime observation | admission strong but resolved closes sparse and adverse | still net-positive overall, but stability now mixed |
| decision | replay authority for segment thesis | continue collection | continue collection | sample-gate reached only on cumulative basis | SAMPLE_GATE_REACHED_KEEP_TESTNET_ONLY |

## rollback_gate
| condition | value | interpretation |
| --- | --- | --- |
| verdict | NO_ROLLBACK_SIGNAL_SAMPLE_GATE_REACHED_KEEP_TESTNET_ONLY | no rollback trigger fired |
| override_observed | true | runtime cohort exists |
| boundary_leak_detected | false | no leakage in retained J contrast surfaces |
| override_outside_testnet_hybrid | false | no live or production leakage |
| realized_positive | false | Package J-only realized net |
| current_total_realized_positive | true | combined I+J net remains positive |
| sl_or_adverse_close_dominates | false | current total sample is not loss-dominant |
| j_window_negative_close_observed | true | Package J contributes one canonical loss |
| sample_gate_reached_current_total | true | I+J reaches 31 admitted override rids and 5 canonical closes |
| sample_size_sufficient_for_promotion | false | sample gate reached is not promotion-grade |
| objective_rows_preserve_override_token | false | observability limitation only |
| decision_ledger_preserves_override_token | false | observability limitation only |
| sidecar_authority_changed | false | no authority change in scope |
| production_scope_changed | false | no rollout widening |

Recommended action: Keep the Package G override unchanged in hybrid_live_data_testnet_exec only; do not promote, do not tune thresholds, and run a short post-sample-gate stability review because Package J adds one canonical override loss while the cumulative I+J sample only just reaches the 31 admitted / 5 canonical-close gate.

## changes_made
- Captured and froze the new authoritative runtime bundle at logs/frozen/nrr062_fresh_capture_20260517_080431.
- Augmented the frozen bundle after capture with frozen decision_ledger_v1.jsonl and FREEZE_REPORT.md so the bundle is audit-ready without modifying runtime or YAML behavior.
- Corrected the FREEZE_REPORT override counts to use the authoritative parsed low_vol_cost_floor override rows instead of an inflated substring count.
- Built the canonical realized dataset at calibrators/datasets/nrr062_testnet_override_runtime/package_j_realized_dataset.
- Built the canonical objective dataset at calibrators/datasets/nrr062_testnet_override_runtime/package_j_objective_dataset.
- Generated the Package J runtime artifacts under calibrators/datasets/nrr062_testnet_override_runtime: runtime ledger J, safety boundary audit J, canonical dataset propagation audit J, outcome analysis J, and rollback gate J in JSON, CSV, and Markdown forms as applicable.
- Added this final Package J report.

## validation
- Frozen manifest integrity: 1953 frozen files re-hashed, 1953 / 1953 matched recorded sha256 values.
- Config snapshot integrity: 11 copied config files re-hashed, 11 / 11 matched recorded sha256 values.
- Generated artifact JSON parse: 5 / 5 files parsed successfully.
- Schema validation via calibrators.datasets.schema_registry.validate_row: package_j_realized=4 rows, package_j_objective_decisions=588 rows, package_j_objective_realized=4 rows.
- Runtime/config git surfaces unchanged in scope: no Package J edits were made under apps/reference or config/aurora.
- Focused pytest command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_low_vol_cost_floor_gate.py tests/domains/decision_making/test_low_vol_direction_confidence_contract.py tests/config/test_decision_making_contracts.py tests/test_calibrators_import_boundary.py
- Pytest result: 102 passed, 0 failed, runtime 7.61s.
- Note: the VS Code runTests tool did not discover tests from valid file paths, so focused pytest was run directly to complete the required validation.

## runtime_behavior_change
NONE.

- No YAML or config values were changed.
- No Python runtime logic was changed.
- No override conditions were expanded.
- No thresholds were tuned.
- No sidecar authority was changed.
- No live or production promotion was performed.
- Package J changed only frozen-bundle artifacts and reports.

## next_recommended_package
Recommended next package: CALIBRATORS_NRR_PACKAGE_K_POST_J_SAMPLE_GATE_STABILITY_REVIEW.

Proposed Package K objective: keep hybrid_live_data_testnet_exec-only runtime collection unchanged and run a short stability review window after the sample gate has been reached. Package K should test whether the new Package J loss remains isolated or becomes loss-dominant, while preserving the same hard constraints: no YAML edits, no threshold tuning, no runtime logic changes, no scope widening, and no production promotion. Rollback should be considered only if leakage appears or the current total sample turns clearly adverse.
