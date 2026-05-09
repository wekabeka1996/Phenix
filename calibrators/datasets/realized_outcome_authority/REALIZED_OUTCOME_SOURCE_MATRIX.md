# REALIZED_OUTCOME_SOURCE_MATRIX

| Source | Identity Coverage | Outcome Coverage | Fee Coverage | Schema Stability | Promotion Suitability | Risks |
| --- | --- | --- | --- | --- | --- | --- |
| reports/executed_trades_master.csv | NONE (0 rows) | NONE | NONE | LOW | NO | manual_forensics_output, stale_vs_current_runtime_logs, header_only_on_empty_subset |
| logs/order_log_v1.jsonl | PARTIAL exact via rid/lifecycle/order ids | POSITION_CLOSED=49 | fees_rows=49 | MEDIUM | NO_DIRECT | fill_identity_can_shift_from_rid, mixed_event_families_require_bridge_logic, not_a_single_row_per_trade_surface |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | EXACT decision_id/rid | realized_rows=7 | fee_rows=7 | MEDIUM_HIGH | NO_PARTIAL | realized_fields_present_only_on_subset, missing_full_execution_geometry |
| decision_ledger + order_log exact bridge | EXACT decision bridge with lifecycle canonicalization residual | bridge_candidate_overlap=31 | order_log_fee_rows=49 | MEDIUM | BEST_CANDIDATE_PENDING_CANONICALIZATION | requires_explicit_canonicalization_rules, must_preserve_fee_and_exit_semantics, close_rows_may_need_lifecycle_bridge_not_raw_rid |
| data/order_ledger.db::orders | EXECUTION_ONLY | NONE | NONE | HIGH | NO | missing_realized_outcome_fields, no_decision_bridge |
| logs/trade_lifecycle.jsonl | PARTIAL exact bridge overlap=24 | LOW | LOW | MEDIUM | NO_DIRECT | bad_json_rows_present, no_explicit_fee_or_net_pnl_surface |
| future_canonical_realized_outcome_dataset | DESIGNED_EXACT | DESIGNED_COMPLETE | DESIGNED_COMPLETE | HIGH | YES_AFTER_BUILD | not_implemented_yet |