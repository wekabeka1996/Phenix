# False Positive Archetypes for Mean Reversion

## Scope

This inventory uses historical MR telemetry from `logs/mean_reversion/bars_300s.jsonl`. It is a signal-pattern study, not a PnL backtest.

## Archetype 1: Low-bandwidth breakout fade

### Definition

- Signal breaches a Bollinger boundary.
- Band width is still low in absolute terms.
- Recent width is expanding.
- The strategy interprets it as fadeable mean reversion instead of breakout ignition.

### Why it matters

This is the cleanest path by which MR turns into "blind fade against expansion."

### Evidence

- DOGE, March 13, 2026:
  - 08:34:59 SHORT, `width=0.00879`, `%B=1.1416`
  - 08:49:59 SHORT, `width=0.01457`, `%B=1.0527`, width expansion ratio `1.66x`
- DOGE, 2026-02-12 06:29:59:
  - SHORT, `width=0.01363`, `%B=1.1833`, `RSI=84.8`
- XRP, 2026-02-21 09:34:59:
  - SHORT, `width=0.01322`, `%B=1.1738`, `RSI=93.1`

### Verdict

- `PROVEN`

## Archetype 2: Repeated same-direction fading during drift trend

### Definition

- The same symbol emits 3 or more same-side MR signals within 30 minutes.
- The price keeps drifting in the adverse direction rather than snapping back quickly.

### Why it matters

Repeated fades are not an edge by themselves. In practice they often show that the model is reading drift-trend continuation as repeated mean-reversion opportunity.

### Evidence

- 75 run-events with run length `>= 3` appear in `bars_300s`.
- DOGE sequences include:
  - 2026-02-12 06:24:59 -> 06:34:59, SHORT run length 4
  - 2026-02-13 03:04:59 -> 03:39:59, SHORT run length 6
  - 2026-03-13 08:34:59 -> 09:44:59, SHORT run length 5

### Verdict

- `PROVEN`

## Archetype 3: Unconfirmed fades because RSI is optional

### Definition

- The signal is admitted on band breach alone.
- RSI does not confirm exhaustion.

### Why it matters

This does not prove RSI should be a hard gate. It does prove that the current contract admits many fades without any exhaustion confirmation at all.

### Evidence

- 96 of 187 historical SHORTs do not contain `rsi_overbought`.
- 139 of 239 historical LONGs do not contain `rsi_oversold`.
- DOGE alone:
  - 60 of 115 SHORTs without RSI confirmation
  - 102 of 158 LONGs without RSI confirmation

### Verdict

- `PROVEN`

## Archetype 4: Flat-low short admission

### Definition

- The raw regime maps to `FLAT_LOW`.
- The strategy still allows SHORT fades above the upper band.

### Why it matters

The March 13 DOGE incident stayed in `FLAT_LOW` for all five shorts. That makes `FLAT_LOW` short handling a first-class candidate family for future tuning.

### Evidence

- Historical `FLAT_LOW` SHORT counts:
  - `DOGEUSDT`: 62
  - `XRPUSDT`: 23
  - `BTCUSDT`: 8
- All 5 March 13 DOGE shorts were `FLAT_LOW`.

### Verdict

- `PROVEN`

## What this does not prove

- That every low-bandwidth fade is bad.
- That RSI must become a hard gate.
- That the best fix is a single global threshold.
- That BTC should share DOGE-specific hardening without further evidence.

