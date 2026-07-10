# J6-S4 — Config SSOT Reconciliation

We resolved duplicated fields in `p42_dual_agent_mvp.yaml` by loading and merging them with properties defined in `collective_memory_config.yaml`.

## Parameter Mapping
- **Agent ID & Numbers**: Sourced from `agents[*].agent_id` and `agent_number` in `collective_memory_config.yaml`.
- **Symbol Ownership**: Sourced from `agents[*].symbols` (e.g. `ETHUSDT` and `SOLUSDT` mapped to `api_agent_01`).
- **Timers and Cadences**: Mapped directly from `timers` (heartbeat cadence, analysis cadence, sync seconds) in `collective_memory_config.yaml`.
- **LLM Parameters**: Left in `p42_dual_agent_mvp.yaml` (provider, model, instruction markdown path, timeout limits).
