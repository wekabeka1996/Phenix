import decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.decision_making.intent_builder import IntentBuilder


REGIME_PROVENANCE = {
    "source_kind": "detector_cache",
    "detector_event": {
        "event_name": "EVT:REGIME_DETECTED",
        "rid": "regime-rid-001",
        "ts_ms": 1700000000000,
        "bar_close_ts_ms": 1700000000000,
        "regime": "TREND_UP",
        "confidence": "0.82",
    },
    "cache_snapshot": {
        "cache_write_ts_ms": 1700000001111,
        "regime": "TREND_UP",
        "confidence": 0.82,
    },
}

OWNER_CTX = {
    "intended_owner": "regime_tpsl",
    "final_owner": "entry_plan",
    "owner_loss_reason": "TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
}


class _FakeSG:
    def __init__(self) -> None:
        self.intent_side = "LONG"
        self.trace_ts_ms = 1700000001234
        self.why_short = "allow:trend-up"
        self.signal_score = 0.91
        self.regime = "TREND_UP"
        self.regime_confidence = 0.82
        self.regime_provenance = REGIME_PROVENANCE
        self.trend_dir = 1
        self.trend_run_length = 7
        self.delta_price = 12.5
        self.pm_norm_10s = 0.1
        self.pm_norm_60s = 0.2
        self.pm_norm_300s = 0.3
        self.vol_pct_10s = 1.1
        self.vol_pct_60s = 1.2
        self.vol_pct_300s = 1.3
        self.min_regime_confidence = 0.42
        self.threshold_applied = True
        self.threshold_verdict = "PASS"
        self.threshold_reason = "regime_confidence=0.82 >= min=0.42"


def _safe_decimal(value, default=None):
    if value in (None, "", "None"):
        return default
    try:
        return decimal.Decimal(str(value))
    except Exception:
        return default


def _make_config():
    strategy_cfg = SimpleNamespace(
        execution=SimpleNamespace(
            entry_order_type="LIMIT",
            entry_tif="GTC",
        ),
        decision=SimpleNamespace(kelly=SimpleNamespace(fraction="0.15")),
    )
    order_capabilities = SimpleNamespace(
        supported_order_types=["LIMIT", "MARKET"],
        supported_tif=["GTC", "GTX", "IOC", "FOK"],
    )
    pending_entry_ttl = SimpleNamespace(
        enabled=True,
        ttl_by_tf_sec={300: 10},
        reject_unknown_tf=True,
    )
    return SimpleNamespace(
        strategies=SimpleNamespace(aurora=strategy_cfg),
        domains=SimpleNamespace(
            execution_position=SimpleNamespace(
                order_capabilities=order_capabilities,
                pending_entry_ttl=pending_entry_ttl,
            )
        ),
    )


def _make_builder() -> IntentBuilder:
    clock = MagicMock()
    clock.now_ms.return_value = 1700000000000
    clock.now_sec.return_value = 1700000000
    return IntentBuilder(
        logger=MagicMock(),
        fsm=MagicMock(),
        clock=clock,
        config=_make_config(),
        tca_prefs={
            "max_slippage_bps": 25,
            "max_latency_ms": 3000,
            "maker_preference": "neutral",
        },
        risk_budgets={
            "trade_cvar95_max_bps": 100,
            "session_cvar95_max_bps": 200,
        },
        safe_decimal_fn=_safe_decimal,
        check_strategy_arbitration_fn=MagicMock(
            return_value={"allowed": True}),
        warmup_gate_fn=lambda **_kwargs: False,
        emit_rejected_fn=MagicMock(),
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0, 600, 0.6, 0.9)),
        side_intent_window={},
        get_regime_epoch_ref_fn=lambda symbol: f"epoch:{symbol}:123",
    )


def _build_kwargs() -> dict:
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": decimal.Decimal("1.5"),
        "price": decimal.Decimal("50000.25"),
        "why_chain": ["alpha", "beta"],
        "rid": "rid-payload-001",
        "reduce_only": False,
        "strategy_id": "aurora",
        "decision_ts_ms": 1700000000999,
        "stop_price": "49000.50",
        "target_price": decimal.Decimal("51000.75"),
        "entry_plan_trace": {"plan": "maker_pullback"},
        "tf_sec": 300,
        "max_slippage_bps": None,
        "max_latency_ms": None,
        "risk_score": 0.33,
        "tpsl_owner_ctx": OWNER_CTX,
        "strategy_trace": {"objective": {"score": 0.9}, "model": "aurora"},
        "normalize_mode": "signed_v2",
        "sg": _FakeSG(),
    }


def test_build_and_emit_preserves_trade_intent_payload_contract() -> None:
    builder = _make_builder()

    with (
        patch("apps.reference.domains.decision_making.intent_builder.wal.append", return_value="wal-ok") as mock_wal,
        patch("apps.reference.domains.decision_making.intent_builder.order_logger.write"),
        patch("apps.reference.domains.decision_making.intent_builder.print"),
        patch("apps.reference.domains.decision_making.intent_builder.emit_regime_decision_audit"),
        patch(
            "apps.reference.domains.decision_making.intent_builder._trade_lifecycle", None),
    ):
        builder.build_and_emit(**_build_kwargs())

    payload = dict(mock_wal.call_args[0][0]["pld"])
    payload["idempotent_key"] = "<uuid>"

    assert payload == {
        "rid": "rid-payload-001",
        "instrument": "BTCUSDT",
        "side": "BUY",
        "strategy": "aurora",
        "order": {
            "qty": "1.5",
            "price": "50000.25",
            "price_ref": "50000.25",
            "reduce_only": False,
            "order_type": "LIMIT",
            "tif": "GTC",
        },
        "p": "0.75",
        "payoff_ratio_r": "2.0",
        "tca_budget": {
            "max_slippage_bps": "25",
            "max_latency_ms": 3000,
            "maker_preference": "neutral",
        },
        "risk_context": {"risk_score": 0.33},
        "risk_budget": {
            "trade_cvar95_max_bps": "100",
            "session_cvar95_max_bps": "200",
        },
        "size": {
            "notional_cap_usd": "75000.375",
            "kelly_fraction": "0.15",
        },
        "valid_for_ms": 10000,
        "why": ["alpha", "beta"],
        "dto_version": "1.0.0",
        "schema_ref": "trade_intent_v1.json",
        "idempotent_key": "<uuid>",
        "stop_price": "49000.50",
        "target_price": "51000.75",
        "entry_plan": {"plan": "maker_pullback"},
        "regime": "TREND_UP",
        "regime_confidence": 0.82,
        "regime_provenance": REGIME_PROVENANCE,
        "regime_epoch_ref": "epoch:BTCUSDT:123",
        "tpsl_owner_ctx": OWNER_CTX,
        "trace": {"objective": {"score": 0.9}, "model": "aurora"},
    }


def test_build_and_emit_preserves_decision_trace_payload_contract() -> None:
    builder = _make_builder()

    with (
        patch("apps.reference.domains.decision_making.intent_builder.wal.append",
              return_value="wal-ok"),
        patch("apps.reference.domains.decision_making.intent_builder.order_logger.write"),
        patch("apps.reference.domains.decision_making.intent_builder.print"),
        patch("apps.reference.domains.decision_making.intent_builder.emit_regime_decision_audit"),
        patch(
            "apps.reference.domains.decision_making.intent_builder._trade_lifecycle", None),
    ):
        builder.build_and_emit(**_build_kwargs())

    decision_trace_calls = [
        call.kwargs["payload"]
        for call in builder._fsm.emit.call_args_list
        if call.args[0] == "EVT:DECISION_TRACE_EMITTED"
    ]

    assert decision_trace_calls == [
        {
            "symbol": "BTCUSDT",
            "ts": 1700000001234,
            "intent_side": "LONG",
            "signal_score": 0.91,
            "regime": "TREND_UP",
            "regime_confidence": 0.82,
            "trend_dir": 1,
            "trend_run_length": 7,
            "delta_price": 12.5,
            "pm_norm_10s": 0.1,
            "pm_norm_60s": 0.2,
            "pm_norm_300s": 0.3,
            "vol_pct_10s": 1.1,
            "vol_pct_60s": 1.2,
            "vol_pct_300s": 1.3,
            "gate_outcome": "ALLOW",
            "deny_reason": None,
            "why": "allow:trend-up",
            "regime_provenance": REGIME_PROVENANCE,
            "tpsl_owner_ctx": OWNER_CTX,
        }
    ]
