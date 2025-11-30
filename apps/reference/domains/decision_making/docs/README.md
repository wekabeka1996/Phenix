# Decision Making Domain

> **Last Updated**: 2025-11-29  
> **Version**: 1.2.0  
> **Status**: Production Ready ✅

## Overview

The **Decision Making** domain is the **core trading decision engine** in the QuantumTraderX system built on **vFoundation FSM** architecture. It aggregates alpha signals from `AlphaModelRegistry`, applies multi-layer risk assessment, QoS controls, and generates executable trade intents (`EVT:TRADE_INTENT_PROPOSED`) based on portfolio state, market regime, and risk budgets.

### Role in System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         UPSTREAM DOMAINS                                │
│  ┌──────────────┐  ┌───────────────────┐  ┌────────────────────┐       │
│  │ Alpha Search │  │ Feature Eng.      │  │ Risk Management    │       │
│  │ (signals)    │  │ (features)        │  │ (risk_assessment)  │       │
│  └──────┬───────┘  └────────┬──────────┘  └──────────┬─────────┘       │
│         │                   │                        │                  │
│         ▼                   ▼                        ▼                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    DECISION MAKING                                │  │
│  │  • Signal Aggregation (AlphaModelRegistry)                       │  │
│  │  • Regime Filtering (TREND_UP/DOWN, HIGH_VOL, MEAN_REVERSION)    │  │
│  │  • QoS Controls (cooldown, rate limiting, exposure blocking)     │  │
│  │  • Position Sizing (SL-based risk fractions + Kelly criterion)   │  │
│  │  • ROI Exit Strategy (CMD:CLOSE on target ROI)                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                │                                        │
│                                ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              EVT:TRADE_INTENT_PROPOSED                            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                │                                        │
│                                ▼                                        │
│                     DOWNSTREAM DOMAINS                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ Execution Pos.   │  │ Order Management │  │ Monitoring/Alerts    │  │
│  │ (order routing)  │  │ (TCA, venue)     │  │ (risk gate metrics)  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

| Component | File | Description |
|-----------|------|-------------|
| **DecisionMaking** | `decision_making.py` | Main FSM component, ~2000 LOC |
| **NormalizedRejectReasons** | `normalized_reject_reasons.py` | NRR code mapping for analytics |
| **DeferredIntentScheduler** | `deferred_scheduler.py` | QoS retry scheduling |
| **ROIExitStrategy** | `roi_exit_strategy.py` | Position ROI monitoring |
| **WhyCodes** | `why_codes.py` | Standardized WHY chain codes |
| **DecisionLog** | `dm_log_adapter.py` | Structured JSON logging |
| **Pydantic Schemas** | `schemas.py` | Portfolio/Position validation |

## Key Features

### 1. Signal Aggregation & Scoring
- Integration with `AlphaModelRegistry` (Momentum, MeanReversion, Volatility models)
- Confidence-weighted signal scoring
- Alpha scores written to WAL for traceability

### 2. Regime-Aware Trading
- **TREND_UP**: Block counter-trend SELL, 1.2x position multiplier
- **TREND_DOWN**: Block counter-trend BUY, 0.8x position multiplier
- **HIGH_VOLATILITY**: Reduced position sizing
- **MEAN_REVERSION**: Conservative sizing
- **UNCERTAIN**: Skip trading decisions

### 3. Multi-Layer QoS Controls (PACK EXP-4)
- **Symbol Cooldown**: Prevents rapid-fire decisions (default 3s)
- **Rate Limiting**: Max intents per minute per symbol (default 6)
- **Exposure Blocking**: Portfolio exposure limits (10s cooldown)
- **Deferred Scheduler**: One-time retry after cooldown

### 4. Position Sizing
- **SL-Based Risk Fractions**: `q_risk * equity / SL_bps`
- **Kelly Criterion Integration**: Optional dynamic sizing
- **Liquidity Kappa Adjustments**: Static/dynamic caps
- **Min/Max Position Guards**: USD thresholds

### 5. ROI Exit Strategy
- Monitors `EVT:PORTFOLIO_STATE_UPDATED` events
- Emits `CMD:CLOSE` when position ROI exceeds target
- Configurable target ROI percentage (default 50%)

## Configuration

### Domains Config (Priority)
```yaml
domains:
  decision_making:
    position_sizing:
      min_position_size_usd: 10
      liquidity_based_cap_usd: 10000
    qos:
      exposure_block_cooldown_sec: 10
      symbol_cooldown_sec: 3
      max_intents_per_minute_per_symbol: 6
      mode: "defer"  # shadow|defer|enforce
    features:
      ttl_sec: 5
    bar_gating:
      enable: false
      bar_ms: 900000  # 15 minutes
    behavior_fsm:
      enable: false
      high_vol_multiplier: 2.0
      low_vol_multiplier: 0.5
```

### Legacy Config (Fallback)
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
```

## Events

### Consumed Events
| Event | Source | Description |
|-------|--------|-------------|
| `EVT:FEATURES_CALCULATED` | feature_engineering | Fresh feature vectors |
| `EVT:RISK_ASSESSMENT_COMPLETED` | risk_management | Risk parameters |
| `EVT:PORTFOLIO_STATE_UPDATED` | position_tracking | Portfolio state |
| `EVT:REGIME_DETECTED` | regime_detector | Market regime |
| `EVT:EXPOSURE_SUMMARY_UPDATED` | risk_management | Exposure limits |

### Produced Events
| Event | Consumers | Schema |
|-------|-----------|--------|
| `EVT:TRADE_INTENT_PROPOSED` | execution_position | `schemas/trade_intent_v1.json` |
| `EVT:ALPHA_SCORE_CALCULATED` | monitoring | N/A |
| `CMD:CLOSE` (via ROIExitStrategy) | execution_position | N/A |

## Performance

| Metric | Target | Actual |
|--------|--------|--------|
| Hot Path p95 | < 50ms | ~15-20ms |
| Overall p95 | < 100ms | ~40ms |
| Timeout Rate | < 1% | < 0.1% |
| WHY-coverage | ≥ 95% | 100% |

## Testing

- **Total Tests**: 15+
- **QoS Tests**: 8 (cooldown, rate limiting, exposure)
- **Rejection Tests**: 7 (NRR scenarios)
- **Coverage Target**: 90% FSM

```bash
# Run domain tests
pytest tests/test_decision_making_qos.py tests/test_normalized_reject_reasons.py -v
```

## Related Documentation

- [API Dependencies](./API_DEPENDENCIES.md) - vFoundation integration details
- [Events](./EVENTS.md) - Event structures and flow
- [Testing](./TESTING.md) - Test strategy and examples
- [Analysis Summary](./ANALYSIS_SUMMARY.md) - Architecture assessment
