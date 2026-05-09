import decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.decision_making.intent.builder import IntentBuilder


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
        self.trend_dir = "UP"
        self.trend_confidence = 0.75
        self.trend_run_length = 7
        self.delta_price = 12.5
        self.pm_norm_10s = 0.1
        self.pm_norm_60s = 0.2
        self.pm_norm_300s = 0.3
        self.vol_pct_10s = 1.1
        self.vol_pct_60s = 1.2
        self.vol_pct_300s = 1.3
        self.min_regime_confidence = 0.45
        self.resolved_min_regime_confidence = 0.45
        self.resolved_min_regime_confidence_source = "scalar_legacy"
        self.resolved_min_regime_confidence_strategy_id = None
        self.resolved_min_regime_confidence_regime_key = None
        self.resolved_regime_confidence_strategy_id = "aurora"
        self.resolved_regime_confidence_symbol = "BTCUSDT"
        self.resolved_regime_confidence_regime_key = None
        self.resolved_max_regime_confidence = None
        self.resolved_max_regime_confidence_source = None
        self.resolved_max_regime_confidence_strategy_id = None
        self.resolved_max_regime_confidence_regime_key = None
        self.resolved_regime_confidence_band_active = True
        self.regime_confidence_breach_kind = "none"
        self.regime_confidence_gate_verdict = "ALLOW"
        self.apply_safety_gates = True
        self.directional_sanity_enabled = True
        self.nrr026_enabled = False
        self.nrr026_effective_enforced = False
        self.nrr027_enabled = False
        self.nrr027_effective_enforced = False
        self.price_motion_sanity_enabled = False
        self.price_motion_backtest_bypass = False
        self.nrr028_enabled = False
        self.nrr028_effective_enforced = False
        self.nrr029_enabled = False
        self.nrr029_effective_enforced = False
        self.nrr030_enabled = False
        self.nrr030_effective_enforced = False
        self.nrr063_enabled = True
        self.nrr063_effective_enforced = True
        self.threshold_applied = True
        self.threshold_verdict = "PASS"
        self.threshold_reason = "regime_confidence=0.82 within band min=0.45 min_source=scalar_legacy max=None max_source=None"
        self.low_vol_cost_floor_details = {
            "evaluation_stage": "observe_only",
            "gate_mode": "observe_only",
            "would_block": False,
            "price_motion_context": {
                "pm_norm_10s": 0.1,
                "pm_norm_60s": 0.2,
                "pm_norm_300s": 0.3,
                "vol_pct_10s": 1.1,
                "vol_pct_60s": 1.2,
                "vol_pct_300s": 1.3,
            },
            "persistence_context": {
                "decision_trace_event": "EVT:DECISION_TRACE_EMITTED",
                "order_logger_event": "ORDER_INTENT",
                "persisted_in": ["EVT:DECISION_TRACE_EMITTED", "ORDER_INTENT"],
            },
        }


def _safe_decimal(value, default=None):
    if value in (None, "", "None"):
        return default
    try:
        return decimal.Decimal(str(value))
    except Exception:
        return default


def _make_config():
    kelly_cfg = SimpleNamespace(
        base_probability="0.5",
        kelly_cap="0.25",
        kelly_alpha="0.8",
        payoff_ratio_r="1.5",
        p_min="0.45",
        p_max="0.65",
        uplift_factor="0.2",
        fraction="0.99",
    )
    strategy_cfg = SimpleNamespace(
        execution=SimpleNamespace(
            entry_order_type="LIMIT",
            entry_tif="GTC",
        ),
        decision=SimpleNamespace(kelly=kelly_cfg),
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


def _expected_kelly_fraction() -> str:
    probability = decimal.Decimal("0.5")
    return str(
        probability - ((decimal.Decimal("1") - probability) /
                       decimal.Decimal("1.5"))
    )


def _expected_kelly_provenance() -> dict:
    expected_fraction = _expected_kelly_fraction()
    return {
        "source_path": "config.strategies.aurora.decision.kelly",
        "p": {
            "source": "config.strategies.aurora.decision.kelly.base_probability",
            "raw": "0.5",
            "p_min": "0.45",
            "p_max": "0.65",
            "value": "0.5",
        },
        "payoff_ratio_r": {
            "source": "config.strategies.aurora.decision.kelly.payoff_ratio_r",
            "value": "1.5",
        },
        "kelly_fraction": {
            "formula": "p - (1 - p) / payoff_ratio_r",
            "full_kelly": expected_fraction,
            "kelly_cap": "0.25",
            "value": expected_fraction,
        },
        "unapplied_config_fields": {
            "kelly_alpha": {
                "value": "0.8",
                "reason": "boundary_semantics_not_proven",
            },
            "uplift_factor": {
                "value": "0.2",
                "reason": "no_score01_probability_producer_on_hot_path",
            },
        },
    }


def test_build_and_emit_preserves_trade_intent_payload_contract() -> None:
    builder = _make_builder()

    with (
        patch("apps.reference.domains.decision_making.intent.builder.wal.append", return_value="wal-ok") as mock_wal,
        patch("apps.reference.domains.decision_making.intent.builder.order_logger.write"),
        patch("apps.reference.domains.decision_making.intent.builder.print"),
        patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit"),
        patch(
            "apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None),
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
        "p": "0.5",
        "payoff_ratio_r": "1.5",
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
            "kelly_fraction": _expected_kelly_fraction(),
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
        "trace": {
            "objective": {"score": 0.9},
            "model": "aurora",
            "kelly_provenance": _expected_kelly_provenance(),
        },
    }


def test_build_and_emit_preserves_decision_trace_payload_contract() -> None:
    builder = _make_builder()

    with (
        patch("apps.reference.domains.decision_making.intent.builder.wal.append",
              return_value="wal-ok"),
        patch("apps.reference.domains.decision_making.intent.builder.order_logger.write"),
        patch("apps.reference.domains.decision_making.intent.builder.print"),
        patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit"),
        patch(
            "apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None),
    ):
        builder.build_and_emit(**_build_kwargs())

    decision_trace_calls = [
        call.kwargs["payload"]
        for call in builder._fsm.emit.call_args_list
        if call.args[0] == "EVT:DECISION_TRACE_EMITTED"
    ]

    normalized_trace = dict(decision_trace_calls[0])
    normalized_trace["lifecycle_id"] = "<uuid>"

    assert [normalized_trace] == [
        {
            "rid": "rid-payload-001",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "strategy_id": "aurora",
            "ts": 1700000001234,
            "intent_side": "LONG",
            "lifecycle_id": "<uuid>",
            "signal_score": 0.91,
            "regime": "TREND_UP",
            "regime_confidence": 0.82,
            "resolved_regime_confidence_strategy_id": "aurora",
            "resolved_regime_confidence_symbol": "BTCUSDT",
            "resolved_regime_confidence_regime_key": None,
            "min_regime_confidence": 0.45,
            "resolved_min_regime_confidence": 0.45,
            "resolved_min_regime_confidence_source": "scalar_legacy",
            "resolved_min_regime_confidence_strategy_id": None,
            "resolved_min_regime_confidence_regime_key": None,
            "resolved_max_regime_confidence": None,
            "resolved_max_regime_confidence_source": None,
            "resolved_max_regime_confidence_strategy_id": None,
            "resolved_max_regime_confidence_regime_key": None,
            "resolved_regime_confidence_band_active": True,
            "regime_confidence_breach_kind": "none",
            "regime_confidence_gate_verdict": "ALLOW",
            "trend_dir": "UP",
            "trend_confidence": 0.75,
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
            "price_motion_context": {
                "pm_norm_10s": 0.1,
                "pm_norm_60s": 0.2,
                "pm_norm_300s": 0.3,
                "vol_pct_10s": 1.1,
                "vol_pct_60s": 1.2,
                "vol_pct_300s": 1.3,
                "missing": {
                    "pm_norm_10s": False,
                    "pm_norm_60s": False,
                    "pm_norm_300s": False,
                    "vol_pct_10s": False,
                    "vol_pct_60s": False,
                    "vol_pct_300s": False,
                },
                "missing_reason": {
                    "pm_norm_10s": None,
                    "pm_norm_60s": None,
                    "pm_norm_300s": None,
                    "vol_pct_10s": None,
                    "vol_pct_60s": None,
                    "vol_pct_300s": None,
                },
            },
            "missing_inputs": {
                "regime_confidence": None,
                "trend_dir": None,
                "trend_confidence": None,
                "trend_run_length": None,
                "pm_norm_10s": None,
                "pm_norm_60s": None,
                "pm_norm_300s": None,
                "vol_pct_10s": None,
                "vol_pct_60s": None,
                "vol_pct_300s": None,
                "low_vol_cost_floor": None,
            },
            "safety_gate_snapshot": {
                "apply_safety_gates": True,
                "directional_sanity_enabled": True,
                "nrr026_enabled": False,
                "nrr026_effective_enforced": False,
                "nrr027_enabled": False,
                "nrr027_effective_enforced": False,
                "price_motion_sanity_enabled": False,
                "price_motion_backtest_bypass": False,
                "nrr028_enabled": False,
                "nrr028_effective_enforced": False,
                "nrr029_enabled": False,
                "nrr029_effective_enforced": False,
                "nrr030_enabled": False,
                "nrr030_effective_enforced": False,
                "nrr063_enabled": True,
                "nrr063_effective_enforced": True,
                "regime_confidence_gate_verdict": "ALLOW",
                "threshold_verdict": "PASS",
                "threshold_reason": "regime_confidence=0.82 within band min=0.45 min_source=scalar_legacy max=None max_source=None",
            },
            "regime_provenance": REGIME_PROVENANCE,
            "tpsl_owner_ctx": OWNER_CTX,
            "low_vol_cost_floor": {
                "evaluation_stage": "observe_only",
                "gate_mode": "observe_only",
                "would_block": False,
                "price_motion_context": {
                    "pm_norm_10s": 0.1,
                    "pm_norm_60s": 0.2,
                    "pm_norm_300s": 0.3,
                    "vol_pct_10s": 1.1,
                    "vol_pct_60s": 1.2,
                    "vol_pct_300s": 1.3,
                },
                "persistence_context": {
                    "decision_trace_event": "EVT:DECISION_TRACE_EMITTED",
                    "order_logger_event": "ORDER_INTENT",
                    "persisted_in": ["EVT:DECISION_TRACE_EMITTED", "ORDER_INTENT"],
                },
            },
        }
    ]


def test_build_and_emit_persists_explicit_missing_reasons_for_absent_inputs() -> None:
    builder = _make_builder()
    sg = _FakeSG()
    sg.regime_confidence = None
    sg.trend_confidence = None
    sg.pm_norm_60s = None
    sg.pm_norm_300s = None
    sg.vol_pct_60s = None
    sg.vol_pct_300s = None
    sg.low_vol_cost_floor_details = None
    kwargs = _build_kwargs()
    kwargs["sg"] = sg

    with (
        patch("apps.reference.domains.decision_making.intent.builder.wal.append",
              return_value="wal-ok"),
        patch("apps.reference.domains.decision_making.intent.builder.order_logger.write"),
        patch("apps.reference.domains.decision_making.intent.builder.print"),
        patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit"),
        patch(
            "apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None),
    ):
        builder.build_and_emit(**kwargs)

    decision_trace_payload = next(
        call.kwargs["payload"]
        for call in builder._fsm.emit.call_args_list
        if call.args[0] == "EVT:DECISION_TRACE_EMITTED"
    )

    assert decision_trace_payload["price_motion_context"]["pm_norm_60s"] is None
    assert decision_trace_payload["price_motion_context"]["pm_norm_300s"] is None
    assert decision_trace_payload["price_motion_context"]["missing"]["pm_norm_60s"] is True
    assert decision_trace_payload["price_motion_context"]["missing_reason"]["pm_norm_60s"] == "absent_from_safety_gate_result"
    assert decision_trace_payload["missing_inputs"]["regime_confidence"] == "absent_from_safety_gate_result"
    assert decision_trace_payload["missing_inputs"]["trend_confidence"] == "absent_from_safety_gate_result"
    assert decision_trace_payload["missing_inputs"]["low_vol_cost_floor"] == "not_evaluated_or_not_attached"


def test_decision_trace_emit_failure_logs_loudly_without_blocking_trade_intent() -> None:
    builder = _make_builder()

    def _emit_side_effect(event_name, *args, **kwargs):
        if event_name == "EVT:DECISION_TRACE_EMITTED":
            raise RuntimeError(
                "Payload validation failed for EVT:DECISION_TRACE_EMITTED: Additional properties are not allowed"
            )
        return None

    builder._fsm.emit.side_effect = _emit_side_effect

    with (
        patch("apps.reference.domains.decision_making.intent.builder.wal.append", return_value="wal-ok") as mock_wal,
        patch("apps.reference.domains.decision_making.intent.builder.order_logger.write"),
        patch("apps.reference.domains.decision_making.intent.builder.print"),
        patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit"),
        patch(
            "apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None),
    ):
        builder.build_and_emit(**_build_kwargs())

    emitted_events = [call.args[0]
                      for call in builder._fsm.emit.call_args_list]
    assert "EVT:DECISION_TRACE_EMITTED" in emitted_events
    assert "EVT:TRADE_INTENT_PROPOSED" in emitted_events
    assert mock_wal.call_count == 1
    assert builder.logger.error.call_count == 1
    log_line = builder.logger.error.call_args[0][0]
    assert "EVT:DECISION_TRACE_EMITTED" in log_line
    assert "RID=rid-payload-001" in log_line
    assert "Payload validation failed" in log_line
