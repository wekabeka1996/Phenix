# 08 — Next Step Plan

This document maps out the path for resolving baseline drift, merging functional branches, and executing live testnet transactions.

---

## 1. Branch Consolidation & Conflict Resolution

To merge the three isolated branches into the single release branch `p42-dual-agent-runtime-integrated-primary-20260710`:

1. **Rebase P42B**:
   - Rebase `p42b-dual-agent-runtime-runner-primary-20260710` onto `9af369b7` to align it with the P40R baseline commit, resolving any `AdapterCapability` schema changes.
2. **Merge P42A & P42B**:
   - Merge the execution bridge (`p42a`) and the runner (`p42b`) in a staging workspace. Run the joint test suite to ensure `verify_preflight` loads YAML config files and resolves `coordination_config.py` correctly.
3. **Merge P42C**:
   - Merge the cockpit view (`p42c`) into the staged build.
4. **Push Integration Release**:
   - Push the unified branch to origin and run the full 516 test suite.

---

## 2. Live Credential Testing (Phase 4 Validation)

To obtain real external execution proof:

1. **Testnet API Keys Provisioning**:
   - Obtain valid Binance USDS-M Futures Testnet API keys and secrets.
2. **Secure Environment Variables**:
   - Populate local `.env` files with `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET`.
3. **Run Harness Live Trace**:
   - Execute `run_lifecycle_trace` with `p40a_gate_allow_order_submit=True` for Agent 2 (`cli_agent_01`) trading `XRPUSDT`.
   - Assert that the response transitions from `BLOCKED_CONFIG` to `EXTERNAL_ACK` or `EXTERNAL_FILL`.
   - Verify that the resulting `orderId` is visible on the Binance Futures Testnet web dashboard.
4. **Teardown & Cleanup**:
   - Run the FSM exit cleanup and verify that the testnet position is flattened and no open orders remain.
