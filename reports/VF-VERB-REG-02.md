# VF-VERB-REG-02 — Registry coverage vs runtime (warn-only)
Дата: 2026-01-08

## Итоги
- runtime tokens (без tests): **60**
- registry tokens: **57**
- runtime_not_in_registry: **9**
- registry_not_in_runtime: **6**

## Артефакты
- `reports/VF-VERB-REG-02_diff.json`

## Режим
- Warn-only: тест не падает при `runtime_not_in_registry > 0`, но печатает репорт в stdout.
