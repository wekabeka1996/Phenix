"""Tests for vfoundation.core.adapters.base — Dataclasses + ABC."""
from __future__ import annotations

import asyncio

import pytest

from vfoundation.core.adapters.base import (
    AbstractExchangeAdapter,
    ExchangeOrderParams,
    ExchangeOrderResponse,
    ExchangePosition,
)


# ── Dataclass tests ───────────────────────────────────────────────────────


class TestExchangeOrderParams:
    def test_defaults(self) -> None:
        p = ExchangeOrderParams(symbol="BTCUSDT", side="BUY",
                                order_type="MARKET", quantity="0.01")
        assert p.time_in_force == "GTC"
        assert p.reduce_only is False
        assert p.close_position is False
        assert p.price is None
        assert p.stop_price is None

    def test_full_params(self) -> None:
        p = ExchangeOrderParams(
            symbol="ETHUSDT", side="SELL", order_type="LIMIT",
            quantity="1.5", price="2500.00", time_in_force="IOC",
            reduce_only=True, client_order_id="cid-1",
            position_side="SHORT", stop_price="2450",
            working_type="MARK_PRICE",
        )
        assert p.symbol == "ETHUSDT"
        assert p.reduce_only is True


class TestExchangeOrderResponse:
    def _make(self, **kw) -> ExchangeOrderResponse:
        defaults = dict(
            order_id="o1", client_order_id="c1", symbol="BTCUSDT",
            side="BUY", quantity="0.01", filled_qty="0.01",
            price="100000", status="FILLED", timestamp_ms=1700000000000,
        )
        defaults.update(kw)
        return ExchangeOrderResponse(**defaults)

    def test_to_dict_keys(self) -> None:
        d = self._make().to_dict()
        expected = {"orderId", "clientOrderId", "symbol", "side",
                    "origQty", "executedQty", "price", "status",
                    "time", "reason"}
        assert set(d.keys()) == expected

    def test_to_dict_values(self) -> None:
        d = self._make(order_id="X", status="REJECTED", reason="bad").to_dict()
        assert d["orderId"] == "X"
        assert d["status"] == "REJECTED"
        assert d["reason"] == "bad"


class TestExchangePosition:
    def _make(self, **kw) -> ExchangePosition:
        defaults = dict(
            symbol="BTCUSDT", position_side="BOTH", side="LONG",
            position_amount="0.01", entry_price="100000",
            mark_price="101000", unrealized_profit="10",
            leverage=10, margin_type="CROSS",
            isolated_margin=0.0, update_time_ms=1700000000000,
        )
        defaults.update(kw)
        return ExchangePosition(**defaults)

    def test_to_dict_keys(self) -> None:
        d = self._make().to_dict()
        for key in ("symbol", "positionSide", "positionAmt",
                    "position_amount", "entryPrice", "markPrice",
                    "leverage", "marginType"):
            assert key in d

    def test_to_dict_dual_amount_keys(self) -> None:
        d = self._make(position_amount="1.5").to_dict()
        assert d["positionAmt"] == "1.5"
        assert d["position_amount"] == "1.5"


# ── ABC enforcement ──────────────────────────────────────────────────────


class TestAbstractAdapterEnforcement:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            AbstractExchangeAdapter()

    def test_concrete_subclass_works(self) -> None:
        class StubAdapter(AbstractExchangeAdapter):
            async def create_order(self, params): return None
            async def cancel_order(
                self, symbol, order_id=None, client_order_id=None): return None

            async def get_open_orders(self, symbol=None): return []
            async def get_open_orders_raw(self, symbol=None): return []
            async def get_open_positions(self, symbol=None): return []
            async def get_mark_price(self, symbol, ttl_ms=250): return 0.0
            async def get_last_price(self, symbol): return 0.0
            async def get_account_balance(self): return []
            async def get_exchange_info(self, symbol): return {}
            async def quantize_quantity(self, symbol, qty): return "0"
            async def aclose(self): pass

        adapter = StubAdapter()
        assert isinstance(adapter, AbstractExchangeAdapter)
