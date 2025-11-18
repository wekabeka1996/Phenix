"""Unit tests for aggregated OCO integration inside ManageFlowFSM."""

from __future__ import annotations

import importlib.util
import os
import time
from decimal import Decimal
from typing import Dict, Any
from types import SimpleNamespace

import pytest
from vfoundation.core.protocol import Message

spec = importlib.util.spec_from_file_location(
    "apps.reference.domains.execution_position.fsm_manage",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "apps",
        "reference",
        "domains",
        "execution_position",
        "fsm_manage.py",
    ),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ManageFlowFSM = mod.ManageFlowFSM
ManageState = mod.ManageState
PositionSide = mod.PositionSide


def build_config(
    *,
    aggregated_enabled: bool,
    recalc_scale_in: bool = True,
    recalc_partial: bool = False,
    ttl_ms: int = 0,
    allow_unprotected: bool = False,
) -> Dict[str, Any]:
    recalc_partial_value = recalc_partial
    allow_unprotected_value = allow_unprotected
    if aggregated_enabled:
        recalc_partial_value = True  # aggregated-only mode contract
        allow_unprotected_value = False
    return {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "sl": {"fixed_bps": 50},
                        "tp": {"fixed_bps": 100},
                        "aggregated_oco": {
                            "enabled": aggregated_enabled,
                            "aggregated_only_mode": aggregated_enabled,
                            "recalc_on_scale_in": recalc_scale_in,
                            "recalc_on_partial_close": recalc_partial_value,
                            "ttl_protect_new_bracket_ms": ttl_ms,
                            "allow_unprotected_position": allow_unprotected_value,
                        },
                    },
                }
            },
            "instruments": {
                "SOLUSDT": {
                    "tick_size": "0.01",
                    "min_price": "0.01",
                }
            },
        }
    }


def make_msg(op: str = "EVT", verb: str = "FILL", pld: Dict[str, Any] | None = None) -> Message:
    payload = {"symbol": "SOLUSDT"}
    if pld:
        payload.update(pld)
    return Message(op=op, verb=verb, src="test", dst="manage", rid="rid-1", pld=payload)


def test_place_brackets_routes_to_aggregated_when_enabled(monkeypatch):
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True))
    fsm.position_qty = Decimal("1")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"

    calls = {"agg": 0, "legacy": 0}

    def fake_agg(self, msg, reason):
        calls["agg"] += 1
        return None

    def fake_legacy(self, msg):
        calls["legacy"] += 1
        return None

    monkeypatch.setattr(ManageFlowFSM, "_place_brackets_aggregated", fake_agg)
    monkeypatch.setattr(ManageFlowFSM, "_place_brackets_legacy", fake_legacy)

    fsm._place_brackets(make_msg())

    assert calls["agg"] == 1
    assert calls["legacy"] == 0


def test_place_brackets_uses_legacy_when_aggregated_disabled(monkeypatch):
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=False))
    fsm.position_qty = Decimal("1")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"

    calls = {"agg": 0, "legacy": 0}

    def fake_agg(self, msg, reason):
        calls["agg"] += 1
        return None

    def fake_legacy(self, msg):
        calls["legacy"] += 1
        return None

    monkeypatch.setattr(ManageFlowFSM, "_place_brackets_aggregated", fake_agg)
    monkeypatch.setattr(ManageFlowFSM, "_place_brackets_legacy", fake_legacy)

    fsm._place_brackets(make_msg())

    assert calls["agg"] == 0
    assert calls["legacy"] == 1


def test_scale_in_fill_triggers_recalc_when_enabled(monkeypatch):
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True, ttl_ms=0))
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"
    fsm.state = ManageState.BRACKETS_PLACED

    recalc_reasons: list[str] = []

    def fake_recalc(self, msg, reason):
        recalc_reasons.append(reason)
        return Message(op="DEC", verb="NOP", src="test", dst="manage", rid="rid-recalc", pld={})

    monkeypatch.setattr(
        ManageFlowFSM, "_recalc_aggregated_brackets", fake_recalc)

    msg = make_msg(
        verb="FILL",
        pld={
            "qty": "0.5",
            "price": "101",
            "side": "BUY",
        },
    )

    result = fsm._check_rules(msg)

    assert recalc_reasons == ["scale_in_fill"]
    assert result is not None


def test_partial_close_recalc_always_triggers_in_aggregated_mode(monkeypatch):
    fsm = ManageFlowFSM(
        config=build_config(aggregated_enabled=True,
                            recalc_partial=True, ttl_ms=0)
    )
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"
    fsm.state = ManageState.BRACKETS_PLACED

    recalc_reasons: list[str] = []

    def fake_recalc(self, msg, reason):
        recalc_reasons.append(reason)
        return Message(op="DEC", verb="NOP", src="test", dst="manage", rid="rid-recalc", pld={})

    monkeypatch.setattr(
        ManageFlowFSM, "_recalc_aggregated_brackets", fake_recalc)

    msg = make_msg(
        verb="FILL",
        pld={
            "qty": "0.4",
            "price": "99",
            "side": "SELL",
            "reduceOnly": "true",
        },
    )

    fsm._check_rules(msg)
    assert recalc_reasons == ["partial_close_fill"]


def test_recalc_respects_ttl_guard(monkeypatch):
    fsm = ManageFlowFSM(
        config=build_config(aggregated_enabled=True,
                            ttl_ms=10_000, allow_unprotected=False)
    )
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"
    fsm.sl_order_id = "sl-1"
    fsm.tp_order_id = "tp-1"
    fsm._aggregated_last_place_ts = int(time.time() * 1000)

    called = {"place": 0}

    def fake_place(self, msg, reason):
        called["place"] += 1
        return None

    monkeypatch.setattr(
        ManageFlowFSM, "_place_brackets_aggregated", fake_place)

    result = fsm._recalc_aggregated_brackets(make_msg(), reason="ttl_guard")

    assert result is None
    assert called["place"] == 0


def test_recalc_bypasses_ttl_when_unprotected(monkeypatch):
    fsm = ManageFlowFSM(
        config=build_config(aggregated_enabled=True,
                            ttl_ms=10_000, allow_unprotected=False)
    )
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"
    fsm._aggregated_last_place_ts = int(time.time() * 1000)

    called = {"place": 0}

    def fake_place(self, msg, reason):
        called["place"] += 1
        return Message(op="DEC", verb="NOP", src="test", dst="manage", rid="rid-recalc", pld={})

    monkeypatch.setattr(
        ManageFlowFSM, "_place_brackets_aggregated", fake_place)

    result = fsm._recalc_aggregated_brackets(make_msg(), reason="ttl_guard")

    assert called["place"] == 1
    assert result is not None


def test_convert_position_side_handles_lowercase_values():
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True))
    fsm.position_side = "buy"
    assert fsm._convert_position_side() == "LONG"
    fsm.position_side = "sell"
    assert fsm._convert_position_side() == "SHORT"


def test_live_snapshot_canonicalizes_side(monkeypatch):
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True))
    fsm._aggregated_only_mode = True

    fsm._live_position_provider = lambda: {
        "symbol": "SOLUSDT",
        "qty": "-3",
        "avg_price": "25",
        "side": "sell",
        "updated_ts": int(time.time() * 1000),
    }

    reasons: list[str] = []

    def fake_recalc(self, msg, reason):
        reasons.append(reason)
        return None

    monkeypatch.setattr(
        ManageFlowFSM, "_recalc_aggregated_brackets", fake_recalc)

    msg = make_msg(pld={"qty": "1", "side": "BUY", "price": "26"})
    fsm._handle_aggregated_fill_event(msg)

    assert fsm.position_side == "SELL"
    assert fsm._agg_side == "SHORT"
    assert reasons == ["snapshot_entry_fill"]


def test_agg_oco_fill_to_brackets_pipeline(monkeypatch):
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True))
    fsm.position_qty = Decimal("2")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = None  # Force canonicalization fallback
    fsm._agg_side = "LONG"
    fsm.symbol = "SOLUSDT"

    fake_levels = SimpleNamespace(
        sl_price=Decimal("95"),
        tp_price=Decimal("110"),
        why="entry_fill",
    )

    monkeypatch.setattr(
        ManageFlowFSM,
        "_compute_aggregated_bracket_levels",
        lambda self, reason: fake_levels,
    )

    monkeypatch.setattr(
        ManageFlowFSM,
        "_normalize_reduce_only_qty",
        lambda self, **kwargs: str(kwargs.get("qty")),
    )

    placed_orders = []

    def fake_emit_place_order(self, msg, client_id, order_type, side, qty, price, why):
        placed_orders.append(
            {
                "client_id": client_id,
                "order_type": order_type,
                "side": side,
                "qty": qty,
                "price": price,
            }
        )
        return Message(
            op="DEC",
            verb="PLACE_ORDER",
            src="test",
            dst="execution_position",
            rid=msg.rid,
            pld={"client_id": client_id},
        )

    monkeypatch.setattr(ManageFlowFSM, "_emit_place_order",
                        fake_emit_place_order)

    msg = make_msg()
    msg.rid = "b3f23e26-1a95-4228-ac36-707835784a35"
    result = fsm._place_brackets_aggregated(msg, reason="entry_fill")

    assert result is not None
    assert len(placed_orders) == 2
    assert {order["order_type"]
            for order in placed_orders} == {"STOP_MARKET", "LIMIT"}
    assert all(order["side"] == "SELL" for order in placed_orders)
    assert all(len(order["client_id"]) <= 36 for order in placed_orders)


def test_client_id_helper_caps_length():
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True))
    fsm.position_qty = Decimal("1")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.symbol = "SOLUSDT"
    fsm.position_open_ts = time.time()

    msg = make_msg()
    msg.rid = "rid-" + ("abcdef" * 8)  # force long seed

    base_id, sl_id, tp_id = fsm._build_sl_tp_client_ids(msg)

    assert len(base_id) <= ManageFlowFSM.CLIENT_ORDER_ID_MAX_LEN - len("_sl")
    assert len(sl_id) <= ManageFlowFSM.CLIENT_ORDER_ID_MAX_LEN
    assert len(tp_id) <= ManageFlowFSM.CLIENT_ORDER_ID_MAX_LEN
    assert sl_id.endswith("_sl")
    assert tp_id.endswith("_tp")

    seed = fsm._generate_client_seed(msg, extra="emergency")
    _, emergency_id = fsm._compose_client_order_id(
        seed, "emergency_sl_with_extra_suffix"
    )
    assert len(emergency_id) <= ManageFlowFSM.CLIENT_ORDER_ID_MAX_LEN


def test_agg_oco_side_canonicalization(monkeypatch):
    fsm = ManageFlowFSM(config=build_config(aggregated_enabled=True))
    fsm.position_qty = Decimal("-3")  # Signed qty should imply SHORT
    fsm.position_entry_price = Decimal("50")
    fsm.position_side = None
    fsm._agg_side = None

    canonical = fsm._resolve_canonical_position_side()
    assert canonical == PositionSide.SHORT
    assert fsm._get_opposite_side() == "BUY"

    fsm.position_qty = Decimal("0")
    flat_canonical = fsm._resolve_canonical_position_side()
    assert flat_canonical == PositionSide.FLAT
