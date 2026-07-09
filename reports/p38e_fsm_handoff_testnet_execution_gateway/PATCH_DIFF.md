# Patch Diff

```diff
diff --git a/apps/reference/dictionaries/verb_registry_v1.yaml b/apps/reference/dictionaries/verb_registry_v1.yaml
index 41769672..8ed607ad 100644
--- a/apps/reference/dictionaries/verb_registry_v1.yaml
+++ b/apps/reference/dictionaries/verb_registry_v1.yaml
@@ -801,6 +801,12 @@ registry:
   status: active
   schema: apps/reference/domains/agent_bridge/schemas/agent_session_stopped_v1.json
   since: '2026-07-06'
+- op: CMD
+  verb: AGENT_TESTNET_ORDER_REQUESTED
+  owner: agent_bridge
+  status: active
+  schema: null
+  since: '2026-07-09'
 policies:
   wildcard:
     UPD: true
diff --git a/apps/reference/domains/execution_position/fsm.py b/apps/reference/domains/execution_position/fsm.py
index 452edf00..5314514a 100644
--- a/apps/reference/domains/execution_position/fsm.py
+++ b/apps/reference/domains/execution_position/fsm.py
@@ -579,6 +579,8 @@ class ExecPosFSM(
         if not self.no_order_observation_mode:
             self.bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1",
                             self._on_external_open_request)
+            self.bus.listen("CMD:AGENT_TESTNET_ORDER_REQUESTED",
+                            self._on_agent_testnet_order_requested)
             self.bus.listen("CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1",
                             self._on_external_position_close_request)
             self.bus.listen("CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1",
@@ -953,6 +955,13 @@ class ExecPosFSM(
             return
         self._intent_router.on_external_open_request(msg)
 
+    def _on_agent_testnet_order_requested(self, msg: Message) -> None:
+        """Handle incoming testnet order requests from external agents."""
+        if self._block_no_order_action("agent_testnet_order_requested"):
+            return
+        if hasattr(self, "_intent_router") and hasattr(self._intent_router, "on_agent_testnet_order_requested"):
+            self._intent_router.on_agent_testnet_order_requested(msg)
+
     def _on_external_position_close_request(self, msg: Message) -> None:
         """Phase 14A: Delegated to IntentRouter (LLM external close path)."""
         if self._block_no_order_action("external_close_request"):
diff --git a/apps/reference/domains/execution_position/flows/open/intent_router.py b/apps/reference/domains/execution_position/flows/open/intent_router.py
index b4693277..1ef5d68f 100644
--- a/apps/reference/domains/execution_position/flows/open/intent_router.py
+++ b/apps/reference/domains/execution_position/flows/open/intent_router.py
@@ -1134,3 +1134,96 @@ class IntentRouter:
             )
         except Exception as e:
             LOG.error(f"Failed to process TRADE_INTENT_REJECTED: {e}")
+
+    def on_agent_testnet_order_requested(self, msg: "Message") -> None:
+        """Processes AGENT_TESTNET_ORDER_REQUESTED by verifying FSM Handoff Gateway rules."""
+        from deepseek_terminal_agent.sessions.agent_action_audit import (
+            AgentActionCommand,
+            FSMAuditRegistry,
+            CommandAuditJournal,
+            FSMHandoffGateway
+        )
+        pld = msg.pld or {}
+        try:
+            cmd = AgentActionCommand(
+                event_id=str(pld.get("event_id") or msg.rid or ""),
+                command_id=str(pld.get("command_id") or msg.rid or ""),
+                session_id=str(pld.get("session_id") or ""),
+                agent_id=str(pld.get("agent_id") or ""),
+                agent_number=int(pld.get("agent_number") or 0),
+                command_kind="AGENT_TESTNET_ORDER_REQUESTED",
+                testnet_only=True,
+                payload=pld,
+            )
+        except Exception as e:
+            LOG.error(f"Failed to instantiate AgentActionCommand for AGENT_TESTNET_ORDER_REQUESTED: {e}")
+            if hasattr(self._fsm, "bus"):
+                self._fsm.bus.emit(
+                    "EVT:DEEPSEEK_AGENT_DECISION_REJECTED",
+                    {"reason": f"Command instantiation failed: {e}"},
+                    "validation_failed",
+                    msg.data_ref,
+                    rid=msg.rid
+                )
+            return
+
+        registry = FSMAuditRegistry()
+        journal = CommandAuditJournal(registry)
+        gateway = FSMHandoffGateway(registry, self._fsm.adapter)
+
+        # Validate handoff rules
+        gateway.validate_and_transit(cmd, journal)
+
+        if cmd.status == "rejected_by_fsm":
+            LOG.warning(f"FSM Handoff Gateway REJECTED command {cmd.command_id}: {journal.history[-1][2]}")
+            if hasattr(self._fsm, "bus"):
+                self._fsm.bus.emit(
+                    "EVT:DEEPSEEK_AGENT_DECISION_REJECTED",
+                    {"command_id": cmd.command_id, "reason": journal.history[-1][2]},
+                    "gateway_rejected",
+                    msg.data_ref,
+                    rid=msg.rid
+                )
+            return
+
+        # Accepted! Let's submit order
+        LOG.info(f"FSM Handoff Gateway ACCEPTED command {cmd.command_id}. Submitting to testnet...")
+        if hasattr(self._fsm, "bus"):
+            self._fsm.bus.emit(
+                "EVT:DEEPSEEK_AGENT_INTENT_ACCEPTED",
+                {"command_id": cmd.command_id},
+                "gateway_accepted",
+                msg.data_ref,
+                rid=msg.rid
+            )
+
+        async def _execute():
+            try:
+                resp = await gateway.execute_testnet_order(cmd, journal)
+                if hasattr(self._fsm, "bus"):
+                    self._fsm.bus.emit(
+                        "EVT:DEEPSEEK_AGENT_TESTNET_ORDER_SUBMITTED",
+                        {"command_id": cmd.command_id, "exchange_order_id": resp.order_id},
+                        "order_submitted",
+                        msg.data_ref,
+                        rid=msg.rid
+                    )
+                    self._fsm.bus.emit(
+                        "EVT:DEEPSEEK_AGENT_TESTNET_ORDER_RESULT",
+                        {"command_id": cmd.command_id, "exchange_order_id": resp.order_id, "status": resp.status},
+                        "order_result",
+                        msg.data_ref,
+                        rid=msg.rid
+                    )
+            except Exception as ex:
+                if hasattr(self._fsm, "bus"):
+                    self._fsm.bus.emit(
+                        "EVT:DEEPSEEK_AGENT_DECISION_REJECTED",
+                        {"command_id": cmd.command_id, "reason": f"Execution failed: {ex}"},
+                        "execution_failed",
+                        msg.data_ref,
+                        rid=msg.rid
+                    )
+
+        # Dispatch async task
+        asyncio.create_task(_execute())
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
index b0aedba3..e2f891da 100644
--- a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py
@@ -93,7 +93,7 @@ class FSMAuditRegistry:
 
     def __init__(self, registered_kinds: Optional[set[str]] = None) -> None:
         self.registered_kinds = registered_kinds or {
-            "ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE", "OBSERVE"
+            "ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE", "OBSERVE", "AGENT_TESTNET_ORDER_REQUESTED"
         }
 
     def verify_registration(self, command: AgentActionCommand) -> None:
@@ -142,4 +142,149 @@ class CommandAuditJournal:
         """Terminal close stage."""
         transit_status(command, "lifecycle_closed")
         self.history.append((datetime.now(timezone.utc), command.status, reason))
+
+
+class FSMHandoffGateway:
+    """Performs FSM handoff validations and coordinates testnet order execution."""
+
+    def __init__(self, registry: FSMAuditRegistry, execution_adapter: Any = None) -> None:
+        self.registry = registry
+        self.execution_adapter = execution_adapter
+
+    def validate_and_transit(self, command: AgentActionCommand, journal: CommandAuditJournal) -> None:
+        """Validates incoming command and transitions status from pending_fsm to accepted or rejected."""
+        # Auto-transition from recorded to pending_fsm
+        if command.status == "recorded":
+            transit_status(command, "pending_fsm")
+
+        if command.status != "pending_fsm":
+            raise ValueError(f"Command must be in 'pending_fsm' status to transit, got '{command.status}'")
+
+        # 1. Missing registry check
+        if self.registry is None:
+            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing registry")
+            return
+
+        # 2. Unknown event kind (verify registration)
+        try:
+            self.registry.verify_registration(command)
+        except ValueError as e:
+            journal.process_fsm_decision(command, accepted=False, reason=f"REJECTED: unknown event kind ({e})")
+            return
+
+        # 3. Missing agent identity
+        if not command.agent_id or not command.session_id or command.agent_number is None:
+            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing agent identity")
+            return
+
+        # 4. Non-testnet flag (testnet_only must be True)
+        if not command.testnet_only:
+            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: non-testnet flag")
+            return
+
+        # 5. Missing or invalid side check
+        if command.command_kind in {"ENTRY", "AGENT_TESTNET_ORDER_REQUESTED"}:
+            side = command.payload.get("side")
+            if not side or str(side).upper() not in {"BUY", "SELL"}:
+                journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing or invalid side (must be BUY or SELL)")
+                return
+
+        # 6. Missing explicit quantity/notional where required
+        if command.command_kind in {"ENTRY", "AGENT_TESTNET_ORDER_REQUESTED"}:
+            payload = command.payload
+            qty = payload.get("quantity") or payload.get("qty")
+            notional = payload.get("notional")
+            if not qty and not notional:
+                journal.process_fsm_decision(command, accepted=False, reason="REJECTED: missing explicit quantity/notional")
+                return
+            # Validate positive values
+            if qty:
+                try:
+                    if float(qty) <= 0:
+                        journal.process_fsm_decision(command, accepted=False, reason="REJECTED: invalid quantity <= 0")
+                        return
+                except (ValueError, TypeError):
+                    journal.process_fsm_decision(command, accepted=False, reason="REJECTED: quantity must be float-castable")
+                    return
+            if notional:
+                try:
+                    if float(notional) <= 0:
+                        journal.process_fsm_decision(command, accepted=False, reason="REJECTED: invalid notional <= 0")
+                        return
+                except (ValueError, TypeError):
+                    journal.process_fsm_decision(command, accepted=False, reason="REJECTED: notional must be float-castable")
+                    return
+
+        # 7. No execution adapter available
+        if self.execution_adapter is None:
+            journal.process_fsm_decision(command, accepted=False, reason="REJECTED: no execution adapter available")
+            return
+
+        # Check adapter base URL to prove it is testnet
+        is_simulated = self.execution_adapter.__class__.__name__ == "SimulatedAdapter"
+        if not is_simulated:
+            base_url = getattr(self.execution_adapter, "base_url", "") or getattr(self.execution_adapter, "rest_url", "")
+            if not base_url or "testnet" not in base_url.lower():
+                journal.process_fsm_decision(command, accepted=False, reason="REJECTED: adapter base URL does not prove testnet")
+                return
+
+        # Passed all checks!
+        journal.process_fsm_decision(command, accepted=True, reason="ACCEPTED: FSM handoff validated successfully")
+
+    async def execute_testnet_order(self, command: AgentActionCommand, journal: CommandAuditJournal) -> Any:
+        """Submits the accepted command to the exchange via the adapter and records the outcome."""
+        if command.status != "accepted_by_fsm":
+            raise ValueError(f"Command must be accepted_by_fsm to execute, got '{command.status}'")
+
+        journal.submit_to_exchange(command, "Routing command to execution adapter")
+
+        payload = command.payload
+        symbol = payload.get("symbol") or payload.get("ticker")
+        side = payload.get("side")
+        order_type = payload.get("order_type") or "MARKET"
+        quantity = str(payload.get("quantity") or payload.get("qty") or "")
+        price = payload.get("price")
+        time_in_force = payload.get("time_in_force") or payload.get("tif") or "GTC"
+        reduce_only = bool(payload.get("reduce_only") or payload.get("reduceOnly"))
+        close_position = bool(payload.get("close_position") or payload.get("closePosition"))
+        client_order_id = payload.get("client_order_id") or payload.get("newClientOrderId") or command.command_id
+        position_side = payload.get("position_side") or payload.get("positionSide")
+        stop_price = payload.get("stop_price") or payload.get("stopPrice")
+        working_type = payload.get("working_type") or payload.get("workingType")
+
+        # Map to ExchangeOrderParams
+        from vfoundation.core.adapters.base import ExchangeOrderParams
+        params = ExchangeOrderParams(
+            symbol=symbol,
+            side=side.upper(),
+            order_type=order_type.upper(),
+            quantity=quantity,
+            price=price,
+            time_in_force=time_in_force.upper(),
+            reduce_only=reduce_only,
+            close_position=close_position,
+            client_order_id=client_order_id,
+            position_side=position_side,
+            stop_price=stop_price,
+            working_type=working_type,
+        )
+
+        try:
+            resp = await self.execution_adapter.create_order(params)
+            # Log exchange response
+            logger.info(f"Exchange response received: {resp}")
+            # Record success (exchange_ack)
+            journal.record_exchange_response(command, ack=True, reason=f"Exchange ACK: {resp.order_id}")
+            # Record lifecycle reference in command payload
+            command.payload["exchange_order_id"] = resp.order_id
+            command.payload["exchange_status"] = resp.status
+            journal.close_command(command, "FSM handoff execution lifecycle closed")
+            return resp
+        except Exception as e:
+            logger.error(f"Exchange order submission failed: {e}")
+            # Record failure (exchange_reject)
+            journal.record_exchange_response(command, ack=False, reason=f"Exchange REJECT: {e}")
+            journal.close_command(command, "FSM handoff execution lifecycle closed after rejection")
+            raise
+
 
diff --git a/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py b/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
index b5af9dbb..92b3c2cd 100644
--- a/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
+++ b/tools/deepseek-terminal-agent/tests/test_agent_action_audit.py
@@ -7,6 +7,7 @@ from deepseek_terminal_agent.sessions.agent_action_audit import (
     FSMAuditRegistry,
     CommandAuditJournal,
     transit_status,
+    FSMHandoffGateway,
 )
 
 
@@ -108,3 +109,112 @@ def test_audit_sequence_reconstruction():
     ]
     actual_sequence = [step[1] for step in journal.history if "Registration failed" not in step[2]]
     assert actual_sequence == expected_status_sequence
+
+
+class MockTestnetAdapter:
+    def __init__(self, base_url: str = "https://testnet.binancefuture.com"):
+        self.base_url = base_url
+        self.orders = []
+
+    async def create_order(self, params):
+        from vfoundation.core.adapters.base import ExchangeOrderResponse
+        import time
+        self.orders.append(params)
+        if params.symbol == "FAIL":
+            raise RuntimeError("API Error")
+        return ExchangeOrderResponse(
+            order_id="order-999",
+            client_order_id=params.client_order_id,
+            symbol=params.symbol,
+            side=params.side,
+            quantity=params.quantity,
+            filled_qty=params.quantity,
+            price=params.price,
+            status="FILLED",
+            timestamp_ms=int(time.time() * 1000)
+        )
+
+
+@pytest.mark.asyncio
+async def test_fsm_handoff_gateway_validations_and_execution():
+    registry = FSMAuditRegistry()
+    adapter = MockTestnetAdapter()
+    gateway = FSMHandoffGateway(registry, adapter)
+    journal = CommandAuditJournal(registry)
+
+    # 1. Invalid kind rejection
+    data = get_base_command()
+    data["command_kind"] = "UNKNOWN_KIND"
+    cmd_invalid_kind = AgentActionCommand(**data)
+    gateway.validate_and_transit(cmd_invalid_kind, journal)
+    assert cmd_invalid_kind.status == "rejected_by_fsm"
+    assert "unknown event kind" in journal.history[-1][2].lower()
+
+    # 2. Missing/invalid side rejection
+    data = get_base_command()
+    data["command_kind"] = "AGENT_TESTNET_ORDER_REQUESTED"
+    data["payload"] = {"quantity": "0.5"}  # no side
+    cmd_missing_side = AgentActionCommand(**data)
+    gateway.validate_and_transit(cmd_missing_side, journal)
+    assert cmd_missing_side.status == "rejected_by_fsm"
+    assert "missing or invalid side" in journal.history[-1][2].lower()
+
+    # 3. Missing explicit quantity/notional rejection
+    data = get_base_command()
+    data["command_kind"] = "AGENT_TESTNET_ORDER_REQUESTED"
+    data["payload"] = {"side": "BUY"}  # Empty quantity
+    cmd_missing_qty = AgentActionCommand(**data)
+    gateway.validate_and_transit(cmd_missing_qty, journal)
+    assert cmd_missing_qty.status == "rejected_by_fsm"
+    assert "missing explicit quantity/notional" in journal.history[-1][2].lower()
+
+    # 4. Invalid quantity <= 0 rejection
+    data = get_base_command()
+    data["command_kind"] = "AGENT_TESTNET_ORDER_REQUESTED"
+    data["payload"] = {"side": "BUY", "quantity": "0"}
+    cmd_invalid_qty = AgentActionCommand(**data)
+    gateway.validate_and_transit(cmd_invalid_qty, journal)
+    assert cmd_invalid_qty.status == "rejected_by_fsm"
+    assert "invalid quantity <= 0" in journal.history[-1][2].lower()
+
+    # 5. Missing adapter rejection
+    data = get_base_command()
+    data["payload"] = {"side": "BUY", "quantity": "1.0"}
+    cmd_no_adapter = AgentActionCommand(**data)
+    gateway_no_adapter = FSMHandoffGateway(registry, None)
+    gateway_no_adapter.validate_and_transit(cmd_no_adapter, journal)
+    assert cmd_no_adapter.status == "rejected_by_fsm"
+    assert "no execution adapter available" in journal.history[-1][2].lower()
+
+    # 6. Non-testnet base URL adapter rejection
+    data = get_base_command()
+    data["payload"] = {"side": "BUY", "quantity": "1.0"}
+    cmd_non_testnet = AgentActionCommand(**data)
+    live_adapter = MockTestnetAdapter(base_url="https://fapi.binance.com")
+    gateway_non_testnet = FSMHandoffGateway(registry, live_adapter)
+    gateway_non_testnet.validate_and_transit(cmd_non_testnet, journal)
+    assert cmd_non_testnet.status == "rejected_by_fsm"
+    assert "url does not prove testnet" in journal.history[-1][2].lower()
+
+    # 7. Valid handoff and successful execution
+    data = get_base_command()
+    data["payload"] = {"side": "BUY", "quantity": "0.5", "price": "100.0"}
+    cmd_valid = AgentActionCommand(**data)
+    
+    # Validation step
+    gateway.validate_and_transit(cmd_valid, journal)
+    assert cmd_valid.status == "accepted_by_fsm"
+
+    # Execution step
+    resp = await gateway.execute_testnet_order(cmd_valid, journal)
+    assert resp.order_id == "order-999"
+    assert cmd_valid.status == "lifecycle_closed"
+    assert cmd_valid.payload["exchange_order_id"] == "order-999"
+
+    # 8. Valid handoff but execution failure
+    data = get_base_command()
+    data["payload"] = {"side": "BUY", "quantity": "0.5", "symbol": "FAIL"}
+    cmd_fail = AgentActionCommand(**data)
+    
+    gateway.validate_and_transit(cmd_fail, journal)
+    assert cmd_fail.status == "accepted_by_fsm"
+
+    with pytest.raises(RuntimeError, match="API Error"):
+        await gateway.execute_testnet_order(cmd_fail, journal)
+    assert cmd_fail.status == "lifecycle_closed"
+    assert "Exchange REJECT" in journal.history[-2][2]
+
```
