# Decision Making API Dependencies

## vFoundation Integration

The Decision Making domain integrates deeply with vFoundation components for FSM orchestration, logging, configuration, and security.

### Core FSM Classes

```python
from vfoundation.core.fsm import FSM
from vfoundation.core.config import ConfigManager
from vfoundation.core.logging import StructuredLogger
from vfoundation.core.security import Ed25519Signer
```

#### FSM Integration

```python
class DecisionMaking(FSM):
    """Decision making FSM extending vFoundation base."""

    def __init__(self, config: ConfigManager, fsm: FSM, alert_manager):
        super().__init__(config)
        self.fsm = fsm  # Parent FSM reference
        self.alert_manager = alert_manager
```

**FSM Methods Used:**
- `fsm.emit(event, payload, why, data_ref)`: Event emission
- `fsm.start()`: Component lifecycle start
- `fsm.stop()`: Component lifecycle stop

### Configuration System

#### Safe Configuration Access

```python
def _safe_config_get(self, *keys, default=None):
    """Safe nested config access with fallbacks."""
    try:
        value = self.config
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError, AttributeError):
        return default
```

**Configuration Paths:**
- `trading.decision.sizing_modifiers`: Regime-based multipliers
- `trading.decision.position_sizing.*`: Position sizing parameters
- `trading.decision.kelly.*`: Kelly criterion settings
- `trading.execution.brackets.*`: Stop-loss/take-profit brackets
- `trading.execution.manage.brackets.*`: Alternative bracket config

### Logging Infrastructure

#### Structured Logging (dlog)

```python
from vfoundation.logging.decision_logger import DecisionLogger

self.dlog = DecisionLogger(fsm_id="DecisionMaking")
```

**Decision Logging Events:**
- `DECISION_EVAL`: Signal evaluation results
- `DECISION_SKIP`: Trade rejection with reason
- `INTENT_PROPOSED`: Successful intent creation

#### Application Logging

```python
from vfoundation.logging.app_logger import AppLogger

self.logger = AppLogger(__name__)
```

**Log Levels Used:**
- `DEBUG`: Detailed decision tracing
- `INFO`: Normal operation events
- `WARNING`: Rejection events and warnings
- `ERROR`: Critical failures

### Security Integration

#### Ed25519 Signing (High-Risk Operations)

```python
from vfoundation.security.signer import Ed25519Signer

# Sign critical trade intents
signature = self.signer.sign({
    "intent": trade_intent,
    "timestamp": current_time,
    "risk_level": "HIGH"
})
```

**Signed Operations:**
- Large position sizes (>1% equity)
- Market orders (high slippage risk)
- Bracket adjustments (OPEN/CLOSE/ADJUST commands)

## External Dependencies

### Alpha Model Registry

```python
from apps.reference.domains.alpha_search.alpha_model_registry import AlphaModelRegistry

# Signal aggregation and scoring
signals = self.alpha_registry.get_signals(symbol)
signal_score = self._calculate_signal_score(signals)
```

**Integration Points:**
- Signal retrieval by symbol
- Confidence-weighted scoring
- Feature vector access

### Alert Manager

```python
from vfoundation.monitoring.alert_manager import AlertManager

# Risk gate monitoring
if blocked_pct > threshold:
    self.alert_manager.check_risk_gate(blocked_pct)
```

**Alert Types:**
- Risk gate violations
- QoS threshold breaches
- Decision latency spikes

### Order Logger V1

```python
from vfoundation.logging.order_logger_v1 import OrderLoggerV1

# Structured order event logging
order_logger.write({
    "rid": rid,
    "event_type": "ORDER_INTENT",
    "symbol": symbol,
    "metadata": {"intent_proposed": True}
})
```

**Logged Events:**
- `ORDER_INTENT`: Successful intent creation
- `ORDER_REJECTED`: Intent rejection with NRR codes

### Deferred Intent Scheduler

```python
from apps.reference.domains.decision_making.deferred_scheduler import DeferredIntentScheduler

# QoS-based intent deferral
if self._should_defer_intent(symbol):
    self.deferred_scheduler.schedule_intent(intent, delay_ms)
```

**QoS Integration:**
- Symbol-specific cooldown management
- Rate limit window tracking
- Exposure limit enforcement

## Data Flow Architecture

### Input Sources

1. **Alpha Signals**: AlphaModelRegistry aggregation
2. **Portfolio State**: Real-time equity and positions
3. **Market Regime**: Regime classification and confidence
4. **Feature Data**: Price references and market features
5. **Configuration**: Dynamic config updates

### Output Destinations

1. **FSM Events**: EVT:TRADE_INTENT_PROPOSED emission
2. **Decision Logs**: Structured decision tracing
3. **Order Logs**: Intent creation/rejection events
4. **Alert System**: Risk monitoring and alerts
5. **QoS State**: Internal quality control updates

### Data Transformation Pipeline

```
Alpha Signals + Portfolio + Regime + Features + Config
    ↓
Decision Evaluation (Signal Scoring + Regime Filtering)
    ↓
QoS Controls (Cooldown + Rate Limit + Exposure Check)
    ↓
Position Sizing (SL-based + Kelly + Regime Multipliers)
    ↓
Intent Creation (DTO Assembly + Why Chain Building)
    ↓
Event Emission + Logging + State Updates
```

## Error Handling Integration

### Exception Propagation

```python
try:
    # Critical decision logic
    intent = self._create_trade_intent(...)
except Exception as e:
    self.logger.error(f"Decision failure: {e}")
    # Emit failure event instead of crashing
    self.fsm.emit("EVT:DECISION_FAILED", {"error": str(e)})
    return
```

### Graceful Degradation

- **Config Fallbacks**: Safe config access with defaults
- **Component Isolation**: Failures don't cascade
- **Logging Continuity**: Errors logged even during failures
- **State Consistency**: QoS state maintained during errors

## Performance Integration

### Latency Requirements

- **Hot Path**: p95 < 50ms
- **Overall**: p95 < 100ms
- **Timeout Rate**: < 1%

### Optimization Points

```python
# Pre-computed values
self.liq_cap_usd = self._safe_config_get("trading", "decision", "liquidity_cap_usd", default=1000.0)
self.min_pos_size_usd = self._safe_config_get("trading", "decision", "min_position_size_usd", default=10.0)

# Cached calculations
@cached_property
def qos_config(self):
    return self._load_qos_configuration()
```

## Monitoring Integration

### Metrics Collection

```python
from vfoundation.monitoring.metrics import MetricsCollector

# Decision metrics
self.metrics.incr("decisions_evaluated")
self.metrics.timing("decision_latency", latency_ms)
self.metrics.gauge("active_intents", len(self.pending_intents))
```

### Health Checks

```python
def health_check(self):
    """Component health validation."""
    return {
        "status": "healthy" if self._is_operational() else "unhealthy",
        "last_decision": self.last_decision_time,
        "qos_state": self._get_qos_health(),
        "error_rate": self._calculate_error_rate()
    }
```

## Future Integration Points

### Planned Enhancements

- **Model Registry V2**: Enhanced signal aggregation
- **Risk Engine V2**: Real-time risk assessment
- **Execution Router**: Direct execution path integration
- **Telemetry V2**: Enhanced observability
- **Config Hot Reload**: Dynamic configuration updates</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\API_DEPENDENCIES.md
