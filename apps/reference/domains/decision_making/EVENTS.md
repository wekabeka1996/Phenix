# Decision Making Events

## EVT:TRADE_INTENT_PROPOSED

### Overview
The `EVT:TRADE_INTENT_PROPOSED` event is emitted by the DecisionMaking FSM when a trade intent has been successfully evaluated, approved through all QoS controls, and is ready for execution routing.

### Event Structure

```json
{
  "event_type": "EVT:TRADE_INTENT_PROPOSED",
  "payload": {
    "instrument": "string",
    "side": "buy|sell",
    "order": {
      "qty": "string",
      "price": "string",
      "price_ref": "string",
      "reduce_only": false
    },
    "p": "string",
    "payoff_ratio_r": "string",
    "tca_budget": {
      "max_slippage_bps": "string",
      "max_latency_ms": number,
      "maker_preference": "neutral|maker|taker"
    },
    "risk_budget": {
      "trade_cvar95_max_bps": "string",
      "session_cvar95_max_bps": "string"
    },
    "size": {
      "notional_cap_usd": "string",
      "kelly_fraction": "string"
    },
    "valid_for_ms": number,
    "why": ["string"],
    "dto_version": "string",
    "schema_ref": "string",
    "idempotent_key": "string"
  },
  "why": "trade_intent",
  "data_ref": ["string"]
}
```

### Field Descriptions

#### Core Order Fields
- **instrument**: Trading pair symbol (e.g., "BTCUSDT")
- **side**: Trade direction ("buy" or "sell")
- **order.qty**: Order quantity as string (e.g., "0.001")
- **order.price**: Limit price as string (e.g., "50000.0")
- **order.price_ref**: Reference price for calculations (e.g., "50000.0")
- **order.reduce_only**: Always false for new positions

#### Risk Parameters
- **p**: Win probability estimate (0.0-1.0) as string
- **payoff_ratio_r**: Reward-to-risk ratio (e.g., "2.0")

#### TCA Budget
Transaction Cost Analysis constraints:
- **tca_budget.max_slippage_bps**: Maximum allowed slippage in basis points
- **tca_budget.max_latency_ms**: Maximum execution latency in milliseconds
- **tca_budget.maker_preference**: Execution preference ("neutral", "maker", "taker")

#### Risk Budget
Portfolio risk constraints:
- **risk_budget.trade_cvar95_max_bps**: Max 95% CVaR per trade in basis points
- **risk_budget.session_cvar95_max_bps**: Max 95% CVaR per session in basis points

#### Size Constraints
Position sizing limits:
- **size.notional_cap_usd**: Maximum notional value in USD
- **size.kelly_fraction**: Kelly criterion fraction (0.0-1.0)

#### Metadata
- **valid_for_ms**: Intent validity duration in milliseconds
- **why**: Array of reasoning strings explaining the decision
- **dto_version**: Data transfer object version
- **schema_ref**: JSON Schema reference
- **idempotent_key**: UUID for duplicate prevention

### Why Chain Examples

The `why` array contains decision reasoning in structured format:

```json
[
  "signal_score=0.85",
  "regime_multiplier=1.2",
  "pos_size_usd=50.0",
  "sizing=slbps q=0.01 sl_bps=50 m_regime=1.2 kappa=1.0"
]
```

### Event Flow

1. **Signal Evaluation**: Alpha signals aggregated and scored
2. **Regime Filtering**: Trade direction validated against market regime
3. **QoS Checks**: Symbol cooldown, rate limits, exposure controls
4. **Position Sizing**: Risk-based quantity calculation
5. **Intent Creation**: Trade intent DTO assembled
6. **Event Emission**: EVT:TRADE_INTENT_PROPOSED emitted to FSM

### Consumer Actions

Execution domains should:
1. Validate intent against current market conditions
2. Check portfolio state and risk limits
3. Route to appropriate execution venue
4. Monitor TCA budget compliance
5. Log execution attempts and outcomes

### Error Handling

If intent cannot be processed:
- Emit rejection events with NRR codes
- Update QoS state for blocked intents
- Log comprehensive rejection reasons
- Trigger risk alerts if thresholds exceeded

### Monitoring

Key metrics to track:
- Intent acceptance rate
- Average processing latency
- Rejection reason distribution
- QoS control effectiveness
- Why chain completeness</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\EVENTS.md
