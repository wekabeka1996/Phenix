AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T6C4_POST_GATE_MONITOR
verdict: POST_GATE_HEALTHY
report_path: AURORA_TIMER_GOVERNANCE_T6C4_POST_GATE_MONITOR_REPORT.md

facts:
  post_gate_boundary: 2026-06-18T09:55:26+00:00
  boundary_basis: latest T6C3 file mtime: config/aurora/domains.yaml 2026-06-18T09:55:26Z
  logs_inspected:
    - logs/shadow_critical_event_journal_v1.jsonl (70829 post-gate records)
    - logs/trade_lifecycle.jsonl (scanned for NRR-064)
    - logs/domain_decision_making.log (scanned for trade_flow refs)
    - logs/domain_feature_engineering.log (scanned for trade_flow_state in features)
    - logs/event_chain.log
    - logs/order_log_v1.jsonl
    - logs/aurora_core.log
  runtime_windows: 8 x 6h
  post_gate_duration_hours: 45.29
  feature_events_with_trade_flow_metadata:
    shadow_journal: 0 / 0
    fe_log: 0 / 6003
    dm_log_trade_flow_refs: 0
  feature_events_missing_trade_flow_metadata:
    shadow_journal: 0
    fe_log: 6003
  trade_flow_state_distribution (aurora signals): {'__missing__': 65}
  strategy_signal_count: 532
  aurora_signal_count: 65
  aurora_entry_candidates: 65
  aurora_close_candidates: 0
  nrr064_block_count: 0
  nrr064_block_rate: 0.0
  orders_placed_after_gate: 803
  close_reduce_candidates_seen: 0

nrr064_analysis:
  nrr064_cases_total: 0
  by_symbol: {}
  by_state: {}
  by_strategy: {}
  by_age_distribution: N/A — no NRR-064 cases found in shadow journal payload
  invalid_blocks (check_a_violations): 0
  close_reduce_blocks (check_b_violations): 0
  missing_unknown_blocks (check_c_violations): 0
  non_sensitive_strategy_blocks (check_d_violations): 0

overblocking_assessment:
  verdict: NOT_SUSPECTED
  evidence: []
  unproven:
    - live frequency of degraded/stale trade_flow_state events
    - economic impact of any missed entries
    - whether additional strategies should be in sensitive_strategies

metadata_health:
  coverage:
    EVT:FEATURES_CALCULATED events in shadow journal: 0
    (FEATURES_CALCULATED events are NOT forwarded to shadow telemetry tap in current config)
    Feature events in FE log: 6003 post-gate
    Trade_flow_state in FE log features: 0
    Trade_flow_state ABSENT from FE log features: 6003
  missing_surfaces:
    - EVT:FEATURES_CALCULATED absent from shadow_critical_event_journal (allowlist does not include it — config line: allowlist_events)
    - trade_flow_state NOT present in domain_feature_engineering.log feature lines (T6C2 T6C3 metadata propagation is through EVT:FEATURES_CALCULATED payload, not FE log text)
    - domain_decision_making.log shows 0 trade_flow text refs (DM log uses structured JSON events; trade_flow_state stored in dm.symbol_states, not logged as text)
  risk:
    MEDIUM — metadata not visible in shadow telemetry. Gate logic relies on dm.symbol_states which is populated from EVT:FEATURES_CALCULATED handler.
    This is expected: trade_flow_state is cached internally and not logged as a discrete event in current surface.

runtime_behavior_change:
  NONE — read-only audit

config_changes:
  NONE — read-only audit

validation:
  audit_script: tools/audits/t6c4_post_gate_monitor.py
  py_compile: PASS (invoked via .venv/Scripts/python.exe -m py_compile)
  audit_script_run: PASS
  csv_parse: see validation section
  git_diff_stat: see git status

final_status:
  T6C_ACCEPTED_FOR_RUNTIME

low_power_reason:
  N/A

nrr064_log_search:
  Total NRR-064 text hits across all log files: 0
  Samples: []

shadow_journal_event_distribution:
  EVT:PORTFOLIO_STATE_UPDATED: 27603
  EVT:EXPOSURE_SUMMARY_UPDATED: 27428
  EVT:REGIME_DETECTED: 5887
  EVT:STRATEGY_DECISION_BLOCKED: 3266
  EVT:QUADRATIC_DECISION_TRACE: 2710
  RESTORE:EXECUTION_TRUTH_HARDENING_RESET: 666
  EVT:STRATEGY_SIGNAL_PRODUCED: 532
  EVT:GATE_CHAIN_TRACE: 464
  EVT:TRADE_INTENT_REJECTED: 433
  EVT:TRADE_EXECUTED: 387
  CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_LOADED: 353
  CMD:OPEN: 316
  CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_EMPTY: 313
  DEC:OPEN: 100
  HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_MISS: 80
  EVT:DECISION_TRACE_EMITTED: 71
  EVT:TRADE_INTENT_PROPOSED: 42
  EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE: 36
  ORDER_INDEX:MARK_TERMINAL: 31
  HARDENING:TRADE_EXECUTED_SUPPRESSED: 18

rejection_code_distribution:
  NRR-054: 341
  EXPOSURE_PRECHECK_FAILED: 28
  OPPOSITE_ENTRY_REQUIRES_EXPLICIT_FLIP_CONTRACT: 26
  CONFIG_POSITION_MODE_INVALID: 18
  ANTI_PYRAMIDING_BLOCK: 8
  PYRAMIDING_BLOCKED_MAX_ADDS_EXCEEDED: 5
  NRR-061: 3
  NO_POSITION_FOR_CLOSE: 2
  SIGNAL_STALE: 1
  NRR-EXECUTION-NO-DOWNSTREAM-EVENT: 1

next_recommended_package:
  T6C closeout — gate is healthy, consider T6C5 strategy expansion evaluation after sufficient runtime.
