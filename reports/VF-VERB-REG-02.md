# VF-VERB-REG-02 — Registry coverage vs runtime (warn-only)
Дата: 2026-01-08

## Итоги
- runtime tokens (без tests): **50**
- registry tokens: **56**
- runtime_not_in_registry: **0**
- registry_not_in_runtime: **6**

## Артефакты
- `reports/VF-VERB-REG-02_diff.json`

## Режим
- Warn-only: тест не падает при `runtime_not_in_registry > 0`, но печатает репорт в stdout.
