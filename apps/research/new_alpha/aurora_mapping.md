# Aurora Mapping: Alpha V1 (Mean Reversion)

**Strategy**: Mean Reversion in Flat Regimes
**Status**: R&D Benchmark in Progress

## 1. Integration Concept
This strategy is designed to run *alongside* the existing Momentum strategy.
- **Momentum**: Active in `UP_HIGH`, `DOWN_HIGH`, `UP_NORMAL`, `DOWN_NORMAL`.
- **Mean Reversion**: Active in `FLAT_LOW`, `FLAT_NORMAL`.

## 2. Config Changes

### `features.yaml`
Need to add Bollinger Bands and RSI to the feature engineering pipeline.
```yaml
features:
  - name: bollinger_bands
    params:
      window: [20, 60]
      num_std: 2.0
  - name: rsi
    params:
      window: [14]
```

### `regime.yaml`
No changes needed. We use the existing regime definitions.

### `decision_making.yaml`
We would introduce a new "Strategy Layer" or "Mode Switcher".

```yaml
strategies:
  - name: sniper_momentum
    active_regimes: [UP_HIGH, DOWN_HIGH, UP_NORMAL, DOWN_NORMAL]
    weight: 1.0
  
  - name: alpha_mean_reversion
    active_regimes: [FLAT_LOW, FLAT_NORMAL]
    weight: 1.0
    params:
      entry_std: 2.5
      exit_std: 0.0
      rsi_oversold: 20
      rsi_overbought: 80
```

## 3. Risk Management
Mean Reversion is risky in "Fake Flat" regimes (accumulation before breakout).
- **Stop Loss**: Must be tight (0.5% - 1%).
- **Exposure Guard**: Reduce size if volatility expands suddenly (regime switch from FLAT to HIGH).

## 4. Verdict (Final)
*   **No Alpha**: The strategy failed to generate positive Net PnL on 5s timeframe due to high Taker fees.
*   **Recommendation**: 
    - **DO NOT deploy** this 5s version to production.
    - **Pivot R&D** to 1m timeframe or investigate Maker execution models.
