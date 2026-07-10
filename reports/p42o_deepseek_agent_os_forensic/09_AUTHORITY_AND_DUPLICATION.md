# 09 Authority and Duplication Analysis

This report maps component authorities and active duplications.

## 1. Component Authority Mapping

| Area | Owner / Active Component | Role / Authority |
|---|---|---|
| **Operator UI** | Target A (`deepseek-agent-os`) | Direct browser interactive panel. |
| **API-Agent Model Calls** | Target C (P42 runner in worktree) | Executes actual LLM requests at run-time. |
| **CLI-Agent Process** | Target C (P42 runner in worktree) | Spawns and manages CLI execution. |
| **Session Creation** | Target C (P42 runner in worktree) | Initiates the durable workspace folder. |
| **Timers & Schedulers** | Target C (P42 runner in worktree) | Handles turn cadence and heartbeats. |
| **Prompt Construction** | Target C (P42 runner in worktree) | Assembles system/user prompts. |
| **Instruction Versions** | Target C (P42 runner in worktree) | Acknowledges instruction version file paths. |
| **Private Memory** | Target C (P42 runner in worktree) | Appends to local JSONL files. |
| **Collective Memory** | Target C (P42 runner in worktree) | Appends to local JSONL files. |
| **FSM Handoff** | Target C (P42 runner in worktree) | Submits intents directly to Phenix FSM. |
| **Execution Lifecycle** | Phenix FSM | Single order lifecyle authority. |

---

## 2. Duplication Audit

### Duplication 1: Two Cockpit Servers
- **Description**: Target A hosts an Express backend on port `3000`. Target B hosts a FastAPI server on port `8787` (dashboard).
- **Classification**: **ACTIVE_DUPLICATION**. Both try to manage sessions, events, attachments, and approvals. Target A acts as a proxy wrapper, forwarding files/command queries to the local bridge daemon which redirects to the active workspace.

### Duplication 2: Two Session Stores
- **Description**: Target A has `.agent_workspace/runtime_store/sessions.json` and SQLite tables. Target B has `.agent_memory/sessions/` directory.
- **Classification**: **ACTIVE_DUPLICATION**. Target A stores sessions in JSON/SQLite locally under `C:\Users\user\Music\deepseek-agent-os (10)`. Target B and Target C write session data to the active Phenix worktree `.agent_memory` directory.

### Duplication 3: Two Timer Loops
- **Description**: Target A's `PhenixTradingAgentService.ts` defines three `setInterval` loops. Target C's `DualAgentRuntimeRunner` defines `asyncio` loop tasks.
- **Classification**: **STALE_CODE**. Target A's timers are inactive because the service is disarmed and hasn't been run since May 2026. Target C's loops are actively executed during runtime sessions.

### Duplication 4: Two Command Ledgers
- **Description**: Target A has `trading_dispatches` table. Target B/C has `order_lifecycle_traces.jsonl`.
- **Classification**: **STALE_CODE** (Target A) / **ACTIVE_DUPLICATION** (Target B/C).
