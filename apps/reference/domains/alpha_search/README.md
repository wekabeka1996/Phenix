# alpha_search — Domain Manual

Останнє оновлення: 2026-02-24.

## TL;DR

- `alpha_search` — домен для розрахунку **alpha score** (сигналу) з features, з контрактом `AlphaModel -> AlphaScore` та реєстром моделей.
- Працює як **shadow daemon** у всіх режимах: backtest, testnet, hybrid, live.
- **Standalone Runtime** — автономний процес для паралельного shadow-тестування до 20 сценаріїв з 3 типами стратегій (Aurora, Mean Reversion, Ensemble). Запуск: `python scripts/run_alpha_search_domain.py`. Детальна інструкція — розділи 13-27.
- Має **уніфікований контракт** події `EVT:ALPHA_SCORE_CALCULATED` (owner: `alpha_search`, status: `active`, schema: `schemas/alpha_score_calculated_v1.json`).
- Два шляхи емісії: in-process через `DecisionMaking.alpha_registry` та backtest shadow plugin — обидва використовують однаковий payload-формат (один event на один score).
- Fail-closed: при відсутності features/ціни повертає `score=0, confidence=0` з поясненням.
- Три моделі: `MomentumAlphaModel`, `MeanReversionAlphaModel`, `VolatilityAlphaModel` + `AuroraAlphaAdapter`.
- WAL listener пише всі alpha score events у WAL для офлайн аналізу.
- Є CLI-інструмент аналізу: `tools/alpha_search_report.py`.
- **267 тестів** у 22 файлах (T1-T4 + cross-cutting): `pytest apps/reference/domains/alpha_search/tests/ -v`

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

---

# Standalone Runtime — Повна інструкція

## Короткий опис

Alpha Search Standalone Runtime — це автономний процес для паралельного shadow-тестування торгових стратегій. Він запускається **незалежно** від основного процесу `apps/reference/main.py` і дозволяє одночасно виконувати до 20 сценаріїв з різними параметрами стратегій (Aurora, Mean Reversion, Ensemble), порівнюючи їхні результати для пошуку найкращих конфігурацій.

Ключові принципи:
- **Shadow mode**: жодних реальних ордерів, тільки виртуальний PnL
- **Fail-closed**: будь-яка помилка валідації або відсутні features призводять до score=0
- **Ізоляція сценаріїв**: кожен сценарій має власний стан, логи, метрики і ShadowBook
- **Без залежностей від main.py**: повністю автономний процес

---

## 13. Швидкий старт

### Передумови

1. Проект Phenix клонований і залежності встановлені:
   ```bash
   pip install -r requirements.txt
   ```

2. Файл вхідних даних існує (JSONL формат):
   ```
   logs/alpha_input/alpha_input_v1.jsonl
   ```

3. Конфіг-файли стратегій присутні:
   ```
   config/aurora/strategies/aurora.yaml
   config/aurora/strategies/mean_reversion.yaml
   config/alpha_search.yaml
   config/alpha_search_system.yaml
   ```

### Запуск (replay mode)

```bash
# Стандартний запуск з матрицею за замовчуванням
python scripts/run_alpha_search_domain.py

# З кастомною матрицею
python scripts/run_alpha_search_domain.py --matrix config/alpha_search/scenario_matrix.yaml

# З підвищеним рівнем логування
python scripts/run_alpha_search_domain.py --log-level DEBUG
```

### Що відбувається при запуску

1. Завантажується `scenario_matrix.yaml` (валідація через Pydantic, fail-closed)
2. Створюється сесійна директорія: `logs/alpha_search_runtime/<YYYYMMDD_HHMMSS>/`
3. Ініціалізуються всі enabled сценарії (воркери + логери + ShadowBook)
4. Читається вхідний потік (`alpha_input_v1.jsonl`)
5. Кожен snapshot розсилається до всіх воркерів (fan-out)
6. Результати пишуться у per-scenario та aggregate логи
7. При завершенні (кінець файлу або Ctrl+C) генерується фінальний звіт

### Перший результат за 30 секунд

```bash
# 1. Переконайтеся що є вхідний файл
ls logs/alpha_input/alpha_input_v1.jsonl

# 2. Запустіть
python scripts/run_alpha_search_domain.py

# 3. Перевірте результати
ls logs/alpha_search_runtime/
```

---

## 14. Архітектура Standalone Runtime

### Діаграма компонентів

```
scripts/run_alpha_search_domain.py     <-- Точка входу
    |
    v
launcher.py                            <-- Завантаження конфіга, логи, reactor loop
    |
    +---> IngestGateway (ingest.py)     <-- Читання JSONL (replay / live_tail)
    |         |
    |         v  alpha_input_v1 snapshots
    |
    +---> ScenarioManager               <-- Ініціалізація та управління воркерами
    |     (scenario_manager.py)
    |         |
    |         +---> ScenarioWorker S01   <-- Aurora Baseline
    |         +---> ScenarioWorker S02   <-- Aurora Aggressive
    |         +---> ScenarioWorker S03   <-- Aurora Conservative
    |         +---> ...
    |         +---> ScenarioWorker S17   <-- Ensemble Momentum-Dominant
    |
    +---> ScenarioExecutor              <-- Паралельне виконання (ThreadPool / Sequential)
    |     (executor.py)
    |
    +---> HealthMonitor (health.py)     <-- Моніторинг здоров'я сценаріїв
    |
    +---> BoundedIngestQueue            <-- Backpressure (drop_oldest / drop_newest / block)
          (backpressure.py)
```

### Потік даних

```
JSONL файл
  --> IngestGateway.iter_replay()      (валідація AlphaInputV1, fail-closed)
    --> ScenarioExecutor.execute_all() (fan-out до всіх воркерів)
      --> ScenarioWorker.process_snapshot() (per-scenario scoring)
        --> AlphaSearchBacktestPlugin  (two-phase: cache features -> score)
          --> AlphaShadowResultV1      (score + side + confidence)
    --> ScenarioScoreWriter            (per-scenario scores.jsonl)
    --> AggregateReporter              (aggregate_metrics.csv)
    --> ShadowBook                     (virtual PnL tracking)
```

### Модулі runtime/

| Модуль | Призначення |
|--------|-------------|
| `contracts.py` | Pydantic-контракти: AlphaInputV1, AlphaShadowResultV1, ScenarioMatrixConfig, RuntimeConfig |
| `launcher.py` | Точка входу: `load_matrix_config()`, `setup_logging()`, `main_reactor()` |
| `ingest.py` | IngestGateway: читання JSONL (replay sync / live_tail async) |
| `scenario_manager.py` | ScenarioManager: ініціалізація воркерів, fan-out, shutdown |
| `scenario_worker.py` | ScenarioWorker: per-scenario scoring через BacktestPlugin |
| `executor.py` | ScenarioExecutor: sequential або thread_pool виконання |
| `config_resolver.py` | Резолюція конфіга: override (dot-path deltas) та full_config (повні YAML) |
| `override_allowlist.py` | Allowlist дозволених override-шляхів per strategy type |
| `shadow_book.py` | ShadowBook: virtual PnL, Sharpe ratio, max drawdown, win rate |
| `backpressure.py` | BoundedIngestQueue: 3 policy (drop_oldest, drop_newest, block) |
| `health.py` | HealthMonitor: heartbeat, degradation detection, auto-recovery |
| `hot_reload.py` | ConfigWatcher: зміна конфіга без перезапуску (safe-swap + rollback) |
| `logger_factory.py` | ScenarioLoggerFactory: ізольовані логери per scenario |
| `reporting.py` | AggregateReporter: aggregate CSV + JSONL звітність |
| `feature_mirror_writer.py` | FeatureMirrorWriter: live mirror features -> JSONL stream |
| `runbook.py` | Утиліти: генерація звітів, порівняння сценаріїв |

---

## 15. Конфігурація: scenario_matrix.yaml

Файл `config/alpha_search/scenario_matrix.yaml` — це **SSOT** (Single Source of Truth) для всіх сценаріїв.

### Структура

```yaml
matrix_id: alpha_search_shadow_v2    # Ідентифікатор матриці
version: 2                           # Версія схеми

# --- Налаштування runtime ---
runtime:
  max_scenarios: 20                  # Максимум сценаріїв (1-50)
  max_concurrent_scenarios: 20       # Максимум паралельних (1-50)
  parallelism: thread_pool           # sequential | thread_pool
  max_workers: 4                     # Потоків у пулі (1-32)
  queue_maxsize: 4000                # Розмір черги (100-100000)
  backpressure_policy: drop_oldest   # drop_oldest | drop_newest | block
  memory_budget_mb_per_scenario: 50  # Бюджет пам'яті per scenario (10-500 MB)
  scenario_timeout_sec: 5.0          # Таймаут per snapshot (0.5-60 сек)
  health_heartbeat_sec: 30.0         # Інтервал heartbeat (5-300 сек)

# --- Hot reload (для live shadow сесій) ---
hot_reload:
  enabled: false                     # true для live mode
  poll_interval_sec: 5.0             # Як часто перевіряти зміни (1-60 сек)
  debounce_sec: 2.0                  # Затримка перед reload (0.5-30 сек)
  rollback_on_error: true            # Відкатити при помилці

# --- Вхідний потік ---
input:
  source_mode: replay                # replay | live_tail
  stream_path: logs/alpha_input/alpha_input_v1.jsonl

# --- Сценарії ---
scenarios:
  - scenario_id: S01_AURORA_BASELINE
    enabled: true
    strategy_type: aurora             # aurora | mean_reversion | ensemble
    config_mode: override             # override | full_config
    base_refs:
      aurora: config/aurora/strategies/aurora.yaml
      alpha_search: config/alpha_search.yaml
    overrides: {}                     # Без змін — базовий сценарій
```

### Параметри runtime

| Параметр | Тип | За замовч. | Опис |
|----------|-----|-----------|------|
| `max_scenarios` | int | 20 | Максимальна кількість enabled сценаріїв |
| `parallelism` | str | `thread_pool` | `sequential` для дебагу, `thread_pool` для продакшену |
| `max_workers` | int | 4 | Кількість потоків у ThreadPoolExecutor |
| `queue_maxsize` | int | 4000 | Розмір черги ingest |
| `backpressure_policy` | str | `drop_oldest` | Що робити при переповненні черги |
| `scenario_timeout_sec` | float | 5.0 | Таймаут на обробку одного snapshot одним сценарієм |
| `health_heartbeat_sec` | float | 30.0 | Інтервал між heartbeat перевірками |

### Backpressure policy

| Policy | Поведінка | Коли використовувати |
|--------|-----------|---------------------|
| `drop_oldest` | При переповненні видаляє найстаріший елемент | Live shadow (важлива актуальність) |
| `drop_newest` | Відхиляє новий елемент при повній черзі | Коли важливий порядок |
| `block` | Блокує запис до звільнення місця | Replay (важлива повнота) |

---

## 16. Сценарії: типи стратегій та режими конфігурації

### Типи стратегій

#### Aurora (`strategy_type: aurora`)

Використовує AuroraScoringKernel. Базовий конфіг: `config/aurora/strategies/aurora.yaml`.

Типові overrides:
```yaml
overrides:
  aurora.decision.signal_threshold: 0.12        # Поріг сигналу
  aurora.decision.gates.anti_flat_sigma: 0.35   # Фільтр плоского ринку
  aurora.decision.signal_weights.obi: 0.30      # Вага OBI
  aurora.decision.feature_neutrals.obi: 0.50    # Нейтральне значення OBI
```

Потрібні features: `obi`, `delta_price`, `macro_resid`.

#### Mean Reversion (`strategy_type: mean_reversion`)

Mean reversion стратегія на базі технічних індикаторів. Базовий конфіг: `config/aurora/strategies/mean_reversion.yaml`.

Типові overrides:
```yaml
overrides:
  alpha_search_system.mean_reversion.rsi.oversold: 25     # Рівень перепроданості
  alpha_search_system.mean_reversion.rsi.overbought: 75   # Рівень перекупленості
  alpha_search_system.mean_reversion.weights.bb: 0.6      # Вага Bollinger Bands
  alpha_search_system.mean_reversion.weights.rsi: 0.2     # Вага RSI
```

Потрібні features: `bb_position`, `bb_width`, `rsi_14`, `price_sma_20_deviation`, `stoch_k`, `stoch_d`.

#### Ensemble (`strategy_type: ensemble`)

Комбінація кількох TA-моделей з динамічними вагами. Базовий конфіг: `config/alpha_search.yaml` + `config/alpha_search_system.yaml`.

Типові overrides:
```yaml
overrides:
  # Увімкнути моделі
  alpha_search.providers.ta_ensemble.ensemble.models.mean_reversion_v1.enabled: true
  alpha_search.providers.ta_ensemble.ensemble.models.momentum_v1.enabled: true
  alpha_search.providers.ta_ensemble.ensemble.models.volatility_v1.enabled: true
  # Налаштувати ваги
  alpha_search.providers.ta_ensemble.ensemble.models.mean_reversion_v1.weight: 0.7
  alpha_search.providers.ta_ensemble.ensemble.models.momentum_v1.weight: 0.2
  alpha_search.providers.ta_ensemble.ensemble.models.volatility_v1.weight: 0.1
```

Потрібні features: об'єднання features всіх увімкнених моделей.

### Режими конфігурації

#### Override mode (`config_mode: override`)

Бере базовий конфіг з `base_refs`, застосовує dot-path overrides.

```yaml
- scenario_id: S02_AURORA_AGGRESSIVE
  config_mode: override
  base_refs:
    aurora: config/aurora/strategies/aurora.yaml
    alpha_search: config/alpha_search.yaml
  overrides:
    aurora.decision.signal_threshold: 0.12     # dot-path -> значення
```

Переваги: швидкі ексерименти, мінімальна конфігурація.

Override-шляхи перевіряються через **allowlist** — не будь-який шлях дозволений. Дозволені шляхи визначені у `override_allowlist.py` per strategy type.

#### Full config mode (`config_mode: full_config`)

Завантажує повні YAML-файли з окремої директорії.

```yaml
- scenario_id: S01_AURORA_BASELINE
  config_mode: full_config
  scenario_config_dir: config/alpha_search/scenarios/S01_AURORA_BASELINE
```

Структура директорії сценарію:
```
config/alpha_search/scenarios/S01_AURORA_BASELINE/
  aurora.yaml              # Повний конфіг Aurora
  alpha_search.yaml        # Повний конфіг alpha_search
  alpha_search_system.yaml # Повний конфіг system
```

Переваги: повний контроль, можливість зберігати складні конфігурації.

---

## 17. Стандартний набір сценаріїв (10)

Матриця включає 10 попередньо налаштованих сценаріїв:

### Aurora family (S01-S04)

| ID | Назва | Опис |
|----|-------|------|
| S01 | `AURORA_BASELINE` | Базовий Aurora без змін — контрольна точка |
| S02 | `AURORA_AGGRESSIVE` | Знижений поріг (0.12), слабший anti-flat |
| S03 | `AURORA_CONSERVATIVE` | Підвищений поріг (0.20), жорсткий anti-fomo |
| S04 | `AURORA_OBI_HEAVY` | Підвищена вага OBI (0.30), зменшений depth_imbalance |

### Mean Reversion family (S11-S13)

| ID | Назва | Опис |
|----|-------|------|
| S11 | `MR_BASELINE` | Базовий Mean Reversion без змін |
| S12 | `MR_RSI_25_75` | RSI oversold=25, overbought=75 (вужчий діапазон) |
| S13 | `MR_BB_HEAVY` | Bollinger Bands вага 0.6, RSI 0.2 |

### Ensemble family (S15-S17)

| ID | Назва | Опис |
|----|-------|------|
| S15 | `ENSEMBLE_BALANCED` | Всі 3 моделі, рівні ваги |
| S16 | `ENSEMBLE_MR_DOMINANT` | MR=0.7, Momentum=0.2, Vol=0.1 |
| S17 | `ENSEMBLE_MOMENTUM_DOMINANT` | Momentum=0.6, MR=0.2, Vol=0.2 |

---

## 18. Вхідний контракт: alpha_input_v1

Кожен рядок у JSONL-файлі — один snapshot ринкових даних.

### Обов'язкові поля

| Поле | Тип | Опис |
|------|-----|------|
| `ts_ms` | int | Timestamp в мілісекундах (epoch) |
| `symbol` | str | Торгова пара, напр. `"BTCUSDT"` |
| `bar_close_ts` | int | Timestamp закриття бару (epoch ms) |
| `price` | float | Ціна (>0) |
| `features` | dict | Словник features (залежить від стратегії) |

### Опціональні поля

| Поле | Тип | За замовч. | Опис |
|------|-----|-----------|------|
| `tf_sec` | int | 300 | Timeframe в секундах (300 = 5m) |
| `regime` | str | `"DEFAULT"` | Режим ринку: `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `MEAN_REVERSION`, `TREND_UP`, `TREND_DOWN`, `UNCERTAIN`, `DEFAULT` |
| `warmup_status` | dict | `{}` | Статус прогріву per feature |
| `source_verb` | str | `""` | Евент-джерело (для трасування) |
| `source_trace_id` | str | `""` | Trace ID |

### Приклад JSONL рядка

```json
{"ts_ms": 1708800000000, "symbol": "BTCUSDT", "tf_sec": 300, "bar_close_ts": 1708800000000, "price": 51234.5, "features": {"obi": 0.15, "delta_price": 0.002, "macro_resid": -0.01, "bb_position": 0.65, "rsi_14": 58.3, "price_sma_20_deviation": 0.012}, "regime": "LOW_VOLATILITY"}
```

### Fail-closed правила

- Відсутнє обов'язкове поле → snapshot відхилено
- `price <= 0` → відхилено
- Невалідний JSON → відхилено (лічильник `snapshots_rejected` інкрементується)
- Порожній рядок → пропущено мовчки

---

## 19. Вихідні дані та артефакти

### Структура директорії сесії

```
logs/alpha_search_runtime/
  20260224_143215/                         <-- Session ID (YYYYMMDD_HHMMSS)
    aggregate/
      alpha_search_domain.log              <-- Головний лог процесу
      aggregate_metrics.csv                <-- CSV зі скорами всіх сценаріїв
      health.jsonl                         <-- Health events
      summary.jsonl                        <-- Фінальна статистика
    S01_AURORA_BASELINE/
      scores.jsonl                         <-- Скори цього сценарію
      trades.jsonl                         <-- Віртуальні трейди
      config_effective.yaml                <-- Ефективний конфіг після override
      health.jsonl                         <-- Per-scenario health
    S02_AURORA_AGGRESSIVE/
      scores.jsonl
      trades.jsonl
      config_effective.yaml
      health.jsonl
    ...
```

### aggregate_metrics.csv

Кожен рядок — один scoring event:

```csv
ts_ms,scenario_id,strategy_type,symbol,provider_id,model_name,score,confidence,threshold,side,regime,shadow
1708800000000,S01_AURORA_BASELINE,aurora,BTCUSDT,aurora,aurora_v2_adapter,0.23,0.78,0.15,BUY,LOW_VOLATILITY,true
```

### scores.jsonl (per scenario)

Один JSON-об'єкт на рядок:

```json
{"scenario_id": "S01_AURORA_BASELINE", "strategy_type": "aurora", "ts_ms": 1708800000000, "symbol": "BTCUSDT", "score": 0.23, "confidence": 0.78, "threshold": 0.15, "side": "BUY", "provider_id": "aurora", "model_name": "aurora_v2_adapter", "regime": "LOW_VOLATILITY", "shadow": true}
```

### config_effective.yaml

Ефективний конфіг сценарію після застосування всіх overrides:

```yaml
scenario_id: S02_AURORA_AGGRESSIVE
strategy_type: aurora
alpha_search:
  enabled: true
  shadow_mode: true
  providers:
    aurora:
      enabled: true
      threshold: 0.1
aurora:
  decision:
    signal_threshold: 0.12
    gates:
      anti_flat_sigma: 0.35
```

---

## 20. Моніторинг здоров'я

### HealthMonitor

Автоматично відстежує стан кожного сценарію:

| Статус | Значення | Умова |
|--------|----------|-------|
| `healthy` | Працює нормально | Є недавній heartbeat |
| `stale` | Немає нових даних | Heartbeat старший за `heartbeat_sec * 3` |
| `degraded` | Часткова відмова | 3+ послідовних failures |
| `unknown` | Ще не обробляв | Жодного heartbeat |

### Auto-recovery

Після `CONSECUTIVE_FAILURE_THRESHOLD` (3) послідовних помилок сценарій позначається як `degraded`. Перший успішний snapshot автоматично відновлює його до `healthy`.

### Heartbeat логи

Кожні `health_heartbeat_sec` секунд виводиться:
```
Heartbeat: processed=1500, health={'S01': 'healthy', 'S02': 'healthy', ...}, ingest={...}
```

---

## 21. Hot Reload (live mode)

Дозволяє змінювати конфігурацію сценаріїв без перезапуску процесу.

### Увімкнення

```yaml
hot_reload:
  enabled: true
  poll_interval_sec: 5.0
  debounce_sec: 2.0
  rollback_on_error: true
```

### Механізм

1. `ConfigWatcher` періодично перевіряє hash файлу `scenario_matrix.yaml`
2. При зміні hash — debounce (чекає `debounce_sec`)
3. Валідація нового конфіга (dry-run через Pydantic)
4. Safe-swap: нові/змінені сценарії запускаються, видалені — зупиняються
5. При помилці — автоматичний rollback до попередньої версії (`rollback_on_error: true`)

### Що можна змінювати на ходу

- Додавати/видаляти сценарії
- Змінювати override параметри сценарій
- Вмикати/вимикати сценарії (`enabled: true/false`)
- Змінювати кількість сценаріїв (10 -> 20 -> 12)

### Що НЕ можна змінювати без перезапуску

- `runtime.parallelism` (sequential <-> thread_pool)
- `input.source_mode` (replay <-> live_tail)
- `input.stream_path`

---

## 22. ShadowBook: віртуальний PnL

Кожен сценарій має свій `ShadowBook` для відстеження віртуальної прибутковості.

### Метрики

| Метрика | Опис |
|---------|------|
| `cumulative_pnl` | Сумарний PnL всіх віртуальних трейдів |
| `max_drawdown` | Максимальна просадка від піку |
| `sharpe_ratio` | Sharpe ratio (0 при < 2 трейдах або нульовій дисперсії) |
| `win_rate` | Відсоток прибуткових трейдів |
| `total_trades` | Загальна кількість трейдів |
| `wins` / `losses` | Кількість виграшних / програшних трейдів |

### Визначення сторони (side)

```
score >  threshold  -->  BUY
score < -threshold  -->  SELL
інакше              -->  NEUTRAL (не торгуємо)
```

---

## 23. Тестування

### Запуск тестів

```bash
# Всі тести alpha_search runtime
pytest apps/reference/domains/alpha_search/tests/ -v --tb=short

# Тільки швидкі unit-тести
pytest apps/reference/domains/alpha_search/tests/ -v -m "not slow and not integration" --tb=short

# Integration тести
pytest apps/reference/domains/alpha_search/tests/ -v -m "integration" --tb=short

# Slow тести (concurrency + performance)
pytest apps/reference/domains/alpha_search/tests/ -v -m "slow" --tb=short

# З coverage
pytest apps/reference/domains/alpha_search/tests/ --cov=apps/reference/domains/alpha_search/runtime --cov-report=term-missing
```

### Тест-файли (22 файли, ~267 тестів)

| Файл | Тести | Рівень | Що перевіряє |
|------|-------|--------|-------------|
| `test_contracts.py` | ~30 | T1 | Pydantic-контракти, extra="forbid", валідатори |
| `test_config_resolver.py` | ~28 | T1 | Override та full_config резолюція, dot-path, allowlist |
| `test_override_allowlist.py` | ~18 | T1 | Allowlist per strategy, fnmatch wildcards |
| `test_scenario_worker.py` | ~20 | T1 | Scoring, self-triggering, inject params, determine_side |
| `test_scenario_manager.py` | ~18 | T2 | Ініціалізація, fan-out, shutdown, ізоляція |
| `test_shadow_book.py` | ~12 | T2 | PnL, drawdown, Sharpe, win rate |
| `test_backtest_plugin_integration.py` | ~8 | T2 | _extract_payload fix, LocalBus, multi-provider |
| `test_executor.py` | ~16 | T3 | Sequential/parallel execution, timeouts, stats |
| `test_backpressure.py` | ~14 | T3 | drop_oldest/newest/block, thread safety |
| `test_health_monitor.py` | ~12 | T3 | Heartbeat, degradation, recovery |
| `test_ingest_gateway.py` | ~8 | T3 | Replay, live_tail, invalid data handling |
| `test_logger_factory.py` | ~8 | T4 | Per-scenario loggers, score writers |
| `test_reporting.py` | ~8 | T4 | CSV, JSONL, aggregate stats |
| `test_feature_mirror_writer.py` | ~10 | T4 | Feature mirror, regime cache, symbol filter |
| `test_hot_reload.py` | ~11 | T4 | Hash detection, reload, rollback |
| `test_launcher.py` | ~12 | T4 | Config load, logging, path resolution |
| `test_integration_flows.py` | ~10 | X-cut | End-to-end pipeline, multi-scenario |
| `test_regression.py` | ~8 | X-cut | Guards проти 4 виправлених багів |
| `test_scoring_parity.py` | ~5 | X-cut | Парність з embedded plugin |
| `test_concurrency.py` | ~5 | X-cut | Deadlock-free 10/20 scenarios |
| `test_performance.py` | ~4 | X-cut | Latency, throughput, memory |

### Маркери

| Маркер | Опис |
|--------|------|
| `@pytest.mark.unit` | Швидкі ізольовані тести (<1с кожний) |
| `@pytest.mark.integration` | Потребують реальні конфіг-файли |
| `@pytest.mark.slow` | Concurrency та performance (>1с) |
| `@pytest.mark.asyncio` | Async тести (live_tail) |

---

## 24. Створення нового сценарію

### Крок 1: Визначити стратегію

Обрати одну з: `aurora`, `mean_reversion`, `ensemble`.

### Крок 2: Додати до scenario_matrix.yaml

```yaml
scenarios:
  # ... існуючі сценарії ...

  - scenario_id: S05_AURORA_CUSTOM         # Унікальний ID (обов'язково)
    enabled: true                          # true/false
    strategy_type: aurora                  # aurora | mean_reversion | ensemble
    config_mode: override                  # override | full_config
    base_refs:                             # Базові конфіги (для override mode)
      aurora: config/aurora/strategies/aurora.yaml
      alpha_search: config/alpha_search.yaml
    overrides:                             # Dot-path overrides
      aurora.decision.signal_threshold: 0.18
      aurora.decision.signal_weights.obi: 0.25
```

### Крок 3: Перевірити валідність

```bash
python -c "
from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config
from pathlib import Path
cfg = load_matrix_config(Path('config/alpha_search/scenario_matrix.yaml'))
print(f'OK: {len([s for s in cfg.scenarios if s.enabled])} enabled scenarios')
for s in cfg.scenarios:
    print(f'  {s.scenario_id}: {s.strategy_type} [{\"ON\" if s.enabled else \"OFF\"}]')
"
```

### Крок 4: Запустити

```bash
python scripts/run_alpha_search_domain.py
```

---

## 25. Troubleshooting

### Проблема: "Scenario matrix not found"

```
FileNotFoundError: Scenario matrix not found: .../scenario_matrix.yaml
```

**Рішення:** Перевірте шлях до файлу матриці. За замовчуванням: `config/alpha_search/scenario_matrix.yaml`.

### Проблема: "No workers initialized"

```
ERROR: No workers initialized. Exiting.
```

**Причини:**
- Всі сценарії мають `enabled: false`
- Конфіг-файли з `base_refs` не знайдені
- Pydantic валідація провалилася для всіх сценаріїв

**Рішення:** Перевірте `--log-level DEBUG` для детальних помилок ініціалізації кожного сценарію.

### Проблема: ValidationError при завантаженні матриці

```
pydantic_core._pydantic_core.ValidationError: ...
```

**Типові причини:**
- `extra="forbid"` — зайвий ключ у YAML
- `scenario_timeout_sec` < 0.5 або > 60
- `health_heartbeat_sec` < 5 або > 300
- `max_scenarios` < 1 або > 50
- Дублікат `scenario_id`
- Override mode без `base_refs`
- Full_config mode без `scenario_config_dir`

### Проблема: Сценарій degraded

```
Heartbeat: health={'S02': 'degraded', ...}
```

**Причина:** 3+ послідовних помилок обробки snapshot у цьому сценарії.

**Рішення:** Перевірте `logs/alpha_search_runtime/<session>/S02_*/health.jsonl` для деталей помилок. Часто це відсутні features або невалідний конфіг.

### Проблема: Пустий scores.jsonl

**Можливі причини:**
1. Для Aurora: відсутні `obi`, `delta_price` або `macro_resid` у features
2. Для MR: відсутні `bb_position`, `rsi_14` та інші
3. Provider не увімкнений у конфігу
4. Snapshot відхилений на етапі IngestGateway (невалідний JSON або schema)

**Діагностика:**
```bash
# Перевірити ingest stats
grep "Heartbeat" logs/alpha_search_runtime/<session>/aggregate/alpha_search_domain.log

# Перевірити rejected snapshots
grep "reject" logs/alpha_search_runtime/<session>/aggregate/alpha_search_domain.log
```

---

## 26. Файлова структура (повна)

```
apps/reference/domains/alpha_search/
  __init__.py
  alpha_model.py              -- AlphaModel ABC, AlphaScore DTO, Registry
  backtest_plugin.py          -- AlphaSearchBacktestPlugin (shadow daemon)
  config_models.py            -- Pydantic config + YAML loader
  ensemble.py                 -- EnsembleModel + dynamic weights
  wal_listener.py             -- WAL writer
  alpha_search_log_adapter.py -- Log adapter
  README.md                   -- Цей файл
  models/
    __init__.py
    aurora_adapter.py         -- AuroraAlphaAdapter
    momentum.py               -- MomentumAlphaModel
    mean_reversion.py         -- MeanReversionAlphaModel
    volatility.py             -- VolatilityAlphaModel
  runtime/                    -- Standalone Runtime модулі
    __init__.py
    backpressure.py           -- BoundedIngestQueue (3 policy)
    config_resolver.py        -- Override + full_config resolution
    contracts.py              -- Pydantic strict контракти
    executor.py               -- Sequential/ThreadPool executor
    feature_mirror_writer.py  -- Live feature mirror
    health.py                 -- HealthMonitor
    hot_reload.py             -- ConfigWatcher + safe-swap
    ingest.py                 -- IngestGateway (replay / live_tail)
    launcher.py               -- Точка входу reactor
    logger_factory.py         -- Per-scenario loggers
    override_allowlist.py     -- Allowlist per strategy type
    reporting.py              -- Aggregate CSV/JSONL reporter
    runbook.py                -- Operational utilities
    scenario_manager.py       -- Worker lifecycle management
    scenario_worker.py        -- Per-scenario scoring
    shadow_book.py            -- Virtual PnL tracking
  tests/                      -- 22 тест-файли (~267 тестів)
    __init__.py
    conftest.py               -- Shared fixtures
    test_*.py                 -- Тест-модулі (див. розділ 23)

config/alpha_search/
  scenario_matrix.yaml        -- SSOT: сценарна матриця

scripts/
  run_alpha_search_domain.py  -- CLI entry point
```

---

## 27. Глосарій (розширений)

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
| **Scenario Matrix** | YAML-файл що визначає набір паралельних сценаріїв для shadow-тестування |
| **Override mode** | Режим конфігурації: базовий конфіг + dot-path дельти |
| **Full config mode** | Режим конфігурації: повні YAML-файли з окремої директорії |
| **Fan-out** | Розсилка одного snapshot до всіх активних воркерів |
| **ShadowBook** | Per-scenario трек віртуальних позицій та PnL |
| **Backpressure** | Механізм обмеження навантаження при переповненні черги |
| **Hot reload** | Зміна конфіга сценаріїв без перезапуску процесу |
| **Degraded** | Стан сценарію після 3+ послідовних помилок |
| **Heartbeat** | Періодична перевірка стану (alive/stale/degraded) |
| **SSOT** | Single Source of Truth — єдине джерело правди |
| **Allowlist** | Список дозволених dot-path override шляхів per strategy type |
