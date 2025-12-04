# Aurora Phase 3: "Full Spectrum" Optimization Proposal

## Executive Summary
Current optimization (Phase 1 & 2) covers approximately **60%** of the Aurora system's logic. We have successfully optimized the core signal generation and basic risk controls. However, critical **execution logic** and **adaptive behaviors** defined in the production configuration are currently hardcoded or missing from the optimization loop.

Phase 3 aims to unlock the remaining **40%** of performance potential by optimizing these "hidden" parameters.

---

## 1. Missing Execution Logic (The "Brain")
The production system (`trading.yaml`) contains sophisticated logic for adapting to market conditions that is currently **ignored** by the backtest engine.

### A. Side-Bias Penalty (Anti-Trend/Anti-Persistency)
**Logic**: Prevents the bot from blindly stacking trades in one direction (e.g., buying the top) by penalizing the signal threshold if the recent trade history is lopsided.
- **Current**: Not implemented in backtest.
- **Proposed**: Implement `SideBiasMonitor` in backtest engine.
- **Parameters to Optimize**:
    - `side_bias_window_sec`: Window to calculate buy/sell ratio (e.g., 60s - 300s).
    - `side_bias_penalty_factor`: How much to increase threshold (e.g., 0.1 - 1.0).

### B. Regime-Adaptive Thresholds
**Logic**: "Be stricter in high volatility, looser in low volatility."
- **Current**: Single `signal_threshold` for all regimes.
- **Proposed**: Implement dynamic threshold multipliers.
- **Parameters to Optimize**:
    - `regime_threshold_high_vol`: Multiplier (e.g., 1.0 - 2.0).
    - `regime_threshold_low_vol`: Multiplier (e.g., 0.5 - 1.0).
    - `regime_threshold_trend`: Multiplier (e.g., 0.8 - 1.2).

### C. Regime-Adaptive Position Sizing
**Logic**: "Bet small in chaos, bet big in calm trends."
- **Current**: Fixed size ($1000).
- **Proposed**: Implement dynamic sizing modifiers.
- **Parameters to Optimize**:
    - `sizing_high_vol`: Multiplier (e.g., 0.1 - 1.0).
    - `sizing_low_vol`: Multiplier (e.g., 1.0 - 2.0).
    - `sizing_mean_rev`: Multiplier (e.g., 0.5 - 1.5).

---

## 2. Unoptimized Feature Parameters (The "Senses")
Several feature engineering parameters are currently using hardcoded defaults.

### A. EMA Bias Normalization
- **Current**: Hardcoded clamp at `[-0.02, 0.02]`.
- **Impact**: Determines sensitivity of the trend filter.
- **Proposed**: Optimize `ema_clamp_min` / `ema_clamp_max`.

### B. Risk Score Composition
- **Current**: Hardcoded weights `{delta: 0.3, volume: 0.4, volatility: 0.3}`.
- **Impact**: Determines what constitutes "high risk".
- **Proposed**: Optimize weights `risk_weight_delta`, `risk_weight_vol`, `risk_weight_volatility`.

### C. Regime Detection Sensitivity
- **Current**: Hardcoded SMA periods (10/50) and ATR thresholds (2.0/0.5).
- **Impact**: Defines *when* the system switches regimes.
- **Proposed**: Optimize:
    - `regime_sma_short` / `regime_sma_long`
    - `regime_high_vol_thresh` / `regime_low_vol_thresh`

---

## 3. Implementation Plan

### Step 1: Upgrade Backtest Engine
- Modify `BacktestEngineAurora` to support:
    - Side-bias state tracking.
    - Dynamic thresholds based on `row['regime']`.
    - Dynamic sizing based on `row['regime']`.

### Step 2: Upgrade Feature Builder
- Expose EMA clamp and Regime parameters in `build_aurora_features`.
- **Note**: Optimizing Regime parameters requires **re-calculating features** inside the Optuna loop (slower) OR pre-calculating a grid of regime variations (faster). *Recommendation: Optimize EMA/Risk weights first, leave Regime detection fixed for now to avoid massive compute overhead.*

### Step 3: Run Phase 3 Optimization
- **Search Space**: ~15 new parameters.
- **Trials**: 2000-3000 per asset.
- **Goal**: Find the optimal "adaptation layer" for the already optimized core signals.

---

## Expected Impact
- **Higher Sharpe Ratio**: By reducing bet sizes in bad regimes (High Vol) and increasing them in good ones.
- **Lower Drawdown**: Side-bias penalty prevents "catching a falling knife" repeatedly.
- **Better Regime Fit**: Adaptive thresholds allow the bot to trade more in safe conditions and less in dangerous ones.
