# Домен Feature Engineering

## 1. Опис
Цей домен є аналітичним ядром системи. Він перетворює потік ринкових подій на структуровані вектори ознак, які використовуються стратегіями для прийняття торгових рішень.

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: оркестрація, залежності та вхідні/вихідні події. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Внутрішня будова: Hot/Cold State, обробка тіків та принципи O(1).
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Специфікація даних `EVT:FEATURES_CALCULATED`.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Математика OBI, TFI та статистичні методи (Уелфорд).
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Аналіз ризиків (Magic Timestamps) та технічний борг.
- [**TESTING.md**](./TESTING.md) — Стратегія знімків (snapshots) та перевірка готовності (warmup).

## 3. Швидкий старт
Домен автоматично обробляє подію `EVT:MARKET_TICK_RECEIVED`. Для додавання нової ознаки необхідно оновити `calculation_engine.py` та схему в `contracts.py`.

---
> **Staleness note (2026-03-15, FE-DOMAIN-AUDIT):** This auto-generated documentation may be stale.
> The authoritative domain reference is `../README.md` in the domain root.

*Документація згенерована автоматично (Domain Cartographer v1.0)*
