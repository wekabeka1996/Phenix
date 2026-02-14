# alpha_search — Актуальна документація (as-is)

Останнє оновлення цього документа: 2026-02-09.

Це “as-is” опис домену `alpha_search` на основі наявних артефактів у репозиторії (код домену, конфіг, схеми подій, verb registry, тести, звіти покриття). Усі твердження прив’язані до конкретних файлів/сутностей. Якщо інформації бракує — це позначено як `Невідомо з наданого контексту`.

## TL;DR (5–10 пунктів)

- `alpha_search` — домен/пакет для розрахунку **alpha score** (сигналу) з **features**, з базовим контрактом `AlphaModel → AlphaScore` та реєстром моделей (`apps/reference/domains/alpha_search/alpha_model.py`).
- Є два суттєво різні режими використання:
  - **In-process** у `decision_making`: `DecisionMaking` ініціалізує `AlphaModelRegistry` і емітить `EVT:ALPHA_SCORE_CALCULATED` зі списком `scores` (`apps/reference/domains/decision_making/decision_making.py`).
  - **Backtest shadow-плагін**: `AlphaSearchBacktestPlugin` робить двофазний міст `EVT:FEATURES_CALCULATED → cache → CMD:PROCESS_STRATEGY` і емітить `EVT:ALPHA_SCORE_CALCULATED` *по одному score на провайдера* (`apps/reference/domains/alpha_search/backtest_plugin.py`).
- Це створює **конфлікт контрактів**: одна й та ж подія `EVT:ALPHA_SCORE_CALCULATED` має різні payload-форми залежно від емiтера (`apps/reference/domains/decision_making/decision_making.py` vs `apps/reference/domains/alpha_search/backtest_plugin.py`).
- Є щонайменше один явний **офлайн consumer** форми `DecisionMaking`: `scripts/analyze_alpha_performance.py` парсить WAL/логи та очікує `{timestamp, scores:[...]}`; payload форми backtest-плагіна `{provider_id, score,...}` цим скриптом не обробляється (`scripts/analyze_alpha_performance.py`, `apps/reference/domains/decision_making/decision_making.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- Backtest-плагін залежить від коректної синхронізації `bar_close_ts`: у схемі `EVT:FEATURES_CALCULATED` бар має `end_ts_ms`, а плагін шукає `close_ts/ts/bar_close_ts` (ризик системних cache miss) (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- `apps/reference/main.py` зараз передає в `AlphaSearchBacktestPlugin` **dict** як `config`, хоча клас очікує `AlphaSearchConfig` (висока ймовірність падіння ініціалізації) (`apps/reference/main.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- `AuroraAlphaAdapter` обгортає `AuroraScoringKernel.compute()` як `AlphaModel` і має fail-closed поведінку для відсутніх essential features/ціни (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).
- `EnsembleModel` комбінує кілька моделей з вагами, але “performance” за замовчуванням — це **confidence як проксі**, а `on_trade_result()` існує, але не підключений бек-тест плагіном (`apps/reference/domains/alpha_search/ensemble.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- Фактичні тести: 30 тестів проходять у `tests/domains/alpha_search/*`, але покриття пакету `apps.reference.domains.alpha_search` ≈ **76%** (найбільші прогалини: `backtest_plugin.py`, `ensemble.py`) (стан репо на 2026-02-09).
- `verb_registry_v1.yaml` позначає `ALPHA_SCORE_CALCULATED` як `experimental` з `owner: unknown` і без schema, тобто контракт “не зафіксований” на рівні реєстру (`apps/reference/dictionaries/verb_registry_v1.yaml`).

---
## 3. Призначення домену

### Ціль

Надати стандартизований спосіб **обчислення alpha score** (нормалізований сигнал + впевненість + пояснення “why”) на базі features, з можливістю:

- виклику **як бібліотеки** (через `AlphaModelRegistry` у `decision_making`) (`apps/reference/domains/alpha_search/alpha_model.py`, `apps/reference/domains/decision_making/decision_making.py`);
- підключення **як shadow-плагіна** для бектесту з багатопровайдерною архітектурою та віртуальним трейдером (PnL-оцінка) (`apps/reference/domains/alpha_search/backtest_plugin.py`, `config/alpha_search.yaml`).

### Межі відповідальності (In-Scope / Out-of-Scope)

**In-Scope**

- Контракт `AlphaModel` та DTO `AlphaScore` (`apps/reference/domains/alpha_search/alpha_model.py`).
- Базові TA-моделі: momentum/mean-reversion/volatility (`apps/reference/domains/alpha_search/models/*.py`).
- Ensemble-компонент, що комбінує моделі (`apps/reference/domains/alpha_search/ensemble.py`).
- Aurora-адаптер як провайдер (обгортка Aurora scoring kernel) (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).
- Pydantic-моделі конфігурації alpha_search (providers/triggers/cache/virtual_trader) і YAML loader (`apps/reference/domains/alpha_search/config_models.py`, `config/alpha_search.yaml`).
- Backtest shadow-плагін: підписка на події, кеш features, емісія alpha score events, віртуальний трейдер, summary (`apps/reference/domains/alpha_search/backtest_plugin.py`).

**Out-of-Scope**

- Генерація/агрегація **features** (це `feature_engineering`) (`apps/reference/domains/feature_engineering/*`, схеми в `apps/reference/domains/feature_engineering/schemas/*`).
- Прийняття торгових рішень, ризик-гейти, ордери, виконання (домени `decision_making`, `risk_management`, `execution_position`) (`apps/reference/domains/decision_making/*` тощо).
- Backtest engine як оркестратор симуляції (`backtest_engine/*`), окрім того, що alpha_search може підключатися як плагін (факт інтеграції в `apps/reference/main.py`).

### Основні терміни (глосарій)

- **Alpha score** — числовий сигнал у діапазоні `[-1, 1]` (через `AlphaScore.score`) (`apps/reference/domains/alpha_search/alpha_model.py`).
- **Confidence** — впевненість сигналу у `[0, 1]` (`AlphaScore.confidence`) (`apps/reference/domains/alpha_search/alpha_model.py`).
- **AlphaModel** — абстрактний інтерфейс моделі, що повертає `AlphaScore` (`apps/reference/domains/alpha_search/alpha_model.py`).
- **AlphaModelRegistry** — реєстр моделей + масовий розрахунок для “готових” моделей (`apps/reference/domains/alpha_search/alpha_model.py`).
- **Provider** — конкретний “джерело сигналу” у backtest-плагіні (aurora adapter або TA ensemble) (`apps/reference/domains/alpha_search/backtest_plugin.py`, `apps/reference/domains/alpha_search/config_models.py`).
- **Shadow mode** — режим, коли сигнали **логуються/емітяться**, але не мають прямого впливу на трейдинг (концепт явно присутній у конфігу й payload) (`config/alpha_search.yaml`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- **Fail-closed** — при відсутності потрібних даних/помилці повертаємо “нейтральний” score=0 з поясненням (Aurora adapter робить це явно; плагін робить це на cache miss/exception) (`apps/reference/domains/alpha_search/models/aurora_adapter.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- **Two-phase bridge** — двофазна зв’язка подій: кешування features на `EVT:FEATURES_CALCULATED` і скоринг на `CMD:PROCESS_STRATEGY` (`apps/reference/domains/alpha_search/backtest_plugin.py`, `config/alpha_search.yaml`).
- **`tf_sec`** — таймфрейм у секундах (ключ частини кешу/контрактів подій) (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`, `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- **`bar_close_ts`** — timestamp закриття бара в ms для decision boundary (`apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- **Virtual trader** — “симулятор” позицій для оцінки PnL на сигнал (у backtest-плагіні) (`apps/reference/domains/alpha_search/backtest_plugin.py`, `config/alpha_search.yaml`).

---

## 4. Архітектура домену (as-is)

### Компоненти (Компонент → Роль → Вхід/Вихід → Ключові залежності)

| Компонент | Роль | Вхід / Вихід | Ключові залежності |
|---|---|---|---|
| `AlphaScore` | DTO результату скорингу | Вихід моделей: `model_name`, `symbol`, `score`, `confidence`, `timestamp`, `features_used`, `why` | Pydantic, `decimal.Decimal` (`apps/reference/domains/alpha_search/alpha_model.py`) |
| `AlphaModel` | Абстрактний контракт моделі | Вхід: `(symbol, market_data, features, context)` → Вихід: `AlphaScore` | `abc.ABC` (`apps/reference/domains/alpha_search/alpha_model.py`) |
| `AlphaModelRegistry` | Оркестратор/реєстр | Вхід: features → Вихід: список `AlphaScore` по готових моделях; ізоляція помилок | `inc_alpha_model_error` (`apps/reference/telemetry/metrics.py`), логування (`apps/reference/domains/alpha_search/alpha_model.py`) |
| `MomentumAlphaModel` | TA momentum модель | Вхід: features (`price_momentum_*`, `rsi_14`, `macd_signal`…) → `AlphaScore` | `Decimal` (`apps/reference/domains/alpha_search/models/momentum.py`) |
| `VolatilityAlphaModel` | TA volatility модель | Вхід: features (`atr_ratio`, `bb_width`, `realized_volatility_*`…) → `AlphaScore` | `Decimal` (`apps/reference/domains/alpha_search/models/volatility.py`) |
| `MeanReversionAlphaModel` | TA mean-reversion модель | Вхід: features (`bb_position`, `stoch_k/stoch_d`…) → `AlphaScore` | `Decimal` (`apps/reference/domains/alpha_search/models/mean_reversion.py`) |
| `EnsembleModel` + `EnsembleConfig` | Комбінатор моделей | Вхід: `market_data` + `features` → комбінований `AlphaScore`; періодичний rebalance ваг | `pandas`, `numpy`, clock abstraction (`apps/reference/core/time.py`) (`apps/reference/domains/alpha_search/ensemble.py`) |
| `AuroraAlphaAdapter` | Обгортка Aurora scoring як `AlphaModel` | Вхід: ціна + essential features → `AlphaScore` (fail-closed при нестачі) | `AuroraScoringKernel` (`apps/reference/domains/decision_making/aurora_scoring_kernel.py`) (`apps/reference/domains/alpha_search/models/aurora_adapter.py`) |
| `AlphaSearchConfig` (+ loader) | Strict SSOT конфіг для плагіна | Вхід: YAML → вихід: валідуваний конфіг | `pydantic` strict `extra="forbid"`, `yaml.safe_load` (`apps/reference/domains/alpha_search/config_models.py`, `config/alpha_search.yaml`) |
| `AlphaSearchBacktestPlugin` | Shadow multi-provider плагін | Вхід: `EVT:FEATURES_CALCULATED`, `CMD:PROCESS_STRATEGY` → Вихід: `EVT:ALPHA_SCORE_CALCULATED`, summary | Event bus (`listen/emit`), провайдери, virtual trader (`apps/reference/domains/alpha_search/backtest_plugin.py`) |
| `DecisionMaking.alpha_registry` | In-process використання registry | Вхід: `feats` → Вихід: емісія `EVT:ALPHA_SCORE_CALCULATED` зі списком scores | `AlphaModelRegistry`, базові моделі (`apps/reference/domains/decision_making/decision_making.py`) |

### Потоки (Flow narratives)

#### Flow 1 — In-process alpha скоринг у `decision_making`

1. `DecisionMaking` під час ініціалізації створює `AlphaModelRegistry` і реєструє моделі (наразі `MomentumAlphaModel`, `VolatilityAlphaModel`) (`apps/reference/domains/decision_making/decision_making.py`).
2. На надходження features (у фрагменті видно обробку `feats`) викликається `alpha_registry.calculate_all_alpha(...)` (`apps/reference/domains/decision_making/decision_making.py`, `apps/reference/domains/alpha_search/alpha_model.py`).
3. Якщо є результати, `DecisionMaking` емітить `EVT:ALPHA_SCORE_CALCULATED` з payload формату `{symbol, scores: [...], timestamp}` (`apps/reference/domains/decision_making/decision_making.py`).

#### Flow 2 — Backtest shadow плагін (двохфазний міст)

1. Плагін підписується на `EVT:FEATURES_CALCULATED` (кешування) і `CMD:PROCESS_STRATEGY` (скоринг) згідно з `AlphaSearchConfig.triggers` (`apps/reference/domains/alpha_search/backtest_plugin.py`, `apps/reference/domains/alpha_search/config_models.py`, `config/alpha_search.yaml`).
2. На `EVT:FEATURES_CALCULATED` плагін кешує `features` за ключем `(symbol, tf_sec, bar_close_ts)` і робить prune до `cache.max_per_symbol` (`apps/reference/domains/alpha_search/backtest_plugin.py`).
3. На `CMD:PROCESS_STRATEGY` плагін дістає cached features за `(symbol, tf_sec, bar_close_ts)` і для кожного enabled provider викликає `model.calculate_alpha(...)` (`apps/reference/domains/alpha_search/backtest_plugin.py`).
4. Плагін емітить `EVT:ALPHA_SCORE_CALCULATED` (назва події береться з `triggers.emit_event`) з payload, що включає `provider_id`, `model_name`, `score`, `confidence`, `threshold`, `shadow`, `signal_id`, `why`, `features_used` (`apps/reference/domains/alpha_search/backtest_plugin.py`).
5. Опційно: virtual trader відкриває/закриває “віртуальні” позиції та акумулює PnL, який потім потрапляє у `get_summary()` (`apps/reference/domains/alpha_search/backtest_plugin.py`, `config/alpha_search.yaml`).

#### Flow 3 — Ініціалізація провайдерів у плагіні (multi-provider)

1. Плагін читає `config.providers` і для кожного enabled провайдера створює модель:
   - `adapter` → `AuroraAlphaAdapter`
   - `ensemble` → `EnsembleModel` з підмоделями `*_v1` (`apps/reference/domains/alpha_search/backtest_plugin.py`, `apps/reference/domains/alpha_search/config_models.py`).
2. Якщо провайдер включений, але модель не створилась, плагін логне попередження й провайдер не потрапить у `self.providers` (`apps/reference/domains/alpha_search/backtest_plugin.py`).

#### Flow 4 — Aurora adapter (fail-closed скоринг)

1. Adapter дістає ціну з `market_data["close"]` або з features (`close/price/last_price`) (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).
2. Перевіряє essential features (за замовчуванням `["obi", "delta_price", "macro_resid"]`) і при нестачі повертає score=0 з `why` із префіксом `fail_closed:*` (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).
3. Викликає `AuroraScoringKernel.compute(...)` і конвертує результат у `AlphaScore` (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).

### Контракти/інтерфейси (що домен приймає/віддає)

#### Публічний інтерфейс моделей

- `AlphaModel.calculate_alpha(symbol, market_data, features, context) -> AlphaScore` (`apps/reference/domains/alpha_search/alpha_model.py`).
- `AlphaModel.get_required_features() -> list[str]` використовується для readiness в registry (`apps/reference/domains/alpha_search/alpha_model.py`).

#### Події (event contracts) — as-is

**Вхідні**

- `EVT:FEATURES_CALCULATED`:
  - Schema у verb registry: `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json` (`apps/reference/dictionaries/verb_registry_v1.yaml`).
  - Важливі поля за схемою: `ts`, `symbol`, `tf_sec` (опційно), `features`, `bar` (з `end_ts_ms`) (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`).
  - Плагін фактично використовує: `symbol`, `features`, `tf_sec` (default 300), `ts`, `bar` (але читає `close_ts/ts`, не `end_ts_ms`) (`apps/reference/domains/alpha_search/backtest_plugin.py`).

- `CMD:PROCESS_STRATEGY`:
  - Schema у verb registry: `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json` (`apps/reference/dictionaries/verb_registry_v1.yaml`).
  - Обов’язкові поля за схемою: `symbol`, `tf_sec`, `bar_close_ts`, `bar`, `features`, `warmup`, `regime` (`apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`).
  - Плагін фактично використовує: `symbol`, `tf_sec`, `bar_close_ts` (`apps/reference/domains/alpha_search/backtest_plugin.py`).

- `EVT:TRADE_EXECUTED`:
  - Є у verb registry зі schema `apps/reference/domains/position_tracking/schemas/trade_executed_v1.json` (`apps/reference/dictionaries/verb_registry_v1.yaml`).
  - Плагін підписується, але handler порожній (`apps/reference/domains/alpha_search/backtest_plugin.py`).

**Вихідні**

- `EVT:ALPHA_SCORE_CALCULATED`:
  - У verb registry: `owner: unknown`, `status: experimental`, `schema: null` (`apps/reference/dictionaries/verb_registry_v1.yaml`).
  - Емітер #1: `DecisionMaking` payload `{symbol, scores: [AlphaScore dict], timestamp}` (`apps/reference/domains/decision_making/decision_making.py`).
  - Емітер #2: `AlphaSearchBacktestPlugin` payload `{provider_id, model_name, symbol, tf_sec, bar_close_ts, score, confidence, threshold, shadow, signal_id, why, features_used}` (`apps/reference/domains/alpha_search/backtest_plugin.py`).

---

## 5. Ключова логіка та інваріанти

### Інваріанти (що має бути істинним завжди)

- `AlphaScore.score ∈ [-1, 1]` та `AlphaScore.confidence ∈ [0, 1]` — enforce через Pydantic Field constraints (`apps/reference/domains/alpha_search/alpha_model.py`).
- `AlphaModelRegistry` не допускає 2 моделі з однаковим `model.name` (кидає `ValueError`) (`apps/reference/domains/alpha_search/alpha_model.py`).
- Registry викликає `calculate_alpha` лише для моделей, які `is_ready(features)=True` (тобто всі required features присутні) (`apps/reference/domains/alpha_search/alpha_model.py`).
- Backtest-плагін:
  - кеш має обмеження `cache.max_per_symbol` і prune старих записів (`apps/reference/domains/alpha_search/backtest_plugin.py`, `config/alpha_search.yaml`);
  - score класифікується як long/short при `score > threshold` або `score < -threshold` (`apps/reference/domains/alpha_search/backtest_plugin.py`).

### Обробка помилок/відмов (fail-closed/fail-open)

- Registry: помилка в одній моделі не ламає інші; exception логиться, а метрика `alpha_model_errors_total{model}` інкрементиться (`apps/reference/domains/alpha_search/alpha_model.py`, `apps/reference/telemetry/metrics.py`).
- Aurora adapter: при відсутності ціни, essential features або при kernel error/deferral повертає `score=0`, `confidence=0` з `why` (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).
- Backtest-плагін: при cache miss або exception провайдера може емітити “fail-closed” score=0, якщо `ProviderConfig.fail_closed=True` (`apps/reference/domains/alpha_search/backtest_plugin.py`, `apps/reference/domains/alpha_search/config_models.py`).

### Крайні випадки (edge cases)

- `EVT:FEATURES_CALCULATED` за SSOT-схемою має `bar.end_ts_ms`, але плагін читає `bar.close_ts`/`bar.ts` і може не влучати в ключ `bar_close_ts` з `CMD:PROCESS_STRATEGY` → системні cache misses і “fail_closed:missing_features_for_bar” (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`, `apps/reference/domains/alpha_search/backtest_plugin.py`, тести наразі використовують `close_ts` у mock payload: `tests/domains/alpha_search/test_backtest_plugin.py`).
- `ProviderConfig` дозволяє конфіг без `adapter` і без `ensemble` (validator це не блокує), але плагін не створює модель і провайдер фактично “зникає” (`apps/reference/domains/alpha_search/config_models.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- Конвенція знаку `score`:
  - Momentum/Volatility трактують знак інтуїтивно (positive bullish / rising vol) (`apps/reference/domains/alpha_search/models/momentum.py`, `apps/reference/domains/alpha_search/models/volatility.py`).
  - MeanReversion має суперечність між docstring та фактичними “why”/тестами (у тесті “buy” очікується як negative) (`apps/reference/domains/alpha_search/models/mean_reversion.py`, `tests/domains/alpha_search/test_models_determinism.py`).
  - Virtual trader у плагіні відкриває `BUY`, якщо `score > 0`, і `SELL` інакше — потенційний конфлікт для mean-reversion/інших провайдерів (`apps/reference/domains/alpha_search/backtest_plugin.py`).

---

## 6. Оцінка якості коду (as-is)

### Сильні сторони

- Чіткий контракт `AlphaModel` + строгий DTO `AlphaScore` (типи, діапазони) (`apps/reference/domains/alpha_search/alpha_model.py`).
- Ізоляція помилок у registry + базова метрика помилок моделей (`apps/reference/domains/alpha_search/alpha_model.py`, `apps/reference/telemetry/metrics.py`).
- Aurora adapter реюзає “pure kernel” з `decision_making`, що знижує дрейф логіки між режимами (`apps/reference/domains/alpha_search/models/aurora_adapter.py`).
- Конфіг backtest-плагіна описаний Pydantic strict (`extra="forbid"`) і винесений у YAML (`apps/reference/domains/alpha_search/config_models.py`, `config/alpha_search.yaml`).
- Наявні доменні тести на ключові інциденти: plumbing features, fail-closed, cache bridge, детермінізм моделей (`tests/domains/alpha_search/*`).

### Слабкі місця (з прив’язкою до файлів/сутностей)

- Документація в домені суттєво “дрейфує” від коду/тестів (приклади: інші `model_name`, інші назви features, заявлені метрики/coverage) (`apps/reference/domains/alpha_search/TESTING.md`, `apps/reference/domains/alpha_search/API_DEPENDENCIES.md`, `apps/reference/domains/alpha_search/EVENTS.md`, `apps/reference/domains/alpha_search/ANALYSIS_SUMMARY.md`).
- Конфлікт контракту `EVT:ALPHA_SCORE_CALCULATED`: різні payload-форми від різних емiтерів (`apps/reference/domains/decision_making/decision_making.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`), а verb registry не має schema/owner (`apps/reference/dictionaries/verb_registry_v1.yaml`).
- Критичний ризик cache key mismatch через різні поля timestamp у схемі vs у плагіні (`end_ts_ms` vs `close_ts/bar_close_ts`) (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- `apps/reference/main.py` створює `AlphaSearchBacktestPlugin(config={...})` як dict (імовірне падіння на доступі `config.enabled`) — wiring gap для бектесту (`apps/reference/main.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- `EnsembleModel` містить механізм `on_trade_result()`, але backtest-плагін не викликає його (handler `_on_trade` порожній) — “мертвий”/незавершений feedback loop (`apps/reference/domains/alpha_search/ensemble.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- `EnsembleModelConfig.performance_window_days` присутній у конфізі, але в логіці трекінгу/ребалансу фактично не використовується (історія “обрізається” до 100 елементів) (`apps/reference/domains/alpha_search/ensemble.py`, `apps/reference/domains/alpha_search/config_models.py`).

### Техборг/заборгованість (як проявляється, чим ризикує)

- “Невизначений контракт події” → ризик ламання моніторингу/споживачів при появі schema validation (verb registry зараз schema=null) (`apps/reference/dictionaries/verb_registry_v1.yaml`).
- Магічні числа в моделях/ensemble (ваги, пороги, нормалізації) → складно калібрувати без конфіга/експериментів, ризик непередбачуваних сигналів при зміні фіч (`apps/reference/domains/alpha_search/models/*.py`, `apps/reference/domains/alpha_search/ensemble.py`).
- Virtual trader не має тестового покриття й має сильні припущення (sign→side, price availability) → ризик “помилкового PnL” і хибних висновків у звітах (`apps/reference/domains/alpha_search/backtest_plugin.py`).

### Ризик-матриця (Impact × Likelihood)

| Ризик | Impact | Likelihood | Де видно |
|---|---|---|---|
| Різні payload’и для `EVT:ALPHA_SCORE_CALCULATED` | High | High | `decision_making.py` vs `backtest_plugin.py`, schema=null у registry |
| Wiring bug: dict config у `apps/reference/main.py` | High | High | `apps/reference/main.py`, `backtest_plugin.py` |
| Cache miss через `end_ts_ms` vs `close_ts/bar_close_ts` | High | Medium/High | `features_calculated_v1.json`, `backtest_plugin.py`, тести з `close_ts` |
| Непідключений feedback loop (`on_trade_result`) | Medium | High | `ensemble.py`, `_on_trade` у `backtest_plugin.py` |
| Невизначена/суперечлива семантика знаку score (mean reversion vs virtual trader) | Medium | Medium | `mean_reversion.py`, `backtest_plugin.py`, тести |
| ProviderConfig дозволяє enabled провайдера без типу | Medium | Medium | `config_models.py`, `_create_provider_model` у `backtest_plugin.py` |

---

## 7. Тестування і покриття

### Що тестується добре

- `AuroraAlphaAdapter`: ініціалізація, fail-closed при відсутніх essential features/ціни, діапазон score, знак при bearish/bullish, інтеграційна перевірка “sign match” з kernel (`tests/domains/alpha_search/test_aurora_adapter.py`).
- `AlphaModelRegistry`: readiness (warmup), пропуск при відсутності required features, ізоляція exception + інкремент метрики (`tests/domains/alpha_search/test_registry_fail_closed.py`).
- `EnsembleModel`: критичний баг “features plumbing” (features не мають бути `{}`), коректна передача symbol у підмоделі (`tests/domains/alpha_search/test_ensemble_features_plumbing.py`).
- Backtest-плагін: кешування, prune, нормалізація timestamp (sec→ms), cache hit/miss статистика, fail-closed на cache miss, allowlist, summary (`tests/domains/alpha_search/test_backtest_plugin.py`).
- Базові моделі: діапазони, детермінізм, clamping на екстремумах, правильні `get_model_name()` (`tests/domains/alpha_search/test_models_determinism.py`).

### Прогалини покриття (функціональні/інваріантні/інтеграційні)

- Virtual trader (відкриття/закриття позицій, exit правила, PnL облік) майже не покритий (`apps/reference/domains/alpha_search/backtest_plugin.py` vs відсутність тестів на ці гілки).
- Реальна форма `EVT:FEATURES_CALCULATED.bar` за schema (`end_ts_ms`) не тестується: тести використовують `bar.close_ts`, якого немає у SSOT-схемі (`tests/domains/alpha_search/test_backtest_plugin.py`, `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`).
- YAML loader `load_alpha_search_config()` і строгі edge cases валідації конфіга майже не покриті (`apps/reference/domains/alpha_search/config_models.py`).
- `EnsembleModel`: rebalance, min/max constraints, `add_model/remove_model/get_ensemble_stats`, `on_trade_result` — слабке покриття (`apps/reference/domains/alpha_search/ensemble.py`).

### Coverage (стан репо на 2026-02-09) + “coverage-пастки”

- Фактичне покриття `apps.reference.domains.alpha_search` ≈ **76%**.
  - `apps/reference/domains/alpha_search/alpha_model.py`: 89%
  - `apps/reference/domains/alpha_search/backtest_plugin.py`: 67%
  - `apps/reference/domains/alpha_search/config_models.py`: 83%
  - `apps/reference/domains/alpha_search/ensemble.py`: 61%
  - `apps/reference/domains/alpha_search/models/aurora_adapter.py`: 87%
  - `apps/reference/domains/alpha_search/models/momentum.py`: 87%
  - `apps/reference/domains/alpha_search/models/mean_reversion.py`: 79%
  - `apps/reference/domains/alpha_search/models/volatility.py`: 92%
- Coverage-пастка №1: тести можуть “заспокоювати”, бо використовують payload-форму, яка не відповідає schema (наприклад, `close_ts`).
- Coverage-пастка №2: частина тестів перевіряє лише “non-zero/doesn’t crash”, але не валідність семантики (знак score, відповідність threshold, узгодженість контракту подій).

### Рекомендована структура тестів (без коду)

- Unit: кожна модель (`models/*`) — семантика знаку, граничні значення, детермінізм.
- Unit: `AlphaModelRegistry` — readiness, дублікати, error isolation + метрики.
- Unit: `config_models` — loader + strict validation (помилки, legacy bucket, “enabled but no providers”).
- Integration (event): Backtest-плагін з payload’ами, що відповідають SSOT-схемам (`end_ts_ms`, `bar_close_ts`), і з перевіркою cache-hit.
- Integration: контракт `EVT:ALPHA_SCORE_CALCULATED` — або уніфікований schema, або явна перевірка на “дві форми” з чітким consumer-очікуванням.

---

## 8. Вузькі місця та точки зламу

### Bottlenecks (продуктивність/складність/зв’язність)

- `AlphaSearchBacktestPlugin._prune_cache()` робить scan по всіх ключах кешу для символу при кожному записі → потенційно O(total_cache_entries) на event (`apps/reference/domains/alpha_search/backtest_plugin.py`).
- `EnsembleModel.calculate_alpha()` конвертує `market_data` у `pandas.DataFrame` навіть для одного запису (overhead) (`apps/reference/domains/alpha_search/ensemble.py`).
- Скоринг у плагіні — послідовний для всіх провайдерів/моделей (`apps/reference/domains/alpha_search/backtest_plugin.py`, `apps/reference/domains/alpha_search/ensemble.py`).

### “Single points of failure”

- Невідповідність timestamp-полів між `EVT:FEATURES_CALCULATED` і `CMD:PROCESS_STRATEGY` може зробити плагін “глухим” (суцільні cache miss) (`apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- Конфлікт контрактів `EVT:ALPHA_SCORE_CALCULATED` — ризик для будь-якого майбутнього consumer зі schema validation (`apps/reference/dictionaries/verb_registry_v1.yaml`, `apps/reference/domains/decision_making/decision_making.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).
- Wiring у `apps/reference/main.py`: неправильний тип `config` при ініціалізації плагіна може повністю вимкнути alpha_search у бектесті (`apps/reference/main.py`).

### Спостережуваність (що логувати/які метрики потрібні — без коду)

**Є зараз**

- Метрика `alpha_model_errors_total{model}` для exception в registry (`apps/reference/telemetry/metrics.py`, `apps/reference/domains/alpha_search/alpha_model.py`).
- Summary зі статистикою cache hits/misses, signals, virtual PnL (`apps/reference/domains/alpha_search/backtest_plugin.py`).
- Debug-логи по кешу/скорингу (`apps/reference/domains/alpha_search/backtest_plugin.py`).

**Варто додати/уточнити (рекомендації)**

- Окремі лічильники: cache_hit/cache_miss, fail_closed emissions, signals_long/short/neutral по провайдеру, virtual_trader pnl distribution.
- Явний “contract version” у payload `EVT:ALPHA_SCORE_CALCULATED` або розділення подій за різними verb’ами.
- Логування причин cache miss (які ключі очікувалися/фактично були), особливо для mismatch `end_ts_ms` vs `bar_close_ts`.

---

## 9. Рекомендації та план покращень

### P0 (критичне)

1) Уніфікувати контракт `EVT:ALPHA_SCORE_CALCULATED` або розділити події на різні verb’и

- Acceptance / DoD:
  - `apps/reference/dictionaries/verb_registry_v1.yaml` має `owner` і `schema` для `ALPHA_SCORE_CALCULATED` (або для нових verb’ів).
  - Є один “SSOT schema” (файл у `schemas/` або `apps/reference/domains/*/schemas/`) і обидва емiтери або відповідають йому, або використовують різні події.
  - Документи `apps/reference/domains/alpha_search/EVENTS.md` та `apps/reference/domains/decision_making/docs/EVENTS.md` не суперечать коду емісії.

2) Виправити wiring backtest-плагіна в `apps/reference/main.py` (тип `config`)

- Acceptance / DoD:
  - `AlphaSearchBacktestPlugin` ініціалізується без винятків у backtest-флоу.
  - Backtest report містить `alpha_search` summary (ін’єкція вже є) (`apps/reference/main.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).

3) Вирівняти timestamp/бар-контракт для cache key у плагіні з SSOT-схемами

- Acceptance / DoD:
  - Плагін коректно використовує `bar.end_ts_ms` з `EVT:FEATURES_CALCULATED` (або upstream додає `bar_close_ts`), і це підтверджено інтеграційним тестом на payload із `features_calculated_v1.json`.
  - Cache miss rate у summary стає діагностично-обґрунтованою, а не “завжди 100%”.

4) Зафіксувати єдину семантику знаку `AlphaScore.score` і узгодити з virtual trader

- Acceptance / DoD:
  - У документації домену є чітке правило: `score > 0` означає що саме (BUY/LONG), `score < 0` — що саме.
  - `MeanReversionAlphaModel` docstring/why/тести та `AlphaSearchBacktestPlugin` entry logic не суперечать цьому правилу.

### P1 (важливе)

5) Зробити `ProviderConfig` строгішим: enabled провайдер має мати або `adapter`, або `ensemble`

- Acceptance / DoD:
  - Неможливо “включити” провайдера, який не створюється у плагіні (валідація блокує або плагін фейлиться fail-closed з явним повідомленням) (`apps/reference/domains/alpha_search/config_models.py`, `apps/reference/domains/alpha_search/backtest_plugin.py`).

6) Доробити або прибрати незадіяний feedback loop `on_trade_result`

- Acceptance / DoD:
  - Або плагін реально корелює `EVT:TRADE_EXECUTED` з `signal_id` і викликає `EnsembleModel.on_trade_result()`, або код/документи більше не обіцяють online-learning.

7) Підняти покриття там, де найбільший ризик (plugin/ensemble)

- Acceptance / DoD:
  - Coverage `backtest_plugin.py` та `ensemble.py` підвищено мінімум до узгодженого порогу (наприклад, 80%+) і включає schema-реалістичні payload’и та virtual trader критичні гілки.

### P2 (планово)

8) Почистити й замінити “шаблонні” документи домену на SSOT (цей документ)

- Acceptance / DoD:
  - `apps/reference/domains/alpha_search/TESTING.md`, `API_DEPENDENCIES.md`, `EVENTS.md`, `ANALYSIS_SUMMARY.md` або приведені у відповідність, або явно позначені як “deprecated/legacy notes”.
  - Документи не містять неіснуючих тестів/метрик/конфігів.

9) Оптимізація продуктивності (за потреби масштабу)

- Acceptance / DoD:
  - Зменшено overhead на DataFrame у `EnsembleModel` (якщо ensemble використовується у проді/масових бектестах).
  - Cache prune не робить глобальних scan’ів при великих наборах символів.

---

## 10. Питання до уточнення (якщо є)

1) Який з двох шляхів є “канонічним” для `alpha_search` у вашій системі:

- In-process у `decision_making` (`apps/reference/domains/decision_making/decision_making.py`)
чи
- Backtest multi-provider плагін (`apps/reference/domains/alpha_search/backtest_plugin.py`)?

`Невідомо з наданого контексту`, чи обидва мають існувати паралельно як стабільний контракт.

2) Хто є реальним consumer події `EVT:ALPHA_SCORE_CALCULATED`?

Відомий офлайн consumer: `scripts/analyze_alpha_performance.py` (парсить WAL/логи та очікує форму `{timestamp, scores:[...]}` з `DecisionMaking`) (`scripts/analyze_alpha_performance.py`, `apps/reference/domains/decision_making/decision_making.py`).

`Невідомо з наданого контексту`, чи є **on-line** споживачі (підписки `listen`/`event_handler`) і чи комусь потрібна форма події від backtest-плагіна `{provider_id, score,...}`. Потрібно: файл/модуль, що читає/валідує/агрегує `EVT:ALPHA_SCORE_CALCULATED`, або приклад із логів/WAL “де це читають”.

3) Чи є у реальних payload’ах `EVT:FEATURES_CALCULATED` поле, еквівалентне `bar_close_ts`?

`Невідомо з наданого контексту`. Потрібно: 1–3 реальні приклади payload з логів/WAL (або шлях до файлу зі збереженими подіями), щоб зафіксувати, чи `ts == bar.end_ts_ms` і як правильно ключувати кеш.

4) Чи планується вмикати `ta_ensemble` провайдера в `config/alpha_search.yaml`?

Зараз він `enabled: false` (`config/alpha_search.yaml`). Якщо планується — треба підтвердити відповідність назв features (наприклад `stoch_k/stoch_d` vs можливі `stochastic_k/stochastic_d`) та узгодити sign convention.
