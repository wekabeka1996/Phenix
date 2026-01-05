# Shadow Run System - Аналіз та Рекомендації

## Огляд

Цей документ містить результати **Shadow Run** аналізу - симуляції торгової системи на історичних feature логах для тестування різних конфігурацій без реального ризику.

---

## 1. Інструменти Shadow Run

Створено набір інструментів у `apps/research/shadow_run/`:

| Файл | Призначення |
|------|-------------|
| `shadow_engine.py` | Core engine для прогону features через signal scoring |
| `compare_proposal.py` | Порівняння поточної vs пропонованої конфігурації |
| `analyze_features.py` | Глибокий аналіз розподілу сигналів |
| `crash_scenarios.py` | Тестування на синтетичних crash сценаріях |

### Швидкий старт

```bash
# Базове порівняння конфігурацій
python3 -m apps.research.shadow_run.compare_proposal

# Глибокий аналіз features
python3 -m apps.research.shadow_run.analyze_features

# Тестування на crashах
python3 -m apps.research.shadow_run.crash_scenarios
```

---

## 2. Результати аналізу

### 2.1. Проблема з поточними логами

Feature логи за період **не містять реальних crash подій**:
- Min delta_price: -0.17% (BTC), -0.67% (DOGE)
- Практично всі сигнали позитивні (Long)
- Жодних Short сигналів при threshold=0.10

### 2.2. Симуляція Crash Сценаріїв

При **синтетичному краші** (падіння -2% з позитивним OBI +0.80):

| Конфігурація | OBI | delta_price | Score | Сигнал |
|--------------|-----|-------------|-------|--------|
| **CURRENT** | 0.10 | 0.05 | +0.306 | 🔴 LONG |
| **PROPOSED** | 0.03 | 0.15 | +0.150 | 🟡 LONG |
| **AGGRESSIVE** | 0.02 | 0.25 | +0.042 | ✅ FLAT |

### 2.3. Висновок

Пропозиція з `SHORT_TREND_ANALYSIS_AND_PROPOSALS.md` (OBI=0.03, delta_price=0.15) **недостатня** для повного захисту від крашів.

---

## 3. Оновлені Рекомендації

### 3.1. Ваги стратегії Aurora

**Рекомендовані зміни в `aurora.yaml`:**

```yaml
# BTCUSDT
BTCUSDT:
  weights:
    obi: 0.02          # Було: 0.10, Пропонувалось: 0.03
    delta_price: 0.25  # Було: 0.05, Пропонувалось: 0.15
    tfi: 0.10
    ema_bias: 0.15
    volume_spike: 0.10
    volatility_state: 0.10
    depth_imbalance: 0.08
    macro_sync: 0.10
    large_trade_imbalance: 0.08
    liquidity_kappa: 0.02

# Аналогічно для інших активів
```

### 3.2. Flash Crash Guard

**Оновлена пропозиція на основі даних:**

| Актив | P1 (перцентиль) | Рекомендований поріг |
|-------|-----------------|----------------------|
| BTC | -0.0365% | **-0.04%** |
| ETH | -0.0482% | **-0.05%** |
| SOL | -0.0539% | **-0.06%** |
| DOGE | -0.0913% | **-0.10%** |
| XRP | -0.0706% | **-0.08%** |

Замість єдиного `-0.35%` для всіх, використати **адаптивний поріг** per-asset.

### 3.3. Реалізація Flash Crash Guard

```python
# В decision_making.py, після розрахунку signal_score

# Per-asset Flash Crash Guard thresholds
CRASH_THRESHOLDS = {
    "BTCUSDT": Decimal("-0.0004"),     # -0.04%
    "ETHUSDT": Decimal("-0.0005"),     # -0.05%
    "SOLUSDT": Decimal("-0.0006"),     # -0.06%
    "DOGEUSDT": Decimal("-0.0010"),    # -0.10%
    "XRPUSDT": Decimal("-0.0008"),     # -0.08%
    "DEFAULT": Decimal("-0.0005"),     # -0.05% for unknown
}

crash_threshold = CRASH_THRESHOLDS.get(symbol, CRASH_THRESHOLDS["DEFAULT"])

if signal_score > 0:  # Only check for potential LONGs
    dp_raw = ctx.trend.delta_price
    price = ctx.price
    dp_pct = dp_raw / price if price > 0 else Decimal("0")
    
    if dp_pct < crash_threshold:
        reject_reason = f"Flash Crash Guard: dp={dp_pct:.4%} < threshold={crash_threshold:.4%}"
        self.logger.warning(f"[{symbol}] CRASH_PROTECTION: {reject_reason}")
        
        # Block Long entry
        signal_score = Decimal("-0.01")  # Force to neutral/negative
        
        self.dlog.write("DECISION_SKIP", rid, {
            "symbol": symbol,
            "reason": "FLASH_CRASH_GUARD",
            "dp_pct": str(dp_pct),
            "threshold": str(crash_threshold),
        })
        return  # Or continue to potentially short
```

---

## 4. Використання Shadow Run для майбутніх змін

### 4.1. Тестування нових конфігурацій

```python
from apps.research.shadow_run import ShadowEngine

engine = ShadowEngine(
    feature_logs_dir="logs/features",
    symbols=["ETHUSDT", "BTCUSDT"],
)

# Тест нової конфігурації
engine.set_weight_override("delta_price", 0.25)
engine.set_weight_override("obi", 0.02)
engine.set_threshold_override(0.10)

results = engine.run()
for symbol, res in results.items():
    res.print_summary()
```

### 4.2. Grid Search для оптимізації

```python
from apps.research.shadow_run import ShadowEngine
from decimal import Decimal
import itertools

engine = ShadowEngine(feature_logs_dir="logs/features")

# Parameter grid
obi_values = [0.02, 0.03, 0.05, 0.10]
dp_values = [0.15, 0.20, 0.25, 0.30]

best_pnl = Decimal("-9999")
best_config = None

for obi, dp in itertools.product(obi_values, dp_values):
    results = engine.run_with_overrides({"obi": obi, "delta_price": dp})
    total_pnl = sum(r.total_pnl for r in results.values())
    
    if total_pnl > best_pnl:
        best_pnl = total_pnl
        best_config = {"obi": obi, "delta_price": dp}

print(f"Best config: {best_config} with P&L: ${float(best_pnl):.2f}")
```

### 4.3. A/B тестування

```python
engine.compare_configs(
    {"obi": 0.10, "delta_price": 0.05},  # Current
    {"obi": 0.02, "delta_price": 0.25},  # Proposed
    label_a="Production",
    label_b="New Alpha",
)
```

---

## 5. Обмеження та Застереження

1. **Історичні дані не репрезентативні** - відсутні реальні crash події
2. **Synthetic crashes** - апроксимація, не реальна динаміка ордербуку
3. **Timing** - shadow run не враховує затримки виконання
4. **Liquidity** - не моделюється вплив власних ордерів на ринок

### Рекомендація

Перед production deployment:
1. Запустити **paper trading** з новими вагами мінімум 1 тиждень
2. Зберегти feature logs під час реальних market drops
3. Повторити shadow run на реальних crash даних

---

## 6. Наступні кроки

- [ ] Імплементувати Flash Crash Guard у `decision_making.py`
- [ ] Оновити ваги в `aurora.yaml` до агресивних значень
- [ ] Налаштувати збір feature logs з timestamp для backtesting
- [ ] Створити автоматизований CI pipeline для shadow run на кожну зміну configs

---

*Документ згенеровано: 2026-01-03*
*Shadow Run Engine v1.0*
