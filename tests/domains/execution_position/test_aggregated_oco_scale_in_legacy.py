"""Integration-style regression tests for legacy execution_position scale-in behaviour."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pytest

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
import types


@dataclass
class PositionSnapshot:
    """Represents aggregated position state for a (symbol, side) pair."""

    symbol: str
    side: str
    qty: Decimal


@dataclass
class BracketOrder:
    """Simplified view of SL orders tracked by the harness."""

    symbol: str
    side: str
    qty: Decimal
    order_id: str
    client_order_id: str


class ExecutionTestEnv:
    """Minimal harness that drives ManageFlowFSM for scale-in scenarios."""

    def __init__(self, symbol: str, manage_config: Optional[Dict[str, Any]] = None):
        self.symbol = symbol
        config = manage_config or _build_manage_config(symbol)
        self.manage_fsm = ManageFlowFSM(config=config)
        self._install_emit_hook()
        self._positions: Dict[Tuple[str, str], Decimal] = {}
        self._sl_orders: List[BracketOrder] = []
        self._tp_ack_count: int = 0

    def open_with_brackets(self, *, side: str, qty: float, price: float = 100.0) -> None:
        """Simulate CMD:OPEN + fill + bracket placement for the requested size."""

        order_side = _normalize_side(side)
        qty_dec = Decimal(str(qty))
        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld={
                "symbol": self.symbol,
                "side": order_side,
                "qty": str(qty),
                "price": str(price),
            },
        )
        self.manage_fsm.handle(msg)

        key = (self.symbol, order_side)
        self._positions[key] = self._positions.get(key, Decimal("0")) + qty_dec

    def close_position_partially(
        self,
        *,
        side: str,
        qty: float,
        price: float = 100.0,
        cancel_brackets_first: bool = True,
    ) -> None:
        """Simulate manual partial close that cancels brackets before exiting."""

        order_side = _normalize_side(side)
        reduce_side = "SELL" if order_side == "BUY" else "BUY"
        qty_dec = Decimal(str(qty))
        key = (self.symbol, order_side)
        current_qty = self._positions.get(key, Decimal("0"))
        if qty_dec > current_qty:
            raise ValueError(
                "Cannot close more than the current position size")

        if cancel_brackets_first:
            self._cancel_sl_for_side(order_side)

        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld={
                "symbol": self.symbol,
                "side": reduce_side,
                "qty": str(qty),
                "price": str(price),
                "reduceOnly": True,
                "closePosition": True,
            },
        )
        self.manage_fsm.handle(msg)
        self._positions[key] = current_qty - qty_dec

    def get_position_state(self, symbol: str, side: str) -> PositionSnapshot:
        order_side = _normalize_side(side)
        qty = self._positions.get((symbol, order_side), Decimal("0"))
        return PositionSnapshot(symbol=symbol, side=order_side, qty=qty)

    def list_sl_orders(self, symbol: str, side: str) -> List[BracketOrder]:
        order_side = _normalize_side(side)
        return [
            order
            for order in self._sl_orders
            if order.symbol == symbol and order.side == order_side
        ]

    def list_open_orders(self, symbol: str, side: str) -> List[BracketOrder]:
        return self.list_sl_orders(symbol, side)

    def _install_emit_hook(self) -> None:
        original_emit = self.manage_fsm._emit_place_order

        def _patched_emit(fsm_self, msg, client_id, order_type, side, qty, price, why):
            decision = original_emit(
                msg, client_id, order_type, side, qty, price, why)
            self._capture_emitted_decision(decision)
            return decision

        self.manage_fsm._emit_place_order = types.MethodType(  # type: ignore[attr-defined]
            _patched_emit,
            self.manage_fsm,
        )

    def _capture_emitted_decision(self, decision: Optional[Message]) -> None:
        if not isinstance(decision, Message):
            return

        payload = decision.pld or {}
        order_type = payload.get("order_type")

        if order_type == "STOP_MARKET":
            self._maybe_track_sl(decision)
        elif order_type == "LIMIT":
            self._acknowledge_tp(decision)

    def _maybe_track_sl(self, decision: Message) -> None:
        if decision.verb != "PLACE_ORDER":
            return
        payload = decision.pld or {}
        if payload.get("order_type") != "STOP_MARKET":
            return

        qty_dec = Decimal(str(payload.get("qty", "0")))
        client_id = (
            payload.get("newClientOrderId")
            or decision.idempotent_key
            or f"{decision.rid}_sl"
        )
        order_id = f"sl_{len(self._sl_orders) + 1}"
        tracking_side = _normalize_side(
            getattr(self.manage_fsm, "position_side", None)
            or payload.get("side", "BUY")
        )
        self._sl_orders.append(
            BracketOrder(
                symbol=payload.get("symbol", self.symbol),
                side=tracking_side,
                qty=qty_dec,
                order_id=order_id,
                client_order_id=client_id,
            )
        )

        ack = Message(
            op="EVT",
            verb="ORDER_UPDATED",
            src="test",
            dst="execution_position",
            pld={"clientOrderId": client_id, "orderId": order_id},
        )
        self.manage_fsm.handle(ack)

    def _acknowledge_tp(self, decision: Message) -> None:
        payload = decision.pld or {}
        client_id = (
            payload.get("newClientOrderId")
            or decision.idempotent_key
            or f"{decision.rid}_tp"
        )
        self._tp_ack_count += 1
        ack = Message(
            op="EVT",
            verb="ORDER_UPDATED",
            src="test",
            dst="execution_position",
            pld={
                "clientOrderId": client_id,
                "orderId": f"tp_{self._tp_ack_count}",
            },
        )
        self.manage_fsm.handle(ack)

    def _cancel_sl_for_side(self, side: str) -> None:
        order_side = _normalize_side(side)
        self._sl_orders = [
            order
            for order in self._sl_orders
            if not (order.symbol == self.symbol and order.side == order_side)
        ]
        if getattr(self.manage_fsm, "position_side", None) == order_side:
            self.manage_fsm.sl_order_id = None
            self.manage_fsm.tp_order_id = None


def _build_manage_config(
    symbol: str,
    *,
    aggregated_cfg: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    manage_node: Dict[str, Any] = {
        "auto": True,
        "brackets": {
            "enable": True,
            "keep_single_bracket_set": True,
            "sl": {"fixed_bps": 50},
            "tp": {"fixed_bps": 100},
            "offset_bps": 5,
        },
    }

    if aggregated_cfg:
        manage_node["mode"] = "aggregated_only"
        manage_node["brackets"]["aggregated_oco"] = aggregated_cfg

    config: Dict[str, Any] = {
        "trading": {
            "instruments": {
                symbol: {
                    "tick_size": "0.01",
                    "step_size": "0.0001",
                    "min_qty": "0.0001",
                    "min_notional": "0.001",
                }
            },
            "execution": {
                "manage": copy.deepcopy(manage_node),
            },
        }
    }

    config["config_v2"] = {
        "domains": {
            "execution": {
                "manage": copy.deepcopy(manage_node),
            }
        }
    }

    return config


def _normalize_side(side: str) -> str:
    side_upper = side.upper()
    if side_upper in {"LONG", "BUY"}:
        return "BUY"
    if side_upper in {"SHORT", "SELL"}:
        return "SELL"
    raise ValueError(f"Unsupported side '{side}'")


def _build_default_aggregated_cfg(
    *,
    enabled: bool,
    recalc_on_scale_in: bool,
    recalc_on_partial_close: bool,
    allow_unprotected_position: bool,
) -> Optional[Dict[str, object]]:
    if not enabled:
        return None

    return {
        "enabled": True,
        "aggregated_only_mode": True,
        "recalc_on_scale_in": recalc_on_scale_in,
        "recalc_on_partial_close": recalc_on_partial_close,
        "ttl_protect_new_bracket_ms": 0,
        "allow_unprotected_position": allow_unprotected_position,
    }


def setup_execution_env_for_symbol(
    symbol: str,
    *,
    aggregated_oco_enabled: bool = False,
    recalc_on_scale_in: bool = True,
    recalc_on_partial_close: bool = False,
    allow_unprotected_position: bool = False,
) -> ExecutionTestEnv:
    """Create a ManageFlowFSM harness with optional Aggregated OCO flags."""

    aggregated_cfg = _build_default_aggregated_cfg(
        enabled=aggregated_oco_enabled,
        recalc_on_scale_in=recalc_on_scale_in,
        recalc_on_partial_close=recalc_on_partial_close,
        allow_unprotected_position=allow_unprotected_position,
    )

    manage_config = _build_manage_config(symbol, aggregated_cfg=aggregated_cfg)
    return ExecutionTestEnv(symbol, manage_config=manage_config)


def open_position_with_brackets(env: ExecutionTestEnv, symbol: str, side: str, qty: float):
    """Open a position and wait for ManageFlowFSM to emit brackets."""

    env.open_with_brackets(side=side, qty=qty)
    return env.get_position_state(symbol, side), env.list_open_orders(symbol, side)


def partial_close_position(
    env: ExecutionTestEnv,
    symbol: str,
    side: str,
    qty: float,
    *,
    cancel_brackets_first: bool = True,
):
    """Execute a partial close via the harness and return the new snapshots."""

    env.close_position_partially(
        side=side,
        qty=qty,
        cancel_brackets_first=cancel_brackets_first,
    )
    return env.get_position_state(symbol, side), env.list_open_orders(symbol, side)


def assert_position_fully_protected(env: ExecutionTestEnv, symbol: str, side: str, why: str) -> None:
    """Ensure sum of SL qty covers the aggregated position qty (legacy invariant)."""

    position = env.get_position_state(symbol, side)
    sl_orders = env.list_sl_orders(symbol, side)
    total_sl_qty = sum(order.qty for order in sl_orders)
    epsilon = position.qty * Decimal("1e-6")
    assert total_sl_qty + epsilon >= position.qty, (
        f"[{why}] expected SL to cover full position size: "
        f"position_qty={position.qty}, sl_total_qty={total_sl_qty}"
    )


def assert_latest_sl_matches_position(env: ExecutionTestEnv, symbol: str, side: str, why: str) -> None:
    sl_orders = env.list_sl_orders(symbol, side)
    assert sl_orders, f"[{why}] expected at least one SL order for {symbol}"
    latest_sl_qty = sl_orders[-1].qty
    position = env.get_position_state(symbol, side)
    assert latest_sl_qty == position.qty, (
        f"[{why}] expected latest SL qty to match position qty: "
        f"position_qty={position.qty}, sl_qty={latest_sl_qty}"
    )


@pytest.mark.integration
@pytest.mark.legacy
@pytest.mark.xfail(reason="Legacy ManageFlowFSM still drops SL coverage on scale-in", strict=False)
def test_scale_in_legacy_leaves_position_unprotected():
    symbol = "SOLUSDT"
    side = "LONG"
    env = setup_execution_env_for_symbol(symbol)

    # First entry installs initial brackets
    open_position_with_brackets(env, symbol, side, qty=1.0)
    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="first_entry_should_be_fully_protected",
    )

    # Scale-in doubles the position but legacy ManageFlowFSM keeps previous SL
    open_position_with_brackets(env, symbol, side, qty=1.0)
    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="scale_in_should_keep_full_sl_protection",
    )


@pytest.mark.integration
def test_scale_in_with_aggregated_oco_keeps_full_sl_coverage():
    symbol = "SOLUSDT"
    side = "LONG"

    env = setup_execution_env_for_symbol(
        symbol,
        aggregated_oco_enabled=True,
        recalc_on_scale_in=True,
        recalc_on_partial_close=True,
        allow_unprotected_position=False,
    )

    first_qty = 1.0
    open_position_with_brackets(env, symbol, side, first_qty)

    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="agg_first_entry_should_be_fully_protected",
    )

    scale_in_qty = 1.0
    open_position_with_brackets(env, symbol, side, scale_in_qty)

    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="agg_scale_in_should_keep_full_sl_protection",
    )


@pytest.mark.integration
def test_scale_in_reinstalls_sl_when_aggregated_enabled():
    symbol = "SOLUSDT"
    side = "LONG"
    env = setup_execution_env_for_symbol(
        symbol,
        aggregated_oco_enabled=True,
        recalc_on_scale_in=True,
        recalc_on_partial_close=True,
        allow_unprotected_position=False,
    )

    open_position_with_brackets(env, symbol, side, qty=1.0)
    assert_latest_sl_matches_position(
        env,
        symbol,
        side,
        why="aggregated_first_entry_installs_sl",
    )

    open_position_with_brackets(env, symbol, side, qty=0.5)
    assert_latest_sl_matches_position(
        env,
        symbol,
        side,
        why="aggregated_scale_in_reinstalls_sl",
    )
