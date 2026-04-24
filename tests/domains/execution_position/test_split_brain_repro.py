import logging
from decimal import Decimal

import pytest

from vfoundation.core.protocol import Message

from apps.reference.core.time import get_clock
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.order_index import OrderIndex
from apps.reference.domains.execution_position.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)
from apps.reference.domains.execution_position.utils import generate_client_order_id


def _portfolio_state(symbol: str, position_amt: str = "0") -> Message:
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="adapter",
        dst="execution_position",
        rid=f"portfolio-{symbol}",
        why="test_portfolio",
        pld={
            "equity_free_usdt": "100000",
            "open_positions_margin_usd": "0",
            "positions_last_ts_ms": 1_000_000,
            "positions": [
                {
                    "symbol": symbol,
                    "positionAmt": position_amt,
                    "realizedPnl": "0",
                }
            ],
            "positions_by_side": {"long_margin": "0", "short_margin": "0"},
        },
    )


def _cmd_open(
    *,
    symbol: str = "BTCUSDT",
    rid: str = "rid-open-1",
    side: str = "BUY",
    qty: str = "0.01",
    price: str = "1000",
) -> Message:
    return Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        why="test_open",
        pld={
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "order_type": "LIMIT",
            "tif": "GTC",
            "valid_for_ms": 60_000,
        },
    )


def _trade_executed(
    *,
    symbol: str = "BTCUSDT",
    rid: str = "rid-fill-1",
    order_id: str = "order-1",
    client_order_id: str = "ENTRY-1",
    side: str = "BUY",
    qty: str = "0.01",
    price: str = "1000",
) -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid=rid,
        why="test_trade_executed",
        pld={
            "symbol": symbol,
            "orderId": order_id,
            "clientOrderId": client_order_id,
            "client_order_id": client_order_id,
            "side": side,
            "qty": qty,
            "quantity": qty,
            "price": price,
        },
    )


def _prime_tracking_state(manage_flow, *, symbol: str = "BTCUSDT") -> None:
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = symbol
    manage_flow.position_qty = Decimal("0.10")
    manage_flow.position_entry_price = Decimal("50000")
    manage_flow.position_side = "BUY"
    manage_flow.position_open_ts = get_clock().now_sec()


def _find_guard_event(bus, topic: str):
    for event_topic, args, kwargs in bus.events:
        if event_topic == topic:
            return event_topic, args, kwargs
    return None


class _GuardianAdapter:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.cancelled: list[tuple[str, str]] = []

    async def get_open_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        return [
            {
                "symbol": symbol or self.symbol,
                "orderId": "orphan-bracket-1",
                "clientOrderId": "TP1-orphan",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": False,
            }
        ]

    async def cancel_order(self, symbol, order_id):
        self.cancelled.append((symbol, order_id))
        return {"status": "CANCELED", "orderId": order_id}


def test_invariant_local_open_blocked_while_manage_tracks(fsm_harness):
    """Hypothesis: `ExecPosFSM` must fail closed before `OpenFlowFSM` if local execution lifecycle is still non-FLAT.
    Why this matters: a fresh `CMD:OPEN` cannot be allowed to ride on top of stale local tracking state.
    Current expected buggy behavior: current code emits `DEC:OPEN` even when local manage state remains `TRACKING` and watchdog has no pending entry.
    What future repair should change: return an explicit guard rejection and emit a structured guard event for local state conflict.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)

    fsm.watchdog.pending_orders.clear()
    fsm.watchdog.acked_orders.clear()
    assert not fsm.watchdog.pending_orders
    assert not fsm.watchdog.acked_orders

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-open-over-tracking"))

    assert out is not None
    assert out.op == "ERR"
    assert out.verb == "OPEN"
    assert out.why == "OPEN_GUARD_FAIL"
    assert out.pld["reason"] == "local_manage_state_conflict"
    assert out.pld["local_manage_state"] == ManageState.TRACKING.value
    guard_evt = _find_guard_event(bus, "EVT:EXECUTION_GUARD_BLOCKED")
    assert guard_evt is not None


def test_invariant_stale_tracking_blocks_new_entry_fill_until_reconcile(fsm_harness):
    """Hypothesis: a new entry fill arriving while local execution state is already tracking another lifecycle must not be silently absorbed.
    Why this matters: without an explicit block/reconcile path, stale tracking suppresses safe bracket handling and keeps the symbol in split-brain.
    Current expected buggy behavior: current code returns `None`, leaves stale bracket ids in place, and silently keeps the old lifecycle alive.
    What future repair should change: emit an explicit guard failure for stale local lifecycle conflict instead of swallowing the new entry fill.
    """
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    manage_flow.sl_order_id = "old-sl-order"
    manage_flow.tp_order_id = "old-tp-order"
    manage_flow.tp1_order_id = "old-tp1-order"
    old_qty = manage_flow.position_qty

    out = fsm.handle(
        _trade_executed(
            symbol=symbol,
            rid="rid-second-entry",
            order_id="entry-order-2",
            client_order_id="ENTRY-SECOND",
            side="BUY",
            qty="0.20",
            price="51000",
        )
    )

    assert out is not None
    assert out.op == "ERR"
    assert out.verb == "TRADE_EXECUTED"
    assert out.why == "MANAGE_GUARD_FAIL"
    assert out.pld["reason"] == "stale_local_lifecycle_conflict"
    assert out.pld["local_manage_state"] == ManageState.TRACKING.value
    assert manage_flow.state == ManageState.TRACKING
    assert manage_flow.position_qty == old_qty
    assert manage_flow.sl_order_id == "old-sl-order"
    assert manage_flow.tp_order_id == "old-tp-order"
    assert manage_flow.tp1_order_id == "old-tp1-order"


def test_invariant_rest_flat_local_tracking_divergence_blocks_reopen(fsm_harness):
    """Hypothesis: portfolio/REST flatness must not overrule local execution tracking when the two truth sources diverge.
    Why this matters: split-brain windows must block new risk until local reconcile succeeds.
    Current expected buggy behavior: `PositionQueries` reports `FLAT` and the same symbol still receives `DEC:OPEN`.
    What future repair should change: divergence must return a guard rejection that explicitly marks the mismatch instead of admitting reopen.
    """
    fsm, bus, cfg = fsm_harness
    symbol = "BTCUSDT"
    portfolio = _portfolio_state(symbol, position_amt="0").pld

    queries = PositionQueries(
        config=cfg,
        get_portfolio=lambda: portfolio,
        min_pos_size_usd=Decimal("5"),
        liq_cap_usd=Decimal("100000"),
        logger=logging.getLogger(__name__),
    )

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    fsm.watchdog.pending_orders.clear()
    fsm.watchdog.acked_orders.clear()

    assert queries.check_symbol_is_flat(symbol) is True
    assert manage_flow.state == ManageState.TRACKING

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-rest-flat-reopen"))

    assert out is not None
    assert out.op == "ERR"
    assert out.verb == "OPEN"
    assert out.pld["reason"] == "local_manage_state_conflict"
    assert out.pld["local_manage_state"] == ManageState.TRACKING.value
    assert out.pld["portfolio_state"] == "FLAT"
    assert out.pld["divergence_detected"] is True
    guard_evt = _find_guard_event(bus, "EVT:EXECUTION_GUARD_BLOCKED")
    assert guard_evt is not None


def test_invariant_foreign_in_flight_entry_blocks_execpos_open(fsm_harness):
    """Hypothesis: execution_position must fail closed on a foreign pending entry even when local manage state is FLAT.
    Why this matters: split-brain recovery cannot rely on portfolio truth alone when OrderIndex still owns a live entry lifecycle.
    Current expected buggy behavior: `CMD:OPEN` slips through because no local lifecycle is active and portfolio state is flat.
    What future repair should change: return `OPEN_GUARD_FAIL` with `entry_order_in_flight` and emit a structured guard event.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    fsm.order_index = OrderIndex(ttl_sec=3600)

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    assert fsm.order_index.try_reserve_entry(symbol, "rid-foreign") is True

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-current"))

    assert out is not None
    assert out.op == "ERR"
    assert out.verb == "OPEN"
    assert out.why == "OPEN_GUARD_FAIL"
    assert out.pld["reason"] == "entry_order_in_flight"
    assert out.pld["tracked_rid"] == "rid-foreign"
    guard_evt = _find_guard_event(bus, "EVT:EXECUTION_GUARD_BLOCKED")
    assert guard_evt is not None
    _, args, kwargs = guard_evt
    payload = args[0]
    assert payload["block_reason"] == "entry_order_in_flight"
    assert payload["why"] == "execution:entry_order_in_flight"
    assert kwargs["why"] == "execution:entry_order_in_flight"


def test_invariant_same_rid_reservation_does_not_block_execpos_open(fsm_harness):
    """Hypothesis: the current lifecycle must not block its own `CMD:OPEN` when the reservation belongs to the same rid.
    Why this matters: the pending-entry guard must distinguish duplicate foreign opens from the active command it is protecting.
    Current expected buggy behavior: same-rid reservations are treated as duplicates and rejected fail-closed.
    What future repair should change: exclude the current rid and allow the command to continue to `DEC:OPEN`.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    fsm.order_index = OrderIndex(ttl_sec=3600)

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    assert fsm.order_index.try_reserve_entry(symbol, "rid-current") is True

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-current"))

    assert out is not None
    assert out.op == "DEC"
    assert out.verb == "OPEN"
    assert all(
        not (
            topic == "EVT:EXECUTION_GUARD_BLOCKED"
            and args
            and args[0].get("block_reason") == "entry_order_in_flight"
        )
        for topic, args, kwargs in bus.events
    )


def test_direct_open_flow_blocks_foreign_in_flight_entry(fsm_harness):
    """Hypothesis: direct `OpenFlowFSM` use must inherit the same pending-entry guard as the wrapper FSM.
    Why this matters: defense in depth fails if callers can bypass `ExecPosFSM.handle(...)` and reopen directly.
    Current expected buggy behavior: direct flow calls skip the wrapper guard and still return `DEC:OPEN`.
    What future repair should change: the injected pre-open guard should reject with `OPEN_GUARD_FAIL`.
    """
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    fsm.order_index = OrderIndex(ttl_sec=3600)

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    assert fsm.order_index.try_reserve_entry(symbol, "rid-foreign") is True

    out = fsm.open_flow(symbol).handle(_cmd_open(symbol=symbol, rid="rid-current"))

    assert out is not None
    assert out.op == "ERR"
    assert out.verb == "OPEN"
    assert out.why == "OPEN_GUARD_FAIL"
    assert out.pld["reason"] == "entry_order_in_flight"


def test_direct_open_flow_allows_same_rid_reservation(fsm_harness):
    """Hypothesis: the injected guard must still allow the current rid through when it owns the reservation.
    Why this matters: defense in depth should not create a self-deadlocking direct-flow seam.
    Current expected buggy behavior: direct `OpenFlowFSM` rejects even when the in-flight ref belongs to the same rid.
    What future repair should change: the same-rid reservation should continue to `DEC:OPEN`.
    """
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    fsm.order_index = OrderIndex(ttl_sec=3600)

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    assert fsm.order_index.try_reserve_entry(symbol, "rid-current") is True

    out = fsm.open_flow(symbol).handle(_cmd_open(symbol=symbol, rid="rid-current"))

    assert out is not None
    assert out.op == "DEC"
    assert out.verb == "OPEN"


@pytest.mark.asyncio
async def test_invariant_orphan_cleanup_remains_tidy_only_and_not_business_close(fsm_harness):
    """Hypothesis: periodic orphan cleanup is a maintenance path and must remain distinct from authoritative close reconciliation.
    Why this matters: cleanup is allowed to tidy remote orphan brackets, but it must not fake a business-valid close or reset stale local state.
    Current expected buggy behavior: there is no bug here to fix; cleanup already behaves as symptom cleanup and must stay that way.
    What future repair should change: keep cleanup as tidy-only behavior while other guards prevent unsafe reopen on dirty local state.
    """
    fsm, bus, cfg = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)

    adapter = _GuardianAdapter(symbol)
    guardian = OrderGuardian(
        adapter=adapter,
        store=InMemoryStore(),
        bus=bus,
        config=cfg,
    )
    fsm.order_guardian = guardian

    cancelled = await guardian.cleanup_orphans(symbol=symbol, hard=True)

    assert cancelled == 1
    assert adapter.cancelled == [(symbol, "orphan-bracket-1")]
    assert manage_flow.state == ManageState.TRACKING
    assert any(
        topic == "EVT:SYMBOL_TIDY" and kwargs.get("why") == "guardian:orphan_cleanup:tidy"
        for topic, args, kwargs in bus.events
    )
    assert all(topic != "EVT:POSITION_CLOSED" for topic, args, kwargs in bus.events)


def test_invariant_valid_tp_fill_matches_preack_client_id(fsm_config):
    """Hypothesis: valid TP fills must match the pre-ACK client id shape used by runtime bracket placement.
    Why this matters: if exit matching ignores `TP1-<hash>` or `client_order_id`, local close reconciliation can silently miss a real exit.
    Current expected buggy behavior: current matcher ignores the fill, leaves TP tracking untouched, and keeps the position quantity unchanged.
    What future repair should change: accept the runtime TP1 client-id format and advance the local lifecycle on the valid exit fill.
    """
    from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM

    manage_flow = ManageFlowFSM(config=fsm_config)
    _prime_tracking_state(manage_flow)
    manage_flow.state = ManageState.BRACKETS_PLACED
    manage_flow.partial_exit_pct = 0.5
    manage_flow.sl_order_id = "sl-exchange-order"

    tp1_client_id = generate_client_order_id(
        "TP1",
        "BTCUSDT",
        idempotent_key="rid-preack-tp",
    )
    manage_flow.tp1_order_id = tp1_client_id
    manage_flow.tp_order_id = tp1_client_id

    out = manage_flow.handle(
        Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="execution_position",
            rid="rid-preack-tp",
            why="tp_fill_before_order_updated",
            pld={
                "symbol": "BTCUSDT",
                "orderId": "exchange-order-556677",
                "clientOrderId": tp1_client_id,
                "client_order_id": tp1_client_id,
                "side": "SELL",
                "qty": "0.05",
                "price": "50500",
            },
        )
    )

    assert out is not None
    assert out.op == "DEC"
    assert out.verb == "CANCEL_ORDER"
    assert out.pld["orderId"] == "sl-exchange-order"
    assert manage_flow.tp1_order_id is None
    assert manage_flow.tp_order_id is None
    assert manage_flow.sl_order_id is None
    assert manage_flow.position_qty == Decimal("0.05")
