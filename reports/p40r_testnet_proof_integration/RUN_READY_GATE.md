# Run Ready Gate

We evaluated the integrated runtime MVP to perform the single order testnet proof.

## STATUS: P40R_GATE_ONE_TESTNET_ORDER_ALLOWED

## Configuration Details
- **Integration Branch**: `p40-runtime-order-proof-integrated-primary-20260710`
- **HEAD Commit SHA**: `e443549be4d3d81b3793df6034e405a30a84e27f`
- **Merged Dependency SHAs**:
  - P40A Gate: `cae21e6443c7b3dd62bb22a420b925b34bc293d0`
  - P40B Capability: `02b63aa666ef11dcf8786016abefc787a718d7ef`
  - P40C Harness: `e28bda99e69e06180373df829fa5113d0774a36f`
- **Allowed Symbols**: `ETHUSDT` / `SOLUSDT`
- **Maximum Order Count**: `1`
- **Quantity/Notional Source**: `payload.qty` / `payload.quantity` / `payload.notional` (validated by `agent_action_audit.py` and capped at `25.0 USD` in `agent_authority_deepseek_testnet.yaml`).
- **Environment**: `testnet`
- **Mainnet**: `false`
- **Required no_order_observation_mode Value**: `False` (disabled only for this single-order proof runner process).
- **Expected Runner Branch**: `p40-runtime-order-proof-integrated-primary-20260710`
