# Residuals

## FACTS

- `SOFT_LIMIT_BELOW_CLIP_MIN` blocks the exact 10 USDT proof after instrument lot rounding.
- `EVT:AGENT_TRADE_INTENT_V2_RECEIVED`, `EVT:AGENT_TRADE_INTENT_V2_SIZED`, and `ERR:OPEN` emitted registry schema deprecation warnings during the run.
- The original forensic script remains untracked and contains explicit direct adapter paths. It is retained as evidence and excluded from success proof.
- Existing non-S1 `asyncio.run()` usages remain outside the repaired command seam and were not broadly refactored.
- Full production service restart and real venue submit were not performed.

## INFERENCES

- A later, separately authorized package must reconcile proof target sizing with clip-min enforcement without adding hidden notional defaults.

## ASSUMPTIONS

- Registry warning cleanup is independent of the repaired dispatch ownership.

## UNKNOWNS

- Whether the approved sizing policy should target a representable notional at or above the clip floor requires operator/config authority.
