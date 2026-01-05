# Логика разворота позиции (flip) в Phenix/Aurora

Цель: описать, где и как система выполняет разворот (LONG→SHORT / SHORT→LONG), то есть **строгий контракт**: сначала закрыть текущую позицию (reduce-only), затем отложить и повторить попытку открытия в противоположную сторону только после подтверждения состояния `FLAT`.

## Термины и сообщения

- **Flip / разворот**: пришёл сигнал открыть сторону, противоположную текущей позиции по символу.
- **reduce-only close**: закрытие позиции рыночным reduce-only ордером (не может увеличить позицию).
- **INTENT_DEFERRED v1**: событие, которое откладывает повтор исходного события (или сигнала) через `RetryScheduler`.

Ключевые сообщения (событийная архитектура):

- `EVT:FEATURES_CALCULATED` / `EVT:STRATEGY_SIGNAL_PRODUCED` — вход в `DecisionMaking`.
- `EVT:TRADE_INTENT_PROPOSED` — предложение открыть/закрыть (intent).
- `CMD:OPEN` / `CMD:CLOSE` — команды на домен `execution_position`.
- `DEC:OPEN` / `DEC:CLOSE` — решения внутри `execution_position`.
- `EVT:INTENT_DEFERRED` — отложенная попытка (QoS/flip/fail-closed).

## Где реализован flip

### 1) Центр оркестрации: `DecisionMaking._handle_flip_orchestration`

Реализация D3 «Flip Orchestration» находится в [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3689-L3833).

Опорные хелперы:

- Чтение позиции из `latest_portfolio` (SSOT кэша) — [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3275-L3304)
- Определение «flip» (противоположная сторона) — [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3305-L3320)
- Эмиссия reduce-only CLOSE intent — [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3321-L3369)
- Эмиссия `EVT:INTENT_DEFERRED` (v1 schema) — [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3451-L3487)

### 2) Две точки входа в flip-гейт

Flip проверяется **до** `EVT:TRADE_INTENT_PROPOSED` (OPEN) и может:
1) разрешить OPEN, 2) заблокировать, 3) инициировать flip (закрыть и deferred).

Точка входа A (strategy signal gateway): [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L585-L707)

- Здесь `DecisionMaking` обрабатывает `EVT:STRATEGY_SIGNAL_PRODUCED` и вызывает `_handle_flip_orchestration` как «GATE 2: FLIP GATE».

Точка входа B (aurora decision): [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2920-L2996)

- Здесь flip-гейт вызывается после sizing/exposure precheck и перед `_propose_trade_intent(...)`.

## Контракт разворота (строгая последовательность)

Ниже — реальная последовательность, когда есть активный LONG, а система хочет открыть SHORT (симметрично для SHORT→LONG).

### Шаг 1 — определить состояние позиции по символу

`DecisionMaking` берёт позицию из `self.latest_portfolio` и приводит к `FLAT/LONG/SHORT/UNKNOWN`: [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3275-L3304).

Fail-closed: если портфель отсутствует/битый → `UNKNOWN`.

### Шаг 2 — классификация запроса

В `_handle_flip_orchestration`:

- Если `UNKNOWN` → блок/дефер (`NRR-PORTFOLIO-UNKNOWN`) [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3711-L3722)
- Если `FLAT` → OPEN разрешён (возврат `None`) [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3724-L3727)
- Если позиция есть:
  - same-side → anti-pyramiding (или разрешить при `position_mode=DYNAMIC`) [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3734-L3761)
  - opposite-side → flip: CLOSE + DEFER [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3763-L3833)

### Шаг 3 — эмиссия reduce-only CLOSE intent

При flip `DecisionMaking` эмитит reduce-only закрытие через `_emit_reduce_only_close(...)`: [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3321-L3369)

Ключевые детали:

- Сторона CLOSE выбирается противоположной текущей позиции (`SELL` для LONG, `BUY` для SHORT).
- Кол-во берётся из портфеля (abs).
- Закрытие оформляется как `EVT:TRADE_INTENT_PROPOSED` с `reduce_only=True` (через `_propose_trade_intent`).

### Шаг 4 — defer открытия (OPEN) до подтверждения FLAT

Сразу после эмиссии CLOSE система **не открывает** противоположную позицию. Вместо этого:

1) Вычисляет `next_allowed_ts` как `now + positions_stale_ttl_sec` (SSOT): [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3775-L3783)
2) Эмитит `EVT:INTENT_DEFERRED` с `reason=FLIP_CLOSE_PENDING` и `original_event` (что именно переэмитить): [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3779-L3833)
3) Возвращает `FLIP_CLOSE_PENDING`, то есть текущий OPEN считается «отложенным».

Параметр задержки берётся из SSOT:

- `domains.position_tracking.positions_stale_ttl_sec`: [config/aurora/domains.yaml](config/aurora/domains.yaml#L159)

## Как CLOSE реально исполняется (execution_position)

### 1) Bridge: reduce-only intent → CMD:CLOSE

В `AuroraBridge` reduce-only intents **обходят QoS и gate свежести портфеля** и сразу переводятся в `CMD:CLOSE`:

- Проверка `reduce_only` и вызов `_dispatch_close`: [apps/reference/main.py](apps/reference/main.py#L373-L398)
- Конвертация в `CMD:CLOSE` (payload: `symbol`, `reason`, `idempotent_key`, `retry_key`) и передача в `execution_position`: [apps/reference/main.py](apps/reference/main.py#L805-L874)

### 2) ExecPosFSM: анти-гонка (closing flag) + DEC:CLOSE

На входе `CMD:CLOSE` система немедленно ставит флаг `_closing_position=True` в manage-flow, чтобы не ставить TP/SL в момент закрытия: [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L1138-L1151).

`CloseFlowFSM` на `CMD:CLOSE` всегда эмитит `DEC:CLOSE(reduce_only=true)`: [apps/reference/domains/execution_position/fsm_close.py](apps/reference/domains/execution_position/fsm_close.py#L72-L176).

### 3) ExecPosFSM: исполнение DEC:CLOSE

`ExecPosFSM._execute_decision` для `DEC:CLOSE` делает:

- повторно ставит closing-flag,
- отменяет отслеживаемые bracket-ордера,
- вычисляет текущую позицию через adapter,
- ставит рыночный reduce-only ордер закрытия `place_market_reduce_only`,
- запускает reconcile открытых ордеров (STOP/TP/LIMIT с `reduceOnly=true` или `closePosition=true`).

См. [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L1260-L1446).

### 4) OrderGuardian: cleanup/reconcile orphaned brackets

После закрытия, отдельный слой «подчищает» сиротские TP/SL при отсутствии позиции:

- `OrderGuardian.reconcile_symbol(...)`: [apps/reference/services/order_guardian.py](apps/reference/services/order_guardian.py#L1127-L1203)

## Надёжность: retry deferred intents

### `EVT:INTENT_DEFERRED` (v1) → RetryScheduler

В sync-режиме Bridge поддерживает v1-полезную нагрузку (`retry_key` + `original_event`) и регистрирует deferred в `RetryScheduler`: [apps/reference/main.py](apps/reference/main.py#L946-L1015).

`RetryScheduler.register_deferred(...)`:

- fail-closed без running event loop,
- хранит попытки/хэш payload,
- планирует retry с backoff/jitter,
- переэмитит `original_event` через `emit_compat`.

См. [apps/reference/retry_scheduler.py](apps/reference/retry_scheduler.py#L78-L200).

## Конфиги, влияющие на flip

- Delay перед повторной попыткой OPEN при flip (и в целом «ждём обновления портфеля»): [config/aurora/domains.yaml](config/aurora/domains.yaml#L159)
- Anti-race окно на стороне manage-flow (блок bracket placement вокруг закрытия):
  - SSOT значение: [config/aurora/trading.yaml](config/aurora/trading.yaml#L111)
  - fail-closed чтение и применение: [apps/reference/domains/execution_position/fsm_manage.py](apps/reference/domains/execution_position/fsm_manage.py#L124-L140) и [apps/reference/domains/execution_position/fsm_manage.py](apps/reference/domains/execution_position/fsm_manage.py#L529-L535)
- Политика same-side (anti-pyramiding vs pyramiding): `strategies.<strategy>.assets.<symbol>.position_mode`:
  - Пример `STRICT`: [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L90)
- Mean Reversion не обходит DM (иначе flip-гейт можно было бы «проскочить»): [config/aurora/strategies/mean_reversion.yaml](config/aurora/strategies/mean_reversion.yaml#L26)

## Итог в одной фразе

Разворот реализован как **двухфазная транзакция**: `DecisionMaking` обнаруживает flip → эмитит reduce-only CLOSE → эмитит `EVT:INTENT_DEFERRED(reason=FLIP_CLOSE_PENDING)` → `RetryScheduler` переэмитит исходное событие → при следующем решении OPEN разрешается только если `position_state == FLAT`.
