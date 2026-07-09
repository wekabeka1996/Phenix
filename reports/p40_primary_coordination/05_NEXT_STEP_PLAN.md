# P40 Next Step Plan

## FACTS

- P40A gate report now exists on `origin/p40-testnet-order-proof-integrated-primary-20260709`.
- P40E runner previously blocked because it did not see that branch/gate at runtime.
- No order submit, ACK/reject, or fill evidence exists.

## INFERENCES

- The next safe step is a rerun of the external proof runner after synchronizing gate and adapter/harness branches.

## ASSUMPTIONS

- The rerun must remain limited to one tiny ETHUSDT or SOLUSDT testnet order.
- The rerun must use existing adapter/FSM path only.

## UNKNOWNS

- Whether the runner will pass gate checks after branch synchronization.

## Proposed Sequence

1. Publish/merge P40A, P40B, and P40C into one integration branch.
2. Verify `RUN_READY_GATE.md` or equivalent run-ready spec is visible to the runner.
3. Rerun external proof with exactly one tiny testnet order.
4. Capture exchange ACK/reject as the minimum proof.
5. Capture fill only if exchange produces one; do not simulate.
6. If blocked, preserve `ORDER_SUBMIT_BLOCKED` reason and stop.
