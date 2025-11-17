# Migration Standards for Config v2

## 1. Мета

Цей документ задає правила перенесення конфігураційних ключів з legacy-формату (`trading.yaml`, `system.yaml`) у новий модульний формат config v2 (`config/*.yaml`).

Принципи міграції:
- **Additive-only**: нові ключі додаються, існуючі не змінюються/не видаляються.
- **Domain-ізоляція**: міграція по доменах (execution → risk → decision → sizing → features → regimes → tca).
- **Fail-closed**: якщо v2-конфіг відсутній/неповний/некоректний → виняток у v2-builder → fallback на legacy.

## 2. Загальні правила міграції

1. **Переносимо по доменах** у порядку: execution, risk, decision, sizing, features, regimes, tca.
2. **Для кожного ключа**:
   - Спочатку додаємо його у відповідний v2-файл (з коментарем, звідки прийшов — legacy path).
   - Потім оновлюємо відповідний резольвер, щоб читав із v2 (якщо ще не зроблено).
   - Додаємо/оновлюємо тести, які перевіряють:
     - v2 priority (якщо v2 присутній і коректний).
     - Fallback на legacy (якщо v2 відсутній/некоректний).
3. **Після повної міграції домену**:
   - Legacy-ключ позначається як `deprecated` у `docs/config_analysis/config_contract_map.md`.
   - Але fallback залишається активним до Фази 7–8 (Freeze & Replace).

## 3. Fail-closed поведінка

Всі v2-резольвери працюють за схемою:
- Спробувати прочитати v2-конфіг.
- Якщо відсутній / неповний / типи некоректні → виняток всередині v2-builder → fallback на legacy.
- Жодних "тихих" напівзаповнених станів: або повний v2, або повний legacy.

## 4. Приклад повної міграції домену (execution)

1. **Крок 1**: Скопіювати всі `trading.execution.manage.*` у `config/domains/execution.yaml: manage.*`.
   - Додати коментарі: `# Migrated from trading.execution.manage.*`
2. **Крок 2**: Актуалізувати `tests/config/test_execution_manage_v2.py`, щоб основний сценарій працював уже на v2.
   - Змінити тест "legacy_only_behavior" на "v2_priority" після заповнення.
3. **Крок 3**: У `docs/config_analysis/config_contract_map.md` позначити legacy-шлях як deprecated для `manage`.
   - Але не вимикати fallback ще.
4. **Крок 4**: Після стабілізації (тести, production) — у Фазі 7–8 прибрати legacy-читання з резольвера.

## 4.x. Instruments domain міграція

Після міграції execution domain, наступний — instruments.

- **Паспорт інструменту** (exchange, base/quote assets, precision, limits) живе в `config/instruments.yaml: instruments.{symbol}.*`.
- **Активні tweaks** (max_leverage per symbol, sizing_modifiers, tp_sl якщо будуть) — у `config/overrides.yaml: symbols.{symbol}.*`.
- **Regime-based overrides** (якщо будуть) — у `config/overrides.yaml: regimes.{regime}.{symbol}.*`.
- Legacy `trading.instruments.*` вважається frozen/не розширюється; нові інструменти додаються тільки в v2.

## 5. Прогрес міграції доменів

Див. `docs/config_v2/migration_progress.md` для поточного стану.
