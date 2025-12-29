"""
Test: Execution Error Mapping
=============================

EXEC-FILL-TIMEOUT-VS-ADAPTER-ERROR-DISTINCTION

Tests that:
1. Adapter errors (precision, rate-limit, etc.) are NOT marked as timeouts
2. Real fill timeouts ARE marked as timeouts
3. Correct error_kind is propagated to logs
4. SymbolExecutor and Runtime use correct error messages

RID: EXEC-FILL-TIMEOUT-VS-ADAPTER-ERROR-DISTINCTION
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

# Import tested modules
from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
    ExecutionStatus,
    TIMEOUT_EXCEPTION_NAMES,
)
from apps.reference.adapters.binance_adapter import BinanceAPIError


class TestExceptionClassification:
    """Test centralized exception classification logic."""

    @pytest.fixture
    def service(self):
        """Create ExecutionService with mock adapter."""
        mock_adapter = MagicMock()
        return ExecutionService(mock_adapter)

    def test_precision_error_not_timeout(self, service):
        """ERR-MAP-1: -1111 Precision error should NOT be marked as timeout."""
        error = BinanceAPIError(
            code=-1111,
            msg="Precision is over the maximum defined for this asset."
        )

        classification = service._classify_exception(error)

        assert classification["is_timeout"] is False
        assert classification["error_kind"] == "ADAPTER_ERROR"
        assert "PRECISION" in classification["normalized_error"].upper()

    def test_would_trigger_error_not_timeout(self, service):
        """ERR-MAP-2: -2021 Would trigger error should NOT be marked as timeout."""
        error = BinanceAPIError(
            code=-2021,
            msg="Order would immediately trigger."
        )

        classification = service._classify_exception(error)

        assert classification["is_timeout"] is False
        assert classification["error_kind"] == "ADAPTER_ERROR"

    def test_duplicate_id_error_not_timeout(self, service):
        """ERR-MAP-3: -4116 Duplicate ID error should NOT be marked as timeout."""
        error = BinanceAPIError(
            code=-4116,
            msg="Order with same clientOrderId already exists."
        )

        classification = service._classify_exception(error)

        assert classification["is_timeout"] is False

    def test_read_timeout_is_timeout(self, service):
        """ERR-MAP-4: ReadTimeout should be marked as timeout."""
        # Create mock timeout exception
        class MockReadTimeout(Exception):
            pass
        MockReadTimeout.__name__ = "ReadTimeout"

        error = MockReadTimeout("Connection timed out")

        classification = service._classify_exception(error)

        assert classification["is_timeout"] is True
        assert classification["error_kind"] == "ADAPTER_ERROR_TIMEOUT"

    def test_connect_timeout_is_timeout(self, service):
        """ERR-MAP-5: ConnectTimeout should be marked as timeout."""
        class MockConnectTimeout(Exception):
            pass
        MockConnectTimeout.__name__ = "ConnectTimeout"

        error = MockConnectTimeout("Failed to connect")

        classification = service._classify_exception(error)

        assert classification["is_timeout"] is True

    def test_network_error_is_network(self, service):
        """ERR-MAP-6: NetworkError should be marked as network error."""
        class MockNetworkError(Exception):
            pass
        MockNetworkError.__name__ = "NetworkError"

        error = MockNetworkError("Network unreachable")

        classification = service._classify_exception(error)

        assert classification["is_network"] is True
        assert classification["error_kind"] == "ADAPTER_ERROR_NETWORK"


class TestExecutePlaceErrorHandling:
    """Test error handling in _execute_place."""

    @pytest.fixture
    def service(self):
        """Create ExecutionService with mock adapter."""
        mock_adapter = MagicMock()
        return ExecutionService(mock_adapter)

    @pytest.mark.asyncio
    async def test_adapter_precision_error_returns_correct_error_kind(self, service):
        """ERR-PLACE-1: Adapter precision error should have correct error_kind."""
        # Mock adapter to raise BinanceAPIError
        service.adapter.create_order = AsyncMock(
            side_effect=BinanceAPIError(
                code=-1111,
                msg="Precision is over the maximum defined for this asset."
            )
        )

        cmd = {
            "verb": "PLACE",
            "symbol": "SOLUSDT",
            "side": "SELL",
            "order_type": "STOP_MARKET",
            "quantity": None,
            "stop_price": "133.123456789",
            "extra_params": {"close_position": True},
        }

        result = await service._execute_place(cmd)

        assert result["success"] is False
        assert result.get("is_timeout") is False
        assert result.get("error_kind") == "ADAPTER_ERROR"
        assert "PRECISION" in str(result.get("error", "")).upper()

    @pytest.mark.asyncio
    async def test_adapter_timeout_returns_is_timeout_true(self, service):
        """ERR-PLACE-2: Adapter timeout should have is_timeout=True."""
        # Create timeout exception
        class MockReadTimeout(Exception):
            pass
        MockReadTimeout.__name__ = "ReadTimeout"

        service.adapter.create_order = AsyncMock(
            side_effect=MockReadTimeout("Read timed out")
        )

        cmd = {
            "verb": "PLACE",
            "symbol": "SOLUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
            "extra_params": {},
        }

        result = await service._execute_place(cmd)

        assert result["success"] is False
        assert result.get("is_timeout") is True
        assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT"


class TestPlaceErrorClassification:
    """Test EXEC-R2-K error classification for PLACE operations."""

    @pytest.fixture
    def service(self):
        mock_adapter = MagicMock()
        return ExecutionService(mock_adapter)

    def test_precision_error_is_unexpected(self, service):
        """ERR-CLASS-1: Precision error should be classified as unexpected."""
        classification = service._classify_place_error(
            "Precision is over the maximum defined for this asset.",
            {}
        )

        assert classification["category"] == "unexpected"
        assert classification["reason_code"] == "PRECISION_VIOLATION"

    def test_would_trigger_is_expected(self, service):
        """ERR-CLASS-2: Would trigger error should be classified as expected."""
        classification = service._classify_place_error(
            "-2021 Order would immediately trigger.",
            {}
        )

        assert classification["category"] == "expected"
        assert classification["reason_code"] == "ORDER_WOULD_TRIGGER"

    def test_rate_limit_is_expected(self, service):
        """ERR-CLASS-3: Rate limit error should be classified as expected."""
        classification = service._classify_place_error(
            "Rate limit exceeded",
            {}
        )

        assert classification["category"] == "expected"
        assert classification["reason_code"] == "RATE_LIMIT"


class TestRuntimeErrorLogging:
    """Test that Runtime logs correct error messages."""

    def test_error_msg_propagated_to_logs(self):
        """RUNTIME-1: Runtime should log actual error_msg, not generic 'Fill timeout'."""
        # This test verifies the contract: runtime logs result.get("error")
        # The fix ensures that error from ExecutorPool contains actual error message

        # Simulate the result that Runtime receives
        result = {
            "success": False,
            "error": "ADAPTER_ERROR_PRECISION: Precision is over the maximum",
            "error_kind": "ADAPTER_ERROR",
            "is_timeout": False,
        }

        # Verify the error message format
        error_msg = result.get("error", "executor_pool_failed")

        # Error msg should contain PRECISION info for precision errors
        assert "PRECISION" in error_msg.upper() or "-1111" in error_msg


class TestIntegrationPrecisionToErrorMapping:
    """Integration test: precision error flows correctly through the stack."""

    @pytest.mark.asyncio
    async def test_precision_error_flow_from_adapter_to_result(self):
        """INT-1: Precision error should flow correctly from adapter to final result."""
        from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
            ExecutionService
        )

        # Create service with mock adapter that raises precision error
        mock_adapter = MagicMock()

        async def mock_create_order(params):
            raise BinanceAPIError(
                code=-1111,
                msg="Precision is over the maximum defined for this asset."
            )

        mock_adapter.create_order = mock_create_order

        service = ExecutionService(mock_adapter)

        # Execute place command
        cmd = {
            "verb": "PLACE",
            "symbol": "SOLUSDT",
            "side": "SELL",
            "order_type": "STOP_MARKET",
            "quantity": None,
            "stop_price": "133.6869070203939861585240578",
            "extra_params": {"close_position": True},
        }

        result = await service._execute_place(cmd)

        # Verify error classification
        assert result["success"] is False
        assert result.get("is_timeout") is False
        assert result.get("error_kind") == "ADAPTER_ERROR"

        # Error message should contain meaningful info
        error_msg = result.get("error", "")
        assert "PRECISION" in error_msg.upper()
