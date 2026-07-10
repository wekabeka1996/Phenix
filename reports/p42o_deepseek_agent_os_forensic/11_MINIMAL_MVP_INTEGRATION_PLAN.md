# 11 Minimal MVP Integration Plan

This plan details the steps required to execute the dual-agent MVP run using the recommended Option D standalone Phenix runtime architecture.

## 1. Step-by-Step Implementation

### Step 1: Prestart Validations
- Verify `.env` credentials (`BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`).
- Verify no unresolved orders or active positions on `XRPUSDT`, `BNBUSDT`, `ETHUSDT`, or `SOLUSDT` (using `check_positions.py` script).
- Reconcile margin modes to `ISOLATED` and target leverages to `20` on the exchange for all target symbols.

### Step 2: Configure Workspace settings
- Edit `config/p42_dual_agent_mvp.yaml` to specify agent parameters (staggers, cadences, and session durations).
- Ensure `RUN_READY_GATE.md` contains the active `Integration SHA` corresponding to the HEAD commit.

### Step 3: Launch Dual-Agent Session
- Run the supervisor via the console:
  `python tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/dual_agent_runner.py`
  (or run the runner script if wrapped).
- Verify heartbeats are emitted to `.agent_memory/sessions/<session_id>/events.dsctx.jsonl`.

### Step 4: Verification and Audit
- Monitor FSM trace records to confirm correct command propagation.
- Validate that no order quantity is decided by the models.
