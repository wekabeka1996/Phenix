"""
EP-STAB-LIVEPOS-SL-SPAM: regression test for SL spam under aggregated OCO auto-heal.

This test encodes the *desired* behaviour:
    - After placing an initial aggregated TP/SL for a stable open position,
    - repeated aggregated OCO watchdog + auto-heal cycles MUST NOT create
      multiple distinct SL orders for the same (symbol, side).

After EP-STAB-SL-CLASS-FIX, this should be fixed by unified exit-order classification
and explicit FLAT_CLOSE support in watchdog invariants.

**Refs**: EP-STAB-SL-CLASS-FIX-C
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set

import pytest
from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.agg_oco_watchdog import (
    ExitOrderKind,
    validate_agg_oco_invariants,
)
from apps.reference.domains.execution_position.fsm import ExecPosFSM, PositionSnapshot
from tests.domains.execution_position.agg_oco_test_utils import make_execpos


class SpamAdapter:
    """
    Adapter stub that:
    - Executes aggregated bracket DEC:PLACE_ORDER via dedicated methods.
    - Exposes open positions correctly.
    - Exposes open orders WITHOUT reduceOnly/closePosition flags, mimicking
      the shape produced by BinanceAdapter.get_open_orders + ExchangeOrderResponse.
    """

    def __init__(self) -> None:
        self.base_url = "https://testnet.binancefuture.com"
        self._seq = 0
        self.open_orders: List[Dict[str, Any]] = []
        self.positions: List[Dict[str, Any]] = []

    def _next_order_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        return list(self.positions)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:  # noqa: ARG002
        return list(self.open_orders)

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:  # noqa: ARG002
        order_id_str = str(order_id)
        self.open_orders = [
            o for o in self.open_orders if str(o.get("orderId")) != order_id_str
        ]
        return {"symbol": symbol, "orderId": order_id_str, "status": "CANCELED"}

    async def place_stop_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: Optional[str] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place STOP_MARKET SL without reduceOnly/closePosition flags.
        """
        order_id = self._next_order_id("sl")
        order: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side or ("LONG" if side.upper() == "SELL" else "SHORT"),
            "orderId": order_id,
            "type": "STOP_MARKET",
            "stopPrice": stop_price,
            # Intentionally omit exit flags, reproducing adapter visibility bug.
            "reduceOnly": False,
            "closePosition": False,
            "clientOrderId": new_client_order_id,
            "workingType": "MARK_PRICE",
        }
        self.open_orders.append(order)
        return {"orderId": order_id, "clientOrderId": new_client_order_id or order_id}

    async def place_take_profit_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: Optional[str] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place TAKE_PROFIT_MARKET TP without reduceOnly/closePosition flags.
        """
        order_id = self._next_order_id("tp-mkt")
        order: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side or ("LONG" if side.upper() == "SELL" else "SHORT"),
            "orderId": order_id,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": stop_price,
            "reduceOnly": False,
            "closePosition": False,
            "clientOrderId": new_client_order_id,
            "workingType": "MARK_PRICE",
        }
        self.open_orders.append(order)
        return {"orderId": order_id, "clientOrderId": new_client_order_id or order_id}

    async def place_limit_reduce_only(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        position_side: Optional[str] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Optional fallback path used for TP when STOP_MARKET would immediately trigger.

        For regression purposes we also omit reduceOnly/closePosition here,
        keeping behaviour consistent with get_open_orders visibility.
        """
        order_id = self._next_order_id("tp")
        order: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side or ("LONG" if side.upper() == "SELL" else "SHORT"),
            "orderId": order_id,
            "type": "LIMIT",
            "price": price,
            "origQty": quantity,
            "reduceOnly": False,
            "closePosition": False,
            "clientOrderId": new_client_order_id,
        }
        self.open_orders.append(order)
        return {"orderId": order_id, "clientOrderId": new_client_order_id or order_id}


@pytest.mark.asyncio
async def test_agg_oco_sl_spam_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Regression scenario:

    1. SOLUSDT LONG position is open with qty > 0.
    2. ManageFlowFSM computes and places aggregated TP/SL via ExecPosFSM.
    3. Adapter exposes the position correctly but hides exit flags on open orders.
    4. Aggregated OCO watchdog + auto-heal run several times.

    Desired invariant:
        - The set of distinct STOP_MARKET SL orderIds remains size 1
          (no repeated replacement of SL for the same stable position).

    This test asserts the invariant; current implementation is expected
    to violate it and therefore is marked xfail.
    """
    symbol = "SOLUSDT"

    # ExecPosFSM in aggregated-only mode with stub guardian/watchdog.
    fsm: ExecPosFSM = make_execpos(monkeypatch, symbol=symbol)
    fsm.shadow_mode = False  # Allow _execute_decision to call adapter

    adapter = SpamAdapter()
    fsm.adapter = adapter

    # Enable aggregated OCO watchdog + auto-heal.
    fsm._agg_watchdog_enabled = True
    fsm._agg_watchdog_auto_heal = True

    # Seed live position snapshot (WS) and adapter positions.
    cache_key = fsm._ws_cache_key(symbol, "LONG")
    fsm._ws_position_cache[cache_key] = PositionSnapshot(
        symbol=symbol,
        side="LONG",
        position_amt=1.0,
        avg_price=130.0,
        updated_ts=time.time(),
    )
    adapter.positions = [
        {
            "symbol": symbol,
            "positionSide": "LONG",
            "positionAmt": "1.0",
            "entryPrice": "130.0",
        }
    ]

    # Seed ManageFlowFSM as if we just received an ENTRY fill.
    manage_flow = fsm.manage_flow(symbol)
    entry_msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="test",
        dst="execution_position",
        rid="sl_spam_entry",
        pld={"symbol": symbol, "qty": "1.0", "price": "130.0", "side": "BUY"},
    )
    manage_flow._on_fill(entry_msg)

    # Compute aggregated bracket levels and place initial TP/SL.
    levels = manage_flow._compute_aggregated_bracket_levels(
        reason="sl_spam_initial_place"
    )
    assert levels is not None, "entry_price guard unexpectedly blocked bracket compute"

    sl_decision = manage_flow._place_or_update_bracket_set_from_levels(
        entry_msg, levels, reason="sl_spam_initial_place"
    )
    decisions = []
    if sl_decision:
        decisions.append(sl_decision)
    decisions.extend(manage_flow.consume_pending_decisions())

    for dec in decisions:
        await fsm._execute_decision(dec)

    # Verify we have exactly one SL after initial placement.
    def current_sl_ids() -> Set[str]:
        return {
            str(order.get("orderId"))
            for order in adapter.open_orders
            if order.get("type") == "STOP_MARKET"
        }

    initial_sl_ids = current_sl_ids()
    assert len(
        initial_sl_ids) == 1, "expected exactly one SL after initial placement"

    unique_sl_ids: Set[str] = set(initial_sl_ids)

    # Run several watchdog + auto-heal cycles.
    for _ in range(3):
        await fsm._run_agg_oco_watchdog_once()
        unique_sl_ids |= current_sl_ids()

    # Desired invariant: no additional SLs should be created.
    # Current bug: unique_sl_ids often grows > 1 due to repeated auto-heal.
    assert (
        len(unique_sl_ids) == 1
    ), f"expected a single stable SL, got {len(unique_sl_ids)} distinct SL orderIds: {sorted(unique_sl_ids)}"


# ============================================================================
# NEW TESTS (Subtask C): Explicit scenario testing after EP-STAB-SL-CLASS-FIX
# ============================================================================


def test_agg_oco_happy_path_sl_stable():
    """
    Happy path scenario after EP-STAB-SL-CLASS-FIX:

    - Open position (qty > 0)
    - Coorrect SL bracket (STOP_LOSS) is present
    - Watchdog should NOT trigger NO_SL_FOR_OPEN_POSITION
    - No unnecessary auto-heal cycles

    **Refs**: EP-STAB-SL-CLASS-FIX-C
    """
    from apps.reference.domains.execution_position.agg_oco_watchdog import (
        normalize_orders_for_watchdog,
        normalize_positions_for_watchdog,
    )

    # Arrange: open LONG position with correct SL
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionSide": "LONG",
            "positionAmt": "1.0",
            "entryPrice": "50000.0",
        }
    ]

    orders = [
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "orderId": "sl-001",
            "type": "STOP_MARKET",
            "stopPrice": "45000.0",
            "reduceOnly": True,
            "clientOrderId": "bracket_sl_001",
        },
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "orderId": "tp-001",
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": "55000.0",
            "reduceOnly": True,
            "clientOrderId": "bracket_tp_001",
        }
    ]

    # Act: validate invariants
    violations = validate_agg_oco_invariants(
        positions=positions,
        open_orders=orders,
        bracket_metas=[],
        now_ts=time.time(),
    )

    # Assert: NO violations
    assert len(violations) == 0, f"expected zero violations, got: {violations}"

    # Verify normalized orders have correct exit_kind
    normalized_orders = normalize_orders_for_watchdog(orders)
    sl_orders = [o for o in normalized_orders if o.exit_kind ==
                 ExitOrderKind.STOP_LOSS]
    tp_orders = [o for o in normalized_orders if o.exit_kind ==
                 ExitOrderKind.TAKE_PROFIT]

    assert len(sl_orders) == 1, "expected exactly one SL order"
    assert len(tp_orders) == 1, "expected exactly one TP order"


def test_agg_oco_flat_close_prevents_no_sl_violation():
    """
    Edge-case scenario after EP-STAB-SL-CLASS-FIX:

    - Open position (qty > 0)
    - FLAT_CLOSE order (LIMIT/MARKET + reduceOnly) is closing position
    - NO SL bracket present (no STOP_LOSS order)
    - Watchdog should NOT trigger NO_SL_FOR_OPEN_POSITION
      because position is being explicitly closed via FLAT_CLOSE

    This is the key fix for SL-spam: before the fix, watchdog would see:
      - qty > 0
      - sl_count == 0
      → triggers NO_SL_FOR_OPEN_POSITION → auto-heal places new SL

    After the fix, watchdog checks for active FLAT_CLOSE and skips NO_SL detection.

    **Refs**: EP-STAB-SL-CLASS-FIX-B, EP-STAB-SL-CLASS-FIX-C
    """
    from apps.reference.domains.execution_position.agg_oco_watchdog import (
        normalize_orders_for_watchdog,
    )

    # Arrange: open LONG position with FLAT_CLOSE (no SL)
    positions = [
        {
            "symbol": "ETHUSDT",
            "positionSide": "LONG",
            "positionAmt": "10.0",
            "entryPrice": "2000.0",
        }
    ]

    orders = [
        {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "orderId": "close-001",
            "type": "LIMIT",
            "price": "2050.0",
            "qty": "10.0",
            "reduceOnly": True,
            "clientOrderId": "manual_close_001",
        }
    ]

    # Act: validate invariants
    violations = validate_agg_oco_invariants(
        positions=positions,
        open_orders=orders,
        bracket_metas=[],
        now_ts=time.time(),
    )

    # Assert: NO NO_SL_FOR_OPEN_POSITION violation
    # (because FLAT_CLOSE is active)
    no_sl_violations = [v for v in violations if v.why ==
                        "no_sl_for_open_position"]
    assert (
        len(no_sl_violations) == 0
    ), f"expected no NO_SL_FOR_OPEN_POSITION with FLAT_CLOSE active, got: {no_sl_violations}"

    # Verify the order is classified as FLAT_CLOSE
    normalized_orders = normalize_orders_for_watchdog(orders)
    assert len(normalized_orders) == 1
    assert normalized_orders[0].exit_kind == ExitOrderKind.FLAT_CLOSE
    assert normalized_orders[0].is_flat_close is True


def test_agg_oco_no_sl_violation_without_flat_close():
    """
    Verify that NO_SL_FOR_OPEN_POSITION is still triggered when:
    - Open position (qty > 0)
    - NO exit orders at all
    - NO FLAT_CLOSE active

    This ensures we didn't break the original invariant.

    **Refs**: EP-STAB-SL-CLASS-FIX-B
    """
    # Arrange: open position with NO exit orders
    positions = [
        {
            "symbol": "BNBUSDT",
            "positionSide": "SHORT",
            "positionAmt": "-5.0",
            "entryPrice": "300.0",
        }
    ]

    orders = []  # No exit orders

    # Act: validate invariants
    violations = validate_agg_oco_invariants(
        positions=positions,
        open_orders=orders,
        bracket_metas=[],
        now_ts=time.time(),
    )

    # Assert: SHOULD have NO_SL_FOR_OPEN_POSITION violation
    no_sl_violations = [v for v in violations if v.why ==
                        "no_sl_for_open_position"]
    assert (
        len(no_sl_violations) == 1
    ), f"expected exactly one NO_SL_FOR_OPEN_POSITION violation, got: {no_sl_violations}"
