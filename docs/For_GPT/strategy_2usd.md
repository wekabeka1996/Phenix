# Strategy 2USD (Snapshot)

**Цель документа:** описать существующую торговую логику, которая по коду реализует «быстрые» сделки ориентиром на ~+$2 прибыли за один тик/свечу. Ничего не предлагается изменить — фиксируем поведение, которое уже выполняется в `execution_position` и конфигурируемых правилах.

## Общий стиль торговли

- **Один актив в работе**: текущая система работает на уровне отдельного `symbol` — каждый `TRADE_INTENT_PROPOSED` переводится через `AuroraBridge._dispatch_open` (apps/reference/main.py:387‑467) в единственный `CMD:OPEN` для этого инструмента. В стратегии подразумевается, что одновременно держится одна позиция на выбранном активе.
- **Высокий левередж**: конфиг `trading.execution.exposure.leverage_defaults` устанавливает 125x (см. config/aurora/trading.yaml:233‑240). Это заложено в ExposureGuard/soft limits (apps/reference/domains/execution_position/exposure_guard.py) и прямо влияет на величину открытия позиции при поступлении `CMD:OPEN`.
- **Быстрые входы**: `CMD:OPEN` генерируется сразу в `AuroraBridge` после успешной проверки QoS и свежести портфеля (apps/reference/main.py:200‑326); при этом `Order details` берутся из `TRADE_INTENT_PROPOSED` и сразу оцениваются `OpenFlowFSM` (`fsm_open.py`), который минимизирует задержку, делая только guard-checks и возвращая `DEC:OPEN`.
- **Быстрые выходы через ManageFlow**: `ManageFlowFSM` (`fsm_manage.py`) живёт в состояниях `TRACKING` и `BRACKETS_PLACED`, отслеживая `EVT:TRADE_EXECUTED`, `EVT:PARTIAL_FILL`, `EVT:FILL`, `EVT:ORDER_UPDATED`, `UPD:MARKET_DATA`. Именно этот FSM инициирует быстрые выходы.
- **Роль SL/TP**: при открытии позиции `ManageFlow` в `BRACKETS_PENDING` вызывает `_place_brackets`, публикует `DEC:PLACE_ORDER` для SL (`STOP_MARKET`) и TP (`LIMIT`) с `reduceOnly=True`, и затем переходит в `BRACKETS_PLACED`. Эти ордера создают OCO-поведение и дают возможность закрыться без дополнительных команд (см. `_handle_bracket_fill`).

## Условия входа

1. `TRADE_INTENT_PROPOSED` приходит от DecisionMaking после агрегации фич, риска и exposure (репер по событиям: `EVT:FEATURES_CALCULATED`, `EVT:RISK_ASSESSMENT_COMPLETED`, `EVT:EXPOSURE_SUMMARY_UPDATED`).
2. `AuroraBridge` проверяет QoS (`_is_qos_allowed`) и свежесть портфеля (`_is_portfolio_fresh`); при блокировке публикуется `EVT:INTENT_DEFERRED` или `EVT:INTENT_DROPPED` и ожидание (apps/reference/main.py:219‑327).
3. При разрешении QoS → мост строит `CMD:OPEN` (`symbol`, `side`, `qty`, `price`, `price_ref`, `idempotent_key`) и сразу вызывает `execution_position.handle`.
4. `OpenFlowFSM` обрабатывает `CMD:OPEN` быстро: idempotency, qty/price guard, cooldown, exposure_guard резервирует нарионал (fsm.py:1462‑2699). При успешной проверке возвращает `DEC:OPEN` и `state=DONE`; иначе `ERR:OPEN`.
5. Вход осуществляется где-то около того же самого тик/свечи: никто не ждет дополнительных таймеров — `AuroraBridge` и `OpenFlow` ориентированы на минимальные проверки.

## Условия удержания

- **Brackets**: сразу после `EVT:TRADE_EXECUTED`/`FILL` позиция прокидывает `ManageFlow` в `BRACKETS_PENDING`, `_place_brackets` открывает SL/TP и переходит в `BRACKETS_PLACED`. Эти ордера `reduceOnly` и отслеживаются (слушать `ORDER_UPDATED` для `sl_order_id`/`tp_order_id`, затем `state = BRACKETS_PLACED`).
- **Tracking**: `state` переходит в `TRACKING`; пока SL и TP живы, `_check_rules` анализирует каждый `UPD:MARKET_DATA` и `EVT`. Это основа удержания.
- **Trailing**: `_check_trailing_stop` активируется (см. `trailing_cfg.activation_profit_atr_k`, `step_bps`); после активации `_adjust_trailing_stop` отменяет старый SL и создаёт новый, двигая стоп в сторону прибыли. Это помогает продлить позицию, если рынок идёт в сторону, но всё ещё способствует быстрой фиксации, когда появляется откат.
- **Breakeven/Time Stop**: `_check_rules` также проверяет `breakeven_after_sec` и статическое `3600s` time stop. При срабатывании оно возвращает `_emit_adjust` (DEC:ADJUST) с меткой `rule=breakeven`/`time_stop`, что может, в зависимости от реализации, переместить SL.
- **Quick Profit**: `_check_quick_profit` первое правило (при `quick_profit_priority == 'highest'`) — запрашивает `PriceService` (или пейлоад) и сравнивает `current_price` с `position_entry_price` в USD: `total_pnl_usd >= quick_profit_target_usd` (config `trading.execution.manage.quick_profit.target_usd`, default 2.0). Тогда `ManageFlow` вызывает `_emit_close` → `DEC:CLOSE` с `why=QUICK_PROFIT_HIT`. Это срабатывание само по себе обеспечивает выход как только цель ~2$ достигнута.
- **Wait Mode**: `_check_rules` в режиме `UPD:MARKET_DATA` вычисляет `adverse_bps` (eval `emergency_cfg.sl_bps`). Если цена движется против позиции и превышает `sl_bps`, система публикует экстренный `DEC:PLACE_ORDER` (emergency SL), переходит в `ManageState.WAIT_MODE`, устанавливает `_wait_mode_until_ts = (bar_index + wait_mode_bars) * _bar_ms`, и до истечения TTL игнорирует остальные правила, возвращая `EVT:MANAGE_SKIPPED`. Wait mode работает как пауза, чтобы дать рынку стабилизироваться; когда таймер заканчивается, `state` возвращается в `TRACKING`.

## Условия выхода

1. **Quick profit close** (`_check_quick_profit`) — если `total_pnl_usd >= target_usd` (примерно 2.0), `DEC:CLOSE` эмитится автоматически, выполняется через ExecPosFSM и адаптер.
2. **Brackets/TP/SL** — раскрытие `DEC:PLACE_ORDER` на SL/TP может закрыть позицию без дополнительных решений (ManageFlow подчищает OCO, отменяя второй ордер через `_handle_bracket_fill`).
3. **Emergency SL** — `wait_mode` вызывает дополнительный SL, который отменяет тп по OCO.
4. **Trailing adjustments** — при достижении активации trailing, логика `_adjust_trailing_stop` как правило, движет SL в прибыль и позволяет «захватить» прибыль, когда откат происходит.
5. **Time stop / breakeven** — `_emit_adjust` может подвинуть стоп выше/ниже, потенциально закрывая позицию по breakeven/time limit, если трейд длится дольше (по коду). В режиме 2USD это скорее страховка, чем основной выход.
6. **Manual `CMD:CLOSE`** — при необходимости человек может вызвать `CMD:CLOSE`, `CloseFlowFSM` только тогда генерирует `DEC:CLOSE` (fsm.py:1463‑1524) — но стратегия ориентирована на правила ManageFlow, поэтому ручной выход редок.

## Ограничения

- **Объём одной позиции** ограничен `OpenFlow` guard и exposure guard (`ExecPosFSM._check_exposure_fail_closed`, exposure_guard отказывает по `trading.exposure.*`). Если `exposure_guard.can_open` отказывает, `CMD:OPEN` прерывается с `ERR:OPEN` и why `exposure_fail_closed`.
- **Многосимвольная logics**: хотя конфиг содержит несколько символов, `AuroraBridge` и DecisionMaking ориентированы на один intent/символ за раз; текущая стратегия держит только одну позицию, другие intents откладываются через QoS.
- **Распределение команд**: `OpenFlow` не делает торговлю сама, а только передаёт `DEC:OPEN`. Также `ManageFlow` не манипулирует `CloseFlow`. Следовательно, быстрый выход возможен только через правила, перечисленные выше.

## Sensitivity к задержкам

- **PriceService / MarketData**: Quick profit и trailing используют `PriceService` (если доступен) и `UPD:MARKET_DATA`; задержки в доставке данных препятствуют срабатыванию `quick_profit` и `trailing`, либо сильно смещают момент выхода.
- **Wait mode + emergency SL**: `wait_mode` жёстко опирается на таймеры (бары `_bar_ms` и `_wait_mode_bars`); любые потерянные ticks могут удлинить `WAIT_MODE` и задержать повторный выход.
- **QoS / Portfolio freshness**: `AuroraBridge` жёстко требует свежего портфеля (`positions_stale_ttl_sec`), иначе намерение откладывается (`INTENT_DEFERRED`). Если состояние портфеля приходит с задержкой, это тормозит вход.
- **Exposure guard**: `ExecPosFSM` резервирует exposure до подтверждения позиционирования; если работа с портфелем тормозит, `exposure_guard.reserve` может удерживать лимиты, предотвращая новые `CMD:OPEN` на время пост‑филловых задержек.

## Итог

Это краткое описание текущей «2USD» логики: вход через один symbol/высокий левередж, быстрый выход через quick profit, трайл/брекеты/экстренные правила и wait_mode, без создания новых правил. Документ лишь описывает то, что уже реализовано в коде (`AuroraBridge`, `OpenFlowFSM`, `ManageFlowFSM`, `ExecPosFSM`, `ExposureGuard` и конфиг `trading.yaml`), а не предлагает что-то новое.
