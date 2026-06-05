import json
from pathlib import Path

import pytest

try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "reference"
    / "domains"
    / "execution_position"
    / "schemas"
    / "order_fill_v1.json"
)


@pytest.fixture(scope="session")
def order_fill_schema():
    with open(SCHEMA_PATH, "r") as f:
        return json.load(f)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_order_fill_backtest_payload_is_valid(order_fill_schema):
    validate(
        instance={
            "orderId": "12345",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.1",
            "price": "50000.0",
            "filled_qty": "0.1",
            "fee": "1.0",
            "fee_asset": "USDT",
            "role": "TAKER",
            "timestamp": 1700000000000,
            "clientOrderId": "ENTRY_BTCUSDT_x",
            "status": "FILLED",
        },
        schema=order_fill_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_order_fill_sim_payload_is_valid(order_fill_schema):
    validate(
        instance={
            "orderId": "ext_order_123",
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "clientOrderId": "sim_test_001",
            "rid": "sim_test_001",
            "price": "95000.0",
            "quantity": "0.1",
            "commission": "0.05",
            "commissionAsset": "USDT",
            "tradeId": 999999,
        },
        schema=order_fill_schema,
    )

