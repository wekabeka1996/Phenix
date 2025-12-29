# Execution Position — Risk & ROI Migration Plan

**Status:** In progress — initial implementation underway  
**Scope:** Перехід системи на розмір позиції у відсотках від капіталу (з урахуванням плеча) та TP/SL, що задаються через ROI (+50% TP, −35% SL), із узгодженням денних лімітів та моніторингу позицій/ордерів.

## Progress log (2025-12-02)
- [x] Added ROI fields to `config/domains/execution.yaml` aggregated_oco blocks (`sl_roi_pct`, `tp_roi_pct`, `roi_basis`, `leverage_source`).
- [x] Extended `AggregatedOcoConfig` + resolver with ROI attributes and helpers `resolve_effective_leverage` / `compute_sl_tp_from_roi`.
- [x] DecisionMaking sizing now reads `config_v2.domains.sizing.defaults.max_risk_pct` and computes SL distance from ROI+leverage (fallback to SL bps), keeping liquidity/regime/Kelly guards.
- [x] RiskManagement now resolves `DailyRiskState` once, feeds portfolio updates, and emits `daily_gate_status/detail` in risk parameters (fail-closed on daily gate breaches).
- [x] Tests: `pytest tests/units/test_daily_gate_unit.py -k can_open --maxfail=1` (pass).
- [x] DecisionMaking blocks intents when `daily_gate_status` != OPEN, logging NRR and clearing symbol state.
- [x] ExecPos runtime now computes ROI-based sl_pct/tp_rr from typed config + leverage, surfaces ROI targets (sl/tp prices, leverage) into position snapshots and exposure updates for downstream consumers.
- [x] ROI leverage lookup fixed to use per-symbol input in bracket evaluation/recovery; exposure updates carry ROI/target prices; guardian register/clear remains wired in runtime bracket application.
- [x] ExecPos bracket placement retries now detect Binance -4116 (duplicate clientOrderId) and regenerate a fresh clientOrderId per retry to avoid duplicate failures.

---

## 1. Поточний стан системи

### 1.1 Позиційний розмір / % від капіталу

**Код:**
- `apps/reference/domains/decision_making/decision_making.py:1664+` — `DecisionMaking._calculate_position_size(...)`

**Логіка зараз:**
- Береться `equity_free_usdt` з `PortfolioSnapshot` (через `portfolio_provider`).
- Зчитується конфіг `trading.decision.position_sizing`:
  - `risk_fraction_q` — частка капіталу, яку дозволено втратити при спрацюванні SL (risk per trade).
  - `liquidity_kappa`, `liquidity_kappa_mode` — корекція на ліквідність (dynamic/static).
- Зчитується `sl_bps` з конфігу:
  - `trading.execution.brackets.sl.fixed_bps`  
  (див. також резолвер `resolve_brackets_config` у `apps/reference/domains/execution_position/brackets_config.py:173`).
- Розрахунок (спрощено):
  - Нехай:
    - `q_risk = risk_fraction_q`
    - `equity = equity_free_usdt`
    - `sl_bps` — відстань до SL у bps.
  - Формула:
    - `denom = sl_bps / 10000`
    - `q_notional = q_risk * equity / denom`
  - Ідея: при русі ціни до SL (на `sl_bps`) втрата ≈ `q_risk * equity`, тобто sizing вже фактично в термінах **% від капіталу при спрацюванні SL**.
- Далі:
  - застосовуються Kelly‑множники, режими, волатильність (через `_sizing_meta`);
  - результат обмежується `liq_cap_usd` (ліквіднісний cap);
  - нотіонал ділять на поточну ціну й округлюють по `step_size` з `trading.instruments.<symbol>.step_size`.

### 1.2 TP/SL (brackets та Aggregator OCO)

**Конфіг:**
- `config/domains/execution.yaml`
  - Блок `brackets`:
    - `sl.fixed_bps`, `tp.fixed_bps`, `offset_bps` — основні BPS для SL/TP.
  - Блок `exposure.leverage_defaults` — дефолтні плечі для символів.

**Код:**
- `apps/reference/domains/execution_position/brackets_config.py`
  - `DEFAULT_SL_BPS = Decimal("50")`
  - `DEFAULT_TP_BPS = Decimal("100")`
  - `resolve_brackets_config(config, symbol)`:
    - читає `execution.brackets` із `config_v2.domains.execution`;
    - повертає `ResolvedBrackets(sl_bps, tp_bps, offset_bps, ...)`.

**Aggregator OCO:**
- `apps/reference/domains/execution_position/config.py`
  - `AggregatedOcoConfig`:
    - `sl_pct` — відстань до SL у частках від ціни (0.02 = 2%).
    - `tp_rr` — Reward/Risk ratio (2.0 = 2:1).
- `ExecutionPositionConfig.aggregated_oco` — типізований контейнер цих параметрів.

На даний момент SL/TP задаються через BPS/`sl_pct`+`tp_rr`, але **ROI (прибутковість на маржу) явно не фігурує** в конфігу.

### 1.3 Денний ліміт / ліміт збитків

**Конфіг v2:**
- `config/domains/risk.yaml`:
  - `daily_limits.max_drawdown_pct`
  - `daily_limits.max_loss_pct`
  - `daily_limits.max_loss_usd`
  - `daily_limits.reset_time_utc`
  - `budgets.max_daily_loss_pct`

**Код:**
- `apps/reference/config_risk.py`:
  - `resolve_daily_risk_state(cfg)`:
    - якщо є `config.config_v2.domains["risk"]` → будує `DailyRiskState` з v2;
    - інакше — fallback до legacy `trading.risk.*`.
- `apps/reference/domains/risk_management/daily_gate.py`:
  - `DailyRiskState`:
    - зчитує `risk.daily_limits`/`risk.daily`;
    - внутрішній стан:
      - `_equity_open` / `_equity_now`: капітал на початку дня / поточний;
      - `_realized_pnl`: накопичений реалізований PnL.
    - `can_open()`:
      - якщо немає валідного `equity_open`/`equity_now` → `NO_EQUITY` (fail‑closed);
      - якщо drawdown ≥ `max_drawdown_pct` → `MAX_DRAWDOWN`;
      - якщо `-realized_pnl >= max_realized_loss_usd` → `MAX_REALIZED_LOSS`.
- `apps/reference/domains/risk_management/risk_management.py`:
  - у `__init__` викликає `resolve_daily_risk_state`, `resolve_risk_score_weights`, `resolve_trading_allowed_thresholds`;
  - `on_portfolio_state_updated(...)`:
    - рахує daily drawdown від `equity` та зберігає `current_daily_drawdown`;
  - `_calculate_risk_parameters(...)`:
    - використовує `DailyRiskState` як частину портфельного гейта (circuit breaker).

### 1.4 Моніторинг позицій та ордерів

**ExecPosRuntimeV2:**
- `apps/reference/domains/execution_position/shadow_execpos/runtime.py`:
  - `_positions_by_symbol`: стан позицій;
  - `order_index`: індекс ордерів (`infra/order_index.py`);
  - `_guard_loop()`:
    - проходиться по активних позиціях;
    - перевіряє свіжість `ORDERS_SNAPSHOT`;
    - викликає `_evaluate_brackets(symbol, pos, reason="guard_loop")`;
    - робить паузи `asyncio.sleep(self._guard_loop_interval_sec)` та `asyncio.sleep(0.2)` між символами.
  - `ExecPosWALWriter` + `ExposureBridge`:
    - пишуть WAL (EXEC_TRADE, EXEC_POSITION);
    - емітять `EVT:EXEC_POS_EXPOSURE_UPDATED`.

**ExposureBridge:**
- `apps/reference/domains/execution_position/shadow_execpos/exposure_bridge.py`:
  - `_calculate_exposure_usdt(position_state)`:
    - `exposure_usdt = qty * entry_price`;
  - `emit_exposure_update(...)`:
    - формує подію з `symbol`, `side`, `qty`, `entry_price`, `exposure_usdt`.

**OrderGuardian (пасивний):**
- `apps/reference/services/order_guardian.py`:
  - `OrderGuardian`:
    - тримає `BracketSetMeta` для `(symbol, side)` (SL/TP ids);
    - не запускає активних лупів (polling/cancel/dr) — лише метадані та лог в `logs/order_guardian.log`.

**Специфікація:**
- `docs/EXEC_POS_V2_RUNTIME_SPEC.md`:
  - Описує, що Aggregated OCO в `ExecPosRuntimeV2` поки частково працює у **detect‑only** режимі; фактичне auto‑heal/auto‑place ще не повністю пров’язано.

---

## 2. Цільова модель

### 2.1 Позиція як % від капіталу з урахуванням плеча

Вимоги:
- Єдине джерело **risk per trade** `R_eq` (частка equity, яку можна втратити при досягненні SL).
- Для кожного символу визначене ефективне плече `L` (з інструментів/експозиції).
- Розмір позиції `N` у нотіоналі повинен задовольняти:

> При русі ціни до SL вартість позиції втрачає ≈ `R_eq * equity`.

Для лінійних ф’ючерсів (як у Binance Futures):
- Якщо `sl_pct_price` — відстань до SL у частках від ціни (наприклад 0.035 = 3.5%),
  - то `N * sl_pct_price ≈ R_eq * equity`.
  - звідси: `N = R_eq * equity / sl_pct_price`.

Система вже використовує аналогічну логіку (через `sl_bps`), але:
- `sl_bps`/`sl_pct` не прив’язані до ROI й плеча;
- параметри risk per trade налаштовані через `trading.decision.position_sizing.risk_fraction_q`, а не через єдиний `sizing.defaults.max_risk_pct`.

### 2.2 TP/SL через ROI (+50% / −35%)

Ціль: задавати TP/SL у термінах **ROI на маржу**, а не просто відстань у ціні.

Нехай:
- ROI_SL_margin = 35% (цільовий збиток на маржу);
- ROI_TP_margin = 50% (цільовий прибуток на маржу);
- `L` — ефективне плече по символу.

Приблизно для лінійних ф’ючерсів:

> ROI_margin ≈ L * ΔP%

де `ΔP%` — відносний рух ціни від entry.

Тоді:
- Відстань до SL у ціні:
  - `sl_pct_price = ROI_SL_margin / (100 * L)` (у частках від ціни, наприклад 0.035).
- Відстань до TP у ціні:
  - `tp_pct_price = ROI_TP_margin / (100 * L)`.
- Відношення `tp_rr`:
  - `tp_rr = tp_pct_price / sl_pct_price = ROI_TP_margin / ROI_SL_margin`.

Приклад: L=10, ROI_SL=35%, ROI_TP=50%:
- `sl_pct_price = 0.35 / (100 * 10) = 0.0035` (0.35% по ціні);
- `tp_pct_price = 0.50 / (100 * 10) = 0.005` (0.5% по ціні);
- `tp_rr ≈ 50 / 35 ≈ 1.4286`.

Це узгоджується з Aggregated OCO:
- `sl_pct` = `sl_pct_price`;
- `tp_rr = tp_pct_price / sl_pct_price`.

### 2.3 Денний ліміт / ліміт збитків

Вимоги:
- **Єдине джерело** конфігурації:
  - `config/domains/risk.yaml` → `daily_limits` (hard gate) + `budgets` (soft).
- Логіка:
  - `DailyRiskState.can_open()` — **жорсткий бар’єр**:
    - без equity → NO_EQUITY (block);
    - drawdown ≥ `max_drawdown_pct` → MAX_DRAWDOWN (block);
    - реалізований збиток ≥ `max_loss_usd` → MAX_REALIZED_LOSS (block).
  - `RiskManagement` публікує стан daily gate у `risk_parameters`.
  - `DecisionMaking` (або bridge) блокує нові трейди, якщо daily gate закритий, із нормалізованим кодом відмови.

### 2.4 Моніторинг позицій та ордерів

Вимоги:
- Для кожної позиції потрібні:
  - `equity`, `leverage_used`, `notional`, `sl_pct_price`, `tp_pct_price`;
  - цільові `roi_sl_pct`, `roi_tp_pct`.
- `ExposureBridge`/логування:
  - повинні включати ці поля у події/метрики, щоб перевірити, що модель ROI реально застосовується й відповідає конфігу.

---

## 3. План міграції

План розбитий на фази. Для кожного кроку вказано:
- **ADD** — додати новий код/поле;
- **CHANGE** — змінити існуючу логіку;
- **REMOVE** — видалити використання старого поля/шляху.

### 3.1 Фаза 1 — Конфіг: risk per trade і ROI як перший клас

#### Крок 1.1. Єдиний risk per trade (R_eq)

**Файл/місця:**
- `config/domains/sizing.yaml`
- `apps/reference/domains/decision_making/decision_making.py` (конструктор)

**Дії:**
1. **ADD/CONFIRM**: використовувати `defaults.max_risk_pct` у `config/domains/sizing.yaml` як canonical risk per trade:
   - `max_risk_pct: 1.0` → 1% від equity на трейд.
2. **CHANGE**: у `DecisionMaking.__init__`:
   - після зчитування `sizing_config = trading.decision.position_sizing`:
     - якщо `position_sizing.risk_fraction_q` **не заданий**:
       - зчитати `sizing.defaults.max_risk_pct` із `config_v2.domains["sizing"]`;
       - встановити `risk_fraction_q = max_risk_pct / 100.0`.

**Обґрунтування:**
- Єдине джерело `risk per trade` → легше змінювати профіль ризику, не змінюючи код DecisionMaking.

#### Крок 1.2. ROI‑таргети для Aggregated OCO

**Файл/місця:**
- `config/domains/execution.yaml` (блок `brackets.aggregated_oco`)
- `apps/reference/domains/execution_position/config.py` (`AggregatedOcoConfig`)
- `apps/reference/config/execution_position.py` (`_resolve_aggregated_oco`)

**Дії:**
1. **ADD**: у `config/domains/execution.yaml` → `brackets.aggregated_oco`:
   - `sl_roi_pct: 35.0`
   - `tp_roi_pct: 50.0`
   - `roi_basis: "margin"` (на майбутнє `"equity"`)
   - `leverage_source: "instrument_max"` або `"exposure_defaults"`.
2. **ADD**: у `AggregatedOcoConfig` нові поля:
   - `sl_roi_pct: float = Field(default=35.0, ge=0.0)`
   - `tp_roi_pct: float = Field(default=50.0, ge=0.0)`
   - `roi_basis: str = "margin"`
   - `leverage_source: str = "instrument_max"`.
3. **CHANGE**: у `_resolve_aggregated_oco(...)` (`apps/reference/config/execution_position.py`):
   - читати ці поля з `agg_node` (`aggregated_oco` вузол);
   - передавати в конструктор `AggregatedOcoConfig`.

**Обґрунтування:**
- Описуємо TP/SL через бізнес‑цілі (ROI), а не сирі BPS; однакові таргети будуть використані й у sizing, і в Aggregator OCO.

---

### 3.2 Фаза 2 — Плече та перетворення ROI → SL/TP у ціні

#### Крок 2.1. Хелпер для ефективного плеча

**Файл/місця:**
- Новий хелпер у `apps/reference/config/execution_position.py` або новому модулі `apps/reference/config/leverage.py`.
- Використання у DecisionMaking / ExecPosRuntimeV2 / Aggregator OCO.

**Дії:**
1. **ADD**: функція `resolve_effective_leverage(symbol: str, config: Any) -> float`:
   - порядок пріоритетів:
     1. `config.instruments.instruments.<symbol>.limits.max_leverage` (`config/instruments.yaml`);
     2. `config.domains.execution.exposure.leverage_defaults` (`config/domains/execution.yaml`);
     3. фолбек (наприклад 10.0) з WARNING у лог.

**Обґрунтування:**
- Плече знаходиться у конфігу, а не в коді DM чи ExecPos; це дозволяє змінювати режим (high/low leverage) через YAML.

#### Крок 2.2. Функція ROI → (sl_pct, tp_rr)

**Файл/місця:**
- `apps/reference/domains/execution_position/config.py`

**Дії:**
1. **ADD**: функція (псевдосигнатура):

```python
def compute_sl_tp_from_roi(
    ep_cfg: ExecutionPositionConfig,
    symbol: str,
    leverage: float,
) -> tuple[float, float]:
    ...
```

2. **Логіка:**
   - якщо `ep_cfg.aggregated_oco.sl_roi_pct`/`tp_roi_pct` задані:
     - `sl_pct_price = (sl_roi_pct / 100.0) / leverage`
     - `tp_pct_price = (tp_roi_pct / 100.0) / leverage`
     - `tp_rr = tp_pct_price / sl_pct_price`
     - повернути `(sl_pct_price, tp_rr)`.
   - інакше → fallback:
     - використовувати існуючі `sl_pct`/`tp_rr` (`AggregatedOcoConfig.sl_pct`, `tp_rr`) без перерахунку.

3. **CHANGE**: у місцях, де `sl_pct`/`tp_rr` використовуються напряму:
   - замінити на виклик `compute_sl_tp_from_roi(...)`.

**Обґрунтування:**
- Централізуємо трансформацію ROI+плече → TP/SL у ціні; код нижче (aggregator_oco, runtime) працює тільки з вже готовими `sl_pct`/`tp_rr`.

#### Крок 2.3. Узгодити `_calculate_position_size` з новою моделлю

**Файл/місця:**
- `apps/reference/domains/decision_making/decision_making.py:1664+`

**Дії:**
1. **CHANGE**: у `_calculate_position_size(...)`:
   - замість:
     - прямого доступу до `sl_bps_val = self._safe_config_get("trading", "execution", "brackets", "sl", "fixed_bps", default=50)`  
       (ПОТІМ видалити це використання),
   - використовувати:
     - `sl_pct_price` з нового хелпера `compute_sl_tp_from_roi(...)` (через `ExecutionPositionConfig` чи `config_v2.domains["execution"]`).
   - Формула стає:
     - `denom = sl_pct_price` (частка від ціни);
     - `q_notional = q_risk * equity / denom`.

2. **REMOVE/CHANGE**: використання прямого шляху `"trading", "execution", "brackets", "sl", "fixed_bps"` у DM.

**Обґрунтування:**
- Розмір позиції повинен бути узгоджений з реальною відстанню до SL, яку використовує execution, а не з окремим локальним параметром.

---

### 3.3 Фаза 3 — TP/SL: повна міграція на ROI +50% / −35%

#### Крок 3.1. Безпечна (no-op) міграція конфігу

**Файл/місця:**
- `config/domains/execution.yaml`

**Дії:**
1. **ADD**: поля `sl_roi_pct`/`tp_roi_pct` з такими значеннями, щоб:
   - після проходу через `compute_sl_tp_from_roi(...)` отримати **той самий** `sl_pct_price/tp_pct_price`, що й поточні `sl.fixed_bps`/`tp.fixed_bps` + поточне плече.
2. **CHANGE**: увімкнути використання ROI → `compute_sl_tp_from_roi(...)` в коді, але з ROI, підібраними під існуючу поведінку.

**Обґрунтування:**
- Спочатку переводимо механіку на новий шлях (ROI‑хелпер), не змінюючи фактичних рівнів SL/TP.

#### Крок 3.2. Встановити цільові ROI (+50% / −35%)

**Файл/місця:**
- `config/domains/execution.yaml` → `brackets.aggregated_oco`

**Дії:**
1. **CHANGE**: задати:
   - `sl_roi_pct: 35.0`
   - `tp_roi_pct: 50.0`
2. **Опціонально**: скоригувати `max_risk_pct`/`risk_fraction_q`, щоб добова просадка при серії збиткових трейдів відповідала профілю ризику.
3. **ADD**: тести:
   - `tests/domains/test_decision_making_*`:
     - перевірити, що для заданих `equity`, `L`, ROI система видає очікуваний розмір позиції;
   - `tests/domains/execution_position/shadow_execpos/test_oco_scenarios_v2_full.py`:
     - перевірити, що Aggregator OCO формує SL/TP на відстанях, які відповідають ROI.

**Обґрунтування:**
- Після того як механіка ROI перевірена, можна змінити самі значення ROI, не торкаючись коду.

---

### 3.4 Фаза 4 — Денний ліміт та ліміт збитків

#### Крок 4.1. Вирівняти RiskManagement із DailyRiskState і risk.yaml

**Файл/місця:**
- `apps/reference/domains/risk_management/risk_management.py`

**Дії:**
1. **CHANGE**: у `_calculate_risk_parameters(...)`:
   - явно викликати `self.daily_state.can_open()` (якщо ще не викликається);
   - включити в `risk_parameters`:
     - `daily_gate_status: "OPEN" | "BLOCKED"`
     - `daily_gate_detail` (NO_EQUITY, MAX_DRAWDOWN, MAX_REALIZED_LOSS)
     - `max_drawdown_pct`, `max_realized_loss_usd` з `self.daily_state.cfg`.
2. **CHANGE**: у `on_portfolio_state_updated(...)`:
   - вирішити, чи `equity` має бути:
     - `equity_free_usdt` (рекомендовано для узгодження з sizing та DailyRiskState), і використовувати його для daily drawdown;
   - синхронізувати це з тим, як `DailyRiskState` читає `equity_free_usdt`.

**Обґрунтування:**
- Весь щоденний ризик повинен ґрунтуватися на єдиному джерелі (risk.yaml + DailyRiskState), а не на декількох різних логіках.

#### Крок 4.2. Підключити DecisionMaking до денного бар’єра

**Файл/місця:**
- `apps/reference/domains/decision_making/decision_making.py`

**Дії:**
1. **ADD/CHANGE**: у `on_risk(...)` (обробка EVT:RISK_ASSESSMENT_COMPLETED):
   - зчитувати `risk_parameters["daily_gate_status"]`;
   - зберігати цей статус у `self.symbol_states[symbol]["daily_gate_status"]`.
2. **CHANGE**: у `_make_decision_for_symbol(...)`:
   - перед `_calculate_position_size(...)` перевіряти:
     - якщо `daily_gate_status != "OPEN"`:
       - не будувати TRADE_INTENT;
       - логувати warning та нормалізований reject reason (наприклад, `NRR-DAILY-LOSS-LIMIT`).
   - для додаткового soft‑контролю:
     - використовувати `config/domains/risk.yaml: budgets.max_daily_loss_pct` як додатковий поріг для алертів, але не як другий жорсткий бар’єр.

**Обґрунтування:**
- Денний бар’єр повинен реально блокувати нові трейди; DM — єдиний домен, який генерує TRADE_INTENT.

---

### 3.5 Фаза 5 — Моніторинг позицій/ордерів під нову модель

#### Крок 5.1. ROI та TP/SL у ExposureBridge

**Файл/місця:**
- `apps/reference/domains/execution_position/shadow_execpos/exposure_bridge.py`
- `apps/reference/domains/execution_position/shadow_execpos/runtime.py`

**Дії:**
1. **CHANGE/ADD**: у `ExposureBridge.emit_exposure_update(position_state)`:
   - додати в payload:
     - `leverage_used` (якщо є змога отримати),
     - `target_sl_price`, `target_tp_price`,
     - `roi_sl_pct`, `roi_tp_pct`.
2. **ADD**: у `ExecPosRuntimeV2`:
   - зберігати ці значення в `PositionState` або в окремій структурі (`_bracket_cfg_by_symbol`);
   - передавати їх у `position_state`, який потім передається у `ExposureBridge`.

**Обґрунтування:**
- Це дає прозору діагностику — можна по логах перевірити, що TP/SL і ROI відповідають конфігу і розрахункам.

#### Крок 5.2. OrderGuardian як метадані для OCO‑сетів

**Файл/місця:**
- `apps/reference/services/order_guardian.py`
- `apps/reference/domains/execution_position/shadow_execpos/runtime.py` (`_apply_bracket_plan`)

**Дії (на майбутнє):**
1. **ADD**: після застосування bracket‑плану в `_apply_bracket_plan(...)`:
   - при успішному розміщенні SL/TP:
     - викликати `guardian.register_bracket_set(...)` з `sl_order_id`, `tp_order_id`;
   - при повному закритті позиції:
     - викликати `guardian.clear_bracket_set_for_position(...)`.
2. **ADD**: опис цього контракту в `docs/EXEC_POS_BRACKETS_ANALYSIS.md` як “metadata‑only Guardian”.

**Обґрунтування:**
- Guardian стає єдиною центральною точкою для моніторингу OCO‑сетів, без дублювання логіки у різних компонентах.

---

## 4. Тестування та захист від регресій

### 4.1 Тести для sizing (risk % + ROI)

**Файли:**
- `tests/domains/test_decision_making_equity_validation.py`
- `tests/domains/test_sizing_matrix.py`

**Дії:**
- Додати сценарії:
  - при заданих `equity`, `max_risk_pct`, `sl_roi_pct`, `tp_roi_pct`, `L`:
    - очікуваний `qty` (або notional) відповідає `R_eq * equity / sl_pct_price`.
  - збільшення плеча `L`:
    - **не змінює** risk per trade в % від equity;
    - змінює лише `sl_pct_price` (менший рух ціни → той самий грошовий ризик).

### 4.2 Тести для денних лімітів

**Файл:**
- новий або існуючий `tests/domains/risk_management/test_daily_gate.py`

**Дії:**
- Кейс `NO_EQUITY`: без коректних даних equity нові позиції блокуються.
- Кейс `MAX_DRAWDOWN`: при просіданні > `max_drawdown_pct` `can_open()` → False.
- Кейс `MAX_REALIZED_LOSS`: при реалізованому збитку > `max_loss_usd` `can_open()` → False.
- Тести для інтеграції з `DecisionMaking`:
  - при закритому daily gate DM не генерує TRADE_INTENT.

---

## 5. Резюме змін

**Конфіг:**
- **ADD** `sl_roi_pct`/`tp_roi_pct`/`roi_basis`/`leverage_source` до `config/domains/execution.yaml` (`brackets.aggregated_oco`).
- **USE** `config/domains/sizing.yaml: defaults.max_risk_pct` як canonical risk per trade.

**Моделі & резолвери:**
- **ADD** ROI‑поля в `AggregatedOcoConfig` (`apps/reference/domains/execution_position/config.py`).
- **CHANGE** `_resolve_aggregated_oco` (`apps/reference/config/execution_position.py`) для читання ROI‑полів.
- **ADD** `resolve_effective_leverage(...)` + `compute_sl_tp_from_roi(...)`.

**Sizing / DecisionMaking:**
- **CHANGE** `_calculate_position_size(...)`:
  - використовувати `sl_pct_price` із ROI+L хелпера;
  - більше не читати `brackets.sl.fixed_bps` напряму.
- **CHANGE** зв’язати `risk_fraction_q` із `max_risk_pct`.

**TP/SL:**
- **CHANGE** всі використання `aggregated_oco.sl_pct`/`tp_rr` так, щоб вони проходили через `compute_sl_tp_from_roi(...)`.

**Денні ліміти:**
- **CHANGE** `_calculate_risk_parameters(...)` в `RiskManagement` для повної інтеграції `DailyRiskState`.
- **CHANGE** `DecisionMaking` (або bridge) для блокування нових трейдів, коли `can_open()` повертає False.

**Моніторинг:**
- **ADD** ROI/TP/SL‑поля в події `ExposureBridge`.
- **ADD** (пізніше) інтеграцію `OrderGuardian` з `_apply_bracket_plan(...)`.

Цей план можна реалізовувати по фазах: спочатку Фаза 1–2 (no‑op міграція з ROI‑хелперами), потім змінити самі значення ROI (Фаза 3) і вже після цього посилювати денні ліміти й моніторинг (Фази 4–5).
