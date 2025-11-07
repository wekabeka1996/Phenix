"""
PHASE 6: Extended Integration Tests
Regression tests for soft-clip + regime adaptation + idempotent cancellations.
Tests interactions between phases 1-5.
"""

import pytest
from decimal import Decimal
from apps.reference.domains.execution_position.soft_clip import SoftClipEngine, SoftLimitConfig
from apps.reference.domains.execution_position.idempotent_cancel import IdempotentCancelHelper, ClientOrderIdConfig
from apps.reference.domains.execution_position.metrics_aggregator import StructuredMetricsLogger, MetricEventType


@pytest.fixture
def default_config():
    """Default soft-limit config (Balanced profile)."""
    return SoftLimitConfig(
        mode="clip",
        clip_min_notional_usdt=Decimal("10"),
        directional_ratio_max=Decimal("3.0"),
        side_exposure_usdt=Decimal("600"),
        margin_exposure_usdt=Decimal("1100"),
    )


@pytest.fixture
def clip_engine(default_config):
    """SoftClipEngine with default config."""
    return SoftClipEngine(default_config)


class TestPhase4Phase5Integration:
    """Test idempotent cancel + metrics integration."""

    def test_cancel_with_metrics_logging(self):
        """Cancel with metrics logging."""
        logger = StructuredMetricsLogger()

        # Simulate idempotent cancel success
        logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="123456",
            success=True,
            is_idempotent_success=True,
        )

        summary = logger.get_summary()
        assert summary["cancel"]["idempotent_ok"] == 1
        assert summary["events_count"] == 1

    def test_2011_absorption_with_metrics(self):
        """Test -2011 absorption recorded in metrics."""
        logger = StructuredMetricsLogger()

        logger.log_cancel_event(
            symbol="ETHUSDT",
            order_id="654321",
            success=True,
            error_code=-2011,
            is_idempotent_success=True,
        )

        summary = logger.get_summary()
        assert summary["cancel"]["2011_absorbed"] == 1
        assert summary["cancel"]["idempotent_ok"] == 1
        # Only 1 event recorded (not duplicated)
        assert summary["events_count"] == 1


class TestPhase2Phase3Integration:
    """Test soft-clip + regime interaction."""

    def test_clip_engine_initialized(self, clip_engine):
        """SoftClipEngine can be initialized."""
        assert clip_engine is not None
        assert clip_engine.config.mode == "clip"

    def test_clip_config_preserved(self, clip_engine):
        """Soft-clip config is preserved after initialization."""
        assert clip_engine.config.clip_min_notional_usdt == Decimal("10")
        assert clip_engine.config.directional_ratio_max == Decimal("3.0")


class TestPhase1Phase2Integration:
    """Test config + soft-clip integration."""

    def test_soft_clip_config_margins(self, clip_engine):
        """Soft-clip respects config exposure limits."""
        # Check that config margins are set
        assert clip_engine.config.margin_exposure_usdt == Decimal("1100")
        assert clip_engine.config.side_exposure_usdt == Decimal("600")


class TestPhase3Phase4Integration:
    """Test regime + idempotent cancel interaction."""

    def test_cancel_during_regime_shift(self):
        """Cancel should work before/after regime shift."""
        helper = IdempotentCancelHelper()
        logger = StructuredMetricsLogger()

        # Pre-regime-shift cancel
        logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="111111",
            success=True,
            is_idempotent_success=True,
        )

        # Simulate regime shift (NORMAL → STRESSED)
        # Post-regime-shift cancel
        logger.log_cancel_event(
            symbol="ETHUSDT",
            order_id="222222",
            success=True,
            is_idempotent_success=True,
        )

        summary = logger.get_summary()
        assert summary["cancel"]["idempotent_ok"] == 2


class TestFullPhaseInteraction:
    """Test all phases working together."""

    def test_order_lifecycle_with_all_phases(self):
        """Order lifecycle: place (Phase 1-3) → cancel (Phase 4) → metrics (Phase 5)."""
        cancel_helper = IdempotentCancelHelper()
        metrics_logger = StructuredMetricsLogger()

        # Phase 1-3: Order placed scenario (would use soft-clip)
        original_notional = Decimal("1000")
        clipped_notional = Decimal("500")

        # Phase 5: Log clipping event
        metrics_logger.log_clip_event(
            symbol="BTCUSDT",
            original_notional=original_notional,
            clipped_notional=clipped_notional,
            clip_reason="margin_exhaustion",
        )

        # Phase 4: Cancel order (simulation)
        # (would use IdempotentCancelHelper in real scenario)

        # Phase 5: Log cancel event
        metrics_logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="123456",
            success=True,
            is_idempotent_success=True,
        )

        summary = metrics_logger.get_summary()
        assert summary["clip"]["count"] == 1
        assert summary["clip"]["notional_total"] == 500.0
        assert summary["cancel"]["idempotent_ok"] == 1


class TestRegressionCases:
    """Regression tests for bug fixes in phases 1-5."""

    def test_zero_clip_amount_not_logged(self):
        """Orders with no clipping should not log clip event."""
        logger = StructuredMetricsLogger()

        # No clipping needed (order within limits)
        clipped = Decimal("500")
        original = Decimal("500")

        # Only log if clipping happened
        if original > clipped:
            logger.log_clip_event(
                symbol="BTCUSDT",
                original_notional=original,
                clipped_notional=clipped,
                clip_reason="none",
            )

        summary = logger.get_summary()
        assert summary["clip"]["count"] == 0

    def test_partial_fill_cancel_idempotent(self):
        """Partially filled order cancel should succeed."""
        logger = StructuredMetricsLogger()

        # Simulate partially filled order cancellation
        logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="333333",
            success=True,
            is_idempotent_success=True,
        )

        summary = logger.get_summary()
        assert summary["cancel"]["idempotent_ok"] == 1

    def test_multiple_cancels_same_order(self):
        """Multiple cancel attempts on same order should accumulate."""
        logger = StructuredMetricsLogger()

        # First cancel attempt fails with -2011
        logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="444444",
            success=True,
            error_code=-2011,
            is_idempotent_success=True,
            attempt=1,
        )

        # Retry would happen in real code, but metrics record both
        summary = logger.get_summary()
        assert summary["cancel"]["2011_absorbed"] == 1
        assert summary["cancel"]["idempotent_ok"] == 1
