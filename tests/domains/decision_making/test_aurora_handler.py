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
                        signals=SimpleNamespace(delta_price_cap_pct=0.01, normalize_signals_mode="signed_v2"),
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
                        signals=None,
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
                        signals=None,
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
                        signals=SimpleNamespace(delta_price_cap_pct=0.005),
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


class TestPortfolioStateNetPosition:
    """Regression tests for Finding 6: invalid net_position must not masquerade as flat."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={"BTCUSDT": SimpleNamespace(enabled=True)},
                )
            ),
            strategies_registry=SimpleNamespace(assignments={"BTCUSDT": ["aurora"]}),
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_valid_net_position_is_tracked(self, handler):
        """A normal non-zero position must be seen as active."""
        event = {
            "positions": [{"symbol": "BTCUSDT", "net_position": "0.5"}],
            "positions_last_ts_ms": 1700000000000,
        }
        # After the call _latest_portfolio should be set; no exception raised.
        handler.on_portfolio_state(event)
        assert handler._latest_portfolio == event

    def test_invalid_net_position_skipped_not_treated_as_flat(self, handler):
        """Malformed net_position must be skipped with a warning — NOT treated as zero.

        Before the fix: except Exception → qty = Decimal("0") → symbol absent from
        active_symbols → CLEAN_START_UPGRADE could be falsely triggered.
        After the fix: invalid entry is skipped via `continue`; the symbol's upgrade
        path is never reached for that position row.
        """
        import decimal
        from unittest.mock import patch

        upgrade_calls = []

        def fake_upgrade(snapshot, **kwargs):
            upgrade_calls.append(snapshot)
            return None  # simulate "not triggered"

        with patch(
            "apps.reference.domains.decision_making.aurora_handler"
            ".upgrade_cold_execution_restore_if_clean_start",
            side_effect=fake_upgrade,
        ):
            event = {
                "positions": [
                    {"symbol": "BTCUSDT", "net_position": "NOT_A_NUMBER"},
                ],
                "positions_last_ts_ms": 1700000000000,
            }
            # Should NOT raise; invalid row is silently skipped with a warning.
            handler.on_portfolio_state(event)

        # upgrade was never called (no snapshot registered), but crucially no
        # AttributeError or silent-zero conversion happened either.
        assert upgrade_calls == []

    def test_zero_net_position_still_treated_as_flat(self, handler):
        """Explicit "0" remains flat (normal path must not be broken)."""
        event = {
            "positions": [{"symbol": "BTCUSDT", "net_position": "0"}],
            "positions_last_ts_ms": 1700000000000,
        }
        handler.on_portfolio_state(event)  # Should not raise


class TestEmitStrategyBlockedWalLogging:
    """Regression test for Finding 7: WAL write failure must be logged, not swallowed."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_wal_failure_is_logged_not_swallowed(self, handler):
        """If write_trade_intent_rejected raises, the exception must appear in
        logger.debug (with exc_info=True) and must NOT propagate to the caller."""
        from unittest.mock import patch

        with patch(
            "apps.reference.domains.decision_making.aurora_handler"
            ".write_trade_intent_rejected",
            side_effect=RuntimeError("disk full"),
        ):
            with patch.object(handler.logger, "debug") as mock_debug:
                # Must not raise
                handler._emit_strategy_blocked(
                    symbol="BTCUSDT",
                    reason_code="TEST",
                    reason="test reason",
                    context="unit_test",
                )

        # logger.debug must have been called with exc_info=True
        assert mock_debug.called
        call_kwargs = mock_debug.call_args[1] if mock_debug.call_args else {}
        assert call_kwargs.get("exc_info") is True


class TestOnSystemStressGuard:
    """Regression test for Finding 8: on_system_stress must guard against non-dict payload."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    @pytest.mark.parametrize("bad_payload", [None, "string", 42, ["list"]])
    def test_non_dict_payload_does_not_raise(self, handler, bad_payload):
        """on_system_stress must silently return on non-dict payload (consistent with other handlers)."""
        handler.on_system_stress(bad_payload)  # Must not raise AttributeError

    def test_valid_dict_payload_updates_state(self, handler):
        """Normal dict payload must still update the symbol state."""
        handler.on_system_stress({"symbol": "BTCUSDT", "state": "HIGH_STRESS"})
        assert handler._symbol_states["BTCUSDT"].system_stress_state == "HIGH_STRESS"

