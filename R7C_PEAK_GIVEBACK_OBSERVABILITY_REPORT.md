# R7C Peak-Giveback Observability Report

## Problem

R7B did not prove peak-giveback trigger correctness because the observed runtime rows did not carry the full economic inputs, did not expose loaded `peak_giveback_close` config at startup, and did not emit stable searchable markers for the arm / below-trigger / threshold-met states.

R7C closes that observability gap only. No business thresholds, close routing, action scope, or sidecar policy families were changed.

## FACTS

- `EVT:POSITION_POLICY_SIDECAR_MODE_ACTIVE` now carries `sidecar_config_snapshot` with the loaded `peak_giveback_close` values and freshness limits.
- `EVT:POSITION_POLICY_SIDECAR_EVALUATED`, `EVT:POSITION_POLICY_SIDECAR_SCORES`, `EVT:POSITION_POLICY_SIDECAR_SUPPRESSED`, `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED`, and `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` now carry `peak_giveback_snapshot`.
- `peak_giveback_snapshot` includes runtime economics, current peak state, threshold inputs, and explicit `null_reasons` when economics are unavailable.
- Peak-giveback markers are now preserved in top-level `reason_codes` instead of being overwritten by later emit steps.
- Peak-giveback recommendations now expose `policy_source=position_policy_sidecar:peak_giveback` on the recommendation row as well as on the close request.
- Peak-giveback trigger score snapshots now include `current_edge_usd` and `giveback_trigger_pct` in addition to `peak_edge_usd` and `giveback_pct`.
- JSON schemas were extended additively to describe `sidecar_config_snapshot`, `peak_giveback_snapshot`, and recommendation `policy_source`.

## INFERENCES

- The next runtime slice can distinguish safe quiet rows from non-proof rows because suppressed or unevaluable rows now emit explicit peak-giveback state markers and explicit null reasons.
- The next runtime slice can answer whether the runtime loaded the intended `peak_giveback_close` config from the bootstrap row alone, without reconstructing config from source code.
- The next runtime slice can answer whether a position never armed, armed but stayed below trigger, or crossed threshold, using only sidecar runtime rows.

## ASSUMPTIONS

- Existing operator queries and forensic workflows can consume additive JSON fields without requiring code changes.
- `source_config_path` may remain `null` unless the config loader attaches a source-path attribute to the typed config object.
- `unrealized_pnl_usdt` remains the runtime truth source for the current edge; R7C did not change the economic calculation authority.

## UNKNOWNS

- No live or shadow runtime slice was produced in this package, so real-market examples of each new state marker are still pending.
- Downstream tooling may later want higher-level summaries of peak-giveback transitions, but R7C intentionally stopped at payload-level observability.
- If future operator workflows require a non-null config source path, the loader may need a follow-up additive metadata hook.

## Fields Added

- `sidecar_config_snapshot.mode`
- `sidecar_config_snapshot.peak_giveback_close.enabled`
- `sidecar_config_snapshot.peak_giveback_close.edge_arm_usd`
- `sidecar_config_snapshot.peak_giveback_close.giveback_trigger_pct`
- `sidecar_config_snapshot.freshness.portfolio_max_age_ms`
- `sidecar_config_snapshot.freshness.features_max_age_ms`
- `sidecar_config_snapshot.freshness.regime_max_age_ms`
- `sidecar_config_snapshot.freshness.order_state_max_age_ms`
- `sidecar_config_snapshot.source_config_path`
- `peak_giveback_snapshot.policy_enabled`
- `peak_giveback_snapshot.mark_price`
- `peak_giveback_snapshot.entry_price`
- `peak_giveback_snapshot.position_qty`
- `peak_giveback_snapshot.side`
- `peak_giveback_snapshot.unrealized_pnl_usdt`
- `peak_giveback_snapshot.unrealized_pnl_pct`
- `peak_giveback_snapshot.peak_edge_usd`
- `peak_giveback_snapshot.current_edge_usd`
- `peak_giveback_snapshot.giveback_pct`
- `peak_giveback_snapshot.is_armed`
- `peak_giveback_snapshot.arm_threshold_usd`
- `peak_giveback_snapshot.giveback_trigger_pct`
- `peak_giveback_snapshot.threshold_crossed`
- `peak_giveback_snapshot.peak_giveback_state`
- `peak_giveback_snapshot.reason_codes`
- `peak_giveback_snapshot.null_reasons`
- `policy_source` on `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED`
- `score_snapshot.current_edge_usd` on peak-giveback trigger recommendations/requests
- `score_snapshot.giveback_trigger_pct` on peak-giveback trigger recommendations/requests

## Schemas Changed

- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_mode_active_v1.json`
- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_evaluated_v1.json`
- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_scores_v1.json`
- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_suppressed_v1.json`
- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_recommended_v1.json`
- `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json`

## Validation Evidence

- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py -q`
  - Result: `3 passed`
  - Purpose: no business-behavior drift after the first sidecar edit.
- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/domains/execution_position/test_position_policy_sidecar.py::test_position_policy_sidecar_recommends_and_emits_bounded_close_request_in_enable_mode tests/domains/execution_position/test_position_policy_sidecar.py::test_execpos_position_policy_sidecar_mode_wiring_and_ordering tests/contracts/test_position_policy_sidecar_contracts.py -q`
  - Result: `14 passed`
  - Purpose: runtime observability fields, startup config snapshot, and schema alignment.
- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/tools/test_position_policy_sidecar_validation.py -q`
  - Result: `13 passed`
  - Purpose: richer sidecar rows remain compatible with the existing forensic validator.

## Residual Risks

- Runtime proof still depends on collecting a fresh slice that actually exercises both quiet and threshold-crossing paths.
- `peak_giveback_not_ready` is intentionally coarse for non-stale, non-close-in-progress suppressions; if operators later need a stricter taxonomy, that should be a separate package.
- `source_config_path` is present by contract but may be `null` until loader metadata is available.
