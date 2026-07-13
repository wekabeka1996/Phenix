# Testnet Canonical Proof

## FACTS

```yaml
canonical_proof:
  symbol: DOGEUSDT
  session_id: p46-1g-s1-63abba72bb42
  participant_id: p46-1g-s1-63abba72bb42-main
  lease_id: p46-1g-s1-63abba72bb42-lease-DOGEUSDT
  client_intent_id: p46-1g-r-intent-cc5fc10f2153470e
  sizing_decision_id: sizing:p46-1g-r-intent-cc5fc10f2153470e
  exposure_decision_id: exposure:p46-1g-r-intent-cc5fc10f2153470e
  exposure_decision_id_capture: deterministic reconstruction; bus snapshot field was null
  config_version: p46-1e-v1
  reference_price: 0.072230 USDT/DOGE
  target_notional: 11.0 USDT
  operator_cap: 20.0 USDT
  derived_quantity: 152 DOGE
  derived_notional: 10.978960 USDT
  tcp_envelopes: 1
  command_handler_calls: 1
  opening_async_dispatch_calls: 1
  cleanup_async_dispatch_calls: 1
  total_async_dispatch_calls: 2
  fsm_handle_calls: 1
  adapter_submit_calls: 1
  exchange_order_id: 1560242837
  opening_status: NEW
  executed_quantity: 0
  duplicate_submit_count: 0
  cleanup_path: canonical_cancel_unfilled
  final_position: 0
  final_open_orders: 0
  reconciliation_divergence: 0
```

- Endpoint: `testnet.binancefuture.com`.
- The original caller payload contained no quantity/notional/leverage/margin fields.
- Existing canonical `LeverageService` was attached to the same FSM/adapter; no skipped live leverage path was accepted.
- No direct adapter success path or emergency containment was used.

## INFERENCES

- The order reached the venue through the canonical V2/TCP/registry/FSM/adapter path exactly once.

## ASSUMPTIONS

- Opening executed quantity was zero because venue status remained `NEW` before canonical cancellation and final position was zero.

## UNKNOWNS

- Filled-order close branch remains untested.
