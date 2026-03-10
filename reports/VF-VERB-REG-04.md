# VF-VERB-REG-04 — Owner inference report (heuristic, evidence-based)
Дата: 2026-01-08

## Правила
- Owner визначається лише по шляху файлів.
- Якщо ≥70% входжень токена знаходяться в `apps/reference/domains/<X>/`, то suggested_owner = `<X>`. 
- Інакше suggested_owner лишається `unknown`, але показуються top-3 кандидати з %.

## Сводка
- unknown tokens in registry: **17**
- report rows: **17**

## Таблица (token → suggested_owner → candidates → evidence)
| token | total | suggested_owner | candidates (owner:pct,count) | top_files (path:count) |
|---|---:|---|---|---|
| DEC:CANCEL | 0 | unknown | - | - |
| EVT:BALANCE_UPDATE_RECEIVED | 3 | unknown | position_tracking:66.67%(2), account_balance:33.33%(1) | apps/reference/domains/position_tracking/position_tracking.py:2, apps/reference/domains/account_balance/account_connector.py:1 |
| EVT:CANCELLED | 3 | unknown | execution_position:33.33%(1) | vfoundation/core/adapters/execution_adapter.py:2, apps/reference/domains/execution_position/drift_monitor.py:1 |
| EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE | 2 | risk_management | risk_management:100.0%(2) | apps/reference/domains/risk_management/risk_management.py:2 |
| EVT:EXPIRED | 1 | unknown | - | vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:FILL | 4 | unknown | execution_position:25.0%(1) | apps/reference/domains/execution_position/fsm_close.py:1, vfoundation/core/payloads.py:1, vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:INTENT_DROPPED | 0 | unknown | - | - |
| EVT:MR_SIGNAL_PRODUCED | 0 | unknown | - | - |
| EVT:ORCHESTRATOR_ERROR | 0 | unknown | - | - |
| EVT:ORDER_EXECUTED | 0 | unknown | - | - |
| EVT:ORDER_REJECTED | 6 | unknown | decision_making:16.67%(1), execution_position:16.67%(1), shadow_telemetry:16.67%(1) | apps/reference/adapters/binance_ws_client.py:2, apps/reference/config_models.py:1, apps/reference/domains/decision_making/md_amr_handler.py:1 |
| EVT:ORDER_STATE_CHANGED | 5 | unknown | execution_position:20.0%(1), shadow_telemetry:20.0%(1) | apps/reference/adapters/binance_ws_client.py:2, apps/reference/config_models.py:1, apps/reference/domains/execution_position/watchdog.py:1 |
| EVT:ORDER_TIMEOUT | 0 | unknown | - | - |
| EVT:PARTIAL_FILL | 3 | unknown | execution_position:66.67%(2) | apps/reference/domains/execution_position/fsm_manage.py:2, vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:POSITION_CLOSED | 5 | unknown | neocortex:60.0%(3), shadow_telemetry:20.0%(1) | apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:3, apps/reference/config_models.py:1, apps/reference/domains/shadow_telemetry/snapshot_store.py:1 |
| EVT:REJECTED | 4 | unknown | - | vfoundation/core/adapters/execution_adapter.py:4 |
| EVT:VERB | 1 | unknown | - | vfoundation/core/fsm_core.py:1 |
