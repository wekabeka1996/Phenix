# Aurora Phase 2 Optimization Plan

**Created**: 2025-12-04  
**Strategy**: Incremental Feature Search (Fix Phase 1, Optimize Phase 2)

---

## 📊 Current State (Phase 1 - DONE)

### Features Optimized (40%)
| Feature | Status | Best Params Found |
|---|---|---|
| **EMA** | ✅ Optimized | `period_short: 7-12`, `period_long: 14-25` |
| **Volume Spike** | ✅ Optimized | `window_sec: 150-280`, `sma_length: 4-16` |
| **Liquidity** | ✅ Optimized | `depth_half: 750-4750`, `kappa_min: 0.15-0.49` |
| **OBI** | ✅ Optimized | `window_sec: 50-290` |
| **TFI** | ✅ Optimized | `window_sec: 80-240` |
| **Macro Sync** | ⚠️ Used (global weight) | NOT optimized per-asset |

**Results**: SOL (+$173), ETH (+$76), XRP (+$29), DOGE (+$5)

---

## 🎯 Phase 2: Unused Features (20%)

### Identified Unused Features

#### 1. **Volatility State** (`volatility_state`)
```yaml
# config/aurora/features.yaml (lines 47-56)
volatility:
  window_sec: 60       # НЕ ОПТИМІЗУВАЛИ!
  sma_length: 10       # НЕ ОПТИМІЗУВАЛИ!

volatility_state:
  cap_max: 3.0         # НЕ ОПТИМІЗУВАЛИ!
```

**Current Weight**: `0.10` (global)  
**Was it optimized?** ❌ NO (ми не змінювали `window_sec`, `sma_length`)  
**Potential**: HIGH (volatility filtering critical for risk management)

#### 2. **Depth Imbalance** (`depth_imbalance`)
```yaml
# config/aurora/features.yaml (lines 70-71)
depth_imbalance:
  use_laplace_smoothing: true  # НЕ ОПТИМІЗУВАЛИ параметр!
```

**Current Weight**: `0.15` (global)  
**Was it optimized?** ❌ NO (ми не змінювали smoothing params)  
**Formula**: `ratio = (asks + depth_half) / (bids + depth_half)`  
**Potential**: MEDIUM (order book asymmetry signal)

#### 3. **Delta Price** (`delta_price`)
```yaml
# config/aurora/features.yaml (lines 78-79)
delta_price:
  spike_filter_ms: 5000  # НЕ ОПТИМІЗУВАЛИ!
```

**Current Weight**: `0.10` (global)  
**Was it optimized?** ❌ NO (ми не змінювали `spike_filter`)  
**Potential**: MEDIUM (price momentum, але може бути шумним)

#### 4. **Macro Sync Window** (partial optimization)
```yaml
# config/aurora/features.yaml (lines 86-93)
macro_sync:
  window: 60            # НЕ ОПТИМІЗУВАЛИ!
  anchors: [BTC, ETH]   # НЕ ОПТИМІЗУВАЛИ (можна додати SOL?)
```

**Current Weight**: `weight_macro` (ми оптимізували ВАГИ, але НЕ window!)  
**Potential**: HIGH (correlation critical for altcoins)

---

## 🔧 Phase 2 Optimization Strategy

### Step 1: Fix Phase 1 Parameters (LOCKED)

Всі параметри з `best_aurora_*_3m.json` та `best_aurora_*_5m.json` стають **ФІКСОВАНИМИ**:

```python
# NEW FILE: apps/research/aurora_optuna/optuna_runner_aurora_v2.py

# PHASE 1 PARAMS (FIXED from best results)
FIXED_PARAMS_SOLUSDT = {
    'ema_period_short': 7,         # LOCKED
    'ema_period_long': 25,         # LOCKED
    'volume_window_sec': 280,      # LOCKED
    'volume_sma_length': 16,       # LOCKED
    'liquidity_depth_half': 3000,  # LOCKED
    'liquidity_kappa_min': 0.345,  # LOCKED
    'obi_window_sec': 70,          # LOCKED
    'tfi_window_sec': 160,         # LOCKED
    'weight_ema': 0.467,           # LOCKED
    'weight_volume': 0.242,        # LOCKED
    'weight_liquidity': 0.138,     # LOCKED
    'weight_obi': 0.344,           # LOCKED
    'weight_tfi': 0.363,           # LOCKED
    'signal_threshold': 0.110,     # LOCKED
    'max_risk_score': 0.784,       # LOCKED
    'sl_pct': 0.526,               # LOCKED
    'max_hold_sec': 660,           # LOCKED
    'allowed_regimes': ['TREND_DOWN'],  # LOCKED
}

# PHASE 2 PARAMS (OPTIMIZED in this run)
def objective_phase2(trial, df, btc_df, fixed_params, bar_seconds=180):
    # Start with fixed params
    params = fixed_params.copy()
    
    # === NEW: Volatility State ===
    params['volatility_window_sec'] = trial.suggest_int('volatility_window_sec', 30, 300, step=10)
    params['volatility_sma_length'] = trial.suggest_int('volatility_sma_length', 3, 20)
    params['volatility_cap_max'] = trial.suggest_float('volatility_cap_max', 2.0, 5.0)
    params['weight_volatility'] = trial.suggest_float('weight_volatility', 0.0, 0.5)
    
    # === NEW: Depth Imbalance ===
    params['depth_imbalance_smoothing'] = trial.suggest_categorical('depth_imbalance_smoothing', [True, False])
    params['weight_depth_imbalance'] = trial.suggest_float('weight_depth_imbalance', 0.0, 0.4)
    
    # === NEW: Delta Price ===
    params['delta_price_spike_filter_ms'] = trial.suggest_int('delta_price_spike_filter_ms', 1000, 10000, step=1000)
    params['weight_delta_price'] = trial.suggest_float('weight_delta_price', 0.0, 0.3)
    
    # === NEW: Macro Sync Window ===
    params['macro_sync_window'] = trial.suggest_int('macro_sync_window', 20, 120, step=10)
    params['weight_macro'] = trial.suggest_float('weight_macro', 0.1, 0.5)  # Re-optimize weight
    
    # Rebuild features and backtest...
    df_trial = build_aurora_features_v2(df, btc_df, params, bar_seconds)
    engine = BacktestEngineAurora(df_trial, params)
    metrics = engine.run()
    
    return metrics['total_pnl']
```

---

## 📝 Modified Files for Phase 2

### File 1: `apps/research/aurora_optuna/features_aurora.py`

**Add new compute functions**:

```python
def compute_volatility_state(df, params, bar_seconds=60):
    """Compute volatility state with optimized window."""
    window_sec = params.get('volatility_window_sec', 60)
    sma_length = params.get('volatility_sma_length', 10)
    cap_max = params.get('volatility_cap_max', 3.0)
    
    window_bars = window_sec // bar_seconds
    
    # Compute price range
    df['range'] = df[get_col_name(df, 'high')] - df[get_col_name(df, 'low')]
    
    # SMA of range
    df['range_sma'] = df['range'].rolling(window=sma_length).mean()
    
    # Volatility ratio
    df['volatility_ratio'] = df['range'] / df['range_sma']
    df['volatility_ratio'] = df['volatility_ratio'].clip(upper=cap_max)
    
    # Normalize to [0, 1]
    df['volatility_state'] = df['volatility_ratio'] / cap_max
    df['volatility_state'] = df['volatility_state'].fillna(0.5)
    
    return df

def compute_depth_imbalance(df, params):
    """Compute depth imbalance with optional smoothing."""
    use_smoothing = params.get('depth_imbalance_smoothing', True)
    depth_half = params.get('liquidity_depth_half', 1000.0)
    
    bid_col = get_col_name(df, 'tob_bid_qty')
    ask_col = get_col_name(df, 'tob_ask_qty')
    
    if use_smoothing:
        # Laplace smoothing
        df['depth_imbalance'] = (df[ask_col] + depth_half) / (df[bid_col] + depth_half)
    else:
        # Raw ratio
        df['depth_imbalance'] = df[ask_col] / df[bid_col]
    
    # Normalize to [0, 1] (1.0 = neutral, >1.0 = ask pressure)
    df['depth_imbalance'] = (df['depth_imbalance'] - 0.5).clip(-0.5, 0.5) + 0.5
    df['depth_imbalance'] = df['depth_imbalance'].fillna(0.5)
    
    return df

def compute_delta_price(df, params):
    """Compute delta price with spike filtering."""
    spike_filter_ms = params.get('delta_price_spike_filter_ms', 5000)
    
    close_col = get_col_name(df, 'close')
    
    # Compute price change
    df['delta_price'] = df[close_col].diff()
    
    # Filter spikes (reconnection artifacts)
    df['ts_diff'] = df['ts'].diff()
    df.loc[df['ts_diff'] > spike_filter_ms, 'delta_price'] = 0
    
    # Normalize (optional: scale by ATR or std)
    df['delta_price'] = df['delta_price'].fillna(0)
    
    return df

def build_aurora_features_v2(df, btc_df, params, bar_seconds=60):
    """Build features with Phase 2 params."""
    # Phase 1 features (use fixed params from `params`)
    df = compute_ema_bias(df, params, bar_seconds)
    df = compute_volume_spike(df, params, bar_seconds)
    df = compute_macro_sync(df, btc_df, params, bar_seconds)
    df = compute_liquidity(df, params)
    df = compute_obi(df, params, bar_seconds)
    df = compute_tfi(df, params, bar_seconds)
    
    # Phase 2 features (NEW!)
    df = compute_volatility_state(df, params, bar_seconds)
    df = compute_depth_imbalance(df, params)
    df = compute_delta_price(df, params)
    
    # Add regime labels
    df = add_regime_labels_aurora(df, bar_seconds)
    
    return df
```

---

### File 2: `apps/research/aurora_optuna/backtest_engine_aurora.py`

**Update signal calculation to include Phase 2 features**:

```python
def run(self):
    # ... existing code ...
    
    # Phase 1 weights (from params)
    signal = (
        params['weight_ema'] * features.get('ema_bias', 0.5) +
        params['weight_volume'] * features.get('volume_spike', 0.5) +
        params['weight_liquidity'] * features.get('liquidity', 0.5) +
        params['weight_obi'] * features.get('obi', 0) +
        params['weight_tfi'] * features.get('tfi', 0)
    )
    
    # Phase 2 weights (NEW!)
    signal += params.get('weight_volatility', 0) * features.get('volatility_state', 0.5)
    signal += params.get('weight_depth_imbalance', 0) * features.get('depth_imbalance', 0.5)
    signal += params.get('weight_delta_price', 0) * features.get('delta_price', 0)
    signal += params.get('weight_macro', 0.138) * features.get('macro_sync', 0.5)  # Re-optimized
    
    # Normalize by total weight
    total_weight = (
        params['weight_ema'] +
        params['weight_volume'] +
        params['weight_liquidity'] +
        params['weight_obi'] +
        params['weight_tfi'] +
        params.get('weight_volatility', 0) +
        params.get('weight_depth_imbalance', 0) +
        params.get('weight_delta_price', 0) +
        params.get('weight_macro', 0.138)
    )
    
    signal = signal / total_weight if total_weight > 0 else 0
    
    # ... rest of backtest ...
```

---

## 🚀 Execution Plan

### Trials Configuration
- **Assets**: SOLUSDT (3m), ETHUSDT (5m), XRPUSDT (3m), DOGEUSDT (3m)
- **Trials**: 1000 per asset (less than Phase 1 since search space is smaller)
- **Fixed Params**: All Phase 1 params from `best_aurora_*_3m.json`
- **Optimize**: 4 new features × 2-4 params each = ~12 new dimensions

### Expected Outcomes
1. **Volatility filtering** → Better risk-adjusted returns
2. **Depth imbalance** → Better entry timing (avoid crowded side)
3. **Delta price** → Momentum confirmation
4. **Macro sync window** → Improved correlation for altcoins

---

## 📊 Success Metrics

| Metric | Phase 1 Baseline | Phase 2 Target |
|---|---|---|
| SOL PnL | $173.73 | **$200+** |
| ETH PnL | $76.12 | **$90+** |
| XRP PnL | $28.95 | **$35+** |
| DOGE PnL | $5.20 | **$10+** |

**Goal**: +15-20% improvement with 20% more features.

---

## 💡 Phase 3 Preview (Future)

After Phase 2, we have:
- 40% features (Phase 1) ✅
- 20% features (Phase 2) 🔄
- **40% remaining**: Futures (funding, OI), Advanced (EMA mid, volume z-score)

Phase 3 would lock Phase 1+2 and optimize the final 20-40%.
