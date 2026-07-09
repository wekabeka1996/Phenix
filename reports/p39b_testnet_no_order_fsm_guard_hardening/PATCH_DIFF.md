# Patch Diff

This diff details the exact modifications made to the FSM handoff audit modules and tests.

```diff
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
index a2d4b791..cc286ad1 100644
--- a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
@@ -31,6 +31,126 @@ ALLOWED_TRANSITIONS: dict[CommandStatus, set[CommandStatus]] = {
 }
 
 
+class AdapterCapabilityDescriptor(BaseModel):
+    """Explicit adapter capability descriptor."""
+    model_config = ConfigDict(extra="forbid")
+
+    adapter_id: str = Field(..., min_length=1)
+    environment: Literal["testnet", "sandbox", "mainnet", "unknown"]
+    supports_order_submit: bool
+    supports_no_order_observation: bool
+    source_of_truth: str = Field(..., min_length=1)
+    checked_at: str = Field(..., min_length=1)
+
+
+def log_rejection(command: AgentActionCommand, reason: str) -> None:
+    """Persists rejection reason into session-specific and global auditable ledgers."""
+    import json
+    import pathlib
+
+    timestamp = datetime.now(timezone.utc).isoformat()
+    record = {
+        "agent_id": command.agent_id or "unknown",
+        "session_id": command.session_id or "unknown",
+        "command_id": command.command_id or "unknown",
+        "event_id": command.event_id or "unknown",
+        "reason": reason,
+        "timestamp": timestamp,
+    }
+
+    session_id = command.session_id or "unknown"
+
+    # Write to session-specific ledger
+    try:
+        session_dir = pathlib.Path(".agent_memory") / "sessions" / session_id
+        session_dir.mkdir(parents=True, exist_ok=True)
+        session_path = session_dir / "audit_rejections.jsonl"
+        with open(session_path, "a", encoding="utf-8") as f:
+            f.write(json.dumps(record) + "\n")
+    except Exception as e:
+        logger.error(f"Failed to write rejection to session ledger: {e}")
+
+    # Write to global audit log
+    try:
+        global_dir = pathlib.Path(".agent_memory")
+        global_dir.mkdir(parents=True, exist_ok=True)
+        global_path = global_dir / "audit_rejections.jsonl"
+        with open(global_path, "a", encoding="utf-8") as f:
+            f.write(json.dumps(record) + "\n")
+    except Exception as e:
+        logger.error(f"Failed to write rejection to global ledger: {e}")
+
+
+def verify_handoff_safety(
+    command: AgentActionCommand,
+    descriptor: Optional[AdapterCapabilityDescriptor],
+    no_order_observation_mode: bool,
+    base_url: Optional[str] = None,
+) -> None:
+    """Verifies FSM handoff safety parameters and capability descriptors."""
+    try:
+        # 1. Identity validation
+        if (
+            not command.agent_id or not str(command.agent_id).strip() or
+            not command.session_id or not str(command.session_id).strip() or
+            not command.command_id or not str(command.command_id).strip() or
+            not command.event_id or not str(command.event_id).strip() or
+            command.agent_number is None or command.agent_number < 0
+        ):
+            raise ValueError("command lacks identity fields")
+
+        # 2. Missing descriptor
+        if descriptor is None:
+            raise ValueError("capability descriptor is missing")
+
+        # 3. Environment validation
+        if descriptor.environment not in ("testnet", "sandbox"):
+            raise ValueError(f"invalid environment: {descriptor.environment}")
+
+        # 4. No-order observation mode
+        if no_order_observation_mode:
+            raise ValueError("no_order_observation_mode is active")
+
+        # 5. Quantity / Notional validation for order submissions
+        is_order_submit = command.command_kind.upper() in {"ENTRY", "ORDER", "FULL_CLOSE", "PARTIAL_CLOSE"} or any(
+            x in command.command_kind.lower() for x in ("order_request", "close_request")
+        )
+        if is_order_submit:
+            payload = command.payload or {}
+            qty_val = None
+            for k, v in payload.items():
+                if k.lower() in ("qty", "quantity", "notional"):
+                    qty_val = v
+                    break
+
+            if qty_val is None:
+                raise ValueError("command lacks explicit configured quantity/notional")
+            try:
+                numeric_qty = float(qty_val)
+                if numeric_qty <= 0:
+                    raise ValueError("command lacks explicit configured quantity/notional")
+            except (ValueError, TypeError):
+                raise ValueError("command lacks explicit configured quantity/notional")
+
+        # 6. Secondary URL checks
+        if base_url:
+            base_url_lower = base_url.lower()
+            prod_domains = ("api.binance.com", "fapi.binance.com", "dapi.binance.com", "api-gcp.binance.com", "api.binance.us")
+            if any(domain in base_url_lower for domain in prod_domains):
+                raise ValueError("production URL detected in base_url")
+
+    except ValueError as err:
+        reason = str(err)
+        if command.status in ("recorded", "pending_fsm"):
+            try:
+                transit_status(command, "rejected_by_fsm")
+            except Exception:
+                pass
+        log_rejection(command, reason)
+        raise
+
+
+
 class AgentActionCommand(BaseModel):
     """Event-backed agent action command representing the attribution data."""
     model_config = ConfigDict(extra="forbid")
@@ -128,6 +248,20 @@ class CommandAuditJournal:
         transit_status(command, target)
         self.history.append((datetime.now(timezone.utc), command.status, reason or f"FSM decided: {target}"))
 
+    def verify_handoff_safety(
+        self,
+        command: AgentActionCommand,
+        descriptor: Optional[AdapterCapabilityDescriptor],
+        no_order_observation_mode: bool,
+        base_url: Optional[str] = None,
+    ) -> None:
+        """Verifies safety parameters and records transition on failure."""
+        try:
+            verify_handoff_safety(command, descriptor, no_order_observation_mode, base_url)
+        except ValueError as err:
+            self.history.append((datetime.now(timezone.utc), command.status, f"Safety check failed: {err}"))
+            raise
+
     def submit_to_exchange(self, command: AgentActionCommand, reason: str = "Submitted") -> None:
         """Testnet submission stage."""
         transit_status(command, "submitted_testnet")
diff --git a/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py b/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
index b5af9dbb..2fb6d475 100644
--- a/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
+++ b/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
@@ -108,3 +108,121 @@ def test_audit_sequence_reconstruction():
     ]
     actual_sequence = [step[1] for step in journal.history if "Registration failed" not in step[2]]
     assert actual_sequence == expected_status_sequence
+
+
+def test_verify_handoff_safety_non_testnet_descriptor_rejects():
+    from deepseek_terminal_agent.sessions.agent_action_audit import (
+        verify_handoff_safety,
+        AdapterCapabilityDescriptor,
+        AgentActionCommand,
+    )
+    cmd = AgentActionCommand(**get_base_command())
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="mainnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    with pytest.raises(ValueError, match="invalid environment: mainnet"):
+        verify_handoff_safety(cmd, desc, no_order_observation_mode=False)
+    assert cmd.status == "rejected_by_fsm"
+
+
+def test_verify_handoff_safety_missing_descriptor_rejects():
+    from deepseek_terminal_agent.sessions.agent_action_audit import (
+        verify_handoff_safety,
+        AgentActionCommand,
+    )
+    cmd = AgentActionCommand(**get_base_command())
+    with pytest.raises(ValueError, match="capability descriptor is missing"):
+        verify_handoff_safety(cmd, None, no_order_observation_mode=False)
+    assert cmd.status == "rejected_by_fsm"
+
+
+def test_verify_handoff_safety_no_order_observation_mode_blocks():
+    from deepseek_terminal_agent.sessions.agent_action_audit import (
+        verify_handoff_safety,
+        AdapterCapabilityDescriptor,
+        AgentActionCommand,
+    )
+    cmd = AgentActionCommand(**get_base_command())
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="testnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    with pytest.raises(ValueError, match="no_order_observation_mode is active"):
+        verify_handoff_safety(cmd, desc, no_order_observation_mode=True)
+    assert cmd.status == "rejected_by_fsm"
+
+
+def test_verify_handoff_safety_url_string_alone_insufficient():
+    from deepseek_terminal_agent.sessions.agent_action_audit import (
+        verify_handoff_safety,
+        AgentActionCommand,
+    )
+    cmd = AgentActionCommand(**get_base_command())
+    # Even if base_url is testnet, missing descriptor must reject
+    with pytest.raises(ValueError, match="capability descriptor is missing"):
+        verify_handoff_safety(cmd, None, no_order_observation_mode=False, base_url="https://testnet.binance.vision")
+    assert cmd.status == "rejected_by_fsm"
+
+
+def test_verify_handoff_safety_valid_passes():
+    from deepseek_terminal_agent.sessions.agent_action_audit import (
+        verify_handoff_safety,
+        AdapterCapabilityDescriptor,
+        AgentActionCommand,
+    )
+    data = get_base_command()
+    data["payload"] = {"ticker": "BTCUSDT", "qty": 0.5}
+    cmd = AgentActionCommand(**data)
+    desc = AdapterCapabilityDescriptor(
+        adapter_id="binance_acl",
+        environment="testnet",
+        supports_order_submit=True,
+        supports_no_order_observation=False,
+        source_of_truth="config",
+        checked_at="2026-07-09T18:00:00Z",
+    )
+    # Valid testnet passes handoff validation without submitting real order
+    verify_handoff_safety(cmd, desc, no_order_observation_mode=False, base_url="https://testnet.binance.vision")
+    assert cmd.status == "recorded"
+
+
+def test_verify_handoff_safety_rejection_log_preserves_fields(tmp_path, monkeypatch):
+    from deepseek_terminal_agent.sessions.agent_action_audit import (
+        verify_handoff_safety,
+        AgentActionCommand,
+    )
+    import json
+    import pathlib
+
+    # Redirect .agent_memory to tmp_path
+    monkeypatch.chdir(tmp_path)
+
+    cmd = AgentActionCommand(**get_base_command())
+
+    with pytest.raises(ValueError):
+        verify_handoff_safety(cmd, None, no_order_observation_mode=False)
+
+    # Read rejection log
+    log_file = pathlib.Path(".agent_memory") / "sessions" / cmd.session_id / "audit_rejections.jsonl"
+    assert log_file.exists()
+
+    with open(log_file, "r") as f:
+        line = f.readline()
+        data = json.loads(line)
+
+    assert data["agent_id"] == cmd.agent_id
+    assert data["session_id"] == cmd.session_id
+    assert data["command_id"] == cmd.command_id
+    assert data["event_id"] == cmd.event_id
+    assert data["reason"] == "capability descriptor is missing"
+    assert "timestamp" in data
```
