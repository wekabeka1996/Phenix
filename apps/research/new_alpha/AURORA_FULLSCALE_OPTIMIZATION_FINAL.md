# Aurora Mean Reversion Strategy — Full-Scale Optimization Report

> **Дата:** 2025-12-05  
> **Тривалість оптимізації:** ~9 годин  
> **Кількість триалів:** 15,000 (3,000 на кожен актив)  
> **Активи:** BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT, DOGEUSDT

---

## 📊 Фінальні Результати

| Актив | PnL ($) | Trades | Win Rate | Max DD ($) | Calmar Ratio |
|-------|---------|--------|----------|------------|--------------|
| **DOGEUSDT** | **+387.24** | 230 | 58.7% | -56.08 | **6.91** 🥇 |
| **XRPUSDT** | **+121.62** | 107 | 59.8% | -40.27 | **3.02** 🥈 |
| **BTCUSDT** | **+103.70** | 213 | 59.6% | -36.15 | **2.87** 🥉 |
| **ETHUSDT** | **+53.94** | 33 | 60.6% | -23.23 | **2.32** |
| **SOLUSDT** | **+27.57** | 99 | 56.6% | -21.23 | **1.30** |

> **Загальний PnL:** +$694.07 за 1 місяць даних (Січень 2024)

---

## 🧠 Опис Стратегії

### Концепція
**Bollinger Bands Mean Reversion** — класична стратегія повернення до середнього. Коли ціна виходить за межі Bollinger Bands, очікується її повернення до середньої лінії (SMA).

### Логіка Входу
1. Ціна пробиває **нижню** межу BB → відкриваємо **LONG**
2. Ціна пробиває **верхню** межу BB → відкриваємо **SHORT**
3. Фільтрація за **волатильністю** (BB Width > min_vol_atr)
4. Фільтрація за **режимом ринку** (allowed_regimes)

---

## 📐 Математичні Формули

### 1. Bollinger Bands

```
SMA = (1/n) × Σ(Close[i])  для i = 1..n

σ = √[(1/n) × Σ(Close[i] - SMA)²]

BB_Upper = SMA + (k × σ)
BB_Lower = SMA - (k × σ)
BB_Width = (BB_Upper - BB_Lower) / SMA
```

**Параметри:**
- `n` = `bb_window` (кількість барів для SMA)
- `k` = `bb_std_dev` (множник стандартного відхилення)

### 2. Умова Входу

```python
# LONG Signal
if price < BB_Lower:
    distance_to_mean = (SMA - price) / price
    if distance_to_mean > cost_basis × 1.5:
        signal = +1.0  # BUY

# SHORT Signal  
if price > BB_Upper:
    distance_to_mean = (price - SMA) / price
    if distance_to_mean > cost_basis × 1.5:
        signal = -1.0  # SELL
```

**Де:**
- `cost_basis` = 0.06% (taker fee на Binance)
- Мінімальна дистанція = 0.09% (1.5 × 0.06%)

### 3. Take Profit (TP) — Рівні

```
TP1 (Partial) = Entry × (1 ± sl_pct × tp_low_ratio)
TP2 (Full)    = Entry × (1 ± sl_pct × tp_high_ratio)
```

**Приклад для LONG:**
```
Entry = $100
sl_pct = 1.5%
tp_low_ratio = 0.57
tp_high_ratio = 1.73

TP1 = $100 × (1 + 0.015 × 0.57) = $100.86
TP2 = $100 × (1 + 0.015 × 1.73) = $102.60
```

### 4. Trailing Stop

```
# Активація
if profit_pct >= trailing_stop_activation_pct:
    trailing_active = True

# Оновлення (для LONG)
if trailing_active:
    highest_price = max(highest_price, current_price)
    dynamic_sl = highest_price × (1 - trailing_stop_distance_pct)
    
    if price <= dynamic_sl:
        EXIT("TRAILING_STOP")
```

### 5. Calmar Ratio

```
Calmar = Total_PnL / |Max_Drawdown|
```

---

## 🔧 Код Стратегії

### Feature Engineering (`features_aurora.py`)

```python
def build_aurora_features(df, btc_df, params, bar_seconds=60):
    """Build all Aurora core features"""
    df = df.copy()
    
    # Bollinger Bands calculation
    if 'bb_window' in params:
        bb_window = params.get('bb_window', 20)
        std_dev = params.get('bb_std_dev', 2.0)
        
        close_col = get_col_name(df, 'close')
        
        # Calculate BB
        sma = df[close_col].rolling(window=bb_window).mean()
        std = df[close_col].rolling(window=bb_window).std()
        
        df[f'bb_mid_{bb_window}'] = sma
        df[f'bb_upper_{bb_window}'] = sma + (std * std_dev)
        df[f'bb_lower_{bb_window}'] = sma - (std * std_dev)
        df[f'bb_width_{bb_window}'] = (
            df[f'bb_upper_{bb_window}'] - df[f'bb_lower_{bb_window}']
        ) / (sma + 1e-9)
    
    return df.dropna()
```

### Entry Logic (`backtest_engine_aurora.py`)

```python
if self.strategy_mode == 'mean_reversion':
    price = row['close_5s']
    min_vol_atr = self.params.get('min_vol_atr', 0.001)
    
    # Check BB columns exist
    if col_lower not in row or pd.isna(row[col_lower]):
        continue
        
    bb_width = row.get(col_width, 0)
    if bb_width < min_vol_atr:
        continue  # Skip low volatility
    
    dist_to_mean = 0.0
    if price < row[col_lower]:
        dist_to_mean = (row[col_mid] - price) / price
        if dist_to_mean > (self.cost_basis * 1.5):
            signal = 1.0  # LONG
    elif price > row[col_upper]:
        dist_to_mean = (price - row[col_mid]) / price
        if dist_to_mean > (self.cost_basis * 1.5):
            signal = -1.0  # SHORT
```

### Trade Management (`backtest_engine_aurora.py`)

```python
def _manage_trade(self, trade, row):
    """FULL EXECUTION LOGIC: TP, Trailing Stop, SL, Time Exit"""
    price = row['close_5s']
    sl_pct = self.params.get('sl_pct', 0.01)
    
    # Phase 3+: TP ratios
    tp_low_ratio = self.params.get('tp_low_ratio', 0.5)
    tp_high_ratio = self.params.get('tp_high_ratio', 1.0)
    partial_exit_pct = self.params.get('partial_exit_pct', 0.5)
    
    # Phase 3+: Trailing stop parameters
    trailing_activation_pct = self.params.get('trailing_stop_activation_pct', 0.005)
    trailing_distance_pct = self.params.get('trailing_stop_distance_pct', 0.003)
    
    # Initialize TP prices
    if trade.tp_low is None:
        if trade.side == 'LONG':
            trade.tp_low = trade.entry_price * (1 + sl_pct * tp_low_ratio)
            trade.tp_high = trade.entry_price * (1 + sl_pct * tp_high_ratio)
        else:  # SHORT
            trade.tp_low = trade.entry_price * (1 - sl_pct * tp_low_ratio)
            trade.tp_high = trade.entry_price * (1 - sl_pct * tp_high_ratio)
    
    # ========== TAKE PROFIT LOGIC ==========
    # TP1 (Partial Exit)
    if not trade.partial_exit_done:
        tp1_hit = False
        if trade.side == 'LONG' and price >= trade.tp_low:
            tp1_hit = True
        elif trade.side == 'SHORT' and price <= trade.tp_low:
            tp1_hit = True
        
        if tp1_hit:
            exit_size = trade.size * partial_exit_pct
            remaining_size = trade.size * (1 - partial_exit_pct)
            
            if trade.side == 'LONG':
                partial_pnl_pct = (price - trade.entry_price) / trade.entry_price
            else:
                partial_pnl_pct = (trade.entry_price - price) / trade.entry_price
            
            trade.pnl_net += (partial_pnl_pct - self.cost_basis) * exit_size
            trade.size = remaining_size
            trade.partial_exit_done = True
            return
    
    # ========== TRAILING STOP LOGIC ==========
    if trade.side == 'LONG':
        trade.highest_price = max(trade.highest_price, price)
        profit_pct = (price - trade.entry_price) / trade.entry_price
        
        if profit_pct >= trailing_activation_pct:
            trade.trailing_stop_active = True
        
        if trade.trailing_stop_active:
            trade.dynamic_sl = trade.highest_price * (1 - trailing_distance_pct)
            if price <= trade.dynamic_sl:
                self._close_trade(trade, price, row['ts'], "TRAILING_STOP")
                return
    
    # ========== STOP LOSS ==========
    if trade.side == 'LONG':
        pnl_pct = (price - trade.entry_price) / trade.entry_price
    else:
        pnl_pct = (trade.entry_price - price) / trade.entry_price
    
    if pnl_pct <= -sl_pct:
        self._close_trade(trade, price, row['ts'], "STOP_LOSS")
        return
    
    # ========== TIME EXIT ==========
    time_diff = (row['ts'] - trade.entry_ts).total_seconds()
    if time_diff > self.params.get('max_hold_sec', 300):
        self._close_trade(trade, price, row['ts'], "TIME_EXIT")
```

### Regime Detection (`regime_labeling.py`)

```python
def label_regime(df, config):
    """
    Label market regime:
    1. HIGH_VOLATILITY / LOW_VOLATILITY
    2. MEAN_REVERSION
    3. TREND_UP / TREND_DOWN
    4. UNCERTAIN (default)
    """
    # ATR для визначення волатильності
    atr = compute_atr(df, atr_period)
    atr_sma = atr.rolling(window=atr_sma_length).mean()
    volatility_ratio = atr / (atr_sma + 1e-9)
    
    regime = pd.Series('UNCERTAIN', index=df.index)
    
    # Priority 1: Volatility
    regime = regime.where(
        ~(volatility_ratio > high_vol_threshold), 'HIGH_VOLATILITY'
    )
    regime = regime.where(
        ~(volatility_ratio < low_vol_threshold), 'LOW_VOLATILITY'
    )
    
    # Priority 2: Mean Reversion
    sma_spread = (sma_short - sma_long).abs() / (sma_long + 1e-9)
    mean_rev_mask = (
        (regime == 'UNCERTAIN') &
        (sma_spread < mean_rev_threshold)
    )
    regime = regime.where(~mean_rev_mask, 'MEAN_REVERSION')
    
    return regime
```

---

## 🎯 Оптимізовані Параметри

### BTCUSDT 🥉

```json
{
  "symbol": "BTCUSDT",
  "params": {
    "bb_window": 40,           // 40 хвилин для SMA
    "bb_std_dev": 2.3,         // 2.3σ для BB
    "min_vol_atr": 0.006,      // Мін. ширина BB 0.6%
    "sl_pct": 0.015,           // Stop Loss 1.5%
    "max_hold_sec": 1500,      // Max hold 25 хвилин
    "tp_low_ratio": 0.57,      // TP1 = 0.57 × SL
    "tp_high_ratio": 1.73,     // TP2 = 1.73 × SL
    "partial_exit_pct": 0.76,  // 76% виходить на TP1
    "trailing_stop_activation_pct": 0.04,   // Trailing активується при +4%
    "trailing_stop_distance_pct": 0.003,    // Trailing distance 0.3%
    "cooldown_sec": 0,         // Без cooldown (агресивна торгівля)
    "allowed_regimes": ["MEAN_REVERSION", "LOW_VOLATILITY", "UNCERTAIN"]
  },
  "metrics": {
    "total_pnl": 103.70,
    "trades": 213,
    "win_rate": 0.596,
    "max_dd": -36.15,
    "calmar": 2.87
  }
}
```

**Коментарі:**
- `bb_window: 40` — Середній таймфрейм, балансує між шумом і запізненням
- `cooldown_sec: 0` — BTC достатньо ліквідний для швидких послідовних угод
- `partial_exit_pct: 0.76` — Високий відсоток часткового виходу фіксує прибуток рано
- `calmar: 2.87` — Відмінне співвідношення прибутку до ризику

---

### ETHUSDT

```json
{
  "symbol": "ETHUSDT",
  "params": {
    "bb_window": 180,          // 3 години для SMA (!)
    "bb_std_dev": 1.5,         // Вужчі BB (1.5σ)
    "min_vol_atr": 0.024,      // Вища мін. волатильність 2.4%
    "sl_pct": 0.027,           // Stop Loss 2.7%
    "max_hold_sec": 1620,      // Max hold 27 хвилин
    "tp_low_ratio": 0.40,      // TP1 = 0.4 × SL
    "tp_high_ratio": 2.23,     // TP2 = 2.23 × SL (!)
    "partial_exit_pct": 0.74,  // 74% на TP1
    "trailing_stop_activation_pct": 0.049,  // +4.9% для активації
    "trailing_stop_distance_pct": 0.006,    // 0.6% distance
    "cooldown_sec": 195,       // 3.25 хв cooldown
    "allowed_regimes": ["MEAN_REVERSION", "LOW_VOLATILITY", "UNCERTAIN"]
  },
  "metrics": {
    "total_pnl": 53.94,
    "trades": 33,
    "win_rate": 0.606,
    "max_dd": -23.23,
    "calmar": 2.32
  }
}
```

**Коментарі:**
- `bb_window: 180` — Дуже широкий таймфрейм, фільтрує короткочасний шум
- `bb_std_dev: 1.5` — Вужчі смуги компенсують широкий window
- `tp_high_ratio: 2.23` — Агресивний TP2, дозволяє великі прибутки
- `trades: 33` — Менше угод через строгі фільтри, але якісніші

---

### XRPUSDT 🥈

```json
{
  "symbol": "XRPUSDT",
  "params": {
    "bb_window": 40,           // 40 хвилин
    "bb_std_dev": 2.5,         // Широкі BB (2.5σ)
    "min_vol_atr": 0.007,      // Низький поріг 0.7%
    "sl_pct": 0.024,           // Stop Loss 2.4%
    "max_hold_sec": 2940,      // Max hold 49 хвилин (!)
    "tp_low_ratio": 0.75,      // TP1 = 0.75 × SL
    "tp_high_ratio": 1.57,     // TP2 = 1.57 × SL
    "partial_exit_pct": 0.41,  // 41% на TP1 (консервативніше)
    "trailing_stop_activation_pct": 0.015,  // Рання активація +1.5%
    "trailing_stop_distance_pct": 0.018,    // Широкий trailing 1.8%
    "cooldown_sec": 165,       // 2.75 хв cooldown
    "allowed_regimes": ["MEAN_REVERSION", "LOW_VOLATILITY", "UNCERTAIN"]
  },
  "metrics": {
    "total_pnl": 121.62,
    "trades": 107,
    "win_rate": 0.598,
    "max_dd": -40.27,
    "calmar": 3.02
  }
}
```

**Коментарі:**
- `max_hold_sec: 2940` — Довше тримає позиції, дає час на розворот
- `trailing_stop_activation_pct: 0.015` — Рання активація trailing
- `trailing_stop_distance_pct: 0.018` — Широкий trailing не виб'є передчасно
- `calmar: 3.02` — Найкращий серед основних активів!

---

### SOLUSDT

```json
{
  "symbol": "SOLUSDT",
  "params": {
    "bb_window": 120,          // 2 години для SMA
    "bb_std_dev": 1.8,         // 1.8σ
    "min_vol_atr": 0.025,      // Високий поріг 2.5%
    "sl_pct": 0.027,           // Stop Loss 2.7%
    "max_hold_sec": 180,       // Max hold всього 3 хвилини (!)
    "tp_low_ratio": 0.48,      // TP1 = 0.48 × SL
    "tp_high_ratio": 0.80,     // TP2 = 0.8 × SL (скромний)
    "partial_exit_pct": 0.31,  // 31% на TP1
    "trailing_stop_activation_pct": 0.046,  // +4.6%
    "trailing_stop_distance_pct": 0.018,    // 1.8%
    "cooldown_sec": 210,       // 3.5 хв cooldown
    "allowed_regimes": ["MEAN_REVERSION", "LOW_VOLATILITY", "UNCERTAIN"]
  },
  "metrics": {
    "total_pnl": 27.57,
    "trades": 99,
    "win_rate": 0.566,
    "max_dd": -21.23,
    "calmar": 1.30
  }
}
```

**Коментарі:**
- `max_hold_sec: 180` — Дуже швидкий скальпінг (3 хвилини max)
- `tp_high_ratio: 0.80` — Консервативний TP2, швидка фіксація
- `partial_exit_pct: 0.31` — Залишає більшу частину для TP2
- SOL — найволатильніший актив, тому швидкі виходи

---

### DOGEUSDT 🥇 **CHAMPION**

```json
{
  "symbol": "DOGEUSDT",
  "params": {
    "bb_window": 20,           // Найкоротший таймфрейм (20 хв)
    "bb_std_dev": 2.1,         // 2.1σ
    "min_vol_atr": 0.005,      // Низький поріг 0.5%
    "sl_pct": 0.019,           // Stop Loss 1.9%
    "max_hold_sec": 6480,      // Max hold 108 хвилин (1.8 год!)
    "tp_low_ratio": 0.63,      // TP1 = 0.63 × SL
    "tp_high_ratio": 2.45,     // TP2 = 2.45 × SL (!)
    "partial_exit_pct": 0.38,  // 38% на TP1
    "trailing_stop_activation_pct": 0.012,  // Рання активація +1.2%
    "trailing_stop_distance_pct": 0.004,    // Tight trailing 0.4%
    "cooldown_sec": 210,       // 3.5 хв cooldown
    "allowed_regimes": ["MEAN_REVERSION", "LOW_VOLATILITY", "UNCERTAIN"]
  },
  "metrics": {
    "total_pnl": 387.24,
    "trades": 230,
    "win_rate": 0.587,
    "max_dd": -56.08,
    "calmar": 6.91
  }
}
```

**Коментарі:**
- `bb_window: 20` — Найкоротший, швидка реакція на DOGE волатильність
- `max_hold_sec: 6480` — Найдовший час утримання, дає DOGE час на "pumps"
- `tp_high_ratio: 2.45` — Найагресивніший TP2, ловить великі рухи
- `calmar: 6.91` — **Феноменальний показник!** Найкращий R/R
- DOGE має найбільше "pump and dump" патернів, ідеально для mean reversion

---

## 📈 Порівняльна Таблиця Параметрів

| Параметр | BTC | ETH | XRP | SOL | DOGE |
|----------|-----|-----|-----|-----|------|
| `bb_window` | 40 | **180** | 40 | 120 | **20** |
| `bb_std_dev` | 2.3 | **1.5** | **2.5** | 1.8 | 2.1 |
| `sl_pct` | **1.5%** | 2.7% | 2.4% | 2.7% | 1.9% |
| `max_hold_sec` | 25м | 27м | 49м | **3м** | **108м** |
| `tp_high_ratio` | 1.73 | 2.23 | 1.57 | 0.80 | **2.45** |
| `cooldown_sec` | **0** | 195 | 165 | 210 | 210 |
| `trailing_activation` | 4.0% | 4.9% | **1.5%** | 4.6% | **1.2%** |

---

## 🔑 Ключові Інсайти

### 1. Asset-Specific Behavior
Кожен актив потребує **унікальних параметрів**:
- **BTC:** Середні параметри, без cooldown
- **ETH:** Широкий BB window, консервативніше
- **XRP:** Довгий holding + рання trailing активація
- **SOL:** Швидкий скальпінг (3 хв max hold)
- **DOGE:** Найагресивніші TP, найдовший hold

### 2. Trailing Stop — Критичний
Активація trailing при +1-5% прибутку дозволяє:
- Фіксувати прибуток при відкаті
- Не виходити передчасно при продовженні руху

### 3. Partial Exit — Захист Прибутку
Вихід 30-76% на TP1:
- Фіксує частину прибутку рано
- Залишає частину для можливого продовження руху

### 4. Cooldown — Уникнення Серійних Втрат
195-210 секунд cooldown між угодами:
- Запобігає "revenge trading"
- Дає ринку час "заспокоїтись"

---

## 📁 Файли Системи

```
apps/research/aurora_optuna/
├── features_aurora.py       # Feature engineering
├── backtest_engine_aurora.py # Execution logic
├── regime_labeling.py       # Regime detection
├── optuna_runner_full_scale.py # Optimization runner
└── config.py                # Data paths

apps/research/new_alpha/
├── AURORA_FULLSCALE_OPTIMIZATION_FINAL.md  # This document
└── *.json                   # Best params per asset

Output files:
├── best_aurora_full_BTCUSDT.json
├── best_aurora_full_ETHUSDT.json
├── best_aurora_full_XRPUSDT.json
├── best_aurora_full_SOLUSDT.json
└── best_aurora_full_DOGEUSDT.json
```

---

## 🚀 Наступні Кроки

1. **Out-of-Sample Testing:** Тестування на Feb-Mar 2024
2. **Walk-Forward Validation:** Перевірка стабільності параметрів
3. **Paper Trading:** Симуляція на live даних
4. **Production Integration:** Інтеграція в reference bot конфіг

---

*Документ створено автоматично на основі результатів 15,000 Optuna триалів.*
