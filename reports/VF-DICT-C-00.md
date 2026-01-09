# VF-DICT-C-00 — Подготовка к runtime-enforce: реестр VERB и diff
Дата: 2026-01-08

## Цель
Собрать максимально полный реестр `OP:VERB` на базе фактов (код + governance-артефакты), проверить возможность извлечения из централизованных регистраций Router, и зафиксировать diff как подготовку к Option C (runtime-enforce).

Важно: этот шаг **не меняет рантайм-поведение** и не вводит deny-листи/allow-листи в исполнение.

## Источники и метод
### Governance-артефакты
- YAML:
  - `vfoundation/dictionaries/**/*.yaml`
  - `apps/reference/dictionaries/**/*.yaml`
- Domain JSON:
  - `apps/reference/domains/**/domain_dict.json`

Извлечение: поиск строковых токенов по regex `(EVT|CMD|DEC|ASK|UPD|ERR):...`.

### Код (runtime view)
- `**/*.py` **без** `tests/**`.

Извлечение: поиск строковых токенов по regex `(EVT|CMD|DEC|ASK|UPD|ERR):...`.

### Router registrations (если есть централизовано)
- Проверка наличия вызовов `Router.register(...)`/`*.register("EVT", ...)` по репо.

## Главные факты (проверено)
### Факт 1: централизованных регистраций Router в прод-коде не найдено
В `vfoundation/core/routing.py` есть `Router.register(op, verb, handler)` и lookup по `(msg.op, msg.verb)`, но явные `register("EVT"/...)` вызовы встречаются **только в тестах**.

Артефакт с примерами: `reports/VF-DICT-C-00_artifacts/router_related_snippets.txt`.

Следствие: «полный реестр VERB из handler-регистраций» сейчас **нельзя** извлечь из runtime wiring, потому что такого wiring в коде не обнаружено (по крайней мере в виде `Router.register`).

### Факт 2: governance-артефакты покрывают только малую часть runtime verb-space
Ни global v2.2, ни domain-словари в текущем виде не дают полного списка verb, которые реально встречаются в коде.

## Сводка количеств
### Runtime (без tests)
- Уникальные `OP:VERB` в `.py` (без tests): **52**
- Уникальные `OP:VERB` в governance-артефактах (YAML + domain_dict.json): **20**
- Пересечение (есть и в runtime-коде, и в governance): **13**
- Runtime-verb, которых нет в governance: **39**

OP-распределение (runtime):
- EVT: 41
- DEC: 6
- CMD: 2
- UPD: 2
- ERR: 1

OP-распределение (runtime, отсутствует в governance):
- EVT: 31
- DEC: 6
- UPD: 1
- ERR: 1

### Полный `.py` (включая tests)
Для полноты также сохранена выборка по всем `.py` (включая tests): `reports/VF-DICT-C-00_artifacts/verbs_from_code_py.norm.txt`.

## Пересечение (13 токенов)
Эти токены реально используются в runtime-коде и присутствуют в governance-артефактах:
- CMD:CLOSE
- CMD:OPEN
- EVT:ALPHA_SCORE_CALCULATED
- EVT:EXPOSURE_SUMMARY_UPDATED
- EVT:FEATURES_CALCULATED
- EVT:MARKET_TICK_RECEIVED
- EVT:PORTFOLIO_STATE_UPDATED
- EVT:POSITION_CLOSED
- EVT:REGIME_DETECTED
- EVT:RISK_ASSESSMENT_COMPLETED
- EVT:TRADE_EXECUTED
- EVT:TRADE_INTENT_PROPOSED
- UPD:*

Артефакт: `reports/VF-DICT-C-00_artifacts/verbs_intersection_runtime_and_dicts.txt`.

## Есть в governance, но не найдено в runtime-коде (6 токенов)
- ASK:CLOSE
- ASK:EVAL
- ASK:OPEN
- DEC:EVAL
- DEC:RISK_ASSESSMENT_COMPLETED
- EVT:*

Артефакт: `reports/VF-DICT-C-00_artifacts/verbs_in_dicts_not_in_code.norm.txt`.

Примечание: `EVT:*`/`UPD:*` — это политика wildcard, а не реестр конкретных verb.

## Runtime-verb, которых нет в governance (39 токенов)
Полный список сохранён артефактом:
- `reports/VF-DICT-C-00_artifacts/verbs_runtime_not_in_dicts.norm.txt`

Смысл этого diff: без полного реестра verb строгий runtime-deny по verb невозможно сделать корректно (будет ложный deny).

## Предложение формата SSOT реестра verb (без имплементации)
Чтобы сделать Option C реализуемым без «героизма», нужен **явный** реестр verb с ownership и статусом.

Минимальный практичный формат (пример):

```yaml
version: 1
registry:
  - op: EVT
    verb: MARKET_TICK_RECEIVED
    owner: market_data
    schema: schemas/market_tick_received_v1.json
    status: active   # active|deprecated|experimental
    since: 2025-xx-xx
  - op: DEC
    verb: OPEN
    owner: execution_position
    status: active
policies:
  wildcard:
    EVT: false
    UPD: true
```

Ключевые требования к формату (чтобы он был SSOT, а не «ещё один YAML»):
- **Owner** обязателен (кто отвечает за контракт).
- **Schema reference** желательно для EVT (контрактная структура).
- **Status/депрекация** обязательны для миграций.
- Wildcard-политики (`EVT:*`, `UPD:*`) должны быть отделены от реестра конкретных verb.

## Рекомендованный порядок для Option C (только как план миграции)
1) Сначала довести SSOT verb registry до покрытия runtime verb-space (или договориться, что «string scan» — источник истины на первом шаге).
2) Затем внедрять runtime-enforce этапами:
   - warn-only (логирование)
   - shadow-deny (метрики + отчёты)
   - hard-deny

## Артефакты VF-DICT-C-00
- `reports/VF-DICT-C-00_artifacts/verbs_from_code_py.notests.norm.txt` — runtime `.py` без tests
- `reports/VF-DICT-C-00_artifacts/verbs_from_yaml.norm.txt` — токены из YAML
- `reports/VF-DICT-C-00_artifacts/verbs_from_domain_json.norm.txt` — токены из domain_dict.json
- `reports/VF-DICT-C-00_artifacts/verbs_from_dicts.norm.txt` — объединённые governance токены
- `reports/VF-DICT-C-00_artifacts/verbs_intersection_runtime_and_dicts.txt`
- `reports/VF-DICT-C-00_artifacts/verbs_runtime_not_in_dicts.norm.txt`
- `reports/VF-DICT-C-00_artifacts/verbs_in_dicts_not_in_code.norm.txt`
- `reports/VF-DICT-C-00_artifacts/stats_runtime_by_op.txt`, `stats_missing_by_op.txt`
- `reports/VF-DICT-C-00_artifacts/router_related_snippets.txt` — evidence по Router.register

---

# PACKAGE TEST-REMAIN-001 — Повний список failing тестів та їх класифікація

Дата: 2026-01-08

## Exact summary lines
(Отримано з `python -m pytest -q --maxfail=0 -ra --durations=20 -m "not legacy"`)

passed: XXXX, failed: 8, skipped: XX, deselected: XX

## Список failing тестів
1. test_name_1 - F: Опис чому
2. test_name_2 - R: Опис чому
...

(Деталі в reports/pytest_core_full.txt)

## Класифікація
- L (Legacy): Старі тести, які не підтримуються
- R (Real bug): Реальна помилка в коді
- F (Flaky): Нестабільний тест
- T (Test bug): Помилка в тесті самому

DoD: Повна карта "що ще червоне" — всі 8 failing класифіковані.
