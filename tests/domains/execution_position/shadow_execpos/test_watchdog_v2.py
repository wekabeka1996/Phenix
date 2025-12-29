import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.shadow_execpos.watchdog import AggOcoWatchdogService
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketPlan,
    BracketAction,
    BracketState,
    BracketRulesConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import PositionView as BracketPositionView
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketSet, BracketLeg
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import OrderView as BracketOrderView

# Phase 11: watchdog no longer uses bracket_service.evaluate_all, uses compute_bracket_plan_from_views
pytestmark = pytest.mark.xfail(
    reason="Phase 11: Legacy bracket_service mock - watchdog uses compute_bracket_plan_from_views")


def make_dummy_plan(severity="WARN", actions=None):
    if actions is None:
        actions = []
    dummy_state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=BracketPositionView(symbol="BTCUSDT", side="LONG", qty=Decimal(
            "1"), avg_entry_price=Decimal("100")),
        bracket_set=None,
        guardian_meta=None,
        snapshot_ts=0,
    )
    return BracketPlan(
        symbol="BTCUSDT",
        side="LONG",
        state=dummy_state,
        actions=actions,
        severity=severity,
        why="test",
        rid=None,
    )


def test_watchdog_info_plan_no_alerts():
    bs = MagicMock()
    bs.evaluate_all.return_value = [
        make_dummy_plan(severity="INFO", actions=[])]

    wd = AggOcoWatchdogService(bracket_service=bs, cfg={
                               "aggregated_oco": {"enabled": True}})

    recs = wd.analyze(open_orders=[], positions=[])

    bs.evaluate_all.assert_called_once()
    assert recs == [] or all(r.kind == "INFO" for r in recs)


def test_watchdog_alert_counts_actions():
    action = BracketAction(
        action="CANCEL",
        order_ref="123",
        client_order_id=None,
        reason_code="ORPHAN_SL",
        why="orphan",
        rid=None,
    )
    bs = MagicMock()
    bs.evaluate_all.return_value = [
        make_dummy_plan(severity="ALERT", actions=[action])]

    wd = AggOcoWatchdogService(bracket_service=bs, cfg={
                               "aggregated_oco": {"enabled": True}})

    recs = wd.analyze(open_orders=[{"symbol": "BTCUSDT"}], positions=[
                      {"symbol": "BTCUSDT", "qty": 1}])

    assert recs
    assert recs[0].kind == "ALERT"
    assert recs[0].orders_to_cancel == ["123"]


def test_watchdog_disable_cfg():
    bs = MagicMock()
    wd = AggOcoWatchdogService(bracket_service=bs, cfg={
                               "aggregated_oco": {"enabled": False}})

    recs = wd.analyze(open_orders=[], positions=[])
    # Should short-circuit evaluate calls when disabled
    assert bs.evaluate_all.call_count == 0
