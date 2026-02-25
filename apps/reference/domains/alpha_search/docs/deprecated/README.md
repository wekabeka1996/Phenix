# Alpha Search Domain

## Огляд

Alpha Search - це домен для розрахунку торгових сигналів (alpha scores) на основі різних моделей аналізу ринку. Система складається з абстрактного фреймворку для моделей, конкретних реалізацій моделей та ensemble системи для комбінування сигналів.

## Архітектура

### Основні компоненти

#### 1. AlphaModel (alpha_model.py)
Абстрактний базовий клас для всіх alpha моделей:
- **AlphaScore**: Pydantic модель для результатів розрахунку
- **AlphaModel**: ABC з методами для розрахунку сигналів
- **AlphaModelRegistry**: Реєстр для управління моделями

#### 2. EnsembleModel (ensemble.py)
Система комбінування сигналів з множини моделей:
- Динамічне зважування на основі продуктивності
- Регулярне ребалансування ваг
- Відстеження внеску кожної моделі

#### 3. Конкретні моделі (models/)
- **MomentumAlphaModel**: Аналіз імпульсу ціни
- **MeanReversionAlphaModel**: Аналіз відхилень від середнього
- **VolatilityAlphaModel**: Аналіз волатильності

## Підтримувані моделі

### Momentum Model
```python
# Аналізує тренд ціни за останні N періодів
# Score: -1 (strong down) to +1 (strong up)
# Features: price_history, volume, momentum_indicators
```

### Mean Reversion Model
```python
# Шукає відхилення від середнього для reversion
# Score: -1 (oversold) to +1 (overbought)
# Features: sma, rsi, bollinger_bands
```

### Volatility Model
```python
# Аналізує зміни волатильності
# Score: -1 (decreasing vol) to +1 (increasing vol)
# Features: atr, bb_width, realized_volatility
```

### Ensemble Model
```python
# Комбінує сигнали від множини моделей
# Динамічні ваги на основі historical performance
# Risk-adjusted weighting
```

## API використання

### Базове використання
```python
from apps.reference.domains.alpha_search import AlphaModelRegistry
from apps.reference.domains.alpha_search.models import MomentumAlphaModel

# Створити реєстр
registry = AlphaModelRegistry()

# Зареєструвати модель
momentum_model = MomentumAlphaModel()
registry.register(momentum_model)

# Розрахувати alpha для символу
market_data = {'price': 45000, 'volume': 100}
features = {'momentum_5': 0.023, 'rsi': 65}
context = {'regime': 'TREND_UP'}

scores = registry.calculate_all_alpha(
    symbol='BTCUSDT',
    market_data=market_data,
    features=features,
    context=context
)
```

### Ensemble використання
```python
from apps.reference.domains.alpha_search import EnsembleModel, EnsembleConfig

# Створити конфігурацію
config = EnsembleConfig(
    rebalance_frequency_days=7,
    risk_adjustment=True
)

# Створити моделі
models = {
    'momentum': MomentumAlphaModel(),
    'mean_rev': MeanReversionAlphaModel(),
    'volatility': VolatilityAlphaModel()
}

# Створити ensemble
ensemble = EnsembleModel(config, models)

# Розрахувати комбінований сигнал
score = ensemble.calculate_alpha(
    symbol='BTCUSDT',
    market_data=market_data,
    features=features
)
```

## Конфігурація

### AlphaScore схема
```json
{
  "model_name": "momentum_model",
  "symbol": "BTCUSDT",
  "score": 0.75,
  "confidence": 0.85,
  "timestamp": "2024-01-15T10:30:00Z",
  "features_used": ["momentum_5", "rsi", "volume"],
  "why": [
    "Strong upward momentum detected",
    "RSI indicates bullish conditions"
  ]
}
```

### Ensemble конфігурація
```python
@dataclass
class EnsembleConfig:
    rebalance_frequency_days: int = 7
    min_weight: float = 0.0
    max_weight: float = 1.0
    performance_window_days: int = 30
    risk_adjustment: bool = True
```

## Події

### EVT:ALPHA_SCORE_CALCULATED
```json
{
  "event": "EVT:ALPHA_SCORE_CALCULATED",
  "payload": {
    "model_name": "ensemble_3_models",
    "symbol": "BTCUSDT",
    "score": 0.65,
    "confidence": 0.78,
    "features_used": ["momentum_5", "rsi", "atr_ratio"],
    "why": ["Combined signal from 3 models"],
    "contributions": {
      "momentum": {"score": 0.8, "weight": 0.4, "contribution": 0.32},
      "mean_rev": {"score": 0.5, "weight": 0.3, "contribution": 0.15},
      "volatility": {"score": 0.6, "weight": 0.3, "contribution": 0.18}
    }
  }
}
```

## Інтеграція з системою

### З feature_engineering
Alpha моделі отримують features від feature_engineering домену:
```
EVT:FEATURES_CALCULATED → alpha_search.calculate_alpha() → EVT:ALPHA_SCORE_CALCULATED
```

### З decision_making
Alpha scores передаються до decision_making для формування торгових рішень:
```
EVT:ALPHA_SCORE_CALCULATED → decision_making.evaluate_opportunity()
```

### З risk_management
Ensemble враховує risk metrics при зважуванні моделей:
```python
if config.risk_adjustment:
    score = score * (1 - min(variance, 0.5))
```

## Моніторинг та метрики

### Performance метрики
- **Model accuracy**: Відсоток правильних передбачень
- **Confidence calibration**: Чи відповідає confidence реальній точності
- **Ensemble diversity**: Різноманітність сигналів між моделями

### Business метрики
- **Signal strength**: Середній absolute score по всіх моделях
- **Coverage**: Відсоток символів з достатніми features
- **Latency**: Час розрахунку alpha scores

## Розробка нових моделей

### Шаблон нової моделі
```python
from apps.reference.domains.alpha_search.alpha_model import AlphaModel, AlphaScore

class MyCustomAlphaModel(AlphaModel):

    def get_model_name(self) -> str:
        return "my_custom_model"

    def get_required_features(self) -> List[str]:
        return ["custom_feature_1", "custom_feature_2"]

    def calculate_alpha(self, symbol: str, market_data: Dict[str, Any],
                       features: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AlphaScore:

        # Ваша логіка розрахунку
        score = self._calculate_score(features)
        confidence = self._calculate_confidence(features)

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=score,
            confidence=confidence,
            features_used=self.get_required_features(),
            why=self._build_reasoning(score, features)
        )
```

## Тестування

### Unit тести
```bash
pytest tests/test_alpha_models.py -v
# 18 passed
```

### Integration тести
```bash
pytest tests/test_ensemble.py -v
pytest tests/test_alpha_models.py::TestAlphaModelIntegration -v
```

## Продуктивність

### Benchmarks
- **Single model**: < 10ms per calculation
- **Ensemble (3 models)**: < 50ms per calculation
- **100 symbols**: < 2s total

### Оптимізації
- **Feature caching**: Перерахунок тільки при зміні даних
- **Model parallelism**: Конкурентний розрахунок моделей
- **Lazy evaluation**: Розрахунок тільки при потребі

## Безпека

### Input validation
- **Feature validation**: Перевірка наявності required features
- **Score bounds**: Клемпінг до [-1, 1] діапазону
- **Confidence bounds**: Клемпінг до [0, 1] діапазону

### Error handling
- **Graceful degradation**: Продовження при помилці однієї моделі
- **Logging**: Детальне логування помилок для debugging
- **Fallback scores**: Default scores при відсутності даних
