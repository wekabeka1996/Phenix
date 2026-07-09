# Risks and Mitigations

We assessed the operational risks of opening the testnet order proof gate.

## Risk Assessment
1.  **Accidental Live/Production Fills**:
    - Risk: If the API keys point to live exchanges or the adapter base URL is misconfigured, real funds could be traded.
    - Mitigation: FSM guardrails verify that `"testnet" in self.adapter.base_url`. If any production domains (e.g. `fapi.binance.com`) are present, execution is instantly aborted.
2.  **Order Spam / Runaway Loop**:
    - Risk: The agent loop could place repeated orders.
    - Mitigation: `max_orders_per_session = 1` is strictly enforced at the gate config and FSM.
3.  **High Slippage / Erroneous Execution**:
    - Risk: Market order execution fills at unfavorable prices.
    - Mitigation: All agent order requests default to `LIMIT` type and are quantized to tick size precision before submission.
