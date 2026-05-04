"""Tests for ExchangeContext — shared session context (Phase 14C)."""
import pytest
from pydantic import ValidationError
from vfoundation.core.exchange_context import ExchangeContext


class TestExchangeContext:
    def test_default_values(self):
        ctx = ExchangeContext(exchange="BINANCE")
        assert ctx.exchange == "BINANCE"
        assert ctx.account_id == "default"
        assert ctx.is_paper is False
        assert ctx.leverage == 1.0

    def test_custom_values(self):
        ctx = ExchangeContext(
            exchange="BYBIT",
            account_id="sub_01",
            is_paper=True,
            leverage=10.0,
            extra_meta={"tier": "vip"}
        )
        assert ctx.exchange == "BYBIT"
        assert ctx.leverage == 10.0
        assert ctx.extra_meta == {"tier": "vip"}

    def test_serialization_roundtrip(self):
        ctx = ExchangeContext(exchange="OKX", leverage=5.0)
        data = ctx.model_dump()
        ctx2 = ExchangeContext(**data)
        assert ctx2 == ctx

    def test_invalid_leverage_rejected(self):
        with pytest.raises(ValidationError):
            ExchangeContext(exchange="A", leverage=0.0)

    def test_negative_leverage_rejected(self):
        with pytest.raises(ValidationError):
            ExchangeContext(exchange="A", leverage=-1.0)

    def test_immutable_by_default(self):
        ctx = ExchangeContext(exchange="A")
        with pytest.raises(Exception):
            ctx.exchange = "B"

    def test_extra_meta_defaults_to_empty_dict(self):
        ctx = ExchangeContext(exchange="A")
        assert ctx.extra_meta == {}
