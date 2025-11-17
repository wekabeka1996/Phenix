# ExecPos поведенческий контракт

## Обзор машины состояний

ExecPosFSM объединяет три потоковых FSM: OpenFlowFSM, ManageFlowFSM и CloseFlowFSM (в соответствующих файлах `apps/reference/domains/execution_position/fsm_open.py`, `fsm_manage.py`, `fsm_close.py`). После очистки от legacy-артефактов каждая из них оперирует строго определёнными состояниями:

- **OpenFlowFSM**: `IDLE` → `PROCESSING` → (`DONE` / `ERROR`). По удачному CMD:OPEN переходит в `DONE`, при отказе валидации — в `ERROR`, а при отклонении только из-за cooldown — обратно в `IDLE`.
- **ManageFlowFSM**: `FLAT` → `BRACKETS_PENDING` → `BRACKETS_PLACED` → `TRACKING`, с вспомогательными `EMIT_DEC_ADJUST`, `WAIT_MODE` и `ERROR`. `EMIT_DEC_ADJUST` — транзитная подсостояние для генерации DEC, `WAIT_MODE` — пауза после экстренного стопа, `ERROR` ловит непредвиденные состояния.
- **CloseFlowFSM**: `FLAT` → `OPENED` → `CLOSE_COND` → `EMIT_DEC_CLOSE` → `DONE` / `ERROR`. В текущей реализации CloseFlowFSM вызывается только при CMD:CLOSE и никогда не запускает автоматические закрытия.

Каждый поток слушает свои события: OpenFlowFSM — только CMD:OPEN, ManageFlowFSM — EVT/UPD, CloseFlowFSM — CMD:CLOSE (с ExecPosFSM, который предварительно выставляет флаги закрытия и состояние `OPENED`). Результат принимается ExecPosFSM, логируется в WAL и передаётся адаптеру.

## Жизненный цикл позиции

### 1. Open Phase
- Событие: `CMD:OPEN` (от органов управления).
- OpenFlowFSM устанавливает `state = PROCESSING`, проверяет min_qty, min_notional, шаги, cooldown, idempotency и, при успехе, публикует `DEC:OPEN` с параметрами (side, qty, price, tif). После этого `state = DONE`, метрики увеличиваются, последний таймстемп обновляется. Любой guard-fail возвращает `ERR:OPEN` (`state = IDLE` на cooldown, `ERROR` в других случаях).

### 2. Fill Phase
- После `DEC:OPEN` ExecPosFSM получает `EVT:PARTIAL_FILL`, `EVT:FILL` или `EVT:TRADE_EXECUTED` и маршрутизирует их в ManageFlowFSM (CloseFlowFSM не используется для этих событий).
- В состоянии `FLAT` событие входного заполнения:
  * проверяет, не является ли оно выходным (`closePosition`, reduceOnly, тип order_type).
  * при ENTRY-позиции вызывает `_on_fill`, устанавливает `position_qty`, `position_entry_price`, `position_side`, сохраняет timestamp и переводит `state = BRACKETS_PENDING`.
  * при EXIT-событии ничего не запускает и остаётся в `FLAT`.

### 3. Brackets Phase
- В `BRACKETS_PENDING` вызывается `_place_brackets`:
  * `resolve_brackets_config` рассчитывает параметры SL/TP, они валидируются (TPSLValidationRules) и смещаются offset’ом.
  * Генерируются `DEC:PLACE_ORDER` для SL (`STOP_MARKET`) и TP (`LIMIT`) с `reduceOnly=True`.
  * ManageFlowFSM ожидает подтверждения `ORDER_UPDATED` — каждое обновление сохраняя `sl_order_id`/`tp_order_id`.
  * Когда оба ID известны, `state = BRACKETS_PLACED` и переходит на TRACKING.

### 4. TRACKING logic
- В `TRACKING` (`BRACKETS_PLACED` тоже отслеживается) запускается `_check_rules` на каждое событие `EVT/UPD`:
  1. **Quick Profit (`_check_quick_profit`)** — активна по конфигу, сначала проверяется через PriceService/пейлоад; при достижении USD-цели возвращает `_emit_close` → `DEC:CLOSE` reduce_only. Это единственный путь, по которому автоматически возникает `DEC:CLOSE`.
  2. **Emergency Take-over** — при `UPD:MARKET_DATA` и резком ухудшении цены (cfg.emergency.sl_bps) ManageFlowFSM генерирует `DEC:PLACE_ORDER` для экстренного SL, переводит `state = WAIT_MODE`, задаёт `_wait_mode_until_ts` (текущее барное время + `wait_mode_bars`). Пока TTL не истёк, `handle` игнорирует события и эмитит `EVT:MANAGE_SKIPPED`.
  3. **Обычные правила**: trailing stop (`_check_trailing_stop`), breakeven (старший предел времени) и time stop (3600 сек). При срабатывании возвращается `_emit_adjust` → `DEC:ADJUST` (см. ниже) и `state` ненадолго становится `EMIT_DEC_ADJUST`.
  4. **Быстрые выходы по OCO**: `TRADE_EXECUTED`/`ORDER_UPDATED` с `orderId` из SL/TP приводит к `_handle_bracket_fill`, отменяется противоположный брекет (`DEC:CANCEL_ORDER`), ID сбрасываются, позиция считается закрытой.

### 5. Manual Close Phase
- Когда приходит `CMD:CLOSE`, ExecPosFSM устанавливает `manage._closing_position = True`, берёт последние (`position_qty`, `_close_position_state`), если нужно — переводит `close_flow.state = OPENED` и вызывает `close_flow.handle`.
- CloseFlowFSM на `CMD:CLOSE` (при `state == OPENED`) идёт в `_emit_close`, формирует `DEC:CLOSE` с `reduce_only=True`, переводит `state` через `CLOSE_COND`, `EMIT_DEC_CLOSE` → `DONE`.
- Несмотря на наличие CloseFlowFSM, все остальные события продолжают обрабатываться ManageFlowFSM, а `DEC:CLOSE` всегда исполняется через ExecPosFSM/адаптер (требование безопасности: CloseFlowFSM не запускает авто-правила, только ручной `CMD:CLOSE`).

## Таблица переходов (state → event → transition → outcome)

| Поток | Текущее состояние | Событие | Следующее состояние | Исход |
| --- | --- | --- | --- | --- |
| OpenFlowFSM | `IDLE` | `CMD:OPEN` | `PROCESSING` → `DONE` | Guard-проверки → `DEC:OPEN`; при ошибке `ERR:OPEN` (`IDLE` на cooldown, иначе `ERROR`). |
| ManageFlowFSM | `FLAT` | `EVT:PARTIAL_FILL`/`FILL`/`TRADE_EXECUTED` (entry) | `BRACKETS_PENDING` | `_on_fill` заполняет позицию и вызывает `_place_brackets` → `DEC:PLACE_ORDER` (SL и TP). |
| ManageFlowFSM | `BRACKETS_PENDING` | `EVT:ORDER_UPDATED` (идентификаторы SL/TP) | `BRACKETS_PLACED` | Сохраняются `sl_order_id`/`tp_order_id`, переходит к `TRACKING`. |
| ManageFlowFSM | `TRACKING` / `BRACKETS_PLACED` | `UPD:MARKET_DATA` | `EMIT_DEC_ADJUST` (трансит) → `TRACKING` | `_check_quick_profit`/`_check_rules` → `_emit_adjust` или `_emit_close`. |
| ManageFlowFSM | `TRACKING` | `UPD:MARKET_DATA` при заданном adverse | `WAIT_MODE` | Эмит `DEC:PLACE_ORDER` экстренного стопа + `EVT:MANAGE_SKIPPED` до `_wait_mode_until_ts`. |
| ManageFlowFSM | `WAIT_MODE` | последующие EVT/UPD | остаётся `WAIT_MODE` (пока `now < _wait_mode_until_ts`) | `EVT:MANAGE_SKIPPED`; по истечении — `state = TRACKING`. |
| ManageFlowFSM | `TRACKING` / `BRACKETS_PLACED` | `EVT:ORDER_UPDATED`/`TRADE_EXECUTED` (SL или TP) | остаётся в `TRACKING` | `_handle_bracket_fill` отменяет второй брекет (`DEC:CANCEL_ORDER`), очищает ID. |
| CloseFlowFSM | `OPENED` (установлен ExecPosFSM перед CMD:CLOSE) | `CMD:CLOSE` | `CLOSE_COND` → `EMIT_DEC_CLOSE` → `DONE` | `_emit_close` → `DEC:CLOSE` (reduce_only) + состояние `position_active = False`. |

## Роли `_emit_adjust`, `_emit_close`, `wait_mode`

- `_emit_adjust(msg, why, details)` (ManageFlowFSM):
  * ставит `state = EMIT_DEC_ADJUST`, увеличивает `fsm_adjust_decisions_total`, формирует `DEC:ADJUST` с `details` (правило, триггерная цена/время), затем возвращает состояние в `TRACKING`.
  * Используется трёхступенчато: trailing stop (`_check_trailing_stop` с `_adjust_trailing_stop`), breakeven/time stop (`_check_rules`), и может служить контейнером для будущих пользовательских подстройок без отдельных состояний.

- `_emit_close(msg, why, details)` (ManageFlowFSM):
  * тоже переходное: `state = EMIT_DEC_ADJUST`, инкремент `fsm_adjust_decisions_total`, затем `state = TRACKING`.
  * Генерирует `DEC:CLOSE` с `reduce_only=True`, добавляет `symbol` из payload/состояния и передаёт `details` (например: `quick_profit`, `rule`, `pnl_usd`).
  * Это единственный путь, по которому появляется автоматический `DEC:CLOSE` (срабатывает при quick profit, emergency-sl, time stop и других правилах ManageFlow). CloseFlowFSM не используется для таких закрытий.

- `wait_mode`:
  * При `UPD:MARKET_DATA` с девиацией ≥ `cfg.emergency.sl_bps` ManageFlowFSM вычисляет `bar_index`, устанавливает `_wait_mode_until_ts = (bar_index + wait_mode_bars) * _bar_ms`, переводит `state = WAIT_MODE` и эмитит `DEC:PLACE_ORDER` для экстренного SL.
  * Пока `now < _wait_mode_until_ts`, `handle` возвращает `EVT:MANAGE_SKIPPED` и блокирует остальные правила — даже если приходят `UPD`/`EVT`, не вызывается `_check_rules`.
  * После окончания окна состояние сбрасывается обратно в `TRACKING`, что гарантирует, что экстренный стоп успел пройти и не блокирует новые решения.

## Исключённые / legacy состояния

Некоторые старые документы (`apps/reference/domains/execution_position/Readme/README.md`, `Readme/EVENTS.md` и `apps/reference/domains/execution_position/Readme/ANALYSIS_SUMMARY.md`) описывают артефактные ступени, которых нет в коде:

- **OpenFlowFSM**: прежние диаграммы говорили о `CANDIDATE`, `READY`, `EMIT_DEC_OPEN`. Сейчас реально используются только `IDLE`, `PROCESSING`, `DONE`, `ERROR`; ни `CANDIDATE`, ни `READY`, ни промежуточный `EMIT_DEC_OPEN` никуда не подписаны и не встречаются в исполнении.
- **ManageFlowFSM**: никакое состояние `ENTRY`, `ORDER_WAITING` или подобное не определено, вся логика сводится к `FLAT`, `BRACKETS_PENDING`, `BRACKETS_PLACED`, `TRACKING`, `EMIT_DEC_ADJUST`, `WAIT_MODE`, `ERROR`.
- **CloseFlowFSM**: хотя схемы помнят `OPENED → CLOSE_COND → EMIT_DEC_CLOSE → DONE`, реальное исполнение привязано только к ручному `CMD:CLOSE` — автоматического перехода из `OPENED` без команды нет (ExecPosFSM кормит CloseFlowFSM только при CMD:CLOSE), поэтому никакие дополнительные legacy-состояния не используются.

## Aggregated OCO v1 (ManageFlowFSM + OrderGuardian)

- **Single bracket per `(symbol, side)`** — у `aggregated_oco.enabled=true` ManageFlowFSM працює з агрегованою позицією, генерує рівні через `bracket_aggregator.py` і реєструє `BracketSetMeta` (через `OrderGuardian.register_bracket_set`). Усі взаємодії з OrderGuardian відбуваються в канонічних side (`LONG`/`SHORT`), тому сирі `BUY/SELL` конвертуються ще у FSM.
- **Scale-in / partial-close / flip** — `_recalc_aggregated_brackets` запускається для перших fill'ів, scale-in і partial-close за прапорцем `recalc_on_partial_close`; при flip попередній сет очищається, новий створюється на протилежний side.
- **Fail-closed cleanup** — OrderGuardian тримає `_bracket_sets[(symbol, side)]`, біжить `ensure_single_bracket_set_for_position`, застосовує TTL (`ttl_protect_new_bracket_ms`) і не видаляє останній SL, коли `position_amt>0` та `allow_unprotected_position=false`. Коли `position_amt` падає до нуля, Guardian одразу дропає BracketSetMeta, щоб не залишалось stale DR-сетів.
- **DR / restart** — ExecPos стартує `_rehydrate_aggregated_brackets_on_startup`, до cleanup викликає `guardian.rehydrate_bracket_set_for_position`; smoke-тест `tests/domains/execution_position/test_aggregated_oco_dr_restart.py` перевіряє, що SL зберігається.
- **Observability** — ManageFlowFSM емитить `AGG_OCO_BRACKET_SET_CHANGED` (why ≤ 80 символів), Guardian емитить `AGG_OCO_BRACKET_GUARD` (decision, why, has_sl_after). Повний контракт: `apps/reference/domains/execution_position/Readme/CONTRACT_aggregated_oco_v1.md`.

