# Decision Making Flow Diagram

```mermaid
flowchart TD
    A[FEATURES_CALCULATED] --> B{features_ready?}
    B -->|No| C[DEFER: features_stale<br/>log: why=features_not_ready]
    B -->|Yes| D{Risk Assessment Ready?}

    D -->|No| E[DEFER: risk_missing]
    D -->|Yes| F{Portfolio Fresh?}

    F -->|No| G[DEFER: portfolio_stale]
    F -->|Yes| H{QoS Allow?}

    H -->|No| I[DEFER: qos_defer<br/>log: cooldown_left_ms, rate_state, code=NRR-012]
    H -->|Yes| J{Trading Allowed?}

    J -->|No| K[BLOCK: risk_gate_block<br/>log: gate=daily_drawdown|score|budget]
    J -->|Yes| L{Signal Valid?}

    L -->|No| M[BLOCK: neutral_signal]
    L -->|Yes| N{Regime Filter?}

    N -->|No| O[BLOCK: regime_filter]
    N -->|Yes| P{Position Size Valid?}

    P -->|No| Q[BLOCK: sizing_invalid]
    P -->|Yes| R[TRADE_INTENT_PROPOSED]

    R --> S[BRIDGE: Convert to CMD:OPEN<br/>log: exec_open_enter]
    S --> T[EXECUTION FSM]

    C --> U[Retry on next features]
    E --> U
    G --> U
    I --> V[Retry after cooldown]
    V --> H

    classDef defer fill:#ffeb3b
    classDef block fill:#f44336
    classDef success fill:#4caf50
    classDef log fill:#2196f3

    class C,E,G,I defer
    class K,M,O,Q block
    class R,S,T success
    class C,I,K log
```

## Key Decision Points

1. **Features Freshness**: `lag_ms <= ttl_ms` (default 30s)
2. **QoS Gates**: Rate limit (6/min), symbol cooldown (3s), exposure block (10s)
3. **Risk Gates**: Daily drawdown     10%, risk_score     threshold, trading_allowed = true
4. **Signal Gates**: Combined score > threshold, regime alignment
5. **Sizing Gates**: Position size within min/max limits

## Instrumentation Points

- **Features stale**: `{symbol, rid, now_ts, last_features_ts, lag_ms, ttl_ms, why="features_not_ready"}`
- **Risk block**: `{gate: 'daily_drawdown'|'score', value, threshold, why="risk_gate_block"}`
- **QoS defer**: `{cooldown_left_ms|rate_state, code:'NRR-012', why="qos_defer"}`
- **Execution enter**: `{rid, symbol, side, qty, clientOrderId, exposure_reservation_state, why="exec_open_enter"}`

## NRR Codes Used

- **NRR-011**: EXPOSURE_LIMIT_EXCEEDED (exposure block)
- **NRR-012**: RATE_LIMIT_EXCEEDED (cooldown/rate limit)
