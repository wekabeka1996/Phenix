# alpha_search — Domain Manual

Останнє оновлення: 2026-02-14.

## TL;DR

- `alpha_search` — домен для розрахунку **alpha score** (сигналу) з features, з контрактом `AlphaModel -> AlphaScore` та реєстром моделей.
- Працює як **shadow daemon** у всіх режимах: backtest, testnet, hybrid, live.
- Має **уніфікований контракт** події `EVT:ALPHA_SCORE_CALCULATED` (owner: `alpha_search`, status: `active`, schema: `schemas/alpha_score_calculated_v1.json`).
- Два шляхи емісії: in-process через `DecisionMaking.alpha_registry` та backtest shadow plugin — обидва використовують однаковий payload-формат (один event на один score).
- Fail-closed: при відсутності features/ціни повертає `score=0, confidence=0` з поясненням.
- Три моделі: `MomentumAlphaModel`, `MeanReversionAlphaModel`, `VolatilityAlphaModel` + `AuroraAlphaAdapter`.
- WAL listener пише всі alpha score events у WAL для офлайн аналізу.
- Є CLI-інструмент аналізу: `tools/alpha_search_report.py`.

---

## 1. Призначення

Домен `alpha_search` надає стандартизований спосіб обчислення alpha score (нормалізований сигнал + впевненість + пояснення "why") на базі features. Основні можливості:

- **Бібліотека**: `AlphaModelRegistry` використовується в `decision_making` для in-process скорингу.
- **Shadow plugin**: `AlphaSearchBacktestPlugin` працює як незалежний shadow daemon у всіх торгових режимах.
- **Аналітика**: WAL listener + CLI інструмент для post-hoc аналізу якості сигналів.

### Межі відповідальності

| In-Scope | Out-of-Scope |
|----------|-------------|
| Контракт `AlphaModel` та DTO `AlphaScore` | Генерація features (це `feature_engineering`) |
| TA-моделі: momentum/mean-reversion/volatility | Торгові рішення (це `decision_making`) |
| Aurora adapter як provider | Ордера та виконання (це `execution_position`) |
| Shadow plugin з virtual trader | Backtest engine оркестрація |
| WAL persistence alpha scores | |

---

## 2. Архітектура

### Компоненти

```
AlphaModel (ABC)              -- контракт: calculate_alpha() -> AlphaScore
  |-- MomentumAlphaModel      -- price momentum multi-timeframe
  |-- MeanReversionAlphaModel -- BB + RSI + SMA deviation
  |-- VolatilityAlphaModel    -- ATR + BB width + realized vol
  |-- AuroraAlphaAdapter      -- wrapper навколо AuroraScoringKernel

AlphaModelRegistry            -- реєстр + масовий розрахунок is_ready() моделей
EnsembleModel                 -- комбінатор моделей з dynamic weights
AlphaSearchBacktestPlugin     -- shadow multi-provider plugin
AlphaScoreWalListener         -- WAL writer для alpha score events
AlphaSearchConfig             -- Pydantic strict конфіг (extra="forbid")
```

### Потоки даних

#### Flow 1: In-process (decision_making)

```
EVT:FEATURES_CALCULATED
  -> DecisionMaking receives features
  -> alpha_registry.calculate_all_alpha(symbol, market_data, features)
  -> For each ready model: emit EVT:ALPHA_SCORE_CALCULATED (one per score)
  -> WAL listener writes to WAL
```

#### Flow 2: Shadow plugin (two-phase bridge)

```
Phase 1: EVT:FEATURES_CALCULATED
  -> _on_features_cache(): cache features by (symbol, tf_sec, bar_close_ts)

Phase 2: CMD:PROCESS_STRATEGY
  -> _on_decision_score(): read cache, run all enabled providers
  -> emit EVT:ALPHA_SCORE_CALCULATED per provider
  -> virtual trader tracks positions/PnL

Phase 3: EVT:TRADE_EXECUTED
  -> _on_trade(): feed PnL back to ensemble models via on_trade_result()
```

#### Flow 3: WAL persistence

```
EVT:ALPHA_SCORE_CALCULATED (from any emitter)
  -> AlphaScoreWalListener._on_alpha_score()
  -> vfoundation.dr.wal.append({verb, symbol, provider_id, score, ...})
```

---

## 3. Контракт події EVT:ALPHA_SCORE_CALCULATED

**Registry**: `verb_registry_v1.yaml` — owner: `alpha_search`, status: `active`

**Schema**: `schemas/alpha_score_calculated_v1.json`

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Trading pair (e.g. "BTCUSDT") |
| `provider_id` | string | Provider identifier ("aurora", "dm_inline", etc.) |
| `model_name` | string | Model name ("aurora_v2_adapter", "momentum_v1", etc.) |
| `score` | number | Alpha score in [-1, 1] |
| `confidence` | number | Confidence in [0, 1] |

### Optional fields

`tf_sec`, `bar_close_ts`, `threshold`, `shadow`, `signal_id`, `features_used`, `why`

### Емітери

1. **DecisionMaking** (provider_id=`"dm_inline"`) — in-process, один event на score
2. **AlphaSearchBacktestPlugin** — shadow plugin, один event на provider

Обидва емітери використовують однаковий формат payload.

---

## 4. Конфігурація

### Файл: `config/alpha_search.yaml`

```yaml
enabled: true
shadow_mode: true

providers:
  aurora:
    enabled: true
    adapter:
      essential_features: [obi, delta_price, macro_resid]
      scoring_version: v2
    threshold: 0.1
    fail_closed: true
    symbols: [BTCUSDT, ETHUSDT, SOLUSDT]

  ta_ensemble:
    enabled: false   # Enable when ready
    ensemble:
      models:
        momentum_v1: { enabled: true, weight: 0.4 }
        mean_reversion_v1: { enabled: true, weight: 0.3 }
        volatility_v1: { enabled: true, weight: 0.3 }
      rebalance_frequency_days: 7
      performance_window_days: 30
      risk_adjustment: true
    threshold: 0.15
    fail_closed: true

triggers:
  feature_event: "EVT:FEATURES_CALCULATED"
  decision_event: "CMD:PROCESS_STRATEGY"
  emit_event: "EVT:ALPHA_SCORE_CALCULATED"

cache:
  max_per_symbol: 10
  require_same_bar_close_ts: false

virtual_trader:
  enabled: false
  notional_size: 1000
  max_positions_per_symbol: 1
  exit:
    max_bars: 12
    max_hold_sec: 3600
```

### Pydantic моделі: `config_models.py`

- `AlphaSearchConfig` — root config, strict `extra="forbid"`
- `ProviderConfig` — per-provider (adapter or ensemble)
- `AuroraAdapterConfig` — aurora-specific settings
- `TriggersConfig` — event names for two-phase bridge
- `CacheConfig` — feature cache settings
- `VirtualTraderConfig` — virtual position tracking

---

## 5. Режими роботи

### Backtest mode

**Wiring**: `apps/reference/main.py:621-642`

```
AlphaSearchBacktestPlugin(event_bus=fsm, config_path="config/alpha_search.yaml")
engine.alpha_search_plugin = alpha_plugin
AlphaScoreWalListener(event_bus=fsm)
```

- Plugin підключається до FSM event bus
- Слухає `EVT:FEATURES_CALCULATED`, `CMD:PROCESS_STRATEGY`, `EVT:TRADE_EXECUTED`
- Summary інжектується в backtest report (`report_data["alpha_search"]`)
- При shutdown генерує `alpha_search_report.json` у `<run_dir>/analysis/`

### Testnet / Hybrid / Live modes

**Wiring**: `apps/reference/main.py:~1387` (після CsvRecorder init)

```
AlphaSearchBacktestPlugin(event_bus=fsm, config_path="config/alpha_search.yaml")
AlphaScoreWalListener(event_bus=fsm)
```

- Працює ідентично до backtest, але без engine attachment
- Shadow mode: сигнали логуються/емітяться, але не впливають на торгівлю
- WAL listener пише events для post-hoc аналізу
- Доступний у всіх non-backtest режимах: `testnet`, `hybrid_live_data_testnet_exec`, `live`

### In-process (decision_making)

**Wiring**: `apps/reference/domains/decision_making/decision_making.py`

- `AlphaModelRegistry` створюється при ініціалізації DecisionMaking
- Моделі: `MomentumAlphaModel`, `MeanReversionAlphaModel`, `VolatilityAlphaModel`
- Емісія при кожному виклику evaluate з features

---

## 6. Моделі

### MomentumAlphaModel (`momentum_v1`)

Аналізує momentum ціни по timeframes:
- Short-term (5m): 30% weight
- Medium-term (1h): 40% weight
- Long-term (1d): 30% weight

Features: `price_momentum_5m`, `price_momentum_1h`, `price_momentum_1d`, `volume_momentum_5m`, `rsi_14`, `macd_signal`

Score > 0 = bullish momentum, < 0 = bearish momentum.

### MeanReversionAlphaModel (`mean_reversion_v1`)

Визначає overbought/oversold умови:
- Bollinger Band position (%B): 40% weight
- RSI divergence: 30% weight
- SMA deviation: 20% weight
- Stochastic crossover: 10% weight

Features: `bb_position`, `bb_width`, `rsi_14`, `price_sma_20_deviation`, `volume_sma_ratio`, `stoch_k`, `stoch_d`

Score > 0 = sell (overbought), < 0 = buy (oversold).

### VolatilityAlphaModel (`volatility_v1`)

Аналізує volatility state:
- ATR ratio: normalized average true range
- BB width: Bollinger Band width
- Realized volatility ratios across timeframes

Score > 0 = rising volatility, < 0 = falling volatility.

### AuroraAlphaAdapter (`aurora_v2_adapter`)

Wrapper навколо `AuroraScoringKernel.compute()`:
- Essential features: `obi`, `delta_price`, `macro_resid`
- Fail-closed: missing features -> score=0 + why
- Reuses production scoring kernel

---

## 7. AlphaScore DTO

```python
@dataclass
class AlphaScore:
    model_name: str           # "momentum_v1", "aurora_v2_adapter", etc.
    symbol: str               # "BTCUSDT"
    score: Decimal            # [-1, 1] — alpha signal
    confidence: Decimal       # [0, 1] — signal confidence
    timestamp: int            # ms since epoch
    features_used: list[str]  # which features were used
    why: list[str]            # human-readable reasoning chain
```

**Invariants**:
- `score` clamped to [-1, 1] via Pydantic Field constraints
- `confidence` clamped to [0, 1]
- Registry не допускає 2 моделі з однаковим name

---

## 8. Fail-Closed Design

| Scenario | Behavior |
|----------|----------|
| Missing essential features (Aurora) | score=0, confidence=0, why=["fail_closed:missing_essential_features"] |
| Missing price | score=0, confidence=0, why=["fail_closed:missing_price"] |
| Cache miss (plugin) | score=0, confidence=0, why=["fail_closed:missing_features_for_bar"] |
| Provider exception | score=0 emitted if `fail_closed=true` in config |
| WAL write failure | Error logged, event silently dropped (listener doesn't crash) |
| Config load failure | Falls back to `get_default_config()` (enabled=false) |

---

## 9. CLI Аналіз: `tools/alpha_search_report.py`

### Usage

```bash
# From backtest run directory
python tools/alpha_search_report.py --run-dir reports/backtests/<run_id>

# From WAL directory
python tools/alpha_search_report.py --wal-dir ops/wal

# Output to file
python tools/alpha_search_report.py --run-dir <dir> --output-json analysis/alpha.json

# Markdown table
python tools/alpha_search_report.py --run-dir <dir> --output-md

# Custom horizon (default 300s)
python tools/alpha_search_report.py --run-dir <dir> --horizon-sec 600
```

### Output

Per-model:
- Signal distribution (long/short/neutral)
- Hit rate vs actual price movement
- Virtual PnL (basis points)
- Confidence calibration (is 80% conf really 80% hit rate?)

### Auto-run

Report автоматично генерується при `alpha_plugin.shutdown(run_dir=...)` після backtest.
Зберігається в `<run_dir>/analysis/alpha_search_report.json`.

---

## 10. Тестування

### Test suites

| Suite | File | Tests | Coverage |
|-------|------|-------|----------|
| Aurora adapter | `test_aurora_adapter.py` | fail-closed, score range, sign match | aurora_adapter.py |
| Registry | `test_registry_fail_closed.py` | readiness, error isolation, metrics | alpha_model.py |
| Ensemble | `test_ensemble_features_plumbing.py` | features passing, symbol propagation | ensemble.py |
| Backtest plugin | `test_backtest_plugin.py` | cache, prune, timestamp normalize, fail-closed | backtest_plugin.py |
| Model determinism | `test_models_determinism.py` | ranges, clamping, determinism | models/*.py |
| Integration | `test_integration.py` | end-to-end flow, WAL capture, schema compliance | all |

### Running tests

```bash
# All alpha_search tests
pytest tests/domains/alpha_search/ -v

# Specific suite
pytest tests/domains/alpha_search/test_integration.py -v
```

---

## 11. Файлова структура

```
apps/reference/domains/alpha_search/
  __init__.py
  alpha_model.py          -- AlphaModel ABC, AlphaScore DTO, AlphaModelRegistry
  backtest_plugin.py      -- AlphaSearchBacktestPlugin (shadow daemon)
  config_models.py        -- Pydantic config models + YAML loader
  ensemble.py             -- EnsembleModel + EnsembleConfig
  wal_listener.py         -- AlphaScoreWalListener (WAL writer)
  README.md               -- This file
  models/
    __init__.py
    aurora_adapter.py     -- AuroraAlphaAdapter
    momentum.py           -- MomentumAlphaModel
    mean_reversion.py     -- MeanReversionAlphaModel
    volatility.py         -- VolatilityAlphaModel

config/
  alpha_search.yaml       -- Plugin configuration

schemas/
  alpha_score_calculated_v1.json  -- Event schema

tools/
  alpha_search_report.py  -- CLI analysis tool

tests/domains/alpha_search/
  test_aurora_adapter.py
  test_backtest_plugin.py
  test_ensemble_features_plumbing.py
  test_integration.py
  test_models_determinism.py
  test_registry_fail_closed.py
```

---

## 12. Глосарій

| Термін | Визначення |
|--------|-----------|
| **Alpha score** | Числовий сигнал [-1, 1], позитивний = bullish (для momentum/aurora) |
| **Confidence** | Впевненість сигналу [0, 1] |
| **Provider** | Джерело сигналу: aurora adapter або TA ensemble |
| **Shadow mode** | Сигнали логуються, але не впливають на торгівлю |
| **Fail-closed** | При помилці повертаємо score=0 з поясненням |
| **Two-phase bridge** | EVT:FEATURES_CALCULATED -> cache -> CMD:PROCESS_STRATEGY -> score |
| **Virtual trader** | Симулятор позицій для оцінки PnL сигналів |
| **WAL** | Write-Ahead Log — JSONL persistence для events |
