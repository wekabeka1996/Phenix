# Якість коду та технічний борг Regime Detector

## 1. Hotspots та ризики
- **Manual Buffer Management**: Домен самостійно веде буфери для розрахунку SMA/ATR, якщо вони відсутні в `features`. Це створює дублювання логіки з `feature_engineering`.
- **Complexity of `handle_event`**: Головний метод обробки подій занадто великий (150+ рядків), поєднуючи валідацію, математику та логіку переходів.

## 2. Технічний борг (Debt Ledger)

| Елемент | Ризик | Доказ | Рекомендація | Пріоритет |
| :--- | :--- | :--- | :--- | :--- |
| **HMM Implementation Gap** | Відсутність сучасних методів детекції. | `regime.yaml` config unused | Реалізувати підтримку Hidden Markov Model. | Medium |
| **Static Multipliers** | Неточність впевненості на різних волатильностях. | `confidence_multiplier=20.0` | Перейти на адаптивні коефіцієнти. | Low |
| **Model Versioning** | Важкість оновлення логіки без зміни коду. | Хардкод `sma_trend_v1` | Використовувати Registry для моделей режимів. | Low |

## 3. Рекомендації
- Повністю синхронізувати розрахунок базових індикаторів з `feature_engineering`, використовуючи готові дані.
- Розбити `handle_event` на менші функціональні блоки: `_update_indicators`, `_evaluate_models`, `_apply_hysteresis`.
