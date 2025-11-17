# FSM_EVENT_MAP.md
Эталонная карта finite-state machine (FSM) для `execution_position`.

======================================================================
1) ПЕРЕЧЕНЬ ВСЕХ СОСТОЯНИЙ FSM
======================================================================
- **OPENING** — инициализация ордера, проверка признаков и отправка `CMD:OPEN`.
- **OPENED** — подтверждение выставления ордера, ожидание `FILL` и фиксация состояния.
- **MANAGING** — мониторинг позиции, запуск exit intent и проверка риска до закрытия.
- **CLOSING** — управление закрывающим ордером, подтверждение `ACK` и ожидание `FILL`.
- **CLOSED** — позиция закрыта, система готова к следующему циклу.

======================================================================
2) ПОЛНЫЙ ПЕРЕЧЕНЬ ВСЕХ EVENT-TYPES
======================================================================
**Входные (input):**
- `EVT:FEATURES_CALCULATED`
- `EVT:DECISION_SIGNAL`
- `EVT:RISK_ASSESSMENT_COMPLETED`
- `CMD:OPEN`
- `ACK`
- `FILL`
- `EVT:TP_FILLED`
- `EVT:SL_FILLED`

**Выходные (output):**
- `EVT:POSITION_OPENED`
- `CMD:CLOSE`
- `EVT:CLOSED`

======================================================================
3) ТАБЛИЦА ПЕРЕХОДОВ FSM (ОСНОВНОЙ РАЗДЕЛ)
======================================================================
##### OPENING
| STATE   | INPUT EVENT | ACTIONS / OUTPUT EVENTS                | NEXT STATE |
|---------|-------------|----------------------------------------|------------|
| OPENING | CMD:OPEN    | отправить `CMD:OPEN` на биржу          | OPENING    |
| OPENING | ACK         | зафиксировать подтверждение            | OPENING    |
| OPENING | FILL        | `EVT:POSITION_OPENED`                  | OPENED     |

##### OPENED
| STATE  | INPUT EVENT | ACTIONS / OUTPUT EVENTS | NEXT STATE |
|--------|-------------|-------------------------|------------|
| OPENED | ACK         | фиксировать состояние   | OPENED     |
| OPENED | FILL        | переход к MANAGING      | MANAGING   |

##### MANAGING
| STATE    | INPUT EVENT                   | ACTIONS / OUTPUT EVENTS              | NEXT STATE         |
|----------|-------------------------------|--------------------------------------|--------------------|
| MANAGING  | EVT:FEATURES_CALCULATED       | обновить состояние позиции           | MANAGING           |
| MANAGING  | EVT:DECISION_SIGNAL           | выполнить проверку exit intent       | MANAGING / CLOSING  |
| MANAGING  | EVT:RISK_ASSESSMENT_COMPLETED | выполнить контроль risk veto         | MANAGING           |
| MANAGING  | EVT:TP_FILLED                 | инициировать `CMD:CLOSE` и переход  | CLOSING            |
| MANAGING  | EVT:SL_FILLED                 | инициировать `CMD:CLOSE` и переход  | CLOSING            |

##### CLOSING
| STATE   | INPUT EVENT | ACTIONS / OUTPUT EVENTS               | NEXT STATE |
|---------|-------------|---------------------------------------|------------|
| CLOSING | ACK         | подтверждение закрывающих ордеров    | CLOSING    |
| CLOSING | FILL        | `EVT:CLOSED`                          | CLOSED     |

##### CLOSED
| STATE   | INPUT EVENT           | ACTIONS / OUTPUT EVENTS      | NEXT STATE |
|---------|-----------------------|------------------------------|------------|
| CLOSED  | EVT:FEATURES_CALCULATED | готовность к новому циклу    | CLOSED     |
| CLOSED  | EVT:DECISION_SIGNAL     | старт нового OPENING         | OPENING    |

======================================================================
4) КОНТРАКТ ЦЕПОЧКИ СОБЫТИЙ (CANONICAL EVENT FLOW)
======================================================================
- TICK
- `EVT:FEATURES_CALCULATED`
- `EVT:DECISION_SIGNAL`
- INTENT_OPEN
- `EVT:RISK_ASSESSMENT_COMPLETED`
- `CMD:OPEN`
- `ACK`
- `FILL`
- FSM:OPENING → FSM:OPENED
- FSM:MANAGING
- `EVT:TP_FILLED` / `EVT:SL_FILLED`
- `CMD:CLOSE`
- FSM:CLOSING
- `EVT:CLOSED`
- FSM:CLOSED
- SUMMARY

======================================================================
5) EXECUTION_POSITION — Aggregated OCO v1 EVENT MAP
======================================================================

**Mode selection**
- `aggregated_oco.enabled = true` → aggregated branch (default).
- `aggregated_oco.enabled = false` → legacy per-entry OCO (**DEPRECATED, guarded by config**).

**Key EVT → DEC mappings (aggregated branch)**
| EVT / input                                  | FSM action                                                      | DEC / LOG output                                     |
|----------------------------------------------|----------------------------------------------------------------|------------------------------------------------------|
| `EVT:ENTRY_FILLED` (first fill)              | `_recalc_aggregated_brackets(reason="first_entry")`            | `DEC:AGG_OCO_RECALC(first_entry)` + `LOG:AGG_OCO_BRACKET_SET_CHANGED` |
| `EVT:SCALE_IN_FILLED`                        | `_recalc_aggregated_brackets(reason="scale_in")`               | `DEC:AGG_OCO_RECALC(scale_in)` + log event           |
| `EVT:PARTIAL_CLOSE_FILLED`                   | `_recalc_aggregated_brackets(reason="partial_close")` (guarded by config) | `DEC:AGG_OCO_RECALC(partial_close)`; when SL missing => `DEC:AGG_OCO_RECALC(partial_close_unprotected)` |
| `EVT:POSITION_CLOSED` or flip (side change)  | `_cleanup_aggregated_brackets()`                                | `DEC:AGG_OCO_CLEANUP(full_close)` + `LOG:AGG_OCO_BRACKET_SET_CHANGED(action="full_close")` |
| DR bootstrap (no EVT, startup hook)          | `_rehydrate_aggregated_brackets_on_startup()`                   | `LOG:AGG_OCO_BRACKET_SET_CHANGED(action="rehydrate")` before guardian cleanup |

**Guardian feedback events**
- `LOG:AGG_OCO_BRACKET_GUARD(decision="ttl_skip"|"cleanup_extras"|"fail_closed_guard")` emitted from OrderGuardian `ensure_single_bracket_set_for_position`.

**Invariants**
- Between any two EVT transitions, if `position_amt > 0` and `allow_unprotected_position = false`, aggregated branch guarantees at least one SL (via ManageFlow recalcs + Guardian fail-closed guard).
