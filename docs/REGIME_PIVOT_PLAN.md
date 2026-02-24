# REGIME_PIVOT_PLAN.md
## Neocortex PPO -> Regime Oracle: Technical Implementation Blueprint

**Status:** DRAFT - Pending Review
**Date:** 2026-02-20
**Scope:** Switch Neocortex PPO from PnL-based trader to self-supervised Regime Predictor

---

## 1. Current Aurora Regimes (Baseline)

### 1.1 Defined Regimes

| # | Regime | Source Model | Mathematical Trigger |
|---|--------|-------------|---------------------|
| 0 | `TREND_UP` | `sma_trend_v1` | `SMA(5) > SMA(15)` AND `price > SMA(5)` |
| 1 | `TREND_DOWN` | `sma_trend_v1` | `SMA(5) < SMA(15)` AND `price < SMA(5)` |
| 2 | `MEAN_REVERSION` | `mean_reversion_v2` | `\|SMA_short - SMA_long\| / SMA_long < 0.005` AND `\|price - SMA_short\| / SMA_short < 0.005` AND `\|price - SMA_long\| / SMA_long < 0.005` |
| 3 | `HIGH_VOLATILITY` | `volatility_v2` | `ATR(14) / SMA(ATR, 32) > 1.3` |
| 4 | `LOW_VOLATILITY` | `volatility_v2` | `ATR(14) / SMA(ATR, 32) < 0.9` |
| 5 | `UNCERTAIN` | fallback | Confidence < `uncertain_cutoff` (0.52) OR no model claims regime |

**Secondary (Derived):** `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH` - mapped from MEAN_REVERSION + ATR% thresholds (used by MR strategy only).

### 1.2 Detection Cascade (Priority Order)

```
1. Volatility Model (highest priority)
   ├── vol_ratio = ATR / ATR_baseline
   ├── if vol_ratio > 1.3 → HIGH_VOLATILITY (conf = 0.40 + excess × 2.0)
   ├── if vol_ratio < 0.9 → LOW_VOLATILITY  (conf = 0.40 + calm × 3.0)
   └── Slope Gate: if HIGH_VOL detected but vol slope ≤ -0.0035 for 3 bars → demote ("dying storm")

2. Mean Reversion Model (if still UNCERTAIN)
   ├── sma_spread, dev_short, dev_long all < 0.005
   └── conf = 0.40 + (0.005 - max_spread) × 100.0

3. SMA Trend Model (lowest priority, if still UNCERTAIN)
   ├── spread_ratio = (SMA_short - SMA_long) / SMA_long
   ├── conf = |spread_ratio| × 35.0
   └── Direction: SMA_short > SMA_long + price > SMA_short → UP (vice versa)

4. Confidence Gate
   └── Any regime with confidence < 0.52 → demoted to UNCERTAIN

5. Hysteresis Filter
   └── New regime must persist 4 bars before becoming "stable"
```

### 1.3 How Regimes Drive Aurora

| Decision Point | Regime Influence |
|---------------|-----------------|
| **Signal threshold** | `base_threshold × regime_threshold_multiplier[regime]` |
| **Position sizing** | `base_qty × regime_sizing[regime]` (e.g., 0.7x in HIGH_VOL) |
| **Stop-loss** | `sl_pct × sl_mult[regime]` (e.g., 1.3x in HIGH_VOL) |
| **Take-profit** | `tp_pct × tp_mult[regime]` (e.g., 3.5x in TREND for BTC) |
| **Entry price** | Smart Limit: `vol_pullback × regime_multiplier[regime]` |
| **Trade gating** | `allowed_regimes` allowlist per symbol |

### 1.4 Key Limitation

Aurora's regime detector is **reactive, not predictive**. It classifies the *current* state based on lagging indicators (SMA-5/15, ATR-14/32). By the time HIGH_VOLATILITY is confirmed (4-bar hysteresis = 20 minutes on 5m), the vol spike may be half-over. There is no mechanism to anticipate regime *transitions* or detect *exhaustion* of a trend before it reverses.

---

## 2. Proposed PPO Action Space (Regime Oracle)

### 2.1 Design Rationale

The Oracle should not merely replicate Aurora's regime detector (that would be pointless). Instead, it should predict **what regime the market is transitioning INTO** over the next N bars. The key value-add is detecting transitions *before* the lagging SMA/ATR indicators confirm them.

### 2.2 Action Space Definition

```python
action_dim = 5  # Discrete categorical

REGIME_ACTIONS = {
    0: "PREDICT_TREND_UP",        # Market entering bullish trend
    1: "PREDICT_TREND_DOWN",      # Market entering bearish trend
    2: "PREDICT_MEAN_REVERSION",  # Market entering range-bound / sideways
    3: "PREDICT_HIGH_VOLATILITY", # Volatility spike incoming
    4: "PREDICT_EXHAUSTION",      # Current regime is dying/transitioning
}
```

### 2.3 Why 5 Actions (Not 6+)

| Considered | Decision | Reason |
|-----------|----------|--------|
| `LOW_VOLATILITY` | Merged into `MEAN_REVERSION` | Low vol IS mean reversion in practice; they have the same trading implication (tight stops, small targets) |
| `UNCERTAIN` | Not an action | `UNCERTAIN` is a detector failure state, not a market property. PPO should always commit to a prediction |
| `EXHAUSTION` | **Added** | The single most valuable prediction. Detecting that a TREND or HIGH_VOL period is *ending* allows Aurora to tighten stops / take profit before reversal |
| `FLAT_LOW/NORMAL/HIGH` | Collapsed | These are sub-states of MR; Aurora can derive them post-hoc from MR + ATR% |

### 2.4 Interpretation by Aurora

When Aurora receives a shadow intent `EVT:NEOCORTEX_REGIME_PREDICTION`:

| PPO Prediction | Aurora Behavior |
|---------------|----------------|
| `PREDICT_TREND_UP` | Pre-bias toward LONG signals; widen TP multiplier early |
| `PREDICT_TREND_DOWN` | Pre-bias toward SHORT signals; widen TP multiplier early |
| `PREDICT_MEAN_REVERSION` | Tighten stops/targets; prefer MR strategy |
| `PREDICT_HIGH_VOLATILITY` | Reduce sizing preemptively; widen stops before confirmation |
| `PREDICT_EXHAUSTION` | Tighten trailing stops on open positions; block new entries in current regime direction |

---

## 3. Self-Supervised Reward Function

### 3.1 Core Principle

PPO is trained on **future realized features** from `logs/features/{symbol}.log`. No PnL is involved. The agent predicts what the market will look like at time `t + H` (horizon), and receives reward based on whether its prediction matched reality.

### 3.2 Feature-Derived "Ground Truth" Labels

At each timestep `t`, we compute the *realized* regime at `t + H` using features from the log:

```python
HORIZON_BARS = 5  # Look-ahead: 5 bars × 5min = 25 minutes

def compute_realized_regime(features_t: dict, features_t_plus_H: dict) -> int:
    """
    Determine what regime ACTUALLY materialized H bars later.
    Uses the same features available in logs/features/*.log.
    """
    # --- Volatility axis ---
    atr_pct_now = features_t["volatility_atr_pct"]
    atr_pct_future = features_t_plus_H["volatility_atr_pct"]
    vol_ratio = atr_pct_future / max(atr_pct_now, 1e-8)

    # --- Trend axis ---
    delta_price_future = features_t_plus_H["delta_price"]
    ema_bias_future = features_t_plus_H["ema_bias"]

    # --- Range axis ---
    range_pct_future = features_t_plus_H["volatility_range_pct"]

    # --- Classification rules ---

    # Rule 1: HIGH_VOLATILITY - vol ratio spiked significantly
    if vol_ratio > 1.4:
        return 3  # PREDICT_HIGH_VOLATILITY

    # Rule 2: EXHAUSTION - vol was high but is collapsing
    if atr_pct_now > EXHAUSTION_ATR_THRESHOLD and vol_ratio < 0.75:
        return 4  # PREDICT_EXHAUSTION

    # Rule 3: TREND_UP - positive directional move + EMA alignment
    if delta_price_future > TREND_DELTA_THRESHOLD and ema_bias_future > TREND_EMA_THRESHOLD:
        return 0  # PREDICT_TREND_UP

    # Rule 4: TREND_DOWN - negative directional move + EMA alignment
    if delta_price_future < -TREND_DELTA_THRESHOLD and ema_bias_future < -TREND_EMA_THRESHOLD:
        return 1  # PREDICT_TREND_DOWN

    # Rule 5: MEAN_REVERSION - small moves, narrow range
    if abs(delta_price_future) < MR_DELTA_THRESHOLD and range_pct_future < MR_RANGE_THRESHOLD:
        return 2  # PREDICT_MEAN_REVERSION

    # Default: the mildest claim
    return 2  # PREDICT_MEAN_REVERSION (conservative fallback)
```

### 3.3 Reward Formulas

#### Formula A: Exact Match Reward (Primary)

$$r_t = \begin{cases} +1.0 & \text{if } a_t = \text{realized\_regime}(t+H) \\ -0.5 & \text{if } a_t \neq \text{realized\_regime}(t+H) \end{cases}$$

Asymmetric penalty (|-0.5| < |+1.0|) prevents collapse to always-predict-majority-class.

#### Formula B: Confusion-Weighted Reward (Refined)

Not all mismatches are equal. Predicting TREND_UP when HIGH_VOL happened is worse than predicting TREND_UP when TREND_DOWN happened (at least the agent noticed directionality).

```python
# Confusion penalty matrix C[predicted][realized]
# Rows = predicted action, Cols = realized regime
# Values: reward for (predicted, realized) pair.
#
#                   realized:  T_UP   T_DOWN   MR     H_VOL   EXHAUST
REWARD_MATRIX = [
    # predicted T_UP          +1.0   -1.0    -0.3    -0.8     -0.5
    # predicted T_DOWN        -1.0   +1.0    -0.3    -0.8     -0.5
    # predicted MR            -0.3   -0.3    +1.0    -0.6     -0.3
    # predicted H_VOL         -0.5   -0.5    -0.4    +1.0     +0.3
    # predicted EXHAUST       -0.3   -0.3    +0.2    +0.3     +1.0
]
```

Key design choices in the matrix:
- **TREND direction errors** are heavily penalized (-1.0): being on the wrong side of a trend is catastrophic
- **HIGH_VOL miss** penalized when predicted TREND (-0.8): vol spikes destroy trend strategies
- **EXHAUSTION/HIGH_VOL partial credit** (+0.3): these are adjacent states (vol rising vs vol peaking), so partial match is acceptable
- **EXHAUSTION/MR partial credit** (+0.2): exhaustion often transitions to MR

$$r_t = C[a_t][\text{realized\_regime}(t+H)]$$

#### Formula C: Continuous Confidence Reward (Advanced)

Instead of hard classification, reward proportional to how well the prediction matched the feature trajectory:

$$r_t = \sum_{k=1}^{K} w_k \cdot \text{alignment}_k(a_t, \mathbf{f}_{t+H})$$

Where alignment functions per feature axis:

| Feature Axis `k` | Alignment function | Weight `w_k` |
|------------------|-------------------|-------------|
| **Volatility** (`volatility_atr_pct`) | `+1 if (predicted H_VOL and atr_pct increased by >30%), else scaled by ratio` | 0.35 |
| **Direction** (`delta_price`, `ema_bias`) | `+1 if bias direction matches predicted trend direction` | 0.30 |
| **Range** (`volatility_range_pct`) | `+1 if (predicted MR and range compressed), else -1` | 0.20 |
| **Exhaustion** (`volatility_atr_pct` slope) | `+1 if (predicted EXHAUST and ATR decreased >25% from local peak)` | 0.15 |

### 3.4 Recommended Approach

**Start with Formula A** (simple exact match). It provides clean gradients and avoids reward-hacking complexity. Once training is stable, upgrade to **Formula B** to penalize catastrophic mispredictions more heavily.

Formula C is a future enhancement for when the agent needs finer-grained learning.

### 3.5 Feature Thresholds (Tunable Hyperparameters)

```yaml
# regime_oracle_reward.yaml
horizon_bars: 5                    # Look-ahead window (5 bars = 25 min on 5m TF)

# Ground-truth labeling thresholds
exhaustion_atr_threshold: 0.003    # ATR% above which "high vol" is considered active
trend_delta_threshold: 0.001       # |delta_price| above which trend is detected
trend_ema_threshold: 0.0005        # |ema_bias| above which EMA confirms direction
mr_delta_threshold: 0.0005         # |delta_price| below which MR is claimed
mr_range_threshold: 0.002          # range_pct below which MR is confirmed
exhaustion_vol_decay: 0.75         # vol_ratio below which exhaustion is confirmed

# Reward scaling
reward_correct: 1.0
reward_wrong: -0.5
reward_matrix_enabled: false       # Start with Formula A, enable B later
```

### 3.6 Episode Construction (Changed)

**Before (PnL):**
```
Episode = (features_at_entry, side, PnL_from_position_close)
Trigger: POSITION_CLOSED event in aurora_core.log
Frequency: Infrequent (per trade, maybe 5-20/day)
```

**After (Regime Oracle):**
```
Episode = (features_at_t, predicted_regime, realized_regime_at_t+H)
Trigger: Every bar close (feature tick), with H-bar look-ahead settled
Frequency: High (every 5 minutes per symbol = 288/day/symbol)
```

This is a **massive increase** in training signal density: from ~10 episodes/day to ~288/day. The agent receives continuous feedback every bar, not just when trades close.

---

## 4. Architectural Changes Required

### 4.1 Files to Modify

| File | Change | Scope |
|------|--------|-------|
| `config/neocortex/neuro.yaml` | `action_dim: 3 → 5`, add `reward_mode: "regime_oracle"` | Config |
| `config/neocortex/ingest.yaml` | Add `horizon_bars: 5`, reward threshold configs | Config |
| `apps/.../neocortex/logic/brain/core.py` | Change `action_names` from `["LONG","SHORT","FLAT"]` to `["TREND_UP","TREND_DOWN","MR","HIGH_VOL","EXHAUSTION"]` (line 382) | Core |
| `apps/.../neocortex/transport/adapter.py` | Replace `_episode_to_dict()` reward extraction (lines 243-290) with feature-based reward computation | Core |
| `apps/.../neocortex/transport/adapter.py` | Replace `_maybe_dream()` trigger logic (lines 292-335): episode = every bar, not every trade close | Core |
| `apps/.../neocortex/transport/adapter.py` | Replace `_generate_shadow_intent()` (lines 428-499): emit `EVT:NEOCORTEX_REGIME_PREDICTION` instead of `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` | Core |
| `apps/.../neocortex/logic/ingest/multi_tailer.py` | Simplify: no longer need order_log or core_log parsing. Only features stream is needed | Simplification |
| `apps/.../neocortex/logic/ingest/parsers/core_parser.py` | Can be deactivated (no PnL reward) | Simplification |
| `apps/.../neocortex/logic/amygdala/valuation.py` | Update importance scoring: no longer `abs(reward)`. Use prediction confidence or entropy | Minor |

### 4.2 New Components to Create

| Component | Purpose | Location |
|-----------|---------|----------|
| `RegimeLabeler` | Compute realized regime from feature history using thresholds | `apps/.../neocortex/logic/reward/regime_labeler.py` |
| `RegimeRewardCalculator` | Apply reward formula (A/B/C) given prediction and label | `apps/.../neocortex/logic/reward/reward_calculator.py` |
| `FeatureRingBuffer` | Store last H bars of features per symbol for look-ahead settlement | `apps/.../neocortex/logic/reward/feature_buffer.py` |
| `regime_oracle_reward.yaml` | Reward thresholds and hyperparameters | `config/neocortex/regime_oracle_reward.yaml` |

### 4.3 Components Unchanged

| Component | Reason |
|-----------|--------|
| **VAE** (encoder/decoder) | Still compresses 20 features → 16-dim latent. No change needed |
| **World Model** (RNN dynamics) | Still predicts latent dynamics. Agnostic to what PPO does with latent |
| **PPO algorithm** (updater, buffer, GAE) | PPO itself is task-agnostic. Only the reward source changes |
| **ActorCriticLSTM** | Architecture stays. Only `action_dim` config changes (3 → 5) |
| **WelfordNormalizer** | Still normalizes input features |
| **FeatureParser** | Still parses EVT:FEATURES_CALCULATED |

### 4.4 Data Flow (After Pivot)

```
EVT:FEATURES_CALCULATED (every 5m bar)
    │
    ├──→ FeatureParser → Normalize → VAE.encode() → z[16]
    │        │
    │        └──→ FeatureRingBuffer.push(features_t)
    │
    ├──→ PPOAgent.act(z) → predicted_regime (0-4)
    │
    ├──→ Emit EVT:NEOCORTEX_REGIME_PREDICTION {
    │        symbol, predicted_regime, confidence, latent_state
    │    }
    │
    └──→ [After H bars settle]
         FeatureRingBuffer.get(t - H) → features_at_t
         FeatureRingBuffer.get(t)     → features_at_t+H
             │
             └──→ RegimeLabeler.label(features_t, features_t+H) → realized_regime
                      │
                      └──→ RegimeRewardCalculator.compute(predicted, realized) → r_t
                               │
                               └──→ EpisodicBuffer.add(z_t, predicted, r_t)
                                        │
                                        └──→ [Every dream_episode_threshold]
                                             BrainCore.train_ppo(episodes)
```

### 4.5 Implementation Phases

**Phase 1: Infrastructure (no behavior change)**
1. Create `FeatureRingBuffer` with capacity = `horizon_bars + margin`
2. Create `RegimeLabeler` with configurable thresholds
3. Create `RegimeRewardCalculator` with Formula A
4. Create `regime_oracle_reward.yaml` config
5. Unit tests for labeler and reward calculator

**Phase 2: Wiring (swap reward source)**
6. Modify `adapter.py` to push features into `FeatureRingBuffer`
7. Modify `_maybe_dream()` to trigger on settled look-ahead bars (not trade closes)
8. Modify `_episode_to_dict()` to use regime reward instead of PnL
9. Update `neuro.yaml`: `action_dim: 5`
10. Update `core.py`: action names mapping

**Phase 3: Output Integration**
11. Modify `_generate_shadow_intent()` to emit regime predictions
12. Define `EVT:NEOCORTEX_REGIME_PREDICTION` event schema
13. Add optional consumer in Aurora's decision module (read-only, shadow mode)

**Phase 4: Validation**
14. Backtest with historical feature logs: does PPO converge?
15. Compare PPO predictions vs Aurora's lagged detector: is PPO earlier?
16. Measure prediction accuracy per regime class
17. A/B shadow test: log PPO predictions alongside Aurora's real regime decisions

---

## 5. Risk Analysis

### 5.1 Label Imbalance

Markets spend ~60-70% of time in MEAN_REVERSION. PPO may collapse to always predicting MR.

**Mitigation:**
- Use class-weighted rewards: `reward_correct[MR] = 0.5`, `reward_correct[HIGH_VOL] = 2.0`
- Or over-sample rare regime episodes in the training buffer
- Monitor per-class prediction frequency in telemetry

### 5.2 Threshold Sensitivity

The ground-truth labeler uses hard thresholds (e.g., `trend_delta_threshold = 0.001`). Bad thresholds = bad labels = garbage training.

**Mitigation:**
- All thresholds live in YAML config, tunable without code changes
- Run threshold sensitivity analysis on historical data before going live
- Consider soft labels (probability distribution over regimes) in Formula C

### 5.3 Look-Ahead Bias in Backtesting

The reward uses `features_at_t+H` which is only available H bars in the future. During backtest, this is trivially available. In production, reward settlement is delayed by H bars.

**Mitigation:**
- FeatureRingBuffer naturally handles this: reward for prediction at `t` is only computed when bar `t+H` arrives
- PPO trains on delayed episodes - this is standard for off-policy updates

### 5.4 Regime Oracle Does NOT Replace Regime Detector

The PPO Oracle is a *complement*, not a replacement for Aurora's rule-based regime detector. Aurora continues to use its SMA/ATR-based detector for all real-time decisions. The Oracle provides an early-warning advisory signal.

---

## 6. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Accuracy (overall)** | > 45% (5-class random = 20%) | `correct_predictions / total_predictions` |
| **Exhaustion recall** | > 30% | `true_exhaust_detected / total_exhaust_events` |
| **Lead time** | > 2 bars earlier than Aurora | `aurora_regime_change_ts - ppo_prediction_ts` |
| **Training convergence** | Policy loss decreasing over 1000+ episodes | Loss curve monitoring |
| **Class diversity** | No single action > 60% of all predictions | Action distribution entropy |

---

## 7. Configuration Summary (New Files)

### `config/neocortex/neuro.yaml` (diff)

```yaml
ppo:
  state_dim: 16       # unchanged
  action_dim: 5       # was: 3 (LONG/SHORT/FLAT) → now: 5 regime predictions
  hidden_dims: [256, 128]  # unchanged
  reward_mode: "regime_oracle"  # NEW: switches reward pipeline
```

### `config/neocortex/regime_oracle_reward.yaml` (new)

```yaml
horizon_bars: 5
exhaustion_atr_threshold: 0.003
trend_delta_threshold: 0.001
trend_ema_threshold: 0.0005
mr_delta_threshold: 0.0005
mr_range_threshold: 0.002
exhaustion_vol_decay: 0.75
reward_correct: 1.0
reward_wrong: -0.5
reward_matrix_enabled: false
class_weights:
  PREDICT_TREND_UP: 1.5
  PREDICT_TREND_DOWN: 1.5
  PREDICT_MEAN_REVERSION: 0.7
  PREDICT_HIGH_VOLATILITY: 2.0
  PREDICT_EXHAUSTION: 2.5
```

---

*End of Document. No functional code changes have been made.*
