# Pure Exposure Preview

## FACTS

`ExposureGuard.can_open(symbol, notional_usd, portfolio_state, ...)` performs soft-clip and hard exposure evaluation without calling `reserve()`. Reservation mutation is isolated in `ExposureGuard.reserve()`.

This is the correct reuse candidate; no duplicate formula is required.

## Blocker

Parity proof cannot be completed until dry-run receives the same authoritative portfolio snapshot, config version, symbol leverage/instrument truth, and lifecycle exposure state as the live FSM. Those identity-bearing readers are currently unavailable.

No policy was weakened and no production clip minimum was changed.
