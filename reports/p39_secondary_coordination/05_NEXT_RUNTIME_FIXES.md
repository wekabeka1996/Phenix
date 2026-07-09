# 05_NEXT_RUNTIME_FIXES.md

## Actions to Move from Observation Mode to Live Testnet Execution

The MVP runner successfully executed in observation mode. To transition to a live testnet run (generating actual orders on the exchange server), the following tasks must be resolved in the next iteration:

1. **Verify Live Testnet Network Latency & Connectivity**:
   - In observation mode, network edge cases are bypassed. Live tests will require loading the Binance testnet endpoint secrets and initializing the adapter connection in a secure sub-process.
   
2. **Implement Preflight Slippage and Quantity Normalizer**:
   - Verify that quantity/notional values received from the agent are dynamically normalized to the exchange's minimum filters (leveraging the P37E invariants/P36E contracts) before sending the payload.

3. **Transition the Gate Status to Live**:
   - Update the `RUN_READY_GATE.md` configuration from `NO_ORDER_ONLY` to `LIVE_TESTNET_ENABLED`, ensuring that the `FSMAuditRegistry` permits status transitions to `submitted_testnet` and `exchange_ack`.
