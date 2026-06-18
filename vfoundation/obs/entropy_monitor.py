"""
EntropyMonitor - System Anomaly Detection

Detects abnormal system behavior:
- Volume spikes (>100 events/minute)
- Error rate spikes (>50% ERR messages)
- Loop detection (same message repeated >10 times)
"""
from __future__ import annotations
import time
from collections.abc import Iterable
from typing import Dict, Tuple
from collections import defaultdict, deque
from vfoundation.core.protocol import Message


class EntropyMonitor:
    """
    Passive observer that tracks event patterns and detects anomalies.
    
    Uses sliding window approach to detect:
    1. Volume spikes - too many events in short time
    2. Error rate spikes - high percentage of ERR messages
    3. Loop patterns - same event repeated excessively
    """
    
    DEFAULT_LOOP_EXEMPT_PATTERNS = frozenset(
        {
            "EVT:MARKET_TICK_RECEIVED",
            "EVT:PORTFOLIO_STATE_UPDATED",
            "EVT:ACCOUNT_UPDATE_RECEIVED",
            "EVT:BALANCE_UPDATE_RECEIVED",
            "EVT:EXPOSURE_SUMMARY_UPDATED",
        }
    )

    def __init__(
        self, 
        window_sec: int = 60,
        volume_threshold: int = 100,
        error_rate_threshold: float = 0.5,
        loop_threshold: int = 10,
        loop_exempt_patterns: Iterable[str] | None = None,
    ):
        """
        Args:
            window_sec: Sliding window duration in seconds
            volume_threshold: Max events per window before spike
            error_rate_threshold: Max ERR rate (0.0-1.0) before spike
            loop_threshold: Max identical events before loop detection
            loop_exempt_patterns: Expected periodic patterns excluded from loop
                detection. They still contribute to volume and error metrics.
        """
        self.window_sec = window_sec
        self.volume_threshold = volume_threshold
        self.error_rate_threshold = error_rate_threshold
        self.loop_threshold = loop_threshold
        self.loop_exempt_patterns = frozenset(
            self.DEFAULT_LOOP_EXEMPT_PATTERNS
            if loop_exempt_patterns is None
            else loop_exempt_patterns
        )
        
        # Event tracking (timestamp, op, verb, rid)
        self.events: deque[Tuple[float, str, str, str]] = deque()
        
        # Loop detection: (op:verb) -> count in current window
        self.pattern_counts: Dict[str, int] = defaultdict(int)
        
    def track_event(self, msg: Message) -> None:
        """
        Track an event for entropy analysis.
        Thread-safe for single-producer (FSMCore).
        """
        now = time.time()
        event = (now, msg.op, msg.verb, msg.rid)
        self.events.append(event)
        
        # Track pattern frequency
        pattern_key = f"{msg.op}:{msg.verb}"
        self.pattern_counts[pattern_key] += 1
        
        # Cleanup old events outside window
        self._cleanup_old_events(now)
        
    def detect_spike(self) -> Tuple[bool, str]:
        """
        Detect if system is experiencing anomalous behavior.
        
        Returns:
            (spike_detected: bool, reason: str)
        """
        now = time.time()
        self._cleanup_old_events(now)
        
        # Check 1: Volume spike
        if len(self.events) > self.volume_threshold:
            return (True, f"VOLUME_SPIKE: {len(self.events)} events in {self.window_sec}s (threshold: {self.volume_threshold})")
        
        # Check 2: Error rate spike
        if self.events:
            err_count = sum(1 for e in self.events if e[1] == "ERR")
            error_rate = err_count / len(self.events)
            if error_rate > self.error_rate_threshold:
                return (True, f"ERROR_SPIKE: {error_rate:.1%} error rate (threshold: {self.error_rate_threshold:.1%})")
        
        # Check 3: Loop detection
        for pattern, count in self.pattern_counts.items():
            if pattern in self.loop_exempt_patterns:
                continue
            if count > self.loop_threshold:
                return (True, f"LOOP_DETECTED: {pattern} repeated {count} times (threshold: {self.loop_threshold})")
        
        return (False, "")
    
    def get_metrics(self) -> Dict[str, any]:
        """Get current entropy metrics for observability"""
        now = time.time()
        self._cleanup_old_events(now)
        
        total = len(self.events)
        err_count = sum(1 for e in self.events if e[1] == "ERR") if self.events else 0
        error_rate = err_count / total if total > 0 else 0.0
        
        # Get top patterns
        top_patterns = sorted(
            self.pattern_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
        
        return {
            "window_sec": self.window_sec,
            "total_events": total,
            "error_count": err_count,
            "error_rate": error_rate,
            "volume_threshold": self.volume_threshold,
            "error_rate_threshold": self.error_rate_threshold,
            "top_patterns": dict(top_patterns),
            "unique_patterns": len(self.pattern_counts),
            "loop_exempt_patterns": sorted(self.loop_exempt_patterns),
        }
    
    def reset(self) -> None:
        """Reset all tracking (useful for testing)"""
        self.events.clear()
        self.pattern_counts.clear()
    
    def _cleanup_old_events(self, now: float) -> None:
        """Remove events outside sliding window"""
        cutoff_time = now - self.window_sec
        
        # Remove old events from deque
        while self.events and self.events[0][0] < cutoff_time:
            old_event = self.events.popleft()
            # Decrement pattern count
            pattern_key = f"{old_event[1]}:{old_event[2]}"
            self.pattern_counts[pattern_key] -= 1
            if self.pattern_counts[pattern_key] <= 0:
                del self.pattern_counts[pattern_key]
