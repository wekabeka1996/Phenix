import json
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import jsonschema
import pytest


@pytest.mark.asyncio
async def test_collect_limit_submit_trace_includes_book_context():
    from apps.reference.domains.execution_position.open_executor import OpenExecutor

    fsm = MagicMock()
    fsm.adapter = MagicMock()
    fsm.adapter.get_book_ticker = AsyncMock(
        return_value={"bidPrice": "100.10", "askPrice": "100.30"}
    )
    executor = OpenExecutor(fsm)
    decision = MagicMock(
        rid="RID-TRACE-1",
        pld={},
        data_ref=[
            "obs://execution_position/limit_rounding?before=100.26&after=100.3&tick=0.1&mode=ceil"
        ],
    )

    trace = await executor._collect_limit_submit_trace(
        decision=decision,
        symbol="BTCUSDT",
        side="SELL",
        price=Decimal("100.3"),
        qty=Decimal("0.001"),
        tif="GTX",
    )

    metadata = trace["metadata"]
    assert trace["event_type"] == "ORDER_INTENT"
    assert trace["source_fsm"] == "ExecPosFSM"
    assert metadata["trace_kind"] == "LIMIT_SUBMIT_TRACE"
    assert metadata["price_before_rounding"] == "100.26"
    assert metadata["price_after_rounding"] == "100.3"
    assert metadata["rounding_mode"] == "ceil"
    assert metadata["best_bid"] == "100.10"
    assert metadata["best_ask"] == "100.30"
    assert metadata["spread"] == "0.20"
    assert metadata["distance_to_touch"] == "0.20"

    schema = json.loads(Path("apps/reference/schemas/order_logger_v1.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=trace, schema=schema)


@pytest.mark.asyncio
async def test_collect_limit_submit_trace_fails_closed_without_book_api():
    from apps.reference.domains.execution_position.open_executor import OpenExecutor

    fsm = MagicMock()
    fsm.adapter = object()
    executor = OpenExecutor(fsm)
    decision = MagicMock(rid="RID-TRACE-2", pld={}, data_ref=[])

    trace = await executor._collect_limit_submit_trace(
        decision=decision,
        symbol="BTCUSDT",
        side="BUY",
        price=Decimal("99.9"),
        qty=Decimal("0.001"),
        tif="GTX",
    )

    assert trace["metadata"]["book_context"] == "UNAVAILABLE"
    assert trace["metadata"]["price_after_rounding"] == "99.9"
