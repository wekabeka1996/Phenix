"""Unit tests for aggregated OCO integration inside ManageFlowFSM."""

from __future__ import annotations

import importlib.util
import os
import time
from decimal import Decimal
from typing import Dict, Any

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


def build_config(
    *,
    aggregated_enabled: bool,
    recalc_scale_in: bool = True,
    recalc_partial: bool = False,
    ttl_ms: int = 0,
    allow_unprotected: bool = False,
) -> Dict[str, Any]:
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
                            "recalc_on_scale_in": recalc_scale_in,
                            "recalc_on_partial_close": recalc_partial,
                            "ttl_protect_new_bracket_ms": ttl_ms,
                            "allow_unprotected_position": allow_unprotected,
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


def test_partial_close_recalc_toggle(monkeypatch):
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

    recalc_reasons.clear()
    fsm.config = build_config(aggregated_enabled=True,
                              recalc_partial=False, ttl_ms=0)
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.state = ManageState.BRACKETS_PLACED

    fsm._check_rules(msg)
    assert recalc_reasons == ["partial_close_unprotected"]

    recalc_reasons.clear()
    fsm.sl_order_id = "sl-1"
    fsm.tp_order_id = "tp-1"
    fsm.position_qty = Decimal("1.0")
    fsm._check_rules(msg)
    assert recalc_reasons == []


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
