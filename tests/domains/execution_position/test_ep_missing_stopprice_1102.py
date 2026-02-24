"""
EP-ORDER-MISSING-STOPPRICE-1102 regression tests.

Forensics confirmed: DEC:PLACE_ORDER for TAKE_PROFIT_MARKET / STOP_MARKET executed
with stopPrice=None; ExecPosFSM.str(stop_price) produced "None" forwarded to Binance
→ Binance -1102 "Mandatory parameter 'stopprice'/'triggerprice' was not sent".

Tests verify:
  A) ExecPosFSM blocks conditional orders when stopPrice is missing/invalid (fail-closed).
  B) ExecPosFSM allows conditional orders when stopPrice is a valid numeric string.
  C) ManageFlowFSM._emit_place_order raises before emitting TP with None stopPrice.
  D) BinanceAdapter raises ValueError before any HTTP call when stopPrice is invalid.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _dec_place_order(
    order_type: str,
    stop_price=None,
    symbol: str = "DOGEUSDT",
    side: str = "SELL",
    qty: str = "100.0",
) -> Message:
    """Build a minimal DEC:PLACE_ORDER message for bracket tests."""
    pld = {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "order_type": order_type,
        "price": None,
        "reduceOnly": True,
        "newClientOrderId": f"test_{order_type.lower()}_001",
    }
    # stopPrice deliberately absent when stop_price is sentinel
    if stop_price is not _OMIT:
        pld["stopPrice"] = stop_price
    return Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="test",
        dst="execution_position",
        rid="test-rid-1102",
        why="test bracket",
        pld=pld,
    )


_OMIT = object()  # sentinel: omit the key entirely from payload


def _arm_fsm(fsm) -> MagicMock:
    """Attach a mock adapter with testnet URL (passes the guardrail) and return it."""
    mock_adapter = MagicMock()
    mock_adapter.base_url = "https://testnet.binancefuture.com"
    mock_adapter.place_stop_market_close_position = AsyncMock(
        return_value={"orderId": "SL-001"}
    )
    mock_adapter.place_take_profit_market_close_position = AsyncMock(
        return_value={"orderId": "TP-001"}
    )
    mock_adapter.place_order = AsyncMock(return_value={"orderId": "GEN-001"})
    fsm.adapter = mock_adapter
    return mock_adapter


def _build_manage_fsm(fsm_config, symbol: str = "BTCUSDT") -> ManageFlowFSM:
    """Create a minimal ManageFlowFSM with required state."""
    m = ManageFlowFSM(config=fsm_config)
    m.symbol = symbol
    m.position_side = "BUY"
    m.position_entry_price = Decimal("0.10000")
    m.position_qty = Decimal("100.0")
    m.position_open_ts = 1_000_000
    return m


# ---------------------------------------------------------------------------
# A) ExecPosFSM: fail-closed when stopPrice is missing / invalid
# ---------------------------------------------------------------------------


class TestExecPosBlocksConditionalOrderWhenStopPriceMissing:
    """
    EP-1102-A: When DEC:PLACE_ORDER carries a conditional order_type but stopPrice
    is None / "None" / "" / "nan", ExecPosFSM MUST:
      - NOT call any adapter.place_* method
      - Log an error containing "EP-1102" plus symbol and order_type
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stop_price_val",
        [
            None,
            "None",
            "",
            "nan",
            "NaN",
            "inf",
            "-inf",
            "1e999999",
        ],
        ids=[
            "None",
            "str_None",
            "empty",
            "nan_lower",
            "nan_upper",
            "inf",
            "neg_inf",
            "overflow_exp",
        ],
    )
    @pytest.mark.parametrize(
        "order_type",
        ["TAKE_PROFIT_MARKET", "STOP_MARKET", "TRAILING_STOP_MARKET"],
        ids=["TP_MARKET", "STOP_MARKET", "TRAILING_STOP_MARKET"],
    )
    async def test_blocks_when_stopprice_invalid(
        self, fsm_harness, caplog, order_type, stop_price_val
    ):
        fsm, _bus, _cfg = fsm_harness
        mock_adapter = _arm_fsm(fsm)

        msg = _dec_place_order(order_type=order_type,
                               stop_price=stop_price_val)

        import logging
        with caplog.at_level(logging.ERROR):
            await fsm._execute_decision(msg)

        # Adapter MUST NOT be called
        mock_adapter.place_stop_market_close_position.assert_not_called()
        mock_adapter.place_take_profit_market_close_position.assert_not_called()
        mock_adapter.place_order.assert_not_called()

        # A fail-closed reason must be logged containing EP-1102
        ep1102_logs = [
            r.message for r in caplog.records if "EP-1102" in r.message]
        assert ep1102_logs, (
            f"Expected at least one log record containing 'EP-1102' for "
            f"{order_type} stopPrice={stop_price_val!r}, got: {caplog.text}"
        )
        # why must be <=80 chars
        for log_msg in ep1102_logs:
            assert len(
                log_msg) <= 80, f"why message exceeds 80 chars: {log_msg!r}"
            assert "DOGEUSDT" in log_msg, f"symbol missing from reason: {log_msg!r}"
            assert order_type in log_msg, f"order_type missing from reason: {log_msg!r}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "order_type",
        ["TAKE_PROFIT_MARKET", "STOP_MARKET", "TRAILING_STOP_MARKET"],
        ids=["TP_MARKET_omit", "STOP_MARKET_omit", "TRAILING_STOP_MARKET_omit"],
    )
    async def test_blocks_when_stopprice_key_absent(
        self, fsm_harness, caplog, order_type
    ):
        """stopPrice key absent entirely is also invalid."""
        fsm, _bus, _cfg = fsm_harness
        mock_adapter = _arm_fsm(fsm)

        msg = _dec_place_order(order_type=order_type, stop_price=_OMIT)

        import logging
        with caplog.at_level(logging.ERROR):
            await fsm._execute_decision(msg)

        mock_adapter.place_stop_market_close_position.assert_not_called()
        mock_adapter.place_take_profit_market_close_position.assert_not_called()
        mock_adapter.place_order.assert_not_called()

        ep1102_logs = [
            r.message for r in caplog.records if "EP-1102" in r.message]
        assert ep1102_logs, f"Expected EP-1102 log, got: {caplog.text}"


# ---------------------------------------------------------------------------
# B) ExecPosFSM: allows conditional order when stopPrice is valid
# ---------------------------------------------------------------------------


class TestExecPosAllowsConditionalOrderWhenStopPriceValid:
    """
    EP-1102-B: When stopPrice is a valid positive numeric string, ADP MUST be called.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stop_price_val",
        ["1.2345", "0.09048", "76.03", "62890.1"],
        ids=["generic", "doge_range", "btc_sl", "btc_tp"],
    )
    async def test_allows_tp_market_with_valid_stopprice(
        self, fsm_harness, stop_price_val
    ):
        fsm, _bus, _cfg = fsm_harness
        mock_adapter = _arm_fsm(fsm)

        msg = _dec_place_order(
            order_type="TAKE_PROFIT_MARKET",
            stop_price=stop_price_val,
            symbol="BTCUSDT",
        )

        await fsm._execute_decision(msg)

        mock_adapter.place_take_profit_market_close_position.assert_called_once()
        call_args = mock_adapter.place_take_profit_market_close_position.call_args
        passed_stop = call_args[0][2]  # positional arg 3 = stop_price
        # Must NOT be the sentinel strings
        assert passed_stop not in (None, "None", "", "nan")
        assert passed_stop == stop_price_val

    @pytest.mark.asyncio
    async def test_allows_stop_market_with_valid_stopprice(self, fsm_harness):
        fsm, _bus, _cfg = fsm_harness
        mock_adapter = _arm_fsm(fsm)

        msg = _dec_place_order(
            order_type="STOP_MARKET",
            stop_price="0.09048",
            symbol="DOGEUSDT",
            side="BUY",
        )

        await fsm._execute_decision(msg)

        mock_adapter.place_stop_market_close_position.assert_called_once()
        call_args = mock_adapter.place_stop_market_close_position.call_args
        assert call_args[0][2] == "0.09048"


# ---------------------------------------------------------------------------
# C) ManageFlowFSM emission guard: never emits TP with stopPrice=None
# ---------------------------------------------------------------------------


class TestManageEmissionNeverSendsTPWithNoneStopPrice:
    """
    EP-1102-C: ManageFlowFSM._emit_place_order MUST raise ValueError (or similar)
    if called with price="None"/"" for a conditional order type.
    This prevents the bad DEC:PLACE_ORDER from ever entering the bus.
    """

    @pytest.mark.parametrize(
        "bad_price",
        ["None", "", "nan", "NaN", "inf", "-inf", "1e999999"],
        ids=[
            "str_None",
            "empty",
            "nan_lower",
            "nan_upper",
            "inf",
            "neg_inf",
            "overflow_exp",
        ],
    )
    @pytest.mark.parametrize(
        "order_type",
        ["TAKE_PROFIT_MARKET", "STOP_MARKET"],
        ids=["TP_MARKET", "STOP_MARKET"],
    )
    def test_emit_place_order_raises_for_missing_stopprice(
        self, fsm_config, bad_price, order_type
    ):
        mf = _build_manage_fsm(fsm_config)

        trigger_msg = Message(
            op="DEC",
            verb="PLACE_BRACKETS",
            src="test",
            dst="execution_position",
            rid="test-rid-emit",
            pld={"symbol": "BTCUSDT"},
        )

        with pytest.raises((ValueError, TypeError)) as exc_info:
            mf._emit_place_order(
                msg=trigger_msg,
                client_id="test_tp_001",
                order_type=order_type,
                side="SELL",
                qty="100.0",
                price=bad_price,
                why="TP bracket",
            )
        reason = str(exc_info.value)
        assert "EP-1102" in reason
        assert "BTCUSDT" in reason
        assert order_type in reason
        assert len(reason) <= 80

    def test_emit_place_order_raises_for_none_price(self, fsm_config):
        """Python None (not string) must also be rejected."""
        mf = _build_manage_fsm(fsm_config)

        trigger_msg = Message(
            op="DEC",
            verb="PLACE_BRACKETS",
            src="test",
            dst="execution_position",
            rid="test-rid-emit-none",
            pld={"symbol": "BTCUSDT"},
        )

        with pytest.raises((ValueError, TypeError)) as exc_info:
            mf._emit_place_order(
                msg=trigger_msg,
                client_id="test_tp_002",
                order_type="TAKE_PROFIT_MARKET",
                side="SELL",
                qty="100.0",
                price=None,
                why="TP bracket None",
            )
        reason = str(exc_info.value)
        assert "EP-1102" in reason
        assert "BTCUSDT" in reason
        assert "TAKE_PROFIT_MARKET" in reason
        assert len(reason) <= 80

    def test_emit_place_order_succeeds_for_valid_price(self, fsm_config):
        """Valid price must NOT raise – positive smoke test."""
        mf = _build_manage_fsm(fsm_config)

        trigger_msg = Message(
            op="DEC",
            verb="PLACE_BRACKETS",
            src="test",
            dst="execution_position",
            rid="test-rid-emit-ok",
            pld={"symbol": "BTCUSDT"},
        )

        result = mf._emit_place_order(
            msg=trigger_msg,
            client_id="test_tp_ok",
            order_type="TAKE_PROFIT_MARKET",
            side="SELL",
            qty="100.0",
            price="0.10500",
            why="TP bracket valid",
        )
        assert result is not None
        assert result.pld["stopPrice"] == "0.10500"


# ---------------------------------------------------------------------------
# D) BinanceAdapter P1: raises ValueError before HTTP when stopPrice invalid
# ---------------------------------------------------------------------------


class TestAdapterRaisesBeforeHttpWhenStopPriceInvalid:
    """
    EP-1102-D: BinanceAdapter.place_take_profit_market_close_position and
    place_stop_market_close_position MUST raise ValueError (or similar) before
    _post_order_with_algo_fallback() is called when stop_price is invalid.
    """

    def _make_adapter(self):
        """Build a minimal BinanceAdapter with mocked HTTP layer."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter

        adapter = MagicMock(spec=BinanceAdapter)
        # Re-bind the real method under test
        adapter.place_take_profit_market_close_position = (
            BinanceAdapter.place_take_profit_market_close_position.__get__(
                adapter)
        )
        adapter.place_stop_market_close_position = (
            BinanceAdapter.place_stop_market_close_position.__get__(adapter)
        )
        adapter._post_order_with_algo_fallback = AsyncMock(
            return_value={"orderId": "TP-HTTP-999"}
        )
        return adapter

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_price",
        [None, "None", "", "nan", "inf", "-inf", "1e999999"],
        ids=["None", "str_None", "empty", "nan", "inf", "neg_inf", "overflow_exp"],
    )
    async def test_tp_adapter_raises_before_http(self, bad_price):
        adapter = self._make_adapter()

        with pytest.raises((ValueError, TypeError)) as exc_info:
            await adapter.place_take_profit_market_close_position(
                "DOGEUSDT", "SELL", bad_price
            )

        adapter._post_order_with_algo_fallback.assert_not_called()
        reason = str(exc_info.value)
        assert "EP-1102" in reason
        assert "DOGEUSDT" in reason
        assert "TAKE_PROFIT_MARKET" in reason
        assert len(reason) <= 80

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_price",
        [None, "None", "", "nan", "inf", "-inf", "1e999999"],
        ids=["None", "str_None", "empty", "nan", "inf", "neg_inf", "overflow_exp"],
    )
    async def test_sl_adapter_raises_before_http(self, bad_price):
        adapter = self._make_adapter()

        with pytest.raises((ValueError, TypeError)) as exc_info:
            await adapter.place_stop_market_close_position(
                "XRPUSDT", "BUY", bad_price
            )

        adapter._post_order_with_algo_fallback.assert_not_called()
        reason = str(exc_info.value)
        assert "EP-1102" in reason
        assert "XRPUSDT" in reason
        assert "STOP_MARKET" in reason
        assert len(reason) <= 80

    @pytest.mark.asyncio
    async def test_adapter_passes_valid_stopprice_to_http(self):
        """Smoke: valid price must reach _post_order_with_algo_fallback."""
        adapter = self._make_adapter()

        await adapter.place_take_profit_market_close_position(
            "DOGEUSDT", "SELL", "0.09500"
        )

        adapter._post_order_with_algo_fallback.assert_called_once()
        posted_params = adapter._post_order_with_algo_fallback.call_args[0][0]
        assert posted_params["stopPrice"] == "0.09500"
