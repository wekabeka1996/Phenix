import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from vfoundation.adapters.binance_adapter import BinanceAdapter

class TestBinanceAdapterQuantizeQuantity:
    @pytest_asyncio.fixture
    async def adapter(self):
        # Mock adapter without real session
        adapter = BinanceAdapter('key', 'secret', 'https://testnet.binancefuture.com')
        adapter._get_session = AsyncMock()
        adapter.get_exchange_info = AsyncMock()
        adapter.get_mark_price = AsyncMock()
        return adapter

    @pytest.mark.asyncio
    async def test_quantize_basic(self, adapter):
        # Mock exchange info for BTCUSDT
        adapter.get_exchange_info.return_value = {
            'symbols': [{
                'symbol': 'BTCUSDT',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'stepSize': '0.001'},
                    {'filterType': 'MIN_NOTIONAL', 'notional': '10.0'}
                ]
            }]
        }
        adapter.get_mark_price.return_value = 50000.0  # mark price

        qty = await adapter.quantize_quantity('BTCUSDT', 0.00377)
        # 0.00377 // 0.001 = 3, so 3 * 0.001 = 0.003
        # 0.003 * 50000 = 150 >= 10, ok
        assert qty == '0.003'

    @pytest.mark.asyncio
    async def test_quantize_rounds_down(self, adapter):
        adapter.get_exchange_info.return_value = {
            'symbols': [{
                'symbol': 'BTCUSDT',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'stepSize': '0.01'},
                    {'filterType': 'MIN_NOTIONAL', 'notional': '1.0'}
                ]
            }]
        }
        adapter.get_mark_price.return_value = 100.0

        qty = await adapter.quantize_quantity('BTCUSDT', 0.055)
        # 0.055 // 0.01 = 5, so 5 * 0.01 = 0.05
        assert qty == '0.05'

    @pytest.mark.asyncio
    async def test_quantize_below_min_notional(self, adapter):
        adapter.get_exchange_info.return_value = {
            'symbols': [{
                'symbol': 'BTCUSDT',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'stepSize': '0.001'},
                    {'filterType': 'MIN_NOTIONAL', 'notional': '100.0'}
                ]
            }]
        }
        adapter.get_mark_price.return_value = 1000.0

        qty = await adapter.quantize_quantity('BTCUSDT', 0.001)  # 0.001 * 1000 = 1 < 100, should increase to 0.1
        assert qty == '0.1'

    @pytest.mark.asyncio
    async def test_quantize_below_min_qty(self, adapter):
        adapter.get_exchange_info.return_value = {
            'symbols': [{
                'symbol': 'BTCUSDT',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'stepSize': '0.001', 'minQty': '0.01'},
                    {'filterType': 'MIN_NOTIONAL', 'notional': '1.0'}
                ]
            }]
        }
        adapter.get_mark_price.return_value = 100.0

        qty = await adapter.quantize_quantity('BTCUSDT', 0.005)  # 0.005 < 0.01, should increase to 0.01
        assert qty == '0.01'

    @pytest.mark.asyncio
    async def test_quantize_zero_after_rounding(self, adapter):
        adapter.get_exchange_info.return_value = {
            'symbols': [{
                'symbol': 'BTCUSDT',
                'filters': [
                    {'filterType': 'LOT_SIZE', 'stepSize': '0.1'},
                    {'filterType': 'MIN_NOTIONAL', 'notional': '1.0'}
                ]
            }]
        }
        adapter.get_mark_price.return_value = 100.0

        with pytest.raises(ValueError, match="rounds to zero"):
            await adapter.quantize_quantity('BTCUSDT', 0.05)  # 0.05 // 0.1 = 0

    @pytest.mark.asyncio
    async def test_symbol_not_found(self, adapter):
        adapter.get_exchange_info.return_value = {'symbols': []}

        with pytest.raises(ValueError, match="Exchange info for BTCUSDT not found"):
            await adapter.quantize_quantity('BTCUSDT', 0.001)


class TestBinanceAdapterRequest:
    @pytest_asyncio.fixture(scope="function")
    async def adapter(self):
        mock_session = MagicMock()
        adapter = BinanceAdapter('key', 'secret', 'https://testnet.binancefuture.com')
        adapter._session = mock_session
        adapter._sync_time = AsyncMock()
        adapter._server_time = AsyncMock(return_value=1234567890000)
        # Reset any global state that might affect the test
        adapter._time_offset_ms = 0
        adapter._last_time_sync_monotonic = 0.0
        yield adapter

    @pytest.mark.asyncio
    async def test_request_success(self, adapter):
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={'result': 'ok'})
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        adapter._session.get.return_value = mock_context

        result = await adapter._request('GET', '/test')
        assert result == {'result': 'ok'}

    @pytest.mark.asyncio
    async def test_request_json_error_body(self, adapter):
        response = AsyncMock()
        response.status = 400
        response.json = AsyncMock(return_value={"code": -1013, "msg": "Invalid quantity"})
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        adapter._session.post.return_value = mock_context

        from vfoundation.adapters.binance_adapter import BinanceAPIError
        print(f"DEBUG: BinanceAPIError class: {BinanceAPIError}")
        print(f"DEBUG: BinanceAPIError module: {BinanceAPIError.__module__}")
        with pytest.raises(BinanceAPIError) as exc_info:
            await adapter._request('POST', '/order')
        print(f"DEBUG: Exception caught: {exc_info.value}")
        assert exc_info.value.code == -1013
        assert exc_info.value.msg == "Invalid quantity"
        assert exc_info.value.status == 400

    @pytest.mark.asyncio
    async def test_request_retry_on_1021(self, adapter):
        # First call: 400 with -1021 error -> should retry with force sync
        response1 = AsyncMock()
        response1.status = 400
        response1.json = AsyncMock(return_value={"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."})
        response2 = AsyncMock()
        response2.status = 200
        response2.json = AsyncMock(return_value={"ok": True})
        mock_context1 = AsyncMock()
        mock_context1.__aenter__ = AsyncMock(return_value=response1)
        mock_context1.__aexit__ = AsyncMock(return_value=None)
        mock_context2 = AsyncMock()
        mock_context2.__aenter__ = AsyncMock(return_value=response2)
        mock_context2.__aexit__ = AsyncMock(return_value=None)
        adapter._session.get.side_effect = [mock_context1, mock_context2]

        result = await adapter._request('GET', '/test', signed=True)
        assert result == {"ok": True}
        # Should have called get twice
        assert adapter._session.get.call_count == 2
        # Should have called _sync_time with force=True on retry
        adapter._sync_time.assert_any_call(True)

    @pytest.mark.asyncio
    async def test_request_retry_on_1022(self, adapter):
        # First call: 400 with -1022 error -> should retry with force sync
        response1 = AsyncMock()
        response1.status = 400
        response1.json = AsyncMock(return_value={"code": -1022, "msg": "Signature for this request is not valid."})
        response2 = AsyncMock()
        response2.status = 200
        response2.json = AsyncMock(return_value={"ok": True})
        mock_context1 = AsyncMock()
        mock_context1.__aenter__ = AsyncMock(return_value=response1)
        mock_context1.__aexit__ = AsyncMock(return_value=None)
        mock_context2 = AsyncMock()
        mock_context2.__aenter__ = AsyncMock(return_value=response2)
        mock_context2.__aexit__ = AsyncMock(return_value=None)
        adapter._session.get.side_effect = [mock_context1, mock_context2]

        result = await adapter._request('GET', '/test', signed=True)
        assert result == {"ok": True}
        assert adapter._session.get.call_count == 2
        adapter._sync_time.assert_any_call(True)

    @pytest.mark.asyncio
    async def test_request_no_retry_on_other_errors(self, adapter):
        # Error -1013, should not retry
        response = AsyncMock()
        response.status = 400
        response.json = AsyncMock(return_value={"code": -1013, "msg": "Invalid quantity"})
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        adapter._session.get.return_value = mock_context

        from vfoundation.adapters.binance_adapter import BinanceAPIError
        print(f"DEBUG2: BinanceAPIError class: {BinanceAPIError}")
        print(f"DEBUG2: BinanceAPIError module: {BinanceAPIError.__module__}")
        with pytest.raises(BinanceAPIError) as exc_info:
            await adapter._request('GET', '/test', signed=True)
        print(f"DEBUG2: Exception caught: {exc_info.value}")
        assert exc_info.value.code == -1013
        # Should have called get only once
        assert adapter._session.get.call_count == 1
        # _sync_time should be called with force=False, but not with True
        adapter._sync_time.assert_called_with(False)
        # Ensure not called with True
        calls = [call for call in adapter._sync_time.call_args_list if call == ((True,), {})]
        assert len(calls) == 0
