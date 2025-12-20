# JOURNAL — RISK-SIZING-V1-PLAN-DOC-FIRST-LIVE-500USDT

> Статус: PLAN-ONLY (READ-ONLY, P0). Жодних змін у коді / конфігах / схемах у рамках цього таску — лише дизайн-специфікація.

---

## 1) Current Behavior (Risk & Sizing Snapshot)

### 1.1 DecisionMaking / Position Sizing (Track A: Aurora Momentum)

- **Єдина реалізація runtime sizing для TradeIntent** — `DecisionMaking._calculate_position_size(symbol, price, side, context)`  
  (`apps/reference/domains/decision_making/decision_making.py:2057+`).
- **Вхідні дані:**
  - `equity` з `context["portfolio"]["equity"]` — крос-портфельний equity, не free margin.
  - `trading.decision.position_sizing.risk_fraction_q` (q) (`config/aurora/trading.yaml:51`):
    - зараз `q = 0.05` (5% ризику per trade, у сенсі Kelly-подібної формули).
  - **SL в bps** для sizing:
    - `trading.execution.brackets.sl.fixed_bps` або legacy `stop_loss_bps`
      (`config/aurora/trading.yaml:468`–:480, дефолт `sl.fixed_bps = 40` bps).
  - **Kelly meta** з `_sizing_meta`:
    - `kelly_fraction`, `regime_multiplier`, `volatility_state` (`HIGH_VOL` / `LOW_VOL` / інше).
  - **Liquidity kappa**:
    - `trading.decision.position_sizing.liquidity_kappa` (1.0) з можливим override від `features.features.liquidity_kappa`.
  - **Liquidity cap**:
    - `trading.decision.position_sizing.liquidity_based_cap_usd = 10000`.
- **Формула (упрощений контракт):**
  - Базовий notional (без Kelly):  
    `sl_bps_dec = Decimal(sl_bps)`  
    `denom = sl_bps_dec / 1e4` (якщо 0 → fallback 0.005)  
    `q_notional = q * equity / denom`
  - Kelly‑обмеження:
    - якщо `kelly_fraction > 0`: `base_notional = min(q_notional, kelly_fraction * equity)`, інакше `base_notional = q_notional`.
    - потім множиться на `regime_multiplier`, якщо цей множник > 0.
  - Волатильність:
    - `volatility_multiplier` = 1.4 (HIGH_VOL), 0.8 (LOW_VOL), 1.0 (інше),
    - `adjusted_sl_bps = sl_bps_dec * volatility_multiplier`,
    - повторна оцінка notional з новим SL (`adjusted_notional`).
  - Liquidity kappa та liquidity cap:
    - `final_pos_size_usd = min(adjusted_notional * kappa_liq, liquidity_based_cap_usd)`.
  - Якщо `q_risk` не заданий → fallback **10% від equity**, обмежений `liquidity_based_cap_usd`.
  - Якщо `final_pos_size_usd < min_position_size_usd` → reject (NRR).
  - `qty = final_pos_size_usd / price` → quantize до `step_size` з `trading.instruments.<SYMBOL>.step_size` з округленням вниз.
- **Важливий факт:** `_calculate_position_size` **не дивиться на відкриті позиції** по символу, а тільки на equity та конфіг → кожен новий intent по символу рахується так, ніби позиції немає (anti‑pyramiding на рівні sizing відсутній).

### 1.2 Mean Reversion (Track B: 1m MR)

- Окремий handler `MeanReversionHandler` (`apps/reference/domains/decision_making/mean_reversion_handler.py`):
  - бере сигнали з `MeanReversion1mStrategy`,
  - емісить `EVT:TRADE_INTENT_PROPOSED` у своєму DTO‑форматі.
- **Розмір позиції** в MR:
  - фіксований `position_size_usd` (`config/aurora/trading.yaml:330`–:361) або з `config/aurora/strategies/mean_reversion.yaml`,
  - `_get_position_size_usd()` повертає `Decimal(position_size_usd)` — **не залежить від equity/SL_bps/volatility**.
- **SL/TP** для MR:
  - можуть братись з `sl_pct` per asset у MR‑конфігу + ATR‑множники,
  - але з точки зору Sizing це просто фіксований notional.

### 1.3 Execution / Margin / Leverage / ExposureGuard

- **ExecPosFSM** (`apps/reference/domains/execution_position/fsm.py`):
  - маршрутизує `CMD:OPEN` → `OpenFlowFSM` → `DEC:OPEN` → `_execute_decision` (MARKET entry + TP/SL brackets),
  - тримає `ExposureGuard`, `OrderGuardian`, `OrderTimeoutWatchdog`.
- **Плече (leverage_defaults):**
  - `trading.execution.exposure.leverage_defaults` (`config/aurora/trading.yaml:545`–:551`):  
    - BTC/ETH/SOL/XRP/DOGE: `20x` (за замовчуванням).
  - ExposureGuard використовує `symbol_leverage` для конвертації notional→margin (`reserve_margin = notional_usd / leverage`).
  - Важливо: **користувач реально виставляє x10 вручну на біржі**, але система припускає leverage по конфігу. Це треба явно прописати в новому risk‑контракті.
- **Margin / exposure state:**
  - `position_tracking._calc_margin_used_usd(positions)` оцінює поточний margin (за API або через notional/leverage_defaults).
  - ExposureGuard (`apps/reference/domains/execution_position/exposure_guard.py`):
    - читає:
      - `equity_free_usdt`,
      - `open_positions_margin_usd`,
      - `positions_by_side.{long_margin,short_margin}`,
    - рахує:
      - `margin_limit = equity_free_usdt * max_equity_utilization_pct`,
      - ліміти per side (`max_long_utilization_pct`, `max_short_utilization_pct`),
      - directional ratio (`max_directional_ratio`),
      - concentration (`max_concentration_pct`),
      - soft‑limits `trading.risk.soft_limits.*` (clip per‑side та per‑portfolio).
    - при перевищенні:
      - може повертати `{"allowed": False, ...}` → повний reject,
      - або `{"allowed": True, "shrink_notional": X}` → **soft‑clip**, але зараз `shrink_notional` не використовується ExecPosFSM для перерахунку qty (це вже зафіксовано в попередньому аудиті).

### 1.4 TP/SL / Brackets / Trailing / Max Hold

- **Перша постановка SL/TP**:
  - Після MARKET‑entry ExecPosFSM рахує TP/SL від `MARK_PRICE` через `calc_tp_sl_from_mark(...)`  
    (`apps/reference/domains/execution_position/utils.py:173`):  
    `tp = mark * (1 ± tp_bps/basis_points_base)`  
    `sl = mark * (1 ∓ sl_bps/basis_points_base)`  
    з `sl_bps`, `tp_bps` з `trading.execution.manage.brackets.{sl.fixed_bps,tp.fixed_bps}` (`config/aurora/trading.yaml:468`–:480`).
- **ManageFlowFSM._calculate_bracket_prices(...)** (`fsm_manage.py:781+`):
  - для **Aurora per‑instrument**:
    - якщо є `trading.aurora_instruments.<SYMBOL>.exit.sl_pct` → SL = entry ± sl_pct,
    - якщо є `take_profit.tp_low_ratio/tp_high_ratio` → TP1/TP2 = entry ± risk_pct * ratio,
    - інакше fallback на глобальні `brackets.sl.fixed_bps` / `tp.fixed_bps`.
  - застосовується safety offset `offset_bps` (`config/aurora/trading.yaml:468`–:480`):
    - SL трішки далі від entry (ширший ризик),
    - TP ще далі (у бік прибутку).
- **Trailing stop** (`fsm_manage.py:1210+`):
  - `aurora_instruments.<SYMBOL>.trailing_stop.enabled` → тільки тоді SL пересувається за піковою ціною,
  - SL рухається лише у напрямку фіксації прибутку (не розширює зону збитку).
- **Max hold**:
  - пер‑інструмент `exit.max_hold_sec` (ETH/SOL/DOGE/XRP):  
    `config/aurora/trading.yaml:153`, :197`, :249`, :297` — використовується `_check_max_hold_time(...)` у ManageFlowFSM.
  - failsafe `CloseFlowFSM(max_hold_sec=86400)` — запасний 24h watchdog.

### 1.5 Anti‑Pyramiding (або його відсутність)

- **Немає явної anti‑pyramiding логіки**:
  - DecisionMaking:
    - `_calculate_position_size` і `_propose_trade_intent` **не дивляться** на відкриті позиції по символу,
    - QoS обмежує **частоту intents** (`symbol_cooldown_sec`, `max_intents_per_minute_per_symbol`), але не загальний notional по символу.
  - ExecutionPosition:
    - OpenFlowFSM не знає про “max_additions_per_position”,
    - ExposureGuard обмежує загальний margin/notional, але дозволяє розбивати позицію на багато entry‑ордерів, поки сумарний margin у ліміті,
    - немає правила “одна позиція = один entry”.

### 1.6 Пер‑символьна табличка (BTC/ETH/SOL/XRP/DOGE, live Aurora конфіг)

**Для equity=500 USDT (поточна логіка):**
- Розмір позиції задається **однією глобальною** `risk_fraction_q=0.05` + SL_bps=40 + Kelly/meta → ≈ **однакова risk‑фракція для всіх символів**, далі обрізка лише по liquidity cap та exposure guard.

**Пер‑символьні інструмент‑спеки та SL/TP (Aurora Track A):**

| Symbol  | Step Size | Tick Size | Min Notional | Leverage Default | SL Source                      | SL Param            | TP Source                         | TP Params                                 |
|--------|-----------|-----------|-------------:|------------------|--------------------------------|---------------------|------------------------------------|-------------------------------------------|
| BTCUSDT| 0.001     | 0.10      | 10 USDT      | 20x              | Global brackets (нет exit.sl_pct)| `sl.fixed_bps=40`   | Global brackets                   | `tp.fixed_bps=80`                         |
| ETHUSDT| 0.001     | 0.01      | 10 USDT      | 20x              | `aurora_instruments.ETH.exit`  | `sl_pct=0.019`      | `aurora_instruments.ETH.take_profit` | `tp_low_ratio=0.4`, `tp_high_ratio=1.4`  |
| SOLUSDT| 0.01      | 0.01      | 10 USDT      | 20x              | `aurora_instruments.SOL.exit`  | `sl_pct=0.027`      | `aurora_instruments.SOL.take_profit` | `tp_low_ratio=0.48`, `tp_high_ratio=0.80`|
| DOGEUSDT| 1        | 0.00001   | 10 USDT      | 20x              | `aurora_instruments.DOGE.exit` | `sl_pct=0.0197`     | `aurora_instruments.DOGE.take_profit` | `tp_low_ratio=0.5`, `tp_high_ratio=1.0` |
| XRPUSDT| 0.1       | 0.0001    | 10 USDT      | 20x              | `aurora_instruments.XRP.exit`  | `sl_pct=0.0144`     | `aurora_instruments.XRP.take_profit` | `tp_low_ratio=0.5`, `tp_high_ratio=1.0` |

> Висновок: зараз sizing — **глобальний** (один q для всіх символів), а SL/TP — частково пер‑інструментні (ETH/SOL/DOGE/XRP), частково глобальні (BTC). Anti‑pyramiding нема; leverage_defaults=20x, але фактичне плече користувач ставить вручну (≈10x).

---

## 2) Target Risk Contract V1 (Перший лайв на 500 USDT)

### 2.1 Цільовий risk‑профіль (margin‑load per symbol)

Для депозиту **E = 500 USDT** і **effective leverage L ≈ 10x** (ставиться вручну на біржі) цільовий контракт:

- BTC:   ~4% від капіталу в **маржі** при повному завантаженні → `m_BTC ≈ 0.04 * E`.
- ETH:   ~5.5% → `m_ETH ≈ 0.055 * E`.
- XRP:   ~4% → `m_XRP ≈ 0.04 * E`.
- DOGE:  ~5% → `m_DOGE ≈ 0.05 * E`.
- SOL:   ~6% → `m_SOL ≈ 0.06 * E`.

Сумарно:  
`m_total ≈ (0.04 + 0.055 + 0.04 + 0.05 + 0.06) * E = 0.245 * E`  
→ для `E=500` це ~122.5 USDT маржі, тобто **24.5% equity**.

При effective leverage `L=10` **цільовий notional per symbol**:

| Symbol  | Target Margin % of Equity | Target Margin (USD, E=500) | Target Notional (USD) = Margin * L |
|--------|---------------------------:|----------------------------:|-----------------------------------:|
| BTCUSDT| 4.0%                       | 20.0                        | 200                                |
| ETHUSDT| 5.5%                       | 27.5                        | 275                                |
| XRPUSDT| 4.0%                       | 20.0                        | 200                                |
| DOGEUSDT| 5.0%                      | 25.0                        | 250                                |
| SOLUSDT| 6.0%                       | 30.0                        | 300                                |
| **Total** | **24.5%**               | **122.5**                   | **1225**                           |

Це і є **Risk Contract V1**:  
> “При equity ≈ 500 USDT та effective leverage ≈ 10x система не повинна дозволяти сукупний margin‑load > ~24.5% і пер‑символьні margin‑фракції, що виходять за 4/5.5/4/5/6% відповідно (у режимі повного завантаження по всім п’ятьом інструментам).”

### 2.2 Формалізація в термінах системи

1. **Система оперує notional (USD), а не реальним плечем.**  
   Ми вводимо поняття **effective_leverage L_eff** як параметр risk‑контракту (а не “магічне число” в коді).  
   На рівні дизайну:  
   `notional_target_i(E) = m_fraction_i * E * L_eff`, де `m_fraction_i` — цільова margin‑фракція по символу.

2. **Цільові величини:**
   - `m_fraction_BTC = 0.04`
   - `m_fraction_ETH = 0.055`
   - `m_fraction_XRP = 0.04`
   - `m_fraction_DOGE = 0.05`
   - `m_fraction_SOL = 0.06`
   - `L_eff ≈ 10` (задокументована константа в risk‑контракті, а не в коді).

3. **Очікуваний контракт для sizing:**
   - На рівні DecisionMaking/Execution:
     - або через **per‑symbol target_notional_usd(E)**,  
     - або через **per‑symbol risk_fraction_per_symbol q_i(E)**, яке мапиться на margin‑фракції з урахуванням L_eff.

4. **Single-entry вимога:**
   - Для Risk Contract V1 припускається, що:
     - по кожному символу в кожен момент часу має бути **один “активний трейд”** у напрямку стратегії,
     - повторні входи в той самий бік мають бути заборонені (або жорстко обмежені) до закриття позиції або до явного partial exit сценарію (TP1/TP2).

---

## 3) Design Options (як це реалізувати, без коду)

### Варіант A: `target_notional_usd_per_symbol(E)` + upper‑clip у `_calculate_position_size`

**Ідея:**
- Ввести в конфігу **пер‑символьні таргети notional** як функцію від equity:
  - `trading.decision.position_sizing.per_symbol_notional_targets.<SYMBOL>.base_fraction` (наприклад, 0.04 для BTC),
  - `effective_leverage` як глобальний параметр Risk Contract (документований, а не зашитий).
- У `_calculate_position_size`:
  - спочатку рахуємо існуючий `final_pos_size_usd` за Kelly/q/sl_bps (тобто залишаємо всю поточну складну логіку),
  - потім застосовуємо **пер‑символьну стелю**:
    - `notional_target_i(E) = base_fraction_i * equity * L_eff`,
    - `final_pos_size_usd = min(final_pos_size_usd, notional_target_i(E))`.

**Плюси:**
- Зберігаємо весь поточний дизайн (Kelly, volatility, liquidity‑kappa), додаючи лише **додаткову “кришку”** per symbol.
- Легко відобразити бажаний baseline (4/5.5/4/5/6%) для E=500; при зміні equity план масштабується лінійно.
- Можна використовувати той самий механізм для інших депозитів без зміни коду (тільки конфіг).

**Мінуси:**
- Щоб отримати **“саме 4% margin‑load”** потрібно узгодити L_eff з реальним плечем на біржі — це параметр, який живе у risk‑контракті, але не контрольований кодом.
- Поточний ExposureGuard з leverage_defaults=20x може бачити інший margin‑load, ніж очікує контракт (якщо користувач реально торгує на x10).

**Модулі, які доведеться змінити (у наступних тасках):**
- `apps/reference/domains/decision_making/decision_making.py`:
  - `_calculate_position_size` — додати пер‑символьний upper‑clip по notional.
  - `_get_aurora_instrument_cfg` — можливо, переюзати для читання per‑symbol sizing config.
- `apps/reference/config_models.py`:
  - додати Pydantic‑моделі для `per_symbol_notional_targets` / `effective_leverage`.
- **Конфіги:**
  - `config/aurora/trading.yaml` — новий блок `position_sizing.per_symbol_targets`.

**Вплив на backtest/Optuna:**
- Поточні backtest‑рушії (`BacktestEngineV2`, `BacktestEngineMultiscale`) працюють з **fixed position_size** (200 USD) і **single-entry**.
- Для узгодження з Risk Contract V1:
  - або нічого не змінюємо в backtest (вважаємо, що лайв‑система з dynamic sizing — надбудова над backtest),
  - або додаємо в майбутньому адаптацію `position_size` у backtest так, щоб воно співпадало з `notional_target_i(E)`.

---

### Варіант B: `risk_fraction_per_symbol` (локальний q_i) + документований mapping у margin‑простір

**Ідея:**
- Зараз є один глобальний `risk_fraction_q=0.05`.
- Запровадити **пер‑символьні q_i**:
  - `trading.decision.position_sizing.per_symbol_risk_fraction.<SYMBOL>`:
    - q_BTC, q_ETH, q_XRP, q_DOGE, q_SOL.
- У `_calculate_position_size`:
  - при виклику для конкретного symbol:
    - шукаємо `q_i` per symbol; якщо немає → fallback на глобальний q,
    - формула `q_notional = q_i * equity / (SL_bps/1e4)` залишається,
    - далі Kelly, regime, volatility, liquidity стосуються вже `q_notional_i`.

**Mapping до margin‑фракцій:**
- Для Risk Contract V1 ми хочемо гарантовано не перевищувати target:
  - `margin_i = notional_i / L_eff`,
  - `margin_i / equity <= m_fraction_i`.
- Можемо підібрати q_i так, щоб **при базових SL_bps/kelly без додаткових множників**:
  - `q_i * equity / (SL_bps/1e4) ≈ m_fraction_i * equity * L_eff`.
  - Звідси: `q_i ≈ m_fraction_i * L_eff * SL_bps / 1e4`.
  - Це дає **пер‑символьні q_i**, які реалізують бажаний margin‑load у baseline.

**Плюси:**
- Використовує вже існуючу семантику `risk_fraction_q`, не вводячи нового типу параметрів (тільки робимо її пер‑символьною).
- Дає аналітичний зв’язок між risk_fraction та margin‑фракцією.

**Мінуси:**
- Вплив Kelly, regime_multiplier, volatility_multiplier може **відхиляти** фактичний margin‑load від baseline (q_i — лише початкова точка).
- Все ще нема жорсткого **upper‑clip**: при високому Kelly або низькому SL_bps позиція може вийти за цільову margin‑фракцію.

**Модулі для змін:**
- `DecisionMaking._calculate_position_size` — читати `q_i` per symbol.
- `config_models.TradingConfig` — додати структуру `per_symbol_risk_fraction`.
- `config/aurora/trading.yaml` — додати per‑symbol q_i.

**Вплив на backtest/Optuna:**
- Найпростіше: залишити backtest як є (fixed 200 USD) і задокументувати, що live sizing відрізняється.
- Якщо захочемо повну відповідність:
  - у backtest‑config створити профілі, де `position_size` ≈ `notional_target_i(500)` для кожного symbol.

---

### Варіант C: Hybrid — `target_notional_usd_per_symbol` + per‑symbol q_i + hard upper‑clip у ExposureGuard

**Ідея:**
- Об’єднати A і B:
  - використати per‑symbol q_i для “форми” формули,
  - використати `notional_target_i(E)` як **жорсткий верхній ліміт** на рівні ExposureGuard.

**Механіка:**
1. DecisionMaking:
   - рахує `final_pos_size_usd_i` з per‑symbol q_i.
2. ExposureGuard:
   - додаємо новий блок “per‑symbol max_notional_usd”:
     - `trading.execution.exposure.per_symbol_notional_cap_usd.<SYMBOL>`,
   - при розрахунку `reserve_margin`:
     - якщо `notional_usd > cap_i(E)`, робимо або:
       - hard reject,
       - або soft‑clip до `cap_i(E)` через `shrink_notional`.

**Плюси:**
- Дві незалежні “скоби”:
  - м’який контроль через q_i,
  - жорсткий через ExposureGuard (fail‑closed).
- Добре вписується в **Constitution FSM / fail‑closed**: якщо щось пішло не так у sizing — exposure guard все одно не пустить поза контракт.

**Мінуси:**
- Складніше валідувати й пояснювати (дві системи лімітів).
- Потрібно акуратно звести soft‑clip (`soft_limits`) і новий per‑symbol cap, щоб не було “подвійного кліпу” з дивною поведінкою.

**Модулі:**
- Все з Варіантів A+B **плюс**:
  - `apps/reference/domains/execution_position/exposure_guard.py` — додати per‑symbol notional cap у `can_open`.

**Backtest/Optuna:**
- Те ж саме, що в A/B: backtest може залишитись fixed‑size, а new risk contract — лише live‑feature.

---

## 4) Anti‑Pyramiding & Single‑Entry Rules

### 4.1 Де зараз виникають багаторазові входи

- **DecisionMaking.on_features(...)**:
  - на кожен `EVT:FEATURES_CALCULATED` може емісити новий `TRADE_INTENT` по символу, якщо:
    - QoS не блокує (cooldown, max_intents/min),
    - risk‑management та exposure_cache пропускають.
- **ExecutionPosition**:
  - не має правила “одна позиція = один entry”:
    - OpenFlowFSM просто прийме CMD:OPEN, якщо quantity/price валідні,
    - ExposureGuard лише перевіряє margin/notional/ratio, не кількість entry‑ордерів,
    - ManageFlowFSM просто веде одну позицію й brackets; кілька послідовних entry можуть **змінювати середню ціну і розмір**.

### 4.2 Варіанти введення single‑entry контракту

#### Варіант 1: Anti‑pyramiding у DecisionMaking (до емісії TradeIntent)

**Ідея:**
- Перед `_propose_trade_intent(symbol, ...)`:
  - подивитись на `latest_portfolio.positions` (або спрощений exposure_cache),
  - якщо вже є **відкрита позиція по symbol в тому ж напрямку (side)**:
    - **не емісити новий intent**,
    - або емісити intent тільки якщо це **explicit scale‑in mode** (в іншому профілі).

**Плюси:**
- Проста й зрозуміла логіка: “DecisionMaking не генерує дубль‑entry”.
- Легше тестувати (unit‑тести DecisionMaking).

**Мінуси:**
- Потребує надійного та свіжого `portfolio_state` з PositionTracking (проблема staleness),
- Не захищає від зовнішнього/manual entry (якщо хтось відкрив позицію руками поза системою).

#### Варіант 2: Anti‑pyramiding у ExecPosFSM / ExposureGuard (hard gate)

**Ідея:**
- В `ExecPosFSM._check_exposure_fail_closed` / `ExposureGuard.can_open`:
  - додати правило:
    - якщо **по symbol вже є відкрита позиція** (qty≠0) і сумарний notional ≥ `max_notional_per_symbol`:
      - CMD:OPEN блокується з NRR‑кодом типу `NRR-ANTI-PYRAMIDING`.

**Плюси:**
- Fail‑closed на рівні execution — не залежить від рішення DecisionMaking.
- Можна використати вже існуючу інформацію `positions` / `open_positions_usd`.

**Мінуси:**
- Ускладнення ExposureGuard (ще одна гілка),
- Треба чітко визначити, як рахувати “already open” при часткових закриттях/TP1/TP2.

#### Варіант 3: Hybrid (soft у DecisionMaking, hard у ExecPosFSM)

**Ідея:**
- DecisionMaking:
  - **не емісить** TradeIntent, якщо бачить активну позицію по symbol/side.
- ExecPosFSM:
  - дублююча **hard‑перевірка**:
    - якщо позиція є, але DecisionMaking з якоїсь причини все ж емісив intent → block CMD:OPEN.

**Плюси:**
- Відповідає fail‑closed принципу,
- Має кращу прозорість (дві незалежні перевірки).

**Мінуси:**
- Потрібно узгодити NRR‑коди і логування, щоб не заплутати операторів/лог‑аналіз.

---

## 5) Testing & TDD Outline (план тестів)

### 5.1 Unit‑тести для `_calculate_position_size` з новим контрактом

- **Для пер‑символьного `target_notional_usd` (Варіант A):**
  - Тест 1: `equity=500`, BTC, L_eff=10 → ensure `final_pos_size_usd ≤ 200` (±толеранс).
  - Тест 2: ETH → `≤ 275`, XRP → `≤ 200`, DOGE → `≤ 250`, SOL → `≤ 300`.
  - Тест 3: при великому equity (наприклад, 5000) перевірити, що:
    - notional масштабуються лінійно з E.
- **Для per‑symbol q_i (Варіант B):**
  - Тести для кожного symbol, де q_i обрані так, щоб без Kelly/volatility результат давав target notional при E=500.
  - Перевірити, що зміна SL_bps змінює notional у правильний бік (більший SL відстань → менший size).

### 5.2 Інтеграційні тести (DecisionMaking + ExecPosFSM + ExposureGuard)

- **Single‑entry per symbol:**
  - Сценарій: equity=500, відкрити позицію по BTC → спроба другого CMD:OPEN:
    - очікування: NRR anti‑pyramiding (або decision‑level block).
- **Max_notional_per_symbol:**
  - Сценарій: згенерувати TradeIntent з великим qty, який перевищує per‑symbol cap:
    - очікування: або shrink_to_fit до cap, або hard reject.
- **Aggregate margin load:**
  - Поставити по всіх 5 символах позиції на target notional,
  - перевірити, що:
    - сумарний margin ≈ 24.5% equity (з урахуванням L_eff),
    - ExposureGuard не дозволяє нові ордери, які помітно заводять margin > заданого порогу (наприклад 30%).

### 5.3 Backtest / Optuna адаптація (опціонально)

- Нові тести для backtest‑runner’ів:
  - профілі, де `position_size` у backtest збігається з target notional (для equity=500),
  - перевірка, що PnL‑профіль із fixed size приблизно відповідає live risk‑контракту.

---

## 6) Migration & Rollout Plan

### 6.1 Feature‑flag для нового режиму sizing

- Ввести в конфігах **режим роботи** sizing:
  - `trading.decision.position_sizing.mode: "legacy" | "risk_contract_v1"`.
- Семантика:
  - `"legacy"`: використовувати повністю поточну логіку (`risk_fraction_q`, Kelly, SL_bps, без per‑symbol caps).
  - `"risk_contract_v1"`:
    - активувати per‑symbol notional targets / q_i,
    - активувати anti‑pyramiding single‑entry rule,
    - активувати per‑symbol caps у ExposureGuard (якщо обраний Варіант C).

### 6.2 Dual‑config для testnet vs prod

- **Testnet:**
  - дозволити вмикати/вимикати Risk Contract V1 через окремий профіль (`mode: "testnet_risk_v1"`),
  - зберегти можливість запускати старий профіль для порівняння.
- **Prod (перший лайв):**
  - тільки після:
    - проходження unit + integration тестів,
    - валідації через кілька testnet‑сесій з “dry‑run” логуванням.

### 6.3 Rollback‑план

- У разі аномалій:
  - перемикання `position_sizing.mode` назад на `"legacy"` без зміни коду,
  - ExposureGuard продовжує працювати як зараз, без додаткових per‑symbol caps,
  - достатньо reload конфігурації (через існуючий hot‑reload механізм, якщо налаштований).

---

## 7) Open Questions / Risks

1. **Реальне плече vs leverage_defaults:**
   - Система зараз припускає `leverage_defaults=20x`, але користувач ставить ~10x.
   - Потрібне рішення:
     - або встановлювати leverage на біржі автоматично й робити L_eff=leverage_defaults,
     - або явно документувати L_eff як “contract‑level assumption” і підганяти leverage_defaults під реальність.

2. **Геп між backtest та live sizing:**
   - Backtest використовує fixed `position_size`, live — dynamic sizing з Kelly/q/sl.
   - Для більшої довіри до результатів треба:
     - або зробити backtest aware of risk‑contract (position_size як функція equity),
     - або у бек‑репортах завжди явно зазначати, що live risk‑профіль відрізняється.

3. **Зміна equity в часі:**
   - Risk Contract V1 зараз лінійний в E (proportional).
   - Питання:
     - чи хочемо ми upper‑cap по notional, який **не росте** вище певного рівня навіть при рості equity?
     - чи потрібні “risk tiers” (наприклад: до 500$, 500–2000$, >2000$)?

4. **Сумісність з MR track B:**
   - Mean Reversion наразі має свій fixed `position_size_usd`.
   - Треба вирішити:
     - чи підпорядковується MR тому ж Risk Contract V1 (через окремі per‑symbol caps),
     - чи MR залишається “окремим профілем” з власним risk‑контрактом.

5. **Взаємодія з soft‑limits (clipping):**
   - Нові per‑symbol caps можуть конфліктувати з `risk.soft_limits` (clip per side / margin).
   - Потрібна чітка ієрархія:
     - спочатку per‑symbol cap,
     - потім soft‑clip,
     - і тільки потім hard reject.

---

## Proposed Follow-up Tasks

- `[TASK PROPOSAL] RISK-SIZING-V1-IMPLEMENTATION-CORE`  
  Реалізувати обраний дизайн (A/B/C або hybrid) у `DecisionMaking`, `ExposureGuard`, конфіг‑моделях та конфігах з feature‑flag’ом `position_sizing.mode`.

- `[TASK PROPOSAL] RISK-SIZING-V1-TESTS`  
  Додати unit‑тести для `_calculate_position_size` та інтеграційні тести для ExecPosFSM/ExposureGuard, які перевіряють:
  - відповідність target notional / margin‑фракцій per symbol,
  - single‑entry контракт по символу.

- `[TASK PROPOSAL] RISK-SIZING-V1-ANTI-PYRAMIDING`  
  Спроєктувати та реалізувати anti‑pyramiding:
  - soft‑gate в DecisionMaking,
  - hard‑gate в ExecPosFSM/ExposureGuard,
  - узгоджені NRR‑коди та логування.

