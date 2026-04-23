# R7B SIDECAR RUNTIME DECISION

**Package**: R7B - Peak-Giveback Sidecar Runtime Observation Audit
**Date**: 2026-04-23

## Decision

The observed runtime slice is sufficient to prove that the Position Policy Sidecar is active after restart, that the standard evaluated/scoring path runs on real open lifecycles, and that the Sidecar suppresses safely under terminal ambiguity, stale-data boundaries, no-lifecycle boundaries, and post-close reconciliation.

The same slice is **not** sufficient to prove that the new peak-giveback path is behaving correctly at the trigger level. The decisive blockers are:

- no runtime proof of loaded `peak_giveback_close` config values
- no valid `mark_price` / `unrealized_pnl_usdt` / `unrealized_pnl_pct` in evaluated payloads
- no arming or threshold-crossing markers
- no observed `POSITION_POLICY_SIDECAR_RECOMMENDED` or `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`

## What Is Proven

- Sidecar activation after restart
- Standard sidecar evaluation on live open lifecycles
- Safe suppressions under terminal ambiguity and post-close cleanup
- No observed sidecar-owned execution, no duplicate action storm, and no recommendation spam in the bounded slice

## What Is Not Proven

- crossing of the 25 USDT arm threshold
- computation of giveback from a real runtime peak
- crossing of the 50 percent giveback trigger threshold
- emission of a peak-giveback recommendation or close request in the bounded slice

## Blocking Reason Cluster

`economic observability gap`

## Final Conclusion

This audit cannot honestly conclude that the new peak-giveback path is behaving correctly in live/testnet operation from the available runtime evidence alone. The defensible bounded-runtime conclusion is fail-closed:

- active and safe sidecar behavior: proven
- peak-giveback-specific correctness: unproven

UNKNOWN_INSUFFICIENT_EVIDENCE
