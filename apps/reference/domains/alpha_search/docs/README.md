# Домен Alpha Search

## 1. Опис
Цей домен відповідає за перетворення ринкових ознак (features) у торгові сигнали (alpha scores). Він реалізує набір стратегічних моделей та механізм їхнього об'єднання (Ensemble).

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: межі, файли, події та залежності. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Внутрішня будова: фреймворк моделей, реєстр та ансамблювання.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Специфікація сигналу `EVT:ALPHA_SCORE_CALCULATED`.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Математичні формули трендових та контр-трендових моделей.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Оцінка технічного боргу та планів (Phase 3).
- [**TESTING.md**](./TESTING.md) — Огляд тестового покриття та стратегій верифікації.

## 3. Як використовувати (Quick Start)
1. Створіть конфігурацію в `alpha_search.yaml`.
2. Зареєструйте моделі в `AlphaModelRegistry`.
3. Слухайте подію `EVT:ALPHA_SCORE_CALCULATED`.

---
*Документація згенерована автоматично (Domain Cartographer v1.0)*
