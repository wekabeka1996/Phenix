from decimal import Decimal, ROUND_DOWN, ROUND_UP
from unittest.mock import patch

import pytest

from apps.reference.adapters.binance_adapter import BinanceAdapter, _make_binance_error


def _make_adapter() -> BinanceAdapter:
    with patch("httpx.AsyncClient"):
        return BinanceAdapter(api_key="k", api_secret="s", base_url="https://test")


def test_to_decimal_supports_scalar_and_price_dict():
    pytest.importorskip("httpx")
    adapter = _make_adapter()

    assert adapter._to_decimal("1.5") == Decimal("1.5")
    assert adapter._to_decimal(2) == Decimal("2")
    assert adapter._to_decimal({"markPrice": "3.14"}) == Decimal("3.14")
    assert adapter._to_decimal({"price": "7.00"}) == Decimal("7.00")


def test_to_decimal_rejects_invalid_inputs():
    pytest.importorskip("httpx")
    adapter = _make_adapter()

    with pytest.raises(ValueError, match="cannot be None"):
        adapter._to_decimal(None)
    with pytest.raises(ValueError, match="markPrice"):
        adapter._to_decimal({"foo": "bar"})


def test_round_step_supports_down_and_up_modes():
    pytest.importorskip("httpx")
    adapter = _make_adapter()

    qty = Decimal("123.456")
    step = Decimal("0.01")
    assert adapter._round_step(qty, step, ROUND_DOWN) == Decimal("123.45")
    assert adapter._round_step(qty, step, ROUND_UP) == Decimal("123.46")
    assert adapter._round_step(qty, Decimal("0")) == qty


def test_make_binance_error_accepts_code_msg_style():
    """Coverage for helper compatibility mode: _make_binance_error(code, msg)."""
    err = _make_binance_error(-2010, "Order would trigger immediately.")
    assert err.code == -2010
    assert err.msg == "Order would trigger immediately."
    assert err.nrr_code == "NRR-018"
