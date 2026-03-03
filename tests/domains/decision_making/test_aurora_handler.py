"""
Tests for AuroraHandler — Stateful Strategy Handler.

Verifies:
1. Regime caching from EVT:REGIME_DETECTED
2. Warmup tracking
3. Side bias history management
4. Signal emission with readiness contract
"""
import pytest
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.aurora_handler import (
    AuroraHandler,
    SymbolState,
)


class TestAuroraHandlerInit:
    """Tests for handler initialization."""

    def test_handler_creates_with_config(self):
        """Handler should initialize with config and emit function."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.15,
                        side_bias_window_sec=300,
                        side_bias_target_ratio=0.7,
                        side_bias_penalty_factor=0.3,
                        side_bias_min_intents=15,
                        regime_threshold_multipliers={"DEFAULT": 1.0, "HIGH_VOL": 1.5},
                        direction_strength_scoring=SimpleNamespace(
                            directional_features=["obi", "tfi"],
                            strength_features=["volume_spike"],
                            strength_alpha=0.6,
                            strength_cap=2.0,
                        ),
                        signals=SimpleNamespace(
                            normalize_signals_mode="signed_v2",
                            enable_new_metrics=True,
                            delta_price_cap_pct=0.01,
                        ),
                    ),
                    assets={},
                )
            )
        )
        emit_fn = MagicMock()
        
        handler = AuroraHandler(config=config, emit_fn=emit_fn)
        
        assert handler.signal_threshold == Decimal("0.15")
        assert handler.side_bias_window_sec == 300.0
        assert handler.side_bias_target_ratio == 0.7
        assert handler.regime_thresholds["HIGH_VOL"] == 1.5
        assert handler.timeframe_sec == 300  # Verify mandatory field


class TestRegimeCaching:
    """Tests for regime state caching."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=SimpleNamespace(
                            normalize_signals_mode="signed_v2",
                            enable_new_metrics=True,
                            delta_price_cap_pct=0.02,
                        ),
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_regime_detected_updates_cache(self, handler):
        """on_regime_detected should cache regime state."""
        event = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 0.85,
            "ts_ms": 1700000000000,
            "warmup": {"full_ready": True, "ticks_seen": 100},
        }
        
        handler.on_regime_detected(event)
        
        state = handler._symbol_states["BTCUSDT"]
        assert state.regime == "TREND_UP"
        assert state.regime_confidence == 0.85
        # SSOT: warmup comes from CMD:PROCESS_STRATEGY only (REGIME_DETECTED must NOT update warmup)
        assert state.warmup_full_ready is False
        assert state.warmup_ticks_seen == 0

    def test_regime_detected_handles_missing_symbol(self, handler):
        """on_regime_detected should handle missing symbol gracefully."""
        event = {"regime": "TREND_UP"}
        handler.on_regime_detected(event)  # Should not raise


class TestSideBiasHistory:
    """Tests for side bias history tracking."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=60,  # 60s window for easy testing
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=5,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=SimpleNamespace(
                            normalize_signals_mode="signed_v2",
                            enable_new_metrics=True,
                            delta_price_cap_pct=0.02,
                        ),
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_get_side_bias_state_counts_history(self, handler):
        """_get_side_bias_state should count recent history."""
        now = time.time()
        state = handler._symbol_states["BTCUSDT"]
        
        # Add some history
        state.buy_timestamps = [now - 10, now - 20, now - 30]
        state.sell_timestamps = [now - 5, now - 15]
        
        bias_state = handler._get_side_bias_state("BTCUSDT")
        
        assert bias_state.buy_count == 3
        assert bias_state.sell_count == 2

    def test_get_side_bias_state_filters_old_entries(self, handler):
        """_get_side_bias_state should filter entries outside window."""
        now = time.time()
        state = handler._symbol_states["BTCUSDT"]
        
        # Add some history - some outside 60s window
        state.buy_timestamps = [now - 10, now - 100]  # One inside, one outside
        state.sell_timestamps = [now - 5, now - 200]  # One inside, one outside
        
        bias_state = handler._get_side_bias_state("BTCUSDT")
        
        assert bias_state.buy_count == 1  # Only recent one
        assert bias_state.sell_count == 1  # Only recent one

    def test_update_side_bias_adds_timestamp(self, handler):
        """_update_side_bias should add timestamp to history."""
        handler._update_side_bias("BTCUSDT", "buy")
        handler._update_side_bias("BTCUSDT", "sell")
        handler._update_side_bias("BTCUSDT", "buy")
        
        state = handler._symbol_states["BTCUSDT"]
        
        assert len(state.buy_timestamps) == 2
        assert len(state.sell_timestamps) == 1


@pytest.mark.skip(reason="LEGACY: Uses deprecated on_features_calculated API. TODO: Migrate to on_process_strategy (T2B-03)")
class TestSignalEmission:
    """Tests for signal emission with readiness contract."""

    @pytest.fixture
    def handler_with_symbol(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=18,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=SimpleNamespace(
                            directional_features=["obi", "tfi"],
                        strength_features=[],
                        strength_alpha=0.5,
                        strength_cap=1.5,
                    ),
                        signals=SimpleNamespace(
                            normalize_signals_mode="signed_v2",
                            enable_new_metrics=True,
                            delta_price_cap_pct=0.005,
                        ),
                        signal_weights={"obi": 0.5, "tfi": 0.5},
                        feature_neutrals={"obi": 0.0, "tfi": 0.0},
                        essential_features=["obi", "tfi"],
                    ),
                    assets={
                        "BTCUSDT": SimpleNamespace(
                            enabled=True,
                            weights={"obi": 0.5, "tfi": 0.5},
                            feature_neutrals={"obi": 0.0, "tfi": 0.0},
                            essential_features=["obi", "tfi"],
                        ),
                    },
                )
            )
        )
        emit_fn = MagicMock()
        handler = AuroraHandler(config=config, emit_fn=emit_fn)
        
        # Set up warmup
        handler._symbol_states["BTCUSDT"].warmup_full_ready = True
        handler._symbol_states["BTCUSDT"].regime = "DEFAULT"
        
        return handler, emit_fn

    def test_signal_includes_readiness(self, handler_with_symbol):
        """Emitted signal should include readiness.warmup_ok."""
        handler, emit_fn = handler_with_symbol
        
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # T2B-01: Must match handler.timeframe_sec
            "features": {"price": "50000", "obi": 0.8, "tfi": 0.6},
            "warmup": {"full_ready": True, "ready": {"obi": True, "tfi": True}},
        }
        
        handler.on_features_calculated(event)
        
        if emit_fn.call_count > 0:
            call_args = emit_fn.call_args
            payload = call_args[0][1]
            assert "readiness" in payload
            assert payload["readiness"]["warmup_ok"] is True

    def test_skips_when_warmup_not_ready(self, handler_with_symbol):
        """Handler should fail-closed and emit an explicit block reason when warmup not ready."""
        handler, emit_fn = handler_with_symbol
        handler._symbol_states["BTCUSDT"].warmup_full_ready = False
        
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # T2B-01: Must match handler.timeframe_sec
            "features": {"price": "50000", "obi": 0.8, "tfi": 0.6},
            "warmup": {"full_ready": False, "ready": {"obi": True, "tfi": True}},
        }
        
        handler.on_features_calculated(event)

        assert emit_fn.call_count == 1
        evt_name, payload = emit_fn.call_args[0]
        assert evt_name == "EVT:STRATEGY_DECISION_BLOCKED"
        assert "READINESS" in str(payload.get("reason", ""))

    def test_skips_disabled_symbol(self, handler_with_symbol):
        """Handler should skip disabled symbols."""
        handler, emit_fn = handler_with_symbol
        handler.config.strategies.aurora.assets["BTCUSDT"].enabled = False
        
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # T2B-01: Must match handler.timeframe_sec
            "features": {"price": "50000", "obi": 0.8, "tfi": 0.6},
            "warmup": {"full_ready": True, "ready": {"obi": True, "tfi": True}},
        }
        
        handler.on_features_calculated(event)
        
        assert emit_fn.call_count == 0
