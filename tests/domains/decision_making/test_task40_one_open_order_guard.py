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
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.fsm = fsm
    dm.logger = logging.getLogger("tests.task40.dm")

    dm._check_strategy_arbitration = lambda _symbol, _strategy_id, **_k: {"allowed": True, "reason": None}
    dm._warmup_gate_before_trade_intent = lambda **_k: False
    dm._record_blocked_intent = lambda *_a, **_k: None
    dm._record_accepted_intent = lambda *_a, **_k: None
    dm._emit_intent_deferred_v1 = lambda **kwargs: fsm.emit("EVT:INTENT_DEFERRED", kwargs)

    # Needed by _emit_intent_deferred_v1
    dm._qos_state = {}
    dm.symbol_states = {}

    # Minimal required strict config for _propose_trade_intent (when it reaches emission).
    dm._tca_prefs = {"max_slippage_bps": 10, "max_latency_ms": 500, "maker_preference": "neutral"}
    dm._risk_budgets = {"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200}

    return dm


def test_order_in_flight_deferred_reason():
    from apps.reference.domains.execution_position.order_index import OrderIndex

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
    from apps.reference.domains.execution_position.order_index import OrderIndex

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
    )

    assert any(name == "EVT:TRADE_INTENT_PROPOSED" for name, _ in fsm.emitted)


def test_double_signal_only_one_order_placed():
    from decimal import Decimal
    from apps.reference.domains.execution_position.order_index import OrderIndex

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
    )

    assert sum(1 for name, _ in fsm.emitted if name == "EVT:TRADE_INTENT_PROPOSED") == 1
    assert any(name == "EVT:INTENT_DEFERRED" for name, _ in fsm.emitted)
