"""Integration-style tests for Aggregated OCO multi-entry flows (OCO-9.1)."""

from __future__ import annotations

import time
import types
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

import pytest

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from apps.reference.services.order_guardian import (
    AggregatedOcoGuardianConfig,
    OrderGuardian,
)
from tests.domains.execution_position.test_aggregated_oco_scale_in_legacy import (  # noqa: F401
    _build_manage_config,
)

pytestmark = pytest.mark.integration


@dataclass
class FakeOrder:
    """Simplified order payload that OrderGuardian can normalize."""

    order_id: str
    client_order_id: str
    symbol: str
    position_side: str
    side: str
    order_type: str
    qty: Decimal
    price: Optional[str]
    reduce_only: bool = True
    close_position: bool = True
    created_ts: float = field(default_factory=lambda: time.time() * 1000)

    def to_dict(self) -> Dict[str, object]:
        return {
            "orderId": self.order_id,
            "clientOrderId": self.client_order_id,
            "symbol": self.symbol,
            "positionSide": self.position_side,
            "side": self.side,
            "type": self.order_type,
            "qty": str(self.qty),
            "origQty": str(self.qty),
            "price": self.price,
            "stopPrice": self.price if "STOP" in (self.order_type or "") else None,
            "reduceOnly": self.reduce_only,
            "closePosition": self.close_position,
            "status": "NEW",
            "time": int(self.created_ts),
        }


class FakeOrderAdapter:
    """Async-friendly adapter mock that tracks bracket placement state."""

    def __init__(self) -> None:
        self._orders: Dict[str, FakeOrder] = {}
        self._positions: Dict[tuple[str, str], Decimal] = {}
        self._seq: int = 1

    def create_order(
        self,
        *,
        client_order_id: str,
        symbol: str,
        position_side: str,
        side: str,
        order_type: str,
        qty: Decimal,
        price: Optional[str],
    ) -> FakeOrder:
        order_id = f"agg_{self._seq:05d}"
        self._seq += 1
        order = FakeOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            position_side=position_side,
            side=side,
            order_type=order_type,
            qty=Decimal(str(qty)),
            price=price,
        )
        self._orders[order_id] = order
        return order

    def list_orders(self, symbol: Optional[str] = None) -> List[FakeOrder]:
        if symbol is None:
            return list(self._orders.values())
        symbol_upper = symbol.upper()
        return [order for order in self._orders.values() if order.symbol.upper() == symbol_upper]

    def snapshot_for_symbol(self, symbol: str) -> List[FakeOrder]:
        return list(self.list_orders(symbol))

    def cancel_local(self, order_id: str) -> None:
        self._orders.pop(str(order_id), None)

    def update_position(self, symbol: str, side: str, qty: Decimal) -> None:
        key = (symbol.upper(), side.upper())
        if qty == 0:
            self._positions.pop(key, None)
            self._drop_orders_for(symbol, side)
            return
        self._positions[key] = Decimal(str(qty))

    def _drop_orders_for(self, symbol: str, side: str) -> None:
        side_upper = side.upper()
        symbol_upper = symbol.upper()
        for order_id, order in list(self._orders.items()):
            if order.symbol.upper() == symbol_upper and order.position_side.upper() == side_upper:
                del self._orders[order_id]

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, object]:
        removed = self._orders.pop(str(order_id), None)
        return {
            "symbol": symbol,
            "orderId": order_id,
            "status": "CANCELED" if removed else "UNKNOWN",
        }

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, object]]:
        return [order.to_dict() for order in self.list_orders(symbol)]

    async def get_open_positions(self) -> List[Dict[str, object]]:
        result: List[Dict[str, object]] = []
        for (symbol, side), qty in self._positions.items():
            result.append({
                "symbol": symbol,
                "positionSide": side,
                "positionAmt": str(qty),
            })
        return result

    async def get_order(self, symbol: str, order_id: str) -> Dict[str, object]:
        order = self._orders.get(str(order_id))
        return order.to_dict() if order else {}


class AggregatedOcoHarness:
    """Small harness that wires ManageFlowFSM to OrderGuardian via the fake adapter."""

    def __init__(
        self,
        *,
        symbol: str,
        entry_side: str = "BUY",
        aggregated_cfg: Dict[str, object],
        adapter: Optional[FakeOrderAdapter] = None,
        guardian: Optional[OrderGuardian] = None,
    ) -> None:
        self.symbol = symbol
        self.entry_side = entry_side.upper()
        self.exit_side = "SELL" if self.entry_side == "BUY" else "BUY"
        self.agg_side = "LONG" if self.entry_side == "BUY" else "SHORT"
        self.adapter = adapter or FakeOrderAdapter()
        guardian_cfg = AggregatedOcoGuardianConfig(
            enabled=True,
            ttl_protect_new_bracket_ms=0,
            allow_unprotected_position=False,
        )
        self.guardian = guardian or OrderGuardian(
            adapter=self.adapter,
            poll_interval_ms=0,
            aggregated_oco_cfg=guardian_cfg,
        )
        manage_config = _build_manage_config(
            self.symbol, aggregated_cfg=aggregated_cfg)
        self.fsm = ManageFlowFSM(config=manage_config,
                                 order_guardian=self.guardian)
        self.position_qty = Decimal("0")
        self._install_order_hooks()

    def _install_order_hooks(self) -> None:
        original_emit = self.fsm._emit_place_order
        original_cancel = self.fsm._emit_cancel_order

        def _patched_emit(fsm_self, msg, client_id, order_type, side, qty, price, why):
            decision = original_emit(
                msg, client_id, order_type, side, qty, price, why)
            if isinstance(decision, Message):
                self._capture_bracket_decision(decision)
            return decision

        def _patched_cancel(fsm_self, msg, order_id, why):
            decision = original_cancel(msg, order_id, why)
            if order_id:
                self.adapter.cancel_local(order_id)
            return decision

        self.fsm._emit_place_order = types.MethodType(
            _patched_emit, self.fsm)  # type: ignore[attr-defined]
        self.fsm._emit_cancel_order = types.MethodType(
            _patched_cancel, self.fsm)  # type: ignore[attr-defined]

    def _capture_bracket_decision(self, decision: Message) -> None:
        payload = decision.pld or {}
        order_type = payload.get("order_type")
        if order_type not in {"STOP_MARKET", "LIMIT"}:
            return
        qty_value = payload.get("qty") or payload.get("quantity") or "0"
        qty_dec = Decimal(str(qty_value))
        client_id = payload.get(
            "newClientOrderId") or decision.idempotent_key or f"{decision.rid}_{order_type}"
        symbol = payload.get("symbol") or self.symbol
        side = payload.get("side") or self.exit_side
        price = payload.get("price") or payload.get("stopPrice")
        order = self.adapter.create_order(
            client_order_id=client_id,
            symbol=symbol,
            position_side=self.agg_side,
            side=side,
            order_type=str(order_type),
            qty=qty_dec,
            price=str(price) if price is not None else None,
        )
        ack = Message(
            op="EVT",
            verb="ORDER_UPDATED",
            src="adapter",
            dst="execution_position",
            pld={
                "clientOrderId": client_id,
                "orderId": order.order_id,
                "symbol": symbol,
                "positionSide": self.agg_side,
            },
        )
        self.fsm.handle(ack)

    def open_entry(self, qty: str | float | Decimal, *, enforce_guardian: bool = True) -> None:
        qty_dec = Decimal(str(qty))
        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            rid=f"entry_{self.symbol}_{time.time_ns()}",
            pld={
                "symbol": self.symbol,
                "side": self.entry_side,
                "qty": str(qty_dec),
                "price": "100.0",
            },
        )
        self.fsm.handle(msg)
        self.position_qty += qty_dec
        self.adapter.update_position(
            self.symbol, self.agg_side, self.position_qty)
        if enforce_guardian:
            self._enforce_guardian_guard()

    def partial_close(self, qty: str | float | Decimal) -> None:
        qty_dec = Decimal(str(qty))
        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            rid=f"exit_{self.symbol}_{time.time_ns()}",
            pld={
                "symbol": self.symbol,
                "side": self.exit_side,
                "qty": str(qty_dec),
                "price": "100.0",
                "reduceOnly": True,
                "closePosition": True,
                "order_type": "MARKET",
            },
        )
        self.fsm.handle(msg)
        self.position_qty = max(Decimal("0"), self.position_qty - qty_dec)
        self.adapter.update_position(
            self.symbol, self.agg_side, self.position_qty)
        self._enforce_guardian_guard()

    def full_close(self) -> None:
        if self.position_qty == 0:
            return
        self.partial_close(self.position_qty)

    def current_orders(self) -> List[FakeOrder]:
        return self.adapter.snapshot_for_symbol(self.symbol)

    def guardian_meta(self):
        return self.guardian.get_active_bracket_set(self.symbol, self.agg_side)

    def _enforce_guardian_guard(self) -> None:
        open_orders = self.adapter.snapshot_for_symbol(self.symbol)
        self.guardian.ensure_single_bracket_set_for_position(
            symbol=self.symbol,
            side=self.agg_side,
            position_amt=float(self.position_qty),
            open_orders=open_orders,
            now_ts=time.time(),
        )


def _build_aggregated_cfg(
    *,
    recalc_on_scale_in: bool = True,
    recalc_on_partial_close: bool = True,
    ttl_ms: int = 0,
) -> Dict[str, object]:
    return {
        "enabled": True,
        "recalc_on_scale_in": recalc_on_scale_in,
        "recalc_on_partial_close": recalc_on_partial_close,
        "ttl_protect_new_bracket_ms": ttl_ms,
        "allow_unprotected_position": False,
    }


@pytest.fixture
def aggregated_cfg() -> Dict[str, object]:
    return _build_aggregated_cfg()


def _assert_single_bracket_set(harness: AggregatedOcoHarness) -> None:
    orders = harness.current_orders()
    assert len(orders) == 2, "aggregated flow must keep a single TP/SL pair"
    for order in orders:
        assert order.reduce_only and order.close_position
        assert order.qty == harness.position_qty


def test_three_entries_share_single_bracket_set(aggregated_cfg: Dict[str, object]) -> None:
    harness = AggregatedOcoHarness(
        symbol="BTCUSDT", aggregated_cfg=aggregated_cfg)

    versions: List[int] = []
    unit = Decimal("0.001")
    for idx in range(3):
        harness.open_entry("0.001")
        meta = harness.guardian_meta()
        assert meta is not None
        versions.append(meta.version)
        _assert_single_bracket_set(harness)
        assert harness.position_qty == unit * Decimal(idx + 1)

    assert versions == [0, 1, 2], "guardian must bump version on every recalc"


def test_partial_close_rebuilds_brackets_with_new_qty(aggregated_cfg: Dict[str, object]) -> None:
    harness = AggregatedOcoHarness(
        symbol="BTCUSDT", aggregated_cfg=aggregated_cfg)

    for _ in range(3):
        harness.open_entry("0.001")
    harness.partial_close("0.001")

    assert harness.position_qty == Decimal("0.002")
    _assert_single_bracket_set(harness)
    latest_meta = harness.guardian_meta()
    assert latest_meta is not None
    assert latest_meta.version == 3, "partial-close must register a fresh bracket set"


def test_full_close_clears_guardian_state(aggregated_cfg: Dict[str, object]) -> None:
    harness = AggregatedOcoHarness(
        symbol="BTCUSDT", aggregated_cfg=aggregated_cfg)

    for _ in range(2):
        harness.open_entry("0.002")
    harness.full_close()

    assert harness.position_qty == Decimal("0")
    assert harness.current_orders() == []
    assert harness.guardian_meta() is None


def test_per_symbol_guardian_cleanup_is_isolated(aggregated_cfg: Dict[str, object]) -> None:
    adapter = FakeOrderAdapter()
    guardian_cfg = AggregatedOcoGuardianConfig(
        enabled=True,
        ttl_protect_new_bracket_ms=0,
        allow_unprotected_position=False,
    )
    guardian = OrderGuardian(
        adapter=adapter, poll_interval_ms=0, aggregated_oco_cfg=guardian_cfg)

    btc = AggregatedOcoHarness(
        symbol="BTCUSDT",
        aggregated_cfg=aggregated_cfg,
        adapter=adapter,
        guardian=guardian,
    )
    eth = AggregatedOcoHarness(
        symbol="ETHUSDT",
        aggregated_cfg=aggregated_cfg,
        adapter=adapter,
        guardian=guardian,
    )

    btc.open_entry("0.001")
    eth.open_entry("0.5")
    # leave duplicate brackets on BTC
    btc.open_entry("0.001", enforce_guardian=False)

    cleanup_count = guardian.ensure_single_bracket_set_for_position(
        symbol="BTCUSDT",
        side="LONG",
        position_amt=float(btc.position_qty),
        open_orders=adapter.snapshot_for_symbol("BTCUSDT"),
        now_ts=time.time(),
    )
    assert cleanup_count >= 1, "BTC cleanup should remove the older bracket set"

    eth_orders = adapter.snapshot_for_symbol("ETHUSDT")
    assert len(eth_orders) == 2, "ETH bracket set must remain untouched"
    btc_meta = guardian.get_active_bracket_set("BTCUSDT", "LONG")
    eth_meta = guardian.get_active_bracket_set("ETHUSDT", "LONG")
    assert btc_meta is not None and eth_meta is not None
    assert btc_meta.bracket_set_id != eth_meta.bracket_set_id
    assert btc_meta.symbol == "BTCUSDT"
    assert eth_meta.symbol == "ETHUSDT"
