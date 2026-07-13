# P46-1G-S2 Coordination Report

## FACTS

- Base: `5bd3c81b2020d917f0e4627261aae3ac35bf65ff` on the canonical branch.
- Root cause: hidden active fee buffer plus pre-buffer proof projection (`CONFIG_SSOT_INCOHERENCE`).
- Fee buffer and snapshot age are now explicit SSOT; production clip floor remains 10 USDT.
- One Testnet DOGEUSDT order (`1560242837`) was submitted through V2/TCP/one FSM/canonical adapter and canceled through canonical `DEC:CANCEL_ORDER`.
- Duplicate submits `0`; final position `0`; final open orders `0`; divergence `0`; emergency/direct fallback `false`.
- Independent venue query confirmed `CANCELED` and flat state.

## INFERENCES

- P46-1G venue lifecycle proof is now complete for the unfilled/cancel branch.

## ASSUMPTIONS

- Filled close behavior remains a later package concern.

## UNKNOWNS

- Exposure ID direct capture timing and filled lifecycle remain residuals.

## Verdict

`P46_1G_CANONICAL_TESTNET_LIFECYCLE_VALIDATED`
