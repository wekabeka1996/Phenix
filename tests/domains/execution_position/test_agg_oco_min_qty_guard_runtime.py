"""Runtime tests for aggregated-only qty guard behaviour (OCO-11.11)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import types
from typing import Any, Dict, List, Optional

import pytest
from vfoundation.core.fsm_emit_compat import Message

from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)
from apps.reference.domains.execution_position.qty_guard import ExecutionQtyGuard


@dataclass
class DummyLevels:
    sl_price: Decimal
    tp_price: Decimal
    why: str = "unit-test"


@pytest.fixture
def aggregated_config() -> Dict[str, Any]:
    return {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "aggregated_oco": {
                            "enabled": True,
                            "aggregated_only_mode": True,
                            "recalc_on_partial_close": True,
                        },
                    },
                }
            }
        }
    }


def _make_guard(profile_overrides: Optional[Dict[str, str]] = None) -> ExecutionQtyGuard:
    profile = {
        "step_size": "0.01",
        "min_qty": "0.01",
        "min_notional": "5",
        "source": "runtime-test",
    }
    if profile_overrides:
        profile.update(profile_overrides)
    return ExecutionQtyGuard(instrument_lookup=lambda symbol: profile)


def _manage_for_test(config: Dict[str, Any], guard: ExecutionQtyGuard) -> ManageFlowFSM:
    fsm = ManageFlowFSM(config=config, symbol="SOLUSDT", qty_guard=guard)
    fsm.state = ManageState.TRACKING
    fsm.position_side = "BUY"
    fsm.position_entry_price = Decimal("100")
    return fsm


def _make_msg() -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="test",
        dst="execution_position",
        rid="agg-guard",
        pld={"symbol": "SOLUSDT", "price": "100"},
    )


def _attach_emit_probe(fsm: ManageFlowFSM) -> List[Dict[str, Any]]:
    emitted: List[Dict[str, Any]] = []

    def _probe(self: ManageFlowFSM, msg: Message, client_id: str, order_type: str, side: str, qty: str, price: str, why: str):  # noqa: ANN001
        payload = {
            "client_id": client_id,
            "order_type": order_type,
            "side": side,
            "qty": qty,
            "price": price,
            "why": why,
        }
        emitted.append(payload)
        return Message(op="DEC", verb="PLACE_ORDER", src="test", dst="execution_position", rid="probe", pld={"symbol": "SOLUSDT", "qty": qty, "side": side})

    fsm._emit_place_order = types.MethodType(
        _probe, fsm)  # type: ignore[assignment]
    return emitted


def test_aggregated_guard_skips_dec_when_qty_under_step(aggregated_config: Dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    guard = _make_guard()
    manage = _manage_for_test(aggregated_config, guard)
    manage.position_qty = Decimal("0.005")
    emitted = _attach_emit_probe(manage)

    caplog.set_level("WARNING", logger="agg_oco")
    msg = _make_msg()
    result = manage._place_or_update_bracket_set_from_levels(
        msg,
        DummyLevels(sl_price=Decimal("95"), tp_price=Decimal("105")),
        reason="unit_reason",
    )

    assert result is None
    assert emitted == []
    assert any(record.message ==
               "AGG_SL_SKIPPED_MIN_QTY" for record in caplog.records)


def test_aggregated_guard_skips_dec_when_notional_below_min(aggregated_config: Dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    guard = _make_guard({"min_notional": "50"})
    manage = _manage_for_test(aggregated_config, guard)
    manage.position_qty = Decimal("0.05")
    emitted = _attach_emit_probe(manage)

    caplog.set_level("WARNING", logger="agg_oco")
    msg = _make_msg()
    result = manage._place_or_update_bracket_set_from_levels(
        msg,
        DummyLevels(sl_price=Decimal("90"), tp_price=Decimal("110")),
        reason="min_notional_fail",
    )

    assert result is None
    assert emitted == []
    assert any(
        record.message == "AGG_SL_SKIPPED_MIN_QTY" and record.name == "agg_oco" for record in caplog.records
    )
