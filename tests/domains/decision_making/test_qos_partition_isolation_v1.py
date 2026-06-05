"""
QoS Partition Isolation Contract Tests (QOS-SPLIT-BRAIN-FIX)

These tests verify that QoS state is properly partitioned by strategy_id,
preventing cross-strategy rate-limiting interference.

Approach: Use _DummyDM pattern (bind methods from DecisionMaking onto minimal mock)
to avoid heavy __init__ dependencies.

Fix Reference: Phase 1 of PLAN_QOS_RETRY_PORTFOLIO_EXECUTION_2026_01_26.md
"""
import logging
from collections import defaultdict
from apps.reference.core.time.clock import MockClock


def _create_default_partition():
    """Factory for QoS partition state (matches DecisionMaking)."""
    return {
        "symbol_cooldowns": {},
        "symbol_intent_counts": {},
        "last_exposure_block": 0.0,
    }


class _DummyDM:
    """Minimal mock with only attributes needed for QoS methods."""
    
    def __init__(self, clock: MockClock):
        self.logger = logging.getLogger("tests.dm.qos_partition")
        self._clock = clock
        
        # QoS config
        self.qos_symbol_cooldown_sec = 5
        self.qos_max_intents_per_minute_per_symbol = 10
        self.qos_exposure_block_cooldown_sec = 30
        
        # QoS state - partitioned by strategy_id
        self._qos_state: dict = defaultdict(_create_default_partition)
        
        # Strategy cooldown overrides (optional)
        self._strategy_cooldown_overrides: dict = {}

        from apps.reference.domains.decision_making.gates.qos_rate_control import QoSRateControl
        self._qos = QoSRateControl(
            clock=self._clock,
            qos_state=self._qos_state,
            apply_to_strategies=set(),
            exposure_block_cooldown_sec=self.qos_exposure_block_cooldown_sec,
            max_intents_per_minute_per_symbol=self.qos_max_intents_per_minute_per_symbol,
            get_symbol_cooldown=self._get_symbol_cooldown,
            logger=self.logger,
        )
    
    def _get_symbol_cooldown(self, symbol: str, strategy_id: str = "aurora") -> float:
        """Get cooldown for symbol, respecting strategy overrides."""
        overrides = self._strategy_cooldown_overrides.get(strategy_id, {})
        return overrides.get(symbol, self.qos_symbol_cooldown_sec)


class TestQoSPartitionIsolation:
    """Test that QoS state is properly partitioned by strategy_id."""

    def test_qos_allow_uses_strategy_partition(self):
        """
        Verify _qos_allow reads from strategy-specific partition.
        
        Scenario:
        1. Strategy 'aurora' triggers cooldown for BTCUSDT
        2. Strategy 'mean_reversion' should NOT be blocked for same symbol
        """
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        
        # Bind _qos_allow from DecisionMaking
        qos_allow = DecisionMaking._qos_allow.__get__(dm, _DummyDM)
        
        # Manually set cooldown for aurora strategy
        dm._qos_state["aurora"]["symbol_cooldowns"]["BTCUSDT"] = clock.now_sec()
        
        # Advance time by 2 seconds (less than 5s cooldown)
        clock.advance_sec(2)
        
        # Aurora should be blocked (cooldown active)
        allowed_aurora, reason_aurora = qos_allow("BTCUSDT", strategy_id="aurora")
        assert allowed_aurora is False, "Aurora should be blocked by cooldown"
        
        # Mean Reversion should NOT be blocked (different partition)
        allowed_mr, reason_mr = qos_allow("BTCUSDT", strategy_id="mean_reversion")
        assert allowed_mr is True, "Mean Reversion should NOT be blocked by Aurora's cooldown"

    def test_qos_update_writes_to_correct_partition(self):
        """
        Verify _update_qos_state writes to strategy-specific partition.
        """
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        
        # Bind _update_qos_state from DecisionMaking
        update_qos = DecisionMaking._update_qos_state.__get__(dm, _DummyDM)
        
        # Update QoS state for aurora
        update_qos("BTCUSDT", strategy_id="aurora")
        
        # Verify aurora partition has the cooldown
        assert "BTCUSDT" in dm._qos_state["aurora"]["symbol_cooldowns"]
        
        # Verify mean_reversion partition is empty
        assert "BTCUSDT" not in dm._qos_state["mean_reversion"].get("symbol_cooldowns", {})

    def test_calculate_next_allowed_time_uses_strategy_partition(self):
        """
        Verify _calculate_next_allowed_time reads from strategy-specific partition.
        """
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        
        # Bind method
        calc_next = DecisionMaking._calculate_next_allowed_time.__get__(dm, _DummyDM)
        
        # Set cooldown for aurora (not for mean_reversion)
        dm._qos_state["aurora"]["symbol_cooldowns"]["BTCUSDT"] = clock.now_sec()
        
        # Advance time by 1 second
        clock.advance_sec(1)
        
        # Calculate next allowed for aurora (should be ~4s in future due to 5s cooldown)
        next_aurora = calc_next("BTCUSDT", strategy_id="aurora")
        
        # Calculate next allowed for mean_reversion (should be now, no cooldown)
        next_mr = calc_next("BTCUSDT", strategy_id="mean_reversion")
        
        # Aurora's next_allowed should be greater than mean_reversion's
        assert next_aurora > next_mr, \
            f"Aurora next_allowed ({next_aurora}) should be > mean_reversion ({next_mr})"

    def test_rate_limit_partition_isolation(self):
        """
        Verify rate limit counters are partitioned by strategy_id.
        """
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        
        # Bind method
        qos_allow = DecisionMaking._qos_allow.__get__(dm, _DummyDM)
        
        # Exhaust rate limit for aurora
        dm._qos_state["aurora"]["symbol_intent_counts"]["BTCUSDT"] = {
            "count": 10,  # max_intents_per_minute_per_symbol = 10
            "window_start": clock.now_sec()
        }
        
        # Aurora should be rate-limited
        allowed_aurora, reason_aurora = qos_allow("BTCUSDT", strategy_id="aurora")
        assert allowed_aurora is False, "Aurora should be rate-limited"
        
        # Mean Reversion should NOT be rate-limited
        allowed_mr, reason_mr = qos_allow("BTCUSDT", strategy_id="mean_reversion")
        assert allowed_mr is True, "Mean Reversion should NOT be rate-limited by Aurora"


class TestQoSPartitionDefaults:
    """Test that QoS partitions are correctly initialized."""

    def test_new_strategy_gets_fresh_partition(self):
        """
        Verify that accessing a new strategy_id creates a fresh partition.
        """
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        
        # Bind method
        qos_allow = DecisionMaking._qos_allow.__get__(dm, _DummyDM)
        
        # Access a new strategy partition
        new_strategy = "new_strategy_xyz"
        allowed, reason = qos_allow("BTCUSDT", strategy_id=new_strategy)
        
        # Should be allowed (fresh partition, no cooldowns)
        assert allowed is True
        
        # Partition should exist now (created by defaultdict)
        assert new_strategy in dm._qos_state
        assert "symbol_cooldowns" in dm._qos_state[new_strategy]


class TestQoSReasonCodes:
    """Test that QoS returns correct reason codes."""

    def test_cooldown_reason_code(self):
        """Verify cooldown rejection returns correct reason code."""
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        qos_allow = DecisionMaking._qos_allow.__get__(dm, _DummyDM)
        
        # Set cooldown
        dm._qos_state["aurora"]["symbol_cooldowns"]["BTCUSDT"] = clock.now_sec()
        clock.advance_sec(1)  # Still within 5s cooldown
        
        allowed, reason = qos_allow("BTCUSDT", strategy_id="aurora")
        
        assert allowed is False
        assert reason == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

    def test_rate_limit_reason_code(self):
        """Verify rate limit rejection returns correct reason code."""
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        clock = MockClock(start_ms=1700000000000)
        dm = _DummyDM(clock)
        qos_allow = DecisionMaking._qos_allow.__get__(dm, _DummyDM)
        
        # Exhaust rate limit
        dm._qos_state["aurora"]["symbol_intent_counts"]["BTCUSDT"] = {
            "count": 10,
            "window_start": clock.now_sec()
        }
        
        allowed, reason = qos_allow("BTCUSDT", strategy_id="aurora")
        
        assert allowed is False
        assert reason == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED
