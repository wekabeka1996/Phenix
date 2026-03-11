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
            "bar_close_ts": 1702500299999,
            "close_boundary_ts_ms": 1702500300000,
            "source_mode": "live",
            "bar_identity": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 300,
                "bar_start_ts_ms": 1702500000000,
                "bar_end_ts_ms": 1702500299999,
                "close_boundary_ts_ms": 1702500300000,
                "source_mode": "live",
            },
            "replay_identity": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 300,
                "close_boundary_ts_ms": 1702500300000,
                "source_mode": "live",
                "replay_generation": 0,
            },
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
            "bar_close_ts": 1702500299999,
            "close_boundary_ts_ms": 1702500300000,
            "source_mode": "live",
            "bar_identity": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 300,
                "bar_start_ts_ms": 1702500000000,
                "bar_end_ts_ms": 1702500299999,
                "close_boundary_ts_ms": 1702500300000,
                "source_mode": "live",
            },
            "replay_identity": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 300,
                "close_boundary_ts_ms": 1702500300000,
                "source_mode": "live",
                "replay_generation": 0,
            },
            "gap_state": "GAP_DETECTED",
            "gap_policy_action": "DEGRADE_TO_NON_TRADING",
            "gap_bars_skipped": 2,
            "is_gap_bar": True,
            "gap": {
                "state": "GAP_DETECTED",
                "policy_action": "DEGRADE_TO_NON_TRADING",
                "gap_bars_skipped": 2,
                "is_gap_bar": True,
                "why": ["gap_detected", "gap_bars_skipped:2"],
                "detected_at": 1702500299999,
                "source": "market_data:payload_bridge",
                "evidence_ref": "bar:BTCUSDT:300:1702500300000:live",
            },
            "why_chain": [
                "enter:buy:score=0.0069>=thr_buy=0.0021",
                "tpsl:regime=TREND_DOWN mode=pct_mult sl_pct_post=0.0050 tp_rr_pre=2.00 rr_post=2.00",
            ],
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": False,
                "mode": "PROTECT_ONLY",
            },
            "runtime_readiness": {
                "strategy_id": "aurora",
                "symbol": "BTCUSDT",
                "updated_at": 1702500000000,
                "source": "decision_making:aurora",
                "blocking_reason_chain": [
                    "basis_bar_gap",
                    "gap_detected",
                    "degrade_to_non_trading",
                    "gap_bars_skipped:2",
                    "protect_only"
                ],
                "permissions": {
                    "can_manage_existing_risk": True,
                    "can_open_new_risk": False,
                    "mode": "PROTECT_ONLY",
                },
                "scopes": {
                    "basis_bar_ready": {
                        "state": "INVALIDATED_GAP",
                        "why": [
                            "basis_bar_gap",
                            "gap_detected",
                            "degrade_to_non_trading",
                            "gap_bars_skipped:2"
                        ],
                        "updated_at": 1702500000000,
                        "source": "market_data:payload_bridge",
                        "evidence_ref": "bar:BTCUSDT:300:1702500300000:live"
                    },
                    "strategy_ready_per_symbol": {
                        "state": "READY",
                        "why": ["signal_emitted"],
                        "updated_at": 1702500000000,
                        "source": "decision_making:aurora",
                        "evidence_ref": "signal:BTCUSDT:1702500000000",
                    },
                    "trading_ready": {
                        "state": "BLOCKED",
                        "why": [
                            "basis_bar_gap",
                            "gap_detected",
                            "degrade_to_non_trading",
                            "gap_bars_skipped:2",
                            "protect_only"
                        ],
                        "updated_at": 1702500000000,
                        "source": "decision_making:aurora",
                        "evidence_ref": "signal:BTCUSDT:1702500000000"
                    }
                },
            },
            "rollout_mode": "quadratic_shadow",
            "rollback_armed_status": "DISARMED",
            "quadratic_rollout": {
                "mode": "quadratic_shadow",
                "requested_scoring_version": "v2",
                "effective_live_scoring_version": "v2",
                "live_profile_id": "aurora_v2",
                "shadow_requested": True,
                "quadratic_readiness_state": "COLD",
                "quadratic_can_open_new_risk": False,
                "protect_existing_risk_allowed": True,
                "rollback_armed": False,
                "rollback_armed_status": "DISARMED",
                "rollback_reason_chain": [],
                "quadratic_blocking_reason_chain": [
                    "quadratic_htf_not_ready",
                    "quadratic_htf_state:COLD",
                    "runtime_open_new_risk_blocked"
                ],
                "shadow_evaluation": {
                    "state": "DEFERRED",
                    "score": None,
                    "side": None,
                    "thr_buy": None,
                    "thr_sell": None,
                    "defer_reason": "PILLAR_WARMUP",
                    "why_chain": [],
                    "error": None,
                    "psi_vector": {}
                }
            },
            "analytics_restore": {
                "strategy_id": "aurora",
                "symbol": "BTCUSDT",
                "updated_at": 1702500000000,
                "source": "startup:test",
                "rollup_state": "PARTIAL",
                "counts": {
                    "RESTORED": 1,
                    "COLD": 3,
                    "PARTIAL": 0,
                    "INVALIDATED_DUE_TO_GAP": 0
                },
                "blocking_reason_chain": [
                    "analytics_restore_partial",
                    "analytics_open_new_risk_blocked",
                    "protect_only"
                ],
                "permissions": {
                    "can_manage_existing_risk": True,
                    "can_open_new_risk": False,
                    "mode": "PROTECT_ONLY"
                },
                "scopes": {
                    "execution_state": {
                        "state": "RESTORED",
                        "why": ["execution_snapshot_loaded"],
                        "updated_at": 1702500000000,
                        "source": "execution_position:startup_restore",
                        "evidence_ref": "execution:BTCUSDT:1702500000000"
                    },
                    "feature_engineering_cache": {
                        "state": "COLD",
                        "why": ["fe_cache_restore_missing"],
                        "updated_at": 1702500000000,
                        "source": "feature_engineering:startup_restore",
                        "evidence_ref": "fe_cache:BTCUSDT:1702500000000"
                    }
                }
            },
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
