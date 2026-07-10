# 05 — Memory and Publication Review

This document audits the session store memory structures and peer publication mechanisms.

---

## 1. Memory Store Isolation

- **Directory Separation**: Each agent runs turn execution loops with isolated directories on disk (e.g. separate folders under `.agent_memory/sessions/`).
- **Log Files**: Traces are written to distinct file paths:
  - Global log: `.agent_memory/order_lifecycle_traces.jsonl`
  - Session-specific log: `.agent_memory/sessions/<session_id>/order_lifecycle_traces.jsonl`
- **No Overwrites**: Because file names and parent directories are isolated and use distinct agent suffixes (e.g., `instructions_api_agent_01.md` and `instructions_cli_agent_01.md`), no cross-agent file overwrites are possible.

---

## 2. Database & State Claims

- **Current Runtime Only**: The database writes are limited strictly to append-only JSONL files (`order_lifecycle_traces.jsonl`) and sqlite `order_ledger.db` files.
- **No Overclaims**: We make no claim to the P41X Memory V2 database schemas. The Memory V2 integration is kept separate and is not activated or assumed to be completed for the P42 MVP.

---

## 3. Peer Publication Event Logs

- **Publication Event**: When an agent completes its turn, it can publish its results, emitting a `PEER_MESSAGE_PUBLISHED` or `COLLECTIVE_STATE_UPDATED` event to the FSM.
- **Liveness Wakeups**: Peer publications are intercepted by the other agent's FSM listeners, triggering an immediate event-driven wakeup. This permits immediate reaction to coordination events rather than waiting for analysis timers to expire.
