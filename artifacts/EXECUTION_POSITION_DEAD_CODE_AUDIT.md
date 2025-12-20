# execution_position: аудит мёртвого кода/модулей (runtime)

Дата: 2025-12-20

## Цель
Найти модули/код внутри домена `apps/reference/domains/execution_position`, которые:
- не импортируются и не участвуют в runtime-цепочке,
- используются только тестами/скриптами,
- либо являются «заготовками» без реального wiring в системе.

## Runtime-цепочка (baseline)
По workspace видно, что реальная точка входа домена — `ExecPosFSM`, который импортируется в приложении из:
- `apps/reference/main.py` (инициализация доменов)

Далее `ExecPosFSM` тянет зависимости внутри домена через прямые импорты.

## Метод
1) Поиск runtime-импортов по `apps/**` (исключая `tests/**`).
2) Построение графа импортов на AST уровне для папки домена и вычисление достижимости из runtime-root:
   - `apps/reference/main.py`
   - `apps/reference/domains/execution_position/fsm.py`

Команда (в терминах воспроизведения идеи): AST-проход по `import`/`from ... import ...` и BFS по зависимостям.

## Результаты

### Модули домена, достижимые из runtime-root (используются)
Достижимые модули (примерно «живое ядро»):
- `fsm.py` (+ `fsm_open.py`, `fsm_manage.py`, `fsm_close.py`)
- `exposure_guard.py`
- `watchdog.py`
- `order_guardian.py`
- `aurora_log_adapter.py`
- `metrics_collector.py`
- `metrics_aggregator.py`
- `soft_clip.py`
- `contracts.py`
- `utils.py`
- `utils_event_bus.py`

### Кандидаты в мёртвые модули в runtime (test-only)
Следующие файлы **не импортируются** runtime-цепочкой (не достижимы по графу импортов), и при этом
их импорты в репозитории встречаются **только в тестах**:

1) `apps/reference/domains/execution_position/drift_monitor.py`
- Назначение: shadow-mode drift/confusion-matrix (off-path)
- Примечание: модуль используется не только тестами, но и инструментами `vfoundation` (debug/cli).
  Он всё равно не входит в hot-path торговли и не является частью runtime-домена `ExecPosFSM`, но и не «мертвый».

2) `apps/reference/domains/execution_position/idempotent_cancel.py`
- Назначение: helper для идемпотентной отмены ордеров (-2011 absorb)
- Реальные импорты: только `tests/**`
- В runtime-конфиге присутствует `domains.execution_position.idempotent_cancel`, но фактического wiring в `ExecPosFSM`/адаптерах не найдено.

3) `apps/reference/domains/execution_position/order_index.py`
- Назначение: in-memory TTL индекс корреляции `rid/idempotent_key/clientOrderId/exchangeOrderId`
- Реальные импорты: только `tests/**`
- В runtime есть потребитель на стороне WS клиента (`apps/reference/adapters/binance_ws_client.py`), но он обращается к `fsm_core.order_index` **условно**, при этом инициализация/присваивание `order_index` в приложении не найдены (значит фича фактически выключена).

### Сигналы «битых/осиротевших ссылок» вокруг домена
Это не runtime домена напрямую, но хороший индикатор «мертвечины» в дереве:
- `tools/run_tests.py` и `tools/run_order_tests.py` импортируют `apps.reference.domains.execution_position.test_order_index`, которого в дереве нет.
- `scripts/migrate_config_get_calls.py` содержит ссылку на `apps/reference/domains/execution_position/binance_execution_adapter.py`, которого в дереве нет.

## Рекомендации (безопасный план)

### A) Если цель — чистка runtime
- Пометить `drift_monitor.py`, `idempotent_cancel.py`, `order_index.py` как `@deprecated` (минимум: комментарий + явный TODO/issue) и вынести решение:
  - либо удалить вместе с тестами,
  - либо интегрировать (wiring) в runtime.

### B) Если цель — оставить функциональность
- `order_index.py`: добавить явный wiring (создание и присваивание `fsm.order_index`/`fsm_core.order_index`) там, где создаётся `FSMCore`, плюс периодический `expire()`.
- `idempotent_cancel.py`: подключить в места отмены ордеров (в домене/адаптере), вместо «простого cancel».
- `drift_monitor.py`: подключать только в debug/оффлайн-реплее (и явно отделить от hot-path).

### C) Починить окружение tooling
- Обновить/удалить `tools/*`, которые импортируют несуществующий `test_order_index`.
- Либо перенаправить на `tests/units/test_order_index.py`, либо убрать из тулов совсем.

## Быстрые критерии удаления
Можно удалять безопасно, если:
- модуль не импортируется вне `tests/**`,
- нет динамических импортов через `importlib`/строковые импорты в рантайме,
- нет упоминаний в конфигурации, которые реально читаются hot-path кодом.

