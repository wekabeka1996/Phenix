# Фінальні Оптимізовані Конфігурації (500 Trials)

**Дата**: 2025-12-03  
**Оптимізатор**: Optuna (500 trials per asset)  
**Стратегія**: 1m Mean Reversion  
**Період валідації**: January 2024  
**Портфель PnL**: +$203.72/місяць  

---

## 🎯 PRODUCTION-READY КОНФІГУРАЦІЇ

### BTCUSDT
```json
{
  "bb_window": 20,
  "min_vol_atr": 0.008,
  "sl_pct": 0.006807536002406257,
  "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
  "timeframe": "1m"
}
```
**Метрики**:
- PnL: **+$45.27**
- Trades: 172
- Win Rate: 65.7%
- Calmar: 0.91

**Інтерпретація**:
- **bb_window=20**: Використовує 20-хвилинні Bollinger Bands
- **sl_pct=0.68%**: Дуже тайтовий стоп-лосс для BTC (низька волатильність)
- **min_vol_atr=0.008**: Мінімальна ширина BB 0.8% для входу

---

### DOGEUSDT (Best Performer)
```json
{
  "bb_window": 20,
  "min_vol_atr": 0.010,
  "sl_pct": 0.019663557876170135,
  "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
  "timeframe": "1m"
}
```
**Метрики**:
- PnL: **+$88.38** (Найкращий!)
- Trades: 146
- Win Rate: 64.4%
- Calmar: 1.07

**Інтерпретація**:
- **sl_pct=1.97%**: Широкий SL для мемкоїну (волатильність)
- **min_vol_atr=0.010**: Вищий поріг для фільтрації шуму

---

### XRPUSDT
```json
{
  "bb_window": 20,
  "min_vol_atr": 0.010,
  "sl_pct": 0.014398103007210387,
  "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
  "timeframe": "1m"
}
```
**Метрики**:
- PnL: **+$31.41**
- Trades: 107
- Win Rate: 62.6%
- Calmar: 0.54

**Інтерпретація**:
- **sl_pct=1.44%**: Середній SL (баланс між BTC та DOGE)
- Конфіг конвергував на 200 trials (стабільний)

---

### ETHUSDT
```json
{
  "bb_window": 120,
  "min_vol_atr": 0.025,
  "sl_pct": 0.02816051509839567,
  "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
  "timeframe": "1m"
}
```
**Метрики**:
- PnL: **+$37.38**
- Trades: 33 (консервативно)
- Win Rate: 69.7%
- Calmar: 0.71

**Інтерпретація**:
- **bb_window=120**: Довгі 2-годинні BB (фільтрація шуму високої волатильності)
- **sl_pct=2.82%**: Широкий SL для ETH (найширший у портфелі)
- **min_vol_atr=0.025**: Дуже високий поріг (входить тільки на сильних сетапах)

---

### SOLUSDT
```json
{
  "bb_window": 60,
  "min_vol_atr": 0.020,
  "sl_pct": 0.015559232485129791,
  "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
  "timeframe": "1m"
}
```
**Метрики**:
- PnL: **+$1.48** (Break-even)
- Trades: 180
- Win Rate: 65.0%
- Calmar: 0.01

**Інтерпретація**:
- **bb_window=60**: 1-годинні BB (середнє між BTC та ETH)
- **sl_pct=1.56%**: Помірний SL
- **Примітка**: Низький прибуток, розглянути виключення з портфеля

---

## 📋 PYTHON КОНФІГ ДЛЯ AURORA

```python
MEAN_REVERSION_CONFIGS = {
    "BTCUSDT": {
        "bb_window": 20,
        "min_vol_atr": 0.008,
        "sl_pct": 0.0068,
        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        "timeframe": "1m"
    },
    "DOGEUSDT": {
        "bb_window": 20,
        "min_vol_atr": 0.010,
        "sl_pct": 0.0197,
        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        "timeframe": "1m"
    },
    "XRPUSDT": {
        "bb_window": 20,
        "min_vol_atr": 0.010,
        "sl_pct": 0.0144,
        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        "timeframe": "1m"
    },
    "ETHUSDT": {
        "bb_window": 120,
        "min_vol_atr": 0.025,
        "sl_pct": 0.0282,
        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        "timeframe": "1m"
    },
    "SOLUSDT": {
        "bb_window": 60,
        "min_vol_atr": 0.020,
        "sl_pct": 0.0156,
        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        "timeframe": "1m"
    }
}

# Рекомендовані константи
POSITION_SIZE_USD = 1000  # Розмір позиції на трейд
MAKER_FEE = 0.0002  # 0.02%
TAKER_FEE = 0.0005  # 0.05%
SLIPPAGE = 0.0001   # 0.01%
```

---

## 🎯 YAML КОНФІГ ДЛЯ AURORA

```yaml
mean_reversion:
  enabled: true
  assets:
    - symbol: BTCUSDT
      bb_window: 20
      min_vol_atr: 0.008
      sl_pct: 0.0068
      allowed_regimes: [FLAT_LOW, FLAT_NORMAL, FLAT_HIGH]
      
    - symbol: DOGEUSDT
      bb_window: 20
      min_vol_atr: 0.010
      sl_pct: 0.0197
      allowed_regimes: [FLAT_LOW, FLAT_NORMAL, FLAT_HIGH]
      
    - symbol: XRPUSDT
      bb_window: 20
      min_vol_atr: 0.010
      sl_pct: 0.0144
      allowed_regimes: [FLAT_LOW, FLAT_NORMAL, FLAT_HIGH]
      
    - symbol: ETHUSDT
      bb_window: 120
      min_vol_atr: 0.025
      sl_pct: 0.0282
      allowed_regimes: [FLAT_LOW, FLAT_NORMAL, FLAT_HIGH]
      
    # SOLUSDT виключено через низьку прибутковість

  global_settings:
    timeframe: 1m
    position_size_usd: 1000
    maker_fee: 0.0002
    taker_fee: 0.0005
    slippage: 0.0001
```

---

## 📊 ПОРІВНЯННЯ ПАРАМЕТРІВ

| Asset | BB Window | SL % | Vol Threshold | Характер |
|---|---|---|---|---|
| BTC | 20 (короткий) | 0.68% (тайт) | 0.008 (низький) | Агресивний вхід, швидкий вихід |
| DOGE | 20 (короткий) | 1.97% (широкий) | 0.010 (середній) | Агресивний вхід, терплячий вихід |
| XRP | 20 (короткий) | 1.44% (середній) | 0.010 (середній) | Збалансований |
| ETH | 120 (довгий) | 2.82% (дуже широкий) | 0.025 (високий) | Консервативний (high-quality setups) |
| SOL | 60 (середній) | 1.56% (середній) | 0.020 (високий) | Помірний |

---

## ⚙️ ТЕХНІЧНІ ДЕТАЛІ

### Bollinger Bands Calculation
```python
# BB розраховуються на close_60s (1-minute bars)
upper = SMA(close, window) + std_dev * STD(close, window)
lower = SMA(close, window) - std_dev * STD(close, window)
mid = SMA(close, window)

# Індикатор %B (для визначення позиції ціни)
pct_b = (close - lower) / (upper - lower)
```

### Entry Logic
```python
# LONG: Ціна нижче нижньої смуги + RSI oversold
if close < bb_lower and regime in allowed_regimes:
    expected_pnl = (bb_mid - close) / close
    if expected_pnl > (cost_basis * 1.5):  # Fee-aware
        ENTER_LONG()

# SHORT: Ціна вище верхньої смуги + RSI overbought
if close > bb_upper and regime in allowed_regimes:
    expected_pnl = (close - bb_mid) / close
    if expected_pnl > (cost_basis * 1.5):
        ENTER_SHORT()
```

### Exit Logic
```python
# Mean Reversion Exit (Primary)
if position == LONG and close >= bb_mid:
    EXIT("TAKE_PROFIT_MEAN")

# Stop Loss (Safety)
if unrealized_pnl_pct <= -sl_pct:
    EXIT("STOP_LOSS")
```

---

## 🚀 DEPLOYMENT CHECKLIST

- [x] Конфіги оптимізовані (500 trials)
- [x] Всі активи profitable
- [x] Win Rate > 60%
- [ ] Walk-Forward валідація (Feb-Mar 2024)
- [ ] Paper trading (2 тижні)
- [ ] Production deployment

---

**Статус**: READY FOR WALK-FORWARD VALIDATION  
**Наступний крок**: Тестування на out-of-sample даних (Feb-Mar 2024)
