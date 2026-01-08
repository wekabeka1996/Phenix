# VF-VERB-REG-06 — Apply owner suggestions (>=70%)
Дата: 2026-01-08

## Правила
- Автоправка только поля `owner`.
- Меняем только если текущий `owner: unknown`, suggested_owner != unknown, confidence >= 0.70.

## Итог
- Applied: **13**
- Artifact: `reports/VF-VERB-REG-06_applied.json`

## Изменения
| token | old_owner | new_owner | confidence | evidence (top_files) |
|---|---|---|---:|---|
| DEC:CANCEL_ORDER | unknown | execution_position | 1.00 | apps/reference/domains/execution_position/fsm_manage.py:2 |
| DEC:PLACE_ORDER | unknown | execution_position | 1.00 | apps/reference/domains/execution_position/fsm_manage.py:2 |
| ERR:OPEN | unknown | execution_position | 0.75 | apps/reference/domains/execution_position/fsm.py:3, apps/reference/telemetry/audit_logger.py:1 |
| EVT:DECISION_BLOCKED | unknown | decision_making | 1.00 | apps/reference/domains/decision_making/decision_making.py:1, apps/reference/domains/decision_making/schemas_decision_blocked.py:1 |
| EVT:DECISION_TRACE_EMITTED | unknown | decision_making | 1.00 | apps/reference/domains/decision_making/decision_making.py:2 |
| EVT:FUNDING_UPDATE | unknown | feature_engineering | 1.00 | apps/reference/domains/feature_engineering/feature_engineering.py:5 |
| EVT:OI_UPDATE | unknown | feature_engineering | 1.00 | apps/reference/domains/feature_engineering/feature_engineering.py:5 |
| EVT:ORDER_ACK | unknown | execution_position | 1.00 | apps/reference/domains/execution_position/fsm.py:2, apps/reference/domains/execution_position/utils_event_bus.py:1 |
| EVT:ORDER_FILL | unknown | execution_position | 1.00 | apps/reference/domains/execution_position/fsm.py:2 |
| EVT:STRATEGY_DECISION_BLOCKED | unknown | decision_making | 1.00 | apps/reference/domains/decision_making/aurora_handler.py:1, apps/reference/domains/decision_making/mean_reversion_handler.py:1 |
| EVT:TICK_RECEIVED | unknown | decision_making | 1.00 | apps/reference/domains/decision_making/__init__.py:1 |
| EVT:TRADE_INTENT_REJECTED | unknown | decision_making | 1.00 | apps/reference/domains/decision_making/decision_making.py:1 |
| UPD:TICK | unknown | execution_position | 1.00 | apps/reference/domains/execution_position/fsm_close.py:1 |
