# 05 Current P42 Runtime Chain

This report maps the actual current P42 execution pipeline.

## 1. P42 Runtime Imports and Invocations

### Dependencies
- **tools/deepseek-terminal-agent**: **DIRECTLY IMPORTED AND INVOKED**. The P42 supervisor (`DualAgentRuntimeRunner` in `dual_agent_runner.py`) directly imports config loading, session stores, and pydantic models from `deepseek_terminal_agent.*`.
- **deepseek-agent-os (10)**: **NEITHER IMPORTED NOR INVOKED**. There are no references, package linkages, or imports referencing `deepseek-agent-os` or folders outside of the Phenix worktree.

---

## 2. Execution Pipeline

```
  Model Invocation (DeepSeek API call)
  → Agent Decision (WAIT / SKIP / REQUEST_ORDER)
  → Session Memory Write (.agent_memory/sessions/<session_id>/events.dsctx.jsonl)
  → FSM Command Registration (EVT:STRATEGY_SIGNAL_PRODUCED emitted via FSM)
  → Preflight check (shadow mode check, size validation, lease match)
  → BinanceAdapter call (REST API request to https://testnet.binancefuture.com)
  → Testnet execution (FSM processes ACK, fill or cancellation)
```

### Segment A: Model Invocation
- The `DualAgentRuntimeRunner` calls `_get_agent_decision`, which compiles the `AgentTurnContextEnvelope` and invokes the model.

### Segment B: Session Memory Write
- Writes are persisted append-only inside `.agent_memory/` local to the worktree to ensure state reconciliation.

### Segment C: FSM Command Registration & Adapter Call
- The runner emits events via the FSM (`fsm.emit(...)`). The FSM acts as the single execution gateway, checking risk parameters before routing commands to `BinanceAdapter` REST endpoints.
