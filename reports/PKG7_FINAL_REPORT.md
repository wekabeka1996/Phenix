# PKG-7 Final Report

## Executive Summary

PKG-7 is complete. The package did not run alpha search. It hardened the search substrate so future bounded search can prove trial distinctness before spending runtime and can preserve evidence even when a study is interrupted.

## Phase 0 Freeze

- working branch during PKG-7 closeout: `backtest_1`
- freeze commit: `cf074c7229252aaca83aed7dc70331115018866d`
- `optimization/research/proxy_runner.py`: `7a81ddfa8fa72f2bf8898cb276a5bbe5b6e9c2b1e31c664736b36b805d7b9986`
- `scripts/diagnostics/run_research_proxy_backtest.py`: `480f725f334c8bcc03a5fe1267afa65facc9a1009a8bd8ed22adabd4a9549289`
- `optimization/backtest_interface.py`: `61a6bdf0666d85108945ef66a5034c053723d89fa93b7dfc114fba043f644c03`
- `artifacts/pkg6_optuna_trials.csv`: `8487ac90cd2c497ead8ba096fca1be29dd05c0b2a10e256cdc589d6be8ecf0aa`
- `artifacts/pkg6_top_candidates.json`: `503a7b71f940ecbfbf10c3b923e846956711f7b315dcf8525b7dad87337d69ef`

Phase-0 note:

- PKG-7 closeout evidence was recorded on the existing repository branch `backtest_1`.
- A dedicated PKG-7 worktree was not created in-session, so the freeze evidence is commit-and-hash based rather than separate-worktree based.

## Exact Root Cause

PKG-6 trial collapse was an artifact/provenance failure:

- overlays changed the effective ETH config in memory;
- the old report hash path did not materialize that ETH slice into artifact-visible evidence;
- distinct requests therefore collapsed to the same reported hash.

PKG-7 fixes that by hashing the effective loaded config and the effective strategy slice, then persisting those results per trial.

## Changes Delivered

- additive runtime provenance contract in config models
- canonical provenance/materialization helpers
- preflight rejection for no-effect trials
- per-trial manifests under `artifacts/search_trials/`
- provenance export in raw report bundles and compact summaries
- focused pytest coverage for the new lifecycle

## Validation Summary

- focused tests: `7 passed`
- anchor validation manifest completed
- scoring-distinct validation manifest completed
- mixed-distinct validation manifest completed
- no-effect validation manifest rejected with `NO_EFFECTIVE_CONFIG_DELTA`

## Validation Commands

Focused tests can be reproduced with:

```powershell
pytest -q tests/optimization/test_research_proxy_runner.py tests/backtest_engine/test_scoring_telemetry_reporting.py
```

Mini validation commands can be reproduced with:

```powershell
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label pkg7_anchor_validation --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-02 --balance 1000 --fail-on-scoring-fallback --trial-id pkg7-anchor --arm-id anchor --trial-params-json {} --expected-paths-json [] --parent-anchor v1 --overlay-yaml artifacts/pkg7_validation/anchor_overlay.yaml
```

```powershell
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label pkg7_scoring_validation --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-02 --balance 1000 --fail-on-scoring-fallback --trial-id pkg7-scoring --arm-id scoring --trial-params-json "{\"macro_resid\": 0.31}" --expected-paths-json "[\"strategies.aurora.assets.ETHUSDT.weights.macro_resid\"]" --parent-anchor v1 --anchor-overlay-yaml artifacts/pkg7_validation/anchor_overlay.yaml --overlay-yaml artifacts/pkg7_validation/scoring_distinct.yaml
```

```powershell
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label pkg7_mixed_validation --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-02 --balance 1000 --fail-on-scoring-fallback --trial-id pkg7-mixed --arm-id mixed --trial-params-json "{\"macro_resid\": 0.31, \"tfi\": 0.14, \"signal_threshold\": 0.0095}" --expected-paths-json "[\"strategies.aurora.assets.ETHUSDT.weights.macro_resid\", \"strategies.aurora.assets.ETHUSDT.weights.tfi\", \"strategies.aurora.assets.ETHUSDT.signal_threshold.value\"]" --parent-anchor v1 --anchor-overlay-yaml artifacts/pkg7_validation/anchor_overlay.yaml --overlay-yaml artifacts/pkg7_validation/mixed_distinct.yaml
```

```powershell
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label pkg7_no_effect_validation --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-02 --balance 1000 --fail-on-scoring-fallback --trial-id pkg7-no-effect --arm-id scoring --trial-params-json "{\"macro_resid\": 0.25}" --expected-paths-json "[\"strategies.aurora.assets.ETHUSDT.weights.macro_resid\"]" --parent-anchor v1 --anchor-overlay-yaml artifacts/pkg7_validation/anchor_overlay.yaml --overlay-yaml artifacts/pkg7_validation/anchor_overlay.yaml
```

## Remaining Risks

- shell/terminal ergonomics remain noisy because `vfoundation.config` emits environment warnings that the PowerShell wrapper surfaces aggressively;
- this is an operational nuisance, not a PKG-7 provenance blocker.
- package-closeout evidence is strong at the commit/hash level, but not at the separate-worktree level.

## Recommendation

Proceed to PKG-8 only if bounded search uses the PKG-7 provenance path as mandatory infrastructure:

1. every trial gets a stable `trial_id`
2. every trial writes a manifest before runtime
3. no candidate is considered distinct unless effective hashes or effective changed values prove it
4. interrupted searches resume from manifests instead of console output