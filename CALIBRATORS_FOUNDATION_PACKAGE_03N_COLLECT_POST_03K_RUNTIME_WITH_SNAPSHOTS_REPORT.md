# AGENT_REPORT_V1

## verdict
POST_03K_CAPTURE_WITH_SPARSE_COVERAGE

## problem_framing
03L already ruled out an in-repo startup or freeze-copy path that truncates or deletes logs/order_log_v1.jsonl. A fresh post-03K runtime capture was still required to answer the remaining runtime question: does the repo-root authority order log now persist across a real session strongly enough for snapshot-based realized-outcome and close-coverage artifacts to use the authority surface directly, without promoting frozen data or widening canonicalization.

## facts
- Active runtime evidence existed during capture: two python -m apps.reference.main processes and two python -m apps.reference.domains.neocortex.main processes were running.
- Pre-run git capture was branch main at commit 1a2e7f6d7437d2262a1921fb116a51a53ab488b0 with an already-dirty worktree before this package started.
- Pre-run authority source stats were: logs/order_log_v1.jsonl exists, 526 rows, 1 BOOT row, 1096073 bytes, sha256 b0c1b3df2b55c54822225ba1bacfe2014ba102b5e8882fae82dc019e4b3c258c, time range 2026-05-09T22:15:03.691000+00:00 to 2026-05-10T16:40:06.128000+00:00.
- Pre-run decision ledger stats were: logs/shadow_telemetry/decision_ledger_v1.jsonl exists, 93 rows, 459451 bytes, sha256 dc4abdf2b3dc389907799c209e64a35ba006b91210b1cf07bf99054af230d685, time range 2026-05-09T22:15:03.634000+00:00 to 2026-05-10T16:35:03.688000+00:00.
- Pre-run trade lifecycle stats were: logs/trade_lifecycle.jsonl exists, 103463 rows, 975006589 bytes, sha256 cee1ebe2ab5ee23887107886af81aeef2acb182ea170117b3745d9b534f4addf, time range 2026-05-09T21:58:22.983000+00:00 to 2026-05-10T18:39:26.519000+00:00.
- The exact requested markdown inputs CALIBRATORS_FOUNDATION_PACKAGE_03K_RUNTIME_ORDER_LOG_RETENTION_REPAIR_REPORT.md, CALIBRATORS_FOUNDATION_PACKAGE_03L_EXTERNAL_RUNTIME_STARTUP_ORDER_LOG_RETENTION_FORENSIC_REPORT.md, ORDER_LOG_RETENTION_AUDIT.md, ORDER_LOG_STARTUP_FLOW_MAP.md, and ORDER_LOG_FREEZE_COPY_AUDIT.md were not present in the workspace by those literal filenames during this package.
- Direct script invocation of calibrators/datasets/build_realized_outcome_dataset.py failed with ModuleNotFoundError: No module named calibrators. Module execution via python -m was used instead, matching the known repo import-order boundary.
- The realized source snapshot manifest at artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/source_snapshot_manifest.json was generated at 2026-05-10T18:40:56.488365+00:00 with missing_required_sources=[] and warnings=[].
- The snapshot recorded all three sources as current_workspace_authority.
- Snapshot copy hash verification succeeded for all copied sources: decision_ledger, order_log, and trade_lifecycle snapshot files matched the source sha256 values recorded in the manifest.
- Snapshot source counts were: decision_ledger 93 rows, order_log 526 rows, trade_lifecycle 103589 rows.
- Snapshot source time ranges were: decision_ledger 2026-05-09T22:15:03.634000+00:00 to 2026-05-10T16:35:03.688000+00:00; order_log 2026-05-09T22:15:03.691000+00:00 to 2026-05-10T16:40:06.128000+00:00; trade_lifecycle 2026-05-09T21:58:22.983000+00:00 to 2026-05-10T18:40:47.938000+00:00.
- The realized dataset manifest reported: eligible_decision_rows=93, matched_rows=4, unmatched_rows=89, match_coverage_pct=4.3011, exact_roundtrip_count=3, diagnostics_only=true, promotion_grade=false.
- The realized data_quality blockers were PARTIAL_EXACT_ROUNDTRIPS, INSUFFICIENT_REALIZED_ROWS, and INSUFFICIENT_REALIZED_COVERAGE.
- The realized manifest recorded one warning: TRADE_LIFECYCLE_JSON_ERRORS:1.
- The objective dataset manifest reported: decision_rows_count=93, realized_rows_count=4, exact_roundtrip_count=3, match_coverage_pct=4.3011, diagnostics_only=true, promotion_grade=false.
- The objective data_quality blockers were SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE, INSUFFICIENT_REALIZED_ROWS, INSUFFICIENT_REALIZED_COVERAGE, and PARTIAL_EXACT_ROUNDTRIPS.
- The close coverage audit ran with audit_source_kind=artifact_authority_snapshot and authority_order_log_exists=true.
- Close coverage unmatched classification counts were: NOT_EXECUTED_OR_REJECTED=77, CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY=8, LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED=2, CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED=1, INCONCLUSIVE=1.
- Order log taxonomy counts were: alternative terminal event present=77, close fill present=9, duplicate close candidates=5, entry fill present=1, no order_log rows=1.
- Lifecycle bridge audit summary_counts were: has_terminal_close=14, has_fill_ingress=15, has_lifecycle_bridge_rows=0, has_trade_bridge_rows=0.
- Nested authority order_log payloads contained trading_mode=hybrid_live_data_testnet_exec.
- Observed active symbols in the captured runtime window were ETHUSDT, XRPUSDT, BTCUSDT, and BNBUSDT.
- After the snapshot and builder runs, live logs/order_log_v1.jsonl measured 531 rows with BOOT=1, proving post-snapshot append without reset during this check.
- Schema validation succeeded for artifacts/calibration_datasets/_post_03k_realized_outcome/realized_trades.jsonl, artifacts/calibration_datasets/_post_03k_objective/trade_decisions.jsonl, and artifacts/calibration_datasets/_post_03k_objective/realized_trades.jsonl through calibrators.datasets.schema_registry.
- Pytest validation passed: 17 tests passed in 5.68s for tests/calibrators/test_realized_outcome_builder.py, tests/calibrators/test_runtime_close_coverage_audit.py, and tests/test_calibrators_import_boundary.py.

## inferences
- The 03K order_logger path repair appears to have stabilized the repo-root authority sink for this runtime window. The strongest evidence is that the source snapshot captured logs/order_log_v1.jsonl as current_workspace_authority with 526 rows and no missing sources, and the live file later grew to 531 rows while BOOT stayed at 1.
- The post-03K failure mode is materially different from 03J. 03J had an authority order_log snapshot of only 2 rows and 0% realized coverage; this post-03K capture retained a 526-row authority snapshot and recovered 4 matched realized rows with 4.3011% coverage.
- Coverage is still sparse because most eligible decisions in this window were not realized exact roundtrips. The dominant unmatched bucket is NOT_EXECUTED_OR_REJECTED, and a secondary bucket shows close evidence in trade_lifecycle without matching order_log POSITION_CLOSED evidence.
- The remaining evidence points more toward close-event observability or bridge completeness than toward authority path reset or snapshot corruption.

## assumptions
- The order_log BOOT row at 2026-05-09T22:15:03.691000+00:00 marks the start of the relevant order_logger session for this package.
- The observed symbol set ETHUSDT, XRPUSDT, BTCUSDT, and BNBUSDT is a reasonable proxy for the enabled symbol set during this window, even though full config enablement was not re-derived from YAML in this package.
- Using python -m for the builder and audit commands is behaviorally equivalent to the requested command intent for this package because the direct file execution path failed before repo-root sys.path initialization.

## unknowns
- Whether old logs were manually deleted before the observed BOOT row.
- Whether any out-of-repo launcher or cleanup step ran before the current window.
- The process working directory at runtime.
- Whether the host or process tree was restarted before the captured BOOT marker.
- Whether a materially longer window would reduce the 77 NOT_EXECUTED_OR_REJECTED rows enough to change promotion-grade conclusions.

## collection_window
| Start | End | Duration | Mode | Symbols | Restarts | Manual Cleanup |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09T22:15:03.691000+00:00 | 2026-05-10T18:40:56.488365+00:00 | 20h 25m 52.797s | hybrid_live_data_testnet_exec | ETHUSDT, XRPUSDT, BTCUSDT, BNBUSDT | not observed in authority order_log during this window; system-level restart unknown | unknown |

Additional runtime notes: external cleanup/launcher usage unknown; process CWD unknown.

## source_snapshot_summary
| Source | Exists | Rows | BOOT Rows | Size | SHA256 | Time Range |
| --- | --- | --- | --- | --- | --- | --- |
| decision_ledger | yes | 93 | 0 | 459451 | dc4abdf2b3dc389907799c209e64a35ba006b91210b1cf07bf99054af230d685 | 2026-05-09T22:15:03.634000+00:00 -> 2026-05-10T16:35:03.688000+00:00 |
| order_log | yes | 526 | 1 | 1096073 | b0c1b3df2b55c54822225ba1bacfe2014ba102b5e8882fae82dc019e4b3c258c | 2026-05-09T22:15:03.691000+00:00 -> 2026-05-10T16:40:06.128000+00:00 |
| trade_lifecycle | yes | 103589 | 0 | 976863589 | 1117c26b4cf61c068b57bb15eef4aaacb61a0be04d0d1462e3200076ca517c38 | 2026-05-09T21:58:22.983000+00:00 -> 2026-05-10T18:40:47.938000+00:00 |

All three copied snapshot files matched the source SHA256 recorded in the manifest.

## realized_builder_results
| Eligible | Matched | Unmatched | Coverage % | Exact Roundtrips | Diagnostics Only | Promotion Grade | Blockers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 93 | 4 | 89 | 4.3011 | 3 | true | false | PARTIAL_EXACT_ROUNDTRIPS; INSUFFICIENT_REALIZED_ROWS; INSUFFICIENT_REALIZED_COVERAGE |

## objective_builder_results
| Decisions | Realized | Exact Roundtrips | Coverage % | Diagnostics Only | Promotion Grade | Blockers |
| --- | --- | --- | --- | --- | --- | --- |
| 93 | 4 | 3 | 4.3011 | true | false | SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE; INSUFFICIENT_REALIZED_ROWS; INSUFFICIENT_REALIZED_COVERAGE; PARTIAL_EXACT_ROUNDTRIPS |

## close_coverage_audit_summary
Audit source kind: artifact_authority_snapshot

Artifact authority snapshot used: yes

Order log taxonomy summary: alternative terminal event present=77; close fill present=9; duplicate close candidates=5; entry fill present=1; no order_log rows=1.

Lifecycle bridge summary: has_terminal_close=14; has_fill_ingress=15; has_lifecycle_bridge_rows=0; has_trade_bridge_rows=0.

| Bucket | Count | Interpretation |
| --- | --- | --- |
| NOT_EXECUTED_OR_REJECTED | 77 | Dominant sparse-coverage bucket; most eligible decisions did not become realized closes. |
| CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY | 8 | Runtime close evidence exists in trade_lifecycle but not as order_log POSITION_CLOSED. |
| LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED | 2 | Small residual bridge opportunity remains, but it is not the dominant cause of sparsity. |
| CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED | 1 | A closed trade exists without matching order_log POSITION_CLOSED authority evidence. |
| INCONCLUSIVE | 1 | Residual unmatched row with insufficient evidence for stronger classification. |

## baseline_comparison
| Metric | 03G | 03J | Post-03K | Interpretation |
| --- | --- | --- | --- | --- |
| Eligible decisions | 53 | n/a | 93 | Window sizes differ; direct coverage comparisons should be normalized by percentage, not row count alone. |
| Matched realized rows | 8 | 0 | 4 | Post-03K recovered non-zero matches versus 03J, but remains below 03G. |
| Coverage % | 15.0943 | 0.0 | 4.3011 | Coverage improved materially over 03J but remains sparse and diagnostics-only. |
| Promotion grade | false | false | false | No baseline reached promotion-grade realized coverage. |
| Authority order_log snapshot rows | n/a | 2 | 526 | Post-03K authority retention is dramatically stronger than the 03J sparse-authority failure mode. |
| Authority source behavior | not recorded here | authority snapshot too sparse | current_workspace_authority snapshot retained and later appended to 531 live rows | The current result supports retention stability rather than reset during this window. |

## classification
Class: POST_03K_RETENTION_STABLE_COVERAGE_STILL_SPARSE

Confidence: MEDIUM

Evidence: the realized source snapshot captured logs/order_log_v1.jsonl directly as current_workspace_authority with 526 rows, missing_required_sources=[], warnings=[], and copy hashes matching the source manifest; the live authority file later measured 531 rows with BOOT still equal to 1; realized coverage recovered above 0% to 4.3011 but unmatched rows remained dominated by NOT_EXECUTED_OR_REJECTED plus trade_lifecycle-only close evidence.

## changes_made
- Generated artifacts under artifacts/calibration_datasets/_post_03k_realized_outcome
- Generated artifacts under artifacts/calibration_datasets/_post_03k_objective
- Generated audit artifacts under calibrators/datasets/runtime_close_coverage_post_03k
- Generated this report

No production code, trading logic, lifecycle semantics, config models, or YAML were edited in this package.

## validation
- python calibrators/datasets/build_realized_outcome_dataset.py --out-dir artifacts/calibration_datasets/_post_03k_realized_outcome
  Result: failed immediately with ModuleNotFoundError: No module named calibrators.
- python -m calibrators.datasets.build_realized_outcome_dataset --out-dir artifacts/calibration_datasets/_post_03k_realized_outcome
  Result: Rows emitted=4, Exact roundtrips=3, Match coverage pct=4.3011, Diagnostics only=true, Promotion grade=false.
- python -m calibrators.strategies.build_objective_stack_dataset --out-dir artifacts/calibration_datasets/_post_03k_objective --realized-outcome-dataset artifacts/calibration_datasets/_post_03k_realized_outcome/realized_trades.jsonl
  Result: Decision rows=93, Realized rows=4, Exact roundtrips=3, Match coverage pct=4.3011, Builder valid=true, Schema valid=true, Promotion grade=false.
- python -m calibrators.datasets.audit_runtime_close_coverage --realized-artifact-dir artifacts/calibration_datasets/_post_03k_realized_outcome --out-dir calibrators/datasets/runtime_close_coverage_post_03k
  Result: Eligible decisions=93, Unmatched decisions=89, Authority order_log exists=true, Audit source kind=artifact_authority_snapshot.
- Parsed artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/source_snapshot_manifest.json
  Result: missing_required_sources=[], warnings=[], and all copied snapshot hashes matched the source SHA256 values in the manifest.
- Parsed and schema-validated artifacts/calibration_datasets/_post_03k_realized_outcome/realized_trades.jsonl, artifacts/calibration_datasets/_post_03k_objective/trade_decisions.jsonl, and artifacts/calibration_datasets/_post_03k_objective/realized_trades.jsonl through calibrators.datasets.schema_registry
  Result: validation succeeded.
- python -m pytest tests/calibrators/test_realized_outcome_builder.py tests/calibrators/test_runtime_close_coverage_audit.py tests/test_calibrators_import_boundary.py -q
  Result: 17 passed in 5.68s.

## runtime_behavior_change
- trading behavior changed: no
- order lifecycle semantics changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
CALIBRATORS_FOUNDATION_PACKAGE_03P_RUNTIME_CLOSE_TRACE_INSTRUMENTATION
