# OPTUNA SEARCH REPORT

## Status

PKG-4 bounded Optuna search was **not executed to completion**.

This is an explicit rejection, not an omission.

## Why Search Was Rejected

### 1. Existing research Optuna path is not repo-truth-compatible

The existing `SelectiveOptimizer` path attempts to inject `trading.symbols_to_track` through overlay.

Current repo truth:

- `ConfigLoader` enforces `trading.symbols_to_track` as derived SSOT data.
- overlaying that field currently trips a strict contract violation.

Observed consequence:

- off-the-shelf `SelectiveOptimizer` is not currently safe for PKG-4 execution without a harness adjustment.

### 2. ETH-only proxy is invalid

Measured benchmark:

- ETH-only March proxy runtime: about `126s`
- result: `0 trades`

Cause:

- macro-resid / warmup readiness collapses when BTC anchor context is removed.

This would create exactly the kind of fake alpha / zero-trade triviality that PKG-4 bans.

### 3. Smallest honest proxy is still expensive

Measured benchmark using direct runtime mutation after config load:

- BTC tracked as anchor
- ETH active as trading symbol
- March runtime: about `1405s` per run
- proxy run id: `20260314_125711`

Implication:

- even a very small 4-trial search plus minimum Jan/Feb/March sanity replay would require multiple hours of full backtest compute.

### 4. Bundle artifacts still do not expose fallback counts

Observed fallback contamination in logs was zero.
However:

- bundle artifacts do not persist fallback-count telemetry,
- so larger search would still be less trustworthy than it should be.

## What Was Proven Instead

1. The scoring path is quadratic-first in current March logs.
2. The fallback path exists but was not observed in available March runtime logs.
3. The existing research harness needs a strict-config-compatible proxy runner before honest bounded search.
4. ETH-only search is invalid; BTC anchor context is required even for a narrow ETH research proxy.

## Artifact Outputs

- `artifacts/optuna_trials.csv` was emitted as a package-level placeholder artifact with rejection metadata instead of fake trial results.
- `artifacts/top_candidates.json` was emitted as a rejection artifact describing reference candidates and remaining blockers.

## PKG-4 Decision For Phase 4

Bounded Optuna search is rejected in this package.

Reason class:

- not scoring contamination,
- but search-harness incompatibility + compute-budget realism + zero-trade proxy risk.