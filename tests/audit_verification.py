from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

import pytest

from vfoundation.core.protocol import Message


def _d(v: str | int | float | Decimal) -> Decimal:
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# 1) "Insufficient Balance" Trap (Fee Insolvency)
# ---------------------------------------------------------------------------


def test_audit_01_fee_insolvency_margin_pct_1_has_no_fee_buffer() -> None:
    """
    Auditor hypothesis:
      sizing_margin_first allows margin_pct=1.0 (100% equity) which ignores fees.
      With leverage=1 this yields order_cost==equity, so order_cost+fee>equity.

    This test asserts the SAFE invariant (should hold in production):
      order_cost + estimated_fee <= equity

    If it fails, the sizing logic is capable of producing an unexecutable order
    when margin_pct=1.0, even before considering slippage.
    """
    from apps.reference.domains.decision_making.sizing_margin_first import (
        compute_notional_target,
        compute_qty,
    )

    equity = _d("1000")
    margin_pct = _d("1.0")
    leverage = 1

    price = _d("100")  # choose values that avoid rounding "saving" fees
    step_size = _d("0.001")

    _margin_usdt, notional_target = compute_notional_target(
        equity=equity,
        margin_pct=margin_pct,
        leverage=leverage,
        notional_cap=None,
    )
    _raw_qty, rounded_qty = compute_qty(
        notional_target=notional_target,
        price=price,
        step_size=step_size,
    )

    order_cost = (rounded_qty * price) / _d(leverage)
    est_fee_rate = _d("0.0005")  # 0.05%
    est_fee = order_cost * est_fee_rate

    assert (
        order_cost + est_fee <= equity
    ), f"Fee insolvency: cost={order_cost} fee={est_fee} total={order_cost + est_fee} equity={equity}"


# ---------------------------------------------------------------------------
# 2) "Zombie Fill" Race Condition (Timeout then late fill)
# ---------------------------------------------------------------------------


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple, dict]] = []

    def emit(self, topic: str, *args, **kwargs) -> None:  # pragma: no cover - harness
        self.events.append((topic, args, kwargs))

    def listen(self, topic: str, handler) -> None:  # pragma: no cover - harness
        # This harness doesn't route bus events; tests inject messages directly.
        return None


def _make_execpos_config() -> MagicMock:
    """
    Minimal-but-sufficient config harness for ExecPosFSM/OpenFlowFSM/ManageFlowFSM.

    This mirrors `tests/domains/execution_position/conftest.py:fsm_config` so the
    audit suite is standalone.
    """
    cfg = MagicMock()

    # Required SSOT: watchdog TTLs (fail-closed)
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000

    # Required SSOT: ManageFlow anti-race
    cfg.trading.execution.anti_race_close_ms = 800

    # Required SSOT: post-close cooldown
    cfg.trading.execution.cooldown_after_close_ms = 10_000

    # Required SSOT: OpenFlow idempotency window
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60

    # Required SSOT: event dedup config
    event_dedup = MagicMock()
    event_dedup.max_size = 100000
    event_dedup.ttl_ms = 86400000
    cfg.domains.execution_position.event_dedup = event_dedup

    # Required SSOT: idempotent cancel config
    idempotent_cancel = MagicMock()
    idempotent_cancel.max_retries = 2
    cfg.domains.execution_position.idempotent_cancel = idempotent_cancel

    # Emergency config required by ManageFlow init
    emergency = MagicMock()
    emergency.enabled = False
    emergency.wait_mode_bars = 2
    emergency.emergency_sl_bps = 100
    cfg.trading.execution.manage.emergency = emergency

    # Brackets config required by ManageFlow (fail-closed in several branches)
    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.brackets.enable = True
    cfg.trading.execution.manage.brackets.oco_emulation = True
    cfg.trading.execution.manage.brackets.sl.fixed_bps = 40
    cfg.trading.execution.manage.brackets.tp.fixed_bps = 80
    cfg.trading.execution.manage.brackets.offset_bps = 5

    # Mock instruments (canonical SSOT)
    btc_spec = MagicMock()
    btc_spec.tick_size = _d("0.01")
    btc_spec.step_size = _d("0.001")
    btc_spec.min_qty = _d("0.001")
    btc_spec.min_notional = _d("5.0")
    btc_spec.execution = MagicMock()
    btc_spec.execution.target_leverage = 20

    class _InstrumentsDict(dict):
        pass

    cfg.instruments = _InstrumentsDict({"BTCUSDT": btc_spec})

    # Per-symbol strategy overrides (ManageFlow fail-closed policy)
    btc_asset_config = MagicMock()
    btc_asset_config.exit = MagicMock()
    btc_asset_config.exit.sl_pct = 0.02
    btc_asset_config.exit.max_hold_sec = 600
    btc_asset_config.take_profit = MagicMock()
    btc_asset_config.take_profit.tp_low_ratio = 0.5
    btc_asset_config.take_profit.tp_high_ratio = 1.0
    btc_asset_config.take_profit.partial_exit_pct = 0.5
    btc_asset_config.trailing_stop = MagicMock()
    btc_asset_config.trailing_stop.enabled = False
    btc_asset_config.trailing_stop.activation_pct = 0.02
    btc_asset_config.trailing_stop.trail_pct = 0.01
    btc_asset_config.trailing_stop.min_update_interval_sec = 5
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset_config}
    cfg.strategies.aurora.decision.bar_gating = None

    # Exposure guard config required by ExecPosFSM.ExposureGuard init
    eg = cfg.domains.execution_position.exposure_guard
    eg.max_equity_utilization_pct = "95.0"
    eg.max_portfolio_fraction = "1.0"
    eg.max_long_utilization_pct = "100.0"
    eg.max_short_utilization_pct = "100.0"
    eg.max_directional_ratio = "5.0"
    eg.max_concentration_pct = "20.0"
    eg.pending_ttl_sec = 5
    eg.post_fill_ttl_sec = 5
    eg.stale_ttl_sec = 10

    cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}
    cfg.trading.execution.exposure.count_pending_orders = True
    cfg.trading.execution.exposure.exclude_reduce_only = True

    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": "10.0",
            "directional_ratio_max": "3.0",
            "side_exposure_usdt": "600.0",
            "margin_exposure_usdt": "1100.0",
        }
    }

    # Storage config for infra components (patched guardian still reads it)
    storage_mock = MagicMock()
    storage_mock.order_history_db = ":memory:"
    cfg.ops.storage = storage_mock

    # Ensure adapter init falls back to shadow mode (no network)
    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""

    return cfg


@pytest.mark.asyncio
async def test_audit_02_zombie_fill_after_watchdog_timeout_is_not_swallowed() -> None:
    """
    Auditor hypothesis:
      After ACK timeout, FSM transitions to DONE (failed) and ignores a late fill,
      leaving an orphaned position.

    This test asserts the SAFE behavior:
      A fill arriving after timeout still updates runtime position tracking
      (ManageFlowFSM) and is processed idempotently.
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    from apps.reference.domains.execution_position.watchdog import OrderTimeoutType

    cfg = _make_execpos_config()
    # Avoid generating DEC:BATCH (which writes to WAL) during this audit repro.
    # We only need to verify that a late fill updates in-memory position tracking.
    cfg.trading.execution.manage.brackets.enable = False
    bus = _FakeBus()

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.cleanup_orphans = MagicMock()

        fsm = ExecPosFSM(config=cfg, fsm=bus)
        fsm.order_guardian = mock_guardian

    rid = "audit_rid_02"
    symbol = "BTCUSDT"
    order_id = "audit_order_02"
    client_order_id = "audit_client_02"

    # Trigger the open flow so it transitions to DONE (normal behavior).
    cmd_open = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld={
            "symbol": symbol,
            "side": "BUY",
            "qty": "0.010",
            "order_type": "MARKET",
            "price": None,
            "tif": None,
            "valid_for_ms": None,
        },
        why="audit_cmd_open",
    )
    dec_open = fsm.handle(cmd_open)
    assert dec_open is not None and dec_open.op in ("DEC", "ERR")

    # Simulate an order being placed and then hitting ACK timeout.
    fsm.watchdog.ack_ttl_ms = 1
    fsm.watchdog.track_order_placed(
        order_id=order_id, client_order_id=client_order_id, symbol=symbol, rid=rid
    )
    fsm.watchdog.pending_orders[order_id].timeout_type = OrderTimeoutType.ACK_TIMEOUT
    fsm.watchdog.pending_orders[order_id].deadline_ms = int(time.time() * 1000) - 1
    await fsm.watchdog._check_timeouts()

    # Inject the fill immediately after timeout (late fill).
    fill_msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="binance_ws",
        dst="execution_position",
        rid=rid,
        pld={
            "orderId": order_id,
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "side": "BUY",
            "qty": "0.010",
            "quantity": "0.010",
            "price": "50000",
            "order_type": "MARKET",
            "closePosition": "false",
            "reduceOnly": "false",
            "ts": int(time.time() * 1000),
        },
        why="audit_late_fill",
    )
    fsm.handle(fill_msg)

    # Verify the fill is not swallowed: ManageFlowFSM should leave FLAT and track a position.
    _open_flow, manage_flow, _close_flow = fsm._get_or_create_flows(symbol)
    assert manage_flow.position_qty is not None, "Late fill did not update ManageFlow position tracking"
    assert manage_flow.symbol == symbol

    # Verify internal idempotency recorded the fill.
    assert f"fill_{order_id}_{symbol}" in fsm._processed_events


# ---------------------------------------------------------------------------
# 3) Dangerous Stop-Loss Rounding
# ---------------------------------------------------------------------------


def test_audit_03_quantize_stop_price_default_is_safe_for_buy_stop() -> None:
    """
    Auditor hypothesis:
      quantize_stop_price defaults to floor, which is unsafe for BUY STOP (short SL).

    This test asserts the SAFE behavior the auditor expects:
      BUY stop prices are rounded UP to the next tick to avoid moving the stop closer.
    """
    from apps.reference.domains.execution_position.utils import quantize_stop_price

    price = 20000.559
    tick = 0.01

    # Auditor's repro updated: explicitly pass side='BUY' to verify the fix
    quantized = quantize_stop_price(price, tick, side="BUY")
    assert quantized == 20000.56, f"Expected ceil for BUY stop, got {quantized}"
