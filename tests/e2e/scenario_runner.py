"""
Scenario Runner for E2E Trading Proof Pack (TASK26).

Generates synthetic events for E2E testing without heavy dependencies.
Uses only existing infrastructure from tests/runtime.
"""

from __future__ import annotations

import decimal
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from vfoundation.core.protocol import Message


@dataclass
class TimelineEvent:
    """Single event in the proof timeline."""
    ts_ms: int
    event_type: str
    payload: Dict[str, Any]
    source: str = "scenario_runner"
    
    def to_dict(self) -> dict:
        return {
            "ts_ms": self.ts_ms,
            "event_type": self.event_type,
            "payload": self.payload,
            "source": self.source,
        }


@dataclass
class MetricsSnapshot:
    """Collected metrics during scenario execution."""
    warmup_blocks: int = 0
    data_quality_drops: int = 0
    retry_scheduler_no_loop: int = 0
    intents_proposed: int = 0
    intents_dropped: int = 0
    guards_blocked: int = 0
    no_trade_reasons: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "warmup_blocks": self.warmup_blocks,
            "data_quality_drops": self.data_quality_drops,
            "retry_scheduler_no_loop": self.retry_scheduler_no_loop,
            "intents_proposed": self.intents_proposed,
            "intents_dropped": self.intents_dropped,
            "guards_blocked": self.guards_blocked,
            "no_trade_reasons": self.no_trade_reasons,
        }


@dataclass
class FailureMode:
    """Documented failure mode for proof artifacts."""
    trigger: str
    expected_behavior: str
    observed_behavior: str
    fail_closed: bool
    
    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger,
            "expected_behavior": self.expected_behavior,
            "observed_behavior": self.observed_behavior,
            "fail_closed": self.fail_closed,
        }


class MockFSM:
    """Mock FSM for capturing events without real infrastructure."""
    
    def __init__(self):
        self.emitted: List[tuple] = []
        self.listeners: Dict[str, List[Callable]] = {}
        
    def emit(
        self, 
        event_name: str, 
        payload: Optional[Dict[str, Any]] = None, 
        why: Optional[str] = None,
        data_ref: Optional[Any] = None,
    ) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))
        
    def listen(self, event_name: str, handler: Callable) -> None:
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(handler)
        
    def dispatch(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Manually dispatch event to registered listeners."""
        if event_name in self.listeners:
            msg = Message(op="EVT", verb=event_name.replace("EVT:", ""), pld=payload)
            for handler in self.listeners[event_name]:
                handler(msg)
                
    def get_events_by_verb(self, verb: str) -> List[tuple]:
        """Get all emitted events matching verb."""
        return [e for e in self.emitted if verb in e[0]]
    
    def has_event(self, event_name: str) -> bool:
        return any(event_name in e[0] for e in self.emitted)
    
    def clear(self) -> None:
        self.emitted.clear()


class ScenarioRunner:
    """
    Synthetic event generator for E2E scenarios.
    
    Generates tick/feature/regime events and collects proof artifacts.
    """
    
    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.fsm = MockFSM()
        self.timeline: List[TimelineEvent] = []
        self.metrics = MetricsSnapshot()
        self.failure_modes: List[FailureMode] = []
        self._start_ts_ms = int(time.time() * 1000)
        
    def now_ms(self) -> int:
        """Current timestamp in milliseconds."""
        return int(time.time() * 1000)
    
    def record_event(self, event_type: str, payload: Dict[str, Any], source: str = "scenario_runner") -> None:
        """Record event to proof timeline."""
        self.timeline.append(TimelineEvent(
            ts_ms=self.now_ms(),
            event_type=event_type,
            payload=payload,
            source=source,
        ))
        
    def record_failure_mode(
        self,
        trigger: str,
        expected: str,
        observed: str,
        fail_closed: bool,
    ) -> None:
        """Record observed failure mode."""
        self.failure_modes.append(FailureMode(
            trigger=trigger,
            expected_behavior=expected,
            observed_behavior=observed,
            fail_closed=fail_closed,
        ))
        
    def generate_tick(
        self,
        symbol: str,
        price: str,
        ts_ms: Optional[int] = None,
        bid_size: str = "100",
        ask_size: str = "100",
        buy_volume: str = "10",
        sell_volume: str = "10",
    ) -> Dict[str, Any]:
        """Generate synthetic tick event."""
        tick = {
            "symbol": symbol,
            "ts": ts_ms or self.now_ms(),
            "price": price,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
        }
        self.record_event("TICK", tick, "market_data")
        return tick
    
    def generate_tick_series(
        self,
        symbol: str,
        start_price: float,
        count: int,
        dt_ms: int = 100,
        price_delta: float = 0.01,
    ) -> List[Dict[str, Any]]:
        """Generate series of ticks with configurable dt."""
        ticks = []
        base_ts = self.now_ms()
        price = start_price
        
        for i in range(count):
            tick = self.generate_tick(
                symbol=symbol,
                price=str(price),
                ts_ms=base_ts + (i * dt_ms),
            )
            ticks.append(tick)
            price += price_delta * (1 if i % 2 == 0 else -1)  # Oscillate
            
        return ticks
    
    def generate_anchor_update(
        self,
        anchor: str,
        price: str,
        ts_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate anchor price update event."""
        payload = {
            "anchor": anchor,
            "price": price,
            "ts_ms": ts_ms or self.now_ms(),
        }
        self.record_event("ANCHOR_UPDATED", payload, "market_data")
        return payload
    
    def generate_warmup_state(
        self,
        full_ready: bool,
        ticks_seen: int,
        features_ready: bool = False,
        regime_ready: bool = False,
    ) -> Dict[str, Any]:
        """Generate warmup state for testing."""
        return {
            "full_ready": full_ready,
            "ticks_seen": ticks_seen,
            "features_ready": features_ready,
            "regime_ready": regime_ready,
        }
    
    def get_timeline_markdown(self) -> str:
        """Generate markdown timeline for proof artifacts."""
        lines = [
            f"# Scenario: {self.scenario_name}",
            f"",
            f"## Timeline",
            f"",
            f"| Timestamp | Event Type | Source | Payload (summary) |",
            f"|-----------|------------|--------|-------------------|",
        ]
        
        for event in self.timeline:
            payload_str = json.dumps(event.payload)[:50] + "..." if len(json.dumps(event.payload)) > 50 else json.dumps(event.payload)
            lines.append(f"| {event.ts_ms} | {event.event_type} | {event.source} | {payload_str} |")
            
        return "\n".join(lines)
    
    def get_metrics_json(self) -> str:
        """Generate JSON metrics snapshot."""
        return json.dumps({
            "scenario": self.scenario_name,
            "metrics": self.metrics.to_dict(),
        }, indent=2)
    
    def get_failure_modes_markdown(self) -> str:
        """Generate failure modes table."""
        lines = [
            f"# Failure Modes: {self.scenario_name}",
            f"",
            f"| Trigger | Expected | Observed | Fail-Closed |",
            f"|---------|----------|----------|-------------|",
        ]
        
        for fm in self.failure_modes:
            closed = "✅" if fm.fail_closed else "❌"
            lines.append(f"| {fm.trigger} | {fm.expected} | {fm.observed} | {closed} |")
            
        return "\n".join(lines)


# Metric increment hooks for monkeypatching
class MetricCollector:
    """Collects metrics increments during test execution."""
    
    def __init__(self, snapshot: MetricsSnapshot):
        self.snapshot = snapshot
        
    def inc_warmup_block(self, *, domain: str, reason: str) -> None:
        self.snapshot.warmup_blocks += 1
        key = f"{domain}:{reason}"
        self.snapshot.no_trade_reasons[key] = self.snapshot.no_trade_reasons.get(key, 0) + 1
        
    def inc_data_quality_drop(self, *, domain: str, reason: str) -> None:
        self.snapshot.data_quality_drops += 1
        
    def inc_data_quality_bad_dt(self, *, domain: str) -> None:
        self.snapshot.data_quality_drops += 1
        
    def inc_retry_scheduler_no_loop(self) -> None:
        self.snapshot.retry_scheduler_no_loop += 1
