# Aurora Existing Features - Optimization Plan

**Мета**: Оптимізувати параметри, які вже працюють в Aurora, БЕЗ додавання нових індикаторів.

## 📊 Що Оптимізуємо (Existing Features):

### 1. EMA Configuration
```yaml
ema:
  period_short: 3      # Діапазон для Optuna: 2-10
  period_long: 7       # Діапазон для Optuna: 5-20
```

### 2. Volume Spike
```yaml
volume:
  window_sec: 60       # Діапазон: 30-300
  sma_length: 5        # Діапазон: 3-20
volume_spike:
  cap_max: 3.0         # Діапазон: 2.0-5.0
```

### 3. Volatility State
```yaml
volatility:
  window_sec: 60       # Діапазон: 30-300
  sma_length: 10       # Діапазон: 5-30
volatility_state:
  cap_max: 3.0         # Діапазон: 2.0-5.0
```

### 4. Liquidity
```yaml
liquidity:
  depth_half: 1000.0   # Діапазон: 500-5000
  kappa_min: 0.3       # Діапазон: 0.1-0.5
  kappa_max: 1.0       # Фіксований
```

### 5. Signal Thresholds (trading.yaml)
```yaml
decision:
  signal_threshold: 0.10           # Діапазон: 0.05-0.30
  neutral_threshold: 0.18          # Діапазон: 0.10-0.30
```

### 6. Regime Multipliers
```yaml
regime_threshold_multipliers:
  HIGH_VOLATILITY: 1.20   # Діапазон: 1.0-1.5
  LOW_VOLATILITY: 0.90    # Діапазон: 0.7-1.0
  MEAN_REVERSION: 1.05    # Діапазон: 0.9-1.2
```

---

## 🎯 Optuna Search Space (21 параметрів)

```python
search_space = {
    # EMA
    'ema_period_short': (2, 10, 'int'),
    'ema_period_long': (5, 20, 'int'),
    
    # Volume
    'volume_window_sec': (30, 300, 'int'),
    'volume_sma_length': (3, 20, 'int'),
    'volume_cap_max': (2.0, 5.0, 'float'),
    
    # Volatility
    'volatility_window_sec': (30, 300, 'int'),
    'volatility_sma_length': (5, 30, 'int'),
    'volatility_cap_max': (2.0, 5.0, 'float'),
    
    # Liquidity
    'liquidity_depth_half': (500, 5000, 'float'),
    'liquidity_kappa_min': (0.1, 0.5, 'float'),
    
    # Signal Thresholds
    'signal_threshold': (0.05, 0.30, 'float'),
    'neutral_threshold': (0.10, 0.30, 'float'),
    
    # Regime Multipliers
    'regime_high_vol': (1.0, 1.5, 'float'),
    'regime_low_vol': (0.7, 1.0, 'float'),
    'regime_mean_rev': (0.9, 1.2, 'float')
}
```

---

## 📂 Структура Проекту:

```
apps/research/aurora_optuna/
├── config.py              # Шляхи та константи
├── features_aurora.py     # Обчислення EMA, Volume, Volatility (копіювання з Aurora)
├── backtest_engine_aurora.py  # Decision logic на існуючих фічах
├── optuna_runner_aurora.py    # Optuna оптимізація
├── build_features.py      # Генерація features з 5s Golden data
└── README.md
```

---

## 🔧 Backtest Engine Logic:

```python
def should_enter(features, params):
    # 1. Compute composite signal (як в Aurora)
    signal = compute_composite_signal(features)
    
    # 2. Apply regime multiplier
    if regime == 'HIGH_VOL':
        threshold = params['signal_threshold'] * params['regime_high_vol']
    
    # 3. Neutral zone filter
    if abs(signal) < params['neutral_threshold']:
        return False
    
    # 4. Enter decision
    if signal > threshold:
        return 'LONG'
    elif signal < -threshold:
        return 'SHORT'
```

---

## 📈 Expected Improvements:

Поточна система (за замовчуванням) дає **PnL = Unknown** (немає baseline).

**Hypothesis**: Optuna знайде кращі параметри для:
- Volume/Volatility windows → точніший детект спайків
- Regime multipliers → менше false signals у високій волатильності
- Signal thresholds → оптимальний balance між активністю та якістю

**Target**: Досягти Calmar > 2.0 та Win Rate > 55% на Jan 2024 data.

---

## ⚙️ Implementation Steps:

1. **features_aurora.py**: Скопіювати logic з `feature_engineering.py`
2. **backtest_engine_aurora.py**: Відтворити decision logic
3. **optuna_runner_aurora.py**: Оптимізувати 21 параметр
4. **Запустити 200 trials** на BTCUSDT Jan 2024
5. **Порівняти з baseline** (default params)

---

**Статус**: Ready to implement
