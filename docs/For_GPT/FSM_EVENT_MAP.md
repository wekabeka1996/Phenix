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
**Входные (input) - Listeners in `fsm.py`:**
- `EVT:PORTFOLIO_STATE_UPDATED` (Portfolio/Exposure updates)
- `EVT:ORDER_ACK` (Order acknowledgement)
- `EVT:TRADE_EXECUTED` (Unified fill event)
- `EVT:ORDER_FILL` (Legacy fill event)
- `EVT:FILL` (Legacy fill event)
- `EVT:ORDER_STATE_CHANGED` (Watchdog/Adapter updates)
- `EVT:ORDER_CANCELLED`
- `EVT:ORDER_REJECTED`
- `EVT:SYMBOL_TIDY`
- `EVT:ACCOUNT_UPDATE_RECEIVED`
- `CMD:OPEN`
- `CMD:CLOSE`

**Входные (input) - Handled in `fsm_manage.py` (via router):**
- `EVT:PARTIAL_FILL`
- `EVT:ORDER_UPDATED`
- `UPD:POSITION_STATE`

**Выходные (output) - Emitted by FSM:**
- `DEC:PLACE_ORDER`
- `DEC:CANCEL_ORDER`
- `DEC:CLOSE`
- `DEC:OPEN` (via Adapter)
- `EVT:EXPOSURE_SUMMARY_UPDATED`
- `EVT:PENDING_EXPOSURE_EXPIRED`
- `ERR:OPEN`
- `ERR:FATAL_CONFIG_MISMATCH`

**Logical/Derived Events (Internal Logic):**
- `EVT:TP_FILLED` (Derived from `EVT:TRADE_EXECUTED` / `EVT:ORDER_UPDATED`)
- `EVT:SL_FILLED` (Derived from `EVT:TRADE_EXECUTED` / `EVT:ORDER_UPDATED`)
- `EVT:POSITION_OPENED` (State transition to MANAGING)
- `EVT:CLOSED` (State transition to CLOSED)

======================================================================
3) ТАБЛИЦА ПЕРЕХОДОВ FSM (ОСНОВНОЙ РАЗДЕЛ)
======================================================================
##### OPENING
| STATE   | INPUT EVENT | ACTIONS / OUTPUT EVENTS                | NEXT STATE |
|---------|-------------|----------------------------------------|------------|
| OPENING | CMD:OPEN    | отправить `DEC:OPEN` (via Adapter)     | OPENING    |
| OPENING | EVT:ORDER_ACK | зафиксировать подтверждение          | OPENING    |
| OPENING | EVT:TRADE_EXECUTED | `EVT:POSITION_OPENED` (logical) | OPENED     |

##### OPENED
| STATE  | INPUT EVENT | ACTIONS / OUTPUT EVENTS | NEXT STATE |
|--------|-------------|-------------------------|------------|
| OPENED | EVT:ORDER_ACK | фиксировать состояние | OPENED     |
| OPENED | EVT:TRADE_EXECUTED | переход к MANAGING | MANAGING   |

##### MANAGING
| STATE    | INPUT EVENT                   | ACTIONS / OUTPUT EVENTS              | NEXT STATE         |
|----------|-------------------------------|--------------------------------------|--------------------|
| MANAGING  | EVT:PORTFOLIO_STATE_UPDATED   | обновить состояние позиции           | MANAGING           |
| MANAGING  | EVT:TRADE_EXECUTED            | update position, check TP/SL logic   | MANAGING / CLOSING |
| MANAGING  | EVT:ORDER_UPDATED             | update bracket status                | MANAGING           |
| MANAGING  | EVT:TP_FILLED (logical)       | инициировать `DEC:CLOSE` и переход   | CLOSING            |
| MANAGING  | EVT:SL_FILLED (logical)       | инициировать `DEC:CLOSE` и переход   | CLOSING            |

##### CLOSING
| STATE   | INPUT EVENT | ACTIONS / OUTPUT EVENTS               | NEXT STATE |
|---------|-------------|---------------------------------------|------------|
| CLOSING | EVT:ORDER_ACK | подтверждение закрывающих ордеров   | CLOSING    |
| CLOSING | EVT:TRADE_EXECUTED | `EVT:CLOSED` (logical)       | CLOSED     |

##### CLOSED
| STATE   | INPUT EVENT           | ACTIONS / OUTPUT EVENTS      | NEXT STATE |
|---------|-----------------------|------------------------------|------------|
| CLOSED  | CMD:OPEN              | старт нового OPENING         | OPENING    |

======================================================================
4) КОНТРАКТ ЦЕПОЧКИ СОБЫТИЙ (CANONICAL EVENT FLOW)
======================================================================
- TICK
- `EVT:FEATURES_CALCULATED` (Upstream)
- `EVT:DECISION_SIGNAL` (Upstream)
- INTENT_OPEN
- `EVT:RISK_ASSESSMENT_COMPLETED` (Upstream)
- `CMD:OPEN`
- `EVT:ORDER_ACK`
- `EVT:TRADE_EXECUTED`
- FSM:OPENING → FSM:OPENED
- FSM:MANAGING
- `EVT:TP_FILLED` / `EVT:SL_FILLED` (Logical)
- `DEC:CLOSE`
- FSM:CLOSING
- `EVT:CLOSED` (Logical)
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
