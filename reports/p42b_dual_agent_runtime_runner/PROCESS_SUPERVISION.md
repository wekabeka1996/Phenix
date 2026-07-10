# Process Supervision

This document defines the process supervision mechanisms, heartbeat checks, and crash recovery behaviors.

---

## 1. Process Controls

The runner exposes controls to manage agent tasks independently:
- **start_agent(agent_id)**: Spawns the async loop task for the specified agent.
- **pause_agent(agent_id)**: Suspends turn executions by transitioning status to `"paused"`.
- **stop_agent(agent_id)**: Cancels the running task and changes status to `"stopped"`.
- **stop_session()**: Stops all agents and unhooks FSM listeners.

---

## 2. Heartbeats and Stale Expiring

- **Emitting**: Each agent task appends an `AGENT_HEARTBEAT` event to the `SessionStore` at `heartbeat_cadence_sec` intervals.
- **Monitoring**: The supervisor monitors the `last_heartbeat` timestamp. If an agent does not update its heartbeat within a set stale timeout threshold (typically `heartbeat_cadence_sec * 3`), the runner flags it as failed.

---

## 3. Failure Isolation and Recovery

- **Crash Isolation**: If an agent process crashes (uncaught exception in turn or network loop), its task is caught by the supervisor, its state is set to `"failed"`, and a failure notification is logged.
- **No Cascade**: The failure of one agent (e.g. `api_agent_01`) does not affect the execution of the other agent (e.g. `cli_agent_01`), which continues its cadence loop normally.
- **Failsafe Gating**: No silent restarts are performed. Failed agents remain stopped until explicit operator intervention, preventing duplicate command issuances.
