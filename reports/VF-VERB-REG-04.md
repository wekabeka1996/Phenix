# VF-VERB-REG-04 — Owner inference report (heuristic, evidence-based)
Дата: 2026-01-08

## Правила
- Owner визначається лише по шляху файлів.
- Якщо ≥70% входжень токена знаходяться в `apps/reference/domains/<X>/`, то suggested_owner = `<X>`. 
- Інакше suggested_owner лишається `unknown`, але показуються top-3 кандидати з %.

## Сводка
- unknown tokens in registry: **11**
- report rows: **11**

## Таблица (token → suggested_owner → candidates → evidence)
| token | total | suggested_owner | candidates (owner:pct,count) | top_files (path:count) |
|---|---:|---|---|---|
| DEC:CANCEL | 0 | unknown | - | - |
| EVT:CANCELLED | 3 | unknown | execution_position:33.33%(1) | vfoundation/core/adapters/execution_adapter.py:2, apps/reference/domains/execution_position/drift_monitor.py:1 |
| EVT:EXPIRED | 1 | unknown | - | vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:FILL | 4 | unknown | execution_position:25.0%(1) | apps/reference/domains/execution_position/fsm_close.py:1, vfoundation/core/payloads.py:1, vfoundation/obs/correlation.py:1 |
| EVT:MR_SIGNAL_PRODUCED | 0 | unknown | - | - |
| EVT:ORCHESTRATOR_ERROR | 0 | unknown | - | - |
| EVT:ORDER_EXECUTED | 0 | unknown | - | - |
| EVT:PARTIAL_FILL | 3 | unknown | execution_position:66.67%(2) | apps/reference/domains/execution_position/fsm_manage.py:2, vfoundation/core/adapters/execution_adapter.py:1 |
| EVT:POSITION_CLOSED | 6 | unknown | neocortex:66.67%(4), shadow_telemetry:16.67%(1) | apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:4, apps/reference/config_models.py:1, apps/reference/domains/shadow_telemetry/snapshot_store.py:1 |
| EVT:REJECTED | 4 | unknown | - | vfoundation/core/adapters/execution_adapter.py:4 |
| EVT:VERB | 1 | unknown | - | vfoundation/core/fsm_core.py:1 |
