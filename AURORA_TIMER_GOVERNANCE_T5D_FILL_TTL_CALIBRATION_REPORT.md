AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5D_FILL_TTL_CALIBRATION
verdict: CALIBRATION_PATCHED_AND_VALIDATED
report_path: AURORA_TIMER_GOVERNANCE_T5D_FILL_TTL_CALIBRATION_REPORT.md

problem:
- Evaluate whether the global watchdog backstop can be reduced from 3600000 to 1800000 without changing per-order override behavior, order lifecycle behavior, or watchdog semantics.
- Admit only the minimal config patch if evidence and focused tests prove it is safe.

facts:
- exact requested historical report filenames were not present in the workspace: AURORA_TIMER_GOVERNANCE_T5A_WATCHDOG_TTL_PROOF_REPORT.md, AURORA_TIMER_GOVERNANCE_T5A1_WATCHDOG_SSOT_SPLIT_BRAIN_REPORT.md, AURORA_TIMER_GOVERNANCE_T5B_FILL_TTL_CALIBRATION_STUDY.md, AURORA_TIMER_GOVERNANCE_T5C_WATCHDOG_OBSERVABILITY_CLEANUP_REPORT.md, DEF_WATCHDOG_DEREG_AFTER_FILL_REPORT.md
- corroborating SSOT references were found in CONFIG_SURFACE_LEDGER_SEED_v1.md, CONFIG_OWNERSHIP_MAP_v1.md, and EXECUTION_CONFIG_SPLIT_AUDIT_REPORT_v1.md, plus live watchdog regression tests.
- current value before patch: 3600000
- proposed value: 1800000
- max observed legitimate fill age: 965236
- p95/p99 fill age: 495737 / 809179
- candidate simulation result: 1800000 = BACKSTOP_ONLY; 3600000 = BACKSTOP_ONLY
- per_order_override coverage: 60/60 calibration-relevant Aurora LIMIT/GTX entries; fill_ttl_source=per_order_override; fill_ttl_override_ms always 1200000
- global_watchdog observations: 0
- stale watchdog status: STALE_WATCHDOG_SUSPECTED; one BNBUSDT symbol-only timeout-after-position-closed suspicion; not lifecycle-confirmed
- no observed legitimate fill exceeded 1800000
- no observed cancel/timeout terminal required 3600000
- lowering the global backstop does not change the observed Aurora LIMIT/GTX path because the operative per-order override remains 1200000

inferences:
- On the observed Aurora entry path, 3600000 behaves as a dormant backstop rather than the operative timeout.
- Reducing the global backstop to 1800000 preserves a 30 minute margin above the maximum observed legitimate fill and remains above the active 1200000 per-order timeout.

assumptions:
- The unrelated broad-suite failures observed in optional sweeps are not caused by the T5D fill_ttl calibration because they exercise untouched contracts and unrelated config/runtime seams.

unknowns:
- exact historical watchdog report artifacts requested by name are absent from the workspace
- fresh runtime still contains no observed global_watchdog path
- non-Aurora future users of the global backstop remain sparsely evidenced in this package

admission_decision:
- criteria passed:
- max observed legitimate fill age 965236 < 1800000
- p99 observed legitimate fill age 809179 < 1800000
- 1800000 candidate has BACKSTOP_ONLY risk in simulation
- no lifecycle-confirmed stale watchdog defect remains open
- no observed global_watchdog order proves need for 3600000
- focused tests prove canonical config value, runtime propagation, per-order override precedence, and fail-closed missing-config behavior
- criteria failed:
- none
- decision:
- ADMIT minimal calibration patch; reduce only trading.execution.watchdog.fill_ttl_ms from 3600000 to 1800000

implementation:
- files changed:
- config/aurora/trading.yaml
- tests/config/test_watchdog_fill_ttl_calibration_t5d.py
- tests/config/test_watchdog_ssot_split_brain_governance.py
- tests/domains/execution_position/test_watchdog_ttl_governance.py
- config value changed:
- trading.execution.watchdog.fill_ttl_ms: 3600000 -> 1800000
- tests added:
- tests/config/test_watchdog_fill_ttl_calibration_t5d.py
- runtime behavior expected:
- global watchdog backstop is now 30 minutes
- Aurora LIMIT/GTX entries still use per-order override 1200000 and should continue timing out at 20 minutes on the observed path

tests:
- Added focused T5D calibration checks for canonical YAML value, system watchdog absence, runtime propagation into OrderTimeoutWatchdog, per-order override precedence, and fail-closed missing fill_ttl_ms behavior.
- Updated watchdog SSOT/governance tests to assert the calibrated 1800000 canonical backstop.

validation:
- pytest tests/config/test_watchdog_fill_ttl_calibration_t5d.py -q: PASS (5 passed)
- pytest tests/domains/execution_position/test_watchdog_ttl_governance.py -q: PASS (18 passed)
- pytest tests/config/test_watchdog_ssot_split_brain_governance.py -q: PASS (10 passed)
- pytest tests/domains/execution_position/test_watchdog_observability_t5c.py -q: PASS (12 passed)
- pytest tests/domains/execution_position/test_watchdog_dereg_after_fill.py -q: PASS (7 passed)
- pytest tests/domains/execution_position -k "watchdog or timeout" -q: PASS (90 passed, 1544 deselected)
- pytest tests/config -q: FAIL, unrelated broad-suite failures outside T5D scope
- tests/config/test_execution_position_contracts.py::test_execution_position_extraction_preserves_model_contract
- tests/config/test_fail_closed_config_loading.py::TestFailClosedEventDedup::test_fsm_fails_without_event_dedup_config
- tests/config/test_fail_closed_config_loading.py::TestFailClosedEventDedup::test_fsm_loads_event_dedup_from_config
- tests/config/test_legacy_reintegration_contracts.py::test_md_amr_profile_loads_when_assigned_in_registry
- tests/config/test_legacy_reintegration_contracts.py::test_bracket_health_uses_md_amr_exit_profile
- pytest tests/domains/execution_position -q: FAIL, unrelated broad-suite failures outside T5D scope
- tests/domains/execution_position/contract_layer/test_emitted_surface_audit.py::test_emitted_surface_audit_matches_current_runtime_contracts
- tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py::test_fsm_cleanup_enabled_prefers_root_execution_true
- tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py::test_fsm_cleanup_enabled_prefers_root_execution_false
- tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py::test_fsm_execute_decision_open_with_backoff
- tests/domains/execution_position/test_execution_position_boundary_policy_ast.py::TestCrossPeerViolationBaseline::test_startup_truth_orchestrator_cross_peer_count_at_baseline
- git diff --stat:
- global repository diff currently shows unrelated tracked changes in 14 files; T5D-related tracked changes are mixed with pre-existing worktree edits
- filtered T5D status: config/aurora/trading.yaml modified; tests/config/test_watchdog_ssot_split_brain_governance.py modified; tests/domains/execution_position/test_watchdog_ttl_governance.py modified; tests/config/test_watchdog_fill_ttl_calibration_t5d.py new
- git diff --name-only:
- global repository name-only includes unrelated tracked files outside T5D scope; T5D-local files are config/aurora/trading.yaml, tests/config/test_watchdog_ssot_split_brain_governance.py, tests/domains/execution_position/test_watchdog_ttl_governance.py, tests/config/test_watchdog_fill_ttl_calibration_t5d.py

runtime_behavior_change:
- global watchdog backstop reduced from 60min to 30min
- Aurora LIMIT/GTX per-order override remains 20min and should dominate observed entry path

config_changes:
- trading.execution.watchdog.fill_ttl_ms: 3600000 -> 1800000

unproven:
- exact historical watchdog report files requested by name were not present in the workspace
- global_watchdog path remains unobserved in fresh data
- md_amr / llm_microstructure observed fill-age distribution remains sparse or unproven in this package
- stale watchdog symbol-only suspicion remains not lifecycle-confirmed

risks:
- future non-override paths may timeout at 30min instead of 60min
- if a stale watchdog defect still exists in another identity path, it will surface earlier
- broad config and full execution_position suites currently have unrelated failures that should be resolved separately before treating the whole tree as green

next_recommended_package:
- T5E post-calibration runtime monitor
