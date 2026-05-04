# Домен In-Flight Reconcile

## 1. Опис
Цей домен забезпечує надійність системи, запобігаючи "зависанню" ордерів у стані обробки. Він активно звіряє стан ринку через надійні REST-канали після закінчення встановлених таймаутів.

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: зв'язки з `execution_position` та біржею.
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Деталі TTL-менеджменту та моделі статусів.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Протоколи взаємодії з адаптерами.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Логіка фільтрації прострочених записів та скасування.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Аналіз технічного боргу (Memory persistence).
- [**TESTING.md**](./TESTING.md) — Сценарії тестування відновлення після збоїв.

## 3. Використання
Реконсилер ініціалізується в оркестраторі виконання:
```python
reconciler = InFlightReconciler(config, adapter)
asyncio.create_task(reconciler.run_forever())
```

---
*Документація згенерована автоматично (Domain Cartographer v1.0)*
