import asyncio
import time
from decimal import Decimal

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from tests.domains.execution_position.shadow_execpos.fakes import FakeExecutionAdapter


def _minimal_config() -> dict:
    return {
        "execution_position": {
            "aggregated_oco": {
                "enabled": True,
                "allow_unprotected_position": False,
                "recalc_on_partial_close": True,
                "recalc_on_scale_in": True,
                "ttl_protect_new_bracket_ms": 5000,
                "max_tp_legs": 1,
                "max_sl_legs": 1,
                "sl_pct": 0.02,
                "tp_rr": 2.0,
            },
            "trailing": {
                "enabled": False,
            },
            "close": {
                "allow_time_exit": True,
                "max_hold_time_sec": 0,
            },
        }
    }


@pytest.mark.asyncio
async def test_runtime_smoke_open_fill_brackets():
    adapter = FakeExecutionAdapter()
    runtime = ExecPosRuntimeV2(config=_minimal_config(), adapter=adapter, price_service=None)

    # entry intent
    await runtime.handle(
        RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={"side": "BUY", "quantity": 0.01, "order_type": "MARKET"},
        )
    )

    # simulate fill
    await runtime.handle(
        RuntimeEvent(
            kind="TRADE_EXECUTED",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={"side": "BUY", "qty": 0.01, "price": "30000"},
        )
    )

    # brackets should place SL/TP via adapter
    assert any(o["type"] in ("STOP_MARKET", "TAKE_PROFIT_MARKET") for o in adapter.placed_orders)


@pytest.mark.asyncio
async def test_bracket_recovery_cancels_orphans():
    adapter = FakeExecutionAdapter()
    runtime = ExecPosRuntimeV2(config=_minimal_config(), adapter=adapter, price_service=None)

    # Patch bracket_service to emit a plan with orphan cancels
    from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
        BracketAction,
        BracketPlan,
    )

    def fake_evaluate_all(*args, **kwargs):
        state = type("S", (), {"is_flat": True})()
        return [
            BracketPlan(
                symbol="BTCUSDT",
                side="LONG",
                state=state,
                actions=[
                    BracketAction(
                        action_type="CANCEL",
                        order_id="sl1",
                        client_order_id="",
                        price=None,
                        qty=None,
                        reason_code="ORPHAN",
                        why="orphan",
                        rid="test",
                    ),
                    BracketAction(
                        action_type="CANCEL",
                        order_id="tp1",
                        client_order_id="",
                        price=None,
                        qty=None,
                        reason_code="ORPHAN",
                        why="orphan",
                        rid="test",
                    ),
                ],
                severity="ALERT",
                why="orphan",
                rid="test",
            )
        ]

    runtime.bracket_service.evaluate_all = fake_evaluate_all  # type: ignore

    await runtime._run_bracket_recovery_pass()

    cancelled_ids = {c["order_id"] for c in adapter.cancelled_orders}
    assert {"sl1", "tp1"} <= cancelled_ids
