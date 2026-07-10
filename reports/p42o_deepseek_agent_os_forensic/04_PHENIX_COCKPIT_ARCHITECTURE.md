# 04 Phenix Cockpit Architecture

This report maps the architecture of `tools/deepseek-terminal-agent` inside Phenix.

## 1. Components and Entrypoints

### FastAPI Server (`dashboard/app.py`)
- **Port**: Listens on `DASHBOARD_PORT` (defaults to `8787`).
- **Role**: Serves as the REST API host for session state management, memory retrieval, instruction validation, and order routing.
- **Key Routes**:
  - `GET /health` and `GET /config-status`
  - `GET/POST /chat/sessions`
  - `POST /chat/sessions/{session_id}/agent-memory/identity`
  - `POST /chat/sessions/{session_id}/agent-memory/instruction-ack`
  - `POST /chat/sessions/{session_id}/agent-events/testnet-order-request` (routes testnet limit entries through the FSM).

### Dual-Agent Runner (`dual_agent_runner.py`)
- **Role**: Supervisors runtime ticks for both the API agent (`api_agent_01`) and CLI agent (`cli_agent_01`).
- **Preflight Guards**: Performs 10 safety checks before booting, including environment verification, unique symbols, instruction load check, FSM reachability, and attestation sha matching.
- **Loop**: Constructs turn contexts (`AgentTurnContextEnvelope`), executes model decision calls, and routes intents to the FSM.

### Order Lifecycle Harness (`agent_order_lifecycle_harness.py`)
- **Role**: Hardened gateway between the agent loop and FSM/exchange adapters.
- **Safety Blocks**: Rejects duplicate command IDs, enforces symbol lease boundaries, and blocks orders if shadow mode is false but credentials are empty.

### Durable Session Memory
- Backs session traces (`events.dsctx.jsonl` and `order_lifecycle_traces.jsonl`) inside `.agent_memory/sessions/<session_id>/`.
- Implements `AgentTradingSessionMemory` with strict identity and append-only constraints.
