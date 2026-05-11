# PKG-7 Provenance Contract

## Purpose

Every research trial must persist enough evidence to answer three questions without re-running the study:

1. What was requested?
2. What effective config was actually materialized?
3. Did the trial run, or was it rejected before runtime?

## Runtime Contract

PKG-7 adds additive runtime metadata at:

- `system_meta.runtime.research_trial`

Persisted fields:

- `trial_id`
- `arm_id`
- `trial_params_json`
- `expected_changed_paths`
- `effective_changed_values`
- `overlay_hash`
- `effective_config_hash`
- `effective_strategy_slice_hash`
- `proxy_universe`
- `fail_closed_on_scoring_fallback`
- `run_id`
- `parent_anchor`
- `timestamp`
- `anchor_effective_config_hash`
- `anchor_effective_strategy_slice_hash`
- `preflight_passed`
- `rejection_reason`
- `execution_status`
- `manifest_path`

## Persistence Points

The same provenance payload is now emitted into:

- `artifacts/search_trials/<trial_id>.json`
- raw backtest report JSON (`report_version=2.2.0`)
- bundle manifest
- compact summary JSON (`summary_version=1.2.0`)

## Hash Semantics

- `overlay_hash`: canonical hash of the requested overlay payload
- `effective_config_hash`: canonical hash of the fully loaded config payload with runtime trial metadata removed
- `effective_strategy_slice_hash`: canonical hash of the target strategy-symbol slice, currently `aurora/ETHUSDT` by default for PKG-7 validation

## Lifecycle Semantics

- `preflight_passed=true`, `execution_status=completed`: trial materialized and completed runtime
- `preflight_passed=true`, `execution_status=runtime_error`: trial materialized but runtime failed later
- `preflight_passed=false`, `execution_status=preflight_rejected`: trial was rejected before runtime

## PKG-7 Invariant

No future bounded-search package may claim that two candidates differ unless the effective hashes or effective changed values prove it.