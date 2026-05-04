from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


SCHEMA_PATH = Path(
    "apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json")


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _base_payload() -> dict:
    return {
        "positions_last_ts_ms": 1_700_000_000_000,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "net_position": "1.0",
                "avg_entry_price": "100.0",
                "venues": ["binance"],
            }
        ],
    }


def test_position_accepts_symbol_economics_fields() -> None:
    payload = _base_payload()
    payload["positions"][0].update(
        {
            "markPrice": "110.0",
            "unrealizedPnl": "10.0",
            "unrealizedPnlPct": "10.0",
        }
    )

    jsonschema.validate(payload, _schema())


def test_position_accepts_nullable_symbol_economics_when_unavailable() -> None:
    payload = _base_payload()
    payload["positions"][0].update(
        {
            "markPrice": None,
            "unrealizedPnl": None,
            "unrealizedPnlPct": None,
        }
    )

    jsonschema.validate(payload, _schema())


def test_position_rejects_unknown_economics_fields() -> None:
    payload = _base_payload()
    payload["positions"][0]["mystery_field"] = "nope"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, _schema())


def test_position_rejects_malformed_symbol_economics() -> None:
    payload = _base_payload()
    payload["positions"][0]["markPrice"] = "bad"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, _schema())
