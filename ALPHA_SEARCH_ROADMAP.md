# Alpha Search Domain — Дорожня Карта Розвитку
**Версія:** 1.1 | **Дата:** 2026-03-01
**Автори:** Claude Sonnet (Forensic Analysis) + Gemini CLI (Architect & Quant)
**Статус:** ЗАТВЕРДЖЕНО ДО ВИКОНАННЯ

---

## КОНТЕКСТ ТА СТАРТОВА ТОЧКА

### Поточний стан системи після forensics

**Aurora Core FSM** перебуває в режимі `hybrid_live_data_testnet_exec`.
Баланс: **93.63 USDT** (-53.1% drawdown) — збиток спричинений виключно **H2 (NRR-046 дедлок)**, не alpha_search.

До початку цієї дорожньої карти три критичних фікси вже застосовані:

| Фікс | Файл | Що вирішує |
|------|------|-----------|
| `ensemble.py:get_required_features()` | `apps/reference/domains/alpha_search/ensemble.py:109-125` | Агрегує required features з дочірніх моделей замість повернення `[]` |
| `backtest_plugin.py` gate upgrade | `apps/reference/domains/alpha_search/backtest_plugin.py:391-408` | Скіпує провайдер якщо БУДЬ-ЯКА required feature відсутня + WARNING + dlog |
| H4 MagicMock fix | `tests/domains/execution_position/test_bracket_health_check.py:49` | `config={}` замість `config=fsm_config` — MagicMock leak закритий |

**H2 (NRR-046) залишається відкритим** — це окремий трек, описаний в `execution_journal.md`.

---

## АРХІТЕКТУРНИЙ БАЗИС ALPHA_SEARCH

### Два режими роботи

```
┌─────────────────────────────────────────────────────────────────┐
│  РЕЖИМ 1: Sidecar (BacktestPlugin)                              │
│  Підключений до Aurora event bus                                │
│  EVT:FEATURES_CALCULATED → backtest_plugin → EVT:ALPHA_SCORE    │
│  Файл: apps/reference/domains/alpha_search/backtest_plugin.py   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  РЕЖИМ 2: Standalone Runtime                                     │
│  Повністю ізольований процес                                    │
│  Entry: scripts/run_alpha_search_domain.py                      │
│  Читає: logs/alpha_input/alpha_input_v1.jsonl (live_tail/replay) │
│  Пише: FeatureMirrorWriter (Aurora bus → JSONL)                 │
│  Config: config/alpha_search/scenario_matrix.yaml               │
└─────────────────────────────────────────────────────────────────┘
```

### Поточний стан сценаріїв (після фіксів)

| Сценарій | Провайдер | Стан | Причина |
|----------|-----------|------|---------|
| S01_BASELINE | aurora | **АКТИВНИЙ** | `feat_obi`, `feat_delta_price`, `feat_macro_resid` присутні |
| S03_CONSERVATIVE | aurora | **АКТИВНИЙ** | Те саме |
| S05_MY_BEST | aurora | **АКТИВНИЙ** | Те саме |
| S06_LOW_THRESHOLD | aurora | **АКТИВНИЙ** | Те саме |
| S20_OBI_VERY_HEAVY | aurora | **АКТИВНИЙ** | Те саме |
| S11_MR_BASELINE | mean_reversion | SKIPPED | `rsi_14`, `bb_position` відсутні → `PROVIDER_SKIPPED_MISSING_FEATURES` |
| S12_MR_RSI_25_75 | mean_reversion | SKIPPED | Те саме |
| S13_MR_BB_HEAVY | mean_reversion | SKIPPED | Те саме |
| S15_BALANCED | ensemble | SKIPPED | TA features відсутні |
| S18_MOMENTUM_AGGRESSIVE | ensemble | SKIPPED | Те саме |
| S19_MR_SHORT_BIAS | ensemble | SKIPPED | Те саме |
| S21_REGIME_ADAPTIVE | ensemble | SKIPPED | Те саме |

### Підтверджені дані в data/recorder

Файл `data/recorder/YYYY-MM-DD/BTCUSDT_300.csv` містить:

**Мікроструктурні фічі (вже у Aurora config):**
`feat_obi`, `feat_tfi`, `feat_delta_price`, `feat_ema_bias`, `feat_depth_imbalance`,
`feat_macro_resid`, `feat_macro_sync`, `feat_volatility_state`, `feat_volume_spike`,
`feat_liquidity_kappa`

**Нові фічі (НЕ у Aurora config — потенційна нова альфа):**
`feat_absorption`, `feat_large_trade_imbalance`, `feat_spread_bps`, `feat_volume_zscore`

**Price momentum (вже розраховані):**
`pm_norm` (нормалізований), `pm_raw` (сирий)

**Метадані якості:**
`ready` (bool), `not_ready_reasons` (str), `regime`, `regime_conf` (float)

**calibrate_aurora_signal_weights.py вже фільтрує:**
```python
df = df[df["ready"] == True]
df = df[not_ready_reasons.str.len() == 0]
```
Look-ahead bias відсутній — фічі записані на момент закриття бару.

---

## ДОРОЖНЯ КАРТА

> **Порядок виконання (скоригований v1.1):**
> `Phase B → Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 (повний) → Phase 5`
> Phase B виконується **першою** — до будь-яких змін коду чи конфіга.
> Це еталон для вимірювання покращень на всіх наступних фазах.

---

### ФАЗА B — Baseline Measurement (ПЕРШОЧЕРГОВО / НЕ ПОТРІБЕН КОД)

**Ціль:** Зафіксувати поточний стан системи до будь-яких змін. Дає еталон для порівняння після Phase 1 (калібрування) та Phase 2/3 (нові моделі).

**Чому зараз:** `virtual_trader.enabled: true` вже встановлений в `config/alpha_search.yaml:125`.
Standalone runtime вже генерує PnL/WinRate/Sharpe/DD для 5 активних Aurora-сценаріїв.

#### B.1 Запуск baseline

```bash
python scripts/run_alpha_search_domain.py \
  --matrix config/alpha_search/scenario_matrix.yaml \
  --log-level INFO
```

#### B.2 Зафіксувати метрики по 5 активних сценаріях

Результати знаходяться в:
```
logs/alpha_search_runtime/<session_id>/
├── S01_AURORA_BASELINE/trades.jsonl
├── S03_CONSERVATIVE/trades.jsonl
├── S05_MY_BEST/trades.jsonl
├── S06_LOW_THRESHOLD/trades.jsonl
└── S20_OBI_VERY_HEAVY/trades.jsonl
```

Або через summary інструмент:
```bash
python tools/alpha_search_runtime_summary.py \
  --session-dir logs/alpha_search_runtime/<session_id>
```

#### B.3 Записати baseline таблицю

| Сценарій | Win Rate | Cumulative PnL | Sharpe | Max DD | Total Trades |
|----------|----------|---------------|--------|--------|-------------|
| S01_AURORA_BASELINE | ? | ? | ? | ? | ? |
| S03_CONSERVATIVE | ? | ? | ? | ? | ? |
| S05_MY_BEST | ? | ? | ? | ? | ? |
| S06_LOW_THRESHOLD | ? | ? | ? | ? | ? |
| S20_OBI_VERY_HEAVY | ? | ? | ? | ? | ? |

> Заповнити після запуску. Ця таблиця — KPI для оцінки Phase 1 та Phase 2/3.

**7 мертвих сценаріїв (S11–S21)** залишатимуться SKIPPED до Phase 2/3 — це очікувана поведінка.

---

### ФАЗА 0 — Передумова: H2 Fix (КРИТИЧНО / БЛОКУЄ LIVE TRADING)

> Ця фаза не входить до alpha_search roadmap, але є обов'язковою передумовою
> для повернення системи в прибуткову роботу.

**Ціль:** Виправити NRR-046 дедлок щоб flip/close ордери проходили при `entry_order_type = "LIMIT"`.

**Два варіанти реалізації (вибрати один):**

- **Варіант A (поліція контракту):** Додати окремий `close_order_type` в конфіг, відокремити від `entry_order_type`. Reduce-only close завжди використовує `MARKET` або `IOC` — без потреби у `tf_sec`.
- **Варіант B (pass-through):** Передавати `tf_sec` з поточного бар-контексту в `_emit_reduce_only_close` та `_handle_regime_flip`. Вимагає зберігання останнього `tf_sec` на рівні символу в DM.

**Файли для зміни:**
- `apps/reference/domains/decision_making/decision_making.py:3820` (`_emit_reduce_only_close`)
- `apps/reference/domains/decision_making/decision_making.py:2519` (`_handle_regime_flip`)
- `apps/reference/domains/execution_position/schemas/` (створити `cmd_close_v1.json`)

**Тести для написання:**
- Flip close з `entry_order_type = "LIMIT"` + без `tf_sec` → NRR-046
- Flip close з `entry_order_type = "LIMIT"` + `tf_sec` переданий → успіх
- Видалити mock `_propose_trade_intent` з усіх 3 flip-test файлів
- Додати `entry_order_type = "LIMIT"` у всі flip-test фікстури

---

### ФАЗА 1 — Калібрування ваг Aurora (НЕГАЙНО / БЕЗ НОВОГО КОДУ)

**Ціль:** Знайти оптимальні `signal_weights` для 5 активних Aurora-сценаріїв на основі historical PnL через Ridge regression.

**Вхідні дані:** `data/recorder/*/BTCUSDT_300.csv` (та інші символи)
**Інструмент:** `tools/calibrate_aurora_signal_weights.py`
**Вихід:** YAML-сніпет з новими `signal_weights` для `config/aurora/strategies/aurora.yaml`

#### 1.1 Базове калібрування (існуючі фічі)

```bash
# Основні пари
python tools/calibrate_aurora_signal_weights.py \
  --recorder-dir data/recorder \
  --symbols BTCUSDT ETHUSDT SOLUSDT \
  --tf-sec 300 \
  --horizon-bars 1

# Альткоїни
python tools/calibrate_aurora_signal_weights.py \
  --recorder-dir data/recorder \
  --symbols DOGEUSDT XRPUSDT \
  --tf-sec 300 \
  --horizon-bars 1
```

**Що отримаємо:** Відкоригований внесок `obi`, `tfi`, `delta_price`, `macro_resid`, `ema_bias` тощо.
Якщо `regime_conf` ≥ порогу — зважувати результати по confidence режиму.

#### 1.2 Пошук нової альфи (Ridge discovery)

Тимчасово додати нульові ваги для невідомих фічей в `aurora.yaml`:

```yaml
# config/aurora/strategies/aurora.yaml — тимчасово для discovery
signal_weights:
  # ... існуючі ...
  absorption: 0.0
  large_trade_imbalance: 0.0
  volume_zscore: 0.0
```

Запустити calibration — Ridge regression автоматично оцінить ці фічі.
Якщо результат ненульовий і стабільний → впровадити в бойовий конфіг.

**Очікування:** `feat_large_trade_imbalance` і `feat_absorption` мають потенційно вищий predicting power ніж `feat_obi` для моментум-режимів.

#### 1.3 Горизонти прогнозування

Запустити калібрування для різних `--horizon-bars`:
- `1` (5 хв) — short-term momentum
- `3` (15 хв) — medium-term
- `6` (30 хв) — swing

Порівняти Sharpe Ratio через AggregateReporter для вибору оптимального горизонту.

---

### ФАЗА 2 — Відродження Ensemble Branch (НОВІ МІКРОСТРУКТУРНІ МОДЕЛІ)

**Ціль:** Оживити 7 мертвих сценаріїв (S11-S13, S15, S18, S19, S21) через заміну TA sub-моделей на мікроструктурно-нативні.

**Принцип:** Старі TA моделі залишаються в кодовій базі (для майбутнього TA pipeline), нові класи створюються поряд.

#### 2.1 MicrostructureReversionModel

**Файл:** `apps/reference/domains/alpha_search/models/microstructure_reversion.py`

**Концепція:** Mean reversion мікроструктурних сигналів замість цінових. Ринок "перегріває" свій order flow так само як ціну — `ema_bias` відхиляється від нуля, `macro_resid` накопичується, `obi` стає екстремальним.

```
get_required_features() → ["ema_bias", "macro_resid", "obi", "depth_imbalance"]

Логіка scoring:
- ema_bias > upper_band → SHORT signal (перекуплений за потоком)
- ema_bias < lower_band → LONG signal (перепроданий за потоком)
- macro_resid підтверджує → boost confidence
- obi протилежний ema_bias → підтвердження розвороту
```

**Конфіг:** Нові параметри в `config/alpha_search_system.yaml`:
```yaml
microstructure_reversion:
  ema_bias_upper: 0.3    # Upper deviation band
  ema_bias_lower: -0.3   # Lower deviation band
  obi_confirm_threshold: -0.2
  macro_resid_weight: 0.4
```

#### 2.2 MomentumAlphaModel — адаптація (не заміна)

**Файл:** `apps/reference/domains/alpha_search/models/momentum.py` — **оновлення**

`pm_norm` вже є в recorder і в `alpha_input_v1.jsonl`. Адаптація:

```
get_required_features() → ["pm_norm", "feat_volume_spike", "feat_tfi"]

Маппінг:
- price_momentum_5m  → pm_norm (вже нормалізований Feature Engine)
- volume_momentum_5m → feat_volume_spike
- macd_signal        → feat_tfi (Trade Flow Imbalance як проксі тренду)
```

Дефолтні значення при відсутності: `pm_norm=0.0`, `feat_volume_spike=0.0`, `feat_tfi=0.0`

Після адаптації `MomentumAlphaModel` отримуватиме реальні дані замість нейтральних дефолтів — 100% сигналів стануть ненульовими.

#### 2.3 Оновлення конфігу Ensemble

Після реалізації нових моделей — оновити scenario matrix:

```yaml
# config/alpha_search/scenario_matrix.yaml
# S15_BALANCED — замість TA моделей:
ensemble:
  models:
    microstructure_reversion_v1:
      enabled: true
    momentum_v2:          # адаптована версія
      enabled: true
    # volatility_v1 — залишити вимкненим до TA pipeline
```

---

### ФАЗА 3 — Нові Alpha Models (Stateful + Cross-Feature)

#### 3.1 OBIDivergenceModel

**Файл:** `apps/reference/domains/alpha_search/models/obi_divergence.py`

**Концепція:** Дивергенція між рухом ціни і OBI. Якщо ціна оновлює локальний максимум але OBI падає — потужний сигнал на розворот (стакан порожній зверху).

```
get_required_features() → ["obi", "feat_delta_price", "feat_price"]

State per instance:
  self._prev_obi: float = 0.0
  self._prev_price: float = 0.0
  self._obi_window: deque[float] = deque(maxlen=N)

Scoring:
  delta_obi = current_obi - prev_obi
  price_new_high = current_price > max(price_window)

  if price_new_high AND delta_obi < -threshold:
      score = -0.8  # Bearish divergence
  elif price_new_low AND delta_obi > +threshold:
      score = +0.8  # Bullish divergence
```

**Thread safety:** `ScenarioWorker` ізолює екземпляри — кожен сценарій отримує власний об'єкт моделі. Shared state відсутній.

**Параметри для калібрування:**
- `obi_threshold` — мінімальна дельта OBI для сигналу
- `price_window` — вікно для визначення local high/low
- `lookback` — кількість барів для накопичення стану

#### 3.2 RegimeAdaptiveModel (S21 replacement)

**Концепція:** Явне перемикання між momentum та reversion залежно від `regime` поля в `AlphaInputV1`.

```
get_required_features() → ["obi", "ema_bias", "macro_resid", "pm_norm"]

if regime in ("TREND_UP", "TREND_DOWN"):
    → використовує momentum logic (pm_norm, tfi)
    → посилений threshold для reversion сигналів
elif regime in ("MEAN_REVERSION", "LOW_VOLATILITY"):
    → використовує reversion logic (ema_bias, macro_resid)
    → посилений threshold для momentum сигналів
elif regime == "HIGH_VOLATILITY":
    → conservative mode, score *= 0.5
else:  # UNCERTAIN, DEFAULT
    → score = 0.0, confidence = 0.1 (не торгуємо в невизначеності)
```

`regime_conf` (вже є в recorder) → використовувати як multiplier для confidence:
```
final_confidence = base_confidence * regime_conf
```

---

### ФАЗА 4 — Offline Replay та Scenario Search

**Ціль:** Знайти найкращу комбінацію ваг, порогів, і моделей через паралельний replay.

#### 4.1 Підготовка offline датасету

`logs/alpha_input/alpha_input_v1.jsonl` вже пишеться `FeatureMirrorWriter` в реальному часі.

Для глибшого history: якщо файл перекриває недостатньо днів — запустити конвертацію з `data/recorder`:

```bash
python scripts/build_offline_alpha_dataset.py \
  --recorder-dir data/recorder \
  --output logs/alpha_input/alpha_input_v1_offline.jsonl \
  --start-date 2026-02-01 \
  --end-date 2026-03-01
```

> Конвертор бере `feat_*` колонки напряму — look-ahead bias відсутній, timestamps aligned.

#### 4.2 Паралельний replay (Standalone Runtime)

```bash
python scripts/run_alpha_search_domain.py \
  --matrix config/alpha_search/scenario_matrix.yaml \
  --log-level INFO
```

IngestGateway читає JSONL у `replay` режимі — весь датасет проганяється за хвилини.
AggregateReporter збирає `aggregate/aggregate_metrics.csv`.

#### 4.3 Вибір переможця

Після replay — порівняння з **Phase B baseline**:

```
Метрики для порівняння (мінімальний поріг для розгляду):
- Sharpe Ratio > 1.0 (і вище за baseline)
- Max Drawdown < 15% (і менше за baseline)
- Win Rate > 52% (і вище за baseline)
- Signals generated > 100 (статистична значущість)
```

Переможні сценарії → їх параметри переносяться в `aurora.yaml` (directional_features, signal_weights, thresholds).

---

### ФАЗА 5 — Замикання Петлі (Live Weight Feedback)

**Ціль:** Alpha_search scores впливають на реальні торгові рішення Aurora.

#### 5.1 Поточний стан підключення

`EVT:ALPHA_SCORE_CALCULATED` вже споживається `decision_making.py:2197`.
Але поточна інтеграція потребує перевірки: чи впливають ці скори на `_propose_trade_intent` або лише логуються.

#### 5.2 Score-weighted signal amplification

Концепція: якщо alpha_search score для символу `> threshold` і **узгоджується** з Aurora directional signal → збільшити розмір позиції або знизити порогову значущість для входу.

```
aurora_score = AuroraScoringKernel.compute(features)
alpha_score  = AlphaProvider.calculate_alpha(features)

if sign(aurora_score) == sign(alpha_score) and alpha_score.confidence > 0.7:
    intent_size_multiplier = 1.0 + alpha_score * 0.3  # max +30%
else:
    intent_size_multiplier = 1.0
```

#### 5.3 Weight auto-update pipeline

```
AggregateReporter output
    → calibrate_aurora_signal_weights.py
        → YAML snippet
            → manual review (HITL required)
                → config/aurora/strategies/aurora.yaml update
                    → hot reload (config.hot_reload.enabled = true)
```

HITL залишається обов'язковим для будь-яких змін `signal_weights` в production.

---

## МАТРИЦЯ ПРІОРИТЕТІВ

| Фаза | Дія | Залежності | Effort | Impact |
|------|-----|-----------|--------|--------|
| **B** | Baseline run (5 активних сценаріїв) | Нічого | Нульовий | КРИТИЧНИЙ (еталон) |
| **0** | H2 NRR-046 fix | Ніяких | Середній | КРИТИЧНИЙ (live PnL) |
| **1.1** | Запуск calibration (існуючі features) | data/recorder | Низький | Високий |
| **1.2** | Ridge discovery нових features | 1.1 + aurora.yaml | Низький | Високий |
| **2.1** | MicrostructureReversionModel | — | Середній | Середній |
| **2.2** | MomentumAlphaModel адаптація (pm_norm) | — | Низький | Середній |
| **3.1** | OBIDivergenceModel (stateful) | 2.x | Середній | Потенційно Високий |
| **3.2** | RegimeAdaptiveModel | 2.x | Середній | Середній |
| **4** | Offline replay + порівняння з baseline | 2.x + 3.x | Середній | Середній |
| **5** | Live weight feedback loop | 4 + H2 fix | Складний | Стратегічний |

---

## ТЕХНІЧНІ ОБМЕЖЕННЯ ТА РИЗИКИ

### Відомі ризики

| Ризик | Рівень | Мітигація |
|-------|--------|-----------|
| Look-ahead bias в offline dataset | Низький | `data/recorder` timestamps aligned, `ready=True` фільтр |
| Overfitting ridge regression | Середній | Використовувати hold-out validation (останні 20% дат) |
| Stateful модель при hot_reload | Середній | `ScenarioWorker` реінітіалізує при оновленні конфігу |
| `except Exception: continue` в ensemble | Середній | Додати structured logging + telemetry counter |
| Cross-asset (BTC→DOGE lead-lag) | Складний | Не в scope до Фази 5, вимагає нового контракту |

### Не в scope цієї roadmap

- TA indicator computation pipeline (RSI, BB, MACD з OHLCV) — потребує окремого рішення
- Parquet migration (190MB JSONL logs) — технічний покращення, не критичне
- Cross-asset AlphaInputV1 розширення — архітектурна зміна контракту

---

## ПОТОЧНИЙ СТАТУС ФІКСІВ (ЗРОБЛЕНО)

```
✓ H1: ensemble.py:get_required_features() — агрегує фічі з sub-моделей
✓ H1: backtest_plugin.py gate — PROVIDER_SKIPPED + WARNING logging
✓ H4: test_bracket_health_check.py:49 — config={} замість MagicMock

✗ H2: NRR-046 — _emit_reduce_only_close / _handle_regime_flip без tf_sec (ВІДКРИТО)
✗ H4: conftest.py:9-12 — AuroraConfig = MagicMock fallback (ВІДКРИТО)
```

---

## ФАЙЛИ ДЛЯ НОВИХ КОМПОНЕНТІВ

```
apps/reference/domains/alpha_search/models/
├── aurora_adapter.py              ✓ Працює
├── momentum.py                    → Адаптувати: pm_norm замість price_momentum_5m
├── mean_reversion.py              → Залишити (для майбутнього TA pipeline)
├── volatility.py                  → Залишити (для майбутнього TA pipeline)
├── microstructure_reversion.py   [NEW] Фаза 2.1
├── obi_divergence.py             [NEW] Фаза 3.1
└── regime_adaptive.py            [NEW] Фаза 3.2

config/alpha_search/
├── scenario_matrix.yaml           → Оновити: S11-S21 з новими моделями
└── alpha_search_system.yaml       → Додати параметри нових моделей

config/aurora/strategies/
└── aurora.yaml                    → Оновити signal_weights після калібрування

tools/
├── calibrate_aurora_signal_weights.py  ✓ Готовий до запуску
└── alpha_search_runtime_summary.py     ✓ Існує
```

---

*Документ синтезує результати спільного аналізу Claude Sonnet (forensics) та Gemini CLI (architecture & quant research). Будь-які зміни в production execution path вимагають HITL review.*
