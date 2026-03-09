# Aurora & Mean Reversion Scoring System

This document outlines the current scoring logic for the Phenix project based purely on the real config files, python implementation code, and JSON schemas.

## 1. Core Principles (Signal Score V2)
The project relies on `SignalScoreV2` standard (defined in `apps/reference/domains/decision_making/signal_score_v2.py`) and is known as the "Net-Zero Scoring" standard.

Key principles:
1. **Fail-Closed**: If `essential_features` are missing or `not_ready` (e.g. during warmup), the engine returns `deferred = True` and blocks execution.
2. **Net-Zero Formula**: All features are normalized around `0`. The formula is:
   `score = Σ w_i * (x_i - neutral_i) / Σ |w_i|`
3. **Hard Gating vs. Weights**: Previously weighted features like Liquidity (`liquidity_kappa`) are now purely hard gates (`kappa_min`), excluded from `score_raw`.
4. **Configuration Contract**: Every feature present in `signal_weights` MUST have a corresponding value in `feature_neutrals`.

## 2. Aurora Kernels

Aurora utilizes two kernels based on the configuration:

### Aurora (Direction/Strength split - v2)
Configured via `scoring_version: v2` and `direction_strength_scoring`.
- **Directional Features** (signed values, dictate side): e.g., `obi`, `tfi`, `delta_price`, `ema_bias`, `depth_imbalance`, `macro_resid`. Note: `macro_resid` replaced `macro_sync` for directional scoring.
- **Strength Features** (magnitude only, apply alpha/cap): e.g., `volume_spike`, `volatility_state`.
- **Logic**: Calculates directional score and strength score separately, combining them via `strength_alpha` and bounding by `strength_cap`.

### Phase 9: Quadratic Brain Kernel
Found in `quadratic_scoring_kernel.py`.
Formula: `Exposure = sign(Σ) × Σ²`
- Used for high-conviction non-linear scaling.
- Near-zero exposure for weak signals (hesitation penalty).
- Aggressive scaling for strong signals (conviction reward).
- Accepts a `linear_score` (Pillar Sum from Timeframe Pillars like Tactician/M15, Operator/H4, Strategist/D1) and applies the squaring before being optionally scaled by a `shield_multiplier`.

## 3. Thresholds & Hysteresis
After raw scoring, `AuroraScoringKernel` applies threshold multiplication and hysteresis.

### Multipliers
1. **Regime Multiplier**: Base threshold is multiplied by `regime_thresholds[current_regime]`. If unavailable, falls back to `DEFAULT`. It can also be smoothed exponentially via `RegimeMultiplierSmoother`.
2. **Side Bias Penalty**: Penalizes the `thr_buy` or `thr_sell` threshold based on the `SideBiasState` (if there's a strong imbalance in previous intent direction vs `target_ratio`).

### Hysteresis (3-zone determination)
If `neutral_threshold` is provided, instead of a simple binary logic, a 3-zone system is created:
- **ENTER**: Score crosses `signal_threshold` (adjusted by regime/bias).
- **HOLD**: While in a position, the side is held as long as the score remains above the lower `neutral_threshold` (in the same direction).
- **EXIT**: If score drops below `neutral_threshold`, the decision is dropped to neutral (`""`).
- **FLIP**: If the score strongly reverses and exceeds the opposite entry threshold (`-thr_sell` or `thr_buy`), it flips the side directly.

## 4. Feature Configuration & Weights
According to `config/aurora/strategies/aurora.yaml` global parameters:

**Feature Neutrals**
- `ema_bias`: `0.5`
- `depth_imbalance`: `0.5`
- `macro_sync`: `0.5`
- All other standard features (`obi`, `tfi`, `delta_price`, `volume_spike`, `volatility_state`, `macro_resid`): `0.0`

**Essential Features**
- `obi`, `delta_price`, `macro_resid`. Without these, fail-closed behavior halts scoring.

## 5. Artifacts and Tooling
- Scoring is entirely deterministic and side-effect free.
- Outputs a `ScoringResult` object: `score`, `side`, `thr_buy`, `thr_sell`, `why_chain` (for tracing), and `psi_vector` (which captures explainable metrics for downstream ML pipelines or audits).
