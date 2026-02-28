# VF-VERB-REG-02 — Registry coverage vs runtime (warn-only)
Дата: 2026-01-08

## Итоги
- runtime tokens (без tests): **62**
- registry tokens: **60**
- runtime_not_in_registry: **12**
- registry_not_in_runtime: **10**

## Артефакты
- `reports/VF-VERB-REG-02_diff.json`

## Режим
- Warn-only: тест не падает при `runtime_not_in_registry > 0`, но печатает репорт в stdout.
