> **Note:** This auto-generated doc may be stale. The authoritative domain
> documentation is `apps/reference/domains/market_data/README.md`.

# Домен Market Data

## 1. Опис
Цей домен є фундаментом торгової системи. Він забезпечує стабільний та детермінований потік ринкових даних від біржі до внутрішніх компонентів, ізолюючи мережеві ризики.

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: архітектура Proxy/Worker, залежності та івенти. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Деталі багатопроцесної ізоляції та агрегації барів.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Специфікація подій тіків, барів та якорів.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Логіка розрахунку OBI/TFI та алгоритм ресамплінгу.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Аналіз витоків пам'яті та технічного боргу.
- [**TESTING.md**](./TESTING.md) — Огляд тестового покриття та стратегій верифікації.

## 3. Розробка та конфігурація
Налаштування символів та воркерів здійснюється в `market_data.yaml`. При зміні логіки агрегації бару редагуйте `bar_aggregator.py`.

---
*Документація згенерована автоматично (Domain Cartographer v1.0)*
