# VF-VERB-REG-04 — Owner inference report (heuristic, evidence-based)
Дата: 2026-01-08

## Правила
- Owner визначається лише по шляху файлів.
- Якщо ≥70% входжень токена знаходяться в `apps/reference/domains/<X>/`, то suggested_owner = `<X>`. 
- Інакше suggested_owner лишається `unknown`, але показуються top-3 кандидати з %.

## Сводка
- unknown tokens in registry: **18**
- report rows: **18**

## Таблица (token → suggested_owner → candidates → evidence)
| token | total | suggested_owner | candidates (owner:pct,count) | top_files (path:count) |
|---|---:|---|---|---|
| DEC:CANCEL | 1 | unknown | - | apps/reference/adapters/simulated_adapter.py:1 |
| EVT:ALPHA_SCORE_CALCULATED | 3 | unknown | decision_making:66.67%(2), alpha_search:33.33%(1) | apps/reference/domains/decision_making/__init__.py:1, apps/reference/domains/decision_making/decision_making.py:1, apps/reference/domains/alpha_search/alpha_model.py:1 |
| EVT:BALANCE_UPDATE_RECEIVED | 3 | unknown | position_tracking:66.67%(2), account_balance:33.33%(1) | apps/reference/domains/position_tracking/position_tracking.py:2, apps/reference/domains/account_balance/account_connector.py:1 |
| EVT:CANCELLED | 4 | unknown | execution_position:25.0%(1) | vfoundation/core/adapters/execution_adapter.py:3, apps/reference/domains/execution_position/drift_monitor.py:1 |
| EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE | 3 | unknown | risk_management:66.67%(2) | apps/reference/domains/risk_management/risk_management.py:2, apps/reference/main.py:1 |
| EVT:EXPIRED | 1 | unknown | - | vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:FILL | 3 | unknown | execution_position:33.33%(1) | apps/reference/domains/execution_position/fsm_close.py:1, vfoundation/obs/correlation.py:1, vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:INTENT_DROPPED | 3 | unknown | - | apps/reference/main.py:3 |
| EVT:MR_SIGNAL_PRODUCED | 1 | unknown | - | apps/reference/config_models.py:1 |
| EVT:ORCHESTRATOR_ERROR | 1 | unknown | - | apps/reference/orchestrator/orchestrator_fsm.py:1 |
| EVT:ORDER_EXECUTED | 1 | unknown | - | apps/reference/orchestrator/orchestrator_fsm.py:1 |
| EVT:ORDER_REJECTED | 1 | unknown | - | apps/reference/orchestrator/orchestrator_fsm.py:1 |
| EVT:ORDER_STATE_CHANGED | 3 | unknown | execution_position:33.33%(1) | apps/reference/adapters/binance_ws_client.py:2, apps/reference/domains/execution_position/watchdog.py:1 |
| EVT:ORDER_TIMEOUT | 1 | unknown | - | apps/reference/orchestrator/orchestrator_fsm.py:1 |
| EVT:PARTIAL_FILL | 3 | unknown | execution_position:66.67%(2) | apps/reference/domains/execution_position/fsm_manage.py:2, vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:POSITION_CLOSED | 1 | unknown | - | apps/reference/orchestrator/orchestrator_fsm.py:1 |
| EVT:REJECTED | 4 | unknown | - | vfoundation/core/adapters/execution_adapter.py:4 |
| EVT:VERB | 1 | unknown | - | vfoundation/core/fsm_core.py:1 |
