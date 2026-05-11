# MINIMAL BACKTEST STRATEGY SPEC

## Candidate

- Candidate ID: `march_candidate_v1_block_eth_trend_down`
- Objective: remove the dominant March repeated loss engine with the smallest existing control surface.
- Scope label: MARCH / SIDE B / DEGRADED PARTIAL-UNIVERSE.

## Selected Rule Package

Single active rule:

- Remove `TREND_DOWN` from `strategies.aurora.assets.ETHUSDT.allowed_regimes` for the March research candidate.

Explicit non-changes:

- Keep `ETHUSDT / MEAN_REVERSION` unchanged.
- Keep BNB behavior unchanged.
- Do not retune TP/SL, thresholds, holding period, or reentry cooldown in v1.
- Do not add a new entry-phase / green-bounce gate in v1.

## Implementation Surface

- Candidate overlay file: `config/overlays/march_candidate_v1_block_eth_trend_down.yaml`
- Launcher support added: `scripts/diagnostics/run_single_backtest.py --overlay-yaml ...`
- Backtest-only application path: existing `ConfigLoader(..., optuna_overlay=overlay)` hook.

This keeps canonical SSOT config intact while allowing a reproducible research delta.

## Overlay Definition

```yaml
overlay:
  strategies:
    aurora:
      assets:
        ETHUSDT:
          allowed_regimes:
            - FLAT_LOW
            - FLAT_NORMAL
            - MEAN_REVERSION
```

## Why Config-Only Won Over Code v1

- Current March anchor evidence is strong enough to justify blocking the whole ETH TREND_DOWN slice on this degraded research surface.
- Current March anchor evidence is not rich enough to justify a narrower code gate with confidence because the order-log artifact and per-trade entry-phase fields are missing.
- The runtime already exposes `allowed_regimes`; no new business-logic path is required for v1.

## Validation Plan

1. Validate launcher overlay parsing with focused pytest.
2. Run March side B baseline with current SSOT config.
3. Run the same March window with the candidate overlay.
4. Compare headline metrics and trade-slice composition from run bundles.

## Validation Results

- Focused test: `tests/scripts/test_run_single_backtest_overlay.py` passed `3/3`.
- Baseline run: `20260314_041537`.
- Candidate run: `20260314_041758`.

## Risks

- High overfit risk outside March 2024.
- Opportunity cost risk: the blocked regime may carry value in Jan-Feb or in a fully covered universe.
- This is not a causal proof that all ETH TREND_DOWN logic is wrong; only that the current March degraded surface prices it as strongly negative.

## Exit Criteria For v2

Advance beyond v1 only if one of the following becomes available:

1. The missing March order-log artifact is recovered, allowing entry-shape evidence.
2. A minimal code gate is implemented and justified by recovered trade-level entry context.
3. Q2 processed coverage is restored so the regime block can be tested outside the March-only degraded surface.