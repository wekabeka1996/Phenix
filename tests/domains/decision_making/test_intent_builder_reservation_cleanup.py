from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.decision_making.intent.builder import IntentBuilder
from apps.reference.domains.execution_position.state.order_index import OrderIndex


class _FakeSG:
    intent_side = "LONG"
    trace_ts_ms = 1_700_000_000_000
    why_short = ""
    signal_score = 0.5
    regime = "TREND_UP"
    regime_confidence = 0.9
    trend_dir = 1
    trend_run_length = 1
    delta_price = 0
    pm_norm_10s = 0
    pm_norm_60s = 0
    pm_norm_300s = 0
    vol_pct_10s = 0
    vol_pct_60s = 0
    vol_pct_300s = 0


def _safe_decimal(value, default=None):
    if value in (None, "", "None"):
        return default
    return Decimal(str(value))


def _make_config():
    kelly_cfg = SimpleNamespace(
        base_probability="0.5",
        kelly_cap="0.25",
        kelly_alpha="0.8",
        payoff_ratio_r="1.5",
        p_min="0.45",
        p_max="0.65",
        uplift_factor="0.2",
    )
    strategy_cfg = SimpleNamespace(
        execution=SimpleNamespace(entry_order_type="LIMIT", entry_tif="GTC"),
        decision=SimpleNamespace(kelly=kelly_cfg),
    )
    return SimpleNamespace(strategies=SimpleNamespace(aurora=strategy_cfg))


def _make_builder(*, order_index: OrderIndex, arb_fn) -> IntentBuilder:
    clock = MagicMock()
    clock.now_ms.return_value = 1_700_000_000_000
    clock.now_sec.return_value = 1_700_000_000
    fsm = SimpleNamespace(order_index=order_index, emit=MagicMock())
    return IntentBuilder(
        logger=MagicMock(),
        fsm=fsm,
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
        check_strategy_arbitration_fn=arb_fn,
        warmup_gate_fn=lambda **_kwargs: False,
        emit_rejected_fn=MagicMock(),
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0, 600, 0.6, 0.9)),
        side_intent_window={},
        get_regime_epoch_ref_fn=lambda symbol: f"epoch:{symbol}:123",
    )


def _build_kwargs(*, rid: str) -> dict:
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": Decimal("1.5"),
        "price": Decimal("50000.25"),
        "why_chain": ["alpha"],
        "rid": rid,
        "reduce_only": False,
        "strategy_id": "aurora",
        "decision_ts_ms": 1_700_000_000_999,
        "stop_price": "49000.50",
        "target_price": Decimal("51000.75"),
        "entry_plan_trace": {"plan": "maker_pullback"},
        "tf_sec": 300,
        "max_slippage_bps": None,
        "max_latency_ms": None,
        "risk_score": 0.33,
        "tpsl_owner_ctx": None,
        "strategy_trace": {"objective": {"score": 0.9}},
        "normalize_mode": "signed_v2",
        "sg": _FakeSG(),
    }


def _emit_trade_intent_calls(builder: IntentBuilder) -> list:
    return [
        call for call in builder._fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:TRADE_INTENT_PROPOSED"
    ]


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_reservation_released_on_arbitration_reject_and_second_attempt_can_emit(
    mock_wal,
    mock_policy,
    *_patches,
):
    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    order_index = OrderIndex(ttl_sec=3600)

    reject_builder = _make_builder(
        order_index=order_index,
        arb_fn=MagicMock(
            return_value={"allowed": False, "reason": "blocked_for_test"}),
    )
    reject_builder.build_and_emit(**_build_kwargs(rid="RID-ARB-REJECT"))

    assert order_index.get(rid="RID-ARB-REJECT") is None
    assert order_index.has_in_flight_entry("BTCUSDT") is False

    allow_builder = _make_builder(
        order_index=order_index,
        arb_fn=MagicMock(side_effect=lambda *_, commit=False,
                         **__: {"allowed": True, "reason": None}),
    )
    allow_builder.build_and_emit(**_build_kwargs(rid="RID-ARB-ALLOW"))

    assert order_index.get(rid="RID-ARB-ALLOW") is not None
    assert len(_emit_trade_intent_calls(allow_builder)) == 1


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_reservation_released_on_wal_failure(
    mock_wal,
    mock_policy,
    *_patches,
):
    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.side_effect = RuntimeError("wal append failed")
    order_index = OrderIndex(ttl_sec=3600)

    builder = _make_builder(
        order_index=order_index,
        arb_fn=MagicMock(side_effect=lambda *_, commit=False,
                         **__: {"allowed": True, "reason": None}),
    )
    builder.build_and_emit(**_build_kwargs(rid="RID-WAL-FAIL"))

    assert order_index.get(rid="RID-WAL-FAIL") is None
    assert order_index.has_in_flight_entry("BTCUSDT") is False
    assert _emit_trade_intent_calls(builder) == []


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_reservation_released_on_emit_failure(
    mock_wal,
    mock_policy,
    *_patches,
):
    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    order_index = OrderIndex(ttl_sec=3600)

    builder = _make_builder(
        order_index=order_index,
        arb_fn=MagicMock(side_effect=lambda *_, commit=False,
                         **__: {"allowed": True, "reason": None}),
    )

    def _emit_side_effect(event_name, *args, **kwargs):
        if event_name == "EVT:DECISION_TRACE_EMITTED":
            return None
        if event_name == "EVT:TRADE_INTENT_PROPOSED":
            raise RuntimeError("emit failed")
        raise AssertionError(f"Unexpected emit call: {event_name}")

    builder._fsm.emit.side_effect = _emit_side_effect
    builder.build_and_emit(**_build_kwargs(rid="RID-EMIT-FAIL"))

    assert order_index.get(rid="RID-EMIT-FAIL") is None
    assert order_index.has_in_flight_entry("BTCUSDT") is False
