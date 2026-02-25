# Домен Execution Position

## 1. Опис
Цей домен є виконавчим механізмом системи. Він транслює торгові ідеї у реальні ордери на біржі, керує ризиками на рівні транзакцій та супроводжує позиції до їх повного закриття.

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: оркестрація, залежності та потік подій. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Внутрішня будова: трьохфазний FSM, гейти та механізми самовідновлення.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Специфікація команд `CMD:OPEN/CLOSE` та подій заповнення.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Математика нормалізації лотів, захист ціни (Anti-2021) та трейлінг-стоп.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Аналіз технічного боргу (Monolithic FSM) та ризиків.
- [**TESTING.md**](./TESTING.md) — Стратегія тестування критичних шляхів виконання.

## 3. Швидкий старт
Домен працює як реактивний сервіс. Для початку торгівлі необхідно надіслати `CMD:OPEN` у шину FSM.

```python
from apps.reference.domains.execution_position.fsm import ExecPosFSM
fsm = ExecPosFSM(bus=fsm_core, adapter=binance_adapter, config=config)
fsm.start()
```

---
*Документація згенерована автоматично (Domain Cartographer v1.0)*
