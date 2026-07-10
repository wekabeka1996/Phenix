# 03 — Agent Runtime Matrix

This document outlines the per-agent runtime parameters, lease ownership boundaries, and task execution loops.

---

## 1. Symbol Boundaries & Identity Leases

Symbol ownership is strictly segregated to prevent race conditions or cross-symbol authority violations:

- **Agent 1 (API Agent)**: `api_agent_01` (agent_number: 1). Interface kind: `api`.
  - **Owned Symbols**: `ETHUSDT`, `SOLUSDT`
- **Agent 2 (CLI Agent)**: `cli_agent_01` (agent_number: 2). Interface kind: `cli`.
  - **Owned Symbols**: `XRPUSDT`, `BNBUSDT`

The single-owner invariant is loaded from `collective_memory_config.yaml` and enforced in `coordination_config.py`. Any attempt by an agent to trade a symbol outside its lease (e.g. Agent 2 trading SOLUSDT) is blocked by the runner's preflight check and returns `BLOCKED_POLICY`.

---

## 2. Loop Cadence & Timeout Parameters

Interval parameters are configured in seconds under `config/p42_dual_agent_mvp.yaml`:

| Cadence Loop / Timeout | Configured Value (Sec) | Details |
| :--- | :--- | :--- |
| **Market Refresh** | 30s | Updates tick price data caches. |
| **Agent Analysis** | 60s | Cadence for decision-making turns. |
| **Heartbeat Cadence** | 10s | Appends liveness events to state log. |
| **Portfolio Sync** | 60s | Queries balances and positions. |
| **Peer/Collective Sync** | 120s | Publishes state to collective ledger. |
| **Reflection Interval** | 180s | Post-trade memory review cadence. |
| **Response Timeout** | 15s | Max wait time for model generation. |

---

## 3. Liveness and Wakeups

- **Heartbeat Monitoring**: Agents emit a heartbeat event every 10 seconds. The runner checks liveness; if `last_heartbeat` age exceeds 30 seconds (`heartbeat_cadence_sec * 3`), the agent state is flagged as `"failed"`.
- **Event-Driven Wakeup**: Agents do not sleep blindly; they wake up immediately upon FSM event bus signals (e.g., `INSTRUCTIONS_REFRESHED`, `ORDER_RESULT`, `PANIC`, or `EXCHANGE_ERROR`).
- **Wait/Skip Loops**: When the model decides to take no action, it returns `WAIT`, and the loop yields control until the next cadence interval.
- **Subagent Routing**: Spawns specialized subagents (e.g. `ScoutAgent` for repo searches) via regex triggers on incoming operator queries, ensuring parent-thread safety.
