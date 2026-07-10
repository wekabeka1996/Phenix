# Symbol Ownership And Authority

Configured ownership:

- `api_agent_01` / agent 1: `ETHUSDT`, `SOLUSDT`
- `cli_agent_01` / agent 2: `XRPUSDT`, `BNBUSDT`

Each assignment becomes a renewable session lease. Command recording checks configured owner, matching agent number, unexpired lease, and portfolio emergency-stop state under the same session lock.

Wrong-symbol, missing-lease, expired-lease, and emergency-stop requests fail closed. A valid request remains `pending_fsm`; P41X cannot accept or execute it. The existing FSM remains lifecycle and sizing authority through the referenced intent/config surfaces.
