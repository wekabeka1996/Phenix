# Trace Gating and System Risks

This document registers potential risks and limitations in the P40 order lifecycle harness.

---

## 1. Trace Verification Risks

### 1. Divergence of Shadow Mode Fills
* **Risk**: The harness tests testnet order submission against `ExchangeACL` configured in `shadow_mode=True`. In shadow mode, fills are simulated and ACKs are immediately returned. Live testnet endpoints may experience network timeouts, order rejection based on margin constraints, or API rate limit blocks that shadow mode does not capture.
* **Mitigation**: Once the P40A gate is opened, the harness will require real testnet executions with direct exchange API connections.

### 2. Trace Logging Thread-Safety
* **Risk**: Writing to `.agent_memory/order_lifecycle_traces.jsonl` from multiple parallel agent threads concurrently without file locks could cause corrupted or overlapping lines.
* **Mitigation**: Keep orders rate-limited according to the MVP cadence rules (30-second interval, no scalping, minimal order rate).

### 3. Replay Integrity on Crash
* **Risk**: If the uvicorn server reboots midway through an order trace lifecycle, the memory reflection or trace file might be missing the final exchange ACK/reject status.
* **Mitigation**: FSM status remains recorded/submitted until ACK is received; observers can query exchange APIs to reconcile state.
