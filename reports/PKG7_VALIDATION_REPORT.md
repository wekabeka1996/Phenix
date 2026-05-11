# PKG-7 Validation Report

## Focused Tests

Focused pytest validation completed green:

- `tests/optimization/test_research_proxy_runner.py`
- `tests/backtest_engine/test_scoring_telemetry_reporting.py`

Result:

- `7 passed`

Repro command:

```powershell
pytest -q tests/optimization/test_research_proxy_runner.py tests/backtest_engine/test_scoring_telemetry_reporting.py
```

Covered behaviors:

- distinct overlays produce distinct effective hashes
- no-effect trials reject preflight
- provenance is exported into raw report and summary artifacts
- completed manifests survive partial/resumed study progression

## Mini Validation Trials

Validation window:

- `2024-03-01 -> 2024-03-02`
- proxy universe: `ETHUSDT` tradable, `BTCUSDT` context
- fail-closed fallback rejection: enabled

Repro command pattern:

```powershell
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label <label> --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-02 --balance 1000 --fail-on-scoring-fallback --trial-id <trial_id> --arm-id <arm_id> --trial-params-json <json> --expected-paths-json <json> --parent-anchor v1 --anchor-overlay-yaml artifacts/pkg7_validation/anchor_overlay.yaml --overlay-yaml <overlay>
```

### Anchor

- manifest: `artifacts/search_trials/pkg7-anchor.json`
- run_id: `20260315_034241`
- `effective_config_hash`: `527b9881cb2c771ee20b827e84061be436cc6d640de34f8057538393e7bfd189`
- `effective_strategy_slice_hash`: `0e5c8c0bae724e1fd3f4000f89c1a6d577ac9def30b26fc0b70f534cea7aba81`
- status: `completed`

### Scoring-Distinct

- manifest: `artifacts/search_trials/pkg7-scoring.json`
- run_id: `20260315_034313`
- requested delta: `macro_resid=0.31`
- `effective_changed_values.strategies.aurora.assets.ETHUSDT.weights.macro_resid = 0.31`
- `effective_config_hash`: `f2a76270071db527f4836185ffb68ea90edcfa99795953393b8bbaef0a54067e`
- `effective_strategy_slice_hash`: `ff17634d1fc6988eb534742352156e2aeb3a452af9e19b2bf59db6de753303d9`
- anchor strategy-slice hash seen by preflight: `0e5c8c0bae724e1fd3f4000f89c1a6d577ac9def30b26fc0b70f534cea7aba81`
- status: `completed`

### Mixed-Distinct

- manifest: `artifacts/search_trials/pkg7-mixed.json`
- run_id: `20260315_034335`
- requested deltas: `macro_resid=0.31`, `tfi=0.14`, `signal_threshold=0.0095`
- effective values proved all three requested paths
- `effective_config_hash`: `d55edbf9610da296e9c7117fd5bfb41c63ac6ff0132cd29e7636e45056a9c98d`
- `effective_strategy_slice_hash`: `c77a5827900888ed96ad95a3b8408b009cc99de5509de6d1ea77bc5c951b7499`
- anchor strategy-slice hash seen by preflight: `0e5c8c0bae724e1fd3f4000f89c1a6d577ac9def30b26fc0b70f534cea7aba81`
- status: `completed`

### No-Effect Reject

- manifest: `artifacts/search_trials/pkg7-no-effect.json`
- requested delta: `macro_resid=0.25`
- `effective_changed_values.strategies.aurora.assets.ETHUSDT.weights.macro_resid = 0.25`
- `effective_strategy_slice_hash` matched the anchor hash
- rejection: `NO_EFFECTIVE_CONFIG_DELTA`
- status: `preflight_rejected`

## Validation Outcome

PKG-7 validation succeeded on the intended contract:

- distinct requested trials produced distinct effective hashes and persisted manifests;
- a no-op requested trial was rejected before runtime;
- artifact persistence now exists independently of long search completion.

## Phase 0 Context

- branch at closeout: `backtest_1`
- freeze commit: `cf074c7229252aaca83aed7dc70331115018866d`
- dedicated worktree isolation was not used during this session; closeout evidence is therefore recorded via commit SHA and file hashes instead.

## Operational Note

The VS Code PowerShell wrapper surfaced several environment warnings from `vfoundation.config` as terminal-level failures. This affected shell exit-code ergonomics during validation, but did not invalidate the manifests or focused tests recorded above.