"""Tests for vfoundation.core.payloads — typed schemas (Phase 14C)."""
import pytest
from pydantic import ValidationError
from vfoundation.core.payloads import (
    OpenPayload, ClosePayload, FillPayload,
    CancelPayload, RejectPayload, ReconcilePayload,
)
from vfoundation.core.protocol import Message


class TestOpenPayload:
    def test_valid_buy(self):
        p = OpenPayload(symbol="BTCUSDT", side="BUY", qty=0.01)
        assert p.symbol == "BTCUSDT"
        assert p.price is None

    def test_valid_with_price(self):
        p = OpenPayload(symbol="ETHUSDT", side="SELL", qty=1.0, price=3000.0)
        assert p.price == 3000.0

    def test_invalid_side_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(symbol="BTC", side="LONG", qty=0.01)

    def test_missing_symbol_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(side="BUY", qty=0.01)

    def test_zero_qty_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(symbol="BTC", side="BUY", qty=0.0)

    def test_negative_qty_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(symbol="BTC", side="BUY", qty=-1.0)

    def test_round_trip(self):
        p = OpenPayload(symbol="BTCUSDT", side="BUY", qty=0.5)
        assert OpenPayload(**p.model_dump()) == p


class TestClosePayload:
    def test_valid(self):
        p = ClosePayload(symbol="BTCUSDT", reason="tp_hit")
        assert p.symbol == "BTCUSDT"

    def test_missing_reason_rejected(self):
        with pytest.raises(ValidationError):
            ClosePayload(symbol="BTC")

    def test_reduce_only_default_true(self):
        p = ClosePayload(symbol="BTC", reason="sl")
        assert p.reduce_only is True


class TestFillPayload:
    def test_valid(self):
        p = FillPayload(order_id="abc", symbol="BTC", qty=0.01,
                        price=50000.0, ts_fill=1700000000000)
        assert p.order_id == "abc"

    def test_missing_order_id_rejected(self):
        with pytest.raises(ValidationError):
            FillPayload(symbol="BTC", qty=0.01, price=50000.0, ts_fill=1700000000000)


class TestCancelPayload:
    def test_valid(self):
        p = CancelPayload(order_id="x", symbol="ETH", reason="timeout")
        assert p.order_id == "x"

    def test_default_reason(self):
        p = CancelPayload(order_id="x", symbol="ETH")
        assert p.reason == "user_request"


class TestRejectPayload:
    def test_valid(self):
        p = RejectPayload(reason_code="NRR-011", message="Exposure limit exceeded")
        assert p.reason_code == "NRR-011"

    def test_optional_symbol(self):
        p = RejectPayload(reason_code="NRR-012", message="rate limit", symbol="BTC")
        assert p.symbol == "BTC"


class TestMessageTypedPayload:
    def test_typed_payload_open(self):
        msg = Message(
            op="DEC", verb="OPEN", src="decision_making",
            dst="execution_position", why="signal",
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": 0.01}
        )
        payload = msg.typed_payload(OpenPayload)
        assert isinstance(payload, OpenPayload)
        assert payload.symbol == "BTCUSDT"

    def test_typed_payload_wrong_data_raises(self):
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", why="x",
                      pld={"symbol": "BTC"})  # missing side, qty
        with pytest.raises(ValidationError):
            msg.typed_payload(OpenPayload)

    def test_typed_payload_empty_pld_raises(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        with pytest.raises(ValidationError):
            msg.typed_payload(OpenPayload)

    def test_typed_payload_close(self):
        msg = Message(op="CMD", verb="CLOSE", src="a", dst="b", why="x",
                      pld={"symbol": "ETH", "reason": "manual"})
        payload = msg.typed_payload(ClosePayload)
        assert payload.symbol == "ETH"
