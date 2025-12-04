# RND-NEW-ALPHA-V1: Strategy Proposal

**Date**: 2025-12-03
**Author**: Antigravity (Autonomous Agent)
**Context**: Sniper V1 (5s Momentum) failed to generate alpha across 5 major assets in Jan 2024, primarily due to high transaction costs relative to small price moves and a dominance of "Flat" regimes where momentum signals generated false positives.

## Candidates

### 1. Mean Reversion in Flat Regimes ("Rubber Band")
*   **Idea**: In `FLAT_LOW` or `FLAT_NORMAL` regimes (which constitute ~70-80% of the time), price tends to oscillate within a band. We fade Bollinger Band breakouts or RSI extremes, betting on a return to the mean (EMA/VWAP).
*   **Why**: Directly addresses the "Flat" regime dominance observed in the baseline. Sniper V1 lost money trying to trend-follow in these conditions.
*   **Horizon**: 5s - 1m.
*   **Risks**: Catching a falling knife (breakout turned into a trend). Needs strong regime filters to disable it during `UP/DOWN` trends.

### 2. Higher Timeframe Momentum ("Trend Hunter")
*   **Idea**: Move from 5s bars to 1m or 5m bars. Use similar logic (EMA crossovers, breakouts) but target larger moves (0.5% - 2%) that can easily absorb fees.
*   **Why**: Fixes the "Fee Burn" problem of Sniper V1. Fewer trades, higher average PnL per trade.
*   **Horizon**: 1m - 5m.
*   **Risks**: Lower sample size for statistical significance. Laggy signals in fast crashes.

### 3. Order Flow Imbalance (OFI) Scalping ("Micro-Structure")
*   **Idea**: Use Level 2 data (Depth Imbalance, Trade Flow) to predict immediate 1s-5s price moves. Enter only when order book skew is extreme (>80%).
*   **Why**: Exploits micro-structure inefficiencies rather than macro trends.
*   **Horizon**: 1s - 5s.
*   **Risks**: Extremely latency-sensitive. Simulation often overestimates fill quality (slippage is killer).

## Selected Strategy: **Mean Reversion ("Rubber Band")**

### Justification
1.  **Data-Driven**: The cross-asset baseline showed that assets like ETH and SOL spent the vast majority of time in `FLAT` regimes. Sniper V1 failed because it applied a trend-following logic to a mean-reverting market.
2.  **Complementary**: This strategy perfectly complements the existing Momentum logic. If we can solve the "Flat" market profitability, we can combine it with Momentum (for Trend regimes) in a future ensemble.
3.  **Feasibility**: We already have the infrastructure (Regime Detection) to identify when *not* to trade. We just need to invert the logic: trade *only* when the regime is Flat and price is at an extreme.

### Implementation Plan
*   **Name**: `apps/research/new_alpha_mean_reversion`
*   **Core Logic**:
    *   **Regime**: STRICTLY `FLAT_LOW` or `FLAT_NORMAL`.
    *   **Signal**: Price deviates > X standard deviations (Bollinger) from EMA_Short.
    *   **Entry**: Limit order (maker) or aggressive market (taker) back to mean? (Start with Taker for simplicity, but model fees).
    *   **Exit**: Touch of EMA_Short (Mean) or Stop Loss.
*   **Features**:
    *   Bollinger Bands (Width, %B).
    *   RSI / Stochastic.
    *   Distance from EMA.
