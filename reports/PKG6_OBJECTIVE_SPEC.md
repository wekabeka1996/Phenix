# PKG6 OBJECTIVE SPEC

Label:

ETH+BTC PROXY / RESEARCH-ONLY / NOT FULL-UNIVERSE

## Objective Philosophy

PKG-6 does not optimize for PnL alone.

The objective is designed to reward:

- risk-adjusted return
- drawdown discipline
- non-trivial but bounded activity
- staying inside the v1-safe profile

And to reject:

- scoring fallback contamination
- non-quadratic observed engine sets
- trivial inactivity
- major drawdown giveback
- reappearance of the toxic ETH TREND_DOWN cluster

## Hard Reject Conditions

A trial is invalid if any of the following is true:

1. `quadratic_fallback_count > 0`
2. observed engine set is not exactly `['quadratic_v1']`
3. `total_trades < 8`
4. `max_drawdown_pct > 10.0`
5. `TREND_DOWN` appears in reconstructed trade regime slices

These are package-level safety gates, not soft preferences.

## Composite Score

For non-rejected trials:

```text
base_score =
    6.0 * sharpe_ratio
  + 0.35 * roi_pct
  - 0.80 * max_drawdown_pct
  - 1.50 * max(0, max_drawdown_pct - 4.0809944658)

activity_term =
    1.0 + 0.25 * (total_trades - 8)          if 8 <= total_trades < 12
    2.0                                      if 12 <= total_trades <= 35
   -0.15 * (total_trades - 35)               if total_trades > 35

concentration_penalty =
    max(0, top_positive_regime_pnl_share - 0.90) / 0.10

objective_score = base_score + activity_term - concentration_penalty
```

## Terms

- `sharpe_ratio`
  - primary reward for risk-adjusted performance.

- `roi_pct`
  - secondary reward for absolute edge.

- `max_drawdown_pct`
  - direct penalty for poor capital preservation.

- `max(0, max_drawdown_pct - 4.0809944658)`
  - explicit v1-anchor drawdown giveback term.
  - `4.0809944658` is the v1 proxy reference DD from run `20260314_172657`.

- `activity_term`
  - rewards non-trivial activity while penalizing high-churn trade counts.
  - this prevents zero-trade winners and discourages baseline-like overtrading.

- `top_positive_regime_pnl_share`
  - mild penalty for one-slice lucky dependence.
  - kept mild because the current v1-safe surface is already concentrated in mean reversion.

## Why This Objective Fits PKG-6

This objective is intentionally conservative.

- It can reward a modest improvement over v1.
- It cannot silently accept fallback contamination.
- It cannot declare a near-zero-trade candidate a winner.
- It strongly resists candidates that recover a little ROI by paying too much drawdown.

## Selection Rule After Search

Search score ranks candidate hypotheses.

Final acceptance still requires manual candidate review against:

- ROI
- max DD
- total trades
- fallback count
- observed engines
- whether v1 safety profile is preserved
- sanity replay behavior in Jan/Feb

So PKG-6 uses the objective as a bounded ranking tool, not as an automatic truth oracle.