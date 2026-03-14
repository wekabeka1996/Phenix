# P1 Mean Reversion Logic Review Summary

## Verdict

- `PROVEN`: current MR is a 5m Bollinger/%B fade strategy with RSI as a confidence bonus, not a momentum-aware mean reversion model.
- `PROVEN`: current live MR scope is DOGE-only.
- `PROVEN`: current MR has no explicit squeeze-expansion, trend, slope, or momentum veto in the core signal path.
- `PROVEN`: strategy-level directional sanity and price-motion sanity are disabled for MR.
- `PROVEN`: the March 13, 2026 DOGE incident was strategy-valid under current code and config, before execution failures compounded it.
- `PROVEN`: historical `bars_300s` shows repeated same-direction fade runs and many flat-low shorts, so the issue is a class, not a single trade.

## Most Important Numbers

- Historical actionable MR signals in `bars_300s`: 426
- By symbol:
  - `DOGEUSDT`: 273
  - `XRPUSDT`: 129
  - `BTCUSDT`: 24
- By regime:
  - `FLAT_LOW`: 204
  - `FLAT_NORMAL`: 167
  - `FLAT_HIGH`: 55
- Signals without RSI confirmation:
  - SHORT: 96 of 187
  - LONG: 139 of 239

## March 13 DOGE Incident Through Strategy Lens

Five DOGE SHORT signals fired between 08:34:59 UTC and 09:44:59 UTC on March 13, 2026 while the strategy still treated the market as `FLAT_LOW`. Width expanded from `0.00879` to `0.03111`, `%B` stayed above the upper band, and the regime detector only flipped to `TREND_UP` after the sequence.

That is not an execution-only story. It is evidence that current MR can admit breakout fades under low-volatility labeling.

## Best Candidate Families For The Next Package

1. DOGE/high-beta-specific width and regime hardening.
2. Additive squeeze-expansion veto.
3. Momentum/slope/drift veto for counter-trend fades.
4. Contract cleanup for 5m naming and `allowed_regimes` semantics.

## What Not To Do Next

- Do not treat global `min_bb_width >= 0.015` as already proven final policy.
- Do not treat cooldown tuning as the main answer.
- Do not mix execution fixes into the next MR package.

