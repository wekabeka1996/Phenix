# ANTI-CHURN Self-Audit — Explicit over Implicit / Fail-Closed

Дата: 2026-01-09

Объекты аудита:
- [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py)
- [apps/reference/config_models.py](apps/reference/config_models.py)
- [tests/domains/decision_making/test_anti_churn_harden.py](tests/domains/decision_making/test_anti_churn_harden.py)

## 1) Критерии

**Explicit over Implicit**
- Включённая фича (anti-churn) не должна «подхватывать» значения через `getattr(..., default)`/магические дефолты в рантайме.
- Дефолты допустимы только как часть контракта (Pydantic defaults) или явные дефолты в “feature disabled” ветке.

**Fail-Closed**
- При `anti_churn.enabled=true` любая невалидная/частичная конфигурация должна приводить к ошибке контракта (а не к тихому fallback).

## 2) Контракты конфигурации (Pydantic)

Файл: [apps/reference/config_models.py](apps/reference/config_models.py)

Наблюдения:
- `RegimeInertiaConfig`, `CostGateConfig`, `AntiChurnConfig` используют `extra='forbid'`.
- В `AntiChurnConfig` реализован валидатор `@model_validator`:
  - если `enabled=true`, то `regime_inertia`, `cost_gate`, `time_multipliers` обязательны.

Оценка:
- **PASS** по “fail-closed на структуру” (частичная конфигурация при `enabled=true` не проходит валидацию).

Риски:
- Значения по умолчанию (например `confirm_window_sec=90.0`, `default_cost_bps=4.0`) — это **контрактные дефолты**. Они допустимы, но должны быть отражены в SSOT/YAML, если для прод-режима требуется явная настройка.

## 3) AuroraHandler: fail-closed и implicit fallbacks

Файл: [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py)

### 3.1 Fail-closed при включении

Наблюдения:
- При `anti_churn.enabled=true` и невалидном `anti_churn` происходит `ConfigContractError`.
- При `enabled=false` невалидная/частичная конфигурация игнорируется для обратной совместимости.

Оценка:
- **PASS**: включённый anti-churn валидируется fail-closed.

### 3.2 Explicit over Implicit: устранение `getattr(..., default)`

Ранее были обнаружены случаи чтения значений anti-churn через `getattr(..., default)` даже при включённой фиче.

Исправления:
- Убраны `getattr(inertia, "confirm_window_same_severity_sec", 5.0)` и `getattr(cg, "fees_are_round_trip", False)` — теперь используются поля Pydantic-моделей напрямую.
- Убраны `getattr(self, "regime_inertia_confirm_window_same_severity_sec", 5.0)` и `getattr(self, "cost_gate_fees_are_round_trip", False)` — используются инициализированные атрибуты.
- Убраны `getattr(self, "cost_gate_vol_lookback_sec", 60)` — используется инициализированный атрибут.

Оценка:
- **PASS**: внутри включённого anti-churn ветвления больше нет скрытых дефолтов для этих параметров.

### 3.3 Оставшиеся “неявные” места (требуют решения политики)

Наблюдение:
- `_estimate_rv_bps()` имеет fallback `fallback_map` по `regime_effective` (источник `"approx_regime"`).

Почему это важно:
- Это **эвристика**, то есть нестрого “контракт-first”.
- С точки зрения “fail-closed” можно требовать, чтобы RV приходил только из features/price_motion, иначе:
  - либо блокировать торговлю (fail-closed, но потенциально слишком консервативно),
  - либо бросать `ConfigContractError`/ошибку runtime (сильно меняет поведение),
  - либо сделать поведение управляемым контрактом (рекомендуется).

Рекомендация (без внесения изменения поведения в этом патче):
- Добавить опцию в контракт `CostGateConfig`, например `require_rv_bps_feature: bool = False`.
  - Если `True` и RV не найден — блокировать (или поднимать исключение), строго по выбранной политике.

## 4) Тесты

Файл: [tests/domains/decision_making/test_anti_churn_harden.py](tests/domains/decision_making/test_anti_churn_harden.py)

Покрытие:
- Risk-off: immediate.
- Risk-on: confirm window.
- Same severity: buffer (5s).
- Monotonicity: wall-time jumps не засчитываются.
- Cost gate: round-trip fee adjustment + `cost_bps_source`.

Оценка:
- **PASS**: тесты покрывают критические инварианты harden/polish.

## 5) Итог

- Fail-closed на конфигурацию при `enabled=true`: **PASS**.
- Explicit over Implicit: устранены ключевые silent-fallback дефолты в включённой anti-churn ветке: **PASS**.
- Открытый вопрос: эвристический `approx_regime` fallback для RV — требуется решение политики (контрактный флаг), если хотим максимальную строгость.
