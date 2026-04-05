import json
from pathlib import Path

import pytest

try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False


REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_SIGNAL_SCHEMA_PATH = REPO_ROOT / \
    "schemas" / "strategy_signal_produced_v1.json"
DECISION_TRACE_SCHEMA_PATH = REPO_ROOT / \
    "schemas" / "decision_trace_emitted_v1.json"
TRADE_INTENT_SCHEMA_PATH = (
    REPO_ROOT / "apps/reference/domains/decision_making/schemas/trade_intent_v1.json"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _owner_ctx(*, final_owner: str | None, reason: str | None) -> dict:
    return {
        "intended_owner": "regime_tpsl",
        "final_owner": final_owner,
        "owner_loss_reason": reason,
    }


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_strategy_signal_schema_accepts_tpsl_owner_ctx_additively() -> None:
    schema = _read_json(STRATEGY_SIGNAL_SCHEMA_PATH)
    validate(
        instance={
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "ts_ms": 1702500000000,
            "rid": "aurora_BTCUSDT_1702500000000",
            "price_ctx": {"entry_price": "25668.84"},
            "tpsl_owner_ctx": _owner_ctx(
                final_owner=None,
                reason="TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
            ),
        },
        schema=schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_trade_intent_schema_accepts_legacy_payload_without_tpsl_owner_ctx() -> None:
    schema = _read_json(TRADE_INTENT_SCHEMA_PATH)
    validate(
        instance={
            "instrument": "BTCUSDT",
            "side": "buy",
            "p": "0.55",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": "10",
                "max_latency_ms": 100,
                "maker_preference": "allow",
            },
            "risk_budget": {
                "trade_cvar95_max_bps": "200",
                "session_cvar95_max_bps": "500",
            },
            "size": {
                "kelly_fraction": "0.1",
                "notional_cap_usd": "1000.00",
            },
            "order": {
                "price_ref": "50000.00",
                "qty": "0.001",
                "price": "50000.00",
                "reduce_only": False,
                "order_type": "LIMIT",
                "tif": "GTX",
            },
            "valid_for_ms": 5000,
            "why": ["test"],
            "dto_version": "1.0.0",
            "schema_ref": "trade_intent_v1.json",
        },
        schema=schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_trade_intent_schema_accepts_tpsl_owner_ctx_additively() -> None:
    schema = _read_json(TRADE_INTENT_SCHEMA_PATH)
    validate(
        instance={
            "instrument": "BTCUSDT",
            "side": "buy",
            "p": "0.55",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": "10",
                "max_latency_ms": 100,
                "maker_preference": "allow",
            },
            "risk_budget": {
                "trade_cvar95_max_bps": "200",
                "session_cvar95_max_bps": "500",
            },
            "size": {
                "kelly_fraction": "0.1",
                "notional_cap_usd": "1000.00",
            },
            "order": {
                "price_ref": "50000.00",
                "qty": "0.001",
                "price": "50000.00",
                "reduce_only": False,
                "order_type": "LIMIT",
                "tif": "GTX",
            },
            "valid_for_ms": 5000,
            "why": ["test"],
            "dto_version": "1.0.0",
            "schema_ref": "trade_intent_v1.json",
            "tpsl_owner_ctx": _owner_ctx(
                final_owner="entry_plan",
                reason="TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
            ),
        },
        schema=schema,
    )


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_decision_trace_schema_accepts_tpsl_owner_ctx_additively() -> None:
    schema = _read_json(DECISION_TRACE_SCHEMA_PATH)
    validate(
        instance={
            "symbol": "SOLUSDT",
            "ts": 1702500000000,
            "intent_side": "LONG",
            "signal_score": 0.9,
            "regime": "LOW_VOLATILITY",
            "regime_confidence": 0.42,
            "trend_dir": "UP",
            "trend_run_length": None,
            "delta_price": 0.0,
            "pm_norm_10s": 0.0,
            "pm_norm_60s": 0.0,
            "pm_norm_300s": 0.0,
            "vol_pct_10s": 0.0,
            "vol_pct_60s": 0.0,
            "vol_pct_300s": 0.0,
            "gate_outcome": "ALLOW",
            "deny_reason": None,
            "why": "owner trace",
            "tpsl_owner_ctx": _owner_ctx(
                final_owner="entry_plan",
                reason="TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
            ),
        },
        schema=schema,
    )
