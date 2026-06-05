import logging
from types import SimpleNamespace

from vfoundation.core.protocol import Message


class _DummyFsm:
    def __init__(self, order_index=None):
        self.emitted: list[tuple[str, dict]] = []
        self.order_index = order_index

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


def _mk_dm(*, fsm):
    from apps.reference.domains.decision_making.core.facade import DecisionMaking
    from apps.reference.core.time.clock import LiveClock

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.fsm = fsm
    dm._clock = LiveClock()
    dm.logger = logging.getLogger("tests.task40.dm")

    # DM-DIR-SSOT-STRICT-01: directional_sanity is SSOT-required
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                directional_sanity=SimpleNamespace(
                    enabled=False,
                    min_abs_delta_price=0.0,
                    min_confidence=0.0,
                    consecutive_bars=2,
                )
                ,
                price_motion_sanity=SimpleNamespace(
                    enabled=False,
                    k_vol=2.0,
                    flash_window_sec=10,
                    bleed_window_sec=300,
                    flash_threshold_norm=1.0,
                    bleed_threshold_norm=0.7,
                    require_bleed_ready=True,
                ),
            )
        ),
        strategies=SimpleNamespace(
            mean_reversion=SimpleNamespace(
                execution=SimpleNamespace(entry_order_type="MARKET"),
                # DM-SAFETY-BYPASSES-P1: Required for fail-closed safety_gates check
                safety_gates=SimpleNamespace(enabled=False),
            ),
        ),
    )

    dm._check_strategy_arbitration = lambda _symbol, _strategy_id, **_k: {"allowed": True, "reason": None}
    dm._warmup_gate_before_trade_intent = lambda **_k: False
    dm._record_blocked_intent = lambda *_a, **_k: None
    dm._record_accepted_intent = lambda *_a, **_k: None
    dm._emit_intent_deferred_v1 = lambda **kwargs: fsm.emit("EVT:INTENT_DEFERRED", kwargs)

    # Needed by _emit_intent_deferred_v1
    dm._qos_state = {}
    dm.symbol_states = {}
    dm._per_symbol_regimes = {}
    dm._system_stress_states = {}
    dm._emit_trade_intent_rejected = lambda **kw: None
    dm._get_side_bias_params = lambda symbol: (0.5, 60, 0.6, 10)
    dm._side_intent_window = {}

    # Minimal required strict config for _propose_trade_intent (when it reaches emission).
    dm._tca_prefs = {"max_slippage_bps": 10, "max_latency_ms": 500, "maker_preference": "neutral"}
    dm._risk_budgets = {"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200}

    from decimal import Decimal as _D
    from apps.reference.domains.decision_making.intent.builder import IntentBuilder
    dm._builder = IntentBuilder(
        fsm=dm.fsm, clock=dm._clock, config=dm.config,
        tca_prefs=dm._tca_prefs, risk_budgets=dm._risk_budgets,
        safe_decimal_fn=lambda v, d=None: _D(str(v)) if v is not None else d,
        check_strategy_arbitration_fn=dm._check_strategy_arbitration,
        warmup_gate_fn=dm._warmup_gate_before_trade_intent,
        emit_rejected_fn=dm._emit_trade_intent_rejected,
        record_blocked_fn=dm._record_blocked_intent,
        record_accepted_fn=dm._record_accepted_intent,
        emit_deferred_fn=dm._emit_intent_deferred_v1,
        get_side_bias_params_fn=dm._get_side_bias_params,
        side_intent_window=dm._side_intent_window,
        logger=dm.logger,
    )

    dm.normalize_signals_mode = "signed_v2"

    return dm


def test_order_in_flight_deferred_reason():
    from apps.reference.domains.execution_position.state.order_index import OrderIndex

    oi = OrderIndex(ttl_sec=3600)
    oi.upsert_from_open(
        rid="rid-open-1",
        idempotent_key="idem-1",
        clientOrderId=None,
        symbol="SOLUSDT",
        side="BUY",
        order_type="ENTRY_INTENT",
    )

    fsm = _DummyFsm(order_index=oi)
    dm = _mk_dm(fsm=fsm)

    dm._propose_trade_intent(
        symbol="SOLUSDT",
        side="BUY",
        qty=SimpleNamespace(),  # won't be used (guard triggers before tca)
        price=SimpleNamespace(),
        why_chain=["w"],
        rid="rid-2",
        reduce_only=False,
        strategy_id="mean_reversion",
    )

    assert any(name == "EVT:INTENT_DEFERRED" for name, _ in fsm.emitted)
    assert not any(name == "EVT:TRADE_INTENT_PROPOSED" for name, _ in fsm.emitted)


def test_unlock_on_terminal_allows_next_open():
    from decimal import Decimal
    from apps.reference.domains.execution_position.state.order_index import OrderIndex

    oi = OrderIndex(ttl_sec=3600)
    ref = oi.upsert_from_open(
        rid="rid-open-1",
        idempotent_key="idem-1",
        clientOrderId=None,
        symbol="SOLUSDT",
        side="BUY",
        order_type="ENTRY_INTENT",
    )
    oi.mark_terminal(ref)

    fsm = _DummyFsm(order_index=oi)
    dm = _mk_dm(fsm=fsm)

    dm._propose_trade_intent(
        symbol="SOLUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("20"),
        why_chain=["w"],
        rid="rid-2",
        reduce_only=False,
        strategy_id="mean_reversion",
        tf_sec=300,
    )

    assert any(name == "EVT:TRADE_INTENT_PROPOSED" for name, _ in fsm.emitted)


def test_double_signal_only_one_order_placed():
    from decimal import Decimal
    from apps.reference.domains.execution_position.state.order_index import OrderIndex

    oi = OrderIndex(ttl_sec=3600)
    fsm = _DummyFsm(order_index=oi)
    dm = _mk_dm(fsm=fsm)

    # First intent (no in-flight entry yet) should pass.
    dm._propose_trade_intent(
        symbol="SOLUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("20"),
        why_chain=["w1"],
        rid="rid-1",
        reduce_only=False,
        strategy_id="mean_reversion",
        tf_sec=300,
    )

    # Simulate bridge/execution creating an in-flight entry reference.
    oi.upsert_from_open(
        rid="rid-open-1",
        idempotent_key="idem-1",
        clientOrderId=None,
        symbol="SOLUSDT",
        side="BUY",
        order_type="ENTRY_INTENT",
    )

    dm._propose_trade_intent(
        symbol="SOLUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("20"),
        why_chain=["w2"],
        rid="rid-2",
        reduce_only=False,
        strategy_id="mean_reversion",
        tf_sec=300,
    )

    assert sum(1 for name, _ in fsm.emitted if name == "EVT:TRADE_INTENT_PROPOSED") == 1
    assert any(name == "EVT:INTENT_DEFERRED" for name, _ in fsm.emitted)
