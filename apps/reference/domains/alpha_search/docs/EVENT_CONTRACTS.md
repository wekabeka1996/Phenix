# Контракти подій домену Alpha Search

## Вихідні події (Outbound)

### EVT:ALPHA_SCORE_CALCULATED
Головна подія домену, що несе торговий імпульс.

**Payload Схема:**
| Поле | Тип | Опис |
|------|-----|------|
| `model_name` | string | Назва моделі або `ensemble_X_models`. |
| `symbol` | string | Торговий тикер (напр. BTCUSDT). |
| `score` | Decimal | Оцінка напрямку [-1.0, 1.0]. |
| `confidence` | Decimal | Впевненість у сигналі [0.0, 1.0]. |
| `features_used` | list | Список назв ознак, використаних у розрахунку. |
| `why` | list | Ланцюжок логічних кроків (reasoning chain). |
| `contributions` | dict | (Опційно для Ensemble) Внесок кожної моделі (weight, score). |

**Приклад:**
```json
{
  "model_name": "ensemble_3_models",
  "symbol": "BTCUSDT",
  "score": 0.65,
  "confidence": 0.82,
  "why": ["Trend is up", "RSI is not overbought", "Volume confirms move"],
  "contributions": {
    "momentum": {"weight": 0.5, "score": 0.8},
    "mean_reversion": {"weight": 0.5, "score": 0.5}
  }
}
```

## Вхідні події (Inbound)

### EVT:FEATURES_CALCULATED
- **Джерело**: `feature_engineering`.
- **Дані**: Словник обчислених метрик.
- **Дія**: Запускає розрахунок альфа-сигналів.
