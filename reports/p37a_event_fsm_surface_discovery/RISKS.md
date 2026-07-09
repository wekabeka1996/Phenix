# Risks and Recommendations

We audited the proposed execution boundary integration surface.

## Identified Risks
1.  **Direct execution bypass**:
    - Risk: If agent-facing code bypasses FSM gates and speaks directly to `BinanceWSClient` or the execution adapter, orders could be submitted without operator reviews or logs.
    - Recommendation: Enforce strict boundaries. Keep the adapter private to FSM, and allow agent actions only via signed `CMD` event envelopes.
2.  **No-Order Observation Mode misconfiguration**:
    - Risk: If `no_order_observation_mode` is accidentally set to False during testnet validation, autonomous trade intents could trigger actual testnet exchange fills.
    - Recommendation: Ensure test configurations assert `no_order_observation_mode = True` explicitly in test environments.
