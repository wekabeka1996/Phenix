from decimal import Decimal

import pytest

from vfoundation.core.protocol import Message

from apps.reference.core.time import get_clock
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
    order_type: str | None = None,
    reduce_only: bool | None = None,
) -> Message:
    payload = {
        "symbol": symbol,
        "orderId": order_id,
        "clientOrderId": client_order_id,
        "client_order_id": client_order_id,
        "side": side,
        "qty": qty,
        "quantity": qty,
        "price": price,
    }
    if order_type is not None:
        payload["order_type"] = order_type
    if reduce_only is not None:
        payload["reduceOnly"] = reduce_only
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid=rid,
        why="test_trade_executed",
        pld=payload,
    )


def _prime_tracking_state(manage_flow, *, symbol: str = "BTCUSDT") -> None:
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = symbol
    manage_flow.position_qty = Decimal("0.10")
    manage_flow.position_entry_price = Decimal("50000")
    manage_flow.position_side = "BUY"
    manage_flow.position_open_ts = get_clock().now_sec()


def _find_first_event(bus, topic: str):
    for event_topic, args, kwargs in bus.events:
        if event_topic == topic:
            payload = args[0] if args else {}
            return payload, kwargs
    return None, None


def _find_all_events(bus, topic: str):
    found = []
    for event_topic, args, kwargs in bus.events:
        if event_topic == topic:
            found.append((args[0] if args else {}, kwargs))
    return found


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


class _CleanReconcileAdapter:
    async def get_open_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        return []


def test_guard_block_emits_structured_event(fsm_harness):
    """Hypothesis: local reopen blocks must emit a structured guard event, not only an ERR response.
    Why this matters: forensic replay needs the exact reason, local state, and truth source at block time.
    Current expected buggy behavior: guard telemetry is too thin and does not provide the structured contract needed for incident triage.
    What future repair should change: emit `EVT:EXECUTION_GUARD_BLOCKED` with stable fields and explicit `why`.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"

    fsm.handle(_portfolio_state(symbol, position_amt="0.10"))
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    fsm.watchdog.pending_orders.clear()
    fsm.watchdog.acked_orders.clear()

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-guard-obs"))

    assert out is not None
    assert out.op == "ERR"
    payload, kwargs = _find_first_event(bus, "EVT:EXECUTION_GUARD_BLOCKED")
    assert payload is not None
    assert payload["symbol"] == symbol
    assert payload["rid"] == "rid-guard-obs"
    assert payload["block_reason"] == "local_manage_state_conflict"
    assert payload["reason"] == "local_manage_state_conflict"
    assert payload["current_local_state"] == ManageState.TRACKING.value
    assert payload["local_manage_state"] == ManageState.TRACKING.value
    assert payload["portfolio_truth_state"] == "LONG"
    assert payload["portfolio_state"] == "LONG"
    assert payload["divergence_detected"] is False
    assert isinstance(payload["ts_ms"], int)
    assert payload["why"] == "execution:local_manage_state_conflict"
    assert kwargs["why"] == "execution:local_manage_state_conflict"


def test_entry_order_in_flight_block_emits_structured_guard_event(fsm_harness):
    """Hypothesis: pending-entry blocks must emit the same structured guard contract as stale local-state blocks.
    Why this matters: incident replay must show that a foreign in-flight reservation, not local tracking, owned the fail-closed decision.
    Current expected buggy behavior: a foreign in-flight entry is blocked, but no explicit `entry_order_in_flight` guard event is emitted.
    What future repair should change: emit `EVT:EXECUTION_GUARD_BLOCKED` with stable pending-entry fields and reason codes.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    fsm.order_index = OrderIndex(ttl_sec=3600)

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    assert fsm.order_index.try_reserve_entry(symbol, "rid-foreign") is True

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-current"))

    assert out is not None
    assert out.op == "ERR"
    payload, kwargs = _find_first_event(bus, "EVT:EXECUTION_GUARD_BLOCKED")
    assert payload is not None
    assert payload["symbol"] == symbol
    assert payload["rid"] == "rid-current"
    assert payload["tracked_rid"] == "rid-foreign"
    assert payload["in_flight_entry_rid"] == "rid-foreign"
    assert payload["block_reason"] == "entry_order_in_flight"
    assert payload["reason"] == "entry_order_in_flight"
    assert payload["portfolio_truth_state"] == "FLAT"
    assert payload["portfolio_state"] == "FLAT"
    assert payload["why"] == "execution:entry_order_in_flight"
    assert kwargs["why"] == "execution:entry_order_in_flight"


def test_divergence_block_emits_structured_divergence_event(fsm_harness):
    """Hypothesis: REST-flat/local-tracking divergence must emit its own explicit divergence signal.
    Why this matters: operators need to separate a plain local guard from a true split-brain divergence.
    Current expected buggy behavior: reopen is blocked, but there is no standalone divergence event with tracked/local truth attached.
    What future repair should change: emit `EVT:EXECUTION_DIVERGENCE_DETECTED` with the mismatch contract.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"

    fsm.handle(_portfolio_state(symbol, position_amt="0"))
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    fsm._last_lifecycle_rid_by_symbol[symbol] = "rid-stale-local"
    fsm.watchdog.pending_orders.clear()
    fsm.watchdog.acked_orders.clear()

    out = fsm.handle(_cmd_open(symbol=symbol, rid="rid-divergence-open"))

    assert out is not None
    assert out.op == "ERR"
    payload, kwargs = _find_first_event(bus, "EVT:EXECUTION_DIVERGENCE_DETECTED")
    assert payload is not None
    assert payload["symbol"] == symbol
    assert payload["current_rid"] == "rid-divergence-open"
    assert payload["tracked_rid"] == "rid-stale-local"
    assert payload["local_manage_state"] == ManageState.TRACKING.value
    assert payload["portfolio_state"] == "FLAT"
    assert payload["divergence_type"] == "portfolio_flat_vs_local_nonflat"
    assert isinstance(payload["ts_ms"], int)
    assert payload["why"] == "execution:divergence_detected"
    assert kwargs["why"] == "execution:divergence_detected"


def test_stale_lifecycle_conflict_emits_structured_guard_event(fsm_harness):
    """Hypothesis: stale local lifecycle conflicts must surface as structured guard telemetry, not only as a dropped fill.
    Why this matters: the incident signature is a new fill arriving over active tracking state, and that must be explicit in logs/events.
    Current expected buggy behavior: the manage-flow guard returns ERR, but no execution guard event is emitted for the stale lifecycle conflict.
    What future repair should change: emit `EVT:EXECUTION_GUARD_BLOCKED` with `stale_local_lifecycle_conflict`.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    manage_flow.sl_order_id = "old-sl-order"
    manage_flow.tp_order_id = "old-tp-order"
    manage_flow.tp1_order_id = "old-tp1-order"

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
    payload, kwargs = _find_first_event(bus, "EVT:EXECUTION_GUARD_BLOCKED")
    assert payload is not None
    assert payload["symbol"] == symbol
    assert payload["rid"] == "rid-second-entry"
    assert payload["block_reason"] == "stale_local_lifecycle_conflict"
    assert payload["current_local_state"] == ManageState.TRACKING.value
    assert payload["why"] == "execution:stale_local_lifecycle_conflict"
    assert kwargs["why"] == "execution:stale_local_lifecycle_conflict"


def test_exit_match_success_emits_normalized_attempt(fsm_harness):
    """Hypothesis: successful TP/SL matching must expose normalized ids, inferred role, and before/after local state.
    Why this matters: without structured matcher telemetry, valid close events are hard to reconstruct after the fact.
    Current expected buggy behavior: runtime matcher can succeed, but there is no explicit forensic event describing how it matched.
    What future repair should change: emit `EVT:EXIT_MATCH_ATTEMPTED` with normalized ids, role inference, and matched=true.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    manage_flow.state = ManageState.BRACKETS_PLACED
    manage_flow.partial_exit_pct = 0.5
    manage_flow.sl_order_id = "sl-exchange-order"

    tp1_client_id = generate_client_order_id(
        "TP1",
        symbol,
        idempotent_key="rid-preack-tp",
    )
    manage_flow.tp1_order_id = tp1_client_id
    manage_flow.tp_order_id = tp1_client_id

    out = fsm.handle(
        _trade_executed(
            symbol=symbol,
            rid="rid-preack-tp",
            order_id="exchange-order-556677",
            client_order_id=tp1_client_id,
            side="SELL",
            qty="0.05",
            price="51050",
            order_type="TAKE_PROFIT_MARKET",
            reduce_only=True,
        )
    )

    assert out is not None
    assert out.op == "DEC"
    events = _find_all_events(bus, "EVT:EXIT_MATCH_ATTEMPTED")
    assert events
    payload, kwargs = events[-1]
    assert payload["symbol"] == symbol
    assert payload["incoming_order_id"] == "exchange-order-556677"
    assert payload["incoming_client_order_id"] == tp1_client_id
    assert payload["normalized_client_order_id"] == tp1_client_id.upper()
    assert payload["inferred_role"] == "TP1"
    assert payload["matched"] is True
    assert payload["match_reason"] in {
        "matched_tp1_client_order_id_exact",
        "matched_tp1_client_order_id_prefix",
    }
    assert payload["local_state_before"] == ManageState.BRACKETS_PLACED.value
    assert payload["local_state_after"] == ManageState.BRACKETS_PLACED.value
    assert payload["local_expected_ids"]["tp1_order_id"] == tp1_client_id
    assert payload["why"] == "execution:exit_match_attempted"
    assert kwargs["why"] == "execution:exit_match_attempted"


def test_exit_match_failure_emits_clear_failed_event(fsm_harness):
    """Hypothesis: unmatched exit-like events must emit explicit failure telemetry instead of disappearing into a None path.
    Why this matters: forensic triage must distinguish WS loss from matcher drift and bad payload shape.
    Current expected buggy behavior: unmatched bracket fills are silently ignored without a structured failure event.
    What future repair should change: emit both `EVT:EXIT_MATCH_ATTEMPTED` and `EVT:EXIT_MATCH_FAILED` with mismatch details.
    """
    fsm, bus, _ = fsm_harness
    symbol = "BTCUSDT"
    manage_flow = fsm.manage_flow(symbol)
    _prime_tracking_state(manage_flow, symbol=symbol)
    manage_flow.state = ManageState.BRACKETS_PLACED
    manage_flow.sl_order_id = "sl-exchange-order"
    manage_flow.tp1_order_id = "TP1-known-order"
    manage_flow.tp2_order_id = "TP2-known-order"
    manage_flow.tp_order_id = "TP-known-order"

    out = fsm.handle(
        _trade_executed(
            symbol=symbol,
            rid="rid-match-miss",
            order_id="exchange-order-999",
            client_order_id="mystery-client-order",
            side="SELL",
            qty="0.02",
            price="50900",
            order_type="TAKE_PROFIT_MARKET",
            reduce_only=True,
        )
    )

    assert out is None
    attempted = _find_all_events(bus, "EVT:EXIT_MATCH_ATTEMPTED")
    failed = _find_all_events(bus, "EVT:EXIT_MATCH_FAILED")
    assert attempted
    assert failed
    attempted_payload, attempted_kwargs = attempted[-1]
    failed_payload, failed_kwargs = failed[-1]
    assert attempted_payload["matched"] is False
    assert attempted_payload["match_reason"] == "no_tracked_bracket_match"
    assert attempted_payload["normalized_client_order_id"] == "MYSTERY-CLIENT-ORDER"
    assert attempted_payload["why"] == "execution:exit_match_attempted"
    assert attempted_kwargs["why"] == "execution:exit_match_attempted"
    assert failed_payload["symbol"] == symbol
    assert failed_payload["event_type"] == "TRADE_EXECUTED"
    assert failed_payload["incoming_order_id"] == "exchange-order-999"
    assert failed_payload["incoming_client_order_id"] == "mystery-client-order"
    assert failed_payload["normalized_client_order_id"] == "MYSTERY-CLIENT-ORDER"
    assert failed_payload["inferred_role"] == "UNKNOWN"
    assert failed_payload["mismatch_reason"] == "no_tracked_bracket_match"
    assert failed_payload["why"] == "execution:exit_match_failed"
    assert failed_kwargs["why"] == "execution:exit_match_failed"


@pytest.mark.asyncio
async def test_tidy_event_is_explicitly_non_business_close(fsm_harness):
    """Hypothesis: tidy/cleanup telemetry must explicitly say it is not a business-valid close reconcile.
    Why this matters: operators must not confuse orphan cleanup with an authoritative lifecycle close.
    Current expected buggy behavior: `EVT:SYMBOL_TIDY` lacks the explicit non-business-close marker required for forensic clarity.
    What future repair should change: emit structured tidy telemetry with `business_close_reconciled=false`.
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
    tidy_payload, tidy_kwargs = _find_first_event(bus, "EVT:EXECUTION_TIDY_PERFORMED")
    assert tidy_payload is not None
    assert tidy_payload["symbol"] == symbol
    assert tidy_payload["tidy_reason"] == "orphan_cleanup"
    assert tidy_payload["business_close_reconciled"] is False
    assert tidy_payload["source"] == "guardian_poll"
    assert tidy_payload["why"] == "guardian:orphan_cleanup:tidy"
    assert tidy_kwargs["why"] == "guardian:orphan_cleanup:tidy"

    symbol_tidy_payload, symbol_tidy_kwargs = _find_first_event(bus, "EVT:SYMBOL_TIDY")
    assert symbol_tidy_payload is not None
    assert symbol_tidy_payload["business_close_reconciled"] is False
    assert symbol_tidy_payload["tidy_reason"] == "orphan_cleanup"
    assert symbol_tidy_payload["why"] == "guardian:orphan_cleanup:tidy"
    assert symbol_tidy_kwargs["why"] == "guardian:orphan_cleanup:tidy"
    assert not _find_all_events(bus, "EVT:EXECUTION_CLOSE_RECONCILED")


@pytest.mark.asyncio
async def test_close_reconcile_event_is_distinct_from_tidy(fsm_harness):
    """Hypothesis: business close reconcile should emit its own explicit event instead of overloading tidy semantics.
    Why this matters: operators need a positive signal for authoritative reconcile without reinterpreting `SYMBOL_TIDY`.
    Current expected buggy behavior: reconcile only emitted tidy-like signals, leaving business-close confirmation implicit.
    What future repair should change: emit `EVT:EXECUTION_CLOSE_RECONCILED` separately while keeping tidy as non-business-close.
    """
    _, bus, cfg = fsm_harness
    guardian = OrderGuardian(
        adapter=_CleanReconcileAdapter(),
        store=InMemoryStore(),
        bus=bus,
        config=cfg,
    )

    await guardian.reconcile_symbol("BTCUSDT", rid="rid-close-obs")

    close_payload, close_kwargs = _find_first_event(bus, "EVT:EXECUTION_CLOSE_RECONCILED")
    assert close_payload is not None
    assert close_payload["symbol"] == "BTCUSDT"
    assert close_payload["rid"] == "rid-close-obs"
    assert close_payload["source"] == "guardian_reconcile"
    assert close_payload["business_close_reconciled"] is True
    assert close_payload["why"] == "guardian:close_reconciled"
    assert close_kwargs["why"] == "guardian:close_reconciled"

    symbol_tidy_payload, _ = _find_first_event(bus, "EVT:SYMBOL_TIDY")
    assert symbol_tidy_payload is not None
    assert symbol_tidy_payload["tidy_reason"] == "close_reconcile_tidy"
    assert symbol_tidy_payload["business_close_reconciled"] is False
