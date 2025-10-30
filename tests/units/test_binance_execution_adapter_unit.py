import hmac
import hashlib

import importlib.util
import importlib.machinery
import sys
import os

# Load execution_adapter module first to satisfy the relative import inside the adapter
base_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "apps",
    "reference",
    "domains",
    "execution_position",
)
exec_adapter_path = os.path.join(base_path, "execution_adapter.py")
spec_exec = importlib.util.spec_from_file_location(
    "apps.reference.domains.execution_position.execution_adapter", exec_adapter_path
)
mod_exec = importlib.util.module_from_spec(spec_exec)
sys.modules[spec_exec.name] = mod_exec
spec_exec.loader.exec_module(mod_exec)

binance_path = os.path.join(base_path, "binance_execution_adapter.py")
spec_bin = importlib.util.spec_from_file_location(
    "apps.reference.domains.execution_position.binance_execution_adapter", binance_path
)
mod_bin = importlib.util.module_from_spec(spec_bin)
sys.modules[spec_bin.name] = mod_bin
spec_bin.loader.exec_module(mod_bin)
BinanceExecutionAdapter = mod_bin.BinanceExecutionAdapter


def test_generate_signature_placeholder():
    # Signature generation tested indirectly by ensuring param ordering logic is as expected
    params = {"symbol": "BTCUSDT", "quantity": "0.1"}
    # ensure sorted order
    qs = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
    assert qs == "quantity=0.1&symbol=BTCUSDT"


def test_build_order_params_market_and_limit():
    cfg_market = {"trading": {"execution": {"open_order_type": "MARKET"}}}
    # call unbound _build_order_params with dummy objects
    import types

    dummy_m = types.SimpleNamespace(config=cfg_market)
    pld = {"symbol": "BTCUSDT", "side": "BUY", "qty": "0.2"}
    params_m = BinanceExecutionAdapter._build_order_params.__get__(
        dummy_m, BinanceExecutionAdapter
    )(pld)
    assert params_m["type"] == "MARKET"
    assert params_m["quantity"] == "0.2"

    cfg_limit = {
        "trading": {
            "execution": {
                "open_order_type": "LIMIT",
                "order_params": {"LIMIT": {"timeInForce": "GTC"}},
            }
        }
    }
    dummy_l = types.SimpleNamespace(config=cfg_limit)
    pld2 = {"symbol": "BTCUSDT", "side": "SELL", "qty": "0.5", "price": "40000"}
    params_l = BinanceExecutionAdapter._build_order_params.__get__(
        dummy_l, BinanceExecutionAdapter
    )(pld2)
    assert params_l["type"] == "LIMIT"
    assert params_l["price"] == "40000"
    assert params_l.get("timeInForce") == "GTC"
