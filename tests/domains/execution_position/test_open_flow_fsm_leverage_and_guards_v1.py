import asyncio
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

import pytest

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM


@dataclass
class LeverageCheckResult:
    ok: bool
    why: str = ""
    actual_leverage: int | None = None
    actual_margin_mode: str | None = None
    error_code: str | None = None


def _cmd_open(
    *,
    rid: str = "RID-1",
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    qty: str = "0.001",
    price: str | None = "10000",
    order_type: str = "LIMIT",
    price_ref: str | None = None,
    tif: str | None = None,
    valid_for_ms: int | None = None,
    idempotent_key: str | None = None,
) -> Message:
    pld: dict = {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "order_type": order_type,
    }
    if order_type.upper() == "LIMIT":
        pld["tif"] = tif or "GTC"
        pld["valid_for_ms"] = valid_for_ms or 60_000
    else:
        pld["tif"] = None
    if price is not None:
        pld["price"] = price
    if price_ref is not None:
        pld["price_ref"] = price_ref
    if idempotent_key is not None:
        pld["idempotent_key"] = idempotent_key

    return Message(
        op="CMD",
        verb="OPEN",
        src="bridge",
        dst="execution_position",
        rid=rid,
        pld=pld,
    )


def test_openflow_rounds_qty_and_price_by_specs(fsm_config):
    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config)

    # Keep notional above fixture min_notional (5.0) after rounding.
    msg = _cmd_open(qty="0.0014", price="10000.005", order_type="LIMIT")
    dec = fsm.handle(msg)

    assert dec is not None
    assert dec.op == "DEC" and dec.verb == "OPEN"
    assert dec.pld["qty"] == "0.001"
    assert dec.pld["price"] == "10000.00"
    assert "price_before_rounding" not in dec.pld
    assert "price_after_rounding" not in dec.pld
    assert "tick_size" not in dec.pld
    assert "rounding_mode" not in dec.pld
    assert any(
        isinstance(ref, str) and ref.startswith("obs://execution_position/limit_rounding?")
        for ref in dec.data_ref
    )


def test_openflow_rounds_sell_limit_price_up_to_tick(fsm_config):
    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config)

    msg = _cmd_open(side="SELL", qty="0.0014", price="10000.005", order_type="LIMIT")
    dec = fsm.handle(msg)

    assert dec is not None
    assert dec.op == "DEC" and dec.verb == "OPEN"
    assert dec.pld["qty"] == "0.001"
    assert dec.pld["price"] == "10000.01"
    assert "price_before_rounding" not in dec.pld
    assert "price_after_rounding" not in dec.pld
    assert "tick_size" not in dec.pld
    assert "rounding_mode" not in dec.pld
    assert any(
        isinstance(ref, str) and "mode=ceil" in ref
        for ref in dec.data_ref
    )


def test_openflow_rejects_limit_notional_below_min(fsm_config):
    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config)

    # min_notional in fixture = 5.0
    msg = _cmd_open(qty="0.001", price="1000", order_type="LIMIT")  # notional=1
    err = fsm.handle(msg)

    assert err is not None
    assert err.op == "ERR" and err.verb == "OPEN"
    assert err.why == "OPEN_GUARD_FAIL"
    assert "notional" in (err.pld.get("reason") or "")


def test_openflow_rejects_market_estimated_notional_below_min(fsm_config):
    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config)

    msg = _cmd_open(
        qty="0.001",
        price=None,
        order_type="MARKET",
        price_ref="1000",
    )
    err = fsm.handle(msg)

    assert err is not None
    assert err.op == "ERR" and err.verb == "OPEN"
    assert err.why == "OPEN_GUARD_FAIL"
    assert "estimated notional" in (err.pld.get("reason") or "")


def test_openflow_idempotency_rejects_duplicate_cmd_open(fsm_config):
    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config)

    msg1 = _cmd_open(idempotent_key="K-1", qty="0.01", price="1000")
    msg2 = _cmd_open(idempotent_key="K-1", rid="RID-2", qty="0.01", price="1000")

    dec1 = fsm.handle(msg1)
    assert dec1 is not None and dec1.op == "DEC"

    err2 = fsm.handle(msg2)
    assert err2 is not None and err2.op == "ERR"
    assert err2.why == "IDEMPOTENCY_FAIL"


def test_openflow_live_requires_leverage_service():
    with pytest.raises(RuntimeError):
        OpenFlowFSM(is_live_execution=True, leverage_service=None, config=MagicMock())


def test_openflow_handle_async_verify_only_pass_delegates_to_sync(fsm_config):
    btc_spec = fsm_config.instruments.get("BTCUSDT")
    btc_spec.execution = MagicMock()
    btc_spec.execution.leverage_policy = "verify_only"
    btc_spec.execution.target_leverage = 10
    btc_spec.execution.margin_mode = "isolated"

    leverage_service = MagicMock()
    leverage_service.verify = AsyncMock(
        return_value=LeverageCheckResult(
            ok=True,
            why="ok",
            actual_leverage=10,
            actual_margin_mode="isolated",
            error_code=None,
        )
    )

    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config, leverage_service=leverage_service)

    msg = _cmd_open(qty="0.01", price="1000", idempotent_key="K-ASYNC-1")
    out = asyncio.run(fsm.handle_async(msg))

    assert out is not None
    assert out.op == "DEC" and out.verb == "OPEN"
    leverage_service.verify.assert_awaited_once()


def test_openflow_handle_async_verify_only_fail_rejects(fsm_config):
    btc_spec = fsm_config.instruments.get("BTCUSDT")
    btc_spec.execution = MagicMock()
    btc_spec.execution.leverage_policy = "verify_only"
    btc_spec.execution.target_leverage = 10
    btc_spec.execution.margin_mode = "isolated"

    leverage_service = MagicMock()
    leverage_service.verify = AsyncMock(
        return_value=LeverageCheckResult(
            ok=False,
            why="mismatch",
            actual_leverage=20,
            actual_margin_mode="isolated",
            error_code="MISMATCH",
        )
    )

    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config, leverage_service=leverage_service)

    msg = _cmd_open(qty="0.01", price="1000", idempotent_key="K-ASYNC-2")
    out = asyncio.run(fsm.handle_async(msg))

    assert out is not None
    assert out.op == "ERR" and out.verb == "OPEN"
    assert out.why.startswith("LEVERAGE_FAIL:")
    leverage_service.verify.assert_awaited_once()


def test_openflow_handle_async_set_and_verify_calls_set_and_verify(fsm_config):
    btc_spec = fsm_config.instruments.get("BTCUSDT")
    btc_spec.execution = MagicMock()
    btc_spec.execution.leverage_policy = "set_and_verify"
    btc_spec.execution.target_leverage = 12
    btc_spec.execution.margin_mode = "cross"

    leverage_service = MagicMock()
    leverage_service.set_and_verify = AsyncMock(
        return_value=LeverageCheckResult(
            ok=True,
            why="ok",
            actual_leverage=12,
            actual_margin_mode="cross",
            error_code=None,
        )
    )
    leverage_service.verify = AsyncMock()

    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config, leverage_service=leverage_service)

    msg = _cmd_open(qty="0.01", price="1000", idempotent_key="K-ASYNC-3")
    out = asyncio.run(fsm.handle_async(msg))

    assert out is not None
    assert out.op == "DEC" and out.verb == "OPEN"
    leverage_service.set_and_verify.assert_awaited_once()
    leverage_service.verify.assert_not_awaited()
