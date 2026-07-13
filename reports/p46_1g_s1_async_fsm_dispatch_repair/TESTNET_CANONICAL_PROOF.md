# Testnet Canonical Proof

## FACTS

```yaml
testnet_attempt:
  endpoint: testnet.binancefuture.com
  symbol: DOGEUSDT
  opening_intents: 1
  caller_quantity_present: false
  http_status: 202
  derived_quantity: "138"
  fsm_guard_result: SOFT_LIMIT_BELOW_CLIP_MIN
  adapter_submit_calls: 0
  venue_order_identity: null
  second_opening_intent_sent: false
  direct_adapter_bypass_used: false
```

- The account, server time, book, position, and open-order reads used Binance Futures Testnet.
- The exact `10.0` USDT target was lot-rounded below the configured exposure guard's `10` USDT clip minimum.
- The guard rejected before async adapter submission. The script then failed with `canonical adapter submit did not complete`.
- Signed query parameters in the local stderr evidence were replaced with `[REDACTED]` before reporting.

## INFERENCES

- The Testnet run exercised the canonical path through FSM guard evaluation but did not exercise the repaired async adapter dispatch.

## ASSUMPTIONS

- The observed Testnet account response was authoritative at query time.

## UNKNOWNS

- Venue submit ACK, order status lifecycle, cancel/close, and exchange reconciliation through the canonical path remain unknown.
