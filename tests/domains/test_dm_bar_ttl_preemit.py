"""
DM-BAR-TTL-PREEMIT-01: Tests for _features_ready bar-aware TTL logic.

These tests verify that the DecisionMaking pre-emit gate correctly handles
bar and tick TTL using bar_ttl_ms, bar_event_age_mode, and the safety guard.
"""
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal


class MockClock:
    """Test clock for deterministic timing."""
    def __init__(self, now_ms: int):
        self._now_ms = now_ms
    
    def now_ms(self) -> int:
        return self._now_ms


class MockConfig:
    """Minimal mock config for _features_ready tests."""
    def __init__(self, bar_ttl_ms: int = 10000, bar_event_age_mode: str = "received"):
        self.system = MagicMock()
        self.system.market_data = MagicMock()
        self.system.market_data.bar_ttl_ms = bar_ttl_ms
        self.system.market_data.bar_event_age_mode = bar_event_age_mode


class TestFeaturesReadyBarTTL:
    """Test suite for DM-BAR-TTL-PREEMIT-01."""
    
    def _create_mock_dm(self, now_ms: int, bar_ttl_ms: int = 10000, 
                        bar_event_age_mode: str = "received",
                        features_ttl_sec: float = 30.0):
        """Create a minimal mock DecisionMaking with required attributes."""
        dm = MagicMock()
        dm._clock = MockClock(now_ms)
        dm.config = MockConfig(bar_ttl_ms, bar_event_age_mode)
        dm.features_ttl_sec = features_ttl_sec
        dm.logger = MagicMock()
        return dm

    def test_bar_not_stale_received_mode(self):
        """
        Test 1: Bar not stale in received mode.
        
        Scenario:
        - tf_sec=300 (5-min bar)
        - bar_close_ts = now - 81s (normal for bar delivery)
        - _received_ts = now - 1s (just received)
        - bar_event_age_mode = "received"
        - bar_ttl_ms = 10000 (10s)
        
        Expected: NOT stale (ready=True)
        """
        now_ms = 1768309581000  # ~13:06:21 UTC
        bar_close_ts = now_ms - 81_000  # 81 seconds ago
        received_ts = now_ms - 1_000    # 1 second ago
        
        dm = self._create_mock_dm(
            now_ms=now_ms,
            bar_ttl_ms=10000,
            bar_event_age_mode="received"
        )
        
        features_data = {
            "ts": bar_close_ts,
            "tf_sec": 300,
            "_received_ts": received_ts,
            "bar_close_ts": bar_close_ts,
        }
        
        # Import and call the actual method
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        result = DecisionMaking._features_ready(dm, "SOLUSDT", features_data)
        
        assert result is True, (
            f"Bar should NOT be stale: received 1s ago, ttl=10s, age_mode=received. "
            f"bar_close_ts was 81s ago but that's normal for 5-min bars."
        )

    def test_ancient_bar_rejected_even_in_received_mode(self):
        """
        Test 2: Very old bar must be rejected even in received mode.
        
        Scenario:
        - tf_sec=300 (5-min bar)
        - bar_close_ts = now - 1200s (20 minutes ago - ANCIENT)
        - _received_ts = now - 1s (just received)
        - bar_event_age_mode = "received"
        - bar_ttl_ms = 10000 (10s)
        
        Expected: STALE (ready=False) due to safety guard
        The safety guard rejects bars older than max(tf_sec*1000, bar_ttl_ms).
        max(300000, 10000) = 300000ms = 300s = 5 min.
        1200s > 300s → reject.
        """
        now_ms = 1768309581000
        bar_close_ts = now_ms - 1_200_000  # 1200 seconds (20 min) ago
        received_ts = now_ms - 1_000       # 1 second ago
        
        dm = self._create_mock_dm(
            now_ms=now_ms,
            bar_ttl_ms=10000,
            bar_event_age_mode="received"
        )
        
        features_data = {
            "ts": bar_close_ts,
            "tf_sec": 300,
            "_received_ts": received_ts,
            "bar_close_ts": bar_close_ts,
        }
        
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        result = DecisionMaking._features_ready(dm, "SOLUSDT", features_data)
        
        assert result is False, (
            f"Ancient bar (20 min old) should be rejected even in received mode. "
            f"Safety guard: max_bar_age = max(300s*1000, 10000) = 300000ms = 300s. "
            f"Actual bar age = 1200s > 300s → reject."
        )

    def test_tick_remains_strict(self):
        """
        Test 3: Tick-level features must use strict TTL.
        
        Scenario:
        - tf_sec=0 (tick, not bar)
        - ts = now - 3000ms (3 seconds ago)
        - features_ttl_sec = 2.0 (tick TTL = 2s)
        
        Expected: STALE (ready=False) because 3000ms > 2000ms
        """
        now_ms = 1768309581000
        tick_ts = now_ms - 3_000  # 3 seconds ago
        
        dm = self._create_mock_dm(
            now_ms=now_ms,
            bar_ttl_ms=10000,
            bar_event_age_mode="received",
            features_ttl_sec=2.0  # Strict 2s TTL for ticks
        )
        
        features_data = {
            "ts": tick_ts,
            "tf_sec": 0,  # TICK
        }
        
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        result = DecisionMaking._features_ready(dm, "SOLUSDT", features_data)
        
        assert result is False, (
            f"Tick 3s old should be stale with 2s TTL. "
            f"Tick TTL logic must remain strict."
        )

    def test_bar_close_ts_mode(self):
        """
        Test 4: Bar in close_ts mode respects bar_close_ts for age.
        
        Scenario:
        - tf_sec=300
        - bar_close_ts = now - 5s (5 seconds ago)
        - bar_event_age_mode = "close_ts"
        - bar_ttl_ms = 10000 (10s)
        
        Expected: NOT stale (5s < 10s TTL)
        """
        now_ms = 1768309581000
        bar_close_ts = now_ms - 5_000  # 5 seconds ago
        
        dm = self._create_mock_dm(
            now_ms=now_ms,
            bar_ttl_ms=10000,
            bar_event_age_mode="close_ts"  # Use close_ts mode
        )
        
        features_data = {
            "ts": bar_close_ts,
            "tf_sec": 300,
            "bar_close_ts": bar_close_ts,
        }
        
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        result = DecisionMaking._features_ready(dm, "SOLUSDT", features_data)
        
        assert result is True, (
            f"Bar 5s old in close_ts mode should pass 10s TTL."
        )

    def test_bar_close_ts_mode_stale(self):
        """
        Test 5: Bar in close_ts mode rejects old bars.
        
        Scenario:
        - tf_sec=300
        - bar_close_ts = now - 15s (15 seconds ago)
        - bar_event_age_mode = "close_ts"
        - bar_ttl_ms = 10000 (10s)
        
        Expected: STALE (15s > 10s TTL)
        """
        now_ms = 1768309581000
        bar_close_ts = now_ms - 15_000  # 15 seconds ago
        
        dm = self._create_mock_dm(
            now_ms=now_ms,
            bar_ttl_ms=10000,
            bar_event_age_mode="close_ts"
        )
        
        features_data = {
            "ts": bar_close_ts,
            "tf_sec": 300,
            "bar_close_ts": bar_close_ts,
        }
        
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        result = DecisionMaking._features_ready(dm, "SOLUSDT", features_data)
        
        assert result is False, (
            f"Bar 15s old in close_ts mode should fail 10s TTL."
        )
