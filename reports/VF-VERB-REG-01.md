# VF-VERB-REG-01 — SSOT Verb Registry seed (from runtime)
Дата: 2026-01-08

## Что сделано
- Сгенерирован seed verb registry из runtime-скана `.py` (без `tests/**` и без `.venv/**`).
- Для неизвестных owner/schema выставлены значения по умолчанию: `owner: unknown`, `schema: null`, `status: experimental`.

## Итоги генерации
- Уникальных `OP:VERB` в runtime (без tests): **51**
- Записей в registry: **51**
- Top-20 по частоте помечены `status: active` и получили owner (см. VF-VERB-REG-03).

## Выходные файлы
- `apps/reference/dictionaries/verb_registry_v1.yaml`
