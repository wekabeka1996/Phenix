# 📘 Alpha Search Standalone Runbook & Quick Start

This runbook is intentionally scoped to the standalone runner path under `scripts/runners/run_alpha_search_domain.py` and `apps/reference/domains/alpha_search/runtime/`.

It is not the full domain authority document for alpha_search. For the current dual-shape domain model, embedded `main.py` integration, judge shadow ownership, and offline simulator boundaries, use `apps/reference/domains/alpha_search/docs/README.md`.

## 1. Огляд standalone path

**Alpha Search standalone runner** — це окремий shadow або replay analysis path для 12 різних сценаріїв:
- **Aurora** сценарії (S03, S05, S06, S20) — детектують мікроструктуру та макро-аномалії
- **Mean Reversion** сценарії (S01, S11, S12, S13) — сигналізують про повернення до середнього
- **Ensemble** сценарії (S15, S18, S19, S21) — комбінують декілька моделей з динамічним зважуванням

**Основний вихід standalone path**: `scores.jsonl`, `aggregate_metrics.csv`, session logs, shadow metrics, та інші analysis artifacts під `logs/alpha_search_runtime/`.

Embedded plugin path у `apps/reference/main.py` окремо використовує `config/alpha_search.yaml` і може емiтити runtime `EVT:ALPHA_SCORE_CALCULATED` events when configured. Цей quickstart не є authority для embedded path.

---

## 2. РЕЖИМИ ЗАПУСКУ

### 2.1 REPLAY MODE (Offline — Аналізування логів)

Використовується для **бектестування** або **аналізу** накопленої історії.

**Конфігурація** (config/alpha_search/scenario_matrix.yaml):
```yaml
input:
  source_mode: replay       # ← Синхронне чтение з файлу
  stream_path: logs/alpha_input/alpha_input_v1.jsonl
```

**Підготовка даних**:
```bash
# 1. Побудувати JSONL з CSV рекордів (data/recorder/*.csv → alpha_input.jsonl)
python tools/alpha_search/build_alpha_input.py

# 2. Перевірити що файл існує:
ls -lh logs/alpha_input/alpha_input_v1.jsonl
# Output: -rw-r--r-- 257.4K logs/alpha_input/alpha_input_v1.jsonl
```

**Запуск**:
```bash
# З аргументами за замовчанням (matrix, log level)
python scripts/runners/run_alpha_search_domain.py --log-level INFO

# Або з кастомною матрицею сценаріїв
python scripts/runners/run_alpha_search_domain.py \
  --matrix config/alpha_search/scenario_matrix.yaml \
  --log-level DEBUG
```

**Вихід**:
```
logs/alpha_search_runtime/
  └── 20260417_004222/           # Session ID (YYYYMMDD_HHMMSS)
      ├── aggregate/
      │   ├── alpha_search_domain.log        # Логи запуску
      │   └── aggregate_metrics.csv          # Агреговані метрики по всім сценаріям
      ├── S01_MR_RSI_HEAVY/
      │   ├── config_effective.yaml          # Ефективна конфігурація сценарію
      │   └── scores.jsonl                   # Детальні результати сигналів
      ├── S03_AURORA_15M_APPROX/
      │   ├── config_effective.yaml
      │   └── scores.jsonl
      └── ... (решта 10 сценаріїв)
```

**Що змотри у результатах**:
- `aggregate_metrics.csv`: Per-snapshot аналітика
  - `scenario_id`, `symbol`, `side` (LONG/SHORT/NEUTRAL), `confidence`, `score`, `regime`
- `logs/alpha_search_runtime/{session}/aggregate/alpha_search_domain.log`
  - Ensemble rebalancing events (динамічні ваги моделей)
  - Heartbeat messages (progress)
  - Errors/warnings

---

### 2.2 LIVE_TAIL MODE (Online input tailing alongside main.py)

Використовується для near-real-time standalone shadow analysis, коли standalone runner tail-ить mirrored input file, який підтримує `main.py` path.

**Конфігурація** (config/alpha_search/scenario_matrix.yaml):
```yaml
input:
  source_mode: live_tail        # ← Async слідкування за файлом
  stream_path: logs/alpha_input/alpha_input_v1.jsonl
```

**Підготовка**:
1. **Запустити `main.py` path**, який writes mirrored feature snapshots via `FeatureMirrorWriter`:
```bash
python apps/reference/main.py --mode live
```

`FeatureMirrorWriter` writes snapshots into `logs/alpha_input/alpha_input_v1.jsonl`, який standalone runner потім tail-ить.

2. **Паралельно запустити alpha_search** (в іншому терміналі):
```bash
python scripts/runners/run_alpha_search_domain.py --log-level INFO
```

**Як це працює**:
```
main.py (live)
  ├─ feature_engineering → EVT:FEATURES_CALCULATED
  ├─ FeatureMirrorWriter appends to alpha_input_v1.jsonl
  └─ execution_position

alpha_search (live_tail)
  ├─ Async monitors alpha_input_v1.jsonl
  ├─ Processes new snapshots in real-time
  └─ Writes standalone score and aggregate artifacts for analysis
```

**Вихід**: Той же path як replay, але файлі не мають фіксованого розміру.

---

## 3. SHADOW ТОРГІВЛЯ

Всі сценарії запускаються в **shadow mode** за замовчанням:
```yaml
alpha_search:
  shadow_mode: true  # config/alpha_search.yaml
```

Це означає:
- ✅ Сигнали **генеруються** для всіх 12 сценаріїв
- ✅ **Не виконуються** реальні ордери
- ✅ Розраховується **virtual PnL** (для аналізу)

**Shadow metrics** з `shadow_book.py`:
```python
{
    "scenario_id": "S21_ENSEMBLE_REGIME_ADAPTIVE",
    "total_trades": 1234,
    "wins": 567,
    "losses": 667,
    "win_rate": 0.4595,
    "cumulative_pnl": 1234.56,        # Virtual USD
    "max_drawdown": 456.78,
    "sharpe_ratio": 0.89,
    "avg_pnl_per_trade": 1.00,
    "notional_size": 1000.0           # Per-trade size
}
```

**Де дивитися результати shadow торгівлі**:
- `scores.jsonl` в кожному сценарію має поле `pnl` (якщо позиція закрита)
- `aggregate_metrics.csv` містить per-snapshot результати
- Логи показують ensemble rebalancing на основі performance

---

## 4. ПАРАМЕТРИ ЗАПУСКУ

### 4.1 CLI аргументи

```bash
python scripts/runners/run_alpha_search_domain.py \
  --matrix CONFIG_PATH      # default: config/alpha_search/scenario_matrix.yaml
  --log-level LEVEL         # choices: DEBUG | INFO | WARNING | ERROR (default: INFO)
```

### 4.2 Конфігурація матриці (scenario_matrix.yaml)

**Key sections**:

#### `matrix_id` & `version`
```yaml
matrix_id: v6b_dedup_noflip_cooldown_20260307
version: 8
```

#### `runtime` — Паралелізм та ресурси
```yaml
runtime:
  max_scenarios: 12                    # Максимум активних сценаріїв
  parallelism: thread_pool             # thread_pool | sequential
  max_workers: 4                       # Рабочих потоків
  queue_maxsize: 4000                  # Buffer для ingest
  backpressure_policy: drop_oldest     # drop_oldest | drop_newest | block
  memory_budget_mb_per_scenario: 50    # Per-scenario RAM limit
  health_heartbeat_sec: 30.0           # Interval для heartbeat логів
```

**Рекомендації для наладу**:
- 🚀 **Швидка локальна аналіза**: `max_workers=1, parallelism=sequential`
- 📊 **Повна батьківська машина**: `max_workers=4, parallelism=thread_pool`
- 🔥 **Live режим на production**: `parallelism=thread_pool, memory_budget_mb_per_scenario=100+`

#### `scenarios` — Список сценаріїв
```yaml
scenarios:
  - scenario_id: S01_MR_RSI_HEAVY
    enabled: true                  # Toggle поточний сценарій
    strategy_type: mean_reversion  # Тип стратегії
    config_mode: override          # Перекрити параметри
    base_refs:
      mean_reversion: config/aurora/strategies/mean_reversion.yaml
      alpha_search: config/alpha_search.yaml
    overrides:                     # Специфічні параметри
      alpha_search_system.mean_reversion.weights.rsi: 0.55
      alpha_search.providers.aurora.threshold: 0.28
```

**Як disable сценарій**:
```yaml
- scenario_id: S01_MR_RSI_HEAVY
  enabled: false    # ← Пропускається при запуску
```

---

## 5. АНАЛІЗ РЕЗУЛЬТАТІВ

### 5.1 Структура CSV (aggregate_metrics.csv)

```csv
timestamp,scenario_id,strategy_type,symbol,ts_ms,score,confidence,threshold,side,provider_id,regime
1776375744.9,S01_MR_RSI_HEAVY,mean_reversion,SOLUSDT,1770567479999,0.0,0.0,0.28,NEUTRAL,aurora,PENDING
1776375744.97,S01_MR_RSI_HEAVY,mean_reversion,SOLUSDT,1770567599999,0.0,0.0,0.28,NEUTRAL,aurora,PENDING
```

**Колонки**:
- `timestamp`: Unix time запуску сценарію
- `scenario_id`: S01_MR_RSI_HEAVY, S03_AURORA_15M_APPROX, ...
- `side`: **LONG** (buy signal), **SHORT** (sell signal), **NEUTRAL** (no signal)
- `confidence`: [0.0, 1.0] — впевненість у сигналі
- `score`: [-1.0, 1.0] — сила та напрямок сигналу
- `regime`: PENDING, UNCERTAIN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY
- `provider_id`: который провайдер генерував сигнал (aurora, ta_ensemble, judge_expert)

### 5.2 Структура JSONL (per-scenario scores.jsonl)

```json
{
  "ts": 1776375744.93,
  "scenario_id": "S01_MR_RSI_HEAVY",
  "strategy_type": "mean_reversion",
  "ts_ms": 1770567479999,
  "symbol": "SOLUSDT",
  "score": 0.0,
  "confidence": 0.0,
  "threshold": 0.28,
  "side": "NEUTRAL",
  "provider_id": "aurora",
  "model_name": "aurora_quadratic_adapter",
  "why": ["fail_closed:PILLAR_WARMUP", "Aurora deferred: PILLAR_WARMUP"],
  "features_used": [],
  "shadow": true,
  "regime": "PENDING"
}
```

**Ключові поля**:
- `why`: Ланцюжок обґрунтування (чому NEUTRAL?)
- `shadow`: `true` (звичайно) — сигнал не торгується
- `features_used`: Ознаки, що були включені в розрахунок

### 5.3 Анализ з Python

```python
import pandas as pd

df = pd.read_csv("logs/alpha_search_runtime/20260417_004222/aggregate/aggregate_metrics.csv")

# Сигнали по сценарію
for sid in df['scenario_id'].unique():
    s_data = df[df['scenario_id'] == sid]
    long = len(s_data[s_data['side'] == 'LONG'])
    short = len(s_data[s_data['side'] == 'SHORT'])
    neutral = len(s_data[s_data['side'] == 'NEUTRAL'])
    print(f"{sid}: LONG={long}, SHORT={short}, NEUTRAL={neutral}")

# Топ сигнали за впевненістю
top = df[df['side'].isin(['LONG', 'SHORT'])].nlargest(10, 'confidence')
print(top[['scenario_id', 'symbol', 'side', 'confidence', 'regime']])

# Розподіл режимів
df['regime'].value_counts()
```

---

## 6. ТИПОВІ ОПЕРАЦІЇ

### 6.1 Запуск локального тесту (15 хвилин)

```bash
# 1. Перебудувати дані з останнього тижня
python tools/alpha_search/build_alpha_input.py

# 2. Запустити в режимі REPLAY з одним робочим потоком
python scripts/runners/run_alpha_search_domain.py --log-level INFO

# 3. Дивитись логи в реальному часі
tail -f logs/alpha_search_runtime/20260417_*/aggregate/alpha_search_domain.log
```

### 6.2 Live shadow trading (на 8+ годин)

```bash
# Terminal 1: Запустити main.py
python apps/reference/main.py --mode live

# Terminal 2: Запустити alpha_search
python scripts/runners/run_alpha_search_domain.py --log-level INFO

# Terminal 3: Дивитись progress
watch -n 5 'tail -20 logs/alpha_search_runtime/*/aggregate/alpha_search_domain.log'
```

### 6.3 Порівняти 3 сценарії

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("logs/alpha_search_runtime/20260417_004222/aggregate/aggregate_metrics.csv")

# Фільтр по 3 сценаріям
scenarios = ['S15_ENSEMBLE_BALANCED', 'S20_AURORA_MICROSTRUCTURE_DEPTH', 'S21_ENSEMBLE_REGIME_ADAPTIVE']
comparison = df[df['scenario_id'].isin(scenarios)]

# Графік confidence за часом
for sid in scenarios:
    s_data = comparison[comparison['scenario_id'] == sid]
    plt.plot(s_data['ts_ms'], s_data['confidence'], label=sid, alpha=0.7)

plt.legend()
plt.xlabel("Time")
plt.ylabel("Confidence")
plt.show()
```

### 6.4 Вимкнути деякі сценарії

Редагувати `config/alpha_search/scenario_matrix.yaml`:
```yaml
scenarios:
  - scenario_id: S01_MR_RSI_HEAVY
    enabled: false  # ← Вимкнути
  - scenario_id: S03_AURORA_15M_APPROX
    enabled: true
  # ... решта сценаріїв
```

Потім:
```bash
python scripts/runners/run_alpha_search_domain.py
# Буде запущено лише S03 та решта `enabled: true`
```

---

## 7. РЕЖИМИ ОТЛАДКИ

### DEBUG логи
```bash
python scripts/runners/run_alpha_search_domain.py --log-level DEBUG
```

Виведе:
- Детальну інформацію про feature cache
- Ensemble rebalancing вагів на кожному кроці
- Per-provider сигнали перед агреганням

### Слідкування за памяттю
```bash
# Додати в запуск
python -m memory_profiler scripts/runners/run_alpha_search_domain.py --log-level INFO
```

### Обмеження на час
```bash
# Запустити лише 5 хвилин (корисно для тесту)
timeout 300 python scripts/runners/run_alpha_search_domain.py --log-level INFO
```

---

## 8. ДОКУМЕНТАЦІЯ

- **[README.md](./apps/reference/domains/alpha_search/docs/README.md)** — Canonical current-domain entrypoint
- **[ATLAS.md](./apps/reference/domains/alpha_search/docs/ATLAS.md)** — Архітектура, межі, runtime shapes, ownership
- **[ARCHITECTURE.md](./apps/reference/domains/alpha_search/docs/ARCHITECTURE.md)** — Embedded plugin path, standalone path, simulator, failure semantics
- **[ALGORITHMS_AND_MATH.md](./apps/reference/domains/alpha_search/docs/ALGORITHMS_AND_MATH.md)** — Формули для scoring families
- **[EVENT_CONTRACTS.md](./apps/reference/domains/alpha_search/docs/EVENT_CONTRACTS.md)** — Runtime event surface versus offline artifacts
- **[TESTING.md](./apps/reference/domains/alpha_search/docs/TESTING.md)** — Test slices for plugin, judge, simulator, and standalone runtime

---

## 9. FAQ

**Q: Що робити якщо немає даних (STARTUP WARNING)?**
A: Запустити `python tools/alpha_search/build_alpha_input.py` або використовувати `live_tail` з `main.py`.

**Q: Як додати новий сценарій?**
A: Додати в `config/alpha_search/scenario_matrix.yaml` під `scenarios:` з `scenario_id`, `strategy_type`, `overrides`.

**Q: Як переключити на LIVE режим з комп'ютера?**
A: Змінити `source_mode: live_tail` в scenario_matrix.yaml та переконатися що `main.py` запущений з FeatureMirrorWriter.

**Q: Які символи підтримуються?**
A: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (задано в config/alpha_search.yaml).

**Q: Яка різниця між replay та live_tail?**
A: **Replay** — синхронне читання з фіксованого файла (бектест), **live_tail** — асинхронне слідкування за файлом, який растет (реальний час).

---

✅ **Готово!** Тепер ви можете запускати standalone alpha_search runner у replay або live_tail режимі і аналізувати результати без змішування цього runbook з embedded plugin authority.
