# Події Alpha Search Domain

## EVT:ALPHA_SCORE_CALCULATED

### Опис
Основна подія, що емітується після розрахунку alpha score будь-якою моделлю.

### Payload схема
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_score_calculated_event.schema.json",
  "type": "object",
  "properties": {
    "ts": {
      "type": "integer",
      "description": "Timestamp in milliseconds"
    },
    "model_name": {
      "type": "string",
      "description": "Name of the alpha model that calculated the score"
    },
    "symbol": {
      "type": "string",
      "pattern": "^[A-Z0-9]{1,20}$",
      "description": "Trading symbol"
    },
    "score": {
      "type": "number",
      "minimum": -1,
      "maximum": 1,
      "description": "Alpha score [-1.0, 1.0]"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence in the score [0.0, 1.0]"
    },
    "features_used": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "List of feature names used in calculation"
    },
    "why": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Reasoning chain explaining the score"
    },
    "contributions": {
      "type": "object",
      "description": "Model contributions (for ensemble only)",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "score": {"type": "number"},
          "weight": {"type": "number"},
          "contribution": {"type": "number"}
        }
      }
    }
  },
  "required": ["ts", "model_name", "symbol", "score", "confidence"]
}
```

### Приклади payload

#### Momentum Model
```json
{
  "ts": 1640995200000,
  "model_name": "momentum_model",
  "symbol": "BTCUSDT",
  "score": 0.75,
  "confidence": 0.85,
  "features_used": ["momentum_5", "momentum_10", "rsi"],
  "why": [
    "Strong upward momentum detected (5-period: +2.3%)",
    "RSI indicates bullish conditions (65.2)",
    "Volume confirms upward movement"
  ]
}
```

#### Mean Reversion Model
```json
{
  "ts": 1640995200000,
  "model_name": "mean_reversion_model",
  "symbol": "ETHUSDT",
  "score": -0.6,
  "confidence": 0.72,
  "features_used": ["sma_20", "rsi", "bb_position"],
  "why": [
    "Price significantly below 20-SMA (-3.2%)",
    "RSI in oversold territory (28.5)",
    "Bollinger Band position suggests reversion opportunity"
  ]
}
```

#### Volatility Model
```json
{
  "ts": 1640995200000,
  "model_name": "volatility_model",
  "symbol": "ADAUSDT",
  "score": 0.45,
  "confidence": 0.68,
  "features_used": ["atr_ratio", "bb_width", "realized_volatility_1h"],
  "why": [
    "ATR ratio increased (2.1x average)",
    "Bollinger Bands expanding (width +15%)",
    "Realized volatility trending higher"
  ]
}
```

#### Ensemble Model
```json
{
  "ts": 1640995200000,
  "model_name": "ensemble_3_models",
  "symbol": "BTCUSDT",
  "score": 0.62,
  "confidence": 0.78,
  "features_used": ["momentum_5", "rsi", "sma_20", "atr_ratio", "bb_width"],
  "why": [
    "Combined signal from 3 models",
    "Momentum model: strong uptrend",
    "Mean reversion model: neutral",
    "Volatility model: increasing vol"
  ],
  "contributions": {
    "momentum": {
      "score": 0.8,
      "weight": 0.4,
      "contribution": 0.32
    },
    "mean_reversion": {
      "score": 0.1,
      "weight": 0.3,
      "contribution": 0.03
    },
    "volatility": {
      "score": 0.6,
      "weight": 0.3,
      "contribution": 0.18
    }
  }
}
```

## Деталі розрахунку моделей

### Momentum Model Algorithm

#### Score Calculation
```python
def calculate_alpha(self, symbol: str, market_data: Dict[str, Any],
                   features: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AlphaScore:

    # Extract momentum features
    momentum_5 = Decimal(str(features.get('momentum_5', 0)))
    momentum_10 = Decimal(str(features.get('momentum_10', 0)))
    rsi = Decimal(str(features.get('rsi', 50)))

    # Calculate base score from momentum
    momentum_score = (momentum_5 * 0.7 + momentum_10 * 0.3) / Decimal('0.01')  # Normalize to %
    momentum_score = max(Decimal('-10'), min(Decimal('10'), momentum_score)) / Decimal('10')  # Clamp to [-1, 1]

    # Adjust for RSI
    if rsi > 70:
        rsi_adjustment = (rsi - 70) / 30  # Positive adjustment for overbought
    elif rsi < 30:
        rsi_adjustment = (rsi - 30) / 30  # Negative adjustment for oversold
    else:
        rsi_adjustment = Decimal('0')

    final_score = momentum_score + rsi_adjustment * Decimal('0.3')
    final_score = max(Decimal('-1'), min(Decimal('1'), final_score))

    # Calculate confidence
    momentum_strength = abs(momentum_5) + abs(momentum_10)
    confidence = min(momentum_strength / Decimal('0.05'), Decimal('1'))  # 5% threshold

    return AlphaScore(...)
```

#### Confidence Factors
- **Momentum strength**: abs(momentum_5) + abs(momentum_10) > 0.05
- **RSI confirmation**: RSI in extreme zones boosts confidence
- **Volume confirmation**: High volume supports momentum signals

### Mean Reversion Model Algorithm

#### Score Calculation
```python
def calculate_alpha(self, symbol: str, market_data: Dict[str, Any],
                   features: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AlphaScore:

    # Extract features
    sma_20 = Decimal(str(features.get('sma_20', 0)))
    current_price = Decimal(str(market_data.get('price', 0)))
    rsi = Decimal(str(features.get('rsi', 50)))
    bb_position = Decimal(str(features.get('bb_position', 0)))  # -1 to 1

    # Calculate deviation from SMA
    if sma_20 > 0:
        deviation_pct = (current_price - sma_20) / sma_20
    else:
        deviation_pct = Decimal('0')

    # RSI-based reversion signal
    if rsi > 70:
        rsi_signal = (rsi - 70) / 30  # Overbought = positive reversion
    elif rsi < 30:
        rsi_signal = (rsi - 30) / 30  # Oversold = negative reversion
    else:
        rsi_signal = Decimal('0')

    # Combine signals
    deviation_weight = Decimal('0.6')
    rsi_weight = Decimal('0.4')

    combined_score = deviation_pct * deviation_weight + rsi_signal * rsi_weight
    combined_score = max(Decimal('-1'), min(Decimal('1'), combined_score))

    # Calculate confidence based on deviation magnitude
    confidence = min(abs(deviation_pct) / Decimal('0.05'), Decimal('1'))  # 5% threshold

    return AlphaScore(...)
```

#### Confidence Factors
- **Deviation magnitude**: Larger deviations = higher confidence
- **RSI extremes**: RSI < 30 or > 70 increases confidence
- **BB position**: Position near bands supports reversion thesis

### Volatility Model Algorithm

#### Score Calculation
```python
def calculate_alpha(self, symbol: str, market_data: Dict[str, Any],
                   features: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AlphaScore:

    # Extract volatility features
    atr_ratio = Decimal(str(features.get('atr_ratio', 1)))
    bb_width = Decimal(str(features.get('bb_width', 0.05)))
    bb_width_change = Decimal(str(features.get('bb_width_change', 0)))
    rv_1h = Decimal(str(features.get('realized_volatility_1h', 0)))
    rv_1d = Decimal(str(features.get('realized_volatility_1d', 0)))

    # ATR ratio signal
    atr_signal = atr_ratio - Decimal('1.0')  # Center on 0
    atr_signal = max(Decimal('-2.0'), min(Decimal('2.0'), atr_signal)) / Decimal('2.0')

    # BB width change signal
    bb_signal = bb_width_change * Decimal('10')  # Amplify small changes
    bb_signal = max(Decimal('-1.0'), min(Decimal('1.0'), bb_signal))

    # Realized volatility trend
    if rv_1d > 0:
        rv_trend = rv_1h - rv_1d
        rv_signal = rv_trend / rv_1d
        rv_signal = max(Decimal('-2.0'), min(Decimal('2.0'), rv_signal)) / Decimal('2.0')
    else:
        rv_signal = Decimal('0')

    # Combine signals with weights
    weights = {
        'atr': Decimal('0.4'),
        'bb': Decimal('0.25'),
        'rv': Decimal('0.2'),
        'range': Decimal('0.1'),
        'vol_corr': Decimal('0.05')
    }

    combined_score = (
        atr_signal * weights['atr'] +
        bb_signal * weights['bb'] +
        rv_signal * weights['rv']
    )

    # Clamp to [-1, 1]
    final_score = max(Decimal('-1.0'), min(Decimal('1.0'), combined_score))

    # Calculate confidence
    confidence = self._calculate_confidence(atr_signal, bb_signal, rv_signal)

    return AlphaScore(...)
```

#### Confidence Calculation
```python
def _calculate_confidence(self, atr_sig: Decimal, bb_sig: Decimal, rv_sig: Decimal) -> Decimal:
    signals = [atr_sig, bb_sig, rv_sig]

    # Agreement ratio
    positive_count = sum(1 for s in signals if s > 0.1)
    negative_count = sum(1 for s in signals if s < -0.1)
    total_strong_signals = positive_count + negative_count

    if total_strong_signals == 0:
        return Decimal('0.4')

    agreement_ratio = max(positive_count, negative_count) / total_strong_signals
    base_confidence = Decimal('0.6') + (agreement_ratio * Decimal('0.3'))

    # Strength factor
    avg_strength = sum(abs(s) for s in signals) / len(signals)
    strength_factor = min(Decimal('1.3'), Decimal('0.7') + avg_strength)

    return min(Decimal('1.0'), base_confidence * strength_factor)
```

## Ensemble Model Algorithm

### Weight Calculation
```python
def _combine_scores(self, valid_scores: List[Tuple[str, AlphaScore]], symbol: str) -> AlphaScore:
    total_weighted_score = Decimal("0.0")
    total_weight = Decimal("0.0")
    total_confidence = Decimal("0.0")

    for model_name, score in valid_scores:
        weight = Decimal(str(self.weights.model_weights.get(model_name, 0.0)))
        if weight > 0:
            weighted_score = score.score * weight
            total_weighted_score += weighted_score
            total_weight += weight
            total_confidence += score.confidence * weight

    if total_weight > 0:
        final_score = total_weighted_score / total_weight
        final_confidence = total_confidence / total_weight
    else:
        final_score = Decimal("0.0")
        final_confidence = Decimal("0.0")

    return AlphaScore(...)
```

### Dynamic Rebalancing
```python
def _rebalance_weights(self) -> None:
    # Calculate performance scores
    performance_scores = {}
    for model_name, performances in self.model_performance.items():
        if performances:
            score = float(np.mean(performances))
            if self._ensemble_config.risk_adjustment:
                variance = float(np.var(performances))
                score = score * (1 - min(variance, 0.5))
            performance_scores[model_name] = max(score, 0.1)

    # Normalize to weights
    total_score = sum(performance_scores.values())
    if total_score > 0:
        new_weights = {model: score / total_score for model, score in performance_scores.items()}

        # Apply constraints
        for model in new_weights:
            new_weights[model] = max(self._ensemble_config.min_weight,
                                   min(self._ensemble_config.max_weight, new_weights[model]))

        self.weights.model_weights = new_weights
```

## State Management

### Model State
```python
# Per-model performance tracking
model_performance: Dict[str, List[float]] = {
    'momentum_model': [0.85, 0.72, 0.91, ...],
    'mean_reversion_model': [0.68, 0.74, 0.59, ...],
    'volatility_model': [0.77, 0.81, 0.69, ...]
}

# Ensemble performance
ensemble_performance: List[float] = [0.78, 0.82, 0.75, ...]
```

### Weight State
```python
weights = EnsembleWeights(
    model_weights={
        'momentum_model': 0.4,
        'mean_reversion_model': 0.35,
        'volatility_model': 0.25
    },
    last_updated=datetime(2024, 1, 15, 10, 30),
    performance_score=0.76
)
```

## Error Handling

### Graceful Degradation
```python
def calculate_all_alpha(self, symbol: str, market_data: Dict[str, Any],
                       features: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> List[AlphaScore]:

    scores = []
    for model in self._models.values():
        if model.is_ready(features):
            try:
                score = model.calculate_alpha(symbol, market_data, features, context)
                scores.append(score)
            except Exception as e:
                # Log error but continue with other models
                logger.warning(f"Error calculating alpha for {model.name}: {e}")
                continue
    return scores
```

### Validation
```python
def _validate_score(self, score: AlphaScore) -> bool:
    """Validate alpha score constraints."""
    if not (-1 <= score.score <= 1):
        return False
    if not (0 <= score.confidence <= 1):
        return False
    if not score.model_name or not score.symbol:
        return False
    return True
```

## Performance Considerations

### Latency Optimization
- **Feature caching**: Avoid recalculation of expensive features
- **Parallel execution**: Models can run concurrently
- **Lazy evaluation**: Calculate only when features available

### Memory Management
- **Performance history**: Limited deque size (max 100 entries)
- **Feature cleanup**: Remove old/unused feature data
- **Model state**: Efficient storage of model weights and metrics

### Scalability
- **Horizontal scaling**: Models can be distributed across workers
- **Feature partitioning**: Different models can use different feature sets
- **Batch processing**: Process multiple symbols in batches
