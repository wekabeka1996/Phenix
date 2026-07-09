diff --git a/docs/cli_agent_session_protocol.md b/docs/cli_agent_session_protocol.md
new file mode 100644
index 00000000..cb558fd3
--- /dev/null
+++ b/docs/cli_agent_session_protocol.md
@@ -0,0 +1,24 @@
+# CLI Agent Session Protocol
+
+This protocol defines the minimal contract and lifecycle logic for bounded CLI agent session loops on the Phenix platform.
+
+## 1. Core Principles
+- **Strict Bounded Execution**: Agents must not execute infinite daemon loops. Loops are constrained by max iterations and max elapsed runtime.
+- **Inspectable State**: Every wakeup iteration produces an inspectable log tick (`TimerTick`).
+- **GET-Only/Read-Only Context**: Agents do not directly edit configs or place execution orders. All updates and proposals are read-only drafts.
+- **Cadence & SOS Synchronization**: Staggered intervals balance memory refresh load, while SOS alerts allow immediate, out-of-band forced updates.
+
+## 2. Actions & Envelopes
+All communication envelopes (`CLIAgentActionEnvelope`) must reject executable field payloads:
+- Prohibited fields: `order`, `sizing`, `leverage`, `quantity`, `notional`, `exchange_order_id`, `client_order_id`.
+- Supported actions:
+  - `memory_refresh`: Pulls the latest synchronized shared context state.
+  - `sos_emit`: Signals sharp market-change events requesting global updates.
+  - `proposal_submit`: Submits drafts for reviewed non-executable suggestions.
+  - `heartbeat`: Registers check-in signals indicating operational stability.
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py
new file mode 100644
index 00000000..9dfb8c5e
--- /dev/null
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py
@@ -0,0 +1,114 @@
+"""Data contract for CLI agent session loops, actions, and state transitions."""
+from __future__ import annotations
+
+from datetime import datetime, timezone
+from typing import Any, Literal, Optional
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+
+
+class CLIAgentSessionState(BaseModel):
+    """Safe state representation of a bounded CLI agent session."""
+    model_config = ConfigDict(extra="forbid")
+
+    schema_version: int = 1
+    session_id: str = Field(..., min_length=1)
+    agent_id: str = Field(..., min_length=1)
+    agent_number: int = Field(..., ge=1)
+    last_memory_refresh_at: Optional[datetime] = None
+    next_refresh_at: Optional[datetime] = None
+    context_version: Optional[int] = None
+    sos_pending: bool = False
+    max_runtime_seconds: float = Field(..., gt=0.0)
+    max_iterations: int = Field(..., gt=0)
+
+
+class CLIAgentActionEnvelope(BaseModel):
+    """Non-executable session wrapper for actions emitted by the CLI agent."""
+    model_config = ConfigDict(extra="forbid")
+
+    schema_version: int = 1
+    action_kind: Literal["memory_refresh", "sos_emit", "proposal_submit", "heartbeat"]
+    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
+    reason: str = Field(..., min_length=1)
+    source_refs: list[str] = Field(default_factory=list)
+    proposal_ref: Optional[str] = None
+    payload: dict[str, Any] = Field(default_factory=dict)
+
+    @field_validator("payload")
+    @classmethod
+    def reject_executable_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
+        """Strict validation enforcing that no executable trading fields are present."""
+        from .agent_proposals import validate_no_forbidden_proposal_fields
+        validate_no_forbidden_proposal_fields(value)
+        return value
+
+
+def build_memory_refresh_action(reason: str, source_refs: list[str]) -> CLIAgentActionEnvelope:
+    """Builds a non-executable action envelope for refreshing shared memory."""
+    return CLIAgentActionEnvelope(
+        action_kind="memory_refresh",
+        reason=reason,
+        source_refs=source_refs,
+    )
+
+
+def build_sos_emit_action(reason: str, market_snapshot_ref: str) -> CLIAgentActionEnvelope:
+    """Builds a non-executable action envelope to emit an SOS trigger."""
+    return CLIAgentActionEnvelope(
+        action_kind="sos_emit",
+        reason=reason,
+        payload={"market_snapshot_ref": market_snapshot_ref},
+    )
+
+
+def build_proposal_submit_action(
+    proposal_ref: str, reason: str, payload: dict[str, Any]
+) -> CLIAgentActionEnvelope:
+    """Builds a non-executable action envelope to submit a trading or analysis proposal."""
+    return CLIAgentActionEnvelope(
+        action_kind="proposal_submit",
+        proposal_ref=proposal_ref,
+        reason=reason,
+        payload=payload,
+    )
+
+
+def should_agent_session_continue(
+    started_at: datetime, now: datetime, state: CLIAgentSessionState, iteration_count: int
+) -> bool:
+    """Evaluates the loop boundary conditions to decide if the session should continue."""
+    if iteration_count >= state.max_iterations:
+        return False
+    
+    elapsed = (now - started_at).total_seconds()
+    if elapsed >= state.max_runtime_seconds:
+        return False
+        
+    return True
+
+
+def apply_timer_tick_to_session_state(
+    state: CLIAgentSessionState,
+    tick_time: datetime,
+    next_refresh: datetime,
+    sos_active: bool,
+) -> CLIAgentSessionState:
+    """Applies a timer tick event to transition the session state."""
+    new_state = state.model_copy(deep=True)
+    
+    # If SOS is active or scheduled refresh is due
+    is_refresh_due = (
+        state.next_refresh_at is not None 
+        and tick_time >= state.next_refresh_at
+    )
+    
+    if sos_active or is_refresh_due:
+        new_state.last_memory_refresh_at = tick_time
+        new_state.next_refresh_at = next_refresh
+        new_state.sos_pending = False
+        if new_state.context_version is not None:
+            new_state.context_version += 1
+        else:
+            new_state.context_version = 1
+            
+    return new_state
diff --git a/tools/deepseek-terminal-agent/tests/test_agent_session_contract.py b/tools/deepseek-terminal-agent/tests/test_agent_session_contract.py
new file mode 100644
index 00000000..08360823
--- /dev/null
+++ b/tools/deepseek-terminal-agent/tests/test_agent_session_contract.py
@@ -0,0 +1,125 @@
+from datetime import datetime, timezone, timedelta
+import pytest
+from pydantic import ValidationError
+
+from deepseek_terminal_agent.sessions.agent_session_contract import (
+    CLIAgentSessionState,
+    CLIAgentActionEnvelope,
+    build_memory_refresh_action,
+    build_sos_emit_action,
+    build_proposal_submit_action,
+    should_agent_session_continue,
+    apply_timer_tick_to_session_state,
+)
+
+
+def test_action_envelope_rejects_forbidden_fields():
+    # Valid envelope payload
+    valid_env = CLIAgentActionEnvelope(
+        action_kind="heartbeat",
+        reason="Periodic ping",
+        payload={"status": "running", "cpu": 12.5},
+    )
+    assert valid_env.action_kind == "heartbeat"
+
+    # Reject forbidden order-like fields (order, sizing, leverage, quantity, notional)
+    forbidden_payloads = [
+        {"order": {"price": 10000, "side": "buy"}},
+        {"sizing": {"percent": 5}},
+        {"leverage": 3},
+        {"quantity": 0.5},
+        {"notional": 100},
+        {"exchange_order_id": "1234"},
+        {"client_order_id": "abc"},
+    ]
+
+    for payload in forbidden_payloads:
+        with pytest.raises(ValidationError):
+            CLIAgentActionEnvelope(
+                action_kind="proposal_submit",
+                reason="Should reject",
+                payload=payload,
+            )
+
+
+def test_session_stop_condition():
+    started = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+    state = CLIAgentSessionState(
+        session_id="session-1",
+        agent_id="agent-6",
+        agent_number=6,
+        max_runtime_seconds=60.0,
+        max_iterations=10,
+    )
+
+    # 1. Bounded check - within limits
+    assert should_agent_session_continue(started, started + timedelta(seconds=30), state, 5) is True
+
+    # 2. Bounded check - iteration limit reached
+    assert should_agent_session_continue(started, started + timedelta(seconds=30), state, 10) is False
+
+    # 3. Bounded check - runtime limit reached
+    assert should_agent_session_continue(started, started + timedelta(seconds=61), state, 5) is False
+
+
+def test_sos_pending_and_state_transitions():
+    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+    next_refresh = now + timedelta(minutes=60)
+    
+    state = CLIAgentSessionState(
+        session_id="session-1",
+        agent_id="agent-6",
+        agent_number=6,
+        next_refresh_at=now + timedelta(minutes=50),
+        sos_pending=True,
+        max_runtime_seconds=60.0,
+        max_iterations=10,
+        context_version=1,
+    )
+
+    # Apply tick without SOS and before scheduled refresh is due
+    tick_time = now + timedelta(minutes=10)
+    state_idle = apply_timer_tick_to_session_state(
+        state, tick_time, next_refresh, sos_active=False
+    )
+    # Refresh should not occur
+    assert state_idle.last_memory_refresh_at is None
+    assert state_idle.sos_pending is True
+    assert state_idle.context_version == 1
+
+    # Apply tick with SOS active -> forces refresh immediately
+    state_sos = apply_timer_tick_to_session_state(
+        state, tick_time, next_refresh, sos_active=True
+    )
+    assert state_sos.last_memory_refresh_at == tick_time
+    assert state_sos.next_refresh_at == next_refresh
+    assert state_sos.sos_pending is False
+    assert state_sos.context_version == 2
+
+    # Apply tick when scheduled refresh is due (tick_time >= next_refresh_at)
+    tick_due = now + timedelta(minutes=55)
+    state_due = apply_timer_tick_to_session_state(
+        state, tick_due, next_refresh, sos_active=False
+    )
+    assert state_due.last_memory_refresh_at == tick_due
+    assert state_due.sos_pending is False
+    assert state_due.context_version == 2
+
+
+def test_proposal_submit_action_is_non_executable():
+    action = build_proposal_submit_action(
+        proposal_ref="proposal-1234",
+        reason="Vol volatility note draft",
+        payload={"analysis": "BTC vol index spiked, no trades proposed"},
+    )
+    assert action.action_kind == "proposal_submit"
+    assert action.proposal_ref == "proposal-1234"
+    assert "analysis" in action.payload
+
+    # Rejects executable entries inside build payload
+    with pytest.raises(ValidationError):
+        build_proposal_submit_action(
+            proposal_ref="proposal-1234",
+            reason="Forbidden payload entry",
+            payload={"sizing": 10},
+        )
