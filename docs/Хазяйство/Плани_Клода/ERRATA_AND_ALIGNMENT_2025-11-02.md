# ERRATA & CODE ALIGNMENT (2025-11-02)

Date: 2025-11-02 (Dashboard implementation completed)

Цей документ синхронізує ключові твердження у планах з фактичним станом коду і уточнює пріоритети/зусилля. Використовуйте його у парі з існуючими документами (EXECUTIVE_SUMMARY, GAP_ANALYSIS, ARCHITECTURAL_DECISIONS, SPRINT_PLAN, RID_WHY_CONTRACTS_ANALYSIS).

## Ключові виправлення

- Risk scoring вже динамічний у коді. Потрібні валідація, тюнінг порогів і тести, а не «виправлення з нуля».
  - Код: `apps/reference/domains/risk_management/risk_management.py:235` — обчислення на базі `delta_price_pct`, `obi`, `tfi`, `absorption` з вагами і гейтом по порогу `max_risk_score`.
  - Споживання: `apps/reference/domains/decision_making/decision_making.py:643` — відкидання наміру, якщо `is_trading_allowed` = False.
  - Рекомендації: додати тести варіації з важелем/волатильністю; параметризувати пороги; розглянути VaR/CVaR як P1.

- WHY chain/XAI наразі не централізований.
  - Емісія: `apps/reference/domains/decision_making/decision_making.py:927` — `why` як список у payload (DTO наміру).
  - Bridge передає лише перший WHY у `Message.why`: `apps/reference/main.py:416` і `vfoundation/apps/reference/main.py:86+` (пошук «Preserve XAI chain»), через що ланцюг втрачається між доменами.
  - Timely fix (P0): передавати повний ланцюг у `Message.data_ref` і акумулювати його по гарячому шляху (Bridge → ExecPosFSM).
  - Strategic (P1): OrchestratorFSM з централізованою агрегацією why_chain і `/debug/{rid}`. ✅ COMPLETED

- `/debug/{rid}` є, але це заглушка.
  - Файл: `vfoundation/obs/debug_api.py:29` — повертає тестові дані; не читає WAL.
  - P0: реалізувати читання WAL з RID‑фільтром, збір `why_chain`, базову перевірку цілісності (ланцюг `_prev` → `_hash`).

- WAL існує без GC/ротації.
  - Файл: `vfoundation/dr/wal.py:203` — створення щоденних файлів `ops/wal/YYYY-MM-DD.jsonl`.
  - P0: окремий фоновий `WALGarbageCollector` (TTL+size rotation), інтеграція в main, прості тести.

- Ed25519 підпис перевіряється у Router, але гарячий шлях його оминає.
  - Перевірка: `vfoundation/core/routing.py:101` — підпис обовʼязковий для `DEC`/`CMD`.
  - Поточний шлях: FSMCore/emit без Router (`apps/reference/...`), через що підпис не верифікується на гарячому шляху.
  - Варіанти: (а) підписувати і верифікувати в існуючому шляху (до ExecPosFSM), (б) перевести DEC/CMD через Router.

## Скориговані пріоритети/зусилля

- P0 (5–7 днів): WAL‑GC + реальний `/debug/{rid}` + алерти + WHY passthrough у `data_ref`.
- P1 (1–2 тижні): OrchestratorFSM (RID lifecycle/WHY/TTL/CB/idempotency/підпис) + AlphaModel ABC + простий backtester + DuckDB feature store.
- P2 (1 тиждень): Ensemble/оптимізація ваг, multi‑TF, базова UI панель.

## Посилання на код (швидка карта)

- Risk scoring: `apps/reference/domains/risk_management/risk_management.py:235`
- Decision гейт за ризиком: `apps/reference/domains/decision_making/decision_making.py:643`
- WHY список у DTO: `apps/reference/domains/decision_making/decision_making.py:927`
- Bridge бере тільки перший WHY: `apps/reference/main.py:416`, `vfoundation/apps/reference/main.py:100`
- WAL без GC: `vfoundation/dr/wal.py:203`
- `/debug/{rid}` заглушка: `vfoundation/obs/debug_api.py:29`
- Перевірка підпису в Router: `vfoundation/core/routing.py:101`
- WAL записи позицій: `apps/reference/domains/position_tracking/position_tracking.py:99`

