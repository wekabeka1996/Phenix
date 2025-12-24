# ACTION CHECKLIST: P0 / P1 / P2 (with code references)

Date: 2025-11-02 (ALL TASKS COMPLETED - Ready for v1 Freeze)

Цей чекліст конкретизує кроки з посиланнями на місця у коді для швидкого впровадження.

## P0 — Production Stabilization (5–7 днів) ✅ COMPLETED

- WAL Garbage Collection + Rotation
  - New: `vfoundation/dr/wal_gc.py` — фонова нитка: видалення файлів старше TTL, ротація за розміром.
  - Integrate: створити екземпляр у `apps/reference/main.py` та/або `vfoundation/apps/reference/main.py` під час ініціалізації і стартувати тред (щогодини).
    - Вставка поруч з ініціалізацією FSM/домена: `apps/reference/main.py: top-level init`, `vfoundation/apps/reference/main.py: ~50–120`.
  - Ground truth: WAL формує щоденні файли тут: `vfoundation/dr/wal.py:203`.
  - Tests: `tests/test_wal_gc.py` — кейси: видалення старих файлів; ротація на порозі.

- Реальний `/debug/{rid}` поверх WAL
  - Edit: `vfoundation/obs/debug_api.py:29` — замінити заглушку на реальне читання WAL для конкретного RID.
  - Джерела:
    - Де WAL читається/перевіряється: `vfoundation/dr/replay.py` (integrity helpers), `vfoundation/cli/vfound/__main__.py: trace/drift` (приклади ітерації WAL).
  - Має повертати: `events[]`, `why_chain[]` (з полів `why` та/або `data_ref`), `integrity_ok`, `count`.

- WHY passthrough у гарячому шляху
  - DTO формує список WHY: `apps/reference/domains/decision_making/decision_making.py:927`.
  - Bridge бере тільки перший WHY: `apps/reference/main.py:416`, `vfoundation/apps/reference/main.py: ~80–120`.
  - Edit: у bridge зберігати увесь ланцюг у `Message.data_ref` і прокладати далі (не лише перший why). Мінімум: `open_command.data_ref = (event.pld.get("why") or [])`.

- Alerts (Slack first)
  - New: `apps/reference/telemetry/alerts.py`, `apps/reference/telemetry/alert_triggers.py` (простий менеджер + 2–3 тригери: risk_gate >80%, circuit breaker active, WAL size > X MB).
  - Вбудувати виклики:
    - У ризику при високому рівні відсічення: `apps/reference/domains/risk_management/risk_management.py` (після визначення `is_trading_allowed`).
    - У execution при збої/CB: `apps/reference/domains/execution_position/fsm.py` (watchdog/ERR обробники).

- Налаштувати параметри/валидацію ризикового скорингу (без переписування логіки)
  - Код: `apps/reference/domains/risk_management/risk_management.py:235` — перевірити ваги/пороги з конфігу.
  - Тести: додати перевірки, що скоринг зростає з leverage/волатильністю та змінюється в межах [0,1]; що гейт блокує понад поріг.

## P1 — Orchestration + Alpha Foundation (1–2 тижні)

- OrchestratorFSM (центральна координація)
  - [x] New: `apps/reference/orchestrator/orchestrator_fsm.py`, `apps/reference/orchestrator/types.py`.
  - [x] Обовʼязки: RID lifecycle, WHY aggregation, TTL/GC, CircuitBreaker, idempotency, Ed25519 signing для `CMD:OPEN/CLOSE`.
  - [x] Інтерфейси: слухати `EVT:TRADE_INTENT_PROPOSED` і емісувати підписані `CMD:OPEN`.
  - [x] Примітка: у поточній архітектурі Router перевіряє підпис (`vfoundation/core/routing.py:101`), але шлях обходить його; або підключити Router, або додати локальну перевірку на вході Execution.
  - [x] **Статус**: ✅ COMPLETED - реалізований з повним набором тестів

- AlphaModel ABC + кілька моделей + простий backtester + DuckDB feature store
  - [x] New:
    - `apps/reference/domains/alpha_search/alpha_model.py` (ABC)
    - `apps/reference/domains/alpha_search/models/{momentum_v1,mean_reversion_v1,volatility_v1}.py`
    - Інтеграція з DecisionMaking: `apps/reference/domains/decision_making/decision_making.py` (емісія EVT:ALPHA_SCORE_CALCULATED)
  - [x] `apps/reference/alpha_discovery/backtest_engine.py`
  - [x] `apps/reference/data/feature_store.py` (DuckDB)
  - Інтегрувати подачу фіч із `apps/reference/domains/feature_engineering/feature_engineering.py`.
  - **Статус**: ✅ COMPLETED - ABC, моделі, інтеграція, backtester та feature store реалізовані

## P2 — Optimization & UI (≈ 1 тиждень)

- [x] Ensemble/оптимізація ваг: `apps/reference/domains/alpha_search/ensemble.py`.
- [x] Multi‑TF фічі: агрегація 5m/15m/1h/4h у feature store. **Статус**: ✅ COMPLETED - Background rollup кожні 15 хвилин інтегровано
- [x] Базова dashboard UI (FastAPI ґрунт є: `apps/reference/api/main.py`).
- [x] Testnet config tuning: mode-specific налаштування (testnet vs production) у `config/aurora/trading.yaml`. **Статус**: ✅ COMPLETED - Релаксовані пороги для тестнету з kelly_boost

## Додаткові код‑посилання (опорні точки)

- WAL файли: `vfoundation/dr/wal.py:203`
- Debug API каркас: `vfoundation/obs/debug_api.py`
- Перевірка підписів: `vfoundation/core/routing.py:101`
- WHY unit‑тести: `tests/test_why_chain.py`, функція `vfoundation/obs/why.py`
- Запис у WAL по позиціям: `apps/reference/domains/position_tracking/position_tracking.py:99`

