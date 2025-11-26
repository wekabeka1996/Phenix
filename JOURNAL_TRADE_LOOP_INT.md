# JOURNAL_TRADE_LOOP_INT

Цей журнал фіксує всі інтеграційні тести й зміни, пов'язані з повним трейд-лупом: DecisionMaking (PortfolioSnapshot) → TRADE_INTENT_PROPOSED → AuroraBridge → CMD:OPEN → ExecPosRuntimeV2 → ExecutionService → BinanceExecutionAdapterV2 → SL/TP → watchdog/agg_oco.

## TASK INT-01.A — Journal + базовий інтеграційний harness (happy-path)

Дата/час: 2025-11-26 07:30:00 +03:00
Контекст: перший інтеграційний тест, який проганяє один лонг по SOLUSDT, ставить SL/TP і не генерує помилок/ALERT.

### 2025-11-26 08:15:00 +03:00 — Harness + happy-path тест

- Додано `tests/integration/test_trade_loop_execpos_v2.py`, який зшиває `AuroraBridge` → `V2RuntimeFacade` → `ExecPosRuntimeV2` з мінімальним `StubFSM` та мокованим Binance-адаптером (власний `place_order_v2/get_open_orders`).
- Сценарій: SOLUSDT BUY intent (MARKET) проходить через bridge, ExecPos відкриває позицію й після симульованого `TRADE_EXECUTED` ставить SL/TP (STOP_MARKET + TAKE_PROFIT_MARKET reduce_only).
- Команда: `pytest tests/integration/test_trade_loop_execpos_v2.py -q` → зелений прогін (1 тест ~6.5s).

## TASK INT-01.B — Short, negative paths & reverse-cleanup

Дата/час: 2025-11-26 09:10:00 +03:00
Контекст: розширення інтеграційного harness:
- short-сценарій (SELL) з коректними SL/TP;
- QoS/negative path, коли TRADE_INTENT блокується до ExecPos;
- reverse-cleanup, щоб не залишати orphan SL/TP/ордери після закриття.

### 2025-11-26 10:05:00 +03:00 — Реалізація INT-01.B

- `test_trade_loop_happy_path_short_with_brackets`: SOLUSDT SELL intent проходить через bridge → ExecPosRuntimeV2, після `TRADE_EXECUTED` фіксуємо один STOP_MARKET і один TAKE_PROFIT_MARKET (BUY reduce_only), їхні обсяги ≤ |position|.
- `test_trade_loop_qos_blocks_intent_before_execpos`: QoS cooldown виставлено вручну, `INTENT_DEFERRED (reason=QOS_COOLDOWN)` з FSM, adapter/place_order не викликається, ExecPosRuntimeV2 залишається idle.
- `test_trade_loop_reverse_cleanup_after_position_close`: після другого філа в протилежний бік всі SL/TP відмінені через adapter.cancel_order, mirror `_open_orders_by_symbol` очищений, позиція `qty≈0`.

### INT-01.B — Test snapshot

- `pytest tests/integration/test_trade_loop_execpos_v2.py -q` → 4 passed
- `pytest tests/domains/decision_making -q` → 4 passed
- `pytest tests/domains/execution_position -q` → 573 passed, 11 skipped, 2 xfailed (A/B replay)
- Перевірено: short-сценарій з валідними SL/TP, QoS path блокує intent до ExecPos при штучному cooldown, reverse-cleanup видаляє SL/TP після повного закриття SOLUSDT позиції.

## TASK INT-01.C — DM-driven equity gates integration

Дата/час: 2025-11-26 12:20:00 +03:00
Контекст: інтеграційні тести, де TRADE_INTENT генерується реальним DecisionMaking
на основі PortfolioSnapshot (S28-фікс), без ручних QoS-хаків.
Мета: перевірити, що:
- equity_free > 0 → TRADE_INTENT доходить до ExecPosRuntimeV2 та адаптера;
- equity_free <= 0 → DM блокує трейд, до ExecPosRuntimeV2 / BinanceExecutionAdapterV2 не доходить.

### INT-01.C0 — Timestamp & cooldown harness fixes

- IntegrationPortfolioProviderAdapter тепер примушує `positions_last_ts_ms` / `timestamp` дорівнювати `time.time()*1000`, тож AuroraBridge більше не маркує тестові snapshots як stale (особливо на Windows, де clock дрейфував від UTC).
- ExecPos gatekeeper бере `execution_position.cooldown_sec` з інтеграційного конфігу; тестовий нульовий cooldown дозволяє поспіль запускати DM-угоди без штучних QoS-хаків.
- `pytest tests/integration/test_trade_loop_execpos_v2.py -q` → 7 passed (оновлений набір INT-01.C).

### INT-01.C1 — ExecutionPosition regression (Binance helper restore)

- Додано легасі-аліас `BinanceExecutionAdapterV2 = BinanceExecutionAdapter` та позакласні helper-и `_create_success_feedback/_create_error_feedback/_build_signed_request`, щоб відновити контракт для ExecPosRuntimeV2 без змін існуючого тіла адаптера (additive-only підхід).
- `pytest tests/domains/execution_position -q` → 573 passed, 11 skipped, 2 xfailed (shadow A/B), ~12.7s. Базова regression зелена, можна рухатися до DM-driven сценаріїв INT-01.C2/INT-01.C3.

## TASK INT-01.C2 — DM-driven positive equity path

Дата/час: 2025-11-26 14:00:00 +03:00
Контекст:
- Мета — підключити реальний DecisionMaking + PortfolioProvider до інтеграційного трейд-лупу ExecPosRuntimeV2.
- TRADE_INTENT має генеруватися DecisionMaking на основі PortfolioSnapshot (equity_free>0), без ручної емісії intent.
- Перевіряємо повний шлях аж до SL/TP.

### 2025-11-26 18:45:00 +03:00 — DM-driven positive equity round-trip

- IntegrationPortfolioProviderAdapter тепер емить `EVT:PORTFOLIO_STATE_UPDATED` у `StubFSM`, тому DecisionMaking, AuroraBridge і ExecPosRuntimeV2 бачать один і той самий payload без ручних викликів `.on_*`.
- Додано async-хелпери `_wait_for_event/_wait_for_entry_order/_wait_for_brackets` і тест `test_dm_equity_positive_full_trade_loop_round_trip`, який проганяє `PortfolioSnapshot → DecisionMaking → TRADE_INTENT → AuroraBridge → CMD:OPEN → ExecPosRuntimeV2 → MockBinanceExecutionAdapter → TRADE_EXECUTED → SL/TP`.
- Тест після філа логінить контрольні події у `logs/aurora_events.jsonl`, тому з'явився артефакт для трасування INT-01.C2.
- Витяг з aurora_events.jsonl (скорочено, rid=1764171095.7296138):
	- `EVT:TRADE_INTENT_PROPOSED symbol=SOLUSDT side=buy quantity=1.04 reasons=['pos_size_usd=125.3120000, sizing=slbps q=0.02 sl_bps=75.0 m_regime=1.0 m_vol=1.0 kappa=1.0']`
	- `CMD:OPEN symbol=SOLUSDT side=BUY order_type=MARKET quantity=1.04 client_order_id=cid_order_1`
	- `BRACKETS_PLANNED symbol=SOLUSDT orders=2 sl_qty=1.04 tp_qty=1.04`

### INT-01.C2 — Test snapshot

- `pytest tests/integration/test_trade_loop_execpos_v2.py -q` → 8 passed
- `pytest tests/domains/decision_making -q` → 4 passed
- `pytest tests/domains/execution_position -q` → 573 passed, 11 skipped, 2 xfailed (shadow replay harness)
- DM-driven позитивний сценарій підтверджує, що equity_free>0 запускає DecisionMaking, AuroraBridge успішно створює CMD:OPEN, ExecPosRuntimeV2 розміщує entry, а після TRADE_EXECUTED ставляться SL/TP reduce_only зі сумарним обсягом ≤ позиції.

## TASK INT-01.C3 — DM-driven negative equity gates (equity_free<=0)

Дата/час: 2025-11-26 20:30:00 +03:00
Контекст:
- Після INT-01.C2 маємо DM-driven позитивний трейд-луп (equity_free>0).
- Цей таск фокусується на інтеграційному підтвердженні equity-гейтів при equity_free<=0.
- Очікуємо: DecisionMaking блокує трейд, ExecPosRuntimeV2/adapter залишаються неактивними.

### 2025-11-26 21:05:00 +03:00 — Equity<=0 gating через DecisionMaking

- `tests/integration/test_trade_loop_execpos_v2.py`: додано `_push_portfolio_equity` + `_drive_signal_context`, а `_make_portfolio_snapshot` навчено конструювати payload з від'ємним equity через pydantic `construct`, щоб перевіряти S28-логіку без ручних моку.
- `test_dm_equity_zero_blocks_trade_before_execpos` тепер фіксує курсор по `StubFSM.emitted` і підтверджує відсутність `EVT:TRADE_INTENT_PROPOSED`/`CMD:OPEN`, порожні `adapter.entry_orders/bracket_orders`, а також логи DM `equity is zero or negative`.
- Новий `test_dm_equity_negative_blocks_trade_before_execpos` симулює equity_free=-15 USDT: DecisionMaking споживає snapshot → risk/features, але не емісить intent, тому AuroraBridge та ExecPosRuntimeV2 залишаються idle, а `logs/aurora_events.jsonl` не отримує нових записів для INT-01.C3 (ланцюг обірвано на equity gate).

### INT-01.C3 — Test snapshot

- `pytest tests/integration/test_trade_loop_execpos_v2.py -q` → 9 passed
- `pytest tests/domains/decision_making -q` → 4 passed
- `pytest tests/domains/execution_position -q` → 573 passed, 11 skipped, 2 xfailed (shadow replay harness)
- Висновки: при equity_free<=0 DecisionMaking блокує TRADE_INTENT на рівні FSM, AuroraBridge не емісить CMD:OPEN, ExecPosRuntimeV2 та BinanceExecutionAdapterV2 не розміщують ордери; S28-гейти підтверджено на інтеграційному рівні.
