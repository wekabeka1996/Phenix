# Mean Reversion Filter Candidate Matrix

## Method

This matrix is based on:

1. code review of the live MR contract
2. historical signal replay from `logs/mean_reversion/bars_300s.jsonl`
3. March 13, 2026 DOGE incident coverage

It is not a realized-PnL backtest.

## Lightweight Replay Table

| Candidate | Historical kept | Historical blocked | March 13 DOGE shorts blocked | Initial read |
|---|---:|---:|---:|---|
| Baseline current logic | 426 | 0 | 0 | Current live behavior |
| Global width floor `0.015` | 108 | 318 | 2 of 5 | Very blunt |
| DOGE-only width floor `0.015` | 202 | 224 | 2 of 5 | Stronger than global |
| Hard RSI confirmation | 191 | 235 | 1 of 5 | Weak alone |
| Squeeze-expansion veto | 417 | 9 | 1 of 5 | Surgical, narrow |
| Block `FLAT_LOW` SHORTs | 333 | 93 | 5 of 5 | Strong candidate |
| Naive 3-bar momentum veto | 135 | 291 | 2 of 5 | Too destructive as-is |

## Family-by-Family Analysis

| Family | What it blocks | What it risks killing | Confidence | Recommendation |
|---|---|---|---|---|
| `min_bb_width` tightening | Narrow-band fades and some breakout-fade setups | A lot of otherwise valid low-width trades, especially if global | HIGH | Use only as symbol- or group-specific candidate |
| Squeeze-expansion veto | Low-band expansion fades with extreme `%B` and width growth | Very little, if implemented narrowly | MEDIUM-HIGH | Strong additive candidate |
| Short/long momentum veto | Counter-trend fades during drift or ignition | Can kill too much if naive | MEDIUM | Research-backed family, but needs careful implementation design |
| Slope/trend veto | Fades against local directional persistence | Could duplicate regime detector if poorly designed | MEDIUM | Good candidate if built from local bar drift, not from a second generic trend stack |
| RSI hardening / regime-conditioned RSI | Fades without exhaustion confirmation | Many baseline signals; may still miss key toxic setups | MEDIUM-LOW | Secondary candidate, not first package |
| Regime-specific thresholds | Toxic fades concentrated in `FLAT_LOW` or selected regimes | Could overblock if regime map lags reality | HIGH | Strong candidate family |
| Symbol-specific thresholds | DOGE/high-beta-specific hardening | More config complexity | HIGH | Strong candidate family |
| Multi-bar confirmation before fade | Single-bar false positives | Added lag; may miss genuine snapbacks | MEDIUM | Candidate only after better replay |
| Cooldown / exhaustion gating | Repeated same-side churn | Does not stop the first bad entry | HIGH | Secondary only |
| ATR-relative expansion veto | Expansion bars that outrun recent ATR context | Needs richer feature replay to calibrate | MEDIUM-LOW | Keep as research follow-up, not first package |

## Detailed Notes

### 1. Global `min_bb_width` tightening

- Thesis: current DOGE floor `0.005` is permissive enough to admit squeeze-breakout fades.
- Replay result: global `0.015` blocks 318 of 426 signals and only catches the first two March 13 DOGE shorts.
- Conclusion: `PROVEN` to be blunt. Not good enough as a universal first fix.

### 2. DOGE-only / high-beta width hardening

- Thesis: a symbol-specific width floor can target high-beta assets without gutting the whole MR family.
- Replay result: DOGE-only `0.015` blocks 224 of 426 signals, catches the same two early March 13 shorts, and leaves BTC/XRP untouched.
- Conclusion: `LIKELY` stronger than a universal width floor.

### 3. Squeeze-expansion veto

- Thesis: block fades when width is still low but expanding sharply into an extreme band breach.
- Replay proxy: width `< 0.015`, recent width expansion `>= 1.4x`, and extreme `%B`.
- Replay result: blocks only 9 of 426 historical signals.
- Limitation: blocks the second March 13 DOGE short, not the first.
- Conclusion: `LIKELY` good additive family, not a standalone answer.

### 4. Momentum / slope veto

- Thesis: block fades when the last bars keep moving in the adverse direction.
- Replay proxy: monotonic 3-bar drift.
- Replay result: blocks 291 of 426 signals.
- Conclusion: the family is `LIKELY` useful, but the naive form is too destructive.

### 5. Hard RSI confirmation

- Thesis: require exhaustion confirmation before fade.
- Replay result: blocks 235 of 426 signals and only blocks 1 of the 5 March 13 DOGE shorts.
- Conclusion: `POSSIBLE`, but weak as a first package.

### 6. Regime-specific short veto in `FLAT_LOW`

- Thesis: low-volatility short fading is the most toxic current regime family.
- Replay result: blocks 93 of 426 signals and all 5 March 13 DOGE shorts.
- Conclusion: `LIKELY` one of the best next package candidates.

### 7. Symbol grouping

- Thesis: majors, mid-beta, and high-beta meme/alt names should not share one MR floor.
- Evidence:
  - DOGE actionable median width `0.00960`
  - XRP actionable median width `0.01321`
  - BTC actionable median width `0.01083`, but with tiny sample
- Conclusion: `LIKELY` worth building before universal threshold claims.

## Decision

Most promising first implementation families:

1. symbol-specific / high-beta width and regime hardening
2. `FLAT_LOW` short hardening
3. squeeze-expansion veto
4. carefully designed momentum-separation veto

Least promising first moves:

1. global width floor as a universal answer
2. cooldown-first tuning
3. RSI-only hardening as the main fix

