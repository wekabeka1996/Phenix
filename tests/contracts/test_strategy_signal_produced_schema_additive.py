import json
from pathlib import Path

import pytest

try:
    from jsonschema import ValidationError, validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False
    ValidationError = Exception


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "strategy_signal_produced_v1.json"


@pytest.fixture(scope="session")
def strategy_signal_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_strategy_signal_minimal_payload_is_valid(strategy_signal_schema):
    validate(
        instance={
            "symbol": "BTCUSDT",
            "strategy_id": "test",
        },
        schema=strategy_signal_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_strategy_signal_mean_reversion_payload_is_valid(strategy_signal_schema):
    validate(
        instance={
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "side": "BUY",
            "readiness": {"warmup_ok": True},
            "score": 0.82,
            "why": "long_entry",
            "ts_ms": 1702500000000,
            "rid": "rid-abc",
            "why_chain": ["long_entry"],
            "price_ctx": {
                "entry_price": "50000",
                "stop_price": None,
                "target_price": None,
            },
            "regime": "UNKNOWN",
            "volatility": None,
            "liquidity": None,
            "mr_params": {
                "sizing_mult": 1.0,
                "stop_mult": 1.0,
                "target_mult": 1.0,
            },
        },
        schema=strategy_signal_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_strategy_signal_aurora_payload_is_valid(strategy_signal_schema):
    validate(
        instance={
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "ts_ms": 1702500000000,
            "rid": "aurora_BTCUSDT_1702500000000",
            "why_chain": [
                "enter:buy:score=0.0069>=thr_buy=0.0021",
                "tpsl:regime=TREND_DOWN mode=pct_mult sl_pct_post=0.0050 tp_rr_pre=2.00 rr_post=2.00",
            ],
            "readiness": {"warmup_ok": True},
            "price_ctx": {
                "entry_price": "25668.8464",
                "stop_price": "25540.5021",
                "target_price": "25925.5348",
            },
            "scoring": {
                "score": 0.00690827,
                "thr_buy": 0.0021030645,
                "thr_sell": 0.0017,
                "regime": "TREND_DOWN",
                "psi_vector": {"source": "feature:pillar_sum"},
            },
            "volatility": {
                "atr_14": 95.01,
                "atr_ready": True,
            },
            "liquidity": {
                "obi_close": "0.1666",
            },
            "tf_sec": 300,
            "regime_ctx": {
                "confidence": 0.39,
                "regime_ts_ms": 1702500000000,
                "regime_age_sec": 0.0,
                "regime": "TREND_DOWN",
            },
            "quantization": {
                "qty": "0.268",
                "notional": "6879.25",
                "margin_required": "343.96",
            },
            "tpsl_ctx": {
                "mode": "pct_mult",
                "regime_used": "TREND_DOWN",
                "sl_pct_post": 0.005,
                "rr_post": 2.0,
            },
        },
        schema=strategy_signal_schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_strategy_signal_payload_requires_symbol(strategy_signal_schema):
    with pytest.raises(ValidationError):
        validate(
            instance={"strategy_id": "aurora", "side": "BUY"},
            schema=strategy_signal_schema,
        )
