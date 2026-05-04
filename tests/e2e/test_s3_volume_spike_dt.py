"""
S3: Volume Spike dt Invariants E2E Scenario (TASK26).

Proves: volume_spike is time-normalized and stable across tick rates.

Invariants:
- P1: volume_spike dt-normalized
- Same vol/sec produces stable spike across dt=20ms, 200ms, 2000ms
- time_diff_ms used correctly in rate calculation
"""

from __future__ import annotations

import decimal
from collections import deque

import pytest

from tests.e2e.scenario_runner import ScenarioRunner


class TestS3VolumeSpikeDt:
    """S3: Volume spike is time-normalized."""
    
    def test_volume_spike_stable_across_tick_rates(
        self,
        scenario_runner: ScenarioRunner,
    ):
        """
        TASK26.S3: Same vol/sec produces stable spike across different dt.
        
        Setup:
        - Scenario A: 10 ticks/sec, vol=1 per tick → 10 vol/sec
        - Scenario B: 1 tick/sec, vol=10 per tick → 10 vol/sec
        - Result: volume_spike should be nearly identical
        """
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            ms_per_sec = 1000
            volume_sma_length = 10
            volume_spike_eps = decimal.Decimal("0.00000001")
            volume_spike_cap = decimal.Decimal("5")
        
        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Scenario A: 10 ticks/sec, vol=1 → rate = 1 / 0.1 = 10 vol/sec
        state_a = HotState(
            vol_hist=deque(maxlen=cfg.volume_sma_length),
            volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
        )
        for _ in range(10):
            engine.update_volume_spike(state_a, volume=decimal.Decimal("1"), time_diff_ms=100)
        spike_a = engine.compute_volume_spike(state_a)
        
        scenario_runner.record_event("VOLUME_SPIKE_A", {
            "dt_ms": 100,
            "vol_per_tick": 1,
            "implied_rate": "10 vol/sec",
            "spike": str(spike_a),
        })
        
        # Scenario B: 1 tick/sec, vol=10 → rate = 10 / 1.0 = 10 vol/sec  
        state_b = HotState(
            vol_hist=deque(maxlen=cfg.volume_sma_length),
            volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
        )
        for _ in range(10):
            engine.update_volume_spike(state_b, volume=decimal.Decimal("10"), time_diff_ms=1000)
        spike_b = engine.compute_volume_spike(state_b)
        
        scenario_runner.record_event("VOLUME_SPIKE_B", {
            "dt_ms": 1000,
            "vol_per_tick": 10,
            "implied_rate": "10 vol/sec",
            "spike": str(spike_b),
        })
        
        # Assert: spikes are nearly identical (same vol/sec)
        tolerance = decimal.Decimal("0.01")
        assert abs(spike_a - spike_b) < tolerance, \
            f"Volume spike must be stable across tick rates: A={spike_a}, B={spike_b}, diff={abs(spike_a - spike_b)}"
        
        scenario_runner.record_failure_mode(
            trigger="same vol/sec, different dt",
            expected=f"|spike_a - spike_b| < {tolerance}",
            observed=f"diff={abs(spike_a - spike_b)}",
            fail_closed=True,
        )
    
    def test_volume_spike_varying_dt_normalized(
        self,
        scenario_runner: ScenarioRunner,
    ):
        """
        TASK26.S3: volume_spike stable with varying dt (20ms, 200ms, 2000ms).
        """
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            ms_per_sec = 1000
            volume_sma_length = 10
            volume_spike_eps = decimal.Decimal("0.00000001")
            volume_spike_cap = decimal.Decimal("5")
        
        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        
        results = {}
        
        for dt_ms, vol_per_tick in [(20, 0.2), (200, 2), (2000, 20)]:
            # All produce 10 vol/sec
            state = HotState(
                vol_hist=deque(maxlen=cfg.volume_sma_length),
                volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
            )
            for _ in range(10):
                engine.update_volume_spike(state, volume=decimal.Decimal(str(vol_per_tick)), time_diff_ms=dt_ms)
            spike = engine.compute_volume_spike(state)
            results[dt_ms] = spike
            
            scenario_runner.record_event("VOLUME_SPIKE_DT", {
                "dt_ms": dt_ms,
                "vol_per_tick": vol_per_tick,
                "spike": str(spike),
            })
        
        # All should be within tolerance
        spikes = list(results.values())
        max_diff = max(spikes) - min(spikes)
        tolerance = decimal.Decimal("0.02")
        
        assert max_diff < tolerance, \
            f"Volume spike must be dt-normalized: max_diff={max_diff}, spikes={results}"
        
        scenario_runner.record_failure_mode(
            trigger="varying dt (20, 200, 2000ms) with same vol/sec",
            expected=f"max spike diff < {tolerance}",
            observed=f"max_diff={max_diff}",
            fail_closed=True,
        )
    
    def test_volume_spike_zero_dt_handled(
        self,
        scenario_runner: ScenarioRunner,
        metric_collector,
        monkeypatch,
    ):
        """
        TASK26.S3: Zero dt handled safely (no division by zero).
        """
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        monkeypatch.setattr(
            "apps.reference.telemetry.metrics.inc_data_quality_bad_dt",
            metric_collector.inc_data_quality_bad_dt,
        )
        
        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            volume_sma_length = 10
            volume_spike_eps = decimal.Decimal("0.00000001")
            volume_spike_cap = decimal.Decimal("5")
        
        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        
        state = HotState(
            vol_hist=deque(maxlen=cfg.volume_sma_length),
            volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
        )
        
        scenario_runner.record_event("VOLUME_SPIKE_ZERO_DT", {"dt_ms": 0})
        
        # This should NOT raise exception
        try:
            engine.update_volume_spike(state, volume=decimal.Decimal("10"), time_diff_ms=0)
            no_exception = True
        except ZeroDivisionError:
            no_exception = False
        
        assert no_exception, "Zero dt must be handled without exception"
        
        scenario_runner.record_failure_mode(
            trigger="dt_ms=0",
            expected="no exception, safe handling",
            observed=f"no_exception={no_exception}",
            fail_closed=no_exception,
        )
