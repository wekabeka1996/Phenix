"""
Handler-level integration tests for clean-start execution restore upgrade.

Validates that MeanReversionHandler correctly processes EVT:PORTFOLIO_STATE_UPDATED
(canonical position-tracking state) and upgrades COLD execution restore snapshots
when reconciled positions confirm zero open quantities for managed symbols.

EVT:PORTFOLIO_STATE_UPDATED is emitted by PositionTracking *after* reconciliation,
so its `positions` field is the authoritative snapshot — unlike
EVT:ACCOUNT_UPDATE_RECEIVED which may carry a partial WebSocket delta.

These tests complement the contract-level tests in
  test_clean_start_execution_restore_upgrade.py
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    RuntimeAnalyticsRestoreState,
    StrategyAnalyticsRestoreSnapshot,
    cold_restore_status,
    combine_restore_permissions_live_first,
    lookup_restore_status,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.runtime_readiness import make_permissions
from apps.reference.domains.decision_making.mean_reversion_handler import (
    MeanReversionHandler,
)
from vfoundation.core.protocol import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = 1_700_000_000_000


def _cold_startup_snapshot(
    strategy_id: str = "mean_reversion",
    symbol: str = "DOGEUSDT",
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


def _make_handler(
    enabled_symbols: set[str] | None = None,
) -> MeanReversionHandler:
    """Build a MeanReversionHandler stub via __new__ (same pattern as existing tests)."""
    handler = object.__new__(MeanReversionHandler)
    handler.fsm = SimpleNamespace(
        emit=lambda *a, **kw: None,
        listen=lambda *a, **kw: None,
    )
    handler.logger = logging.getLogger("tests.mr.clean_start")
    handler.mlog = logging.getLogger("tests.mr.clean_start")
    handler._enabled = True
    handler._enabled_symbols = enabled_symbols or {"DOGEUSDT"}
    handler._analytics_restore_snapshots = {}
    handler._position_qty = {}
    handler._signal_counts = {}
    handler._last_signal_time = {}
    handler._last_cmd_features = {}
    handler._stats = {"signals_emitted": 0}
    handler.seq_counter = 0
    handler._latest_portfolio = None
    handler._latest_exposure_summary = None
    handler._position_queries = None
    handler._objective_blocked_ts_ms = {}
    handler._objective_cancel_replace_ts_ms = {}
    handler._objective_reentry_ts_ms = {}
    handler._strategies = {}
    handler._last_block_reason = {}
    handler._last_block_ts_ms = {}
    handler.timeframe_sec = 60
    handler.config = SimpleNamespace(
        domains=SimpleNamespace(
            objective_engine=SimpleNamespace(enabled=False)),
        strategies=SimpleNamespace(
            mean_reversion=SimpleNamespace(
                objective=SimpleNamespace(enabled=False))
        ),
    )
    return handler


def _portfolio_state_message(
    positions: list[dict[str, Any]] | None = None,
    ts_ms: int = _TS + 5000,
) -> Message:
    """Build a minimal EVT:PORTFOLIO_STATE_UPDATED message (canonical state)."""
    pld = {
        "ts": ts_ms,
        "equity": "1000.00",
        "equity_free_usdt": "1000.00",
        "realized_pnl": "0.00",
        "unrealized_pnl": "0.00",
        "available_balance": "1000.00",
        "positions": positions if positions is not None else [],
        "open_positions_usd": "0.00",
        "open_positions_margin_usd": "0.00",
        "positions_by_side": {"long_margin": "0.00", "short_margin": "0.00"},
        "positions_last_ts_ms": ts_ms,
    }
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="any",
        pld=pld,
    )


# ---------------------------------------------------------------------------
# TEST 1 — handler clean start unlock
# ---------------------------------------------------------------------------

class TestHandlerCleanStartUnlock:

    def test_portfolio_state_zero_positions_upgrades_cold_snapshot(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        # Verify before: COLD execution, PROTECT_ONLY
        snap_before = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_before = lookup_restore_status(
            snap_before, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_before is not None
        assert exec_before.state == RuntimeAnalyticsRestoreState.COLD

        # Deliver canonical portfolio state with empty positions
        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(positions=[], ts_ms=_TS + 5000)
        )

        # Verify after: RESTORED execution
        snap_after = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_after = lookup_restore_status(
            snap_after, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_after is not None
        assert exec_after.state == RuntimeAnalyticsRestoreState.RESTORED
        assert "clean_start_zero_positions_confirmed" in exec_after.why

    def test_after_upgrade_permissions_allow_open_new_risk(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(positions=[], ts_ms=_TS + 5000)
        )

        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        base = make_permissions(
            can_manage_existing_risk=True, can_open_new_risk=True)
        result = combine_restore_permissions_live_first(base, snap)
        assert result.can_open_new_risk is True
        assert result.mode == "OPEN_AND_MANAGE"


# ---------------------------------------------------------------------------
# TEST 2 — non-empty positions: no upgrade
# ---------------------------------------------------------------------------

class TestHandlerNonEmptyPositionsNoUpgrade:

    def test_portfolio_with_open_position_does_not_upgrade(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(
                positions=[
                    {
                        "symbol": "DOGEUSDT",
                        "net_position": "100.0",
                        "avg_entry_price": "0.15",
                        "venues": ["binance"],
                    }
                ],
                ts_ms=_TS + 5000,
            )
        )

        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_status = lookup_restore_status(
            snap, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_status is not None
        assert exec_status.state == RuntimeAnalyticsRestoreState.COLD

        base = make_permissions(
            can_manage_existing_risk=True, can_open_new_risk=True)
        result = combine_restore_permissions_live_first(base, snap)
        assert result.can_open_new_risk is False
        assert result.mode == "PROTECT_ONLY"


# ---------------------------------------------------------------------------
# TEST 3 — no account confirmation: remains protected
# ---------------------------------------------------------------------------

class TestHandlerNoAccountConfirmation:

    def test_without_portfolio_update_snapshot_remains_cold(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        # No portfolio update delivered
        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_status = lookup_restore_status(
            snap, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_status is not None
        assert exec_status.state == RuntimeAnalyticsRestoreState.COLD

    def test_missing_positions_payload_does_not_upgrade(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        # Portfolio update WITHOUT positions key
        bad_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="any",
            pld={
                "ts": _TS + 5000,
                "equity": "1000.00",
                "positions_last_ts_ms": _TS + 5000,
                # NOTE: no "positions" key
            },
        )
        handler._on_portfolio_clean_start_check(bad_msg)

        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_status = lookup_restore_status(
            snap, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_status.state == RuntimeAnalyticsRestoreState.COLD


# ---------------------------------------------------------------------------
# TEST 4 — gateway semantics: before/after upgrade
# ---------------------------------------------------------------------------

class TestGatewaySemantics:
    """Verify the full chain: handler snapshot upgrade → permissions change."""

    def test_signal_permissions_flip_from_protect_only_to_open_and_manage(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        # Before: PROTECT_ONLY
        snap_before = handler.get_runtime_analytics_restore_snapshot(
            "DOGEUSDT")
        base = make_permissions(
            can_manage_existing_risk=True, can_open_new_risk=True)
        perm_before = combine_restore_permissions_live_first(base, snap_before)
        assert perm_before.mode == "PROTECT_ONLY"

        # Canonical portfolio state with zero positions
        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(positions=[], ts_ms=_TS + 5000)
        )

        # After: OPEN_AND_MANAGE
        snap_after = handler.get_runtime_analytics_restore_snapshot("DOGEUSDT")
        perm_after = combine_restore_permissions_live_first(base, snap_after)
        assert perm_after.mode == "OPEN_AND_MANAGE"
        assert perm_after.can_open_new_risk is True


# ---------------------------------------------------------------------------
# TEST 5 — idempotency at handler level
# ---------------------------------------------------------------------------

class TestHandlerIdempotency:

    def test_repeated_empty_portfolio_updates_are_safe(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        # First update: upgrades
        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(positions=[], ts_ms=_TS + 5000)
        )
        snap1 = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec1 = lookup_restore_status(
            snap1, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec1.state == RuntimeAnalyticsRestoreState.RESTORED

        # Second update: no destructive rewrite (snapshot stays RESTORED)
        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(positions=[], ts_ms=_TS + 10000)
        )
        snap2 = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec2 = lookup_restore_status(
            snap2, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec2.state == RuntimeAnalyticsRestoreState.RESTORED

        # Snapshot object stable (second call didn't recreate if idempotent)
        assert snap1 is snap2

    def test_permissions_remain_stable_after_repeated_updates(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )
        base = make_permissions(
            can_manage_existing_risk=True, can_open_new_risk=True)

        # Three updates
        for ts_offset in [5000, 10000, 15000]:
            handler._on_portfolio_clean_start_check(
                _portfolio_state_message(
                    positions=[], ts_ms=_TS + ts_offset)
            )

        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        result = combine_restore_permissions_live_first(base, snap)
        assert result.can_open_new_risk is True
        assert result.mode == "OPEN_AND_MANAGE"


# ---------------------------------------------------------------------------
# TEST 6 — no false unlock on invalid / malformed payloads
# ---------------------------------------------------------------------------

class TestNoFalseUnlockOnInvalidPayload:

    def test_none_pld_does_not_upgrade(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        handler._on_portfolio_clean_start_check(
            Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED",
                    src="position_tracking", dst="any", pld={})
        )

        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_status = lookup_restore_status(
            snap, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_status.state == RuntimeAnalyticsRestoreState.COLD

    def test_positions_not_list_does_not_upgrade(self) -> None:
        handler = _make_handler(enabled_symbols={"DOGEUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
        )

        handler._on_portfolio_clean_start_check(
            Message(
                op="EVT",
                verb="PORTFOLIO_STATE_UPDATED",
                src="position_tracking",
                dst="any",
                pld={"positions": "bad", "positions_last_ts_ms": _TS + 5000},
            )
        )

        snap = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_status = lookup_restore_status(
            snap, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_status.state == RuntimeAnalyticsRestoreState.COLD

    def test_multi_symbol_only_upgrades_zero_position_symbols(self) -> None:
        """With multiple managed symbols, only upgrade the ones with zero positions."""
        handler = _make_handler(enabled_symbols={"DOGEUSDT", "BTCUSDT"})
        handler._analytics_restore_snapshots["DOGEUSDT"] = _cold_startup_snapshot(
            symbol="DOGEUSDT"
        )
        handler._analytics_restore_snapshots["BTCUSDT"] = _cold_startup_snapshot(
            symbol="BTCUSDT"
        )

        handler._on_portfolio_clean_start_check(
            _portfolio_state_message(
                positions=[
                    {
                        "symbol": "BTCUSDT",
                        "net_position": "0.5",
                        "avg_entry_price": "30000",
                        "venues": ["binance"],
                    }
                ],
                ts_ms=_TS + 5000,
            )
        )

        # DOGEUSDT should upgrade (not in active positions)
        snap_doge = handler._analytics_restore_snapshots["DOGEUSDT"]
        exec_doge = lookup_restore_status(
            snap_doge, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_doge.state == RuntimeAnalyticsRestoreState.RESTORED

        # BTCUSDT should NOT upgrade (has open position)
        snap_btc = handler._analytics_restore_snapshots["BTCUSDT"]
        exec_btc = lookup_restore_status(
            snap_btc, RuntimeAnalyticsRestoreScope.EXECUTION_STATE
        )
        assert exec_btc.state == RuntimeAnalyticsRestoreState.COLD
