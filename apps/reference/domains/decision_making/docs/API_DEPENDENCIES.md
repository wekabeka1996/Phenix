# Decision Making API Dependencies

> **Last Updated**: 2025-11-29  
> **Version**: 1.2.0

## vFoundation Integration

The Decision Making domain integrates with vFoundation components for FSM orchestration, logging, configuration, WAL, and security.

### Core Imports

```python
# FSM Core
from vfoundation.core.protocol import Message
from vfoundation.core.why_codes import WhyCode, format_why_with_details

# Data Recovery (WAL)
from vfoundation.dr import wal

# Telemetry
from apps.reference.telemetry.metrics import inc_decision_deferred
from apps.reference.telemetry.order_logger import order_logger

# Optional: Alerts
from apps.reference.telemetry.alerts import AlertManager

# Optional: Alpha Models
from apps.reference.domains.alpha_search import (
    AlphaModelRegistry,
    MomentumAlphaModel,
    MeanReversionAlphaModel,
    VolatilityAlphaModel
)
```

## FSM Integration

### Class Initialization

```python
class DecisionMaking:
    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        
        # Event listeners registration
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)
        self.fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED", self.update_exposure_cache)
```

### FSM Methods Used

| Method | Purpose | Example |
|--------|---------|---------|
| `fsm.listen(event, handler)` | Register event handler | `fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)` |
| `fsm.emit(event, payload, why, data_ref)` | Emit FSM event | `fsm.emit("EVT:TRADE_INTENT_PROPOSED", payload, why, refs)` |

## Configuration System

### Safe Configuration Access

The domain supports **both Pydantic models and dictionaries** with safe fallback:

```python
def _safe_config_get(self, *keys, default=None):
    """Safe nested config access with fallbacks."""
    current = self.config
    for key in keys:
        if hasattr(current, key):
            current = getattr(current, key)
        elif isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current
```

### Configuration Priority

1. **Domains Config** (preferred): `config.domains.decision_making.*`
2. **Legacy Config** (fallback): `config.trading.decision.*`

### Configuration Paths

| Path | Type | Default | Description |
|------|------|---------|-------------|
| `domains.decision_making.position_sizing.min_position_size_usd` | Decimal | 10 | Min position USD |
| `domains.decision_making.position_sizing.liquidity_based_cap_usd` | Decimal | 10000 | Max position USD |
| `domains.decision_making.qos.exposure_block_cooldown_sec` | int | 10 | Exposure cooldown |
| `domains.decision_making.qos.symbol_cooldown_sec` | int | 3 | Symbol cooldown |
| `domains.decision_making.qos.max_intents_per_minute_per_symbol` | int | 6 | Rate limit |
| `domains.decision_making.qos.mode` | str | "defer" | QoS mode |
| `domains.decision_making.features.ttl_sec` | int | 5 | Features freshness TTL |
| `domains.decision_making.bar_gating.enable` | bool | false | Bar gating toggle |
| `domains.decision_making.behavior_fsm.enable` | bool | false | Behavior FSM toggle |

## Logging Infrastructure

### Decision Logger (dlog)

```python
from dm_log_adapter import DecisionLog

self.dlog = DecisionLog()

# Usage
self.dlog.write(
    "FEATURES_RX",                    # event type
    rid,                              # request ID
    {"symbol": symbol, "keys": [...]} # payload
)
```

**Log Events:**
- `FEATURES_RX` - Feature data received
- `RISK_RX` - Risk parameters received
- `PORTFOLIO_RX` - Portfolio state received
- `DECISION_EVAL` - Decision evaluation
- `INTENT_PROPOSED` - Trade intent created
- `INTENT_REJECTED` - Trade intent rejected

### Application Logger

```python
self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
chain_logger = logging.getLogger("event_chain")
```

**Log Levels:**
- `DEBUG` - Decision tracing, QoS state
- `INFO` - Normal events, intent creation
- `WARNING` - Rejections, QoS blocks
- `ERROR` - Critical failures

## WAL Integration

Alpha scores are written to WAL for traceability:

```python
try:
    wal_record = {
        "op": "EVT",
        "verb": "ALPHA_SCORE_CALCULATED",
        "symbol": symbol,
        "scores": [score.dict() for score in alpha_scores],
        "timestamp": int(time.time() * 1000),
        "why": "alpha_calculation"
    }
    wal.append(wal_record)
except Exception as wal_e:
    self.logger.warning(f"Failed to write alpha scores to WAL: {wal_e}")
```

## External Dependencies

### Alpha Model Registry

```python
if ALPHA_MODELS_AVAILABLE:
    self.alpha_registry = AlphaModelRegistry()
    self.alpha_registry.register(MomentumAlphaModel())
    self.alpha_registry.register(MeanReversionAlphaModel())
    self.alpha_registry.register(VolatilityAlphaModel())
```

**Methods:**
- `alpha_registry.calculate_all_alpha(symbol, market_data, features)` - Calculate all model scores
- `alpha_registry.list_models()` - List registered models

### Alert Manager

```python
if ALERT_MANAGER_AVAILABLE:
    self.alert_manager = AlertManager(
        config=config, 
        logger=self.logger.getChild("alerts")
    )
```

**Metrics tracked:**
- `intents_seen_total` - Total intents evaluated
- `intents_blocked_total` - Intents blocked by risk gate

### Order Logger

```python
from apps.reference.telemetry.order_logger import order_logger

order_logger.write({
    "rid": rid,
    "event_type": "ORDER_INTENT",
    "symbol": symbol,
    "metadata": {"intent_proposed": True}
})
```

### Deferred Intent Scheduler

```python
from deferred_scheduler import DeferredIntentScheduler

self._deferred_scheduler = DeferredIntentScheduler()

# Schedule one-time retry
self._deferred_scheduler.schedule_once(
    symbol,
    int(cooldown_sec * 1000),
    retry_callback
)
```

## Data Flow

### Input Sources

| Source | Data | Event |
|--------|------|-------|
| Alpha Search | Signal scores | `EVT:ALPHA_SCORE_CALCULATED` |
| Feature Engineering | Feature vectors | `EVT:FEATURES_CALCULATED` |
| Risk Management | Risk parameters | `EVT:RISK_ASSESSMENT_COMPLETED` |
| Position Tracking | Portfolio state | `EVT:PORTFOLIO_STATE_UPDATED` |
| Regime Detector | Market regime | `EVT:REGIME_DETECTED` |

### Output Destinations

| Destination | Data | Event |
|-------------|------|-------|
| Execution Position | Trade intent | `EVT:TRADE_INTENT_PROPOSED` |
| Execution Position | Close command | `CMD:CLOSE` |
| Monitoring | Alpha scores | `EVT:ALPHA_SCORE_CALCULATED` |
| WAL | Alpha records | N/A |
| Logs | Decision trace | N/A |

## Data Transformation Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ INPUTS                                                          │
│  Alpha Signals + Portfolio + Regime + Features + Risk + Config  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ DECISION EVALUATION                                              │
│  • Signal scoring (aggregate alpha scores)                      │
│  • Regime filtering (block counter-trend)                       │
│  • Features freshness check (TTL validation)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ QOS CONTROLS                                                     │
│  • Symbol cooldown (prevent rapid-fire)                         │
│  • Rate limiting (max intents/minute)                           │
│  • Exposure blocking (portfolio limits)                         │
│  • Deferred scheduling (retry after cooldown)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ POSITION SIZING                                                  │
│  • SL-based risk fractions                                      │
│  • Kelly criterion (optional)                                   │
│  • Regime multipliers                                           │
│  • Liquidity kappa adjustments                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ INTENT CREATION                                                  │
│  • DTO assembly (trade_intent_v1 schema)                        │
│  • Why chain building                                           │
│  • Idempotency key generation                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ OUTPUTS                                                          │
│  • EVT:TRADE_INTENT_PROPOSED emission                           │
│  • Decision logging (dlog)                                      │
│  • Order logging (order_logger)                                 │
│  • QoS state updates                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Error Handling

### Exception Isolation

```python
try:
    intent = self._create_trade_intent(...)
except Exception as e:
    self.logger.error(f"Decision failure: {e}")
    # Don't crash - log and continue
    return
```

### Graceful Degradation

| Component | Failure Behavior |
|-----------|------------------|
| Alpha Registry | Trading continues without alpha scores |
| Alert Manager | Metrics not collected, but trading continues |
| WAL Write | Warning logged, trading continues |
| Config Missing | Safe defaults used |

## Performance Optimization

### Pre-computed Values

```python
# Cached at init time
self.min_pos_size_usd = decimal.Decimal(str(min_size))
self.liq_cap_usd = decimal.Decimal(str(liq_cap))
self.qos_exposure_block_cooldown_sec = int(exp_cooldown)
```

### Latency Targets

| Operation | Target | Actual |
|-----------|--------|--------|
| Signal Evaluation | 10ms | ~5-10ms |
| Regime Filtering | 5ms | ~2-5ms |
| QoS Controls | 8ms | ~3-8ms |
| Position Sizing | 15ms | ~5-15ms |
| Intent Creation | 5ms | ~2-5ms |
| **Total (p95)** | **<50ms** | **~20ms** |
