# 05_NEXT_RUNTIME_FIXES.md

## Steps to Unblock the P40 Testnet Order Proof

1. **Publish Primary Integration Branch (`P40A`)**:
   - The primary coordinator must complete the integration tasks and push `origin/p40-testnet-order-proof-integrated-primary-20260709` containing the necessary preflight validators and `RUN_READY_GATE.md`.
2. **Fetch and Merge**:
   - Once published, the secondary runner branch must pull and merge the primary integration branch to ingest the gate instructions.
3. **Execute Order Proof**:
   - Set the runtime gate to authorize a single tiny testnet order and verify the exchange ACK response.
