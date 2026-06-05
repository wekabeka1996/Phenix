import hashlib
import hmac
from decimal import Decimal
from urllib.parse import quote_plus, urlencode
from unittest.mock import patch

import pytest

from apps.reference.adapters.binance_adapter import (
    BinanceAdapter,
    BinanceAPIError,
    _make_binance_error,
)


def _make_adapter() -> BinanceAdapter:
    with patch("httpx.AsyncClient"):
        return BinanceAdapter(api_key="k", api_secret="s", base_url="https://test")


def test_norm_params_and_sign_build_current_arch(monkeypatch):
    """Unit coverage for current adapter location (apps/reference), not removed vfoundation shim."""
    pytest.importorskip("httpx")
    adapter = _make_adapter()

    normalized = adapter._norm_params(
        {"flag": True, "amt": Decimal("0.1000"), "none": None}
    )
    assert normalized["flag"] == "true"
    assert normalized["amt"] == "0.1"
    assert "none" not in normalized

    monkeypatch.setattr("apps.reference.adapters.binance_adapter.time.time", lambda: 1234567890.0)
    adapter._time_offset_ms = 0

    qs, final = adapter._sign_build({"a": 1, "b": "x"})
    assert "signature=" in qs
    assert "timestamp" in final
    assert "signature" in final

    expected_base = adapter._norm_params({"a": 1, "b": "x"})
    expected_base["timestamp"] = str(int(1234567890.0 * 1000))
    expected_base.setdefault("recvWindow", str(adapter._recv_window_ms))
    expected_qs = urlencode(expected_base, doseq=True, quote_via=quote_plus)
    expected_sig = hmac.new(
        adapter.api_secret,
        expected_qs.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert final["signature"] == expected_sig


def test_make_binance_error_maps_rejection_code_to_nrr():
    """Exchange rejection codes should map to NRR-018 for downstream normalization."""

    class DummyResp:
        status_code = 400

    err = _make_binance_error(DummyResp(), {"code": -1013, "msg": "Invalid quantity"})
    assert isinstance(err, BinanceAPIError)
    assert err.code == -1013
    assert err.nrr_code == "NRR-018"
    assert "Invalid quantity" in str(err)
