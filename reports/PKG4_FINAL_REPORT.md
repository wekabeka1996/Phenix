# PKG4 FINAL REPORT

## Executive Summary

PKG-4 did **not** produce a new honest alpha winner.

What it did produce is the next hard methodological boundary:

- current March scoring path appears quadratic-first in observed logs,
- observed fallback contamination is zero in available March runtime logs,
- but the current constrained-search harness is not strict-config-compatible,
- and the smallest honest runtime proxy still costs enough that a real March search plus Jan/Feb sanity was not honest to fake in this package.

Package verdict:

**Current surface is not blocked by observed scoring fallback contamination, but it is still too narrow and too operationally constrained for an honest bounded alpha search with the current harness.**

## Files Created / Updated

Created:

- `reports/SCORING_INTEGRITY_REPORT.md`
- `reports/CONSTRAINED_SEARCH_SPACE.md`
- `reports/ALPHA_SEARCH_EXPERIMENT_MATRIX.md`
- `reports/OPTUNA_SEARCH_REPORT.md`
- `reports/JAN_FEB_MARCH_SANITY_REPORT.md`
- `reports/PKG4_FINAL_REPORT.md`
- `artifacts/optuna_trials.csv`
- `artifacts/top_candidates.json`

Updated:

- `JOURNAL.md`
- `TODO.md`

## Commands Executed

- `git rev-parse HEAD`
- `Get-FileHash config/aurora/strategies.yaml -Algorithm SHA256`
- `Get-FileHash config/aurora/strategies/aurora.yaml -Algorithm SHA256`
- `Get-FileHash scripts/diagnostics/run_single_backtest.py -Algorithm SHA256`
- log scans for `QUADRATIC_FALLBACK`, `FALLBACK ALSO FAILED`, `KERNEL_DIAG: engine=`
- ETH-only benchmark via direct runtime invocation
- ETH+BTC proxy benchmark via direct runtime invocation

## Tests Run

- No new PKG-4 code tests were added or run.
- Existing earlier focused test still remains green in session history: `tests/scripts/test_run_single_backtest_overlay.py`.

## Runs Executed

- Full-surface March baseline reference already available: `20260314_041537`
- Full-surface March v1 reference already available: `20260314_041758`
- ETH-only proxy benchmark: `20260314_125415` → invalid zero-trade proxy
- ETH+BTC proxy benchmark: `20260314_125711` → valid but still expensive proxy

## Top Findings

1. `QuadraticScoringKernel` is active on the observed March log path and emits `engine=quadratic_v1` in sampled diagnostics.
2. The fail-open fallback path is real in code, but zero observed fallback events were found in the available March runtime logs.
3. The existing `SelectiveOptimizer` path is currently incompatible with strict config truth because it overlays `trading.symbols_to_track`.
4. ETH-only search is invalid because removing BTC anchor context collapses readiness and produces zero-trade triviality.
5. ETH+BTC is the smallest honest proxy discovered, but it still costs about `1405s` per March run.

## Rejected Hypotheses

- Rejected: “March search is blocked mainly by observed scoring fallback contamination.”
  - Observed fallback count in available logs is zero.

- Rejected: “ETH-only proxy is a safe cheap search surface.”
  - It collapses into zero trades and violates package anti-triviality rules.

- Rejected: “Existing SelectiveOptimizer can be reused unchanged.”
  - It conflicts with current strict config contract on `trading.symbols_to_track`.

## Fallback Contamination Status

- Code path exists: yes
- Observed in available March logs: no
- Artifact-level persisted counter: no
- PKG-4 status: zero observed contamination, but not artifact-hardened

## Winner Or Rejection

Package outcome: **rejection**.

No new scoring-first or mixed alpha winner is accepted from PKG-4.

Current best evidence-bound reference remains:

- `march_candidate_v1_block_eth_trend_down`
- reference March run: `20260314_041758`

## Remaining Blockers

1. Search harness needs a strict-config-compatible way to define the research proxy universe without illegal overlay of `trading.symbols_to_track`.
2. Backtest run bundles need scoring fallback telemetry if larger search packages are to be trusted.
3. Full Phase 4 + Phase 5 runtime cost remains high even on the smallest honest proxy.

## Recommendation For Next Package

Next package should be:

**PKG-5 — RESEARCH HARNESS HARDENING FOR ETH+BTC PROXY SEARCH**

Required goals:

1. Add artifact-visible quadratic fallback counters or fail-closed research mode.
2. Add a strict-config-compatible constrained proxy runner for ETH trading + BTC anchor tracking.
3. Run a genuinely bounded scoring-first vs mixed search on that proxy.
4. Only then perform Jan/Feb/March sanity replay for the resulting top candidates.