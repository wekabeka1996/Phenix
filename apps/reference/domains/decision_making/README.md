# Decision Making Domain

## Overview

The Decision Making domain is the core trading decision engine in the QuantumTraderX system. It aggregates signals from the AlphaModelRegistry, applies risk assessment, and makes final trading decisions based on portfolio state, market conditions, and quality-of-service (QoS) controls.

## Architecture

### Core Components

- **DecisionMaking**: Main FSM component handling trade intent evaluation
- **NormalizedRejectReasons**: Standardized rejection reason mapping for consistent logging
- **DeferredIntentScheduler**: QoS management for symbol cooldowns and rate limiting

### Key Features

- **Signal Scoring**: Aggregates alpha signals with regime filtering
- **Position Sizing**: SL-based risk fractions with Kelly criterion integration
- **QoS Controls**: Symbol cooldown, rate limiting, and exposure blocking
- **Risk Management**: AlertManager integration with intent blocking monitoring
- **Comprehensive Logging**: Structured logging with why chains and NRR codes

## API Usage

### Basic Usage

```python
from apps.reference.domains.decision_making.decision_making import DecisionMaking

# Initialize with config
dm = DecisionMaking(config=config, fsm=fsm, alert_manager=alert_manager)

# Evaluate trading opportunity
dm.evaluate_opportunity(
    symbol="BTCUSDT",
    features_data={"price": "50000.0", "features": {...}},
    portfolio={"equity": "100000.0"},
    regime={"regime": "TREND_UP", "confidence": 0.8},
    rid="test-rid-123"
)
```

### Configuration

```yaml
trading:
  decision:
    sizing_modifiers:
      TREND_UP: 1.2
      TREND_DOWN: 0.8
    position_sizing:
      risk_fraction_q: 0.01
      liquidity_kappa_mode: "static"
      liquidity_kappa: 1.0
    kelly:
      base_probability: 0.5
      kelly_cap: 0.25
      kelly_alpha: 0.8
      payoff_ratio_r: 2.0
  execution:
    brackets:
      sl:
        fixed_bps: 50
      tp:
        fixed_bps: 100
```

## Events

### EVT:TRADE_INTENT_PROPOSED

Emitted when a trade intent is successfully created and approved.

**Payload Structure:**
```json
{
  "instrument": "BTCUSDT",
  "side": "buy",
  "order": {
    "qty": "0.001",
    "price": "50000.0",
    "price_ref": "50000.0",
    "reduce_only": false
  },
  "p": "0.75",
  "payoff_ratio_r": "2.0",
  "tca_budget": {
    "max_slippage_bps": "10",
    "max_latency_ms": 500,
    "maker_preference": "neutral"
  },
  "risk_budget": {
    "trade_cvar95_max_bps": "100",
    "session_cvar95_max_bps": "200"
  },
  "size": {
    "notional_cap_usd": "50.0",
    "kelly_fraction": "0.1"
  },
  "valid_for_ms": 5000,
  "why": ["signal_score=0.85", "regime_multiplier=1.2", "pos_size_usd=50.0"],
  "dto_version": "1.0.0",
  "schema_ref": "...",
  "idempotent_key": "uuid-string"
}
```

## QoS Controls

### Symbol Cooldown
Prevents over-trading the same symbol within a time window.

### Rate Limiting
Limits total trading intents per time window across all symbols.

### Exposure Blocking
Blocks trading when portfolio exposure exceeds configured limits.

### Side Bias Penalty
Adjusts signal thresholds when BUY/SELL ratio becomes imbalanced.

## Position Sizing

### SL-Based Sizing
Primary sizing method using stop-loss risk fractions:
- `q_risk`: Risk fraction of equity per trade
- SL-based notional calculation
- Liquidity kappa adjustments

### Kelly Criterion Integration
Optional Kelly fraction calculation:
- Dynamic probability estimation from signal scores
- Conservative probability bounds [0.45, 0.65]
- Capped Kelly fractions with alpha scaling

### Regime Multipliers
Regime-based position size adjustments:
- Configurable multipliers per regime state
- Applied after base sizing calculation

## Rejection Reasons

All rejections include normalized reason codes (NRR) for consistent monitoring:

- `NEUTRAL_SIGNAL`: Signal below threshold
- `BEHAVIOR_GATE`: FSM behavior state disallows entry
- `REGIME_FILTER`: Regime filter blocks trade
- `NO_PRICE_REFERENCE`: Missing price data
- `ZERO_QUANTITY`: Position size calculation failed
- `EXPOSURE_LIMIT_EXCEEDED`: QoS exposure blocking
- `RATE_LIMIT_EXCEEDED`: QoS rate limiting
- `INSUFFICIENT_BALANCE`: Portfolio balance insufficient

## Dependencies

- **vFoundation**: FSM base classes, logging, configuration
- **AlphaModelRegistry**: Signal aggregation and scoring
- **AlertManager**: Risk monitoring and alerting
- **OrderLoggerV1**: Structured order event logging
- **NormalizedRejectReasons**: Rejection reason standardization</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\README.md
