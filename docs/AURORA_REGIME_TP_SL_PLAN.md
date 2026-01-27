# Aurora: Regime-Based TP/SL (план реалізації + тестування)

## 0) Ціль
Зробити для стратегії **Aurora** розрахунок **TP/SL залежно від режиму ринку** (*market regime*) так, щоб:
- **не ламати “ядро”** (DecisionMaking / ExecPosFSM вже вміють приймати *strategy-provided* `stop_price/target_price`);
- мати **керованість через конфіг** (вкл/викл + мапінг по режимах);
- отримати **прозору телеметрію** (який режим → які TP/SL були застосовані);
- мати **глибокий план тестування** (unit → інтеграція → backtest regression → shadow rollout).

## 1) Поточна архітектура (що вже є в коді)
### 1.1 Вхідні дані “режим ринку”
- RegimeDetector емітить `EVT:REGIME_DETECTED`.
- `AuroraHandler` кешує режим у `SymbolState.regime` (та має анти-чорн “effective regime”, якщо увімкнено) в `apps/reference/domains/decision_making/aurora_handler.py`.

### 1.2 Точка інжекту TP/SL від стратегії (вже підтримано)
Ланцюжок “Strategy Primacy” уже реалізований:
- `AuroraHandler` емітить `EVT:STRATEGY_SIGNAL_PRODUCED` з `price_ctx.entry_price` (`apps/reference/domains/decision_making/aurora_handler.py`, метод `_emit_signal`).
- `DecisionMaking` на gateway-етапі **пріоритетно** бере `price_ctx.stop_price/target_price`, якщо вони присутні (`apps/reference/domains/decision_making/decision_making.py`, блок `STRATEGY PRIMACY FOR SL/TP`).
- `ExecPosFSM` також має **пріоритет Strategy SL/TP** (береться з DEC:OPEN) (`apps/reference/domains/execution_position/fsm.py`, блок `STRATEGY PRIMACY FOR SL/TP`) і валідує/квантує ціни.

Це означає: **для Aurora достатньо додати `stop_price/target_price` у `price_ctx`** — ядро вже підхопить.

### 1.3 Приклад, де це вже працює
`MeanReversionHandler` уже інжектить `stop_price/target_price` у `price_ctx` і це проходить весь пайплайн (`apps/reference/domains/decision_making/mean_reversion_handler.py`, `_emit_signal`).

## 2) Вимоги до нового функціоналу
### 2.1 Функціональні
- Для кожного сигналу Aurora (BUY/SELL) рахувати:
  - `stop_price` (SL)
  - `target_price` (TP1)
  - (опційно у V2) `target_price_2` / частковий вихід (TP2/partial) — **не обов’язково для MVP**, бо ядро зараз стабільно оперує мінімальним набором.
- Вибір TP/SL має залежати від `regime` (наприклад `TREND_UP`, `LOW_VOLATILITY`, `FLAT_NORMAL`, …).
- Має бути **fallback-ланцюжок** (якщо режим невідомий/ATR не ready/немає ключа в мапі) без крашів у live:
  - MVP: fallback на базові `exit.sl_pct` + `take_profit.tp_low_ratio` з `config/aurora/strategies/aurora.yaml`.
  - Опційно: fail-closed тільки якщо `regime_tpsl.enabled=true` і відсутні необхідні дані.

### 2.2 Нефункціональні (безпека/керованість)
- Default: `enabled=false` (нічого не змінює у live поки не ввімкнемо).
- Телеметрія: **структурований** `tpsl_ctx` у payload (для машинного аналізу), а `why_chain` — лише як людино-читабельний дубль (без regex-парсингу).
- Валідація:
  - SL і TP мають бути на правильному боці від ціни входу
  - мінімальна дистанція (не “майже одразу тригериться”)
  - квантизація (tick size) відбудеться в ExecPosFSM, але ми маємо уникати явно некоректних значень.

### 2.3 Ризик-менеджмент: “Varied Risk per Trade” (критичний нюанс)
У нас сайзинг в `DecisionMaking` зараз **margin-first** і не залежить від SL/TP (qty рахується від `margin_pct * leverage`, а не від “грошового ризику на SL”).
Тому:
- якщо в режимі `HIGH_VOLATILITY` збільшити `sl_mult` (наприклад 1.35), а `qty` залишиться тим самим → **грошовий ризик на угоду зросте** ~в ті ж 1.35×;
- найризиковіші режими можуть отримати **найвищий $-ризик**, якщо не врахувати це окремо.

Політика для MVP (рекомендація):
- тримати `sl_mult` консервативним (напр. 0.8–1.2), а “адаптацію” робити переважно через `tp_mult`/гейти/anti-churn (щоб не роздувати $-ризик).

V2 (покращення, потребує торкнутись сайзингу):
- risk-normalized sizing: `qty_eff = qty_base / sl_mult` (або аналог у bps) щоб **$-ризик був стабільніший** між режимами.

## 3) Стратегія розрахунку: 2 варіанти (рекомендація + чому)
Є 2 адекватні підходи. В плані реалізації можна почати з A (простий), а B додати після MVP або одразу, якщо ATR стабільний у твоєму лайф/бектесті.

### Варіант A (простий, % від entry_price)
**Сенс:** беремо базові параметри per-symbol з aurora.yaml і масштабуємо мультиплікаторами по режиму.

База (вже є в конфігу):
- `exit.sl_pct` (наприклад BTC 0.02)
- `take_profit.tp_low_ratio` (наприклад BTC 0.5)

Режимний масштаб:
- `sl_pct_eff = sl_pct_base * sl_mult[regime]`
- `tp_rr_eff = tp_low_ratio_base * tp_mult[regime]`

Тоді:
- LONG: `SL = entry * (1 - sl_pct_eff)`, `TP = entry * (1 + sl_pct_eff * tp_rr_eff)`
- SHORT: `SL = entry * (1 + sl_pct_eff)`, `TP = entry * (1 - sl_pct_eff * tp_rr_eff)`

Плюси: мінімум залежностей, стабільно працює без ATR.
Мінуси: менш “адаптивно” до реально мінливої волатильності.

### Варіант B (кращий математично, від ATR/price, наближено до “середніх рухів бару”)
**Сенс:** ринкові режими часто відображають **масштаб коливань**. Найбільш природна метрика — `ATR% = atr / price`.

Тоді:
- `atr_pct = atr_14 / entry_price`
- `sl_pct_eff = atr_pct * sl_k_atr[regime]` (наприклад 8×ATR% у high vol, 4×ATR% у low vol)
- `tp_rr_eff = rr_by_regime[regime]` (risk-reward у мультиплікаторах ризику)

Плюси: реально прив’язано до “типового руху” (те, що ти просиш).
Мінуси: вимагає ATR readiness; у бектесті потрібно переконатись, що ATR стабільно розраховується на твоєму TF.

## 4) Початкові “прайори” (чернові значення з загальних знань)
Це **не істина** — це стартові гіпотези для першого backtest-кола.

### 4.1 Інтуїція по режимах (5m, crypto)
- `LOW_VOLATILITY` / `FLAT_LOW`: невеликі амплітуди → SL/TP ближче (інакше довго “висить”), RR нижчий.
- `FLAT_NORMAL`: середні коливання → базові значення.
- `MEAN_REVERSION`: часто працює на “повернення до середнього”, тому TP не повинен бути занадто далеким; SL помірний.
- `TREND_UP/DOWN`: шум + дрейф → SL трохи ширший, TP суттєво ширший (щоб ловити тренд і зменшити churn).
- `HIGH_VOLATILITY`: широкий шум → SL ширший (щоб не вибивало), TP помірно ширший або базовий.

### 4.2 Рекомендовані стартові мапи (для MVP, Варіант A: мультиплікатори)
#### SL multiplier (`sl_mult`)
- `FLAT_LOW`: 0.70
- `LOW_VOLATILITY`: 0.75
- `FLAT_NORMAL`: 0.85
- `MEAN_REVERSION`: 0.95
- `TREND_UP`: 1.10
- `TREND_DOWN`: 1.10
- `HIGH_VOLATILITY`: 1.35
- `UNCERTAIN`: 1.00
- `DEFAULT`: 1.00

#### TP RR multiplier (`tp_mult`) (масштабує `tp_low_ratio`)
- `FLAT_LOW`: 0.75
- `LOW_VOLATILITY`: 0.80
- `FLAT_NORMAL`: 0.90
- `MEAN_REVERSION`: 0.85
- `TREND_UP`: 1.25
- `TREND_DOWN`: 1.25
- `HIGH_VOLATILITY`: 1.05
- `UNCERTAIN`: 1.00
- `DEFAULT`: 1.00

### 4.3 Рекомендовані стартові мапи (Варіант B: ATR-логіка)
Якщо йдемо через ATR%, тоді краще задавати *k* для SL і RR напряму:

- `sl_k_atr_by_regime` (скільки ATR% до SL):
  - `FLAT_LOW`: 4.0
  - `LOW_VOLATILITY`: 4.5
  - `FLAT_NORMAL`: 5.5
  - `MEAN_REVERSION`: 5.0
  - `TREND_UP/DOWN`: 6.5
  - `HIGH_VOLATILITY`: 8.0
  - `DEFAULT`: 5.5
- `rr_by_regime` (TP як множник SL):
  - `FLAT_LOW`: 0.6
  - `LOW_VOLATILITY`: 0.7
  - `FLAT_NORMAL`: 0.9
  - `MEAN_REVERSION`: 0.8
  - `TREND_UP/DOWN`: 1.3
  - `HIGH_VOLATILITY`: 1.0
  - `DEFAULT`: 0.9

## 5) Пропозиція по конфігу (SSOT: `config/aurora/strategies/aurora.yaml`)
Оскільки `apps/reference/config_models.py` має `extra='forbid'`, **будь-які нові ключі в YAML потребують оновлення pydantic-моделей**.

### 5.1 Пропонований мінімальний конфіг (MVP)
Додати в `strategies.aurora.assets.<SYMBOL>`:
```yaml
exit:
  sl_pct: 0.02
  max_hold_sec: 3000
  regime_tpsl:
    enabled: false
    mode: "pct_mult"  # "pct_mult" | "atr"
    sl_mult:
      DEFAULT: 1.0
      TREND_UP: 1.1
      TREND_DOWN: 1.1
      HIGH_VOLATILITY: 1.35
      LOW_VOLATILITY: 0.75
      FLAT_LOW: 0.7
      FLAT_NORMAL: 0.85
      MEAN_REVERSION: 0.95
    tp_mult:
      DEFAULT: 1.0
      TREND_UP: 1.25
      TREND_DOWN: 1.25
      HIGH_VOLATILITY: 1.05
      LOW_VOLATILITY: 0.8
      FLAT_LOW: 0.75
      FLAT_NORMAL: 0.9
      MEAN_REVERSION: 0.85
```

### 5.2 Guardrails в конфігу (рекомендація)
Щоб уникнути “дурних” значень:
```yaml
exit:
  regime_tpsl:
    min_sl_pct: 0.003   # 0.3%
    max_sl_pct: 0.06    # 6%
    min_tp_rr: 0.3
    max_tp_rr: 3.0
    min_dist_bps: 15    # не ставити SL/TP ближче ніж 15 bps
```

## 6) План реалізації (кроки, без зміни ядра)
### Крок 1 — Дизайн моделі конфігу
Файли:
- `apps/reference/config_models.py` (додати model для `regime_tpsl` в `AuroraExitConfig`)
- `docs/CONFIG_MAP.md` (оновити карту полів)

Рішення:
- `enabled` за замовчуванням `false`
- `mode`: `"pct_mult"` або `"atr"`
- словники `sl_mult`, `tp_mult` (або `sl_k_atr_by_regime`, `rr_by_regime` для `"atr"`)
- guardrails (min/max + min_dist_bps)

### Крок 2 — Реалізація обчислення TP/SL в AuroraHandler
Файли:
- `apps/reference/domains/decision_making/aurora_handler.py`

Зміни:
- Додати helper-функцію (або приватний метод) типу `compute_regime_tpsl(entry_price, side, regime, instr_cfg, features)` яка:
  - вибирає `regime_used` (краще: `state.regime_effective` якщо anti_churn_enabled, інакше `state.regime`)
  - читає базові `exit.sl_pct`, `take_profit.tp_low_ratio`
  - застосовує мапи/guardrails
  - повертає `stop_price`, `target_price` + `tpsl_ctx`
- У `_emit_signal` додати в `payload["price_ctx"]`:
  - `stop_price`
  - `target_price`
- Додати в payload `tpsl_ctx` (для бектест репорту/логів).

**Важливо:** якщо `regime_tpsl.enabled=false` — не інжектити stop/target (повністю зберегти поточну поведінку).

### Крок 3 — Телеметрія та відладка
- **SSOT для аналізу:** `tpsl_ctx` як окремий dict у payload `EVT:STRATEGY_SIGNAL_PRODUCED` (і далі в backtest report).  
  `why_chain` лишається як дубль “для очей”.
- Додати короткий запис у `why_chain`, наприклад: `tpsl:regime=TREND_UP mode=pct_mult sl_pct=0.022 tp_rr=0.62`
- Додати метрики (мінімум): лічильник `regime_tpsl_used_total{symbol,regime}`.

### Крок 4 — Backtest-only увімкнення
Файли:
- `config/aurora/backtest_override.yaml` (або окремий override для aurora strategy)

Підхід:
- Увімкнути `regime_tpsl.enabled=true` тільки для бектесту.
- Залишити live конфіги без змін (або shadow mode, див. rollout нижче).

### Крок 5 — Репортинг/summary (опційно, але дуже бажано)
Щоб потім реально аналізувати:
- Додати в backtest report (в `intents[]`) поля:
  - `tpsl_ctx.regime_used`, `tpsl_ctx.sl_pct_eff`, `tpsl_ctx.tp_rr_eff`, `stop_price`, `target_price`
- У `tools/backtest_summarize.py` додати агрегати:
  - середній SL/TP bps по режимах
  - winrate по bucket’ам SL/TP

## 7) План тестування (глибокий)
### 7.1 Unit-тести (найважливіше)
Додати тести на чисту функцію обчислення TP/SL (без FSM):
- BUY/SELL: правильний бік (SL < entry для BUY, SL > entry для SELL, аналогічно для TP).
- Fallback:
  - regime=None → DEFAULT
  - regime не в мапі → DEFAULT
- Guardrails:
  - `sl_pct_eff` clamp до min/max
  - `tp_rr_eff` clamp до min/max
  - `min_dist_bps`: якщо занадто близько — або fail-closed (коли enabled), або підняти до min
- `"atr"` mode:
  - ATR missing → fallback або fail-closed (визначити політику)
  - ATR = 0 → reject

### 7.2 Unit/Contract тести конфігу
Оскільки `extra='forbid'`, додати тест, що:
- новий YAML ключ `exit.regime_tpsl` парситься в `AuroraConfig`
- invalid значення (наприклад `sl_mult` без `DEFAULT`) → fail-fast з ясною помилкою

### 7.3 Інтеграційний тест пайплайну (Strategy → DM → ExecPos)
Ціль: перевірити, що “Strategy Primacy” реально спрацьовує.

Сценарій:
1) Підняти `AuroraHandler` з тестовим `emit_fn`-колектором.
2) Прокинути `EVT:REGIME_DETECTED` (наприклад `TREND_UP`).
3) Викликати `_emit_signal` (або `on_process_strategy` з мінімальним cmd), подати `features` з `price` (+ ATR якщо треба).
4) Перевірити, що `EVT:STRATEGY_SIGNAL_PRODUCED.payload.price_ctx` містить `stop_price/target_price`.
5) Далі (мінімально) прогнати gateway `DecisionMaking` на цьому payload і впевнитись, що в `TRADE_INTENT_PROPOSED` stop/target присутні.

### 7.4 Backtest regression (системний тест)
Мета: переконатись, що в бектесті:
- ордери дійсно отримали SL/TP
- зʼявляються закриття по TP/SL, а не тільки flip/timeout
- не “вмирає” warmup/ATR

Чекліст:
- прогнати короткий бектест з `BACKTEST_MAX_TICKS` (або коротким датасетом)
- перевірити в `reports/backtests/backtest_*.json`:
  - у `intents[]` є stop/target
  - у `orders[]/fills[]` присутні bracket-дії (якщо їх пишемо в репорт)
- прогнати `tools/backtest_summarize.py`:
  - TP/SL close reasons не нульові (або хоча б зʼявляються)

### 7.5 Shadow rollout у live (після успішного backtest)
Щоб не ризикувати депозитом:
- Додати `regime_tpsl.mode="shadow"` (або `enabled=true` але `apply=false`) — **рахувати**, але **не інжектити** stop/target у `price_ctx`.
- Логувати `tpsl_ctx` і порівнювати з фактичними (конфіг-фолбек) SL/TP.
- Після 1–2 днів логів → ввімкнути apply тільки на 1 символ і 1–2 режими.

## 8) Acceptance критерії
Функціонал вважаємо готовим, якщо:
- При `enabled=false` **поведінка 1:1 як зараз** (regression OK).
- При `enabled=true`:
  - `price_ctx.stop_price/target_price` зʼявляються в сигналах Aurora
  - DecisionMaking/ExecPos використовують їх (видно в логах “STRATEGY_PRIMACY”)
  - SL/TP завжди валідні (сторона/дистанція/квантизація)
- Backtest показує різницю по метриках (хоча б: менше flip’ів або кращий PF/fee efficiency) — далі tuning.

## 9) Наступні кроки після MVP (якщо захочеш)
- V2: підтримка TP2/partial exit через розширення intent payload або через керований план брекетів.
- Вбудувати risk-based sizing, де qty залежить від фактичної SL-дистанції (щоб ризик/угода був стабільний).
- Автокалібрування параметрів: з бектесту зібрати розподіли `MAE/MFE` по режимах і підібрати `sl_mult/tp_mult` data-driven.

V3 (ідея під MEAN_REVERSION):
- “dynamic_mean” TP: для MR-режимів ціль може бути не RR%, а повернення до середнього (SMA/BB mid), **але** це потребує стабільної SSOT-фічі (BB/SMA) і readiness/warmup, тому краще після MVP.
