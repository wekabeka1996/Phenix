# Plan: Native TA Features in FeatureEngineering pipeline

## Problem Summary

`ta_ensemble` (alpha_search) ЗАВЖДИ пропускається з WARNING:
```
[ETHUSDT] Skipping ta_ensemble: missing required features=['bb_position', 'bb_width', 'rsi_14', ...]
```

**Корінна причина**: `EVT:FEATURES_CALCULATED` для tick-data (tf_sec=0) містить лише Aurora
мікроструктурні фічі. TA-фічі (RSI, BB, Stochastic) потребують OHLCV-барів і в live-режимі
ніколи не обчислюються нативно — тільки в backtest через BacktestEngine (коментар у
`feature_engineering.py:912`).

**Сторонні спостереження**:
- `bars_60s.tsv` і `bars_180s.tsv` — 83 байти (тільки header). Це legacy-артефакти від старих
  `timeframe_sec=60/180`, зараз активний тільки 300s. Проблема не критична — просто сміття.
- Математика та формули в MR та ta_ensemble ідентичні. Різниця лише в назвах ключів:
  `bb.pct_b` → `bb_position`, `rsi` → `rsi_14`.

---

## Scope: що реалізуємо

### Фаза 1 (цей план) — MeanReversion features
Потрібні DOGEUSDT/MR моделлю та `ta_ensemble.mean_reversion_v1`:
| Потрібна назва (alpha_search) | Обчислення | Джерело |
|---|---|---|
| `bb_position` | BB.pct_b = (price - lower) / (upper - lower) | `compute_bollinger_bands()` вже є |
| `bb_width` | (upper - lower) / mid | `compute_bollinger_bands()` вже є |
| `rsi_14` | RSI(14) | `compute_rsi()` вже є |
| `price_sma_20_deviation` | (price - SMA20) / SMA20 | `compute_sma()` вже є |
| `volume_sma_ratio` | volume / mean(volumes[-20:]) | проста арифметика |
| `stoch_k` | Stochastic %K(14) | **потрібно додати** в indicators.py |
| `stoch_d` | SMA(%K, 3) | **потрібно додати** в indicators.py |

### Фаза 1 (цей план) — ATR features (для `volatility_v1`)
| Потрібна назва | Обчислення | Джерело |
|---|---|---|
| `atr_14` | ATR(14) | `compute_atr()` вже є + `BarVolatilityState.last_atr` вже рахується |
| `atr_ratio` | atr_14 / mean(atr_hist[-20:]) | потрібно rolling buffer |

### Фаза 2 (не в цьому плані) — Momentum + складні volatility features
`price_momentum_5m/1h/1d`, `macd_signal`, `realized_volatility_*` — потребують multi-timeframe
lookback, поки не реалізуємо.

---

## Архітектурний підхід

**Де**: `feature_engineering.py` — єдине правильне місце (SSOT для всіх фічей).

**Патерн**: Точно такий самий що і для `BarVolatilityState` — `Dict[Tuple[str,int], BarTAState]`.

```
on_bar_closed(symbol, tf_sec, bar_data)
  │
  ├── [існуючий код] будує bar_tick, aug_keys passthrough
  │
  ├── [NEW] _update_bar_ta_state(symbol, tf_sec, bar)
  │       → додає close/high/low/volume в rolling buffers
  │       → обчислює rsi_14, bb_position, bb_width, stoch_k, stoch_d,
  │                  price_sma_20_deviation, volume_sma_ratio, atr_14, atr_ratio
  │       → повертає dict з TA фічами
  │
  ├── [NEW] інжектує TA фічі в bar_tick
  │       bar_tick["rsi_14"] = "48.40"
  │       bar_tick["bb_position"] = "0.23"
  │       ...
  │
  └── [існуючий] _calculate_and_emit_features_for_tf()
        → aug_keys passthrough (lines 915-931) підхоплює їх автоматично
        → emit EVT:FEATURES_CALCULATED (tf_sec=300) з TA фічами ✓
              │
              └── feature_mirror_writer → alpha_input_v1.jsonl
                    └── ta_ensemble.get_required_features() → всі є ✓
```

**Ключова перевага**: `_calculate_and_emit_features_for_tf()` змінювати не треба — `aug_keys`
passthrough (рядки 915-931) підхопить нові ключі автоматично.

---

## Файли для зміни

### 1. `apps/reference/domains/feature_engineering/indicators.py`
**Додати** функцію `compute_stochastic()` після `compute_rsi()` (~line 243):

```python
def compute_stochastic(
    highs: List[Decimal],
    lows: List[Decimal],
    closes: List[Decimal],
    k_period: int = 14,
    d_period: int = 3,
) -> Optional[Tuple[float, float]]:
    """
    Compute Stochastic %K and %D.
    %K = (close - lowest_low) / (highest_high - lowest_low) * 100
    %D = SMA(%K, d_period)
    Returns (stoch_k, stoch_d) or None if insufficient data.
    """
    if len(closes) < k_period + d_period - 1:
        return None
    k_values = []
    for i in range(d_period):
        idx = -(d_period - i)
        window_highs = highs[idx - k_period + 1 : idx + 1 if idx < -1 else None]
        window_lows  = lows [idx - k_period + 1 : idx + 1 if idx < -1 else None]
        window_close = closes[idx]
        highest = max(window_highs)
        lowest  = min(window_lows)
        denom = float(highest - lowest)
        if denom == 0:
            k_values.append(50.0)
        else:
            k_values.append(float(window_close - lowest) / denom * 100.0)
    stoch_k = k_values[-1]
    stoch_d = sum(k_values) / len(k_values)
    return stoch_k, stoch_d
```

---

### 2. `apps/reference/domains/feature_engineering/types.py`
**Додати** `BarTAState` dataclass після `BarVolatilityState` (~line 170):

```python
from collections import deque
from typing import Optional

@dataclass
class BarTAState:
    """Per-(symbol, tf_sec) rolling buffer for TA indicator computation."""
    max_bars: int = 30  # 30 bars > max(bb_window=20, stoch=14+3)

    close_buf:  deque = field(default_factory=lambda: deque(maxlen=30))
    high_buf:   deque = field(default_factory=lambda: deque(maxlen=30))
    low_buf:    deque = field(default_factory=lambda: deque(maxlen=30))
    volume_buf: deque = field(default_factory=lambda: deque(maxlen=30))
    atr_buf:    deque = field(default_factory=lambda: deque(maxlen=30))  # for atr_ratio

    # Latest computed values (None = not ready yet)
    rsi_14: Optional[float] = None
    bb_position: Optional[float] = None
    bb_width: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    price_sma_20_deviation: Optional[float] = None
    volume_sma_ratio: Optional[float] = None
    atr_14: Optional[float] = None
    atr_ratio: Optional[float] = None

    def push(self, bar) -> None:
        """Append bar data to all buffers."""
        self.close_buf.append(bar.close)
        self.high_buf.append(bar.high)
        self.low_buf.append(bar.low)
        self.volume_buf.append(float(bar.volume) if bar.volume else 0.0)

    def as_feature_dict(self) -> dict:
        """Return only computed (non-None) values as string dict."""
        mapping = {
            "rsi_14": self.rsi_14,
            "bb_position": self.bb_position,
            "bb_width": self.bb_width,
            "stoch_k": self.stoch_k,
            "stoch_d": self.stoch_d,
            "price_sma_20_deviation": self.price_sma_20_deviation,
            "volume_sma_ratio": self.volume_sma_ratio,
            "atr_14": self.atr_14,
            "atr_ratio": self.atr_ratio,
        }
        return {k: str(round(v, 6)) for k, v in mapping.items() if v is not None}
```

---

### 3. `apps/reference/domains/feature_engineering/feature_engineering.py`

**3a. `__init__`** (~line 152) — додати поряд з `_bar_volatility_states`:
```python
self._bar_ta_states: Dict[Tuple[str, int], BarTAState] = {}
```

**3b. Новий метод** `_update_bar_ta_state()`:
```python
def _update_bar_ta_state(
    self, symbol: str, tf_sec: int, bar
) -> Dict[str, str]:
    """
    Update rolling TA buffers for (symbol, tf_sec) and compute indicators.
    Returns feature dict ready for bar_tick injection.
    """
    from apps.reference.domains.feature_engineering.types import BarTAState
    from apps.reference.domains.feature_engineering.indicators import (
        compute_bollinger_bands, compute_rsi, compute_stochastic, compute_sma,
    )
    import decimal

    key = (symbol, tf_sec)
    state = self._bar_ta_states.setdefault(key, BarTAState())
    state.push(bar)

    closes = list(state.close_buf)
    highs  = list(state.high_buf)
    lows   = list(state.low_buf)
    vols   = list(state.volume_buf)

    # RSI(14)
    if len(closes) >= 15:
        rsi = compute_rsi([decimal.Decimal(str(c)) for c in closes], 14)
        state.rsi_14 = float(rsi) if rsi is not None else None

    # Bollinger Bands(20)
    if len(closes) >= 20:
        bb = compute_bollinger_bands(
            [decimal.Decimal(str(c)) for c in closes], window=20, num_std=2.0
        )
        if bb is not None:
            state.bb_position = bb.pct_b
            state.bb_width    = bb.width
            # price_sma_20_deviation = (close - mid) / mid
            if float(bb.mid) > 0:
                state.price_sma_20_deviation = (
                    float(closes[-1]) - float(bb.mid)
                ) / float(bb.mid)

    # Stochastic(14,3)
    if len(closes) >= 16:
        result = compute_stochastic(
            [decimal.Decimal(str(h)) for h in highs],
            [decimal.Decimal(str(l)) for l in lows],
            [decimal.Decimal(str(c)) for c in closes],
            k_period=14, d_period=3,
        )
        if result is not None:
            state.stoch_k, state.stoch_d = result

    # volume_sma_ratio
    if len(vols) >= 2:
        mean_vol = sum(vols[:-1]) / len(vols[:-1])
        if mean_vol > 0:
            state.volume_sma_ratio = vols[-1] / mean_vol

    # atr_14 — reuse BarVolatilityState.last_atr якщо вже є
    vol_state = self._bar_volatility_states.get(key)
    if vol_state is not None and vol_state.atr_ready and vol_state.last_atr is not None:
        atr_val = float(vol_state.last_atr)
        state.atr_14 = atr_val
        state.atr_buf.append(atr_val)
        if len(state.atr_buf) >= 5:
            mean_atr = sum(state.atr_buf) / len(state.atr_buf)
            state.atr_ratio = atr_val / mean_atr if mean_atr > 0 else None

    return state.as_feature_dict()
```

**3c. `on_bar_closed()`** (~line 640, перед викликом `_calculate_and_emit_features_for_tf()`):
```python
# [NEW] Compute native TA features for alpha_search ta_ensemble
ta_features = self._update_bar_ta_state(symbol, tf_sec, bar_data_obj)
bar_tick.update(ta_features)  # inject: rsi_14, bb_position, etc.
```

---

## Порядок виконання

1. **`indicators.py`** — додати `compute_stochastic()` (нова функція, нічого не ламає)
2. **`types.py`** — додати `BarTAState` dataclass (нова сутність, нічого не ламає)
3. **`feature_engineering.py`** — `__init__` + `_update_bar_ta_state()` + hook в `on_bar_closed()`

---

## Що НЕ змінюємо

- `_calculate_and_emit_features_for_tf()` — aug_keys passthrough вже підхопить нові ключі
- MeanReversion internal fields (`bb.pct_b`, `state.rsi`) — вони коректні для MR власного використання
- `mean_reversion_logger.py` — барний лог MR використовує свої поля, не залежить від TA state
- `bars_60s.tsv` / `bars_180s.tsv` — можна видалити вручну, не програмне питання
- alpha_search models — вони вже правильно оголошують required features

---

## Критичні файли

| Файл | Зміна | Рядки |
|---|---|---|
| `apps/reference/domains/feature_engineering/indicators.py` | ADD `compute_stochastic()` | ~243 |
| `apps/reference/domains/feature_engineering/types.py` | ADD `BarTAState` dataclass | ~170 |
| `apps/reference/domains/feature_engineering/feature_engineering.py` | `__init__` + нов. метод + hook | ~152, ~640 |
| `apps/reference/domains/feature_engineering/__init__.py` | EXPORT `compute_stochastic`, `BarTAState` | existing exports |

---

## Верифікація

### Unit tests (існуючі та нові)
```bash
# Стохастик
pytest tests/ -k "stochastic" -v

# Feature engineering bar flow
pytest tests/ -k "test_bar" -v

# alpha_search ta_ensemble
pytest apps/reference/domains/alpha_search/tests/test_backtest_plugin_integration.py -v
```

### Перевірка в логах після запуску
```
# БУЛО (до фіксу):
WARNING | Skipping ta_ensemble: missing required features=['bb_position', ...]

# БУДЕ (після фіксу, при отриманні bar evt tf_sec=300):
DEBUG | [DOGEUSDT] ta_ensemble: score=0.2341 conf=0.71 thr=0.18
```

### Перевірка alpha_input_v1.jsonl
```json
// Запис ПІСЛЯ фіксу (tf_sec=300) матиме:
{
  "features": {
    "obi": "0.39",
    "rsi_14": "48.40",       ← нова TA фіча
    "bb_position": "0.23",   ← нова TA фіча
    "bb_width": "0.015",     ← нова TA фіча
    "stoch_k": "34.5",       ← нова TA фіча
    ...
  }
}
```

### Warmup очікування
Перші ~20 барів (tf_sec=300 → ~100 хвилин реального часу) bb_position/rsi_14 будуть `None`
і не з'являться у фічах — це нормально, warming up.
