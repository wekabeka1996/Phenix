"""
Runtime Scenario Runner & Test Doubles
=======================================

Deterministic harness for testing ExecPosRuntimeV2 under edge cases and concurrency scenarios.

TEST-ONLY infrastructure - do NOT import into production code.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from decimal import Decimal


@dataclass
class FakeClock:
    """
    Deterministic clock for reproducible timing tests.
    
    Time advances only via explicit tick() calls, not real wall-clock time.
    """
    current_ts: float = 0.0
    
    def now(self) -> float:
        """Get current timestamp."""
        return self.current_ts
    
    def tick(self, delta_seconds: float = 1.0) -> float:
        """Advance time by delta and return new timestamp."""
        self.current_ts += delta_seconds
        return self.current_ts
    
    def utcnow(self) -> datetime:
        """Get current time as datetime (for compatibility)."""
        return datetime.utcfromtimestamp(self.current_ts)


@dataclass
class AdapterCall:
    """Record of a call to FakeExecutionAdapter."""
    method: str
    args: tuple
    kwargs: dict
    timestamp: float


@dataclass  
class FakeExecutionAdapter:
    """
    Scriptable execution adapter for testing.
    
    Records all calls and can be programmed to succeed/fail with specific error codes.
    """
    clock: FakeClock
    call_history: List[AdapterCall] = field(default_factory=list)
    
    # Scripting: map (method_name, call_index) -> (success: bool, result/error)
    script: Dict[tuple, tuple] = field(default_factory=dict)
    
    async def place_order(self, **kwargs) -> Dict[str, Any]:
        """Place order - scriptable outcome."""
        call = AdapterCall("place_order", (), kwargs, self.clock.now())
        self.call_history.append(call)
        
        idx = sum(1 for c in self.call_history if c.method == "place_order") - 1
        key = ("place_order", idx)
        
        if key in self.script:
            success, result = self.script[key]
            if not success:
                raise RuntimeError(f"Adapter error: {result}")
            return result
        
        # Default: success with mock order_id
        return {
            "orderId": f"FAKE_ORDER_{idx}",
            "clientOrderId": kwargs.get("clientOrderId", f"FAKE_CLIENT_{idx}"),
            "status": "NEW",
            "symbol": kwargs.get("symbol", "UNKNOWN"),
        }
    
    async def cancel_order(self, **kwargs) -> Dict[str, Any]:
        """Cancel order - scriptable outcome."""
        call = AdapterCall("cancel_order", (), kwargs, self.clock.now())
        self.call_history.append(call)
        
        idx = sum(1 for c in self.call_history if c.method == "cancel_order") - 1
        key = ("cancel_order", idx)
        
        if key in self.script:
            success, result = self.script[key]
            if not success:
                raise RuntimeError(f"Adapter error: {result}")
            return result
        
        # Default: success
        return {"orderId": kwargs.get("orderId", "UNKNOWN"), "status": "CANCELED"}
    
    async def close_position(self, **kwargs) -> Dict[str, Any]:
        """Close position - scriptable outcome."""
        call = AdapterCall("close_position", (), kwargs, self.clock.now())
        self.call_history.append(call)
        
        idx = sum(1 for c in self.call_history if c.method == "close_position") - 1
        key = ("close_position", idx)
        
        if key in self.script:
            success, result = self.script[key]
            if not success:
                raise RuntimeError(f"Adapter error: {result}")
            return result
        
        # Default: success
        return {"symbol": kwargs.get("symbol", "UNKNOWN"), "status": "CLOSED"}
    
    def get_calls(self, method: Optional[str] = None) -> List[AdapterCall]:
        """Get call history, optionally filtered by method."""
        if method:
            return [c for c in self.call_history if c.method == method]
        return list(self.call_history)


@dataclass
class ScenarioStep:
    """
    Single step in a test scenario.
    
    Attributes:
        tick: Time offset (seconds from scenario start)
        event: RuntimeEvent to inject (dict with kind, payload, etc.)
        description: Human-readable step description
    """
    tick: float
    event: Dict[str, Any]
    description: str = ""


class RuntimeScenarioRunner:
    """
    Orchestrates ExecPosRuntimeV2 with fake adapter/clock through scripted scenarios.
    
    Usage:
        runner = RuntimeScenarioRunner()
        runner.add_step(0.0, {"kind": "ENTRY_INTENT", ...}, "User opens LONG")
        runner.add_step(1.0, {"kind": "TRADE_EXECUTED", ...}, "Fill arrives")
        await runner.run()
        assert_invariants(runner.get_state())
    """
    
    def __init__(self):
        self.clock = FakeClock()
        self.adapter = FakeExecutionAdapter(clock=self.clock)
        self.steps: List[ScenarioStep] = []
        self.runtime = None  # Will be ExecPosRuntimeV2 instance
        
    def add_step(self, tick: float, event: Dict[str, Any], description: str = ""):
        """Add a scenario step."""
        self.steps.append(ScenarioStep(tick=tick, event=event, description=description))
    
    def script_adapter(self, method: str, call_index: int, success: bool, result: Any):
        """
        Script adapter behavior for specific call.
        
        Args:
            method: Adapter method name ("place_order", "cancel_order", etc.)
            call_index: Which call (0-indexed)
            success: True = return result, False = raise with result as error message
            result: Return value (if success) or error message (if not)
        """
        self.adapter.script[(method, call_index)] = (success, result)
    
    async def run(self, runtime_factory: Callable = None):
        """
        Execute scenario steps in order.
        
        Args:
            runtime_factory: Optional factory function to create ExecPosRuntimeV2
                           with injected clock/adapter. If None, uses default.
        """
        # Sort steps by tick
        self.steps.sort(key=lambda s: s.tick)
        
        # Create runtime (would need dependency injection support in ExecPosRuntimeV2)
        if runtime_factory:
            self.runtime = runtime_factory(clock=self.clock, adapter=self.adapter)
        else:
            # For now, note that ExecPosRuntimeV2 needs DI support
            raise NotImplementedError(
                "RuntimeScenarioRunner requires ExecPosRuntimeV2 to support "
                "injectable clock/adapter for testing. Provide runtime_factory."
            )
        
        # Execute steps
        for step in self.steps:
            # Advance clock to step time
            self.clock.current_ts = step.tick
            
            # Inject event into runtime
            await self.runtime.handle(step.event)
    
    def get_state(self) -> Dict[str, Any]:
        """Get current runtime state for assertions."""
        if not self.runtime:
            return {}
        
        # Would call runtime.get_debug_state() or similar
        # For now, return placeholder
        return {
            "positions": getattr(self.runtime, "_positions_by_symbol", {}),
            "orders": getattr(self.runtime, "_orders", []),
            "metrics": getattr(self.runtime, "_metrics", {}),
        }
    
    def get_adapter_calls(self, method: Optional[str] = None) -> List[AdapterCall]:
        """Get adapter call history."""
        return self.adapter.get_calls(method)
