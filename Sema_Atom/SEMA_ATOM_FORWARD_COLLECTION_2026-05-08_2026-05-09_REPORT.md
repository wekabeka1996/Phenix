# SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT

## Verdict
FORWARD_COLLECTION_COMPLETED_WITH_RESIDUALS

## Scope
- Offline forward collector from frozen Aurora log slice to new SAF slice and index.
- Read-only batch collection only. No live logic, policy, gates, enforcement, or runtime journal writes.

## Inputs Read
- order_log: C:\Users\user\Music\Phenix\logs\order_log_v1.jsonl
- trade_lifecycle: C:\Users\user\Music\Phenix\logs\trade_lifecycle.jsonl
- shadow_telemetry: C:\Users\user\Music\Phenix\logs\shadow_telemetry
- recorder_root: C:\Users\user\Music\Phenix\data\recorder
- baseline_saf: C:\Users\user\Music\Phenix\aurora_real_logs_v02.saf.jsonl
- poc02_report: C:\Users\user\Music\Phenix\SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md
- poc03_report: C:\Users\user\Music\Phenix\SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md
- poc03b_manifest: C:\Users\user\Music\Phenix\SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json
- poc04_report: C:\Users\user\Music\Phenix\SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md
- missing_required_inputs: []
- missing_optional_inputs: []

## Time Window
- from: 2026-05-08
- to: 2026-05-09
- slice_id: 2026-05-08_2026-05-09
- window_start_ts_ms: 1778198400000
- window_end_ts_ms_exclusive: 1778371200000
- log_dates_observed: ["2026-05-08"]
- recorder_dates_available: ["2026-05-08"]
- recorder_dates_missing: ["2026-05-09"]

## Output Artifacts
- aurora_forward_slice_2026-05-08_2026-05-09.saf.jsonl
- SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT.md
- SEMA_ATOM_FORWARD_COLLECTION_INDEX.json

## Accepted Reducer Results
- log lines read: 86
- accepted close events found: 1
- accepted contracts completed: 0
- incomplete_accepted_missing_realized_pnl_net: 1
- accepted incomplete buckets: {"incomplete_accepted_missing_realized_pnl_net": 1, "incomplete_accepted_unresolved_pnl_status": 1}

## Rejected Collector Results
- rejected events found: 47
- rejected with reference_price: 43
- rejected missing reference_price: 4
- rejected missing critical fields: 0
- rejected evaluated: 43

## Offline Replay Results
- MFE/MAE computed: 1
- MFE/MAE missing: 0
- rejected missing market coverage: 0

## SemaAtom Encoding Results
- atoms created: 43
- accepted_atoms_created: 0
- rejected_atoms_created: 43
- diagnostics_only_atoms_created: 0
- atoms_created_reconciliation_ok: True
- atoms skipped: 1
- encoding errors: 0

## Context Migration
- new contexts: 6
- existing contexts updated: 6
- contexts promoted from low-support: 3
- contexts still low-support: 2
- new_context_keys: ["BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.75..1.00", "SOLUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25", "SOLUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50", "SOLUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75", "SOLUSDT|BUY|aurora|LOW_VOLATILITY|0.75..1.00", "XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75"]

## Reference Price Coverage
- rejected_reference_price_coverage: 0.9148936170212766

## MFE/MAE Coverage
- computed: 1
- missing: 0

## Missing Field Histogram
- histogram: {"realized_pnl_net": 1}

## Deduplication
- duplicates_detected: 0
- duplicates_skipped: 0

## Error Samples
- none

## Residual Risks
- Requested date window exceeds recorder date coverage for at least one day.

## Next Recommended Step
- SEMA_ATOM_FC_02_MULTI_SLICE_REVALIDATION
