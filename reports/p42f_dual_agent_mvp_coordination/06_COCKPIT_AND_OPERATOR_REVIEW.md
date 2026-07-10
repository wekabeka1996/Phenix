# 06 — Cockpit and Operator Review

This document audits the cockpit interface, control actions, and local network binding parameters.

---

## 1. Cockpit Visuals & Status Indicators

The cockpit uvicorn server runs a dashboard app exposing the dual-agent projection at `/arena` and `/arena/runtime`. It validates:

- **Agent Visibility**: Both `api_agent_01` and `cli_agent_01` are rendered with their status (running, paused, stopped, failed).
- **Ownership Maps**: Symbol maps are clearly visible, illustrating that `ETH/SOL` are leased to the API agent and `XRP/BNB` are leased to the CLI agent.
- **Evidence Verification**: Renders color-coded badges indicating execution status (`REAL_EXTERNAL`, `SHADOW`, `STUB`, `TEST`, `BLOCKED`, `UNKNOWN`).
- **Kill Switch (Panic)**: The active status of the FSM panic kill switch is monitored and displayed in the main header.

---

## 2. Control Surfaces

Operator commands use `/arena/commands/{action}` POST requests to dispatch signals to the runner. The supported controls are:
- `pause_agent`, `resume_agent`, `stop_agent`, `stop_session`
- `trigger_analysis`, `instruction_refresh`
- `emergency_stop`

These events are safely written to the FSM bus and log ledgers but never execute direct raw exchange orders.

---

## 3. LAN Binding & Security

- **Safe Default**: Binds to localhost (`127.0.0.1:8787`) by default.
- **LAN Access**: Activating `-PrivateLan` binds the server to local private network interfaces (`0.0.0.0`) and verifies incoming requests against private RFC1918 subnets only. Wildcard binds and public host headers are strictly blocked to prevent unauthorized remote operations.
- **LAN Smokes**: Local uvicorn binds have been validated as successful, but remote LAN verification from secondary physical devices is unproven because no additional devices are connected to the testbed sandbox.
