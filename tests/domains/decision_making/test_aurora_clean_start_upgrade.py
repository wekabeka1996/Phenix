from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

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
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

_TS = 1_700_000_000_000


def _cold_startup_snapshot(
    strategy_id: str = "aurora",
    symbol: str = "BTCUSDT",
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


def _make_handler(enabled_symbols: set[str] | None = None) -> AuroraHandler:
    handler = object.__new__(AuroraHandler)
    handler.logger = logging.getLogger("tests.aurora.clean_start")
    handler.strategy_id = "aurora"
    handler.wall_time_fn = lambda: (_TS + 5000) / 1000.0
    handler._enabled_symbols = enabled_symbols or {"BTCUSDT"}
    handler._analytics_restore_snapshots = {}
    handler._latest_portfolio = None
    return handler


def _portfolio_state(
    positions: list[dict] | None = None,
    ts_ms: int = _TS + 5000,
) -> dict:
    return {
        "ts": ts_ms,
        "equity": "1000.00",
        "equity_free_usdt": "1000.00",
        "available_balance": "1000.00",
        "positions": positions if positions is not None else [],
        "positions_last_ts_ms": ts_ms,
    }


def test_aurora_zero_positions_upgrades_cold_execution_snapshot() -> None:
    handler = _make_handler()
    handler._analytics_restore_snapshots["BTCUSDT"] = _cold_startup_snapshot()

    handler.on_portfolio_state(_portfolio_state())

    snapshot = handler._analytics_restore_snapshots["BTCUSDT"]
    execution_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    assert execution_status is not None
    assert execution_status.state == RuntimeAnalyticsRestoreState.RESTORED
    assert "clean_start_zero_positions_confirmed" in execution_status.why


def test_aurora_clean_start_upgrade_unlocks_open_new_risk() -> None:
    handler = _make_handler()
    handler._analytics_restore_snapshots["BTCUSDT"] = _cold_startup_snapshot()

    handler.on_portfolio_state(_portfolio_state())

    snapshot = handler._analytics_restore_snapshots["BTCUSDT"]
    permissions = combine_restore_permissions_live_first(
        make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=True,
        ),
        snapshot,
    )
    assert permissions.can_open_new_risk is True
    assert permissions.mode == "OPEN_AND_MANAGE"


def test_aurora_non_zero_positions_keep_snapshot_cold() -> None:
    handler = _make_handler()
    handler._analytics_restore_snapshots["BTCUSDT"] = _cold_startup_snapshot()

    handler.on_portfolio_state(
        _portfolio_state(
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "net_position": str(Decimal("0.010")),
                }
            ]
        )
    )

    snapshot = handler._analytics_restore_snapshots["BTCUSDT"]
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


def test_aurora_portfolio_clean_start_resolves_enabled_symbols_from_registry() -> None:
    config = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={"BTCUSDT": ["aurora"]}),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                enabled=True,
                assets={"BTCUSDT": SimpleNamespace(enabled=True)},
            )
        ),
        instruments=None,
    )

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=lambda *_args, **_kwargs: None,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: (_TS + 5000) / 1000.0,
        )

    handler.apply_runtime_analytics_restore_snapshot(_cold_startup_snapshot())
    handler.on_portfolio_state(_portfolio_state())

    snapshot = handler.get_runtime_analytics_restore_snapshot("BTCUSDT")
    execution_status = lookup_restore_status(
        snapshot,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
    )
    assert execution_status is not None
    assert execution_status.state == RuntimeAnalyticsRestoreState.RESTORED
