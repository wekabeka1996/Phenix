"""Harness to trace order lifecycle events from FSM handoff to exchange response and reflection."""
from __future__ import annotations

import json
import os
import pathlib
import asyncio
import concurrent.futures
from datetime import datetime, timezone
from typing import Any, Optional, Dict
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from .agent_action_audit import (
    AgentActionCommand,
    AdapterCapabilityDescriptor,
    verify_handoff_safety,
)
from .agent_memory_lifecycle import AgentMemoryLifecycle
from .agent_trading_memory import ReflectionEntry
from ..config import Settings


class OrderLifecycleTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    command_id: str
    event_id: str
    session_id: str
    agent_id: str
    agent_number: int
    symbol: str
    side: str
    order_type: str
    quantity_notional_source: str = Field(..., alias="quantity/notional source")
    created_at: str
    fsm_status: str
    adapter_status: str
    exchange_status: str
    lifecycle_ref: str
    memory_ref: str


class EXTERNAL_ACK(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    status: str = "ACK"


class EXTERNAL_REJECT(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    reason: str
    status: str = "REJECT"


class EXTERNAL_FILL(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    filled_qty: float
    price: float
    status: str = "FILL"


class BLOCKED_CONFIG(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    reason: str
    status: str = "BLOCKED_CONFIG"


class BLOCKED_POLICY(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    reason: str
    status: str = "BLOCKED_POLICY"


class BLOCKED_DUPLICATE(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    reason: str
    status: str = "BLOCKED_DUPLICATE"


class BLOCKED_ENVIRONMENT(OrderLifecycleTrace):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    reason: str
    status: str = "BLOCKED_ENVIRONMENT"


class AgentOrderLifecycleHarness:
    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = pathlib.Path(root_dir)
        self.memory_lifecycle = AgentMemoryLifecycle(settings, root_dir=root_dir)

    def _run_async_sync(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)

    def run_lifecycle_trace(
        self,
        command: AgentActionCommand,
        descriptor: Optional[AdapterCapabilityDescriptor],
        no_order_observation_mode: bool,
        p40a_gate_allow_order_submit: bool = False,
        base_url: Optional[str] = None,
    ) -> OrderLifecycleTrace:
        created_at_str = datetime.now(timezone.utc).isoformat()
        
        # Determine quantity/notional source
        qty_source = "missing"
        payload = command.payload or {}
        for k in payload.keys():
            if k.lower() in ("qty", "quantity", "notional"):
                qty_source = f"payload.{k}"
                break

        symbol = str(payload.get("ticker") or payload.get("symbol") or "UNKNOWN")
        side = str(payload.get("side") or "BUY").upper()
        order_type = str(payload.get("order_type") or payload.get("type") or "MARKET").upper()

        trace_data = {
            "command_id": command.command_id,
            "event_id": command.event_id,
            "session_id": command.session_id,
            "agent_id": command.agent_id,
            "agent_number": command.agent_number,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity/notional source": qty_source,
            "created_at": created_at_str,
            "fsm_status": command.status,
            "adapter_status": "unknown",
            "exchange_status": "none",
            "lifecycle_ref": "none",
            "memory_ref": "none",
        }

        # 1. Duplicate command ID check
        is_duplicate = False
        try:
            global_log_path = self.root_dir / ".agent_memory" / "order_lifecycle_traces.jsonl"
            if global_log_path.exists():
                with open(global_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get("command_id") == command.command_id:
                                is_duplicate = True
                                break
        except Exception:
            pass

        if is_duplicate:
            trace_data["adapter_status"] = "blocked_duplicate"
            response = BLOCKED_DUPLICATE(**trace_data, reason="Duplicate command ID detected")
            return self._finalize_trace_and_reflect(command, trace_data, "Blocked: duplicate command ID", response)

        # 2. FSM Handoff Validation
        try:
            verify_handoff_safety(command, descriptor, no_order_observation_mode, base_url)
            trace_data["fsm_status"] = command.status
        except ValueError as err:
            reason = str(err)
            trace_data["fsm_status"] = command.status
            trace_data["adapter_status"] = "blocked_guard"
            response = BLOCKED_ENVIRONMENT(**trace_data, reason=reason)
            return self._finalize_trace_and_reflect(command, trace_data, f"FSM blocked handoff safety check: {reason}", response)

        # 3. Check configuration details
        if not descriptor or not descriptor.adapter_id:
            trace_data["adapter_status"] = "blocked_missing_config"
            response = BLOCKED_CONFIG(**trace_data, reason="Capability descriptor missing key configuration")
            return self._finalize_trace_and_reflect(command, trace_data, "Capability descriptor missing key configuration", response)

        if descriptor.adapter_id.strip().lower() in ("stub", "shadow", "mock", "exchange_acl") or descriptor.no_order_observation_mode:
            trace_data["adapter_status"] = "blocked_missing_config"
            response = BLOCKED_CONFIG(**trace_data, reason="Stub or shadow-only adapter rejected under real testnet requirements")
            return self._finalize_trace_and_reflect(command, trace_data, "Stub or shadow-only adapter rejected", response)

        # 4. Symbol Ownership Check
        try:
            from .coordination_config import load_coordination_config
            coord_cfg = load_coordination_config()
            owner = coord_cfg.owner_for_symbol(symbol)
            if owner.agent_id != command.agent_id or owner.agent_number != command.agent_number:
                trace_data["adapter_status"] = "blocked_policy"
                reason = f"Wrong symbol owner: {symbol} is owned by {owner.agent_id} (agent_number={owner.agent_number})"
                response = BLOCKED_POLICY(**trace_data, reason=reason)
                return self._finalize_trace_and_reflect(command, trace_data, f"Policy block: {reason}", response)
        except Exception as e:
            trace_data["adapter_status"] = "blocked_policy"
            response = BLOCKED_POLICY(**trace_data, reason=f"Symbol ownership resolution failed: {e}")
            return self._finalize_trace_and_reflect(command, trace_data, f"Policy block: {e}", response)

        # 5. Agent 1 places external order restriction
        api_agent_allowed = False
        try:
            from apps.reference.config_loader import ConfigLoader
            config = ConfigLoader().load_config()
            if getattr(config, "agent_arena", None) and getattr(config.agent_arena, "api_agent_order_submit_enabled", False):
                api_agent_allowed = True
        except Exception:
            pass

        if command.agent_number == 1 and not api_agent_allowed and p40a_gate_allow_order_submit and descriptor.environment == "testnet":
            trace_data["adapter_status"] = "blocked_policy"
            reason = "Agent 1 is prohibited from placing external orders"
            response = BLOCKED_POLICY(**trace_data, reason=reason)
            return self._finalize_trace_and_reflect(command, trace_data, f"Policy block: {reason}", response)

        # 6. Dry-Run / No-Order checks
        if not p40a_gate_allow_order_submit:
            trace_data["adapter_status"] = "blocked_no_order"
            response = BLOCKED_POLICY(**trace_data, reason="Blocked: P40A order submission gate is not allowed")
            return self._finalize_trace_and_reflect(command, trace_data, "Blocked: P40A order submission gate is not allowed", response)

        # 7. Check credentials
        api_key = os.environ.get("BINANCE_TESTNET_API_KEY")
        api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET")
        
        try:
            from apps.reference.config_loader import ConfigLoader
            config = ConfigLoader().load_config()
            if config.binance_api and config.binance_api.testnet:
                if not api_key or api_key.startswith("$"):
                    api_key = config.binance_api.testnet.api_key
                if not api_secret or api_secret.startswith("$"):
                    api_secret = config.binance_api.testnet.api_secret
        except Exception:
            pass
            
        if api_key and (api_key.startswith("$") or api_key.strip() == ""):
            api_key = None
        if api_secret and (api_secret.startswith("$") or api_secret.strip() == ""):
            api_secret = None

        if not api_key or not api_secret:
            trace_data["adapter_status"] = "blocked_missing_config"
            response = BLOCKED_CONFIG(**trace_data, reason="Missing testnet API credentials")
            return self._finalize_trace_and_reflect(command, trace_data, "Missing testnet API credentials", response)

        # 8. Exchange Submission (Real Binance Futures Testnet Adapter)
        try:
            from apps.reference.adapters.binance_adapter import BinanceAdapter
            
            raw_rationale = (
                command.payload.get("rationale")
                or command.payload.get("reason")
                or getattr(command, "rationale", None)
                or getattr(command, "reason", None)
                or "order request"
            )
            why_str = str(raw_rationale)[:80]

            adapter = BinanceAdapter(
                api_key=api_key,
                api_secret=api_secret,
                rest_url=descriptor.environment == "testnet" and "https://testnet.binancefuture.com" or base_url or "https://testnet.binancefuture.com",
            )
            
            qty = str(payload.get("qty") or payload.get("quantity") or payload.get("notional") or 0.0)
            price = payload.get("price")
            if price is not None:
                price = str(price)

            if order_type == "LIMIT":
                coro = adapter.place_limit_entry(
                    symbol=symbol,
                    side=side,
                    price=price,
                    quantity=qty,
                    time_in_force=payload.get("time_in_force", "GTC"),
                    new_client_order_id=command.command_id,
                )
            else:
                coro = adapter.place_market_entry(
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    new_client_order_id=command.command_id,
                )
            
            result = self._run_async_sync(coro)
            trace_data["adapter_status"] = "submitted_testnet"
            
            if isinstance(result, dict) and "orderId" in result:
                order_id = str(result["orderId"])
                status = result.get("status")
                trace_data["exchange_status"] = "exchange_ack"
                trace_data["lifecycle_ref"] = order_id
                
                if status == "FILLED":
                    filled_qty = float(result.get("executedQty") or qty)
                    avg_price = float(result.get("avgPrice") or price or 0.0)
                    response = EXTERNAL_FILL(**trace_data, filled_qty=filled_qty, price=avg_price)
                else:
                    response = EXTERNAL_ACK(**trace_data, order_id=order_id)
            else:
                trace_data["exchange_status"] = "exchange_reject"
                trace_data["lifecycle_ref"] = "none"
                response = EXTERNAL_REJECT(**trace_data, reason=str(result))
                
        except Exception as exc:
            trace_data["adapter_status"] = "submitted_testnet"
            trace_data["exchange_status"] = "exchange_reject"
            response = EXTERNAL_REJECT(**trace_data, reason=f"Adapter exception: {exc}")
            return self._finalize_trace_and_reflect(command, trace_data, f"Adapter submission exception: {exc}", response)

        return self._finalize_trace_and_reflect(command, trace_data, f"Order successfully routed to exchange. ACK status: {trace_data['exchange_status']}", response)

    def _finalize_trace_and_reflect(
        self,
        command: AgentActionCommand,
        trace_data: dict,
        reflection_msg: str,
        response: OrderLifecycleTrace,
    ) -> OrderLifecycleTrace:
        session_id = command.session_id
        agent_id = command.agent_id
        
        reflection_id = f"trace-review-{uuid4().hex}"
        trace_data["memory_ref"] = reflection_id
        response.memory_ref = reflection_id
        
        try:
            memory = self.memory_lifecycle.load_or_create(
                session_id=session_id,
                agent_id=agent_id,
                agent_number=command.agent_number,
            )
            memory.append_event_ref(command.event_id)
            memory.append_reflection(
                ReflectionEntry(
                    reflection_id=reflection_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    kind="decision_review",
                    related_event_ids=[command.event_id],
                    related_command_ids=[command.command_id],
                    content=f"Order Lifecycle Trace ({trace_data['adapter_status']}/{trace_data['exchange_status']}): {reflection_msg}",
                ),
                token_estimate=max(1, len(reflection_msg.split()) + 10)
            )
            self.memory_lifecycle._write_memory(memory)
        except Exception:
            pass
            
        try:
            session_dir = self.root_dir / self.settings.sessions.root_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            trace_log_path = session_dir / "order_lifecycle_traces.jsonl"
            with open(trace_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_data) + "\n")
        except Exception:
            pass

        try:
            global_dir = self.root_dir / ".agent_memory"
            global_dir.mkdir(parents=True, exist_ok=True)
            global_log_path = global_dir / "order_lifecycle_traces.jsonl"
            with open(global_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_data) + "\n")
        except Exception:
            pass
            
        return response
