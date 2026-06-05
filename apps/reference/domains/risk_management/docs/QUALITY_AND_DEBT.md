# Якість коду та технічний борг Risk Management

## 1. Hotspots та ризики
- **Config Fragility**: Прямий доступ до Pydantic моделей (`self.config.domains.risk_management...`) призводить до `AttributeError` та краху системи, якщо у YAML файлі пропущено хоча б одне поле.
- **Persistence amnesia**: Якщо файл `risk_gate_state.json` буде видалено або пошкоджено, система може "забути" про денну просадку і розблокувати торгівлю (хоча реалізовано `_recovery_required` для мінімізації цього ризику).

## 2. Технічний борг (Debt Ledger)

| Елемент | Ризик | Доказ | Рекомендація | Пріоритет |
| :--- | :--- | :--- | :--- | :--- |
| **Silent Absorption Fallback** | Використання 0.0 без масштабування ваг. | `D5` deprecation logic | Перерахувати суму ваг до 1.0, якщо аборпція вимкнена. | Medium |
| **Manual PnL Recalc** | Можлива розбіжність з біржею. | `ACCOUNT_UPDATE` sync | Повністю довіряти `realized_pnl` від біржі замість локального розрахунку. | High |
| **Strict Config Access** | Краш при опечатках у YAML. | `_get_max_risk_score` | Використовувати `getattr(..., default)` або `DomainConfigResolver`. | Low |

## 3. Рекомендації
- Додати перевірку суми ваг у рантаймі: якщо $\sum W_i 
eq 1.0$, емітувати `WARNING`.
- Реалізувати підтримку декількох часових поясів для скидання дня (залежно від біржі).
