# LOW_VOL_FLAT_SHORT_WEAK_CONFIDENCE_RESEARCH_PLAN

## Objective

Determine whether the `LOW_VOL + FLAT_LOW + SHORT + pct_b 0.75-0.85 + weak direction_confidence`
segment has a verified net edge, or whether it should remain blocked by the
low-vol cost floor.

This segment must be treated as exploratory until historical and runtime
evidence show positive expectancy after fees, slippage, stale-fill effects, and
partial-fill protection costs.

## Cohort Definition

Include only trade intents or historical replay candidates matching all fields:

- Aurora regime: `LOW_VOLATILITY`.
- Mean-reversion regime: `FLAT_LOW`.
- Proposed side: `SELL` / `SHORT`.
- Bollinger position: `0.75 <= pct_b <= 0.85`.
- Direction confidence below active threshold.
- Low-vol cost floor would otherwise block with
  `direction_confidence_below_threshold`.
- Geometry is available and valid: entry, target, stop, TP fee coverage, and RR
  are all computable.

Exclude rows with missing close attribution, ambiguous symbol/time joins, or
unprotected execution windows unless they are reported in a separate execution
quality appendix.

## Data Sources

- `logs/order_log_v1.jsonl` for runtime intent, placement, fill, and close rows.
- `logs/trade_lifecycle.jsonl` for lifecycle timing and close attribution.
- `logs/mean_reversion/bars_300s.jsonl` for `FLAT_LOW`, `pct_b`, RSI, ATR, and
  Bollinger state at the decision bar.
- `logs/regime_confidence_audit_v1.jsonl` for Aurora regime confidence and
  hysteresis.
- `calibrators/datasets/nrr062_*` artifacts for previous accepted/rejected
  NRR062 cohorts and counterfactual replay.

## Required Joins

Primary runtime join:

- `rid` from Aurora `ORDER_INTENT` to lifecycle close.
- `symbol + nearest 300s bar_close_ts_ms` to MR bar state.
- `symbol + detector_event.bar_close_ts_ms` to regime audit.

Fallback join:

- `symbol + decision_ts_ms +/- 5s` for missing rid propagation.

Every joined row must carry a `join_quality` field: `exact_rid`,
`exact_bar_close`, `nearest_bar`, or `excluded`.

## Metrics

Report by symbol and aggregate:

- trade count;
- gross PnL;
- net PnL;
- expectancy per trade;
- median and mean MAE/MFE;
- win rate;
- max drawdown;
- fee coverage ratio;
- average fill delay;
- stale-fill loss estimate;
- partial-fill unprotected exposure duration;
- TP hit, SL hit, timeout, manual/other close split.

Report by bins:

- `pct_b`: `0.75-0.80`, `0.80-0.85`;
- direction confidence: `0-0.05`, `0.05-0.10`, `0.10-0.25`;
- fill delay: `<60s`, `60-180s`, `>180s`;
- regime confidence: `0.35-0.55`, `0.55-0.75`, `0.75-0.85`.

## Stress Profile

A candidate segment is not capital-ready unless it remains profitable under:

- 2x configured round-trip taker fee;
- 0.5x and 1.0x observed spread slippage per trade;
- conservative taker exit assumption on SL;
- stale fill penalty for fills after 50% of the 300s bar lifetime;
- partial-fill protection cost if brackets were deferred until terminal fill.

## Promotion Gates

The segment can only be considered for runtime enablement if all pass:

- minimum 100 closed trades or a documented lower-sample exception;
- positive net expectancy after stress;
- positive net expectancy in at least 70% of symbols with 10+ samples;
- max drawdown within configured MR/Aurora guardrail;
- no single symbol contributes more than 35% of total net PnL;
- stale-fill cohort remains profitable or is blocked by a freshness guard;
- partial-fill unprotected exposure is eliminated or explicitly priced.

## Kill Gates

Keep the runtime block if any condition holds:

- net expectancy is non-positive after stress;
- win rate does not clear net break-even implied by TP/SL geometry;
- edge exists only before fees/slippage;
- profitability disappears when fill delay exceeds 60 seconds;
- results depend on `nrr062_segment_override_no_production=true`;
- close attribution or lifecycle joins are not trustworthy.

## Implementation Plan

1. Build a read-only extractor for candidate rows from order logs and MR 300s
   bars.
2. Join candidates to lifecycle close rows and classify close reason.
3. Add execution-quality annotations: first fill delay, full fill delay, bracket
   placement delay, partial-fill exposure.
4. Compute gross/net/stress metrics by symbol and bins.
5. Produce markdown and JSON reports under this directory.
6. Only after the report passes promotion gates, propose a bounded runtime rule.

## Current Policy

Until this plan produces a passing report, the segment remains blocked outside
pure testnet diagnostics. Hybrid live-data runtimes must not use the NRR062
segment override to admit weak direction-confidence trades.
