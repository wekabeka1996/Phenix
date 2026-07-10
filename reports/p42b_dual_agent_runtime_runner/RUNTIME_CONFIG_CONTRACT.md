# Runtime Configuration Contract

This document specifies the YAML and Pydantic configuration schema constraints for the P42 Dual-Agent MVP.

---

## 1. Config Object Schema

The configuration file is loaded from `config/p42_dual_agent_mvp.yaml` and parsed using the `DualAgentMVPConfig` model:

```json
{
  "agents": {
    "api_agent_01": {
      "agent_id": "api_agent_01",
      "agent_number": 1,
      "runtime_kind": "api",
      "symbols": ["ETHUSDT", "SOLUSDT"],
      "provider": "deepseek",
      "model": "deepseek-v4-pro",
      "instruction_files": ["config/instructions_api_agent_01.md"],
      "market_refresh_cadence_sec": 30,
      "analysis_cadence_sec": 60,
      "response_timeout_sec": 15,
      "retry_count": 3,
      "heartbeat_cadence_sec": 10,
      "collective_publication_cadence_sec": 120,
      "portfolio_sync_cadence_sec": 60,
      "reflection_cadence_sec": 180,
      "session_duration_sec": 3600,
      "max_pending_commands": 5,
      "testnet_order_limits": {
        "max_orders": 10,
        "max_notional": 50.0
      },
      "startup_stagger_sec": 5,
      "shutdown_behavior": "graceful"
    }
  }
}
```

---

## 2. Invariants & Rules
- **No Hidden Defaults**: Every field listed must be present in the configuration file; default values inside Python are strictly forbidden.
- **Symbol Exclusivity**: Symbol ownership lists must be completely non-overlapping. Overlapping symbols are caught during preflight checks.
- **Cadence Timeframes**: All intervals and cadences are configured in seconds.
