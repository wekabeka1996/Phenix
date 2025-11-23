"""
Shadow Runtime Replay Harness
==============================

AB replay infrastructure for comparing expected vs actual adapter calls.
Used to validate ExecPosRuntimeV2 behavior against documented expectations.

Note: This does NOT execute legacy fsm.py. "Legacy" behavior is expressed
as expected adapter calls defined in tests.
"""
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import asyncio

from .runtime import ExecPosRuntimeV2
from .types import RuntimeEvent

@dataclass
class AdapterCall:
    """Record of an adapter call."""
    verb: str  # "place" | "cancel" | "close"
    symbol: str
    side: Optional[str] = None
    quantity: Optional[str] = None
    price: Optional[str] = None
    order_type: Optional[str] = None
    client_order_id: Optional[str] = None
    order_id: Optional[str] = None

@dataclass
class AdapterDiffReport:
    """Diff between expected and actual adapter calls."""
    matched: bool
    total_expected_calls: int
    total_actual_calls: int
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    only_in_expected: List[AdapterCall] = field(default_factory=list)
    only_in_actual: List[AdapterCall] = field(default_factory=list)

@dataclass
class ABReplayResult:
    """Result of AB replay run."""
    expected_adapter_calls: List[AdapterCall]
    actual_adapter_calls: List[AdapterCall]
    expected_summary: Dict[str, Any]
    actual_metrics: Dict[str, Any]
    diff: AdapterDiffReport

def diff_adapter_calls(
    expected_calls: List[AdapterCall],
    actual_calls: List[AdapterCall]
) -> AdapterDiffReport:
    """
    Compare expected vs actual adapter calls.
    
    Returns diff report with:
    - matched: True if perfect match
    - mismatches: List of differences by index
    - only_in_expected/only_in_actual: Calls present in only one side
    """
    total_expected = len(expected_calls)
    total_actual = len(actual_calls)
    mismatches = []
    
    # Compare up to min length
    min_len = min(total_expected, total_actual)
    for i in range(min_len):
        exp = expected_calls[i]
        act = actual_calls[i]
        
        differences = []
        
        if exp.verb != act.verb:
            differences.append(f"verb: expected={exp.verb}, actual={act.verb}")
        
        if exp.symbol != act.symbol:
            differences.append(f"symbol: expected={exp.symbol}, actual={act.symbol}")
        
        if exp.side != act.side:
            differences.append(f"side: expected={exp.side}, actual={act.side}")
        
        if exp.quantity != act.quantity:
            differences.append(f"quantity: expected={exp.quantity}, actual={act.quantity}")
        
        if exp.price != act.price:
            differences.append(f"price: expected={exp.price}, actual={act.price}")
        
        if exp.order_type != act.order_type:
            differences.append(f"order_type: expected={exp.order_type}, actual={act.order_type}")
        
        if differences:
            mismatches.append({
                "index": i,
                "expected": exp,
                "actual": act,
                "differences": differences
            })
    
    # Handle length differences
    only_in_expected = expected_calls[min_len:] if total_expected > total_actual else []
    only_in_actual = actual_calls[min_len:] if total_actual > total_expected else []
    
    matched = (
        total_expected == total_actual and
        len(mismatches) == 0
    )
    
    return AdapterDiffReport(
        matched=matched,
        total_expected_calls=total_expected,
        total_actual_calls=total_actual,
        mismatches=mismatches,
        only_in_expected=only_in_expected,
        only_in_actual=only_in_actual
    )

class ExecPosReplay:
    """
    Replay harness for ExecPosRuntimeV2.
    
    Feeds synthetic event sequences into shadow runtime and
    compares actual adapter calls against expected behavior.
    """
    
    def __init__(self, runtime_factory: Callable[[], ExecPosRuntimeV2]):
        """
        Args:
            runtime_factory: Function that creates ExecPosRuntimeV2 instance
                            with FakeRecordingAdapter
        """
        self.runtime_factory = runtime_factory
    
    def to_shadow_event(self, raw: Dict[str, Any]) -> RuntimeEvent:
        """Convert raw record to RuntimeEvent."""
        return RuntimeEvent(
            kind=raw["kind"],
            symbol=raw["symbol"],
            timestamp=raw.get("t", 0.0),
            payload={
                k: v for k, v in raw.items()
                if k not in ["t", "kind", "symbol"]
            }
        )
    
    async def run(
        self,
        raw_records: List[Dict[str, Any]],
        expected_adapter_calls: List[AdapterCall],
        expected_summary: Optional[Dict[str, Any]] = None
    ) -> ABReplayResult:
        """
        Run replay sequence through shadow runtime.
        
        Args:
            raw_records: List of raw event dicts
            expected_adapter_calls: Expected adapter calls (from documentation)
            expected_summary: Optional expected state summary
            
        Returns:
            ABReplayResult with actual vs expected comparison
        """
        # Create runtime (with FakeRecordingAdapter injected)
        runtime = self.runtime_factory()
        
        # Get adapter from runtime to extract calls later
        fake_adapter = runtime.execution_service.adapter
        
        # Process all events
        for raw in raw_records:
            event = self.to_shadow_event(raw)
            await runtime.handle(event)
        
        # Extract actual adapter calls
        actual_adapter_calls = [
            AdapterCall(
                verb=call.verb,
                symbol=call.symbol,
                side=call.kwargs.get("side"),
                quantity=call.kwargs.get("quantity"),
                price=call.kwargs.get("price"),
                order_type=call.kwargs.get("order_type"),
                client_order_id=call.kwargs.get("client_order_id"),
                order_id=call.kwargs.get("order_id")
            )
            for call in fake_adapter.calls
        ]
        
        # Get metrics
        actual_metrics = runtime.get_metrics()
        
        # Compute diff
        diff = diff_adapter_calls(expected_adapter_calls, actual_adapter_calls)
        
        return ABReplayResult(
            expected_adapter_calls=expected_adapter_calls,
            actual_adapter_calls=actual_adapter_calls,
            expected_summary=expected_summary or {},
            actual_metrics=actual_metrics,
            diff=diff
        )
