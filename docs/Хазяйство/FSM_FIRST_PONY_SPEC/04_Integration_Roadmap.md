# 04 Integration Roadmap — План Розгортання з DoD

**Мета**: Фазовий план розв'язання залишків для досягнення §19 критеріїв (J̄ > 0, CVaR ≤ 0.10, MaxDD ≤ 0.20, ρ_reject ≤ 0.08).

**Дата**: 3 листопада 2025 | **Статус**: ✅ DRAFT

---

## 🚀 ФАЗИ РОЗГОРТАННЯ

### **PHASE 1: BASELINE VALIDATION** (1-2 тижні)
**Мета**: Перевірити базову функціональність на live market data з testnet execution.

#### Завдання 1.1: Configuration Validation
**DoD (Definition of Done)**:
- ✅ `trading.yaml` містить всі параметри (§18)
- ✅ `models.volatility` конфіг завантажується без помилок
- ✅ `decision.sizing_modifiers` застосовується до Kelly розмірів
- ✅ Всі режими детектуються в логах

**Дії**:
```python
# 1. Verify YAML structure
from apps.reference.config import ConfigLoader
cfg = ConfigLoader.load("config/aurora/trading.yaml")
assert "models" in cfg["trading"]
assert "volatility" in cfg["trading"]["models"]
assert "sizing_modifiers" in cfg["trading"]["decision"]

# 2. Run sanity checks
test_signal_weights_sum_to_one()
test_kelly_cap_in_range_0_to_1()
test_daily_limits_reasonable()
```

**Файли для створення**:
- ✅ `tests/config/test_trading_yaml_structure.py`

**Timeline**: ~2-3 дні

---

#### Завдання 1.2: Event Flow Validation
**DoD**:
- ✅ EVT:MARKET_TICK_RECEIVED → EVT:FEATURES_CALCULATED → EVT:REGIME_DETECTED → DEC:TRADE_INTENT
- ✅ Всі переходи логуються в JSONL (structured logging)
- ✅ Нема пропущених подій або race conditions

**Дії**:
```bash
# 1. Start live market data stream
.venv/Scripts/Activate.ps1
python -m apps.reference.main --mode testnet --symbols BTCUSDT ETHUSDT

# 2. Monitor logs
Get-Content logs/event_flow.log -Tail 50 -Wait

# 3. Verify state transitions
# Expected: MARKET_TICK → FEATURES → REGIME → INTENT (every M15 bar)
```

**Файли для завдання**:
- 📝 `tests/integration/test_event_flow_m15.py` (new)

**Timeline**: ~2 дні

---

#### Завдання 1.3: Why-Chain Coverage
**DoD**:
- ✅ 100% рішень вхідних мають why_chain запис
- ✅ ψ(t) вектор містить: [φ_OBI, φ_TFI, φ_ΔP, regime, confidence]
- ✅ Детерміновано повторюється при тому ж вхідних даних

**Дії**:
```python
# 1. Extend DecisionLog to capture full ψ vector
class DecisionLog:
    def write_trade_intent(self, rid, symbol, why_chain):
        # Ensure all ψ components logged
        psi_vector = {
            "obi": why_chain.get("obi"),
            "tfi": why_chain.get("tfi"),
            "delta_price": why_chain.get("delta_price"),
            "regime": why_chain.get("regime"),
            "confidence": why_chain.get("confidence"),
            "signal_score": why_chain.get("signal_score"),
            "kelly": why_chain.get("kelly_fraction"),
            "regime_multiplier": why_chain.get("regime_multiplier"),
        }
        # Log to JSONL
        self.wal_log.append({"rid": rid, "psi": psi_vector})

# 2. Replay: Given ψ(t), verify Action(t) is identical
def test_action_determinism():
    psi_recorded = fetch_psi_from_log(rid)
    action_recorded = fetch_action_from_log(rid)

    # Re-run decision logic with ψ_recorded
    action_recomputed = decision_making._try_make_decision_from_psi(psi_recorded)

    assert action_recomputed == action_recorded  # Determinism!
```

**Файли для створення**:
- 📝 `dm_log_adapter.py` — розширити Why-Chain
- 📝 `tests/determinism/test_why_chain_determinism.py` (new)

**Timeline**: ~3 дні

---

### **PHASE 2: REGIME SCALABILITY** (1 тиждень)
**Мета**: Розширити режимну детекцію на повну Tension Index.

#### Завдання 2.1: ΔOI Integration
**DoD**:
- ✅ ΔOI fetching з Binance API або feed
- ✅ Z-score нормалізація (rolling window)
- ✅ Додано до Tension Index: T_s(t) = β₁|Δ̃OI| + ...
- ✅ HIGH_TENSION режим детектується

**Дії**:
```python
# 1. Add OI fetcher in market_data domain
class MarketData:
    def fetch_open_interest(self, symbol):
        # Use Binance OpenInterest endpoint
        oi = binance_adapter.get_open_interest(symbol)
        delta_oi = oi - self.last_oi[symbol]
        return delta_oi

# 2. Compute z-score
def compute_oi_zscore(delta_oi, window=50):
    deltas = self.oi_history[-window:]
    mu = mean(deltas)
    sigma = stdev(deltas)
    return (delta_oi - mu) / sigma if sigma > 0 else 0

# 3. Update Tension Index in RegimeDetector
T_s(t) = β₁|z_ΔOI| + β₂|z_Funding| + ...
```

**Файли для створення**:
- 📝 `market_data/oi_fetcher.py` (new)
- 📝 `regime_detector.py` — розширити Tension Index

**Timeline**: ~3 дні

---

#### Завдання 2.2: Funding Events
**DoD**:
- ✅ Funding events обробляються (якщо доступні з біржі)
- ✅ Z-score нормалізація funding rate
- ✅ Додано до Tension Index
- ✅ Режимні переходи точніші

**Дії**:
```python
# 1. Listen to funding events
# (Note: Binance funding 8-godинний, не in real-time)
def on_funding_event(self, event):
    symbol = event["symbol"]
    funding_rate = Decimal(event["funding_rate"])
    z_funding = normalize_zscore(funding_rate, self.funding_history)

    # Update latest_funding
    self.latest_funding[symbol] = z_funding

# 2. Update Tension Index
```

**Файли для створення**:
- 📝 `market_data/funding_listener.py` (new)
- 📝 `regime_detector.py` — додати funding компонента

**Timeline**: ~2 дні

---

#### Завдання 2.3: Break/Fake Detection
**DoD**:
- ✅ BreakUp/BreakDown детектується (price > R_max precedent)
- ✅ Hold validation (ціна утримується вище/нижче рівня)
- ✅ Fake-out детектується
- ✅ FSM переходи Break/Fake → Trend коректні

**Дії**:
```python
# 1. Implement Break detection
def detect_breakout(symbol, price, lookback_period=20):
    highs = self.price_history[symbol][-lookback_period:]
    max_high = max(highs)

    is_break_up = price > max_high
    return is_break_up

# 2. Implement Hold validation
def validate_hold_up(symbol, break_price, hold_period=5):
    prices = self.price_history[symbol][-hold_period:]
    min_price = min(prices)

    is_held = min_price > break_price - epsilon
    return is_held

# 3. Detect fake-outs
regime_transition = {
    "Break/Fake": {
        "BreakUp ∧ ¬HoldUp": "Cooldown",
        "BreakUp ∧ HoldUp": "Trend",
    }
}
```

**Файли для створення**:
- 📝 `regime_detector.py` — додати Break/Fake logic

**Timeline**: ~3 дні

---

### **PHASE 3: WALK-FORWARD VALIDATION** (1-2 тижні)
**Мета**: Реалізувати §12 walk-forward фреймворк.

#### Завдання 3.1: Historical Data Preparation
**DoD**:
- ✅ Historical OHLCV data для 3+ місяців (live або Binance archive)
- ✅ Дані розділені на train/val/test блоки
- ✅ Часова послідовність збережена (NO data leakage)

**Дії**:
```python
# 1. Download historical data
from binance.client import Client
client = Client(api_key="...", api_secret="...")

# Fetch 3 months of 15m data
klines = client.get_historical_klines("BTCUSDT", "15m", "3 months ago UTC")

# 2. Prepare train/val/test blocks
def prepare_walk_forward_blocks(klines, block_size_days=7, train_val_ratio=0.8):
    blocks = []
    for i in range(0, len(klines), block_size_days):
        block = klines[i:i+block_size_days]
        split_idx = int(len(block) * train_val_ratio)

        blocks.append({
            "train": block[:split_idx],
            "val": block[split_idx:],
            "block_num": i // block_size_days,
        })

    return blocks

# 3. Verify NO data leakage
assert max(train_dates) < min(val_dates)
```

**Файли для створення**:
- 📝 `tests/validation/historical_data_loader.py` (new)
- 📝 `tests/validation/walk_forward_harness.py` (new)

**Timeline**: ~2 дні

---

#### Завдання 3.2: Backtesting Engine
**DoD**:
- ✅ Simulated execution (entry/exit з реалістичним сліппеджем)
- ✅ PnL tracking per trade
- ✅ Metrics: Exp, CVaR, MaxDD, Trades count
- ✅ Can replay any trade with why_chain

**Дії**:
```python
class BacktestEngine:
    def __init__(self, config, decision_making_logic):
        self.config = config
        self.dm = decision_making_logic
        self.trades = []
        self.pnl_realized = 0
        self.pnl_unrealized = 0

    def on_bar(self, bar_data):
        """Simulate one M15 bar"""
        # 1. Emit EVT:MARKET_TICK
        self.dm.on_market_tick(bar_data)

        # 2. Run decision logic
        intent = self.dm._try_make_decision()

        # 3. Simulate execution
        if intent:
            entry_price = bar_data["close"]
            slippage = self._estimate_slippage(entry_price)
            filled_price = entry_price + slippage

            trade = {
                "entry": filled_price,
                "sl": intent["sl_price"],
                "tp_low": intent["tp_low"],
                "tp_high": intent["tp_high"],
                "qty": intent["qty"],
                "why": intent["why_chain"],
            }
            self.trades.append(trade)

        # 4. Check for exits
        self._check_exits(bar_data["close"], bar_data["high"], bar_data["low"])

    def compute_metrics(self):
        """Compute J, CVaR, MaxDD"""
        returns = [t["pnl"] / t["notional"] for t in self.trades if "pnl" in t]

        exp = mean(returns) if returns else 0
        var_95 = percentile(returns, 95)
        cvar_95 = mean([r for r in returns if r <= var_95])

        return {
            "exp": exp,
            "cvar_95": cvar_95,
            "max_dd": self._compute_max_dd(),
            "trades_count": len(self.trades),
        }
```

**Файли для створення**:
- 📝 `tests/validation/backtest_engine.py` (new)

**Timeline**: ~4 дні

---

#### Завдання 3.3: Hyperparameter Sweep
**DoD**:
- ✅ Grid search або Bayesian opt для параметрів (w1, w2, ϑ, SL_bps, κ_regime)
- ✅ Optimize J̄ subject to hard constraints
- ✅ Report stability (Var(J) across folds)

**Дії**:
```python
from skopt import gp_minimize

def objective(params):
    """Minimize negative J̄ subject to constraints"""
    w1, w2, theta, sl_bps = params

    j_scores = []
    for block in walk_forward_blocks:
        backtest = BacktestEngine(config, decision_making)
        metrics = backtest.run(block["train"], block["val"])

        # Hard constraints
        if metrics["cvar_95"] > 0.10 or metrics["max_dd"] > 0.20:
            return 1000  # Penalty

        j_scores.append(metrics["exp"])

    var_j = stdev(j_scores)
    mean_j = mean(j_scores)

    # Minimize variance while maximizing mean
    return -mean_j + 0.1 * var_j

# Run optimization
result = gp_minimize(
    objective,
    [(0.3, 0.7),    # w1
     (0.2, 0.6),    # w2
     (0.12, 0.35),  # theta
     (40, 120)],    # sl_bps
    n_calls=50,
    n_initial_points=10,
)
```

**Файли для створення**:
- 📝 `tests/validation/hyperparameter_sweep.py` (new)

**Timeline**: ~3 дні

---

### **PHASE 4: LIVE VALIDATION** (ongoing)
**Мета**: Перенести на live market з реальними малими капіталами (risk: ~$10/день).

#### Завдання 4.1: Paper Trading
**DoD**:
- ✅ Симуляція на live market data, без реальної тор​гівлі
- ✅ PnL tracking (з реалістичним сліппеджем)
- ✅ 2-4 тижні履歴 для перевірки §19 критеріїв
- ✅ Alert-и на anomalies

**Дії**:
```bash
# 1. Start paper trading
python -m apps.reference.main --mode paper-trading --duration 4w

# 2. Monitor daily metrics
# Expected: Exp > 0, CVaR ≤ 0.10, MaxDD ≤ 0.20

# 3. Alert on violations
if daily_dd > 0.08:
    AlertManager.send_alert("Daily DD exceeded 8%")
```

**Timeline**: ~4 тижні спостереження

---

#### Завдання 4.2: Live with Capital Gate
**DoD**:
- ✅ Запуск на live з max $100 капіталу
- ✅ Position size ≤ $10 (1% daily risk)
- ✅ Daily stop-loss if DD > 8%
- ✅ Безперервна фіксація metrics & why-chain

**Дії**:
```yaml
# config/aurora/trading.yaml
execution:
  manage:
    auto: true                    # Enable auto position management
    max_equity_utilization_pct: 0.40  # 40% leverage limit
    leverage_defaults:
      BTCUSDT: 2                  # Minimal leverage
      ETHUSDT: 2

risk:
  daily:
    max_realized_loss_usd: 50.0   # Stop at -$50
    max_drawdown_pct: 8.0
```

**Timeline**: ~8 тижнів до досягнення §19 критеріїв

---

## 📊 КРИТИЧНІ ЗАЛЕЖНОСТІ

```
Phase 1 (Config)
    ↓
    Phase 1 (Event Flow)
    ↓
    Phase 1 (Why-Chain)  ← MUST pass before Phase 2
    ↓
Phase 2 (Regime Scalability)
    ↓
    Phase 3 (Walk-Forward) ← MUST validate §19 before Phase 4
    ↓
Phase 4 (Live)
```

---

## ⏰ TIMELINE

| Фаза | Завдання | Днів | Дата Старту | Дата Фінішу |
|------|----------|------|-------------|------------|
| **1** | Config | 3 | 3 Nov | 6 Nov |
| **1** | Event Flow | 2 | 6 Nov | 8 Nov |
| **1** | Why-Chain | 3 | 8 Nov | 11 Nov |
| **2** | ΔOI | 3 | 11 Nov | 14 Nov |
| **2** | Funding | 2 | 14 Nov | 16 Nov |
| **2** | Break/Fake | 3 | 16 Nov | 19 Nov |
| **3** | Historical Data | 2 | 19 Nov | 21 Nov |
| **3** | Backtest Engine | 4 | 21 Nov | 25 Nov |
| **3** | Hyperparameter Sweep | 3 | 25 Nov | 28 Nov |
| **4** | Paper Trading | 28 | 28 Nov | 26 Dec |
| **4** | Live Validation | 56 | 26 Dec | 20 Feb |

**Усього**: ~140 днів = ~4.5 місяців до повної готовності

---

## 🎯 SUCCESS CRITERIA (§19)

```
J̄ > 0
  ∧ CVaR₀.₉₅ ≤ 0.10
  ∧ MaxDD ≤ 0.20
  ∧ ρ_reject ≤ 0.08
  ∧ WHY_coverage = 100%
```

**Критерії перевіряються на walk-forward validation (Phase 3).**

---

## 📝 ВИСНОВОК

Дорожна карта охоплює:
- ✅ **Фаза 1**: Перевірка базових компонентів
- ✅ **Фаза 2**: Розширення режимної детекції
- ✅ **Фаза 3**: Валідація на історичних даних
- ✅ **Фаза 4**: Живе тестування

**Наступний крок**: Перейти до `05_Configuration_Template.md` для конкретних параметрів YAML.

