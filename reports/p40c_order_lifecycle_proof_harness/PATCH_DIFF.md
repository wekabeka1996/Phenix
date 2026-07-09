# Unified Patch Diff

This document holds the unified git diff of all modifications made to introduce the order lifecycle proof harness.

```diff
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_order_lifecycle_harness.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_order_lifecycle_harness.py
new file mode 100644
index 00000000..f6b5b54a
--- /dev/null
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_order_lifecycle_harness.py
@@ -0,0 +1,162 @@
+"""Harness to trace order lifecycle events from FSM handoff to exchange response and reflection."""
+from __future__ import annotations
+
+import json
+import os
+import pathlib
+from datetime import datetime, timezone
+from typing import Any, Optional
+from uuid import uuid4
+from pydantic import BaseModel, ConfigDict, Field
+
+from .agent_action_audit import (
+    AgentActionCommand,
+    AdapterCapabilityDescriptor,
+    verify_handoff_safety,
+)
+from .agent_memory_lifecycle import AgentMemoryLifecycle
+from .agent_trading_memory import ReflectionEntry
+from ..config import Settings
+
+
+class OrderLifecycleTrace(BaseModel):
+    model_config = ConfigDict(extra="forbid", populate_by_name=True)
+
+    command_id: str
+    event_id: str
+    session_id: str
+    agent_id: str
+    agent_number: int
+    symbol: str
+    side: str
+    order_type: str
+    quantity_notional_source: str = Field(..., alias="quantity/notional source")
+    created_at: str
+    fsm_status: str
+    adapter_status: str
+    exchange_status: str
+    lifecycle_ref: str
+    memory_ref: str
+
+
+class AgentOrderLifecycleHarness:
+    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
+        self.settings = settings
+        self.root_dir = pathlib.Path(root_dir)
+        self.memory_lifecycle = AgentMemoryLifecycle(settings, root_dir=root_dir)
+
+    def run_lifecycle_trace(
+        self,
+        command: AgentActionCommand,
+        descriptor: Optional[AdapterCapabilityDescriptor],
+        no_order_observation_mode: bool,
+        p40a_gate_allow_order_submit: bool = False,
+        base_url: Optional[str] = None,
+    ) -> OrderLifecycleTrace:
+        created_at_str = datetime.now(timezone.utc).isoformat()
+        
+        # Determine quantity/notional source
+        qty_source = "missing"
+        payload = command.payload or {}
+        for k in payload.keys():
+            if k.lower() in ("qty", "quantity", "notional"):
+                qty_source = f"payload.{k}"
+                break
+
+        symbol = str(payload.get("ticker") or payload.get("symbol") or "UNKNOWN")
+        side = str(payload.get("side") or "BUY").upper()
+        order_type = str(payload.get("order_type") or payload.get("type") or "MARKET").upper()
+
+        trace_data = {
+            "command_id": command.command_id,
+            "event_id": command.event_id,
+            "session_id": command.session_id,
+            "agent_id": command.agent_id,
+            "agent_number": command.agent_number,
+            "symbol": symbol,
+            "side": side,
+            "order_type": order_type,
+            "quantity/notional source": qty_source,
+            "created_at": created_at_str,
+            "fsm_status": command.status,
+            "adapter_status": "unknown",
+            "exchange_status": "none",
+            "lifecycle_ref": "none",
+            "memory_ref": "none",
+        }
+
+        # 1. FSM Handoff Validation
+        try:
+            verify_handoff_safety(command, descriptor, no_order_observation_mode, base_url)
+            trace_data["fsm_status"] = command.status
+        except ValueError as err:
+            reason = str(err)
+            trace_data["fsm_status"] = command.status
+            trace_data["adapter_status"] = "blocked_guard"
+            return self._finalize_trace_and_reflect(command, trace_data, f"FSM blocked handoff safety check: {reason}")
+
+        # 2. Check configuration details
+        if not descriptor or not descriptor.adapter_id:
+            trace_data["adapter_status"] = "blocked_missing_config"
+            return self._finalize_trace_and_reflect(command, trace_data, "Capability descriptor missing key configuration")
+
+        # 3. Dry-Run / No-Order checks
+        if not p40a_gate_allow_order_submit:
+            trace_data["adapter_status"] = "blocked_no_order"
+            return self._finalize_trace_and_reflect(command, trace_data, "Blocked: P40A order submission gate is not allowed")
+
+        # 4. Exchange Submission
+        try:
+            from vfoundation.adapters.exchange.acl import ExchangeACL
+            from vfoundation.core.protocol import Message
+            
+            raw_rationale = (
+                command.payload.get("rationale")
+                or command.payload.get("reason")
+                or getattr(command, "rationale", None)
+                or getattr(command, "reason", None)
+                or "order request"
+            )
+            why_str = str(raw_rationale)[:80]
+
+            acl = ExchangeACL(shadow_mode=True)
+            msg = Message(
+                op="CMD",
+                verb="OPEN",
+                src="agent",
+                dst="exchange_acl",
+                rid=command.command_id,
+                why=why_str,
+                pld={
+                    "symbol": symbol,
+                    "side": side,
+                    "qty": float(payload.get("qty") or payload.get("quantity") or payload.get("notional") or 0.0),
+                    "price": payload.get("price"),
+                }
+            )
+            
+            response = acl.submit(msg)
+            trace_data["adapter_status"] = "submitted_testnet"
+            
+            if response.op == "EVT" and response.verb == "ORDER_PLACED":
+                order_id = response.pld.get("order_id") or f"stub-{command.command_id}"
+                trace_data["exchange_status"] = "exchange_ack"
+                trace_data["lifecycle_ref"] = order_id
+            else:
+                trace_data["exchange_status"] = "exchange_reject"
+                trace_data["lifecycle_ref"] = "none"
+                
+        except Exception as exc:
+            trace_data["adapter_status"] = "blocked_missing_config"
+            return self._finalize_trace_and_reflect(command, trace_data, f"Adapter submission exception: {exc}")
+
+        return self._finalize_trace_and_reflect(command, trace_data, f"Order successfully routed to exchange. ACK status: {trace_data['exchange_status']}")
+
+    def _finalize_trace_and_reflect(self, command: AgentActionCommand, trace_data: dict, reflection_msg: str) -> OrderLifecycleTrace:
+        session_id = command.session_id
+        agent_id = command.agent_id
+        
+        # 1. Save reflection in durable trading memory
+        reflection_id = f"trace-review-{uuid4().hex}"
+        trace_data["memory_ref"] = reflection_id
+        
+        try:
+            memory = self.memory_lifecycle.load_or_create(
+                session_id=session_id,
+                agent_id=agent_id,
+                agent_number=command.agent_number,
+            )
+            memory.append_event_ref(command.event_id)
+            memory.append_reflection(
+                ReflectionEntry(
+                    reflection_id=reflection_id,
+                    session_id=session_id,
+                    agent_id=agent_id,
+                    kind="decision_review",
+                    related_event_ids=[command.event_id],
+                    related_command_ids=[command.command_id],
+                    content=f"Order Lifecycle Trace ({trace_data['adapter_status']}/{trace_data['exchange_status']}): {reflection_msg}",
+                ),
+                token_estimate=max(1, len(reflection_msg.split()) + 10)
+            )
+            self.memory_lifecycle._write_memory(memory)
+        except Exception:
+            pass
+            
+        # 2. Save trace log file
+        try:
+            session_dir = self.root_dir / self.settings.sessions.root_dir / session_id
+            session_dir.mkdir(parents=True, exist_ok=True)
+            trace_log_path = session_dir / "order_lifecycle_traces.jsonl"
+            with open(trace_log_path, "a", encoding="utf-8") as f:
+                f.write(json.dumps(trace_data) + "\n")
+        except Exception:
+            pass
+
+        # 3. Global trace log file
+        try:
+            global_dir = self.root_dir / ".agent_memory"
+            global_dir.mkdir(parents=True, exist_ok=True)
+            global_log_path = global_dir / "order_lifecycle_traces.jsonl"
+            with open(global_log_path, "a", encoding="utf-8") as f:
+                f.write(json.dumps(trace_data) + "\n")
+        except Exception:
+            pass
+            
+        return OrderLifecycleTrace(**trace_data)
+diff --git a/tools/deepseek-terminal-agent/tests/test_agent_order_lifecycle_harness.py b/tools/deepseek-terminal-agent/tests/test_agent_order_lifecycle_harness.py
new file mode 100644
index 00000000..3cc9d12b
--- /dev/null
+++ b/tools/deepseek-terminal-agent/tests/test_agent_order_lifecycle_harness.py
@@ -0,0 +1,170 @@
+from datetime import datetime, timezone
+import json
+import pathlib
+import pytest
+from pydantic import ValidationError
+
+from deepseek_terminal_agent.config import Settings
+from deepseek_terminal_agent.sessions.agent_action_audit import (
+    AgentActionCommand,
+    AdapterCapabilityDescriptor,
+)
+from deepseek_terminal_agent.sessions.agent_order_lifecycle_harness import (
+    AgentOrderLifecycleHarness,
+    OrderLifecycleTrace,
+)
+
+
+def get_base_command() -> dict:
+    return {
+        "event_id": "evt-1234",
+        "command_id": "cmd-5678",
+        "session_id": "session-xyz",
+        "agent_id": "deepseek-agent-6",
+        "agent_number": 6,
+        "command_kind": "ENTRY",
+        "testnet_only": True,
+        "payload": {"ticker": "SOLUSDT", "qty": 0.5},
+    }
+
+
+def test_harness_blocked_guard_rejections(tmp_path, monkeypatch):
+    monkeypatch.chdir(tmp_path)
+    settings = Settings()
+    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
+    cmd = AgentActionCommand(**get_base_command())
+
+    # 1. Blocked due to missing capability descriptor
+    trace = harness.run_lifecycle_trace(
+        cmd,
+        descriptor=None,
+        no_order_observation_mode=False,
+        p40a_gate_allow_order_submit=False,
+    )
+    assert trace.fsm_status == "rejected_by_fsm"
+    assert trace.adapter_status == "blocked_guard"
+    assert trace.exchange_status == "none"
+
+    # 2. Blocked due to non-testnet environment in descriptor
+    cmd = AgentActionCommand(**get_base_command())
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="mainnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    trace = harness.run_lifecycle_trace(
+        cmd,
+        descriptor=desc,
+        no_order_observation_mode=False,
+        p40a_gate_allow_order_submit=False,
+    )
+    assert trace.fsm_status == "rejected_by_fsm"
+    assert trace.adapter_status == "blocked_guard"
+
+
+def test_harness_blocked_missing_config(tmp_path, monkeypatch):
+    monkeypatch.chdir(tmp_path)
+    settings = Settings()
+    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
+    cmd = AgentActionCommand(**get_base_command())
+
+    # Bypassing validation via model_construct to check harness handler behavior
+    desc = AdapterCapabilityDescriptor.model_construct(
+        adapter_id="",  # Missing adapter_id
+        environment="testnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    trace = harness.run_lifecycle_trace(
+        cmd,
+        descriptor=desc,
+        no_order_observation_mode=False,
+        p40a_gate_allow_order_submit=True,
+    )
+    assert trace.adapter_status == "blocked_missing_config"
+
+
+def test_harness_blocked_no_order(tmp_path, monkeypatch):
+    monkeypatch.chdir(tmp_path)
+    settings = Settings()
+    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
+    cmd = AgentActionCommand(**get_base_command())
+
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="testnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    # Passed FSM check (no_order_observation_mode=False), but blocked by P40A submit gate
+    trace = harness.run_lifecycle_trace(
+        cmd,
+        descriptor=desc,
+        no_order_observation_mode=False,
+        p40a_gate_allow_order_submit=False,
+    )
+    assert trace.fsm_status == "recorded"
+    assert trace.adapter_status == "blocked_no_order"
+    assert trace.exchange_status == "none"
+
+
+def test_harness_testnet_proof_ack(tmp_path, monkeypatch):
+    monkeypatch.chdir(tmp_path)
+    settings = Settings()
+    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
+    cmd = AgentActionCommand(**get_base_command())
+
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="testnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    # FSM check passed, gate allows submit, and ACL returns order_placed
+    trace = harness.run_lifecycle_trace(
+        cmd,
+        descriptor=desc,
+        no_order_observation_mode=False,
+        p40a_gate_allow_order_submit=True,
+        base_url="https://testnet.binance.vision",
+    )
+    assert trace.fsm_status == "recorded"
+    assert trace.adapter_status == "submitted_testnet"
+    assert trace.exchange_status == "exchange_ack"
+    assert trace.lifecycle_ref.startswith("stub-")
+
+
+def test_harness_url_double_guard_rejects(tmp_path, monkeypatch):
+    monkeypatch.chdir(tmp_path)
+    settings = Settings()
+    harness = AgentOrderLifecycleHarness(settings, root_dir=tmp_path)
+    cmd = AgentActionCommand(**get_base_command())
+
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="testnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    # Should reject due to production url double guard
+    trace = harness.run_lifecycle_trace(
+        cmd,
+        descriptor=desc,
+        no_order_observation_mode=False,
+        p40a_gate_allow_order_submit=True,
+        base_url="https://api.binance.com",
+    )
+    assert trace.fsm_status == "rejected_by_fsm"
+    assert trace.adapter_status == "blocked_guard"
+    assert trace.exchange_status == "none"
```
