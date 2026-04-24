from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.strategy_compatibility_matrix import (
    build_active_strategy_compatibility_profiles,
)
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler
from apps.reference.domains.feature_engineering.md_amr_strategy import (
    MDAMRSignal,
    MDAMRStrategyV11,
)


class _FSMStub:
    def __init__(self) -> None:
        self.listeners: list[tuple[str, object]] = []
        self.emitted: list[tuple[str, dict, str | None, object]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.append((event, handler))

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
    ) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))

    def get_domain(self, _name: str):
        return None


def _make_config(symbol: str = "BNBUSDT"):
    asset_cfg = SimpleNamespace(
        enabled=True,
        cooldown_sec=60,
        allowed_regimes=[
            "MEAN_REVERSION",
            "LOW_VOLATILITY",
            "HIGH_VOLATILITY",
            "FLAT_LOW",
            "FLAT_HIGH",
        ],
        exit=SimpleNamespace(
            sl_pct=0.005,
            tp_rr=1.0,
            regime_tpsl=None,
        ),
    )
    md_amr_cfg = SimpleNamespace(
        enabled=True,
        timeframe_sec=900,
        defer_ttl_sec=60,
        channel_window_bars=12,
        channel_robust_pct=0.05,
        atr_window=14,
        atr_stats_window=64,
        hysteresis_mult=1.20,
        threshold_z=2.20,
        volatility_dampening_factor=0.50,
        thr_base=0.55,
        thr_floor=0.10,
        alpha=0.25,
        conf_min=0.22,
        hold_edge_min=-0.5,
        # Phase 1 reconciliation: reverted to Package A.1 baseline per roadmap truth.
        # Package B code support exists; YAML default = 0.0 per B.1 economic verdict.
        target_approach_pct=0.0,
        max_hold_bars=16,
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        fee_bps=4.0,
        slippage_buffer_bps=2.0,
        scaleout_fraction=0.50,
        scaleout_cost_model="round_trip",
        progress_tracking=SimpleNamespace(
            early_progress_max_pct=0.25,
            partial_progress_max_pct=0.70,
            near_completion_max_pct=1.00,
        ),
        setup_quality=SimpleNamespace(
            penetration_depth_full_scale=0.50,
            channel_width_pct_full_scale=1.00,
            volatility_z_full_penalty=3.00,
        ),
        hold_quality=SimpleNamespace(
            expected_progress_grace_frac=0.25,
            time_decay_weight=0.35,
            progress_deficit_weight=0.45,
        ),
        context_validity=SimpleNamespace(
            regime_confidence_floor=0.35,
            regime_confidence_valid=0.60,
            volatility_z_weakening=1.50,
            volatility_z_invalid=3.00,
            channel_width_pct_floor=0.10,
            channel_width_pct_valid=1.00,
            regime_weight=0.35,
            volatility_weight=0.20,
            structure_weight=0.20,
            progress_alignment_weight=0.25,
            valid_score_min=0.70,
            invalid_score_max=0.35,
        ),
        entry_anchor_persistence=SimpleNamespace(
            storage_path="ops/restore/md_amr_entry_anchor_state_v1.json",
        ),
        weights=SimpleNamespace(d1=0.35, h1=0.30, m30=0.20, m15=0.15),
        objective=SimpleNamespace(enabled=False),
        execution=SimpleNamespace(
            gtx_retry_max=2,
            emit_market_fallback_marker_on_retry_exhaustion=True),
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=-0.8,
            block_ttl_sec=14_400,
        ),
        concentration_guard=SimpleNamespace(
            enabled=False,
            max_simultaneous_entries_per_bar=2,
        ),
        assets={symbol: asset_cfg},
    )
    return SimpleNamespace(
        basis_import_buffer=20,
        regime=SimpleNamespace(
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(sma_long_period=64),
                volatility=SimpleNamespace(atr_period=14, atr_sma_length=20),
            )
        ),
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                position_sizing=SimpleNamespace(
                    min_position_size_usd=10,
                    liquidity_based_cap_usd=10_000,
                )
            )
        ),
        strategies_registry=SimpleNamespace(assignments={symbol: ["md_amr"]}),
        strategies=SimpleNamespace(md_amr=md_amr_cfg),
    )


def _make_handler(symbol: str = "BNBUSDT") -> tuple[MDAMRHandler, _FSMStub]:
    fsm = _FSMStub()
    handler = MDAMRHandler(fsm=fsm, config=_make_config(symbol))
    return handler, fsm


def _event_payload(symbol: str = "BNBUSDT") -> dict:
    return {
        "symbol": symbol,
        "tf_sec": 900,
        "warmup": {"full_ready": True},
        "features": {},
        "bar": {
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "10",
            "end_ts_ms": 1_700_000_000_000,
        },
    }


def test_md_amr_handler_initializes_and_enables_for_assigned_symbol(caplog) -> None:
    with caplog.at_level(logging.INFO):
        handler, _fsm = _make_handler()

    assert handler._enabled is True
    assert handler._enabled_symbols == {"BNBUSDT"}
    assert "MD_AMR_INIT" in caplog.text
    assert "MD_AMR_ENABLED" in caplog.text


def test_md_amr_registers_required_listeners(caplog) -> None:
    handler, fsm = _make_handler()

    with patch.object(MDAMRHandler, "_hydrate_state_from_rest", lambda self: None):
        with caplog.at_level(logging.INFO):
            handler.register()

    assert [event for event, _handler in fsm.listeners] == [
        "CMD:PROCESS_STRATEGY",
        "EVT:FEATURES_CALCULATED",
        "EVT:REGIME_DETECTED",
        "EVT:TRADE_EXECUTED",
        "EVT:ORDER_REJECTED",
        "EVT:PORTFOLIO_STATE_UPDATED",
        "EVT:EXPOSURE_SUMMARY_UPDATED",
        "EVT:ORDER_STATE_CHANGED",
        "EVT:TRADE_INTENT_REJECTED",
    ]
    assert "MD_AMR_REGISTERED" in caplog.text


def test_md_amr_cold_start_reachability_thresholds_are_consistent() -> None:
    profiles = build_active_strategy_compatibility_profiles(_make_config())
    md_amr_profile = profiles["md_amr"]

    assert md_amr_profile.required_basis_tf_sec == 900
    assert md_amr_profile.needs_regime is True
    assert md_amr_profile.needs_execution_context is True
    assert md_amr_profile.local_hydration_contract == "md_amr_rest_hydration"
    assert md_amr_profile.degraded_mode_allowance == "PROTECT_ONLY"
    assert md_amr_profile.protect_only_capability is True
    assert md_amr_profile.basis_required_bars == 96


def test_md_amr_emits_observable_defer_reason_before_signal_ready(caplog) -> None:
    handler, _fsm = _make_handler()
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {"status": "DEFER",
                                  "missing_fields": ["dir_score"]}
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=1),
    ):
        with caplog.at_level(logging.INFO):
            handler._on_process_strategy(SimpleNamespace(pld=_event_payload()))

    assert "BNBUSDT" in handler._deferred
    assert "MD_AMR_DEFER" in caplog.text
    assert "dir_score" in caplog.text


def test_md_amr_first_entry_becomes_possible_after_required_history() -> None:
    strategy = MDAMRStrategyV11(
        channel_window_bars=12,
        hysteresis_mult=1.20,
        threshold_z=2.20,
        volatility_dampening_factor=0.50,
        thr_base=0.55,
        alpha=0.25,
        conf_min=0.22,
        max_hold_bars=16,
        fee_bps=4.0,
        slippage_buffer_bps=2.0,
        scaleout_fraction=0.50,
        weights={"d1": 0.35, "h1": 0.30, "m30": 0.20, "m15": 0.15},
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        thr_floor=0.10,
        scaleout_cost_model="round_trip",
        atr_window=14,
        atr_stats_window=64,
        hold_edge_min=-0.50,
        target_approach_pct=0.0,
        progress_tracking_early_progress_max_pct=0.25,
        progress_tracking_partial_progress_max_pct=0.70,
        progress_tracking_near_completion_max_pct=1.00,
        setup_quality_penetration_depth_full_scale=0.50,
        setup_quality_channel_width_pct_full_scale=1.00,
        setup_quality_volatility_z_full_penalty=3.00,
        hold_quality_expected_progress_grace_frac=0.25,
        hold_quality_time_decay_weight=0.35,
        hold_quality_progress_deficit_weight=0.45,
        context_validity_regime_confidence_floor=0.35,
        context_validity_regime_confidence_valid=0.60,
        context_validity_volatility_z_weakening=1.50,
        context_validity_volatility_z_invalid=3.00,
        context_validity_channel_width_pct_floor=0.10,
        context_validity_channel_width_pct_valid=1.00,
        context_validity_regime_weight=0.35,
        context_validity_volatility_weight=0.20,
        context_validity_structure_weight=0.20,
        context_validity_progress_alignment_weight=0.25,
        context_validity_valid_score_min=0.70,
        context_validity_invalid_score_max=0.35,
    )

    last_result = None
    for _index in range(95):
        last_result = strategy.on_bar(
            bar={"open": "100", "high": "101", "low": "99", "close": "100"},
            position_ctx={"qty_signed": 0.0, "bars_held": 0},
        )

    assert last_result == {"status": "DEFER", "missing_fields": ["dir_score"]}

    signal_result = strategy.on_bar(
        bar={"open": "100", "high": "101", "low": "90", "close": "90"},
        position_ctx={"qty_signed": 0.0, "bars_held": 0},
    )

    assert signal_result["status"] == "SIGNAL"
    signal = signal_result["signal"]
    assert signal.intent_kind == "ENTRY"
    assert signal.side == "BUY"


def test_md_amr_runtime_logs_init_enable_and_signal_readiness(caplog) -> None:
    with caplog.at_level(logging.INFO):
        handler, fsm = _make_handler()
        handler._regime["BNBUSDT"] = "MEAN_REVERSION"
        handler._strategies["BNBUSDT"] = SimpleNamespace(
            on_bar=lambda **_kwargs: {
                "status": "SIGNAL",
                "signal": MDAMRSignal(
                    intent_kind="ENTRY",
                    side="BUY",
                    reason_code="MD_AMR_ENTRY_LONG",
                    signal_score=0.9,
                    conf_ratio=0.8,
                    scaleout_fraction=None,
                    price_ref=Decimal("100"),
                    channel_state={"avg_high_12": 101.0,
                                   "avg_low_12": 99.0, "avg_close_12": 100.0},
                    atr=1.0,
                    dir_score=0.1,
                    trace={"conf_ratio": 0.8, "qty_base": 1.0, "qty_new": 1.0},
                ),
            }
        )

        with patch.object(MDAMRHandler, "_hydrate_state_from_rest", lambda self: None):
            with patch(
                "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
                return_value=SimpleNamespace(basis_required_bars=1),
            ):
                handler.register()
                handler._on_process_strategy(
                    SimpleNamespace(pld=_event_payload()))

    emitted_events = [name for name, _payload, _why, _data_ref in fsm.emitted]
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in emitted_events
    assert "MD_AMR_INIT" in caplog.text
    assert "MD_AMR_ENABLED" in caplog.text
    assert "MD_AMR_REGISTERED" in caplog.text
    assert "MD_AMR_BARS_PROGRESS" in caplog.text
    assert "MD_AMR_SIGNAL_READY" in caplog.text
    assert "MD_AMR_SIGNAL_EMITTED" in caplog.text


def test_md_amr_objective_multiplier_keeps_payload_and_trace_aligned() -> None:
    handler, fsm = _make_handler()
    handler.config.domains.objective_engine = SimpleNamespace(
        enabled=True,
        data_requirements=SimpleNamespace(strict_fail_closed=True),
        components={
            "cost": SimpleNamespace(
                enabled=True,
                parameters={
                    "base_fee_bps": 4.0,
                    "slippage_from_spread_ratio": 0.5,
                },
            ),
            "behavior": SimpleNamespace(
                enabled=True,
                parameters={"window_sec": 60.0},
            ),
        },
    )
    handler.config.strategies.md_amr.objective = SimpleNamespace(enabled=True)
    handler._latest_portfolio = {
        "positions_last_ts_ms": 1_700_000_000_000,
        "equity_free_usdt": "1000",
        "positions": [],
    }
    handler._latest_exposure_summary = {}
    handler._regime["BNBUSDT"] = "MEAN_REVERSION"
    handler._regime_ts_ms["BNBUSDT"] = 1_700_000_000_000
    handler._regime_confidence["BNBUSDT"] = 0.85
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {
            "status": "SIGNAL",
            "signal": MDAMRSignal(
                intent_kind="ENTRY",
                side="BUY",
                reason_code="MD_AMR_ENTRY_LONG",
                signal_score=0.9,
                conf_ratio=0.8,
                scaleout_fraction=None,
                price_ref=Decimal("100"),
                channel_state={"avg_high_12": 101.0, "avg_low_12": 99.0},
                atr=1.0,
                dir_score=0.1,
                trace={
                    "conf_ratio": 0.8,
                    "qty_base": 1.0,
                    "qty_new": 1.0,
                    "thr_buy": 0.55,
                    "thr_sell": 0.55,
                },
            ),
        }
    )

    objective_trace = {
        "trace_id": "obj-md-amr-1",
        "multiplier": 0.5,
        "objective_score": 0.42,
        "components": {"cost": 0.5},
        "raw_metrics": {"fee_bps": 4.0},
    }
    mock_obj_score = SimpleNamespace(
        is_blocked=False,
        multiplier=0.5,
        objective_score=0.42,
        trace=SimpleNamespace(
            model_dump=lambda: dict(objective_trace)),
        components={"cost": 0.5},
        raw_metrics={"fee_bps": 4.0},
        block_reason=None,
    )

    with (
        patch(
            "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
            return_value=SimpleNamespace(basis_required_bars=1),
        ),
        patch.object(
            MDAMRHandler,
            "_compute_tpsl",
            return_value={
                "stop_price": Decimal("99"),
                "target_price": Decimal("101"),
                "tpsl_ctx": {
                    "regime_used": "MEAN_REVERSION",
                    "sl_pct_eff": 0.01,
                    "tp_rr_eff": 1.0,
                },
            },
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_market_input",
            return_value=SimpleNamespace(spread_bps=1.0),
        ) as build_market_input_mock,
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.compute_readiness_completeness",
            return_value=1.0,
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_signal_input",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_structure_input_from_prices",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.compute_projected_order_notional",
            return_value=100.0,
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_exposure_input",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_behavior_input",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_execution_input",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.build_objective_input",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.evaluate_objective",
            return_value=mock_obj_score,
        ),
    ):
        handler._on_process_strategy(
            SimpleNamespace(
                pld={
                    **_event_payload(),
                    "warmup": {"full_ready": True, "ready": {}},
                    "features": {"price": "100.0"},
                }
            )
        )

    assert build_market_input_mock.call_args.kwargs["features"]["atr"] == pytest.approx(
        1.0
    )

    produced = [
        payload
        for name, payload, _why, _data_ref in fsm.emitted
        if name == "EVT:STRATEGY_SIGNAL_PRODUCED"
    ]
    assert len(produced) == 1
    payload = produced[0]
    assert payload["trace"]["conf_ratio"] == pytest.approx(0.4)
    assert payload["score"] == pytest.approx(0.42)
    assert payload["trace"]["objective"]["trace_id"] == "obj-md-amr-1"
    assert payload["scoring"]["objective"]["objective_score"] == pytest.approx(
        0.42)


def test_md_amr_objective_missing_tpsl_fails_closed_before_evaluator() -> None:
    handler, _fsm = _make_handler()
    rejected: list[dict] = []
    handler._emit_trade_intent_rejected_gate = lambda **kwargs: rejected.append(
        kwargs)
    handler.config.domains.objective_engine = SimpleNamespace(
        enabled=True,
        data_requirements=SimpleNamespace(strict_fail_closed=True),
        components={
            "cost": SimpleNamespace(
                enabled=True,
                parameters={
                    "base_fee_bps": 4.0,
                    "slippage_from_spread_ratio": 0.5,
                },
            ),
            "behavior": SimpleNamespace(
                enabled=True,
                parameters={"window_sec": 60.0},
            ),
        },
    )
    handler.config.strategies.md_amr.objective = SimpleNamespace(enabled=True)
    handler._latest_portfolio = {
        "positions_last_ts_ms": 1_700_000_000_000,
        "equity_free_usdt": "1000",
        "positions": [],
    }
    handler._latest_exposure_summary = {}
    handler._regime["BNBUSDT"] = "MEAN_REVERSION"
    handler._regime_ts_ms["BNBUSDT"] = 1_700_000_000_000
    handler._regime_confidence["BNBUSDT"] = 0.85
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {
            "status": "SIGNAL",
            "signal": MDAMRSignal(
                intent_kind="ENTRY",
                side="BUY",
                reason_code="MD_AMR_ENTRY_LONG",
                signal_score=0.9,
                conf_ratio=0.8,
                scaleout_fraction=None,
                price_ref=Decimal("100"),
                channel_state={"avg_high_12": 101.0, "avg_low_12": 99.0},
                atr=1.0,
                dir_score=0.1,
                trace={
                    "conf_ratio": 0.8,
                    "qty_base": 1.0,
                    "qty_new": 1.0,
                    "thr_buy": 0.55,
                    "thr_sell": 0.55,
                },
            ),
        }
    )

    with (
        patch(
            "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
            return_value=SimpleNamespace(basis_required_bars=1),
        ),
        patch.object(MDAMRHandler, "_compute_tpsl", return_value=None),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.evaluate_objective_gate",
            side_effect=AssertionError("evaluator must not run"),
        ),
        patch(
            "apps.reference.domains.strategies.runtimes.md_amr.handler.inc_decision_blocked"
        ) as blocked_metric,
    ):
        handler._on_process_strategy(
            SimpleNamespace(
                pld={
                    **_event_payload(),
                    "warmup": {"full_ready": True, "ready": {}},
                    "features": {"price": "100.0"},
                }
            )
        )

    assert len(rejected) == 1
    assert rejected[0]["reason_code"] == "OBJECTIVE_ENGINE_FAIL_CLOSED"
    assert rejected[0]["why"] == "OBJECTIVE_TPSL_MISSING"
    assert rejected[0]["details"] == {"error": "OBJECTIVE_TPSL_MISSING"}
    blocked_metric.assert_called_once_with(
        stage="strategy", reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED"
    )


def test_md_amr_restored_execution_snapshot_allows_open_new_risk_on_signal() -> None:
    handler, fsm = _make_handler()
    restore_snapshot = make_strategy_restore_snapshot(
        strategy_id="md_amr",
        symbol="BNBUSDT",
        updated_at=1_700_000_000_000,
        scopes={
            scope.value: restored_restore_status(
                why=[f"{scope.value}_restored"],
                updated_at=1_700_000_000_000,
                source="startup:test",
                evidence_ref=f"{scope.value}:BNBUSDT:1700000000000",
            )
            for scope in RuntimeAnalyticsRestoreScope
        },
        source="startup:test",
        has_open_position=False,
    )
    handler.apply_runtime_analytics_restore_snapshot(restore_snapshot)
    handler._latest_portfolio = {
        "positions_last_ts_ms": 1_700_000_000_000,
        "equity_free_usdt": "1000",
        "positions": [],
    }
    handler._latest_exposure_summary = {}
    handler._regime["BNBUSDT"] = "MEAN_REVERSION"
    handler._regime_ts_ms["BNBUSDT"] = 1_700_000_000_000
    handler._regime_confidence["BNBUSDT"] = 0.9
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {
            "status": "SIGNAL",
            "signal": MDAMRSignal(
                intent_kind="ENTRY",
                side="BUY",
                reason_code="MD_AMR_ENTRY_LONG",
                signal_score=0.9,
                conf_ratio=0.8,
                scaleout_fraction=None,
                price_ref=Decimal("100"),
                channel_state={"avg_high_12": 101.0, "avg_low_12": 99.0},
                atr=1.0,
                dir_score=0.1,
                trace={
                    "conf_ratio": 0.8,
                    "qty_base": 1.0,
                    "qty_new": 1.0,
                    "thr_buy": 0.55,
                    "thr_sell": 0.55,
                },
            ),
        }
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=1),
    ):
        handler._on_process_strategy(
            SimpleNamespace(
                pld={
                    **_event_payload(),
                    "warmup": {"full_ready": True, "ready": {}},
                    "features": {"price": "100.0"},
                }
            )
        )

    produced = [
        payload
        for name, payload, _why, _data_ref in fsm.emitted
        if name == "EVT:STRATEGY_SIGNAL_PRODUCED"
    ]
    assert len(produced) == 1
    payload = produced[0]
    assert payload["runtime_permissions"]["can_open_new_risk"] is True
    assert payload["runtime_permissions"]["mode"] == "OPEN_AND_MANAGE"
