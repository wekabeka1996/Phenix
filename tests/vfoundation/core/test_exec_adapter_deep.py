import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from vfoundation.core.adapters.execution_adapter import ExecutionAdapter, CBOpenError, IdempotentDuplicateError
from vfoundation.core.adapters.execution_exceptions import SDKError

class MockExecAdapter(ExecutionAdapter):
    def __init__(self):
        self.base_url = "http://test"
        self.api_key = "key"
        self.api_secret = "secret"
        self.logger = MagicMock()
        self.metrics = MagicMock()
        self.metrics.sdk_cb_open_total = 0
        self.metrics.sdk_retries_total = 0
        self.cb = MagicMock()
        self.ledger = MagicMock()
        self.sdk_cancel_latencies = [100]
        
    def _cancel_impl(self, order_id, client_order_id): pass
    def _submit_impl(self, order, client_order_id): pass
    async def stream(self): pass

@pytest.mark.asyncio
async def test_exec_adapter_cancel_cb_open():
    """Test cancel raises CBOpenError when circuit breaker is open."""
    adapter = MockExecAdapter()
    adapter.cb.is_open.return_value = True
    
    with pytest.raises(CBOpenError):
        adapter.cancel("id1", "cid1")
    
    assert adapter.metrics.sdk_cb_open_total >= 1

@pytest.mark.asyncio
async def test_exec_adapter_cancel_idempotent_duplicate():
    """Test cancel raises IdempotentDuplicateError when already in ledger."""
    adapter = MockExecAdapter()
    adapter.cb.is_open.return_value = False
    adapter.ledger.get.return_value = {"event": "CANCELLED"}
    
    with pytest.raises(IdempotentDuplicateError):
        adapter.cancel("id1", "cid123")

@pytest.mark.asyncio
async def test_exec_adapter_cancel_exception_handling():
    """Test exception recording in cancel."""
    adapter = MockExecAdapter()
    adapter.cb.is_open.return_value = False
    adapter.ledger.get.return_value = None # NO DUPLICATE
    
    # Mock _cancel_impl to crash
    adapter._cancel_impl = MagicMock(side_effect=RuntimeError("Net Crash"))
    
    with pytest.raises(RuntimeError, match="Net Crash"):
        adapter.cancel("id1", "cid1")
        
    adapter.cb.record_error.assert_called_once()

@pytest.mark.asyncio
async def test_exec_adapter_retry_loop_exhaustion():
    """Test _retry_operation raises SDKError after all attempts fail."""
    adapter = MockExecAdapter()
    
    # We must mock global config instance
    from vfoundation.config import config
    with patch.object(config, "adapter_retry_max_attempts", 2), \
         patch.object(config, "adapter_retry_base_ms", 1):
        
        # SDKError(operation, sdk_code=None, sdk_message=None)
        err = SDKError("test_op", sdk_code="500", sdk_message="FAIL")
        op = MagicMock(side_effect=err)
        
        with pytest.raises(SDKError):
            with patch("time.sleep"):
                adapter._retry_operation(op, op_name="test_op")
        
        assert op.call_count == 2
        assert adapter.metrics.sdk_retries_total >= 1
