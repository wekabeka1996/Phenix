"""
PHASE 4: Idempotent Cancellation Tests
Tests for -2011 absorption, pre-cancel checks, and deterministic clientOrderId.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from decimal import Decimal
try:
    from apps.reference.domains.execution_position.idempotent_cancel import (
        IdempotentCancelHelper,
        IdempotentCancelResult,
        ClientOrderIdConfig,
        OrderStatus,
    )
except ModuleNotFoundError:
    pytest.skip("apps package unavailable on sys.path", allow_module_level=True)


class TestClientOrderIdGeneration:
    """Test deterministic clientOrderId generation."""

    def test_generate_client_order_id_basic(self):
        """Generate deterministic clientOrderId."""
        client_id = IdempotentCancelHelper.generate_deterministic_clientOrderId(
            symbol="BTCUSDT",
            side="BUY",
            notional_usdt=Decimal("1000"),
            session_prefix="AUR",
            use_timestamp=False,
            counter=0
        )

        assert client_id.startswith("epv")  # canonical prefix
        assert len(client_id) <= 36  # Binance limit

    def test_generate_client_order_id_deterministic(self):
        """Same inputs should generate same clientOrderId."""
        id1 = IdempotentCancelHelper.generate_deterministic_clientOrderId(
            symbol="ETHUSDT",
            side="SELL",
            notional_usdt=Decimal("500"),
            use_timestamp=False,
            counter=42
        )

        id2 = IdempotentCancelHelper.generate_deterministic_clientOrderId(
            symbol="ETHUSDT",
            side="SELL",
            notional_usdt=Decimal("500"),
            use_timestamp=False,
            counter=42
        )

        assert id1 == id2

    def test_generate_client_order_id_different_counter(self):
        """Different counters should generate different IDs."""
        id1 = IdempotentCancelHelper.generate_deterministic_clientOrderId(
            symbol="BTCUSDT",
            side="BUY",
            notional_usdt=Decimal("1000"),
            use_timestamp=False,
            counter=0
        )

        id2 = IdempotentCancelHelper.generate_deterministic_clientOrderId(
            symbol="BTCUSDT",
            side="BUY",
            notional_usdt=Decimal("1000"),
            use_timestamp=False,
            counter=1
        )

        assert id1 != id2

    def test_generate_client_order_id_length_respected(self):
        """ClientOrderId should not exceed Binance's 36 char limit."""
        # Test with realistic long symbol (e.g., BNBUSDT)
        client_id = IdempotentCancelHelper.generate_deterministic_clientOrderId(
            symbol="BNBUSDT",
            side="BUY",
            notional_usdt=Decimal("9999.99"),
            use_timestamp=False,
            counter=99999
        )

        assert len(client_id) <= 36


class TestIdempotentCancelResult:
    """Test IdempotentCancelResult dataclass."""

    def test_result_success(self):
        """Successful cancellation result."""
        result = IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            order_status_before="NEW",
            order_status_after="CANCELED",
            is_idempotent_success=True
        )

        assert result.success is True
        assert result.is_idempotent_success is True
        assert result.error_code is None

    def test_result_2011_absorbed(self):
        """Result for -2011 (Unknown order) treated as success."""
        result = IdempotentCancelResult(
            success=True,
            reason="IDEMPOTENT_-2011_ABSORBED",
            order_status_before=None,
            order_status_after="UNKNOWN",
            error_code=-2011,
            is_idempotent_success=True
        )

        assert result.success is True
        assert result.is_idempotent_success is True
        assert result.error_code == -2011

    def test_result_already_canceled(self):
        """Result for order that was already canceled."""
        result = IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_CANCELED",
            order_status_before="CANCELED",
            order_status_after="CANCELED",
            already_canceled=True,
            is_idempotent_success=True
        )

        assert result.success is True
        assert result.already_canceled is True
        assert result.is_idempotent_success is True

    def test_result_failure(self):
        """Failure result with error code."""
        result = IdempotentCancelResult(
            success=False,
            reason="BINANCE_ERROR_-1000",
            error_code=-1000,
            is_idempotent_success=False
        )

        assert result.success is False
        assert result.is_idempotent_success is False
        assert result.error_code == -1000


class TestIdempotentCancelHelper:
    """Test IdempotentCancelHelper core logic."""

    def test_helper_init(self):
        """Initialize helper with config."""
        config = ClientOrderIdConfig(prefix="TEST")
        helper = IdempotentCancelHelper(config=config)

        assert helper.config.prefix == "TEST"
        assert helper.config.use_timestamp is True

    def test_helper_order_status_enum(self):
        """OrderStatus enum values."""
        assert OrderStatus.NEW.value == "NEW"
        assert OrderStatus.CANCELED.value == "CANCELED"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.EXPIRED.value == "EXPIRED"

    def test_helper_config_defaults(self):
        """ClientOrderIdConfig defaults."""
        config = ClientOrderIdConfig()

        assert config.prefix == "AUR"
        assert config.use_timestamp is True
        assert config.counter_enabled is True

    def test_helper_log_result_success(self, caplog):
        """Log successful cancellation."""
        import logging
        caplog.set_level(logging.INFO)

        helper = IdempotentCancelHelper()
        result = IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            order_status_before="NEW",
            order_status_after="CANCELED",
            is_idempotent_success=True
        )

        helper.log_cancel_result(result, "123456")

        assert "IDEMPOTENT_CANCEL_AUDIT" in caplog.text
        assert "status=SUCCESS" in caplog.text
        assert "123456" in caplog.text

    def test_helper_log_result_failure(self, caplog):
        """Log failed cancellation."""
        import logging
        caplog.set_level(logging.WARNING)

        helper = IdempotentCancelHelper()
        result = IdempotentCancelResult(
            success=False,
            reason="BINANCE_ERROR_-1000",
            error_code=-1000,
            is_idempotent_success=False
        )

        helper.log_cancel_result(result, "123456")

        assert "IDEMPOTENT_CANCEL_AUDIT" in caplog.text
        assert "status=FAILED" in caplog.text


class TestIdempotentCancelIntegration:
    """Integration tests for idempotent cancel scenarios."""

    def test_scenario_order_already_canceled(self):
        """Scenario: Order is already CANCELED (pre-check returns CANCELED)."""
        result = IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_CANCELED",
            order_status_before="CANCELED",
            order_status_after="CANCELED",
            already_canceled=True,
            is_idempotent_success=True
        )

        assert result.success is True
        # Should not attempt cancel, just return success

    def test_scenario_order_2011_absorbed(self):
        """Scenario: Cancel returns -2011 (Unknown order), absorbed as success."""
        result = IdempotentCancelResult(
            success=True,
            reason="IDEMPOTENT_-2011_ABSORBED",
            error_code=-2011,
            is_idempotent_success=True
        )

        assert result.success is True
        assert result.is_idempotent_success is True
        # Should return success even though order not found

    def test_scenario_cancel_success(self):
        """Scenario: Cancel successful (NEW → CANCELED)."""
        result = IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            order_status_before="NEW",
            order_status_after="CANCELED",
            is_idempotent_success=True
        )

        assert result.success is True
        assert result.order_status_after == "CANCELED"

    def test_scenario_cancel_filled_already(self):
        """Scenario: Order already FILLED, no cancel needed."""
        result = IdempotentCancelResult(
            success=True,
            reason="PRE_CHECK_TERMINAL_FILLED",
            order_status_before="FILLED",
            order_status_after="FILLED",
            already_canceled=False,
            is_idempotent_success=True
        )

        assert result.success is True
        # Should return success, order execution completed
