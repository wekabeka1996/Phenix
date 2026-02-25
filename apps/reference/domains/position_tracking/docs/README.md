# Домен Position Tracking

## 1. Опис
Цей домен є Single Source of Truth для стану портфеля. Він відстежує позиції, рахує гроші та гарантує, що система завжди знає свій фінансовий стан, навіть після катастрофічних збоїв.

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: "бухгалтерія", залежності та WAL. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Внутрішня будова: відмовостійкість, синхронізація та Truth-First підхід.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Специфікація `EVT:PORTFOLIO_STATE_UPDATED`.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Розрахунок середньої ціни, PnL та маржі.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Аналіз технічного боргу та ризиків (Simplified PnL).
- [**TESTING.md**](./TESTING.md) — Огляд тестового покриття та сценаріїв стійкості.

## 3. Як використовувати
Домен автоматично слухає угоди. Для отримання поточного стану підпишіться на:
```python
fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", my_handler)
```

---
*Документація згенерована автоматично (Domain Cartographer v1.0)*
