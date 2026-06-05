"""
S2: MacroSync Async Ticks E2E Scenario (TASK26).

Proves: macro_sync correlation handles async anchor arrivals correctly.

Invariants:
- P1: macro_sync not "dead" - explicit insufficient_data, not silent 0.5
- Anchors arrive at different frequencies
- Tail alignment logic works correctly
"""

from __future__ import annotations

import decimal
from collections import deque

import pytest

from tests.e2e.scenario_runner import ScenarioRunner


class TestS2MacroSyncAsync:
    """S2: MacroSync handles async anchors correctly."""
    
    def test_macro_sync_insufficient_data_returns_explicit_flag(
        self,
        scenario_runner: ScenarioRunner,
    ):
        """
        TASK26.S2: When n < min_buffer, return insufficient_data=true, not 0.5.
        """
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            ms_per_sec = 1000
            macro_sync_enabled = True
            macro_sync_anchors = ["BTCUSDT"]
            macro_sync_min_buffer = 10  # Require 10 samples
            macro_sync_window = 200
            macro_sync_align_mode = "tail_min_len"
            macro_sync_ttl_ms = 10_000
            macro_sync_time_diff_threshold_ms = 10_000
        
        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Only add 5 samples (less than min_buffer=10)
        state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
        
        base_price = decimal.Decimal("100")
        for i in range(5):  # Only 5 < 10 required
            price = base_price * (1 + decimal.Decimal(str(0.001 * i)))
            engine.update_macro_sync_buffer(state, price, 200)
        
        scenario_runner.record_event("MACRO_SYNC_BUFFER", {
            "samples": 5,
            "min_required": 10,
        })
        
        # Compute with insufficient data
        now_ms = 1_000_000
        anchor_prices = {"BTCUSDT": deque([decimal.Decimal("1000")] * 5, maxlen=200)}
        
        phi = engine.compute_macro_sync(
            state,
            anchor_prices,
            anchor_last_ts_ms={"BTCUSDT": now_ms},
            current_ts_ms=now_ms,
        )
        
        scenario_runner.record_event("MACRO_SYNC_RESULT", {
            "phi": str(phi),
            "macro_sync_ready": state.macro_sync_ready,
            "not_ready_reason": getattr(state, "macro_sync_not_ready_reason", None),
        }, source="feature_engineering")
        
        # Assert: NOT silent 0.5 - must have explicit reason
        assert state.macro_sync_ready is False, "macro_sync_ready must be False with insufficient data"
        assert hasattr(state, "macro_sync_not_ready_reason"), "Must have explicit not_ready_reason"
        assert state.macro_sync_not_ready_reason is not None, "not_ready_reason must be set"
        
        scenario_runner.record_failure_mode(
            trigger="n < min_buffer (5 < 10)",
            expected="macro_sync_ready=false + reason",
            observed=f"ready={state.macro_sync_ready}, reason={getattr(state, 'macro_sync_not_ready_reason', None)}",
            fail_closed=not state.macro_sync_ready,
        )
    
    def test_macro_sync_stale_anchor_explicit_block(
        self,
        scenario_runner: ScenarioRunner,
    ):
        """
        TASK26.S2: Stale anchor data (TTL expired) blocks with explicit reason.
        """
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            ms_per_sec = 1000
            macro_sync_enabled = True
            macro_sync_anchors = ["BTCUSDT"]
            macro_sync_min_buffer = 5
            macro_sync_window = 200
            macro_sync_align_mode = "tail_min_len"
            macro_sync_ttl_ms = 500  # Short TTL
            macro_sync_time_diff_threshold_ms = 10_000
        
        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Sufficient data
        state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
        for i in range(20):
            engine.update_macro_sync_buffer(state, decimal.Decimal("100") + decimal.Decimal(str(i * 0.1)), 100)
        
        scenario_runner.record_event("MACRO_SYNC_BUFFER", {
            "samples": 20,
            "anchor_ttl_ms": 500,
        })
        
        # Anchor is STALE (last update older than TTL)
        current_ts_ms = 10_000
        stale_anchor_ts = current_ts_ms - cfg.macro_sync_ttl_ms - 100  # 100ms past TTL
        
        anchor_prices = {"BTCUSDT": deque([decimal.Decimal("1000")] * 20, maxlen=200)}
        
        phi = engine.compute_macro_sync(
            state,
            anchor_prices,
            anchor_last_ts_ms={"BTCUSDT": stale_anchor_ts},
            current_ts_ms=current_ts_ms,
        )
        
        scenario_runner.record_event("MACRO_SYNC_RESULT", {
            "phi": str(phi),
            "macro_sync_ready": state.macro_sync_ready,
            "not_ready_reason": getattr(state, "macro_sync_not_ready_reason", None),
            "anchor_age_ms": current_ts_ms - stale_anchor_ts,
        }, source="feature_engineering")
        
        # Assert: blocked due to stale anchor
        assert state.macro_sync_ready is False, "macro_sync must be blocked with stale anchor"
        assert "fresh" in str(getattr(state, "macro_sync_not_ready_reason", "")).lower() or \
               "stale" in str(getattr(state, "macro_sync_not_ready_reason", "")).lower() or \
               state.macro_sync_not_ready_reason == "no_fresh_anchor_data", \
               f"Reason must indicate stale/fresh issue, got: {state.macro_sync_not_ready_reason}"
        
        scenario_runner.record_failure_mode(
            trigger=f"anchor_age > TTL ({current_ts_ms - stale_anchor_ts}ms > {cfg.macro_sync_ttl_ms}ms)",
            expected="macro_sync_ready=false, reason=stale",
            observed=f"ready={state.macro_sync_ready}, reason={state.macro_sync_not_ready_reason}",
            fail_closed=not state.macro_sync_ready,
        )
    
    def test_macro_sync_valid_correlation_not_neutral(
        self,
        scenario_runner: ScenarioRunner,
    ):
        """
        TASK26.S2: Valid data produces non-neutral correlation.
        """
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            ms_per_sec = 1000
            macro_sync_enabled = True
            macro_sync_anchors = ["ANCHOR"]
            macro_sync_min_buffer = 5
            macro_sync_window = 200
            macro_sync_align_mode = "tail_min_len"
            macro_sync_ttl_ms = 10_000
            macro_sync_time_diff_threshold_ms = 10_000
        
        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Correlated returns: symbol follows anchor
        returns = [0.01, -0.004, 0.02, -0.01, 0.012, 0.006, -0.008, 0.015] * 5
        
        def prices_from_returns(start, rets):
            price = start
            prices = [price]
            for r in rets:
                price = price * (1 + decimal.Decimal(str(r)))
                prices.append(price)
            return prices
        
        sym_prices = prices_from_returns(decimal.Decimal("100"), returns)
        anchor_prices = prices_from_returns(decimal.Decimal("1000"), returns)
        
        state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
        for p in sym_prices:
            engine.update_macro_sync_buffer(state, p, 100)
        
        now_ms = 1_000_000
        phi = engine.compute_macro_sync(
            state,
            {"ANCHOR": deque(anchor_prices, maxlen=cfg.macro_sync_window)},
            anchor_last_ts_ms={"ANCHOR": now_ms},
            current_ts_ms=now_ms,
        )
        
        scenario_runner.record_event("MACRO_SYNC_RESULT", {
            "phi": str(phi),
            "macro_sync_ready": state.macro_sync_ready,
            "expected": "> 0.7 (high correlation)",
        }, source="feature_engineering")
        
        # Assert: valid correlation, not default 0.5
        assert state.macro_sync_ready is True, "macro_sync must be ready with valid data"
        assert phi != cfg.neutral_value, f"phi must not be neutral 0.5, got {phi}"
        assert phi > decimal.Decimal("0.7"), f"Highly correlated returns should give phi > 0.7, got {phi}"
        
        scenario_runner.record_failure_mode(
            trigger="valid correlated anchor/symbol data",
            expected="macro_sync_ready=true, phi > 0.7",
            observed=f"ready={state.macro_sync_ready}, phi={phi}",
            fail_closed=True,  # Ready is correct behavior here
        )
