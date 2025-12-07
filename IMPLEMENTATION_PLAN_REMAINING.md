# 🎯 Plan Реалізації — Що Залишилось

**Дата створення:** 2025-12-05 (оновлено)  
**Статус:** В процесі імплементації  
**Мова відповіді:** Українська  
**Джерела:** `apps/research/new_alpha/` — R&D документи з результатами Optuna

---

## 📊 Поточний Стан Системи

### ✅ Що РЕАЛІЗОВАНО (інфраструктура):

| Компонент | Статус | Тести |
|-----------|--------|-------|
| Pydantic моделі для per-instrument config | ✅ | 34 |
| FSM: TP1/TP2 partial exit | ✅ | 8 |
| FSM: Trailing stop | ✅ | 4 |
| FSM: Max hold time | ✅ | 3 |
| Config fallback chain (per-asset → global) | ✅ | 6 |
| BarResampler (tick → 1m OHLCV) | ✅ | 25 |
| Bollinger Bands / ATR indicators | ✅ | 26 |
| FLAT regime mapping | ✅ | 34 |
| MeanReversion1mStrategy | ✅ | 25 |
| MeanReversionHandler integration | ✅ | 16 |
| **Всього тестів** | ✅ | **189** |

### ❌ Що НЕ РЕАЛІЗОВАНО:

| Компонент | Причина | Пріоритет |
|-----------|---------|-----------|
| **XRPUSDT** config | Не перенесено з Phase 3 JSON | 🔴 HIGH |
| **DOGEUSDT** config | Показав +$88.38 в 1m MR | 🔴 HIGH |
| Instrument specs для XRP/DOGE | Відсутні step_size/tick_size | 🔴 HIGH |
| symbols_to_track не включає XRP/DOGE | Система не відстежує | 🔴 HIGH |
| SOLUSDT Phase 3 update | Часткові параметри | 🟡 MEDIUM |
| End-to-end тест всіх монет | Не написано | 🔴 HIGH |
| Smoke test на testnet | Не виконано | 🟡 MEDIUM |
| BTCUSDT Aurora config | Негативний PnL в Aurora, але +$45 в 1m MR | 🟢 LOW |

---

## 📈 Optuna Результати — ОНОВЛЕНО на основі new_alpha документів

### 🔥 Aurora Phase 3+ (Tick-Based Strategy)

| Symbol | Timeframe | PnL | Improvement | Статус в Config |
|--------|-----------|-----|-------------|-----------------|
| **SOLUSDT** | 3m | **+$318.94** | +58.2% vs P2 | ⚠️ Частково |
| **ETHUSDT** | 5m | **+$130.50** → $180.84 (P3+) | +38.6% | ⚠️ Частково |
| **XRPUSDT** | 3m | **+$45.93** → $74.15 (P3+) | +61.4% | ❌ **ВІДСУТНІЙ** |
| BTCUSDT | 5m | -$1.37 | Failed | ❌ Skip |

**Джерело:** `apps/research/new_alpha/RESULTS_PHASE3.md`, `AURORA_PHASE3_FULL_REPORT.md`

### 🔥 1m Mean Reversion (Bar-Based Strategy)

| Symbol | Timeframe | PnL | Trades | Win Rate | Статус |
|--------|-----------|-----|--------|----------|--------|
| **DOGEUSDT** | 1m | **+$88.38** 🏆 | 146 | 64.4% | ❌ **НЕ УВІМКНЕНО** |
| **BTCUSDT** | 1m | **+$45.27** | 172 | 65.7% | ⚠️ Config є |
| **ETHUSDT** | 1m | **+$37.38** | 33 | 69.7% | ⚠️ Config є |
| **XRPUSDT** | 1m | **+$31.41** | 107 | 62.6% | ⚠️ Config є |
| SOLUSDT | 1m | +$1.48 | 180 | 65.0% | ⚠️ Вимкнено (break-even) |

**Портфель 1m MR:** +$203.72/місяць (5 assets)  
**Джерело:** `apps/research/new_alpha/FINAL_CONFIGS_500TRIAL.md`, `cross_asset_1m_results.md`

### 📊 Ключові Інсайти з new_alpha документів:

1. **Side-Bias Asset-Specific:**
   - SOL: `0.0` (ВИМКНЕНО) — сильні трендові фази
   - ETH: `0.9` (МАКСИМУМ) — mean-reversion dominant
   - XRP: `0.4` (помірний)

2. **Sizing Optimization:**
   - LOW_VOL: 1.7x - 2.0x (агресивно)
   - HIGH_VOL: 0.1x - 0.6x (консервативно)
   - **KEY:** Прибуток робиться в LOW_VOL режимах!

3. **TP Strategy (Phase 3+):**
   - TP1 = 0.4x SL (агресивний), 50-70% позиції
   - TP2 = 1.4x-1.6x SL (extended)
   - XRP: trailing stop ACTIVE (0.4%/0.6%)
   - ETH: trailing stop DISABLED (static TP краще)

4. **DOGEUSDT — BEST 1m MR Performer:**
   - +$88.38 PnL (найвищий!)
   - sl_pct = 1.97% (широкий для мемкоїну)
   - bb_window = 20 (стандартний)

---

## 🔧 PHASE C1: Додати XRPUSDT Config (Aurora)

**Оцінка часу:** 30 хвилин  
**Пріоритет:** 🔴 HIGH  
**Джерело:** `best_aurora_XRPUSDT_3m_phase3.json`, `RESULTS_PHASE3.md`

### C1-01: Додати instruments.XRPUSDT

```yaml
# config/aurora/trading.yaml → trading.instruments
XRPUSDT:
  symbol: "XRPUSDT"
  step_size: "0.1"       # Binance XRPUSDT step_size
  tick_size: "0.0001"    # Binance XRPUSDT tick_size
  min_notional: "10"
```

### C1-02: Додати symbols_to_track

```yaml
symbols_to_track: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"]
```

### C1-03: Додати aurora_instruments.XRPUSDT

```yaml
# Source: best_aurora_XRPUSDT_3m_phase3.json + AURORA_PHASE3_FULL_REPORT.md
XRPUSDT:
  weights:
    ema: 0.427
    volume: 0.385
    macro: 0.469
    liquidity: 0.199
    obi: 0.12
    tfi: 0.402
    volatility: 0.367
    depth_imbalance: 0.392
    delta_price: 0.028
  
  side_bias:
    penalty_factor: 0.4    # MODERATE (from Phase 3)
    window_sec: 600        # 10 min
    target_ratio: 0.6
  
  regime_thresholds:
    HIGH_VOLATILITY: 1.9   # MAXIMUM filter (з RESULTS_PHASE3.md)
    LOW_VOLATILITY: 0.95
    TREND: 1.0
  
  regime_sizing:
    HIGH_VOLATILITY: 0.1   # MINIMAL (almost stops in chaos!)
    LOW_VOLATILITY: 1.7    # Aggressive
    MEAN_REVERSION: 0.8
  
  exit:
    sl_pct: 0.01671        # 1.671%
    max_hold_sec: 660      # 11 хвилин
  
  # Phase 3+ Take-Profit (from AURORA_PHASE3_FULL_REPORT.md)
  take_profit:
    tp_low_ratio: 0.4      # TP1 = 0.4x SL (aggressive)
    tp_high_ratio: 1.6     # TP2 = 1.6x SL
    partial_exit_pct: 0.5  # 50% at TP1
  
  # Phase 3+ Trailing Stop (XRP uses it!)
  trailing_stop:
    enabled: true
    activation_pct: 0.004  # Activate at +0.4%
    trail_pct: 0.006       # Trail 0.6% behind
    min_update_interval_sec: 5
  
  # Phase 3+ Cooldown
  execution:
    cooldown_sec: 20       # 20s pause between trades
```

---

## 🔧 PHASE C2: Додати DOGEUSDT Config

**Оцінка часу:** 30 хвилин  
**Пріоритет:** 🔴 HIGH  
**Джерело:** `FINAL_CONFIGS_500TRIAL.md` (1m MR best performer!)

### C2-01: Додати instruments.DOGEUSDT

```yaml
DOGEUSDT:
  symbol: "DOGEUSDT"
  step_size: "1"         # Binance DOGEUSDT step_size
  tick_size: "0.00001"   # Binance DOGEUSDT tick_size
  min_notional: "10"
```

### C2-02: Оновити mean_reversion_1m.yaml

DOGEUSDT вже є в конфігу, але потрібно переконатися що `enabled: true`:

```yaml
assets:
  DOGEUSDT:
    enabled: true        # MUST BE TRUE!
    bb_window: 20
    min_vol_atr: 0.010
    sl_pct: 0.0197       # 1.97% (wide for meme coin)
    allowed_regimes:
      - FLAT_LOW
      - FLAT_NORMAL
      - FLAT_HIGH
```

### C2-03: Глобально увімкнути 1m MR

```yaml
mean_reversion_1m:
  enabled: true          # CHANGE FROM false TO true!
```

---

## 🔧 PHASE C3: Оновлення SOLUSDT Config (Phase 3 params)

**Оцінка часу:** 20 хвилин  
**Пріоритет:** 🟡 MEDIUM  
**Джерело:** `best_aurora_SOLUSDT_3m_phase3.json`, `RESULTS_PHASE3.md`

### C3-01: Оновити weights та side_bias

**КРИТИЧНО:** SOL НЕ потребує side-bias penalty!

```yaml
SOLUSDT:
  weights:
    ema: 0.075          # було 0.12
    volume: 0.296       # було 0.18
    macro: 0.430        # було 0.10 (!)
    liquidity: 0.050    # було 0.25
    obi: 0.145          # було 0.14
    tfi: 0.180          # було 0.09
    volatility: 0.293   # було 0.05 (ЗНАЧНА ЗМІНА!)
    depth_imbalance: 0.205  # було 0.20
    delta_price: 0.213  # було 0.22

  side_bias:
    penalty_factor: 0.4  # УВАГА: Phase 3 каже 0.0 для SOL!
    window_sec: 300
    target_ratio: 0.5

  regime_thresholds:
    HIGH_VOLATILITY: 2.0  # MAXIMUM filter
    LOW_VOLATILITY: 0.6   # 
    TREND: 1.0

  regime_sizing:
    HIGH_VOLATILITY: 0.6  
    LOW_VOLATILITY: 2.0   # AGGRESSIVE
    MEAN_REVERSION: 0.7

  exit:
    sl_pct: 0.01733       # було 0.015
    max_hold_sec: 660
  
  take_profit:
    tp_low_ratio: 2.0
    tp_high_ratio: 4.0
    partial_exit_pct: 0.7
```

---

## 🔧 PHASE C4: Оновлення ETHUSDT (Phase 3+)

**Оцінка часу:** 20 хвилин  
**Пріоритет:** 🟡 MEDIUM  
**Джерело:** `AURORA_PHASE3_FULL_REPORT.md`

### C4-01: Weights — вже OK! ✅

### C4-02: Додати Phase 3+ TP параметри

```yaml
ETHUSDT:
  # ... existing weights ...
  
  # Phase 3+ Take-Profit (з AURORA_PHASE3_FULL_REPORT.md)
  take_profit:
    tp_low_ratio: 0.4      # TP1 = 0.4x SL (AGGRESSIVE!)
    tp_high_ratio: 1.4     # TP2 = 1.4x SL
    partial_exit_pct: 0.7  # 70% at TP1
  
  trailing_stop:
    enabled: false         # ETH: static TP preferred!
  
  execution:
    cooldown_sec: 15       # 15s pause between trades
```

---

## 🔧 PHASE C5: Валідація Config Loading

**Оцінка часу:** 15 хвилин  
**Пріоритет:** 🔴 HIGH

### C5-01: Написати тест завантаження всіх конфігів

```python
# tests/unit/test_config_loading.py

def test_load_all_aurora_instruments():
    """Verify all per-instrument configs load correctly."""
    config = load_config()
    
    # Must have these symbols
    expected_symbols = ["ETHUSDT", "SOLUSDT", "XRPUSDT"]
    
    for symbol in expected_symbols:
        instr_cfg = config.trading.aurora_instruments.get(symbol)
        assert instr_cfg is not None, f"{symbol} missing"
        assert instr_cfg.weights is not None
        assert instr_cfg.exit is not None
        assert instr_cfg.exit.sl_pct > 0
```

### C4-02: Написати тест fallback chain

```python
def test_config_fallback_chain():
    """Verify per-instrument → global fallback works."""
    config = load_config()
    
    # XRPUSDT has trailing_stop.enabled = false
    xrp_cfg = config.trading.aurora_instruments["XRPUSDT"]
    assert xrp_cfg.trailing_stop.enabled is False
    
    # ETHUSDT has trailing_stop.enabled = true
    eth_cfg = config.trading.aurora_instruments["ETHUSDT"]
    assert eth_cfg.trailing_stop.enabled is True
```

---

## 🔧 PHASE C5: End-to-End Multi-Symbol Test

**Оцінка часу:** 1-2 години  
**Пріоритет:** 🔴 HIGH

### C5-01: Створити інтеграційний тест

```python
# tests/integration/test_multi_symbol_aurora.py

@pytest.fixture
def multi_symbol_fsm():
    """Create FSM instances for each tracked symbol."""
    config = load_config()
    fsms = {}
    for symbol in config.trading.symbols_to_track:
        fsms[symbol] = ManageFlowFSM(config)
        fsms[symbol].symbol = symbol
    return fsms

def test_bracket_prices_per_symbol(multi_symbol_fsm):
    """Each symbol should use its own SL%/TP ratios."""
    expected_sl_pcts = {
        "ETHUSDT": 0.019,
        "SOLUSDT": 0.01733,
        "XRPUSDT": 0.01671,
    }
    
    for symbol, fsm in multi_symbol_fsm.items():
        fsm.position_entry_price = Decimal("100")
        fsm.position_side = "BUY"
        fsm.position_qty = Decimal("1")
        
        sl, tp1, tp2 = fsm._calculate_bracket_prices()
        
        expected_sl = Decimal("100") * (1 - Decimal(str(expected_sl_pcts.get(symbol, 0.02))))
        assert abs(sl - expected_sl) < Decimal("0.01"), f"{symbol} SL mismatch"
```

---

## 🔧 PHASE C6: Testnet Smoke Test

**Оцінка часу:** 2-4 години  
**Пріоритет:** 🟡 MEDIUM

### C6-01: Запустити систему на testnet

```bash
# 1. Set testnet mode
export TRADING_MODE=testnet

# 2. Run with single symbol first
python -m apps.reference.main --symbols ETHUSDT

# 3. Check logs for:
#    - Config loading success
#    - Per-instrument params applied
#    - Signal generation working
#    - Order placement via FSM
```

### C6-02: Перевірити order placement

- [ ] SL order placed at correct price (per-asset sl_pct)
- [ ] TP1 order with 70% qty
- [ ] TP2 order with 30% qty (if configured)
- [ ] Trailing stop activates at configured %
- [ ] Max hold time triggers exit

### C7-03: Перевірити multi-symbol

```bash
# Run with all profitable symbols (Aurora + 1m MR)
python -m apps.reference.main --symbols ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT
```

---

## 📋 Черга Виконання (ОНОВЛЕНО)

| # | Phase | Задача | Час | PnL Impact |
|---|-------|--------|-----|------------|
| 1 | **C1** | Додати XRPUSDT config (Aurora) | 30m | **+$74/міс** |
| 2 | **C2** | Додати DOGEUSDT + увімкнути 1m MR | 30m | **+$88/міс** |
| 3 | **C3** | Оновити SOLUSDT Phase 3 params | 20m | +$117/міс |
| 4 | **C4** | Оновити ETHUSDT Phase 3+ | 20m | +$50/міс |
| 5 | **C5** | Тест config loading | 15m | - |
| 6 | **C6** | E2E multi-symbol test | 1-2h | - |
| 7 | **C7** | Testnet smoke test | 2-4h | - |

**Очікуваний сумарний PnL:** +$329/місяць (Aurora) + $203/місяць (1m MR) = **+$532/місяць**

---

## 🚦 Definition of Done

### Для PRODUCTION READY:

- [ ] **C1**: XRPUSDT Aurora config додано (+trailing stop!)
- [ ] **C2**: DOGEUSDT instruments + 1m MR enabled
- [ ] **C3**: SOLUSDT оновлено (weights, side_bias=0.4)
- [ ] **C4**: ETHUSDT Phase 3+ TP params
- [ ] **C5**: Тест config loading (всі 5 symbols)
- [ ] **C6**: E2E multi-symbol test проходить
- [ ] **C7**: Testnet smoke test успішний
- [ ] Всі 189+ тестів проходять
- [ ] Логи не містять errors/warnings

---

## ⚠️ Ризики та Застереження (ОНОВЛЕНО)

1. **XRPUSDT sl_pct = 1.671** в JSON — це **0.01671** (1.671%), НЕ помилка
2. **DOGEUSDT в Aurora** має негативний PnL (-$38), але **+$88 в 1m MR** → використовуємо MR!
3. **BTCUSDT Aurora** негативний, але **+$45 в 1m MR** → є в конфігу, потребує only MR
4. **SOL side_bias:** Phase 3 каже `0.0`, але поточний config має `0.4` — ПЕРЕВІРИТИ!
5. **ETH trailing stop:** Phase 3+ каже `enabled: false` — static TP краще!
6. **XRP trailing stop:** Phase 3+ каже `enabled: true` (0.4%/0.6%) — АКТИВУВАТИ!

---

## 📊 Метрики Успіху (ОНОВЛЕНО)

| Метрика | Поточне | Ціль |
|---------|---------|------|
| Тестів проходить | 189 | 200+ |
| Символів у Aurora config | 2 (ETH, SOL) | **4** (+ XRP, DOGE*) |
| Символів у 1m MR | 5 (disabled) | **5 (enabled)** |
| E2E тестів | 0 | 5+ |
| Testnet smoke | ❌ | ✅ |
| Очікуваний PnL/міс | - | **+$532** |

*DOGE використовує 1m MR, не Aurora

---

## 📚 Джерела new_alpha

| Документ | Інформація |
|----------|------------|
| `RESULTS_PHASE3.md` | SOL +58%, XRP +58%, ETH +23% |
| `AURORA_PHASE3_FULL_REPORT.md` | TP/Trailing/Cooldown params |
| `FINAL_CONFIGS_500TRIAL.md` | 1m MR configs (DOGE best!) |
| `cross_asset_1m_results.md` | Portfolio +$187/month |

---

*Оновлено на основі `apps/research/new_alpha/` документів.*
