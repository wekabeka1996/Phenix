"""
EXEC-R2-K: Tests for bracket state divergence handling

Tests verify fail-closed behavior when avg_entry_price diverges from position state:
1. TRADE_EXECUTED with qty>0, avg_entry_price=0 → does NOT raise Exception
2. Runtime logs WARNING 'BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE'
3. Bracket evaluation skipped this cycle (watchdog may recover later)
4. Runtime remains operational (no crash)

Also tests PLACE/CANCEL expected failures (races) vs unexpected (state divergence).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.shadow_execpos.runtime import (
    ExecPosRuntimeV2,
    PositionState,
)
from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
)


@pytest.fixture
def mock_adapter():
    """Mock adapter for testing."""
    adapter = MagicMock()
    adapter.place_order = AsyncMock(
        return_value={"success": True, "order_id": "12345"})
    adapter.cancel_order = AsyncMock(return_value={"success": True})
    adapter.get_open_orders = AsyncMock(return_value=[])
    adapter.get_open_positions = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def mock_price_service():
    """Mock price service."""
    price_service = MagicMock()
    price_service.get_mark_price = MagicMock(return_value=50000.0)
    return price_service


@pytest.fixture
def runtime_config():
    """Basic runtime config."""
    return {
        "bracket": {
            "enabled": True,
            "tp_pct": 2.0,
            "sl_pct": 1.0,
        }
    }


@pytest.fixture
def runtime(runtime_config, mock_adapter, mock_price_service):
    """Create ExecPosRuntimeV2 instance."""
    runtime = ExecPosRuntimeV2(
        config=runtime_config,
        adapter=mock_adapter,
        price_service=mock_price_service,
    )
    # Disable watchdog for test isolation
    runtime._watchdog_enabled = False
    return runtime


@pytest.mark.asyncio
async def test_avg_entry_price_zero_skips_brackets_no_crash(runtime, caplog):
    """
    EXEC-R2-K: Test TRADE_EXECUTED with qty>0, avg_entry_price=0 → skip brackets, no crash.

    Scenario:
    1. Position has qty=1.0 (LONG), but avg_entry_price=0 (divergence)
    2. _evaluate_brackets called → detects invalid entry_price
    3. Runtime logs WARNING 'BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE'
    4. Does NOT raise Exception (fail-closed)
    5. Runtime remains operational

    Expected: No Exception, WARNING logged, metric incremented
    """
    symbol = "BTCUSDT"

    # Create position with qty>0 but avg_entry_price=0 (E-004 invariant violation)
    position = PositionState(
        symbol=symbol,
        qty=1.0,  # LONG position (qty>0 means LONG, side is a @property)
        avg_entry_price=0.0,  # ← PROBLEM: entry_price=0 when qty>0
    )

    # Manually set position in runtime
    runtime._positions_by_symbol[symbol] = position

    # Call _evaluate_brackets (this would raise ValueError before fix)
    with caplog.at_level("WARNING"):
        await runtime._evaluate_brackets(symbol, position, reason="test_zero_entry_price")

    # Verify: No Exception raised (runtime survived)
    # Verify: WARNING logged
    assert any(
        "BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE" in record.message
        for record in caplog.records
    ), "Expected WARNING about missing entry_price"

    # Verify: Metric incremented
    assert runtime._metrics.get("brackets_skipped_no_entry_price", 0) == 1

    # Verify: Runtime still operational (can process another event)
    runtime._metrics["events_total"] = 0
    await runtime.handle({"kind": "TRADE_EXECUTED", "symbol": symbol, "payload": {
        "side": "BUY", "quantity": 0.5, "price": 50000, "ts": 1234567890
    }})
    assert runtime._metrics["events_total"] == 1, "Runtime should process events after skip"


@pytest.mark.asyncio
async def test_avg_entry_price_valid_creates_brackets(runtime, mock_adapter, caplog):
    """
    EXEC-R2-K: Baseline test — valid avg_entry_price allows bracket evaluation.

    Scenario:
    1. Position has qty=1.0, avg_entry_price=50000 (valid)
    2. _evaluate_brackets called → creates PositionView successfully
    3. No WARNING logged

    Expected: No Exception, no BRACKETS_SKIPPED log
    """
    symbol = "ETHUSDT"

    # Create valid position
    position = PositionState(
        symbol=symbol,
        qty=2.0,  # LONG position (qty>0)
        avg_entry_price=2000.0,  # Valid entry_price
    )

    runtime._positions_by_symbol[symbol] = position

    with caplog.at_level("WARNING"):
        await runtime._evaluate_brackets(symbol, position, reason="test_valid_entry_price")

    # Verify: No WARNING about missing entry_price
    assert not any(
        "BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE" in record.message
        for record in caplog.records
    ), "Should NOT skip brackets with valid entry_price"

    # Verify: Metric NOT incremented
    assert runtime._metrics.get("brackets_skipped_no_entry_price", 0) == 0


@pytest.mark.asyncio
async def test_place_expected_error_logs_warning(mock_adapter):
    """
    EXEC-R2-K: Test PLACE with expected error (ORDER_WOULD_TRIGGER) → WARNING, not ERROR.

    Scenario:
    1. Adapter returns error "Order would immediately trigger"
    2. ExecutionService classifies as "expected" race
    3. Logs WARNING (not ERROR) with reason_code=ORDER_WOULD_TRIGGER

    Expected: WARNING log, reason_code in result
    """
    execution_service = ExecutionService(adapter=mock_adapter)

    # Mock adapter to return expected error
    mock_adapter.place_order = AsyncMock(return_value={
        "success": False,
        "error": "Order would immediately trigger",
        "error_kind": "ADAPTER_ERROR"
    })

    with patch("apps.reference.domains.execution_position.shadow_execpos.execution_service.logger") as mock_logger:
        result = await execution_service.place_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.01,
            price=50000
        )

    # Verify: Result has reason_code
    assert result["success"] is False
    assert result["reason_code"] == "ORDER_WOULD_TRIGGER"

    # Verify: WARNING called (not ERROR)
    assert mock_logger.warning.called, "Expected WARNING for expected error"
    assert not mock_logger.error.called or mock_logger.warning.call_count > mock_logger.error.call_count


@pytest.mark.asyncio
async def test_place_unexpected_error_logs_error(mock_adapter):
    """
    EXEC-R2-K: Test PLACE with unexpected error (INVALID_QUANTITY) → ERROR log.

    Scenario:
    1. Adapter returns error "Invalid quantity"
    2. ExecutionService classifies as "unexpected" (state divergence)
    3. Logs ERROR with reason_code=INVALID_QUANTITY

    Expected: ERROR log, reason_code in result
    """
    execution_service = ExecutionService(adapter=mock_adapter)

    # Mock adapter to return unexpected error
    mock_adapter.place_order = AsyncMock(return_value={
        "success": False,
        "error": "Invalid quantity: precision violation",
        "error_kind": "ADAPTER_ERROR"
    })

    with patch("apps.reference.domains.execution_position.shadow_execpos.execution_service.logger") as mock_logger:
        result = await execution_service.place_order(
            symbol="SOLUSDT",
            side="SELL",
            order_type="MARKET",
            quantity=0.001  # Invalid precision
        )

    # Verify: Result has reason_code
    assert result["success"] is False
    assert result["reason_code"] == "INVALID_QUANTITY"

    # Verify: ERROR called (unexpected divergence)
    assert mock_logger.error.called or (
        not mock_logger.warning.called and mock_logger.error.called
    ), "Expected ERROR for unexpected state divergence"


@pytest.mark.asyncio
async def test_cancel_unknown_order_idempotent_success(mock_adapter):
    """
    EXEC-R2-K: Test CANCEL with -2011 (Unknown Order) → idempotent success.

    Scenario:
    1. Adapter raises exception with -2011 "Unknown Order"
    2. ExecutionService treats as idempotent success (order already closed)
    3. Logs INFO (not WARNING/ERROR)

    Expected: success=True, CANCEL_IDEMPOTENT log
    """
    execution_service = ExecutionService(adapter=mock_adapter)

    # Mock adapter to raise -2011 error
    mock_adapter.cancel_order = AsyncMock(
        side_effect=Exception("-2011: Unknown Order"))

    with patch("apps.reference.domains.execution_position.shadow_execpos.execution_service.logger") as mock_logger:
        result = await execution_service.cancel_order(
            symbol="BNBUSDT",
            order_id="999888777"
        )

    # Verify: Treated as success (idempotent)
    assert result["success"] is True
    assert result["error"] == "UNKNOWN_ORDER"

    # Verify: INFO log (idempotent case)
    assert mock_logger.info.called, "Expected INFO for idempotent cancel"
    info_calls = [
        call for call in mock_logger.info.call_args_list if "IDEMPOTENT" in str(call)]
    assert len(info_calls) > 0, "Expected CANCEL_IDEMPOTENT log"


@pytest.mark.asyncio
async def test_cancel_other_error_logs_warning_with_reason(mock_adapter):
    """
    EXEC-R2-K: Test CANCEL with other error → WARNING with reason_code.

    Scenario:
    1. Adapter raises exception (not -2011)
    2. ExecutionService logs WARNING with reason_code

    Expected: success=False, WARNING log, reason_code in result
    """
    execution_service = ExecutionService(adapter=mock_adapter)

    # Mock adapter to raise generic error
    mock_adapter.cancel_order = AsyncMock(
        side_effect=Exception("Network error"))

    with patch("apps.reference.domains.execution_position.shadow_execpos.execution_service.logger") as mock_logger:
        result = await execution_service.cancel_order(
            symbol="ETHUSDT",
            order_id="123456"
        )

    # Verify: Failure with reason_code
    assert result["success"] is False
    assert "reason_code" in result
    assert result["reason_code"] in [
        "CANCEL_FAILED_UNKNOWN", "ORDER_NOT_FOUND_RACE"]

    # Verify: WARNING logged
    assert mock_logger.warning.called, "Expected WARNING for CANCEL failure"
