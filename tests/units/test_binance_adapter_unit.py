import time
from decimal import Decimal
import hmac
import hashlib
from urllib.parse import urlencode, quote_plus

from vfoundation.adapters.binance_adapter import BinanceAdapter


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
    qs_no_sig = urlencode(base, doseq=True, quote_via=quote_plus)
    expected = hmac.new(adapter.api_secret, qs_no_sig.encode(), hashlib.sha256).hexdigest()
    assert sig == expected
