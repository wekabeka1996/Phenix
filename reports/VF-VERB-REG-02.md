# VF-VERB-REG-02 — Registry coverage vs runtime (warn-only)
Дата: 2026-01-08

## Итоги
- runtime tokens (без tests): **83**
- registry tokens: **90**
- runtime_not_in_registry: **14**
- registry_not_in_runtime: **21**

## Артефакты
- `reports/VF-VERB-REG-02_diff.json`

## Режим
- Warn-only: тест не падает при `runtime_not_in_registry > 0`, но печатает репорт в stdout.
