diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
new file mode 100644
index 00000000..f924b1a8
--- /dev/null
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
@@ -0,0 +1,133 @@
+"""FSM and Event-First Agent Invariant Auditing."""
+from __future__ import annotations
+
+import logging
+from datetime import datetime, timezone
+from typing import Any, Literal, Optional
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+
+logger = logging.getLogger(__name__)
+
+CommandStatus = Literal[
+    "recorded",
+    "pending_fsm",
+    "accepted_by_fsm",
+    "rejected_by_fsm",
+    "submitted_testnet",
+    "exchange_ack",
+    "exchange_reject",
+    "lifecycle_closed",
+]
+
+ALLOWED_TRANSITIONS: dict[CommandStatus, set[CommandStatus]] = {
+    "recorded": {"pending_fsm", "accepted_by_fsm", "rejected_by_fsm"},
+    "pending_fsm": {"accepted_by_fsm", "rejected_by_fsm"},
+    "accepted_by_fsm": {"submitted_testnet", "exchange_reject"},
+    "rejected_by_fsm": {"lifecycle_closed"},
+    "submitted_testnet": {"exchange_ack", "exchange_reject"},
+    "exchange_ack": {"lifecycle_closed"},
+    "exchange_reject": {"lifecycle_closed"},
+    "lifecycle_closed": set(),
+}
+
+
+class AgentActionCommand(BaseModel):
+    """Event-backed agent action command representing the attribution data."""
+    model_config = ConfigDict(extra="forbid")
+
+    schema_version: int = 1
+    event_id: str = Field(..., min_length=1)
+    command_id: str = Field(..., min_length=1)
+    session_id: str = Field(..., min_length=1)
+    agent_id: str = Field(..., min_length=1)
+    agent_number: int = Field(..., ge=0)
+    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
+    command_kind: str = Field(..., min_length=1)
+    testnet_only: bool = True
+    status: CommandStatus = "recorded"
+    payload: dict[str, Any] = Field(default_factory=dict)
+
+    @field_validator("testnet_only")
+    @classmethod
+    def must_be_testnet(cls, value: bool) -> bool:
+        """Enforces that all execution-intent commands are testnet only."""
+        if not value:
+            raise ValueError("testnet_only must be True. Mainnet/Live trading is prohibited.")
+        return value
+
+    @field_validator("payload")
+    @classmethod
+    def reject_forbidden_or_credentials(cls, value: dict[str, Any]) -> dict[str, Any]:
+        """Recursively checks and blocks credentials, secrets, or api key fields in payload."""
+        cls._validate_no_secrets(value)
+        return value
+
+    @classmethod
+    def _validate_no_secrets(cls, value: Any, path: str = "payload") -> None:
+        if isinstance(value, dict):
+            for k, val in value.items():
+                k_lower = str(k).lower()
+                child_path = f"{path}.{k_lower}" if path else k_lower
+                # Reject credential keys
+                if any(sec in k_lower for sec in ("api_key", "apikey", "secret", "private_key", "password", "token", "credential")):
+                    raise ValueError(f"Forbidden credential/secret field detected: {child_path}")
+                cls._validate_no_secrets(val, path=child_path)
+        elif isinstance(value, list):
+            for idx, item in enumerate(value):
+                cls._validate_no_secrets(item, path=f"{path}[{idx}]")
+
+
+def transit_status(command: AgentActionCommand, target: CommandStatus) -> None:
+    """Transitions command status enforcing strict FSM state transitions."""
+    current = command.status
+    if target not in ALLOWED_TRANSITIONS[current]:
+        raise ValueError(
+            f"Invalid state transition from '{current}' to '{target}'. "
+            f"Allowed: {ALLOWED_TRANSITIONS[current]}"
+        )
+    command.status = target
+
+
+class FSMAuditRegistry:
+    """Validates FSM registrations for agent action command types."""
+
+    def __init__(self, registered_kinds: Optional[set[str]] = None) -> None:
+        self.registered_kinds = registered_kinds or {
+            "ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE", "OBSERVE"
+        }
+
+    def verify_registration(self, command: AgentActionCommand) -> None:
+        """Verifies if the command kind is registered. Fails closed on missing registration."""
+        if command.command_kind not in self.registered_kinds:
+            command.status = "pending_fsm"
+            raise ValueError(
+                f"FSM registration missing for command_kind '{command.command_kind}'. "
+                f"Failing closed. Status updated to pending_fsm."
+            )
+
+
+class CommandAuditJournal:
+    """Reconstructs sequence history for event-backed commands."""
+
+    def __init__(self, registry: FSMAuditRegistry) -> None:
+        self.registry = registry
+        self.history: list[tuple[datetime, CommandStatus, str]] = []
+
+    def record_request(self, command: AgentActionCommand, reason: str = "Requested") -> None:
+        """Starts sequence tracking by verifying FSM registration."""
+        self.history.append((datetime.now(timezone.utc), command.status, reason))
+        try:
+            self.registry.verify_registration(command)
+        except ValueError as err:
+            self.history.append((datetime.now(timezone.utc), command.status, f"Registration failed: {err}"))
+            raise
+
+    def process_fsm_decision(self, command: AgentActionCommand, accepted: bool, reason: str = "") -> None:
+        """FSM evaluation stage."""
+        target: CommandStatus = "accepted_by_fsm" if accepted else "rejected_by_fsm"
+        transit_status(command, target)
+        self.history.append((datetime.now(timezone.utc), command.status, reason or f"FSM decided: {target}"))
+
+    def submit_to_exchange(self, command: AgentActionCommand, reason: str = "Submitted") -> None:
+        """Testnet submission stage."""
+        transit_status(command, "submitted_testnet")
+        self.history.append((datetime.now(timezone.utc), command.status, reason))
+
+    def record_exchange_response(self, command: AgentActionCommand, ack: bool, reason: str = "") -> None:
+        """Exchange callback handling stage."""
+        target: CommandStatus = "exchange_ack" if ack else "exchange_reject"
+        transit_status(command, target)
+        self.history.append((datetime.now(timezone.utc), command.status, reason or f"Exchange response: {target}"))
+
+    def close_command(self, command: AgentActionCommand, reason: str = "Closed") -> None:
+        """Terminal close stage."""
+        transit_status(command, "lifecycle_closed")
+        self.history.append((datetime.now(timezone.utc), command.status, reason))
diff --git a/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py b/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
new file mode 100644
index 00000000..b5af9dbb
--- /dev/null
+++ b/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
@@ -0,0 +1,110 @@
+from datetime import datetime, timezone
+import pytest
+from pydantic import ValidationError
+
+from deepseek_terminal_agent.sessions.agent_action_audit import (
+    AgentActionCommand,
+    FSMAuditRegistry,
+    CommandAuditJournal,
+    transit_status,
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
+        "payload": {"ticker": "BTCUSDT"},
+    }
+
+
+def test_action_command_rejects_non_testnet():
+    # Valid testnet
+    cmd = AgentActionCommand(**get_base_command())
+    assert cmd.testnet_only is True
+
+    # Mainnet/Live is forbidden
+    data = get_base_command()
+    data["testnet_only"] = False
+    with pytest.raises(ValidationError):
+        AgentActionCommand(**data)
+
+
+def test_action_command_rejects_credentials_recursively():
+    forbidden_payloads = [
+        {"api_key": "12345"},
+        {"secret": "my-secret"},
+        {"sub_payload": {"private_key": "secret-key"}},
+        {"creds": [{"password": "abc"}]},
+    ]
+
+    for payload in forbidden_payloads:
+        data = get_base_command()
+        data["payload"] = payload
+        with pytest.raises(ValidationError):
+            AgentActionCommand(**data)
+
+
+def test_action_command_missing_fsm_fails_closed():
+    registry = FSMAuditRegistry()
+    
+    # 1. Registered kind succeeds
+    cmd_ok = AgentActionCommand(**get_base_command())
+    registry.verify_registration(cmd_ok)
+    assert cmd_ok.status == "recorded"
+
+    # 2. Unregistered kind fails closed and transitions status to pending_fsm
+    data = get_base_command()
+    data["command_kind"] = "UNREGISTERED_ACTION_KIND"
+    cmd_err = AgentActionCommand(**data)
+    
+    with pytest.raises(ValueError, match="FSM registration missing"):
+        registry.verify_registration(cmd_err)
+    assert cmd_err.status == "pending_fsm"
+
+
+def test_audit_sequence_reconstruction():
+    registry = FSMAuditRegistry()
+    journal = CommandAuditJournal(registry)
+    cmd = AgentActionCommand(**get_base_command())
+
+    # Sequence step 1: Request recorded
+    journal.record_request(cmd, "Recording incoming request")
+    assert cmd.status == "recorded"
+    assert len(journal.history) == 1
+
+    # Sequence step 2: FSM accepts request
+    journal.process_fsm_decision(cmd, accepted=True, reason="FSM validation check passed")
+    assert cmd.status == "accepted_by_fsm"
+
+    # Reject invalid sequence transitions (e.g. going back to recorded)
+    with pytest.raises(ValueError):
+        transit_status(cmd, "recorded")
+
+    # Sequence step 3: Submission to testnet
+    journal.submit_to_exchange(cmd, "Routing to testnet API")
+    assert cmd.status == "submitted_testnet"
+
+    # Sequence step 4: Exchange ACK response
+    journal.record_exchange_response(cmd, ack=True, reason="Received order confirmation")
+    assert cmd.status == "exchange_ack"
+
+    # Sequence step 5: Close command lifecycle
+    journal.close_command(cmd, "Archiving finished command context")
+    assert cmd.status == "lifecycle_closed"
+
+    # Confirm chronological audit history matches sequence
+    expected_status_sequence = [
+        "recorded",
+        "accepted_by_fsm",
+        "submitted_testnet",
+        "exchange_ack",
+        "lifecycle_closed",
+    ]
+    actual_sequence = [step[1] for step in journal.history if "Registration failed" not in step[2]]
+    assert actual_sequence == expected_status_sequence
