# Unified Patch Diff

This document holds the unified git diff of all modifications made to introduce the dual-agent runtime supervisor runner.

```diff
diff --git a/config/p42_dual_agent_mvp.yaml b/config/p42_dual_agent_mvp.yaml
new file mode 100644
index 00000000..c78a093b
--- /dev/null
+++ b/config/p42_dual_agent_mvp.yaml
@@ -0,0 +1,46 @@
+agents:
+  api_agent_01:
+    agent_id: "api_agent_01"
+    agent_number: 1
+    runtime_kind: "api"
+    symbols: ["ETHUSDT", "SOLUSDT"]
+    provider: "deepseek"
+    model: "deepseek-v4-pro"
+    instruction_files: ["config/instructions_api_agent_01.md"]
+    market_refresh_cadence_sec: 30
+    analysis_cadence_sec: 60
+    response_timeout_sec: 15
+    retry_count: 3
+    heartbeat_cadence_sec: 10
+    collective_publication_cadence_sec: 120
+    portfolio_sync_cadence_sec: 60
+    reflection_cadence_sec: 180
+    session_duration_sec: 3600
+    max_pending_commands: 5
+    testnet_order_limits:
+      max_orders: 10
+      max_notional: 50.0
+    startup_stagger_sec: 5
+    shutdown_behavior: "graceful"
+
+  cli_agent_01:
+    agent_id: "cli_agent_01"
+    agent_number: 2
+    runtime_kind: "cli"
+    symbols: ["XRPUSDT", "BNBUSDT"]
+    provider: "deepseek"
+    model: "deepseek-v4-pro"
+    instruction_files: ["config/instructions_cli_agent_01.md"]
+    market_refresh_cadence_sec: 30
+    analysis_cadence_sec: 60
+    response_timeout_sec: 15
+    retry_count: 3
+    heartbeat_cadence_sec: 10
+    collective_publication_cadence_sec: 120
+    portfolio_sync_cadence_sec: 60
+    reflection_cadence_sec: 180
+    session_duration_sec: 3600
+    max_pending_commands: 5
+    testnet_order_limits:
+      max_orders: 10
+      max_notional: 50.0
+    startup_stagger_sec: 5
+    shutdown_behavior: "graceful"
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/p42_config.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/p42_config.py
new file mode 100644
index 00000000..819283f2
--- /dev/null
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/p42_config.py
@@ -0,0 +1,41 @@
+"""Pydantic config schemas for the P42 dual-agent trading arena."""
+from __future__ import annotations
+
+import pathlib
+from typing import Dict, List, Literal
+import yaml
+from pydantic import BaseModel, ConfigDict, Field
+
+class TestnetOrderLimits(BaseModel):
+    model_config = ConfigDict(extra="forbid", frozen=True)
+    max_orders: int = Field(..., ge=1)
+    max_notional: float = Field(..., gt=0.0)
+
+class AgentRuntimeConfig(BaseModel):
+    model_config = ConfigDict(extra="forbid", frozen=True)
+    
+    agent_id: str = Field(..., min_length=1)
+    agent_number: int = Field(..., ge=0)
+    runtime_kind: Literal["api", "cli"]
+    symbols: List[str] = Field(..., min_length=1)
+    provider: str = Field(..., min_length=1)
+    model: str = Field(..., min_length=1)
+    instruction_files: List[str] = Field(..., min_length=1)
+    market_refresh_cadence_sec: int = Field(..., ge=1)
+    analysis_cadence_sec: int = Field(..., ge=1)
+    response_timeout_sec: int = Field(..., ge=1)
+    retry_count: int = Field(..., ge=0)
+    heartbeat_cadence_sec: int = Field(..., ge=1)
+    collective_publication_cadence_sec: int = Field(..., ge=1)
+    portfolio_sync_cadence_sec: int = Field(..., ge=1)
+    reflection_cadence_sec: int = Field(..., ge=1)
+    session_duration_sec: int = Field(..., ge=1)
+    max_pending_commands: int = Field(..., ge=1)
+    testnet_order_limits: TestnetOrderLimits
+    startup_stagger_sec: int = Field(..., ge=0)
+    shutdown_behavior: Literal["graceful", "immediate"]
+
+class DualAgentMVPConfig(BaseModel):
+    model_config = ConfigDict(extra="forbid", frozen=True)
+    agents: Dict[str, AgentRuntimeConfig]
```
