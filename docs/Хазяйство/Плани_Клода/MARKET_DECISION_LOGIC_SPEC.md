# Market Analysis & Decision Logic — v1 (Testnet‑Optimized)
Date: 2025-11-02

Objective
- Define the full decision pipeline from live features → alpha models → ensemble → risk gating → position sizing → trade intent.
- Optimize risk policy for testnet: slightly less conservative gating to accelerate discovery, while retaining guardrails.

1) Live Features → Feature Store
- Source: EVT:FEATURES_CALCULATED (market_data → feature_engineering) carries normalized features e.g., price, delta_price, OBI, TFI, ATR, volatility.
- Store: apps/reference/data/feature_store.py persists 5m features and maintains multi‑TF tables (5m/15m/1h/4h) for backtests and future multi‑TF aggregation.
- Action: ensure live collector aggregates 15m/1h/4h from 5m via rolling window with overlap-safe grouping (P2).

2) Alpha Models (Pluggable)
- Interface: apps/reference/domains/alpha_search/alpha_model.py exposes `on_features()` → score ∈ [−1, +1], with metadata.
- Baselines:
  - Momentum: sign(price ROC) with bandpass; bullish if price > SMA and ROC > τ.
  - Mean Reversion: z‑score(price − SMAk); contrarian entries near ±2σ, avoid trend regimes.
  - Volatility Regime: ATR/volatility filter; avoid low‑quality entries in volatility collapse.
- Emission (already present): EVT:ALPHA_SCORE_CALCULATED with list of model scores.

3) Ensemble Aggregation
- Weighted sum of normalized model scores with regime‑aware weights:
  - Example: `alpha_ens = w_mom*α_mom + w_mr*α_mr + w_vol*α_vol` with Σw=1.
  - Regime filter: If `regime ∈ {TREND_UP, TREND_DOWN}`, up‑weight momentum; if `MEAN_REVERSION`, up‑weight MR; if `HIGH_VOLATILITY`, apply volatility penalty to position size rather than decision.
- Decision threshold:
  - Dynamic τ based on recent hit‑rate (shadow backtester over last N trades) and spread/vol: `τ = τ0 + κ·spread_bps + λ·vol_zscore`.
  - Testnet policy: set τ0 lower (e.g., 0.15) to increase exploration; production τ0 ≥ 0.25.

4) Risk Gating (Testnet‑Optimized)
- Inputs (implemented): leverage ratio, volatility factor, diversification proxy, drawdown recovery (apps/reference/domains/risk_management/risk_management.py).
- Testnet policy adjustments:
  - Clamp risk_score ∈ [0.05, 0.97] (slightly broader).
  - Max risk_score threshold (gating) set higher in testnet, e.g., `max_risk_score = 0.9` (prod default 0.8).
  - ExposureGuard limits remain in force, but allow higher notional cap (via config) for exploration.
- Acceptance: Even in testnet, exposure hard gate prevents runaway leverage; WAL audit preserves all decisions.

5) Position Sizing (Kelly‑tuned for testnet)
- Inputs: calibrated p (probability), EV, risk budget (CVaR budget), equity.
- Sizing logic:
  - Compute full Kelly fraction `f* = p − (1 − p)/R` (R = payoff ratio), then apply testnet boost factor β_testnet ∈ [1.0, 1.5] bounded by CVaR budget and exposure.
  - `kelly_used = min(β_testnet·f*, kelly_ceiling)` where kelly_ceiling depends on regime (e.g., 0.2 trend, 0.1 MR, 0.15 high vol).
  - Final notional: `size_usd = equity * kelly_used`, bounded by min/max position rules and liquidity caps.
- Justification: Encourages exploration on testnet while keeping drawdown‑aware constraints.

6) Decision Policy (Pseudo‑flow)
```
on EVT:FEATURES_CALCULATED(symbol, feats):
  α = AlphaRegistry.calculate_all(feats)
  emit EVT:ALPHA_SCORE_CALCULATED(α)

  α_ens = Ensemble.aggregate(α, regime)
  τ = dynamic_threshold(spread, vol, recent_hit_rate, mode)
  if |α_ens| < τ: reject("NEUTRAL_SIGNAL")

  risk = Risk.evaluate(portfolio, feats, regime)  # dynamic score ∈ [0,1]
  if risk.score > risk.max_allowed: reject("RISK_DISALLOWED")

  side = sign(α_ens)
  f* = kelly(p, R)
  k_used = clamp(β(mode) * f*, regime_ceiling)
  size = clamp(equity * k_used, min_pos_usd, liq_cap)
  intent = build_intent(symbol, side, size, why_chain=[...])
  emit EVT:TRADE_INTENT_PROPOSED(intent)
```

7) Explainability (WHY Chain)
- Each component appends a compact explanation (≤ 80 chars) to WHY/data_ref:
  - α: `alpha: mom=0.32 mr=−0.10 vol=0.05 ens=0.23 τ=0.15`
  - risk: `risk: score=0.42 max=0.90 regime=TREND_UP`
  - sizing: `size: kelly=0.12 boost=1.2 used=0.14 notional=$1234`
  - decision: `decision: BUY score=0.23 ok`
- `/debug/{rid}` returns full chain reconstructed from WAL, enabling review.

8) Testnet vs Production Modes
- Mode switch via config/env:
  - testnet: lower τ0, higher max_risk_score, β_testnet > 1, relaxed min position.
  - production: stricter thresholds, β=1, lower kelly ceiling.
- Both modes retain hard exposure limits and WAL/XAI invariants.

9) Acceptance & KPIs
- Shadow hit‑rate computed over last N decisions; dynamic τ responds accordingly.
- SLO: p95 decision path < 50ms.
- Backtester validates α models/weights on last 90–180 days; drift monitored by Debug API aggregates.

10) Implementation Notes
- EVT:ALPHA_SCORE_CALCULATED is emitted (verified in decision_making.py:382+), ensure WAL capture.
- Ensemble weights can be optimized offline (backtester) and periodically updated.
- Testnet configuration templates should live in config/aurora/trading.yaml with explicit mode flags.

