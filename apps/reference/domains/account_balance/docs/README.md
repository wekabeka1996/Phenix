# Домен Account Balance

## 1. Опис
Цей домен забезпечує отримання залишків балансу та відкритих позицій з біржі (Binance) та публікацію їх у внутрішню шину подій системи.

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Швидкий огляд: межі, залежності, файли, івенти, діаграми. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Внутрішня будова: потоки (threading), цикли, конфігурація.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Схеми подій `EVT:BALANCE_UPDATE_RECEIVED` та `EVT:ACCOUNT_UPDATE_RECEIVED`.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Математична логіка: фільтрація активів, Decimal-розрахунки.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Аналіз технічного боргу, ризиків та вузьких місць.
- [**TESTING.md**](./TESTING.md) — Опис тестів, сценаріїв та прогалин у покритті.

## 3. Швидкий старт
Домен автоматично ініціалізується в оркестраторі `neocortex` (або подібних), використовуючи `AuroraConfig`.

```python
from apps.reference.domains.account_balance.account_connector import AccountConnector
connector = AccountConnector(fsm=fsm_instance, config=config_instance)
connector.start() # Запускає фоновий потік моніторингу
```
---
*Документація згенерована та консолідована автоматично (Domain Cartographer v1.0)*
