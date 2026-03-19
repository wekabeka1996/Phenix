from __future__ import annotations

import logging
from decimal import Decimal

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    RuntimeAnalyticsRestoreState,
    StrategyAnalyticsRestoreSnapshot,
    cold_restore_status,
    combine_restore_permissions_live_first,
    lookup_restore_status,
    make_strategy_restore_snapshot,
)
from apps.reference.contracts.runtime_readiness import make_permissions
from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler
from vfoundation.core.protocol import Message

_TS = 1_700_000_000_000


def _cold_startup_snapshot(
    strategy_id: str = "md_amr",
    symbol: str = "BNBUSDT",
) -> StrategyAnalyticsRestoreSnapshot:
    scopes = {
        scope.value: cold_restore_status(
            why=[f"{scope.value}_restore_missing"],
            updated_at=_TS,
            source="startup:test",
            evidence_ref=f"{scope.value}:{symbol}:{_TS}",
        )
        for scope in RuntimeAnalyticsRestoreScope
    }
    return make_strategy_restore_snapshot(
        strategy_id=strategy_id,
        symbol=symbol,
        updated_at=_TS,
        scopes=scopes,
        source="startup:test",
        has_open_position=False,
    )


def _make_handler(enabled_symbols: set[str] | None = None) -> MDAMRHandler:
    handler = object.__new__(MDAMRHandler)
    handler.logger = logging.getLogger("tests.md_amr.clean_start")
    handler.mlog = logging.getLogger("tests.md_amr.clean_start")
    handler._enabled_symbols = enabled_symbols or {"BNBUSDT"}
    handler._analytics_restore_snapshots = {}
    handler._latest_portfolio = None
    return handler


def _portfolio_event(
    positions: list[dict] | None = None,
    ts_ms: int = _TS + 5000,
) -> Message:
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="any",
        pld={
            "ts": ts_ms,
            "equity": "1000.00",
            "equity_free_usdt": "1000.00",
            "available_balance": "1000.00",
            "positions": positions if positions is not None else [],
            "positions_last_ts_ms": ts_ms,
        },
    )


def test_md_amr_zero_positions_upgrades_cold_execution_snapshot() -> None:
    handler = _make_handler()
    handler._analytics_restore_snapshots["BNBUSDT"] = _cold_startup_snapshot()

    handler._on_portfolio_state_updated(_portfolio_event())

    snapshot = handler._analytics_restore_snapshots["BNBUSDT"]
    execution_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    assert execution_status is not None
    assert execution_status.state == RuntimeAnalyticsRestoreState.RESTORED
    assert "clean_start_zero_positions_confirmed" in execution_status.why


def test_md_amr_clean_start_upgrade_unlocks_open_new_risk() -> None:
    handler = _make_handler()
    handler._analytics_restore_snapshots["BNBUSDT"] = _cold_startup_snapshot()

    handler._on_portfolio_state_updated(_portfolio_event())

    snapshot = handler._analytics_restore_snapshots["BNBUSDT"]
    permissions = combine_restore_permissions_live_first(
        make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=True,
        ),
        snapshot,
    )
    assert permissions.can_open_new_risk is True
    assert permissions.mode == "OPEN_AND_MANAGE"


def test_md_amr_non_zero_positions_keep_snapshot_cold() -> None:
    handler = _make_handler()
    handler._analytics_restore_snapshots["BNBUSDT"] = _cold_startup_snapshot()

    handler._on_portfolio_state_updated(
        _portfolio_event(
            positions=[
                {
                    "symbol": "BNBUSDT",
                    "net_position": str(Decimal("1.5")),
                }
            ]
        )
    )

    snapshot = handler._analytics_restore_snapshots["BNBUSDT"]
    execution_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    assert execution_status is not None
    assert execution_status.state == RuntimeAnalyticsRestoreState.COLD

    permissions = combine_restore_permissions_live_first(
        make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=True,
        ),
        snapshot,
    )
    assert permissions.can_open_new_risk is False
    assert permissions.mode == "PROTECT_ONLY"
