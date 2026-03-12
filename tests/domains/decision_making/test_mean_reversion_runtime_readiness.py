from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.bootstrap.startup_warmup import (
    activate_startup_warmup_gate,
    release_startup_warmup_gate,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    cold_restore_status,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    build_canonical_bar_identity,
)
from apps.reference.domains.decision_making.mean_reversion_handler import (
    MeanReversionHandler,
)
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignal,
    MRSignalType,
)


class _FSMStub:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))


def _make_handler(restore_snapshot=None) -> tuple[MeanReversionHandler, _FSMStub]:
    handler = object.__new__(MeanReversionHandler)
    fsm = _FSMStub()

    handler.fsm = fsm
    handler.logger = logging.getLogger("tests.mean_reversion.runtime")
    handler.mlog = logging.getLogger("tests.mean_reversion.runtime")
    handler.timeframe_sec = 300
    handler.config = SimpleNamespace(
        domains=SimpleNamespace(objective_engine=SimpleNamespace(enabled=False)),
        strategies=SimpleNamespace(
            mean_reversion=SimpleNamespace(objective=SimpleNamespace(enabled=False))
        ),
    )
    handler._signal_counts = {}
    handler._last_signal_time = {}
    handler._last_cmd_features = {
        "BTCUSDT": {
            "volatility": {"atr_14": 1.0, "atr_ready": True},
            "liquidity": {"obi_close": "0.1"},
        }
    }
    handler._analytics_restore_snapshots = {}
    handler.get_runtime_analytics_restore_snapshot = lambda _symbol: restore_snapshot
    handler._stats = {"signals_emitted": 0}
    handler.seq_counter = 0
    handler._latest_portfolio = None
    handler._latest_exposure_summary = None
    handler._position_queries = None
    handler._objective_blocked_ts_ms = {}
    handler._objective_cancel_replace_ts_ms = {}
    handler._objective_reentry_ts_ms = {}
    handler._strategies = {}
    return handler, fsm


def _signal() -> MRSignal:
    return MRSignal(
        signal_type=MRSignalType.LONG,
        symbol="BTCUSDT",
        price=Decimal("100"),
        atr=Decimal("1"),
        flat_regime=SimpleNamespace(name="FLAT_LOW"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99"),
        target_price=Decimal("101"),
        confidence=Decimal("0.8"),
        timestamp_ms=1_700_000_000_000,
        why="enter:buy",
        bar=SimpleNamespace(end_ts_ms=1_699_999_999_999),
    )


def test_mean_reversion_live_warmup_overrides_cold_restore_snapshot() -> None:
    restore_snapshot = make_strategy_restore_snapshot(
        strategy_id="mean_reversion",
        symbol="BTCUSDT",
        updated_at=1_700_000_000_000,
        scopes={
            RuntimeAnalyticsRestoreScope.EXECUTION_STATE.value: restored_restore_status(
                why=["execution_snapshot_loaded"],
                updated_at=1_700_000_000_000,
                source="execution_position:startup_restore",
                evidence_ref="execution:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE.value: cold_restore_status(
                why=["fe_cache_restore_missing"],
                updated_at=1_700_000_000_000,
                source="feature_engineering:startup_restore",
                evidence_ref="fe_cache:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE.value: cold_restore_status(
                why=["regime_restore_missing"],
                updated_at=1_700_000_000_000,
                source="regime_detector:startup_restore",
                evidence_ref="regime:BTCUSDT:1700000000000",
            ),
            RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value: cold_restore_status(
                why=["strategy_local_restore_missing"],
                updated_at=1_700_000_000_000,
                source="decision_making:startup_restore",
                evidence_ref="strategy_local:BTCUSDT:1700000000000",
            ),
        },
        source="startup:test",
        has_open_position=True,
    )
    handler, fsm = _make_handler(restore_snapshot)
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    with patch(
        "apps.reference.domains.decision_making.mean_reversion_handler.get_clock",
        return_value=SimpleNamespace(now_ms=lambda: 1_700_000_000_000, now_sec=lambda: 1_700_000_000),
    ):
        handler._emit_signal(
            _signal(),
            bar_identity=identity,
            replay_identity=identity.to_replay_identity(),
            warmup_readiness={"full_ready": True},
        )

    _, payload = fsm.emitted[0]
    assert payload["runtime_permissions"]["can_open_new_risk"] is True
    assert payload["runtime_permissions"]["mode"] == "OPEN_AND_MANAGE"
    assert payload["runtime_readiness"]["scopes"]["microstructure_ready"]["state"] == "READY"


def test_mean_reversion_startup_gate_blocks_new_risk_but_preserves_manage() -> None:
    handler, fsm = _make_handler()
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )

    activate_startup_warmup_gate(
        updated_at=1_700_000_000_000,
        source="startup:test",
    )
    try:
        with patch(
            "apps.reference.domains.decision_making.mean_reversion_handler.get_clock",
            return_value=SimpleNamespace(now_ms=lambda: 1_700_000_000_000, now_sec=lambda: 1_700_000_000),
        ):
            handler._emit_signal(
                _signal(),
                bar_identity=identity,
                replay_identity=identity.to_replay_identity(),
                warmup_readiness={"full_ready": True},
            )
    finally:
        release_startup_warmup_gate()

    _, payload = fsm.emitted[0]
    assert payload["runtime_permissions"]["can_manage_existing_risk"] is True
    assert payload["runtime_permissions"]["can_open_new_risk"] is False
    assert "startup_warmup_in_progress" in payload["runtime_readiness"]["blocking_reason_chain"]
