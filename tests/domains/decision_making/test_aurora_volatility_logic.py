"""
Unit tests for Aurora Volatility-Based Limit Entry Logic.

Tests:
1. Calculation accuracy (offset applied correctly)
2. Fail-closed behavior (missing ATR aborts signal)
3. Default fallback (unknown regime uses DEFAULT multiplier)
"""
import decimal
import pytest
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch


class MockScoringResult:
    """Mock scoring result for testing."""

    def __init__(self, side: str = "buy", score: float = 0.5):
        self.side = side
        self.score = Decimal(str(score))
        self.thr_buy = Decimal("0.1")
        self.thr_sell = Decimal("-0.1")
        self.regime = "DEFAULT"
        self.why_chain = ["test"]
        self.psi_vector = {}


class TestVolatilityEntryLogic:
    """Tests for volatility-based limit entry pricing."""

    @pytest.fixture
    def handler(self):
        """Create handler with volatility_entry_logic enabled for TESTUSDT."""
        import sys
        sys.path.insert(0, '/home/wekabeka/Музыка/Phenix')

        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

        config = SimpleNamespace(
            basis_tf_sec=300,
            liveness_factor=3,
            strategies_registry=None,
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=18,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                        holding_period=None,
                        reentry_cooldown_sec=60,
                        anti_churn=None,
                        gates=None,
                        neutral_threshold=0.05,
                    ),
                    assets={
                        "TESTUSDT": SimpleNamespace(
                            enabled=True,
                            weights=None,
                            volatility_entry_logic=SimpleNamespace(
                                enabled=True,
                                regime_multipliers={
                                    "HIGH_VOLATILITY": 0.6,
                                    "LOW_VOLATILITY": 0.1,
                                    "DEFAULT": 0.2,
                                }
                            ),
                        ),
                    },
                )
            ),
            domains=SimpleNamespace(
                feature_engineering=SimpleNamespace(
                    warmup=SimpleNamespace(enforcement_mode="warn_only")
                )
            ),
        )

        emit_fn = MagicMock()
        handler = AuroraHandler(config=config, emit_fn=emit_fn)

        # Set up warmup state
        handler._symbol_states["TESTUSDT"].warmup_full_ready = True
        handler._symbol_states["TESTUSDT"].regime = "HIGH_VOLATILITY"
        handler._symbol_states["TESTUSDT"].last_regime_heartbeat_ms = int(
            handler.monotonic_fn() * 1000)

        return handler, emit_fn

    def test_long_entry_offset_below_anchor(self, handler):
        """
        Test Case 1a: LONG entry should be anchor - offset.

        Given:
            price = 100, atr = 2, regime = HIGH_VOLATILITY (mult=0.6)
        Expected:
            offset = 2 * 0.6 = 1.2
            entry_price = 100 - 1.2 = 98.8
        """
        handler_obj, emit_fn = handler

        result = MockScoringResult(side="buy", score=0.5)
        features = {"price": "100", "volatility": {"atr_14": 2.0}}

        handler_obj._emit_signal(
            symbol="TESTUSDT",
            result=result,
            features=features,
            source_event={},
        )

        assert emit_fn.call_count >= 1

        # Find the STRATEGY_SIGNAL_PRODUCED call
        signal_call = None
        for call in emit_fn.call_args_list:
            event_name = call[0][0]
            if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
                signal_call = call
                break

        assert signal_call is not None, "EVT:STRATEGY_SIGNAL_PRODUCED was not emitted"

        payload = signal_call[0][1]
        entry_price = Decimal(payload["price_ctx"]["entry_price"])

        # 100 - (2 * 0.6) = 98.8
        assert entry_price == Decimal(
            "98.8"), f"Expected 98.8, got {entry_price}"

    def test_short_entry_offset_above_anchor(self, handler):
        """
        Test Case 1b: SHORT entry should be anchor + offset.

        Given:
            price = 100, atr = 2, regime = HIGH_VOLATILITY (mult=0.6)
        Expected:
            offset = 2 * 0.6 = 1.2
            entry_price = 100 + 1.2 = 101.2
        """
        handler_obj, emit_fn = handler

        result = MockScoringResult(side="sell", score=-0.5)
        features = {"price": "100", "volatility": {"atr_14": 2.0}}

        handler_obj._emit_signal(
            symbol="TESTUSDT",
            result=result,
            features=features,
            source_event={},
        )

        signal_call = None
        for call in emit_fn.call_args_list:
            event_name = call[0][0]
            if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
                signal_call = call
                break

        assert signal_call is not None, "EVT:STRATEGY_SIGNAL_PRODUCED was not emitted"

        payload = signal_call[0][1]
        entry_price = Decimal(payload["price_ctx"]["entry_price"])

        # 100 + (2 * 0.6) = 101.2
        assert entry_price == Decimal(
            "101.2"), f"Expected 101.2, got {entry_price}"

    def test_missing_atr_aborts_signal(self, handler):
        """
        Test Case 2: Fail-closed behavior.

        If ATR is missing, signal should be ABORTED (not emitted).
        EVT:STRATEGY_DECISION_BLOCKED should be emitted instead.
        """
        handler_obj, emit_fn = handler

        result = MockScoringResult(side="buy", score=0.5)
        features = {"price": "100"}  # NO ATR!

        handler_obj._emit_signal(
            symbol="TESTUSDT",
            result=result,
            features=features,
            source_event={},
        )

        # Should NOT have emitted STRATEGY_SIGNAL_PRODUCED
        signal_calls = [
            c for c in emit_fn.call_args_list
            if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"
        ]
        assert len(
            signal_calls) == 0, "Signal should NOT be emitted when ATR missing"

        # Should have emitted STRATEGY_DECISION_BLOCKED
        blocked_calls = [
            c for c in emit_fn.call_args_list
            if c[0][0] == "EVT:STRATEGY_DECISION_BLOCKED"
        ]
        assert len(
            blocked_calls) >= 1, "DECISION_BLOCKED should be emitted on ATR missing"

        # Verify reason code
        payload = blocked_calls[0][0][1]
        assert payload["reason_code"] == "ATR_MISSING_FAIL_CLOSED"

    def test_unknown_regime_uses_default(self, handler):
        """
        Test Case 3: Default fallback.

        If regime is unknown (not in multipliers), DEFAULT should be used.

        Given:
            regime = "WEIRD_UNKNOWN_REGIME"
        Expected:
            Uses DEFAULT multiplier (0.2)
        """
        handler_obj, emit_fn = handler

        # Set weird regime
        handler_obj._symbol_states["TESTUSDT"].regime = "WEIRD_UNKNOWN_REGIME"

        result = MockScoringResult(side="buy", score=0.5)
        features = {"price": "100", "volatility": {"atr_14": 2.0}}

        handler_obj._emit_signal(
            symbol="TESTUSDT",
            result=result,
            features=features,
            source_event={},
        )

        signal_call = None
        for call in emit_fn.call_args_list:
            event_name = call[0][0]
            if event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
                signal_call = call
                break

        assert signal_call is not None, "Signal should be emitted with DEFAULT fallback"

        payload = signal_call[0][1]
        entry_price = Decimal(payload["price_ctx"]["entry_price"])

        # 100 - (2 * 0.2) = 99.6 (DEFAULT multiplier)
        assert entry_price == Decimal(
            "99.6"), f"Expected 99.6 (DEFAULT mult=0.2), got {entry_price}"

    def test_missing_default_emits_blocked_event_in_legacy_config(self, handler):
        """Legacy/mock configs must fail closed observably when DEFAULT is absent."""
        handler_obj, emit_fn = handler
        handler_obj._symbol_states["TESTUSDT"].regime = "WEIRD_UNKNOWN_REGIME"
        handler_obj.config.strategies.aurora.assets[
            "TESTUSDT"
        ].volatility_entry_logic.regime_multipliers = {
            "HIGH_VOLATILITY": 0.6,
            "LOW_VOLATILITY": 0.1,
        }

        result = MockScoringResult(side="buy", score=0.5)
        features = {"price": "100", "volatility": {"atr_14": 2.0}}

        handler_obj._emit_signal(
            symbol="TESTUSDT",
            result=result,
            features=features,
            source_event={},
        )

        signal_calls = [
            c for c in emit_fn.call_args_list
            if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"
        ]
        blocked_calls = [
            c for c in emit_fn.call_args_list
            if c[0][0] == "EVT:STRATEGY_DECISION_BLOCKED"
        ]
        reject_calls = [
            c for c in emit_fn.call_args_list
            if c[0][0] == "EVT:TRADE_INTENT_REJECTED"
        ]

        assert len(signal_calls) == 0
        assert len(blocked_calls) >= 1
        assert len(reject_calls) == 0
        payload = blocked_calls[0][0][1]
        assert payload["reason_code"] == "VOLATILITY_ENTRY_MULTIPLIER_MISSING"


class TestVolatilityEntryConfigValidation:
    """Tests for VolatilityEntryConfig Pydantic validation."""

    def test_valid_config_accepted(self):
        """Valid config with DEFAULT key should be accepted."""
        import sys
        sys.path.insert(0, '/home/wekabeka/Музыка/Phenix')
        from apps.reference.config_models import VolatilityEntryConfig

        cfg = VolatilityEntryConfig(
            enabled=True,
            regime_multipliers={"DEFAULT": 0.2, "HIGH_VOLATILITY": 0.6}
        )
        assert cfg.enabled is True
        assert cfg.regime_multipliers["DEFAULT"] == 0.2

    def test_missing_default_raises_error(self):
        """Missing DEFAULT key should raise ValueError (fail-closed)."""
        import sys
        sys.path.insert(0, '/home/wekabeka/Музыка/Phenix')
        from apps.reference.config_models import VolatilityEntryConfig

        with pytest.raises(ValueError) as exc_info:
            VolatilityEntryConfig(
                enabled=True,
                regime_multipliers={"HIGH_VOLATILITY": 0.6}  # No DEFAULT!
            )

        assert "DEFAULT" in str(exc_info.value)
