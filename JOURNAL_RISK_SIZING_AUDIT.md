# JOURNAL — RISK-SIZING-EP-AUDIT-POSITION-ADDING-AND-SIZING

> Статус: READ-ONLY аудит (P1). Жодних змін у коді / конфигах / схемах — лише аналіз і документація.

---

## 1. Overview

- Проаналізовані домени:
  - `decision_making` — розрахунок розміру позиції (position sizing) та емісія `EVT:TRADE_INTENT_PROPOSED`.
  - `execution_position` — відкриття/менеджмент/закриття позицій, експозиційні обмеження, TP/SL, trailing, partial exits.
  - `risk_management` — портфельний gate по daily drawdown / risk_score.
  - `position_tracking` — джерело портфельного стану для exposure guard.
  - `apps/research/momentum_backtest + optuna_*` — бек-тести та Optuna-оптимізація.
- Основні висновки (high level):
  - Розмір **початкового ордера** рахується виключно в `DecisionMaking._calculate_position_size(...)` на основі equity, risk_fraction_q, SL_bps та liquidity капи; **поточна позиція на біржі не входить у формулу** (лише непрямо через exposure guard).
  - **Явної "доливочної" логіки (pyramiding / DCA / scale-in) в коді немає**. Додаткові маркет-ордери на один символ виникають, коли DecisionMaking кілька разів видає `TRADE_INTENT` по символу, а `execution_position` (через exposure guard + QoS) це дозволяє.
  - TP/SL:
    - Початкові значення рахуються в `ManageFlowFSM._calculate_bracket_prices(...)` із:
      - per-instrument `aurora_instruments.<SYMBOL>.exit.sl_pct` / `take_profit.*` (ETH/SOL),
      - або глобальних `trading.execution.manage.brackets.*`.
    - Динаміка після відкриття позиції обмежена:
      - **Trailing stop** тільки "затягує" SL в бік прибутку; не розширює ризик.
      - TP фіксовані (TP1/TP2), не пересуваються.
      - Є emergency-логіка, але вона не переміщує існуючий SL, а додає окремий STOP (потенційно без ефективного впливу).
  - Optuna/backtest:
    - Весь pipeline `apps/research/momentum_backtest` моделює **один вхід на трейд з фіксованим `position_size`**, **без доливок** та без динамічного пересування TP/SL (крім time-exit).

---

## 2. Code & Config Inventory

> Ключові місця, де рахується **розмір позиції**, відбувається **додавання** до позиції (як результат повторних входів), та де керуються **TP/SL**.

### 2.1 Position sizing — DecisionMaking & MeanReversion

| Path | Function / Class | Role | Ключові конфіги |
|------|------------------|------|-----------------|
| `apps/reference/domains/decision_making/decision_making.py:908` | `DecisionMaking.on_features` | Головний handler `EVT:FEATURES_CALCULATED`: формує контекст, рахує сигнал, визначає `side`, готує `sizing_meta` (Kelly, regime, volatility_state) і викликає `_calculate_position_size(...)`. | `trading.decision.*`, `domains.decision_making.*`, `trading.execution.*` |
| `apps/reference/domains/decision_making/decision_making.py:2057` | `_calculate_position_size(symbol, price, side, context)` | **Єдина реалізація runtime position sizing для TradeIntent**. Рахує кінцевий `qty` (у базовій валюті) та пояснювальний ланцюжок `why_sizing`. Не дивиться на `open positions`, тільки на equity + конфіг. | `trading.decision.position_sizing.{min_position_size_usd, liquidity_based_cap_usd, risk_fraction_q, liquidity_kappa, liquidity_kappa_mode}`, `trading.execution.brackets.sl.fixed_bps` (SL_bps), `trading.decision.kelly.*`, `domains.decision_making.position_sizing.*`, `trading.instruments.<SYMBOL>.step_size` |
| `apps/reference/domains/decision_making/decision_making.py:2238` | `_propose_trade_intent(...)` | Будує DTO `trade_intent` з `order.qty` та `price_ref`, додає `size.notional_cap_usd ≈ qty * price` і емісує `EVT:TRADE_INTENT_PROPOSED`. **Тут немає логіки доливок** — кожен intent незалежний. | Немає окремих конфігів, бере `qty` з `_calculate_position_size`. |
| `apps/reference/domains/decision_making/decision_making.py:1047` | `on_portfolio(...)` | Кешує `latest_portfolio` та `equity_free_usdt` для логів/diagnostics; **не змінює формулу sizing**, тільки забезпечує дані для risk-management та exposure-кешу. | Портфельні івенти з `position_tracking`, але не впливають прямо на sizing. |
| `apps/reference/domains/decision_making/decision_making.py:2365` | `update_exposure_cache(...)` | Оновлює `_exposure_cache` зі `EVT:EXPOSURE_SUMMARY_UPDATED` від `execution_position`. Використовується для попереднього exposure gate в `_precheck_exposure_cache(...)`. | Payload з `ExecPosFSM` → `ExposureGuard.get_exposure_summary()`. |
| `apps/reference/domains/decision_making/decision_making.py:2378` | `_precheck_exposure_cache(symbol, side, notional_usd)` | Soft gate **до** емісії TradeIntent: додає `notional_usd` до `current_exposure_usd` по символу та порівнює з `max_exposure_usd`. Якщо перевищено — блокування decision (`NRR-011`). | Очікує, що `_exposure_cache[symbol]` має `current_exposure_usd` та `max_exposure_usd`. Поточна реалізація `ExposureGuard.get_exposure_summary()` таких полів не дає → gate фактично працює як "allow all" (важливий нюанс). |
| `apps/reference/domains/decision_making/mean_reversion_handler.py:43` | `MeanReversionHandler` | Окремий трек B: Mean Reversion 1m. Генерує `EVT:TRADE_INTENT_PROPOSED` з фіксованим `position_size_usd` з MR-конфігу. | `config/aurora/trading.yaml: mean_reversion.assets.*.risk.position_size_usd` |
| `apps/reference/domains/decision_making/mean_reversion_handler.py:325` | `_get_position_size_usd()` | Повертає фіксований `Decimal(position_size_usd)` з MR-конфігу; **не залежить від equity / SL_bps / volatility**. | `config/aurora/trading.yaml: mean_reversion.assets.<SYMBOL>.risk.position_size_usd` |

#### Формула `_calculate_position_size(...)` (спрощено)

- Вхід:
  - `equity` з `context["portfolio"]["equity"]` (крос-портфельний equity, **не** free_margin, але далі експозиція рахується в `execution_position` вже по margin).
  - `q_risk = trading.decision.position_sizing.risk_fraction_q` (якщо None — fallback в "10% від equity").
  - `sl_bps`:
    - первинно: `trading.execution.brackets.sl.fixed_bps` (або legacy `stop_loss_bps`),
    - для Kelly (вище по коду) — береться пара TP/SL з `execution.manage.brackets` або `execution.brackets`.
  - `kappa_liq`:
    - або статична `trading.decision.position_sizing.liquidity_kappa`,
    - або, при `liquidity_kappa_mode == "dynamic"`, береться з features: `features.features.liquidity_kappa`.
  - `sizing_meta` з `on_features`:
    - `kelly_fraction` (з Kelly-конфігу + payoff ratio з TP/SL),
    - `regime_multiplier` (з конфігу regime sizing),
    - `volatility_state` (`HIGH_VOL` / `LOW_VOL` / `NORMAL`) → впливає на ефективний SL_bps.
- Кроки:
  - Якщо `q_risk` заданий:
    - `sl_bps_dec` = normalized SL в bps.
    - `denom = sl_bps_dec / 1e4` (або 0.005 як fallback).
    - Базовий notional: `q_notional = q_risk * equity / denom`.
    - Якщо `kelly_fraction` > 0 → `base_notional = min(q_notional, kelly_fraction * equity)`, інакше просто `q_notional`.
    - Якщо `regime_multiplier` > 0 → множиться на нього.
    - Далі **динамічна волатильність**:
      - `volatility_multiplier` = 1.4 (HIGH_VOL), 0.8 (LOW_VOL), 1.0 (NORMAL).
      - `adjusted_sl_bps = sl_bps_dec * volatility_multiplier`.
      - `adjusted_q_notional = q_risk * equity / (adjusted_sl_bps / 1e4)`.
      - Повторна Kelly-мінімізація з новим SL.
    - Після цього застосовується `kappa_liq` і **жорстка стеля** `liq_cap_usd`:
      - `final_pos_size_usd = min(adjusted_notional * kappa_liq, liquidity_based_cap_usd)`.
  - Якщо `q_risk` не заданий → Fallback: `final_pos_size_usd = min(liq_cap_usd, 0.1 * equity)` (10% від equity).
  - Якщо `final_pos_size_usd < min_position_size_usd` → reject (NRR з причиною).
  - `qty = final_pos_size_usd / price`, далі quantize до `step_size` з `trading.instruments.<SYMBOL>.step_size` з округленням вниз.

**Важливо для доливок:** `_calculate_position_size` **не дивиться на поточні відкриті позиції по символу**, тільки на equity та конфіг. Доливка до існуючої позиції — це окремий новий intent з таким самим алгоритмом sizing (обмежений лише exposure guard + QoS).

### 2.2 Execution Position — відкриття, TP/SL, trailing, emergency

| Path | Function / Class | Role | Ключові конфіги |
|------|------------------|------|-----------------|
| `apps/reference/domains/execution_position/fsm.py:102` | `ExecPosFSM` | Обгортка над трьома FSM (Open/Manage/Close) + ExposureGuard + OrderGuardian. Приймає `CMD:*` і `EVT:*`, маршрутизує в `OpenFlowFSM`, `ManageFlowFSM`, `CloseFlowFSM`. | `config/aurora/trading.yaml: execution.*`, `config/aurora/domains.yaml: execution_position.*` |
| `apps/reference/domains/execution_position/fsm_open.py:133` | `OpenFlowFSM.handle(msg)` | Приймає `CMD:OPEN` (з qty, symbol, side, price_ref), застосовує guard-и: `min_qty`, step_size, tick_size, `min_notional`, cooldown. Якщо все ок — емісує `DEC:OPEN` для ExecPosFSM. | `trading.instruments.<SYMBOL>.{min_qty, step_size, tick_size, min_notional}`, `domains.execution_position.fsm_open.idempotency_window_sec`, `trading.execution.cooldown_ms` |
| `apps/reference/domains/execution_position/fsm_manage.py:387` | `ManageFlowFSM.handle(msg)` | Обробляє `EVT:PARTIAL_FILL|FILL|TRADE_EXECUTED|ORDER_UPDATED|UPD:MARKET_DATA` для відкритих позицій, ставить/слідкує за TP/SL, trailing stop, max_hold. | `trading.execution.manage.brackets.*`, `trading.aurora_instruments.<SYMBOL>.exit.*`, `take_profit.*`, `trailing_stop.*` |
| `apps/reference/domains/execution_position/fsm_manage.py:781` | `_calculate_bracket_prices()` | Розрахунок початкових SL, TP1, TP2 для поточної позиції (на основі `position_entry_price` та `position_side`). Приоритезує `aurora_instruments.<SYMBOL>.exit.sl_pct` + `take_profit.*`, fallback — глобальні `manage.brackets.sl/tp.fixed_bps`. | `config/aurora/trading.yaml: aurora_instruments.<SYMBOL>.exit.sl_pct`, `...take_profit.{tp_low_ratio,tp_high_ratio,partial_exit_pct}`, `trading.execution.manage.brackets.{sl.fixed_bps,tp.fixed_bps,stop_loss_bps}` |
| `apps/reference/domains/execution_position/fsm_manage.py:880` | `_calculate_sl_from_bps(entry_price)` | Fallback SL по bps, якщо `sl_pct` немає. Використовує `manage.brackets.sl.fixed_bps` або legacy `stop_loss_bps`. | `trading.execution.manage.brackets.sl.fixed_bps`, `stop_loss_bps` |
| `apps/reference/domains/execution_position/fsm_manage.py:898` | `_calculate_tp_from_bps(entry_price)` | Fallback TP по bps, якщо `sl_pct` / TP ratios не задані. | `trading.execution.manage.brackets.tp.fixed_bps` |
| `apps/reference/domains/execution_position/fsm_manage.py:1023` | `_check_rules(msg)` | Основний manage-loop: emergency SL (margin-based), OCO-емуляція bracketів (`_handle_bracket_fill`), trailing stop (`_check_trailing_stop`), max_hold time (`_check_max_hold_time`). | `trading.execution.manage.emergency.*`, `aurora_instruments.<SYMBOL>.trailing_stop.*`, `aurora_instruments.<SYMBOL>.exit.max_hold_sec` |
| `apps/reference/domains/execution_position/fsm_manage.py:1107` | `_handle_bracket_fill(msg)` | OCO-логіка: коли SL/TP1/TP2/legacy TP заповнений — оновлює `position_qty`, відміняє відповідні протилежні ордери, обнуляє track-бук. TP1 реалізує partial exit (зменшує `position_qty` на `partial_exit_pct`). | `manage.brackets.oco_emulation`, `take_profit.partial_exit_pct` |
| `apps/reference/domains/execution_position/fsm_manage.py:328` | `_check_max_hold_time(...)` | Максимальний час утримання позиції: після `max_hold_sec` емісує `DEC:CLOSE_POSITION` (маркет, повна кількість). | `aurora_instruments.<SYMBOL>.exit.max_hold_sec` |
| `apps/reference/domains/execution_position/fsm_manage.py:1210` | `_check_trailing_stop(msg)` | Trailing stop: на UPD:MARKET_DATA, якщо увімкнено `trailing_stop.enabled`, SL пересувається за піковою ціною (High-water mark) на відстань `trail_pct` після активації `activation_pct`. SL тільки "затягується", не розширюється. | `aurora_instruments.<SYMBOL>.trailing_stop.{enabled,activation_pct,trail_pct,min_update_interval_sec}`, або legacy `config.trailing.*` |
| `apps/reference/domains/execution_position/fsm_manage.py:1294` | `_adjust_trailing_stop(...)` | Реалізує CANCEL старого SL + PLACE нового SL з новою ціною (opposite side, reduceOnly). | Ті ж конфіги, що для trailing. |
| `apps/reference/domains/execution_position/exposure_guard.py:72` | `class ExposureGuard` | Margin-based exposure guard. Визначає, чи можна відкривати нову позицію, базуючись на equity, margin, long/short side exposure, directional ratio, soft clipping. | `domains.execution_position.exposure_guard.*`, `trading.risk.soft_limits.*`, `trading.execution.exposure.leverage_defaults.*`, `trading.execution.fallback.*` |
| `apps/reference/domains/execution_position/exposure_guard.py:478` | `can_open(symbol, notional_usd, portfolio_state)` | Головний exposure gate перед CMD:OPEN → DEC:OPEN. Фейл-клоз при відсутності equity або stale/unknown positions; враховує margin, pending/postfill reserves, long/short розподіл. При перевищенні лімітів може повернути `shrink_notional`. | `domains.execution_position.exposure_guard.{max_equity_utilization_pct,max_portfolio_fraction,max_long_utilization_pct,max_short_utilization_pct,max_directional_ratio,max_concentration_pct, pending_ttl_sec,post_fill_ttl_sec,stale_ttl_sec}`, `trading.risk.soft_limits.*`, `trading.execution.exposure.leverage_defaults.*` |
| `apps/reference/domains/execution_position/fsm.py:2193` | `ExecPosFSM._check_exposure_fail_closed(msg)` | Обгортка над `ExposureGuard.can_open`: рахує `notional_usd = qty * price_ref` і вирішує, чи блокувати CMD:OPEN. Якщо `allowed=False` — емісує `ERR:OPEN` і **резервує exposure** попри блок. Якщо `allowed=True` — просто резервує exposure. **Наразі не використовує `shrink_notional` для реального зменшення qty.** | `ExposureGuard`, `_latest_portfolio_state` з `EVT:PORTFOLIO_STATE_UPDATED`. |

### 2.3 Position tracking & Risk management (портфельні обмеження)

| Path | Function / Class | Role | Ключові конфіги |
|------|------------------|------|-----------------|
| `apps/reference/domains/position_tracking/position_tracking.py:796` | `_calculate_open_positions_notional()` | Сумарний notional відкритих позицій (≈ Σ|qty|·entry_price). Використовується для метрик і downstream-логіки. | Використовує внутрішній `_positions`, leverage не враховує (це notional, не margin). |
| `apps/reference/domains/position_tracking/position_tracking.py:823` | `_calc_margin_used_usd(positions)` | Обчислює сумарний **margin** (notional/leverage) для відкритих позицій; якщо `positions` з API є, використовує їх; інакше fallback на `_positions` + `trading.execution.exposure.leverage_defaults`. | `trading.execution.exposure.leverage_defaults.{BTCUSDT,ETHUSDT,...,__default__}` |
| `apps/reference/domains/position_tracking/position_tracking.py:896` | `_calculate_margin_by_side(positions)` | Окремо рахує margin long/short для directional ratio (довгі vs короткі). | Ті ж leverage defaults. |
| `apps/reference/domains/risk_management/risk_management.py:260` | `_calculate_risk_parameters(features)` | Portfolio-level gate: daily drawdown (vs opening equity) + risk_score з OBI/TFI/volatility/absorption. Повертає `is_trading_allowed` та `risk_score`. Не змінює розмір позиції, але може повністю вимкнути трейдинг. | `config/aurora/trading.yaml: risk.*`, `domains.risk_management.risk_score_weights.*`, `domains.risk_management.trading_allowed_thresholds.max_risk_score`, `system.risk.max_daily_drawdown_limit` |

### 2.4 Backtest / Optuna engines

| Path | Function / Class | Role | Ключові параметри |
|------|------------------|------|-------------------|
| `apps/research/momentum_backtest/backtest_engine_v2.py:29` | `BacktestEngineV2` | 1s backtest engine з single position: `active_position` (long/short) + SL/TP/time exit. **Не дозволяє другу угоду поки попередня не закрита.** | `params.{sl_pct, sl_tp_ratio, max_holding_secs, position_size, commission, slippage, spread_half, funding_threshold_long, strategy_mode}` |
| `apps/research/momentum_backtest/backtest_engine_v2.py:126` | `run(debug=False, ...)` | Ітерується по барах, якщо `active_position` None і `signal==1` → відкриває **одну** позицію. Виходи: `_check_exit` (SL/TP), time-стоп. Кожен `Trade` — один вхід/вихід. **Немає доливок чи scale-in.** | Внутрішній `position_size` використовується як фіксований notional. |
| `apps/research/momentum_backtest/backtest_engine_multiscale.py:25` | `BacktestEngineMultiscale` | Multiscale backtester (5s features, 1s `golden` для виходів), також **один трейд за раз**: на кожен сигнал симулює `Trade` через `_simulate_trade(...)`, потім fast-forward індекс до моменту після exit. | `params.{sl_pct, sl_tp_ratio, max_holding_secs, position_size, commission, slippage, spread_half, funding_threshold_long}` |
| `apps/research/momentum_backtest/optuna_runner.py:69` | `objective(trial)` | Optuna-об'єктив для базового (1s) Sniper: викликає `run_walk_forward_for_params(..., BacktestEngineV2)`. Параметри пошуку **не включають position sizing чи pyramiding**, тільки weights/thresholds/SL/TP/time. | `build_search_space(...): params.position_size = 200.0 (fixed)` |
| `apps/research/momentum_backtest/optuna_runner_regime.py:176` | `objective(trial, symbol, year, month)` | Optuna-об'єктив для regime filters (5s Sniper). Використовує `BacktestEngineMultiscale`. Теж фіксований `position_size=200.0`. | `build_search_space(...): position_size=200.0` |
| `apps/research/momentum_backtest/run_optuna_high_leverage.py:71` | `objective_high_leverage(trial)` | High-leverage strategія з walk-forward (через `BacktestEngineV2`), але `position_size` все одно фіксований (200 USD notional) — leverage впливає лише на mapping ROI→price move, не на pyramiding. | `build_search_space_high_leverage(...): position_size=200.0, leverage (50–75) тільки для SL/TP в процентах ціни` |

---

## 3. Position Additions / Pyramiding Logic

> Мета: зрозуміти, звідки беруться 10–15 маркет-ордерів на одну біржову позицію, чи є явна логіка "доливок".

### 3.1 Де в коді *можуть* з’являтися додаткові ордери

1. **DecisionMaking → нові TradeIntents**
   - `on_features(...)` (`decision_making.py:908`) реагує на кожен `EVT:FEATURES_CALCULATED`.
   - Якщо сигнал проходить всі фільтри (signal threshold, behavior FSM, crowding, liquidity, risk_management, QoS, exposure_cache), викликається `_calculate_position_size(...)` → `_propose_trade_intent(...)` → `EVT:TRADE_INTENT_PROPOSED`.
   - **Рішення не враховує, чи є вже відкрита позиція по символу.**
     - Є лише:
       - QoS-обмеження:
         - `domains.decision_making.qos.symbol_cooldown_sec` (cooldown між intent-ами по символу).
         - `domains.decision_making.qos.max_intents_per_minute_per_symbol`.
       - Exposure precheck (_precheck_exposure_cache), який поки працює як "allow all" через форму summary.
   - В результаті, при активному alpha-сигналі, можливо отримати **серію TradeIntent-ів в одному напрямку по одному символу**, поки QoS + exposure guard їх не обмежать.

2. **ExecPosFSM → CMD:OPEN → DEC:OPEN → MARKET/STOP/TP**
   - Після того, як TradeIntent буде прийнято ExecutionManagement (наразі `execution_management.py` тільки логує, але в реальному пайплайні має форвардити в `execution_position`), `ExecPosFSM.handle(CMD:OPEN)` робить:
     1. `_check_exposure_fail_closed(...)`:
        - Рахує `notional_usd = qty * price_ref` з payload-а.
        - Викликає `ExposureGuard.can_open(symbol, notional_usd, portfolio_state)`.
        - Якщо `allowed=False` → емісія `ERR:OPEN` і резервування exposure (fail-closed).
        - Якщо `allowed=True` → резервування exposure і продовження.
        - **Критично:** якщо `can_open` повертає `{"allowed": True, "shrink_notional": X}`, ця інформація **не використовується** — qty не перераховується. Тобто фактичне "clip" не доходить до реальної заявки.
     2. `OpenFlowFSM.handle(CMD:OPEN)`:
        - Перевіряє `min_qty`, step_size, tick_size, `min_notional` (через `trading.instruments.<SYMBOL>` або дефолти).
        - Має `cooldown_sec` (з `trading.execution.cooldown_ms`), який відсікає CMD:OPEN, якщо минуло менше часу від останнього open.
        - Якщо все ок — повертає `DEC:OPEN`.
     3. `ExecPosFSM._execute_decision(DEC:OPEN)` → adapter → реальний ордер (MARKET/LIMIT/...).
   - **Немає механіки "max_additions_per_position" / "max_orders_per_symbol" у ExecutionPosition**. Обмеження — тільки:
     - QoS у DecisionMaking,
     - exposure guard `ExposureGuard.can_open(...)` (margin/side/directional limits),
     - `cooldown_sec` в OpenFlowFSM.

3. **ExposureGuard & PositionTracking — як враховується вже відкрита позиція**
   - `position_tracking`:
     - Вираховує `open_positions_margin_usd` та `positions_by_side.{long_margin,short_margin}` з `positionRisk` або fallback на внутрішній state з leverage-config.
   - `ExposureGuard.can_open(...)`:
     - бере `equity_free_usdt` і `open_positions_margin_usd` з `portfolio_state` (з `EVT:PORTFOLIO_STATE_UPDATED`),
     - рахує:
       - `reserve_margin = notional_usd / leverage`,
       - `total_margin_exposure = open_positions_margin_usd + pending_margin + postfill_margin`,
       - per-side margin (`long_margin`, `short_margin`) включно з pending/postfill,
       - `directional_ratio = max(long_margin, short_margin) / min(...)` при наявності обох боків.
     - Ліміти:
       - `margin_limit = equity_free_usdt * max_equity_utilization_pct`,
       - per-side `side_limit = equity_free_usdt * max_long_utilization_pct` / `max_short...`,
       - directional ratio ≤ `max_directional_ratio`,
       - max concentration per symbol (`max_concentration_pct`) через інші гілки коду (не детально тут).
   - Якщо новий ордер не порушує ліміти → **дозволяється**, незалежно від того, чи є по символу вже 1, 5 чи 10 ордерів — важливий лише **сукупний margin/notional**.

### 3.2 Висновки щодо "доливок" / pyramiding

- В коді **немає**:
  - параметрів `max_additions`, `scale_in_step`, `pyramid_levels`,
  - явних функцій типу `add_to_position`, `scale_in`, `reavg_position`.
- Те, що виглядає як **10–15 маркет-ордерів по одній позиції**, на рівні системи — це:
  - **серія незалежних входів** за однаковим напрямком та символом, коли:
    - DecisionMaking кілька разів підтверджує сигнал,
    - QoS (`symbol_cooldown_sec`, `max_intents_per_minute_per_symbol`) не блокують,
    - ExposureGuard дозволяє додатковий margin (не досягнуті `max_equity_utilization_pct`, side caps, directional ratio).
- Важливі обмеження:
  - `domains.execution_position.exposure_guard.max_equity_utilization_pct: 0.95` (domains.yaml) + `trading.execution.exposure.max_equity_utilization_pct` (trading.yaml для глобального профілю) — задають фактичну стелю по margin.
  - Per-side ліміти і directional ratio перешкоджають односторонньому "накачуванню" плеча.
  - Однак **немає прямого "max_orders_per_position"** — система дозволяє "розбивати" позицію на багато окремих entry-ордерів, поки сумарна експозиція в ліміті.

---

## 4. Dynamic TP/SL Logic

> Мета: де і як TP/SL **перераховуються після відкриття позиції**, чи можуть SL/TP рухатися таким чином, що ризик розширюється або позиція "вічно висить".

### 4.1 Початковий розрахунок TP/SL

1. **Per-instrument Aurora config (ETH/SOL)**
   - `config/aurora/trading.yaml`:
     - `aurora_instruments.ETHUSDT.exit.sl_pct: 0.019` (≈1.9% SL).
     - `aurora_instruments.ETHUSDT.take_profit.{tp_low_ratio,tp_high_ratio,partial_exit_pct}`:
       - TP1 = 0.4 × risk (0.4·sl_pct),
       - TP2 = 1.4 × risk,
       - partial_exit_pct = 0.7 (70% позиції закривається на TP1).
     - Аналогічно для `SOLUSDT` зі своїми SL/TP параметрами і trailing_stop.
   - `ManageFlowFSM._calculate_bracket_prices()`:
     - Якщо per-instrument `exit.sl_pct` заданий:
       - `sl_price = entry_price * (1 - sl_pct)` для BUY, `1 + sl_pct` для SELL (`_calculate_sl_from_pct`).
     - Якщо per-instrument `take_profit` заданий:
       - `risk_pct = sl_pct`,
       - `tp1_off = risk_pct * tp_low_ratio`, `tp2_off = risk_pct * tp_high_ratio`,
       - TP1 = entry ± `tp1_off`, TP2 = entry ± `tp2_off` (залежно від side).
     - Далі quantize до `tick_size`, потім застосовується `offset_bps` (див. нижче).

2. **Глобальний fallback — `execution.manage.brackets`**
   - `config/aurora/trading.yaml: trading.execution.manage.brackets`:
     - `sl.fixed_bps: 40`, `tp.fixed_bps: 80`.
     - Legacy: `stop_loss_bps: 40`, `take_profit_low_ratio`, `take_profit_high_ratio` (використовуються Kelly-логікою в DecisionMaking).
   - Якщо per-instrument `sl_pct` немає:
     - `_calculate_sl_from_bps(entry_price)`:
       - LONG: `entry_price * (1 - sl_bps/1e4)`.
       - SHORT: `entry_price * (1 + sl_bps/1e4)`.
   - Якщо пер-інструментального TP немає:
     - `_calculate_tp_from_bps(entry_price)`:
       - LONG: `entry_price * (1 + tp_bps/1e4)`.
       - SHORT: `entry_price * (1 - tp_bps/1e4)`.

3. **Safety offset (анти -2021)**
   - У `_calculate_bracket_prices()` після обчислення SL/TP1/TP2:
     - з `manage.brackets.offset_bps` (default 5) через `TPSLValidationRules.add_safety_offset(...)` розраховується зсув.
     - Для LONG:
       - SL зсувається **далі від entry**: `sl_price = sl_price - sl_offset` (тобто SL стає трохи ширшим).
       - TP1/TP2 зсуваються **ще далі від entry** (вище).
     - Для SHORT — дзеркально.
   - Потім ці ціни зберігаються в `self.sl_price`, `self.tp1_price`, `self.tp2_price`, і на їх основі створюються STOP/TAKE_PROFIT_MARKET ордери.

### 4.2 Динаміка після відкриття позиції

#### 4.2.1 Trailing stop

- Активується в `_check_rules(...)`, коли приходить `UPD:MARKET_DATA`:
  - Визначає `enabled, activation_pct, trail_pct, min_update_sec` через `_get_trailing_stop_params(self.symbol)`:
    - Спочатку per-instrument `aurora_instruments.<SYMBOL>.trailing_stop.*`.
    - Якщо немає — legacy `config.trailing` (для сумісності).
- `_check_trailing_stop(...)`:
  - Тримає `peak_price` (кожен new high для LONG / new low для SHORT).
  - Активація:
    - Якщо `current_price` ≥ `entry_price * (1 + activation_pct)` (LONG) або ≤ (SHORT) — `trailing_activated=True`.
  - Частота оновлень: не частіше, ніж `min_update_sec`.
  - Нова ціна SL:
    - `trail_pct_dec = Decimal(trail_pct)`.
    - LONG:
      - `new_sl_price = peak_price * (1 - trail_pct_dec)`.
      - **Оновлює SL тільки якщо `new_sl_price > self.sl_price`** → SL рухається ближче до поточної ціни, не віддаляючись від entry.
    - SHORT:
      - `new_sl_price = peak_price * (1 + trail_pct_dec)`.
      - Оновлення тільки якщо `new_sl_price < self.sl_price` → SL рухається "вниз" (тобто ближче до поточної ціни в смислі прибутку).
  - `_adjust_trailing_stop(...)`:
    - CANCEL старого SL (DEC:CANCEL_ORDER),
    - PLACE нового STOP_MARKET з новою ціною, side = протилежний.

**Висновок:** trailing stop **ніколи не розширює SL далі в зону збитку**, лише затягує його в бік профіту (protect profit).

#### 4.2.2 Emergency SL (margin-based)

- У `_check_rules(...)` на `UPD:MARKET_DATA`:
  - Якщо `manage.emergency.enable = true`:
    - Береться `emergency_sl_bps` (default 100).
    - Рахується `adverse_bps` від `position_entry_price`:
      - LONG: `(entry_price - current_price) / entry_price * 1e4`.
      - SHORT: `(current_price - entry_price) / entry_price * 1e4`.
    - Якщо `adverse_bps >= emergency_sl_bps`:
      - FSM переходить в `WAIT_MODE` на N барів (`_wait_mode_until_ts`).
      - Рахує "emergency SL" з тим самим `emergency_sl_bps` і **емітує новий STOP_MARKET** через `_emit_place_order(...)`:
        - side = `self.position_side` (той самий напрямок),
        - `reduceOnly=True`, без `closePosition`.
      - Це виглядає як **спроба окремого emergency SL**, але:
        - Базовий SL, виставлений раніше через `_calculate_bracket_prices`, **не пересувається**.
        - Через те, що side = `position_side`, а reduceOnly=True, на Binance такий STOP, ймовірно, не буде зменшувати позицію (це потенційно неефективний ордер).

**Висновок:** emergency-логіка **не розширює існуючий SL**; фактичний ризик задається первинними brackets + trailing. Наявний код emergency, скоріш за все, не впливає на реальний SL (це скоріше відкритий баг/edge case, а не активна поведінка).

#### 4.2.3 Partial exits (TP1/TP2) та OCO-емуляція

- `_handle_bracket_fill(...)`:
  - **SL filled**:
    - OCO: скасовує всі TP1/TP2 (якщо `manage.brackets.oco_emulation=True`).
    - Не змінює позицію безпосередньо (закриття відбувається через сам SL-ордер).
  - **TP1 filled**:
    - Якщо `position_qty` та `partial_exit_pct` задані:
      - `filled_qty = position_qty * partial_exit_pct`,
      - `position_qty` ← `position_qty - filled_qty`.
    - Якщо `tp2_order_id` немає (single-TP mode):
      - скасовує SL (OCO).
    - TODO-коментар у коді: "Consider adjusting SL to breakeven after TP1 (optional feature)" — **наразі не реалізовано**.
  - **TP2 filled**:
    - Cancel SL (OCO), `position_qty=0` → позиція повністю закрита.

**Висновок:**
- TP/SL **не пересуваються динамічно** після виставлення, окрім:
  - safety offset при первинному розрахунку,
  - trailing stop (тільки SL у бік профіту).
- Немає реалізованого "breakeven" чи "profit SL, що далі розширює TP".
- TP не рухається "вверх до безкінечності": він фіксований (TP1/TP2) до закриття/відміни.

### 4.3 Чи може SL розширювати збиток? Чи може TP робити "вічну" позицію?

- **SL:**
  - Початковий SL вже містить safety offset `offset_bps`, який робить його трохи ширшим за базове значення.
  - Trailing stop SL тільки затягує, не розширює.
  - Emergency-логіка не змінює існуючий SL (за поточною реалізацією).
  - В коді **немає логіки, яка б рухала SL ще далі від entry після відкриття позиції**.
- **TP:**
  - TP1/TP2 обчислюються один раз при постановці brackets.
  - Немає trailing TP чи динамічного збільшення TP.
  - Отже, **TP не може "від’їжджати" вдалину** — ризику "вічної" позиції через TP немає (інший ризик можливий через відсутність fillів або disabled brackets, але це окрема тема).

---

## 5. Optuna / Backtest Behavior re: Position Additions

> Мета: відповісти, чи Optuna-бектести моделювали **додавання до позиції** або працювали в режимі "один трейд = один вхід".

### 5.1 BacktestEngineV2 (1s) — Single Entry Only

- `BacktestEngineV2` (`apps/research/momentum_backtest/backtest_engine_v2.py:29`):
  - Має єдину змінну `active_position` (dict з `entry_time`, `entry_price`, `side`).
  - В `run()`:
    - Якщо `active_position` існує:
      - Перевіряє SL/TP через `_check_exit(...)` + time-stop,
      - При exit створює `Trade` (entry+exit) та звільняє `active_position`.
    - Якщо `active_position` None і `signal_arr[i] == 1`:
      - Відкриває **одну** позицію з `position_size` (USD notional), обчисленою один раз з параметра.
  - **Немає коду, який би дозволяв другий вхід, поки `active_position` не закрита.**
  - Position size:
    - `size` у кожному `Trade` = `params.position_size` (fixed, наприклад 200 USD).
    - Немає залежності від equity, SL_bps чи відкритих позицій.

### 5.2 BacktestEngineMultiscale (5s+1s) — Single Entry per Trade

- `BacktestEngineMultiscale` (`apps/research/momentum_backtest/backtest_engine_multiscale.py:25`):
  - Логіка:
    - Для кожного бара 5s з `signal==1` виконує `_simulate_trade(entry_time, entry_price, side="long")`.
    - Після отримання `Trade`:
      - "fast-forward" індекс `i` до **першого бара після `trade.exit_time`** через `np.searchsorted`.
    - Таким чином, навіть якщо `signals` часто =1, завжди **один трейд за раз**, без overlap та без доливок.
  - `position_size` також фіксований параметр.

### 5.3 Optuna Runners — що оптимізують

- `optuna_runner.py` (Sniper V2, 1s):
  - `build_search_space(...)` **не включає жодних параметрів sizing чи pyramiding**:
    - оптимізуються тільки weights для phi-фіч, thresholds, SL%, TP ratio, max_holding_secs, funding_threshold.
    - `position_size = 200.0` жорстко зафіксований.
  - `objective(...)` викликає `run_walk_forward_for_params(..., BacktestEngineV2)`:
    - Walk-forward просто складає trades/metrics із декількох OOS-вікон.
- `optuna_runner_sniper_v2.py` (локальний пошук):
  - Теж працює через `run_walk_forward_for_params(..., BacktestEngineV2)` з фіксованим `position_size`.
  - Додає обмеження на кількість трейдів (180–600), але **не змінює модель position sizing чи pyramiding**.
- `optuna_runner_regime.py` (regime filters, 5s):
  - Використовує `BacktestEngineMultiscale`.
  - Теж має `position_size = 200.0` фіксовано, без scale-in параметрів.
- `run_optuna_high_leverage.py`:
  - Оптимізує `leverage` і ROI (TP/SL у термінах ROI), але:
    - фактичний backtest все так само працює через `run_walk_forward_for_params(..., BacktestEngineV2)` з фіксованим `position_size`,
    - leverage впливає на **розмір руху ціни**, потрібний для досягнення цільової ROI, **а не на кількість доливок/розмір позиції**.

### 5.4 Однозначна відповідь

- **Optuna backtests: `single-entry only` (fixed position size, без additions).**
  - В усіх backtest engine-ах немає механіки scale-in/pyramiding.
  - Кожен трейд — один вхід, один вихід, постійний `size`.
  - Немає симуляції:
    - повторних входів у той самий трейд,
    - додавання обсягу при сприятливому русі,
    - step-based DCA.
- Живе ядро (DecisionMaking + ExecutionPosition) працює з:
  - **динамічним sizing на основі equity, SL_bps, volatility, Kelly, liquidity**, але
  - **дозволяє серії незалежних входів**, поки ExposureGuard + QoS їх не обмежують.

---

## 6. Open Questions / Notes

> Пункти, які потребують окремого архітектурного / операційного рішення.

1. **Soft clipping (`shrink_notional`) зараз не впливає на реальний qty.**
   - `ExposureGuard.can_open(...)` може повернути `"shrink_notional"`, але `ExecPosFSM._check_exposure_fail_closed(...)` її ігнорує.
   - Поточна поведінка: або повний allow, або повний reject, без фактичного "clip to fit".
   - TODO-рішення (поза цим аудитом): або використовувати `shrink_notional` для перерахунку `qty`, або вимкнути soft-clip і використовувати тільки hard reject.

2. **Exposure summary shape vs DecisionMaking._precheck_exposure_cache.**
   - `ExposureGuard.get_exposure_summary()` повертає агрегати (`reservations_usd`, `postfill_hold_margin_usd`, TTL-и), **без** per-symbol `current_exposure_usd` / `max_exposure_usd`.
   - `DecisionMaking._precheck_exposure_cache(...)` очікує структуру `self._exposure_cache[symbol]`, в якій є `current_exposure_usd` та `max_exposure_usd`.
   - Фактично це означає, що precheck зараз не робить реального gating по символу — лише логічний "allow all" (якщо кеш не порожній).

3. **Emergency stop у ManageFlowFSM.**
   - Використовує side = `position_side` + `reduceOnly=True` в `_emit_place_order(...)`.
   - Для Binance Futures такий STOP навряд чи буде зменшувати позицію (reduceOnly + той же side зазвичай не закриває).
   - Це не розширює ризик (бо базовий SL лишається), але означає, що emergency-логіка може бути "no-op".

4. **Відсутність явної "anti-pyramiding" логіки.**
   - Система не обмежує кількість entry-ордерів по символу/позиції (лише margin/side/directional caps).
   - Якщо потрібно "один трейд = один вхід", треба:
     - або додати в DecisionMaking перевірку `positions` із `latest_portfolio` (наприклад, не відкривати новий TradeIntent по символу, якщо вже є позиція в тому ж напрямку),
     - або в `execution_position` додати rule, що блокує CMD:OPEN, якщо позиція вже відкрита і перевищено `max_position_size_usd` (через домен `risk_management` чи окремий guard).

5. **Розрив між backtest та live-поведінкою.**
   - Backtests/Optuna:
     - single-entry, fixed `position_size`.
     - немає dynamic Kelly, немає dynamic SL_bps sizing, немає exposure guard (margin), немає pyramiding.
   - Live ядро:
     - dynamic sizing на основі `risk_fraction_q`, SL_bps, volatility, Kelly, liquidity.
     - margin-based exposure guard з leverage.
     - потенційно багато входів по одному символу.
   - Рішення: або **зробити backtest ближчим до live ядра** (моделювати dynamic sizing, exposure guard, multi-entry per symbol), або **навпаки "обрубити" live поведінку до моделі backtest** (single-entry, fixed size), залежно від стратегії.

6. **MeanReversion track B та Aurora Optuna ядро.**
   - MR-стратегія (DOGE/BTC/XRP) використовує **фіксований `position_size_usd`** з конфігу і ATR-based SL (Phase 2).
   - Основне Optuna-ядро (momentum Sniper) працює окремо через momentum_backtest.
   - При інтеграції обох стратегій важливо слідкувати за сумарними exposure caps (ExposureGuard + RiskManagement), але це вже out-of-scope для цього аудиту.

---

**Summary for quick reference**

- **Position sizing (live):** `DecisionMaking._calculate_position_size(...)` → dynamic, на основі equity, SL_bps, risk_fraction_q, Kelly, volatility, liquidity caps. Поточні позиції не враховуються явно (тільки через margin-based ExposureGuard).
- **Position additions:** немає explicit pyramiding; додаткові ордери — це повторні незалежні входи, поки не спрацюють QoS та `ExposureGuard.can_open(...)`.
- **Dynamic TP/SL:** початкові SL/TP з per-instrument `exit.sl_pct`/`take_profit.*` або `execution.manage.brackets`; trailing stop лише затягує SL; TP статичні; SL не розширюється після відкриття.
- **Optuna backtests:** **`single-entry only / additions disabled`** — фіксований `position_size`, одна позиція за раз, без scale-in / DCA.

