from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.config.domains import decision_making as domain_dm

import calibrators.policy_gates.calibrate_nrr062_historical as calibrator


def _gate_config(**overrides):
    payload = {
        "enabled": True,
        "enforce_in_modes": ["testnet", "hybrid_live_data_testnet_exec"],
        "observe_only_in_modes": ["live", "production"],
        "regimes": ["LOW_VOLATILITY"],
        "fee": {
            "open_fee_bps": 4.0,
            "close_fee_bps": 4.0,
            "fee_source": "explicit_config",
        },
        "slippage": {
            "buffer_bps": 2.0,
            "source": "explicit_config",
        },
        "thresholds": {
            "target_net_fee_multiple": 2.0,
            "min_tp_fee_coverage": 3.0,
            "min_rr": 1.2,
            "min_regime_confidence_by_regime": {
                "DEFAULT": 0.45,
                "LOW_VOLATILITY": 0.39,
            },
            "min_direction_confidence_by_regime": {
                "DEFAULT": 0.55,
                "LOW_VOLATILITY": 0.51,
            },
        },
        "direction_confidence": {
            "required": True,
            "allowed_sources": [
                "strategy_confidence",
                "signal_score",
                "final_score",
                "judge_confidence",
            ],
            "missing_policy": "fail_closed",
        },
        "geometry": {
            "require_tpsl": True,
            "missing_policy": "fail_closed",
        },
    }
    payload.update(overrides)
    return domain_dm.LowVolCostFloorGateConfig.model_validate(payload)


def _make_1m_bar(minute_index: int, *, open_: float, high: float, low: float, close: float) -> calibrator.HistoricalBar:
    open_time_ms = minute_index * 60_000
    return calibrator.HistoricalBar(
        symbol="BTCUSDT",
        tf_sec=60,
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 59_999,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


def test_detect_missing_1m_gaps_and_aggregate_bars() -> None:
    bars = [
        _make_1m_bar(0, open_=100.0, high=101.0, low=99.5, close=100.5),
        _make_1m_bar(1, open_=100.5, high=101.5, low=100.0, close=101.0),
        _make_1m_bar(2, open_=101.0, high=102.0, low=100.8, close=101.8),
        _make_1m_bar(3, open_=101.8, high=102.2, low=101.2, close=101.4),
        _make_1m_bar(4, open_=101.4, high=101.9, low=100.9, close=101.1),
        _make_1m_bar(5, open_=101.1, high=101.6, low=100.7, close=101.3),
    ]

    assert calibrator.detect_missing_1m_gaps(bars) == []

    bars_180 = calibrator.aggregate_1m_bars(bars, 180)
    assert len(bars_180) == 2
    assert bars_180[0].open == 100.0
    assert bars_180[0].close == 101.8
    assert bars_180[0].high == 102.0
    assert bars_180[0].low == 99.5

    bars_300 = calibrator.aggregate_1m_bars(bars, 300)
    assert len(bars_300) == 1
    assert bars_300[0].open == 100.0
    assert bars_300[0].close == 101.1
    assert bars_300[0].high == 102.2
    assert bars_300[0].low == 99.5

    bars_with_gap = bars[:3] + bars[4:]
    gaps = calibrator.detect_missing_1m_gaps(bars_with_gap)
    assert len(gaps) == 1
    assert gaps[0].expected_open_time_ms == 180_000
    assert gaps[0].actual_open_time_ms == 240_000


def test_evaluate_surface_uses_real_low_vol_gate_and_relaxed_rr_changes_result() -> None:
    observation = calibrator.GateObservation(
        symbol="BTCUSDT",
        ts_ms=1_700_000_000_000,
        timestamp_utc="2023-11-14T22:13:20+00:00",
        regime="LOW_VOLATILITY",
        regime_confidence=0.80,
        regime_age_bars=4,
        side="BUY",
        signal_score=0.90,
        threshold_factor=1.0,
        pillar_sum=0.90,
        tactician=0.8,
        operator=0.6,
        strategist=0.1,
        atr=0.25,
        entry_price=100.0,
        stop_price=99.0,
        target_price=100.5,
        entry_plan_confidence=0.90,
        outcome="FILLED_TP",
        exit_price=100.5,
        exit_ts_ms=1_700_000_030_000,
        fill_ts_ms=1_700_000_006_000,
        pnl_pct=0.5,
        r_multiple=0.5,
        bars_held_1m=3,
    )
    base_cfg = _gate_config()
    _, base_metrics = calibrator.evaluate_surface(
        observations=[observation],
        gate_cfg=base_cfg,
        trading_mode="testnet",
    )
    assert base_metrics.allowed_count == 0
    assert base_metrics.blocked_count == 1
    assert base_metrics.blocked_profitable == 1
    assert base_metrics.violation_counts["rr_ratio_below_min"] == 1

    relaxed_cfg = calibrator.mutate_gate_cfg(
        base_cfg,
        calibrator.SurfaceThresholds(
            target_net_fee_multiple=2.0,
            min_tp_fee_coverage=3.0,
            min_rr=0.5,
            low_vol_min_regime_confidence=0.39,
            low_vol_min_direction_confidence=0.51,
        ),
    )
    _, relaxed_metrics = calibrator.evaluate_surface(
        observations=[observation],
        gate_cfg=relaxed_cfg,
        trading_mode="testnet",
    )
    assert relaxed_metrics.allowed_count == 1
    assert relaxed_metrics.blocked_count == 0
    assert relaxed_metrics.allowed_tp_hits == 1


def test_build_gate_observations_for_symbol_uses_shared_strategy_confidence_helper() -> None:
    bar = calibrator.HistoricalBar(
        symbol="BTCUSDT",
        tf_sec=300,
        open_time_ms=0,
        close_time_ms=299_999,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
    )
    fake_entry_plan = SimpleNamespace(
        compute=lambda **kwargs: SimpleNamespace(
            entry_price="100.0",
            stop_loss_price="99.0",
            take_profit_price="101.2",
        )
    )

    with patch.object(
        calibrator,
        "resolve_symbol_decision_contract",
        return_value=calibrator.DecisionContract(
            signal_threshold=0.1,
            neutral_threshold=0.05,
            regime_thresholds={"DEFAULT": 1.0},
            score_multiplier=1.0,
            delta_price_cap_pct=1.0,
            admission_mode="binary",
            admission_power=None,
            sizing_mode="binary",
            sizing_power=None,
            admission_shield_floor=0.0,
            tick_size=None,
            allowed_regimes=("LOW_VOLATILITY",),
        ),
    ), patch.object(
        calibrator,
        "compute_atr_series",
        return_value=[1.0],
    ), patch.object(
        calibrator.QuadraticScoringKernel,
        "compute",
        return_value=SimpleNamespace(
            deferred=False,
            side="buy",
            threshold_factor=0.2,
            score=0.1,
        ),
    ), patch.object(
        calibrator,
        "simulate_limit_path",
        return_value=("FILLED_TP", 101.2, 2, 1, 1.2, 1.2, 1),
    ):
        observations = calibrator.build_gate_observations_for_symbol(
            symbol="BTCUSDT",
            bars_300=[bar],
            bars_1m=[_make_1m_bar(
                0, open_=100.0, high=101.0, low=99.5, close=100.5)],
            regime_by_ts={
                bar.close_time_ms: calibrator.RegimeObservation(
                    symbol="BTCUSDT",
                    ts_ms=bar.close_time_ms,
                    regime="LOW_VOLATILITY",
                    regime_confidence=0.8,
                    regime_age_bars=1,
                )
            },
            pillar_by_ts={
                bar.close_time_ms: calibrator.PillarSnapshot(
                    ts_ms=bar.close_time_ms,
                    tactician=0.1,
                    operator=0.2,
                    strategist=0.3,
                    pillar_sum=0.1,
                )
            },
            decision_cfg={},
            asset_cfg={},
            entry_plan=fake_entry_plan,
            entry_plan_cfg=SimpleNamespace(atr_period=1),
            timeout_bars=1,
        )

    assert len(observations) == 1
    expected_confidence = calibrator.compute_aurora_strategy_confidence(
        score=0.1,
        threshold_factor=0.2,
    )
    assert observations[0].entry_plan_confidence == expected_confidence
    assert observations[0].strategy_confidence == expected_confidence
    assert observations[0].strategy_confidence_side_scope == "BUY"


def test_evaluate_surface_patched_contract_prefers_strategy_confidence() -> None:
    observation = calibrator.GateObservation(
        symbol="BTCUSDT",
        ts_ms=1,
        timestamp_utc="2024-01-01T00:00:00+00:00",
        regime="LOW_VOLATILITY",
        regime_confidence=0.80,
        regime_age_bars=1,
        side="BUY",
        signal_score=0.0041,
        threshold_factor=0.2,
        pillar_sum=0.62,
        tactician=0.1,
        operator=0.1,
        strategist=0.1,
        atr=1.0,
        entry_price=100.0,
        stop_price=99.75,
        target_price=100.30,
        entry_plan_confidence=0.62,
        outcome="FILLED_TP",
        exit_price=100.30,
        exit_ts_ms=2,
        fill_ts_ms=1,
        pnl_pct=0.30,
        r_multiple=1.2,
        bars_held_1m=1,
        signal_score_raw=0.0041,
        strategy_confidence=0.62,
        strategy_confidence_side_scope="BUY",
    )

    legacy_rows, legacy_metrics = calibrator.evaluate_surface(
        observations=[observation],
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        contract_mode=calibrator.LEGACY_DIRECTION_CONTRACT,
    )
    patched_rows, patched_metrics = calibrator.evaluate_surface(
        observations=[observation],
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        contract_mode=calibrator.PATCHED_DIRECTION_CONTRACT,
    )

    assert legacy_metrics.blocked_count == 1
    assert patched_metrics.allowed_count == 1
    assert patched_rows[0]["selected_direction_confidence_source"] == "strategy_confidence"
    assert legacy_rows[0]["selected_direction_confidence_source"] == "signal_score"


def test_select_patch_candidate_prefers_highest_pnl_with_sl_rate_guard() -> None:
    baseline = calibrator.SurfaceEvaluation(
        label="baseline",
        thresholds=calibrator.SurfaceThresholds(2.0, 3.0, 1.2, 0.39, 0.51),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=10,
            allowed_count=4,
            blocked_count=6,
            allowed_tp_hits=2,
            allowed_sl_hits=1,
            allowed_timeout=1,
            allowed_not_filled=0,
            total_allowed_pnl_pct=1.0,
            blocked_profitable=1,
            blocked_outcomes={"FILLED_TP": 1},
            violation_counts={"rr_ratio_below_threshold": 4},
        ),
    )
    guarded_out = calibrator.SurfaceEvaluation(
        label="guarded_out",
        thresholds=calibrator.SurfaceThresholds(2.0, 3.0, 0.8, 0.39, 0.20),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=10,
            allowed_count=6,
            blocked_count=4,
            allowed_tp_hits=3,
            allowed_sl_hits=2,
            allowed_timeout=1,
            allowed_not_filled=0,
            total_allowed_pnl_pct=3.0,
            blocked_profitable=1,
            blocked_outcomes={"FILLED_TP": 1},
            violation_counts={"rr_ratio_below_threshold": 2},
        ),
    )
    lower_threshold = calibrator.SurfaceEvaluation(
        label="lower_threshold",
        thresholds=calibrator.SurfaceThresholds(2.0, 3.0, 0.8, 0.39, 0.10),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=10,
            allowed_count=5,
            blocked_count=5,
            allowed_tp_hits=3,
            allowed_sl_hits=1,
            allowed_timeout=1,
            allowed_not_filled=0,
            total_allowed_pnl_pct=1.8,
            blocked_profitable=1,
            blocked_outcomes={"FILLED_TP": 1},
            violation_counts={"rr_ratio_below_threshold": 2},
        ),
    )
    higher_threshold = calibrator.SurfaceEvaluation(
        label="higher_threshold",
        thresholds=calibrator.SurfaceThresholds(2.0, 3.0, 0.8, 0.39, 0.15),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=10,
            allowed_count=5,
            blocked_count=5,
            allowed_tp_hits=3,
            allowed_sl_hits=1,
            allowed_timeout=1,
            allowed_not_filled=0,
            total_allowed_pnl_pct=1.8,
            blocked_profitable=1,
            blocked_outcomes={"FILLED_TP": 1},
            violation_counts={"rr_ratio_below_threshold": 2},
        ),
    )
    selected, reason = calibrator.select_patch_candidate(
        baseline,
        [guarded_out, lower_threshold, higher_threshold],
    )
    assert selected.label == "higher_threshold"
    assert reason == "candidate_selected:max_allowed_pnl_with_sl_rate_guard"


def test_build_near_dominant_pareto_table_prefers_smallest_regression_frontier() -> None:
    baseline = calibrator.SurfaceEvaluation(
        label="baseline",
        thresholds=calibrator.SurfaceThresholds(2.0, 3.0, 1.2, 0.39, 0.51),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=100,
            allowed_count=50,
            blocked_count=50,
            allowed_tp_hits=10,
            allowed_sl_hits=20,
            allowed_timeout=5,
            allowed_not_filled=2,
            total_allowed_pnl_pct=5.0,
            blocked_profitable=4,
            blocked_outcomes={},
            violation_counts={},
        ),
    )
    almost = calibrator.SurfaceEvaluation(
        label="almost",
        thresholds=calibrator.SurfaceThresholds(2.0, 3.0, 1.0, 0.39, 0.48),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=100,
            allowed_count=53,
            blocked_count=47,
            allowed_tp_hits=12,
            allowed_sl_hits=21,
            allowed_timeout=5,
            allowed_not_filled=2,
            total_allowed_pnl_pct=6.0,
            blocked_profitable=4,
            blocked_outcomes={},
            violation_counts={},
        ),
    )
    dominated = calibrator.SurfaceEvaluation(
        label="dominated",
        thresholds=calibrator.SurfaceThresholds(2.0, 2.5, 1.0, 0.35, 0.48),
        metrics=calibrator.SurfaceMetrics(
            total_candidates=100,
            allowed_count=54,
            blocked_count=46,
            allowed_tp_hits=12,
            allowed_sl_hits=22,
            allowed_timeout=6,
            allowed_not_filled=2,
            total_allowed_pnl_pct=4.0,
            blocked_profitable=5,
            blocked_outcomes={},
            violation_counts={},
        ),
    )

    top_rows, frontier_count, tp_gain_count = calibrator.build_near_dominant_pareto_table(
        baseline,
        [almost, dominated],
    )

    assert tp_gain_count == 2
    assert frontier_count == 1
    assert [row["label"] for row in top_rows] == ["almost"]


def test_build_symbol_month_blocked_breakdown_counts_saved_sl_vs_blocked_tp() -> None:
    rows = [
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1735689600000,
            "gate_block": True,
            "outcome": "FILLED_TP",
        },
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1735776000000,
            "gate_block": True,
            "outcome": "FILLED_SL",
        },
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1735862400000,
            "gate_block": True,
            "outcome": "FILLED_SL",
        },
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1735862400000,
            "gate_block": False,
            "outcome": "FILLED_TP",
        },
    ]

    breakdown = calibrator.build_symbol_month_blocked_breakdown(rows)

    assert breakdown == [
        {
            "symbol": "BTCUSDT",
            "month": "2025-01",
            "blocked_total": 3,
            "blocked_profitable": 1,
            "saved_sl": 2,
            "blocked_timeout": 0,
            "blocked_not_filled": 0,
            "net_saved_sl_minus_blocked_profitable": 1,
        }
    ]


def test_build_direction_blocker_summary_tracks_range_and_joint_violations() -> None:
    rows = [
        {
            "gate_block": True,
            "gate_violations": "direction_confidence_below_threshold",
            "direction_confidence": 0.25,
        },
        {
            "gate_block": True,
            "gate_violations": "direction_confidence_below_threshold|regime_confidence_below_threshold",
            "direction_confidence": 0.12,
        },
        {
            "gate_block": True,
            "gate_violations": "direction_confidence_below_threshold|tp_fee_coverage_below_min",
            "direction_confidence": 0.39,
        },
        {
            "gate_block": False,
            "gate_violations": "",
            "direction_confidence": 0.8,
        },
    ]

    summary = calibrator.build_direction_blocker_summary(rows)

    assert summary["blocked_count"] == 3
    assert summary["sole_direction_count"] == 1
    assert summary["joint_direction_count"] == 2
    assert summary["min_direction_confidence"] == 0.12
    assert summary["max_direction_confidence"] == 0.39
    assert summary["bins"] == {"lt_0.40": 3}
    assert summary["top_joint_violations"][0]["violations"] == "direction_confidence_below_threshold|regime_confidence_below_threshold"


def test_build_unlock_cliff_table_groups_first_unlocking_surface() -> None:
    gate_cfg = _gate_config()
    observations = [
        calibrator.GateObservation(
            symbol="BTCUSDT",
            ts_ms=1,
            timestamp_utc="2024-01-01T00:00:00+00:00",
            regime="LOW_VOLATILITY",
            regime_confidence=0.80,
            regime_age_bars=1,
            side="BUY",
            signal_score=0.49,
            threshold_factor=1.0,
            pillar_sum=0.49,
            tactician=0.1,
            operator=0.1,
            strategist=0.1,
            atr=1.0,
            entry_price=100.0,
            stop_price=99.0,
            target_price=101.3,
            entry_plan_confidence=0.49,
            outcome="FILLED_TP",
            exit_price=101.3,
            exit_ts_ms=2,
            fill_ts_ms=1,
            pnl_pct=1.3,
            r_multiple=1.3,
            bars_held_1m=1,
        ),
        calibrator.GateObservation(
            symbol="BTCUSDT",
            ts_ms=2,
            timestamp_utc="2024-01-01T00:05:00+00:00",
            regime="LOW_VOLATILITY",
            regime_confidence=0.80,
            regime_age_bars=1,
            side="BUY",
            signal_score=0.35,
            threshold_factor=1.0,
            pillar_sum=0.35,
            tactician=0.1,
            operator=0.1,
            strategist=0.1,
            atr=1.0,
            entry_price=100.0,
            stop_price=99.0,
            target_price=100.7,
            entry_plan_confidence=0.35,
            outcome="FILLED_SL",
            exit_price=99.0,
            exit_ts_ms=3,
            fill_ts_ms=2,
            pnl_pct=-1.0,
            r_multiple=-1.0,
            bars_held_1m=1,
        ),
    ]

    rows, summary = calibrator.build_unlock_cliff_table(
        observations=observations,
        gate_cfg=gate_cfg,
        trading_mode="testnet",
    )

    assert summary["blocked_considered"] == 2
    assert summary["unlockable_in_relaxed_grid"] == 2
    assert summary["locked_outside_relaxed_grid"] == 0
    assert rows[0]["low_vol_min_direction_confidence"] == 0.40
    assert rows[0]["newly_unblocked_total"] == 1
    assert rows[0]["newly_unblocked_tp"] == 1
    assert rows[-1]["cumulative_unblocked_total"] == 2
    assert len(rows) == 2


def test_build_raw_unlock_cliff_table_captures_outside_grid_requirements() -> None:
    gate_cfg = _gate_config()
    observations = [
        calibrator.GateObservation(
            symbol="BTCUSDT",
            ts_ms=1,
            timestamp_utc="2024-01-01T00:00:00+00:00",
            regime="LOW_VOLATILITY",
            regime_confidence=0.80,
            regime_age_bars=1,
            side="BUY",
            signal_score=0.35,
            threshold_factor=1.0,
            pillar_sum=0.35,
            tactician=0.1,
            operator=0.1,
            strategist=0.1,
            atr=1.0,
            entry_price=100.0,
            stop_price=99.0,
            target_price=100.7,
            entry_plan_confidence=0.35,
            outcome="FILLED_SL",
            exit_price=99.0,
            exit_ts_ms=3,
            fill_ts_ms=2,
            pnl_pct=-1.0,
            r_multiple=-1.0,
            bars_held_1m=1,
        ),
    ]

    rows, summary = calibrator.build_raw_unlock_cliff_table(
        observations=observations,
        gate_cfg=gate_cfg,
        trading_mode="testnet",
    )

    assert summary["blocked_considered"] == 1
    assert summary["rows_with_raw_unlock_inside_relaxed_grid"] == 1
    assert summary["rows_requiring_thresholds_outside_relaxed_grid"] == 0
    assert rows[0]["within_relaxed_grid"] is True
    assert rows[0]["low_vol_min_direction_confidence"] == 0.35
    assert rows[0]["min_rr"] == 0.7
    assert rows[0]["newly_unblocked_sl"] == 1


def test_build_direction_confidence_sweep_emits_legacy_and_patched_contracts() -> None:
    rows = calibrator.build_direction_confidence_sweep(
        observations=[
            calibrator.GateObservation(
                symbol="BTCUSDT",
                ts_ms=1,
                timestamp_utc="2024-01-01T00:00:00+00:00",
                regime="LOW_VOLATILITY",
                regime_confidence=0.80,
                regime_age_bars=1,
                side="BUY",
                signal_score=0.04,
                threshold_factor=0.2,
                pillar_sum=0.20,
                tactician=0.1,
                operator=0.1,
                strategist=0.1,
                atr=1.0,
                entry_price=100.0,
                stop_price=99.75,
                target_price=100.30,
                entry_plan_confidence=0.20,
                outcome="FILLED_TP",
                exit_price=100.30,
                exit_ts_ms=2,
                fill_ts_ms=1,
                pnl_pct=0.30,
                r_multiple=1.2,
                bars_held_1m=1,
                signal_score_raw=0.04,
                strategy_confidence=0.20,
                strategy_confidence_side_scope="BUY",
            )
        ],
        gate_cfg=_gate_config(),
        trading_mode="testnet",
    )

    contract_modes = {row["contract_mode"] for row in rows}
    assert contract_modes == {
        calibrator.LEGACY_DIRECTION_CONTRACT,
        calibrator.PATCHED_DIRECTION_CONTRACT,
    }
    assert any(
        row["contract_mode"] == calibrator.LEGACY_DIRECTION_CONTRACT
        and row["low_vol_min_direction_confidence"] == 0.051
        for row in rows
    )
    assert any(
        row["contract_mode"] == calibrator.PATCHED_DIRECTION_CONTRACT
        and row["low_vol_min_direction_confidence"] == 0.05
        for row in rows
    )
