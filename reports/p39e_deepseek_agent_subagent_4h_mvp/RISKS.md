# Risks (P39E MVP Resumed)

## 1. Simulated vs Live Execution Divergence
- **Risk**: Since the FSM is locked in `no-order observation mode`, live network latency, exchange API rate limits, or margin/leverage errors could not be fully tested in the real testnet environment.
- **Mitigation**: The `FSMHandoffGateway` validation checks cover Pydantic/YAML constraints completely, ensuring that any future transitions to live execution will fail-closed on malformed or unauthorized parameters.

## 2. Scalping Drift
- **Risk**: Main agent decision loops might drift to sub-5m intervals if the local timer runs incorrectly.
- **Mitigation**: Locked down cadence rules inside `agent_cadence.py` staggered offsets by agent number, preventing rapid overlapping triggers.
