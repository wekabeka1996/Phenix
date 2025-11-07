# 06 Validation Criteria — Як Перевірити §19 Критерії

**Мета**: Формалізація критеріїв прийнятності та методологія走-forward валідації.

**Дата**: 3 листопада 2025 | **Статус**: ✅ DRAFT

---

## 🎯 §19: КРИТЕРІЙ ІНЖЕНЕРНОЇ ПРИЙНЯТНОСТІ

```
Sistema vážяется ІНЖЕНЕРНО ПРИЙНЯТНОЮ, якщо:

  J̄ > 0
  ∧ CVaR_0.95 ≤ 0.10
  ∧ MaxDD ≤ 0.20
  ∧ ρ_reject ≤ 0.08
  ∧ WHY_coverage = 100%
```

---

## 📊 МЕТРИКИ ДЕТАЛЬНО

### 1. **J̄ (Expected Value)**

**Формула**:
$$J̄ = \frac{1}{K} \sum_{k=1}^{K} J^{(k)}$$

де $J^{(k)}$ = expectancy (середній профіт per trade) на k-му fold валідації

**Типова структура**:
```
J^(k) = (Σ profits) / (Σ trades)

Example:
  - Total realized PnL: +$150
  - Total trades: 50
  → J = +$3 per trade (PASS ✓)
```

**Критерій**: **J̄ > 0** (позитивне очікування)

**Інтерпретація**:
- ✅ J̄ > 0: Система прибуткова в середньому
- ❌ J̄ ≤ 0: Система убиткова або нейтральна (FAIL)

---

### 2. **CVaR₀.₉₅ (Conditional Value at Risk)**

**Формула**:
$$\text{CVaR}_{0.95} = \frac{1}{0.05 \cdot N} \sum_{i : \text{return}_i \leq \text{VaR}_{0.95}} \text{return}_i$$

тобто середній збиток у гіршому 5% сценаріїв

**Типова структура**:
```
1. Упорядкувати все доходи від меньшого до більшого
   Returns (sorted): [-0.05, -0.04, -0.03, ..., 0.02, 0.03]

2. Взяти нижній 5% квантиль
   VaR_0.95 = returns[0.05 * len]

3. Усередити значення ≤ VaR_0.95
   CVaR_0.95 = mean(returns where return ≤ VaR_0.95)

Example (100 trades):
  - VaR_0.95 (5th percentile): -0.03 (−3% per trade)
  - Avg of 5 worst returns: -0.045 (−4.5%)
  → CVaR = 4.5% (FAIL ✗, ≤ 10% is acceptable)
```

**Критерій**: **CVaR₀.₉₅ ≤ 0.10** (не більше −10%)

**Інтерпретація**:
- ✅ CVaR ≤ 10%: Хвості ризику контрольовані
- ⚠️ CVaR 10−15%: Граничне, потреби розслідування
- ❌ CVaR > 15%: Надмірний хвіст-ризик (FAIL)

---

### 3. **MaxDD (Maximum Drawdown)**

**Формула**:
$$\text{MaxDD} = \max_{t} \frac{\text{Equity}(t) - \text{Peak}(t)}{\text{Peak}(t)}$$

максимальне відносне падіння від історичного піку

**Типова структура**:
```
Equity curve over time:
  t=0:   $10,000 (peak)
  t=10:  $9,500  (dd = 500/10000 = 5%)
  t=15:  $8,200  (dd = 1800/10000 = 18%)
  t=20:  $8,500  (recovery)
  t=30:  $11,000 (new peak)
  t=35:  $9,500  (dd = 1500/11000 = 13.6%)

MaxDD = max(5%, 18%, 13.6%) = 18%
```

**Критерій**: **MaxDD ≤ 0.20** (не більше 20%)

**Інтерпретація**:
- ✅ MaxDD ≤ 20%: Прийнятний ризик
- ⚠️ MaxDD 20−30%: Граничне, потреби менеджменту
- ❌ MaxDD > 30%: Надмірна волатильність (FAIL)

---

### 4. **ρ_reject (Rejection Rate)**

**Формула**:
$$\rho_{\text{reject}} = \frac{N_{\text{rejected}}}{N_{\text{total intent proposed}}}$$

частка trade intent, які були заблоковані ризик-гейтами

**Типова структура**:
```
Events on market:
  - Market tick: 1000
  - Features calc: 500
  - Regime detected: 250
  - Trade intent proposed: 100
  - ├─ Risk gate APPROVED: 92
  - └─ Risk gate BLOCKED: 8

ρ_reject = 8 / 100 = 0.08 (8%)
```

**Критерій**: **ρ_reject ≤ 0.08** (не більше 8%)

**Інтерпретація**:
- ✅ ρ_reject ≤ 8%: Нормальна частота блокування
- ⚠️ ρ_reject 8−15%: Висока, потреби перегляду сигналів
- ❌ ρ_reject > 15%: Система генерує забагато інтентів (FAIL)

---

### 5. **WHY_coverage (Why-Chain Coverage)**

**Формула**:
$$\text{WHY\_coverage} = \frac{N_{\text{trade intents with why\_chain}}}{N_{\text{total trade intents}}} \times 100\%$$

відсоток trade intent з повними why-chain записами

**Типова структура**:
```
Trade Intent #1: {why_chain: {...}} ✓ LOGGED
Trade Intent #2: {why_chain: MISSING} ✗ NOT LOGGED
Trade Intent #3: {why_chain: {...}} ✓ LOGGED
...

WHY_coverage = 99/100 = 99%
```

**Критерій**: **WHY_coverage = 100%**

**Інтерпретація**:
- ✅ WHY_coverage = 100%: Всі рішення пояснені
- ⚠️ WHY_coverage > 99%: Прийнятно, але потреби розслідувати пропуски
- ❌ WHY_coverage < 99%: Недостатня пояснюваність (FAIL)

---

## 🧪 WALK-FORWARD VALIDATION PROCESS (§12)

### Фаза 1: Данні Preparation

```python
# 1. Завантажити історичні OHLCV дані
from binance.client import Client
klines = Client().get_historical_klines(
    "BTCUSDT",
    "15m",
    "3 months ago UTC"
)
# Result: ~2,880 M15 bars за 3 місяці

# 2. Розділити на train/val/test блоки
blocks = []
for i in range(0, len(klines), 7*96):  # 7 днів = 7*96 M15 барів
    block = klines[i:i+7*96]
    if len(block) < 3*96:  # Skip incomplete blocks
        continue

    split_train = int(0.8 * len(block))  # 80% train, 20% val
    blocks.append({
        "num": len(blocks),
        "train": block[:split_train],
        "val": block[split_train:],
    })

# Result: ~12 blocks over 3 months
```

### Фаза 2: Training Loop

```python
for block in blocks:
    # 1. Train on block['train']
    decision_making.fit(block['train'])  # Optimize parameters

    # 2. Validate on block['val']
    trades_val = decision_making.backtest(block['val'])

    # 3. Compute metrics for this fold
    j_fold = mean([t['pnl'] for t in trades_val])
    cvar_fold = compute_cvar(trades_val)
    maxdd_fold = compute_maxdd(trades_val)

    metrics_per_fold.append({
        "j": j_fold,
        "cvar": cvar_fold,
        "maxdd": maxdd_fold,
        "trades": len(trades_val),
    })

# Result: List of metrics for each fold
```

### Фаза 3: Stability Analysis

```python
# 1. Compute aggregate metrics
j_values = [m["j"] for m in metrics_per_fold]
j_mean = mean(j_values)
j_std = stdev(j_values)

cvar_values = [m["cvar"] for m in metrics_per_fold]
cvar_mean = mean(cvar_values)

maxdd_values = [m["maxdd"] for m in metrics_per_fold]
maxdd_mean = mean(maxdd_values)

# 2. Check acceptance criteria
results = {
    "J_mean": j_mean,
    "J_std": j_std,
    "CVaR_mean": cvar_mean,
    "MaxDD_mean": maxdd_mean,
    "PASS": (
        j_mean > 0 and
        cvar_mean <= 0.10 and
        maxdd_mean <= 0.20
    ),
}

# 3. Report
print(f"""
WALK-FORWARD VALIDATION RESULTS
────────────────────────────────
Folds: {len(metrics_per_fold)}
Period: {blocks[0]['train'][0]['time']} to {blocks[-1]['val'][-1]['time']}

Expected Value (J̄):
  Mean: {j_mean:.4f}  ← PASS ✓ if > 0
  Std:  {j_std:.4f}

CVaR₀.₉₅:
  Mean: {cvar_mean:.4f}  ← PASS ✓ if ≤ 0.10

MaxDD:
  Mean: {maxdd_mean:.4f}  ← PASS ✓ if ≤ 0.20

Final: {'PASS ✓' if results['PASS'] else 'FAIL ✗'}
""")
```

---

## 🛡️ SAFETY GATES & FAILSAFES

### Daily Drawdown Gate

```python
def check_daily_dd_gate():
    """Stop trading if daily DD exceeds limit"""
    today_open_equity = fetch_daily_open()
    current_equity = fetch_current_equity()
    dd_today = (today_open_equity - current_equity) / today_open_equity

    if dd_today > 0.08:  # 8% limit
        TRADING_ALLOWED = False
        emit_alert(f"Daily DD {dd_today:.2%} exceeds 8% limit")
        return False

    return True
```

### Rejection Rate Gate

```python
def check_rejection_rate_gate():
    """Monitor if system is rejecting too many intents"""
    rejection_rate = intents_rejected / intents_proposed

    if rejection_rate > 0.08:  # 8% limit
        emit_warning(f"Rejection rate {rejection_rate:.2%} high")
        # Optionally: reduce signal threshold or adjust sizing

    return rejection_rate <= 0.10  # Hard limit at 10%
```

### CVaR Monitoring Gate

```python
def check_cvar_gate():
    """Monitor if tail risk is increasing"""
    recent_trades = get_last_n_trades(50)
    cvar = compute_cvar(recent_trades)

    if cvar > 0.15:  # Warn at 15%
        emit_warning(f"CVaR {cvar:.2%} elevated")

    if cvar > 0.20:  # Hard stop at 20%
        TRADING_ALLOWED = False
        emit_alert(f"CVaR {cvar:.2%} exceeds safety limit")
        return False

    return True
```

---

## ✅ ACCEPTANCE CHECKLIST

```
PHASE 1: Configuration Validation
────────────────────────────────────
☐ trading.yaml loads without errors
☐ All parameters in valid ranges
☐ signal_weights sum to 1.0
☐ sizing_modifiers ∈ [0.3, 1.5]

PHASE 2: Unit Testing
────────────────────
☐ RegimeDetector detects all 5 regimes
☐ Kelly calculator produces positive sizes
☐ Why-chain logs 100% of intents
☐ Risk gates reject obviously bad trades

PHASE 3: Integration Testing
────────────────────────────
☐ Event flow works (TICK → FEATURES → REGIME → INTENT)
☐ No state corruption
☐ Order execution successful
☐ PnL tracking accurate

PHASE 4: Walk-Forward Validation
─────────────────────────────────
☐ J̄ > 0 (positive expectancy)
  └ Typical: $1–$5 per trade
☐ CVaR₀.₉₅ ≤ 0.10
  └ Typical: 5–10% of equity per trade
☐ MaxDD ≤ 0.20
  └ Typical: 10–20% max
☐ ρ_reject ≤ 0.08
  └ Typical: 5–8% rejection
☐ WHY_coverage = 100%

PHASE 5: Paper Trading (2–4 weeks)
──────────────────────────────────
☐ Metrics stable across 10+ days
☐ No anomalies or edge cases
☐ Alerts working correctly
☐ Ready for live trading

FINAL: Go Live Decision
──────────────────────
☐ All acceptance criteria MET
☐ Risk limits configured correctly
☐ Monitoring & alerts active
☐ Team consensus on parameters
```

---

## 📈 EXPECTED PERFORMANCE RANGES

| Метрика | Conservative | Balanced | Aggressive |
|---------|--------------|----------|-----------|
| **J̄ (USD/trade)** | +$1 | +$2–$3 | +$3–$5 |
| **CVaR₀.₉₅** | 3–5% | 5–10% | 8–15% |
| **MaxDD** | 8–12% | 12–18% | 15–25% |
| **Trades/day** | 20–40 | 50–80 | 80–120 |
| **Win Rate** | 55–65% | 50–60% | 45–55% |
| **Avg Trade** | +15 bps | +20 bps | +25 bps |

---

## 🚨 RED FLAGS

❌ **Система НЕ ГОТОВА якщо**:

```
✗ J̄ ≤ 0              → убиткова (abort)
✗ CVaR > 15%          → надмірний хвіст-ризик (abort)
✗ MaxDD > 30%         → надмірна волатильність (abort)
✗ ρ_reject > 20%      → система нестійка (investigate)
✗ WHY_coverage < 99%  → недостатня пояснюваність (fix)
✗ Stability (Var(J)) high → нестійка на різних періодах (retune)
```

---

## 📝 ВИСНОВОК

Ця методологія забезпечує:
- ✅ Кількісну валідацію §19 критеріїв
- ✅ Walk-forward перевірку перевалідаціїstaleness
- ✅ Safety gates для live торгівлі
- ✅ Clear acceptance/rejection criteria

**Наступний крок**: Виконання Phase 1 (Configuration) і Phase 2 (Unit Tests) для підтвердження готовності.

