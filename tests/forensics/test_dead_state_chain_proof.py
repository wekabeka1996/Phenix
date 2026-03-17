from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.reference.bootstrap.startup_basis_hydrator import (
    execute_startup_basis_hydration,
)
from apps.reference.bootstrap.startup_hydration_planner import (
    HydrationAction,
    StartupHydrationPlanReport,
    StrategyHydrationPlan,
    StrategyHydrationRequirement,
)
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


def _make_handler() -> AuroraHandler:
    config = SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(
                    signal_threshold=0.1,
                    side_bias_window_sec=420,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    direction_strength_scoring=None,
                    signals=None,
                ),
                assets={
                    "BTCUSDT": SimpleNamespace(enabled=True),
                },
            )
        )
    )
    handler = AuroraHandler(
        config=config, emit_fn=lambda *_args, **_kwargs: None)
    # Avoid external profile lookup in tests; keep gate deterministic.
    handler._basis_required_bars_override = 3
    return handler


def test_cmd_process_strategy_missing_tf_sec_rejected_and_counter_not_incremented(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _make_handler()
    rejected: list[dict[str, object]] = []

    def _capture_reject(**kwargs: object) -> None:
        rejected.append(kwargs)

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.aurora_handler.write_trade_intent_rejected",
        _capture_reject,
    )

    cmd = {
        "symbol": "BTCUSDT",
        "bar_close_ts": 1740000000000,
        "features": {"price": 50000.0},
        "warmup": {"full_ready": True, "ready": {}},
    }

    handler.on_process_strategy(cmd)

    assert handler._bars_seen_since_restart.get("BTCUSDT", 0) == 0
    assert len(rejected) == 1
    assert rejected[0]["reason_code"] in {"MISSING_TF_SEC", "NRR-046"}
    assert "missing tf_sec" in str(rejected[0]["why"])


def test_cmd_process_strategy_missing_bar_close_ts_rejected_and_counter_not_incremented(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _make_handler()
    rejected: list[dict[str, object]] = []

    def _capture_reject(**kwargs: object) -> None:
        rejected.append(kwargs)

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.aurora_handler.write_trade_intent_rejected",
        _capture_reject,
    )

    cmd = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "features": {"price": 50000.0},
        "warmup": {"full_ready": True, "ready": {}},
    }

    handler.on_process_strategy(cmd)

    assert handler._bars_seen_since_restart.get("BTCUSDT", 0) == 0
    assert len(rejected) == 1
    assert rejected[0]["reason_code"] in {"DATA_NOT_READY", "NRR-025"}
    assert "missing bar_close_ts" in str(rejected[0]["why"])


def test_cold_start_gate_blocks_until_basis_required_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _make_handler()
    rejected: list[dict[str, object]] = []

    def _capture_reject(**kwargs: object) -> None:
        rejected.append(kwargs)

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.aurora_decision.write_trade_intent_rejected",
        _capture_reject,
    )

    handler.on_regime_detected(
        {
            "symbol": "BTCUSDT",
            "regime": "DEFAULT",
            "confidence": 0.8,
            "ts_ms": 1740000000000,
        }
    )

    base_cmd = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1740000000000,
        "features": {"price": 50000.0},
        "warmup": {"full_ready": True, "ready": {}},
    }

    handler.on_process_strategy(base_cmd)
    handler.on_process_strategy({**base_cmd, "bar_close_ts": 1740000005000})

    assert handler._bars_seen_since_restart["BTCUSDT"] == 2
    assert len(rejected) == 2
    assert all("Cold-start" in str(item.get("why", "")) for item in rejected)


def test_startup_hydration_reports_insufficient_seed_without_import_or_restore() -> None:
    requirement = StrategyHydrationRequirement(
        compatibility_profile_id="test-profile",
        strategy_id="aurora",
        symbol="BTCUSDT",
        basis_tf_sec=300,
        basis_required_bars=10,
    )
    plan = StrategyHydrationPlan(
        strategy_id="aurora",
        symbol="BTCUSDT",
        requirement=requirement,
        actions=(
            HydrationAction(
                action="SEED_HANDLER_BASIS_COUNTER",
                owner="decision_making",
                scope="bars",
                reason="test_chain_proof",
                timeframe_sec=300,
                required_bars=10,
            ),
        ),
    )
    report = StartupHydrationPlanReport(
        updated_at=1740000000000,
        source="test",
        plans={"aurora:BTCUSDT": plan},
    )

    result = execute_startup_basis_hydration(
        hydration_plan=report,
        restore_report=None,
        started_strategy_handlers={"aurora": _make_handler()},
        bar_aggregator=None,
        backfill_adapter=None,
        guardian_runtime=SimpleNamespace(run=lambda *_args, **_kwargs: None),
    )

    assert result["imports"] == {}
    assert result["seeded"] == []
    assert any(
        str(item).startswith("basis_seed_skipped:aurora:BTCUSDT:300")
        for item in result["skipped"]
    )
    assert result["readiness"]
    readiness = result["readiness"][0]
    assert readiness["ready"] is False
    assert str(readiness["block_reason"]).startswith("INSUFFICIENT_SEED:")
