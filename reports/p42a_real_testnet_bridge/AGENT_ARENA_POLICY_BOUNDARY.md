# AGENT_ARENA_POLICY_BOUNDARY — Safe Strategy Bypass

This document describes how the Agent Arena mode separates external agent authority from internal system safety invariants.

---

## 1. Schema Configuration

The new Pydantic config model `AgentArenaConfig` is defined under `apps/reference/config_models.py` and merged at the root of `AuroraConfig`.

```yaml
agent_arena:
  enabled: true
  external_agents_enabled: true
  internal_strategy_decision_authority: false
  execution_environment: testnet
```

### Attributes:
- `enabled`: Activates the multi-agent sandbox execution bridge.
- `external_agents_enabled`: Permits external commands to inject trades directly.
- `internal_strategy_decision_authority`: Set to `false` to prevent internal strategy heuristics (such as Kelly sizing or alpha regimes) from overriding incoming decisions.
- `execution_environment`: Restricts executions to `testnet` or `sandbox`.

---

## 2. Active safety and coordination guards

While strategy-specific heuristics are disabled in Agent Arena mode to give external agents authority over entry and exit, all low-level infrastructure safety gates remain active and cannot be bypassed.

| Security Gate / Guard | Target File / Component | Behavior |
| :--- | :--- | :--- |
| **Mainnet Block** | [verify_handoff_safety](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py#L113) | Any command referencing a production domain base URL or `mainnet` environment raises `ValueError` immediately and is blocked. |
| **Quantity Validation** | [verify_handoff_safety](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py#L129) | Rejects trades missing explicit quantity/notional (or having non-positive values). |
| **Symbol Ownership** | [coordination_config.py](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/coordination_config.py) | Asserts that the calling agent lease matches the target symbol (e.g. XRPUSDT owned by CLI Agent 2, SOLUSDT owned by API Agent 1). |
| **Agent 1 Restricted Gate**| [agent_order_lifecycle_harness.py](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_order_lifecycle_harness.py) | Explicitly blocks Agent 1 (`api_agent_01`, `agent_number: 1`) from placing external testnet orders. |
| **Idempotency Protection** | [agent_order_lifecycle_harness.py](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_order_lifecycle_harness.py) | Deduplicates commands before crossing exchange boundaries via trace files. |
| **Tidy/Execution Guards**| [ExecPosFSM](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/execution_position/fsm.py) | Keeps portfolio exposure limits, precision alignment (`tick_size`, `step_size`), and tidy state gates fully operational. |
