"""Contract tests for aggregated-only execution_position mode (OCO-11.2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Sequence
from unittest.mock import MagicMock

import pytest

from vfoundation.core.protocol import Message

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.services.order_guardian import (
    AggregatedOcoGuardianConfig,
    OrderGuardian,
)
from tests.domains.execution_position.test_aggregated_oco_multi_entry_flow import (
    AggregatedOcoHarness,
    FakeOrder,
    FakeOrderAdapter,
    _build_aggregated_cfg,
)

INLINE_PROTECTION_KEYS = {
    "tp_price",
    "sl_price",
    "stopLoss",
    "takeProfit",
    "ocoOrder",
    "attachedOrders",
}


@pytest.fixture
def execpos_aggregated(monkeypatch: pytest.MonkeyPatch) -> execpos_mod.ExecPosFSM:
    """ExecPosFSM configured for aggregated-only mode with patched dependencies."""

    stub_adapter = MagicMock()
    stub_adapter.base_url = "https://stub"
    stub_guardian = MagicMock()
    stub_watchdog = MagicMock()

    monkeypatch.setattr(execpos_mod, "BinanceAdapter",
                        lambda *a, **k: stub_adapter)
    monkeypatch.setattr(execpos_mod, "OrderGuardian",
                        lambda *a, **k: stub_guardian)
    monkeypatch.setattr(execpos_mod, "OrderTimeoutWatchdog",
                        lambda *a, **k: stub_watchdog)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_fsm_cleanup_loop", lambda self: None)

    config = _build_execpos_config()
    return execpos_mod.ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)


@pytest.fixture
def aggregated_cfg() -> Dict[str, object]:
    return _build_aggregated_cfg()


@pytest.fixture
def aggregated_harness(aggregated_cfg: Dict[str, object]) -> AggregatedOcoHarness:
    return AggregatedOcoHarness(symbol="BTCUSDT", aggregated_cfg=aggregated_cfg)


def _build_execpos_config() -> Dict[str, object]:
    return {
        "trading": {
            "execution": {
                "cooldown_ms": 0,
                "guard_enabled": False,
                "exposure": {},
                "manage": {
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "keep_single_bracket_set": True,
                        "sl": {"fixed_bps": 50},
                        "tp": {"fixed_bps": 100},
                        "aggregated_oco": _build_aggregated_cfg(),
                    },
                },
            },
            "instruments": {
                "BTCUSDT": {
                    "min_qty": 0.001,
                    "step_size": 0.001,
                    "tick_size": 0.01,
                    "min_notional": 5.0,
                }
            },
        }
    }


def _assert_no_inline_tp_sl(payload: Dict[str, object]) -> None:
    for key in INLINE_PROTECTION_KEYS:
        assert key not in payload, f"expected aggregated-only payload to omit {key}"


def _assert_active_sl(orders: Sequence[FakeOrder], *, expected_side: str, expected_qty: Decimal) -> None:
    sl_orders = [
        order for order in orders if order.order_type == "STOP_MARKET"]
    assert sl_orders, "aggregated-only mode must install at least one SL order"
    for sl in sl_orders:
        assert sl.side == expected_side
        assert sl.reduce_only and sl.close_position
        assert sl.qty == expected_qty


def test_entry_orders_have_no_inline_tp_sl_in_aggregated_mode(
    execpos_aggregated: execpos_mod.ExecPosFSM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "order_type": "MARKET",
            "price_ref": "42000",
        },
    )

    monkeypatch.setattr(
        execpos_aggregated.exposure_guard,
        "can_open",
        lambda *a, **k: {"allowed": True, "reason": None},
    )
    monkeypatch.setattr(execpos_aggregated.exposure_guard,
                        "reserve", lambda *a, **k: None)
    decision = execpos_aggregated.handle(cmd)

    assert decision is not None and decision.verb == "OPEN"
    payload = decision.pld or {}
    _assert_no_inline_tp_sl(payload)
    assert payload.get("reduceOnly") is not True
    assert not payload.get("closePosition")


def test_exit_orders_do_not_carry_inline_tp_sl(execpos_aggregated: execpos_mod.ExecPosFSM) -> None:
    _, _, close_flow = execpos_aggregated._get_or_create_flows("BTCUSDT")
    close_flow.position_active = True
    close_flow.state = execpos_mod.CloseState.OPENED

    cmd = Message(
        op="CMD",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        pld={"symbol": "BTCUSDT"},
    )

    decision = execpos_aggregated.handle(cmd)

    assert decision is not None and decision.verb == "CLOSE"
    payload = decision.pld or {}
    _assert_no_inline_tp_sl(payload)
    reduce_only_flag = payload.get("reduceOnly") or payload.get("reduce_only")
    close_flag = payload.get("closePosition") or payload.get("close_position")
    assert reduce_only_flag or close_flag


@pytest.mark.integration
def test_open_creates_single_bracket_set_for_positive_position(aggregated_harness: AggregatedOcoHarness) -> None:
    harness = aggregated_harness
    harness.open_entry("0.002")

    assert harness.position_qty == Decimal("0.002")
    meta = harness.guardian_meta()
    assert meta is not None
    assert meta.symbol == harness.symbol

    all_meta = [m for m in harness.guardian.list_all_bracket_sets()
                if m.symbol == harness.symbol]
    assert len(
        all_meta) == 1, "only one BracketSetMeta should exist per symbol/side"

    orders = harness.current_orders()
    _assert_active_sl(orders, expected_side=harness.exit_side,
                      expected_qty=harness.position_qty)


@pytest.mark.integration
def test_scale_in_replaces_bracket_set_and_preserves_sl_coverage(aggregated_harness: AggregatedOcoHarness) -> None:
    harness = aggregated_harness
    harness.open_entry("0.001")
    first_meta = harness.guardian_meta()
    assert first_meta is not None
    first_sl_ids = {order.order_id for order in harness.current_orders(
    ) if order.order_type == "STOP_MARKET"}

    harness.open_entry("0.001")
    second_meta = harness.guardian_meta()
    assert second_meta is not None
    assert second_meta.version == first_meta.version + 1

    second_sl_ids = {order.order_id for order in harness.current_orders(
    ) if order.order_type == "STOP_MARKET"}
    assert first_sl_ids.isdisjoint(
        second_sl_ids), "scale-in should rotate SL orders"
    _assert_active_sl(
        harness.current_orders(),
        expected_side=harness.exit_side,
        expected_qty=harness.position_qty,
    )


@pytest.mark.integration
def test_partial_close_keeps_or_rebuilds_sl_without_new_entry(aggregated_harness: AggregatedOcoHarness) -> None:
    harness = aggregated_harness
    harness.open_entry("0.003")
    base_meta = harness.guardian_meta()
    assert base_meta is not None

    harness.partial_close("0.001")

    assert harness.position_qty == Decimal("0.002")
    updated_meta = harness.guardian_meta()
    assert updated_meta is not None
    assert updated_meta.version >= base_meta.version
    _assert_active_sl(
        harness.current_orders(),
        expected_side=harness.exit_side,
        expected_qty=harness.position_qty,
    )


@pytest.mark.integration
def test_partial_close_rebuilds_brackets_based_on_position_snapshot(aggregated_harness: AggregatedOcoHarness) -> None:
    harness = aggregated_harness
    harness.open_entry("0.004")
    base_meta = harness.guardian_meta()
    assert base_meta is not None

    harness.partial_close("0.001", final_position_qty=Decimal("0.0015"))

    assert harness.position_qty == Decimal("0.0015")
    updated_meta = harness.guardian_meta()
    assert updated_meta is not None
    assert updated_meta.version >= base_meta.version + 1
    _assert_active_sl(
        harness.current_orders(),
        expected_side=harness.exit_side,
        expected_qty=harness.position_qty,
    )


@pytest.mark.integration
def test_scale_in_and_partial_close_share_same_recalc_path(aggregated_harness: AggregatedOcoHarness) -> None:
    harness = aggregated_harness
    harness.open_entry("0.001")
    first_meta = harness.guardian_meta()
    assert first_meta is not None

    harness.open_entry("0.0007")
    second_meta = harness.guardian_meta()
    assert second_meta is not None
    assert second_meta.version == first_meta.version + 1

    harness.partial_close("0.0004", final_position_qty=Decimal("0.0011"))
    third_meta = harness.guardian_meta()
    assert third_meta is not None
    assert third_meta.version == second_meta.version + 1

    metas = [
        meta for meta in harness.guardian.list_all_bracket_sets()
        if meta.symbol == harness.symbol
    ]
    assert len(metas) == 1, "aggregated-only mode must keep a single bracket set"
    _assert_active_sl(
        harness.current_orders(),
        expected_side=harness.exit_side,
        expected_qty=Decimal("0.0011"),
    )


@pytest.mark.integration
def test_full_close_clears_brackets_and_reduce_only_orders(aggregated_harness: AggregatedOcoHarness) -> None:
    harness = aggregated_harness
    harness.open_entry("0.002")

    harness.full_close()

    assert harness.position_qty == Decimal("0")
    assert harness.current_orders() == []
    assert harness.guardian_meta() is None
    assert not [m for m in harness.guardian.list_all_bracket_sets()
                if m.symbol == harness.symbol]


@pytest.mark.integration
def test_flip_side_removes_old_bracket_set_before_new_side(aggregated_cfg: Dict[str, object]) -> None:
    adapter = FakeOrderAdapter()
    guardian_cfg = AggregatedOcoGuardianConfig(
        enabled=True, ttl_protect_new_bracket_ms=0, allow_unprotected_position=False)
    guardian = OrderGuardian(
        adapter=adapter, poll_interval_ms=0, aggregated_oco_cfg=guardian_cfg)

    long_harness = AggregatedOcoHarness(
        symbol="ADAUSDT",
        entry_side="BUY",
        aggregated_cfg=aggregated_cfg,
        adapter=adapter,
        guardian=guardian,
    )
    short_harness = AggregatedOcoHarness(
        symbol="ADAUSDT",
        entry_side="SELL",
        aggregated_cfg=aggregated_cfg,
        adapter=adapter,
        guardian=guardian,
    )

    long_harness.open_entry("0.004")
    assert guardian.get_active_bracket_set("ADAUSDT", "LONG") is not None

    long_harness.full_close()
    assert guardian.get_active_bracket_set("ADAUSDT", "LONG") is None

    short_harness.open_entry("0.004")
    short_meta = guardian.get_active_bracket_set("ADAUSDT", "SHORT")
    assert short_meta is not None
    assert guardian.get_active_bracket_set("ADAUSDT", "LONG") is None

    short_orders = [order for order in adapter.snapshot_for_symbol("ADAUSDT")]
    assert all(order.position_side == "SHORT" for order in short_orders)
    _assert_active_sl(short_orders, expected_side=short_harness.exit_side,
                      expected_qty=short_harness.position_qty)
