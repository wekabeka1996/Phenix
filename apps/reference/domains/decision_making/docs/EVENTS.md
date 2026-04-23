# Decision Making Events

> **Last Updated**: 2025-11-29
> **Version**: 1.2.0

## Event Overview

| Event | Direction | Description |
|-------|-----------|-------------|
| `EVT:FEATURES_CALCULATED` | **IN** | Feature vectors from feature_engineering |
| `EVT:RISK_ASSESSMENT_COMPLETED` | **IN** | Risk parameters from risk_management |
| `EVT:PORTFOLIO_STATE_UPDATED` | **IN** | Portfolio state from position_tracking |
| `EVT:REGIME_DETECTED` | **IN** | Market regime from regime_detector |
| `EVT:EXPOSURE_SUMMARY_UPDATED` | **IN** | Exposure limits from risk_management |
| `EVT:TRADE_INTENT_PROPOSED` | **OUT** | Trade intent to execution_position |
| `EVT:STRATEGY_DECISION_BLOCKED` | **OUT** | Telemetry for blocked decisions (NRR codes) |
| `EVT:ALPHA_SCORES_AGGREGATED` | **OUT** | Aggregate alpha telemetry to monitoring |
| `CMD:CLOSE` | **OUT** | ROI exit command to execution_position |

---

## EVT:TRADE_INTENT_PROPOSED

### Description
Emitted when a trade intent has been successfully evaluated, approved through all QoS controls, and is ready for execution routing.

### Schema Reference
`schemas/trade_intent_v1.json` (JSON Schema 2020-12)

### Payload Structure

```json
{
  "instrument": "BTCUSDT",
  "side": "buy",
  "p": "0.55",
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
    "kelly_fraction": "0.1",
    "notional_cap_usd": "50.0"
  },
  "order": {
    "price_ref": "50000.0",
    "qty": "0.001",
    "price": "50000.0",
    "reduce_only": false
  },
  "valid_for_ms": 5000,
  "why": [
    "signal_score=0.85",
    "regime_multiplier=1.2",
    "pos_size_usd=50.0",
    "sizing=slbps q=0.01 sl_bps=50 m_regime=1.2 kappa=1.0"
  ],
  "dto_version": "1.0.0",
  "schema_ref": "trade_intent_v1.json"
}
```

### Field Reference

#### Core Order Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instrument` | string | ✅ | Trading pair symbol (e.g., "BTCUSDT") |
| `side` | enum | ✅ | Trade direction: "buy" or "sell" |
| `order.qty` | string | ✅ | Order quantity (string-encoded Decimal) |
| `order.price` | string | ✅ | Limit price (string-encoded Decimal) |
| `order.price_ref` | string | ✅ | Reference price for calculations |
| `order.reduce_only` | boolean | ✅ | Always false for new positions |

#### Risk Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `p` | string | ✅ | Win probability estimate [0.0-1.0] |
| `payoff_ratio_r` | string | ✅ | Reward-to-risk ratio |

#### TCA Budget

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tca_budget.max_slippage_bps` | string | ✅ | Max slippage in basis points |
| `tca_budget.max_latency_ms` | integer | ✅ | Max execution latency (ms) |
| `tca_budget.maker_preference` | string | ✅ | "neutral", "maker", or "taker" |

#### Risk Budget

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `risk_budget.trade_cvar95_max_bps` | string | ✅ | Max 95% CVaR per trade (bps) |
| `risk_budget.session_cvar95_max_bps` | string | ✅ | Max 95% CVaR per session (bps) |

#### Size Constraints

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `size.kelly_fraction` | string | ✅ | Kelly criterion fraction [0.0-1.0] |
| `size.notional_cap_usd` | string | ✅ | Max notional value in USD |

#### Metadata

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `valid_for_ms` | integer | ✅ | Validity duration (milliseconds) |
| `why` | array[string] | ✅ | Decision reasoning chain |
| `dto_version` | string | ✅ | Semver format (e.g., "1.0.0") |
| `schema_ref` | string | ✅ | JSON Schema reference |

### Why Chain Examples

```json
// Signal-based decision
["signal_score=0.85", "regime=TREND_UP", "multiplier=1.2"]

// Position sizing explanation
["sizing=slbps", "q=0.01", "sl_bps=50", "m_regime=1.2", "kappa=1.0"]

// Kelly-based sizing
["kelly_fraction=0.1", "probability=0.55", "payoff=2.0"]

// Risk-limited sizing
["capped_by_liquidity", "notional_cap=1000.0", "original=1500.0"]
```

---

## EVT:ALPHA_SCORES_AGGREGATED

### Description
Emitted when decision_making aggregates local alpha_registry scores for a symbol and exports the result as monitoring telemetry.

### Schema Reference
`schemas/alpha_scores_aggregated_v1.json` (JSON Schema 2020-12)

### Payload Structure

```json
{
  "symbol": "BTCUSDT",
  "scores": [
    {
      "model_name": "momentum",
      "score": 0.72,
      "confidence": 0.85,
      "timestamp": 1732900000000
    },
    {
      "model_name": "mean_reversion",
      "score": -0.15,
      "confidence": 0.62,
      "timestamp": 1732900000000
    }
  ],
  "timestamp": 1732900000000
}
```

---

## CMD:CLOSE (ROI Exit Strategy)

### Description
Emitted by `ROIExitStrategy` when a position's ROI exceeds the target threshold.

### Payload Structure

```json
{
  "symbol": "BTCUSDT",
  "reason": "ROI_TARGET_MET",
  "roi": 0.52,
  "target_roi": 0.50,
  "reduce_only": true
}
```

### Message Envelope

```python
Message(
    op="CMD",
    verb="CLOSE",
    src="decision_making",
    dst="execution_position",
    rid="correlated-rid",
    why="roi_target_met_0.52",
    pld={...}
)
```

---

## EVT:STRATEGY_DECISION_BLOCKED

### Description
Emitted when a strategy signal is generated but blocked by safety gates (Risk, QoS, Feature Readiness).

### Schema Reference
`schemas_decision_blocked.py` (Pydantic Model)

### Payload Structure
```json
{
  "symbol": "BTCUSDT",
  "stage": "on_features.risk_gate",
  "ts_ms": 1732900000000,
  "reason_code": "NRR-RISK-SCORE-HIGH",
  "reason": "Risk score 0.85 exceeds max 0.8",
  "path": "risk_parameters.score",
  "why": "risk_score_limit"
}
```

---

## Consumed Events

### EVT:FEATURES_CALCULATED

**Source**: `feature_engineering`

```json
{
  "symbol": "BTCUSDT",
  "ts": 1732900000000,
  "features": {
    "price": "50000.0",
    "volume_24h": "1000000000",
    "volatility": "0.02",
    "spread_bps": "5"
  }
}
```

### EVT:RISK_ASSESSMENT_COMPLETED

**Source**: `risk_management`

```json
{
  "symbol": "BTCUSDT",
  "risk_parameters": {
    "is_trading_allowed": true,
    "risk_score": "0.35",
    "max_position_size_usd": "10000"
  }
}
```

### EVT:PORTFOLIO_STATE_UPDATED

**Source**: `position_tracking`

```json
{
  "equity": "100000.0",
  "equity_free_usdt": "80000.0",
  "equity_cross_usdt": "100000.0",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "positionAmt": "0.1",
      "entryPrice": "48000.0",
      "unRealizedProfit": "200.0",
      "leverage": "10"
    }
  ]
}
```

### EVT:REGIME_DETECTED

**Source**: `regime_detector`

```json
{
  "symbol": "BTCUSDT",
  "regime": "TREND_UP",
  "confidence": 0.85,
  "timestamp": 1732900000000
}
```

---

## Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EVENT FLOW                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  EVT:FEATURES_CALCULATED ──────┐                                    │
│                                │                                    │
│  EVT:RISK_ASSESSMENT_COMPLETED─┼──► on_features()                   │
│                                │    on_risk()                       │
│  EVT:PORTFOLIO_STATE_UPDATED ──┼──► on_portfolio()                  │
│                                │                                    │
│  EVT:REGIME_DETECTED ──────────┘──► on_regime()                     │
│                                                                     │
│                                │                                    │
│                                ▼                                    │
│                    _check_and_trigger_decision()                    │
│                                │                                    │
│                                ▼                                    │
│                    _make_decision_for_symbol()                      │
│                                │                                    │
│              ┌─────────────────┼─────────────────┐                  │
│              ▼                 ▼                 ▼                  │
│        QoS Check        Signal Eval       Position Sizing           │
│              │                 │                 │                  │
│              └─────────────────┼─────────────────┘                  │
│                                │                                    │
│              ┌─────────────────┼─────────────────┐                  │
│              ▼                 ▼                 ▼                  │
│         APPROVED          DEFERRED          REJECTED                │
│              │                 │                 │                  │
│              ▼                 ▼                 ▼                  │
│    EVT:TRADE_INTENT    schedule_once()    log(NRR code)            │
│       _PROPOSED                                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Consumer Actions

When processing `EVT:TRADE_INTENT_PROPOSED`, downstream domains should:

1. **Validate** intent against current market conditions
2. **Check** portfolio state and risk limits
3. **Route** to appropriate execution venue
4. **Monitor** TCA budget compliance
5. **Log** execution attempts and outcomes

### Error Handling

If intent cannot be processed:
- Emit rejection events with NRR codes
- Update QoS state for blocked intents
- Log comprehensive rejection reasons
- Trigger risk alerts if thresholds exceeded

### Monitoring Metrics

| Metric | Description |
|--------|-------------|
| `intent_acceptance_rate` | Approved / Total |
| `intent_processing_latency_p95` | 95th percentile latency |
| `rejection_reason_distribution` | NRR code breakdown |
| `qos_control_effectiveness` | Blocked by QoS / Total |
| `why_chain_completeness` | WHY fields populated |
