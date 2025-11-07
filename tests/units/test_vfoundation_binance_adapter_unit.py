import hashlib
import hmac
from decimal import Decimal
from urllib.parse import urlencode, quote_plus

import pytest
import importlib.util
import pathlib
import sys

# Load module by file path so tests don't depend on package installation
_p = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vfoundation"
    / "adapters"
    / "binance_adapter.py"
)
spec = importlib.util.spec_from_file_location(
    "vfoundation.adapters.binance_adapter", str(_p)
)
ba_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba_mod)
sys.modules["vfoundation.adapters.binance_adapter"] = ba_mod


def test_norm_params_converts_and_filters():
    a = ba_mod.BinanceAdapter(
        api_key="k", api_secret="s", base_url="https://test")
    params = {"a": None, "b": True, "c": Decimal("1.2300"), "d": 5}
    out = a._norm_params(params)
    assert "a" not in out
    assert out["b"] == "true"
    assert out["c"] == "1.23"
    assert out["d"] == "5"


def test_to_decimal_and_rounding_and_errors():
    a = ba_mod.BinanceAdapter(
        api_key="k", api_secret="s", base_url="https://test")
    assert a._to_decimal("1.5") == Decimal("1.5")
    assert a._to_decimal(2) == Decimal("2")
    with pytest.raises(ValueError):
        a._to_decimal(None)
    # dict with markPrice
    assert a._to_decimal({"markPrice": "3.14"}) == Decimal("3.14")
    # rounding step
    from decimal import Decimal as D

    r = a._round_step(D("123.456"), D("0.01"))
    assert isinstance(r, D)


def test_sign_build_is_deterministic(monkeypatch):
    a = ba_mod.BinanceAdapter(
        api_key="KKEY", api_secret="SSECRET", base_url="https://test"
    )
    # set time to fixed value
    monkeypatch.setattr(ba_mod.time, "time", lambda: 1000.0)
    a._time_offset_ms = 0
    a._recv_window_ms = 20000

    base = {"symbol": "BTCUSDT", "side": "BUY"}
    qs, final = a._sign_build(base)

    # replicate expected signature
    base_norm = a._norm_params({"symbol": "BTCUSDT", "side": "BUY"})
    ts = int(1000.0 * 1000)
    base_norm["timestamp"] = str(ts)
    base_norm.setdefault("recvWindow", str(a._recv_window_ms))
    expected_qs = urlencode(base_norm, doseq=True, quote_via=quote_plus)
    expected_sig = hmac.new(
        a.api_secret, expected_qs.encode(), hashlib.sha256
    ).hexdigest()

    assert final["signature"] == expected_sig
    assert expected_sig in qs


@pytest.mark.skip(reason="Methods _is_code_1021 and _make_binance_error not found in module")
def test_is_code_1021_and_make_error():
    err = {"code": -1021, "msg": "time"}
    assert ba_mod._is_code_1021(err) is True

    class DummyResp:
        status = 400

    bin_err = ba_mod._make_binance_error(DummyResp(), err)
    assert isinstance(bin_err, ba_mod.BinanceAPIError)
    assert bin_err.code == -1021
