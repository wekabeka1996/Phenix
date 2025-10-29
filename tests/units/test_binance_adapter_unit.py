import time
from decimal import Decimal
import hmac
import hashlib

import importlib.util
import os

# Load BinanceAdapter from source path to avoid import issues in test env
spec = importlib.util.spec_from_file_location(
    "vfoundation.adapters.binance_adapter",
    os.path.join(os.path.dirname(__file__), "..", "..", "vfoundation", "adapters", "binance_adapter.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BinanceAdapter = mod.BinanceAdapter


def test_norm_params_and_sign_build(monkeypatch):
    adapter = BinanceAdapter(api_key="k", api_secret="s", base_url="https://test")

    d = {"flag": True, "amt": Decimal("0.1000"), "none": None}
    out = adapter._norm_params(d)
    assert out["flag"] == "true"
    assert out["amt"] == "0.1"
    assert "none" not in out

    # Patch time.time to fixed value so signature is deterministic
    monkeypatch.setattr('time.time', lambda: 1234567890.0)
    adapter._time_offset_ms = 0
    qs, final = adapter._sign_build({"a": 1, "b": "x"})

    assert "signature=" in qs
    assert "timestamp" in final
    assert "signature" in final
    # verify signature matches hmac with secret
    # signature is computed over qs without signature; final['signature'] holds the hex
    sig = final['signature']
    # recompute expected
    base = adapter._norm_params({"a": 1, "b": "x"})
    base["timestamp"] = str(int(time.time() * 1000))
    base.setdefault("recvWindow", str(adapter._recv_window_ms))
    from urllib.parse import urlencode, quote_plus
    qs_no_sig = urlencode(base, doseq=True, quote_via=quote_plus)
    expected = hmac.new(adapter.api_secret, qs_no_sig.encode(), hashlib.sha256).hexdigest()
    assert sig == expected
