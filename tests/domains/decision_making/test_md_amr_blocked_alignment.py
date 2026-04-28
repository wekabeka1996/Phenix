from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.decision_making.gates.objective_gate_evaluator import (
    ObjectiveGateStatus,
)
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRSignal
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler


class _Event:
    def __init__(self, payload: dict) -> None:
        self.pld = payload


class _FSMStub:
    def __init__(self) -> None:
        self._listeners: dict[str, list[object]] = {}
        self.emitted: list[tuple[str, dict, str | None, object]] = []

    def listen(self, event: str, handler: object) -> None:
        self._listeners.setdefault(event, []).append(handler)

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
    ) -> None:
        payload = payload or {}
        self.emitted.append((event_name, payload, why, data_ref))
        for handler in list(self._listeners.get(event_name, [])):
            handler(SimpleNamespace(pld=payload))

    def get_domain(self, _name: str):
        return None


def _asset_cfg(*, allowed_regimes: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        cooldown_sec=60,
        allowed_regimes=list(
            allowed_regimes
            or [
                "MEAN_REVERSION",
                "LOW_VOLATILITY",
                "HIGH_VOLATILITY",
                "FLAT_LOW",
                "FLAT_HIGH",
            ]
        ),
        exit=SimpleNamespace(
            sl_pct=0.005,
            tp_rr=1.0,
            regime_tpsl=None,
        ),
    )


def _make_config(symbol: str = "BNBUSDT") -> SimpleNamespace:
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
            emit_market_fallback_marker_on_retry_exhaustion=True,
        ),
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=-0.8,
            block_ttl_sec=14_400,
        ),
        concentration_guard=SimpleNamespace(
            enabled=False,
            max_simultaneous_entries_per_bar=2,
        ),
        assets={symbol: _asset_cfg()},
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
            ),
            objective_engine=SimpleNamespace(
                enabled=False,
                data_requirements=SimpleNamespace(strict_fail_closed=True),
            ),
        ),
        strategies_registry=SimpleNamespace(assignments={symbol: ["md_amr"]}),
        strategies=SimpleNamespace(md_amr=md_amr_cfg),
    )


def _make_handler(symbol: str = "BNBUSDT") -> tuple[MDAMRHandler, _FSMStub]:
    fsm = _FSMStub()
    handler = MDAMRHandler(fsm=fsm, config=_make_config(symbol))
    handler._is_duplicate_live_event = lambda _symbol, _ts_ms: False
    handler._expire_defer_if_needed = lambda _symbol, _now_ms: None
    return handler, fsm


def _entry_signal() -> MDAMRSignal:
    return MDAMRSignal(
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
    )


def _event_payload(symbol: str = "BNBUSDT", *, full_ready: bool = True) -> dict:
    return {
        "symbol": symbol,
        "tf_sec": 900,
        "warmup": {"full_ready": full_ready, "ready": {}},
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


def _strategy_blocked_payload(**kwargs) -> dict:
    payload = {
        "schema_version": 1,
        "strategy_id": str(kwargs["strategy_id"]),
        "symbol": str(kwargs["symbol"]),
        "reason_code": str(kwargs["reason_code"]),
        "reason": str(kwargs["reason"]),
        "stage": "STRATEGY",
        "context": str(kwargs["context"]),
        "why": str(kwargs.get("why") or kwargs["context"]),
        "ts_ms": int(kwargs["ts_ms"]),
        "why_chain": list(kwargs.get("why_chain") or []),
    }
    if kwargs.get("details") is not None:
        payload["details"] = kwargs["details"]
    if kwargs.get("rid"):
        payload["rid"] = kwargs["rid"]
    if kwargs.get("tf_sec") is not None:
        payload["tf_sec"] = int(kwargs["tf_sec"])
    return payload


def _payloads_for(fsm: _FSMStub, event_name: str) -> list[dict]:
    return [payload for event, payload, _why, _data_ref in fsm.emitted if event == event_name]


def _assert_blocked_without_trade_reject(
    handler: MDAMRHandler,
    fsm: _FSMStub,
    *,
    expected_reason_code: str,
) -> None:
    blocked = _payloads_for(fsm, "EVT:STRATEGY_DECISION_BLOCKED")
    rejected = _payloads_for(fsm, "EVT:TRADE_INTENT_REJECTED")

    assert len(blocked) == 1
    assert blocked[0]["reason_code"] == expected_reason_code
    assert blocked[0]["stage"] == "STRATEGY"
    assert rejected == []
    assert list(handler._objective_blocked_ts_ms[blocked[0]["symbol"]]) == [
        blocked[0]["ts_ms"]
    ]


def test_md_amr_mandatory_live_warmup_emits_strategy_blocked() -> None:
    handler, fsm = _make_handler()
    handler.mandatory_warmup_until = 1_700_000_100_000
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {"status": "SIGNAL",
                                  "signal": _entry_signal()}
    )
    handler._is_mandatory_live_warmup_active = lambda _now_ms: True

    with patch(
        "apps.reference.domains.strategies.runtimes.md_amr.handler.write_strategy_decision_blocked",
        side_effect=_strategy_blocked_payload,
    ):
        handler._on_process_strategy(_Event(_event_payload()))

    _assert_blocked_without_trade_reject(
        handler,
        fsm,
        expected_reason_code="MANDATORY_LIVE_WARMUP",
    )
    blocked = _payloads_for(fsm, "EVT:STRATEGY_DECISION_BLOCKED")[0]
    assert blocked["details"] == {
        "mandatory_warmup_until_ms": 1_700_000_100_000,
    }


@pytest.mark.parametrize(
    ("full_ready", "profile_side_effect", "expected_reason_code"),
    [
        (False, None, "READINESS_WARMUP_NOT_OK"),
        (True, ValueError("broken compatibility profile"),
         "READINESS_CONTRACT_UNRESOLVED"),
    ],
)
def test_md_amr_readiness_local_denials_emit_strategy_blocked(
    full_ready: bool,
    profile_side_effect: Exception | None,
    expected_reason_code: str,
) -> None:
    handler, fsm = _make_handler()
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {"status": "NO_SIGNAL"}
    )
    handler._is_mandatory_live_warmup_active = lambda _now_ms: False

    profile_kwargs = (
        {"side_effect": profile_side_effect}
        if profile_side_effect is not None
        else {"return_value": SimpleNamespace(basis_required_bars=1)}
    )
    with (
        patch(
            "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
            **profile_kwargs,
        ),
        patch(
            "apps.reference.domains.strategies.runtimes.md_amr.handler.write_strategy_decision_blocked",
            side_effect=_strategy_blocked_payload,
        ),
    ):
        handler._on_process_strategy(
            _Event(_event_payload(full_ready=full_ready)))

    _assert_blocked_without_trade_reject(
        handler,
        fsm,
        expected_reason_code=expected_reason_code,
    )


def test_md_amr_regime_gate_blocked_emits_strategy_blocked() -> None:
    handler, fsm = _make_handler()
    handler._bars_seen_since_restart["BNBUSDT"] = 5
    handler._regime["BNBUSDT"] = "TREND_UP"
    handler._cfg.assets["BNBUSDT"] = _asset_cfg(
        allowed_regimes=["MEAN_REVERSION"])
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {"status": "SIGNAL",
                                  "signal": _entry_signal()}
    )
    handler._is_mandatory_live_warmup_active = lambda _now_ms: False

    with (
        patch(
            "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
            return_value=SimpleNamespace(basis_required_bars=1),
        ),
        patch(
            "apps.reference.domains.strategies.runtimes.md_amr.handler.write_strategy_decision_blocked",
            side_effect=_strategy_blocked_payload,
        ),
    ):
        handler._on_process_strategy(_Event(_event_payload()))

    _assert_blocked_without_trade_reject(
        handler,
        fsm,
        expected_reason_code="REGIME_GATE_BLOCKED",
    )
    blocked = _payloads_for(fsm, "EVT:STRATEGY_DECISION_BLOCKED")[0]
    assert blocked["details"]["regime"] == "TREND_UP"


@pytest.mark.parametrize(
    (
        "objective_case",
        "tpsl_result",
        "objective_result",
        "expected_reason_code",
        "expected_why",
        "expected_details",
    ),
    [
        (
            "missing_tpsl",
            None,
            AssertionError("objective evaluator must not run"),
            "OBJECTIVE_ENGINE_FAIL_CLOSED",
            "OBJECTIVE_TPSL_MISSING",
            {"error": "OBJECTIVE_TPSL_MISSING"},
        ),
        (
            "gate_blocked",
            {"stop_price": "99", "target_price": "101"},
            SimpleNamespace(
                status=ObjectiveGateStatus.GATE_BLOCKED,
                objective_score=SimpleNamespace(
                    block_reason="OBJECTIVE_ENGINE_BLOCKED",
                    objective_score=0.2,
                    multiplier=1.0,
                ),
                trace_payload={"status": "blocked"},
            ),
            "OBJECTIVE_GATE_BLOCKED",
            "OBJECTIVE_ENGINE_BLOCKED",
            {"objective_score": 0.2},
        ),
        (
            "precondition_failed",
            {"stop_price": "99", "target_price": "101"},
            SimpleNamespace(
                status=ObjectiveGateStatus.PRECONDITION_FAILED,
                precondition_code="MISSING_OBJECTIVE_INPUT",
            ),
            "OBJECTIVE_ENGINE_FAIL_CLOSED",
            "MISSING_OBJECTIVE_INPUT",
            {"error": "MISSING_OBJECTIVE_INPUT"},
        ),
        (
            "evaluation_error",
            {"stop_price": "99", "target_price": "101"},
            SimpleNamespace(
                status=ObjectiveGateStatus.EVALUATION_ERROR,
                error="objective engine exploded",
            ),
            "OBJECTIVE_ENGINE_FAIL_CLOSED",
            "objective engine exploded",
            {"error": "objective engine exploded"},
        ),
    ],
)
def test_md_amr_objective_local_denials_emit_strategy_blocked(
    objective_case: str,
    tpsl_result: dict | None,
    objective_result: object,
    expected_reason_code: str,
    expected_why: str,
    expected_details: dict,
) -> None:
    handler, fsm = _make_handler()
    handler._bars_seen_since_restart["BNBUSDT"] = 5
    handler._regime["BNBUSDT"] = "MEAN_REVERSION"
    handler._regime_ts_ms["BNBUSDT"] = 1_700_000_000_000
    handler._regime_confidence["BNBUSDT"] = 0.85
    handler._latest_portfolio = {
        "positions_last_ts_ms": 1_700_000_000_000,
        "equity_free_usdt": "1000",
        "positions": [],
    }
    handler._latest_exposure_summary = {}
    handler._cfg.objective.enabled = True
    handler.config.domains.objective_engine.enabled = True
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **_kwargs: {"status": "SIGNAL",
                                  "signal": _entry_signal()}
    )
    handler._is_mandatory_live_warmup_active = lambda _now_ms: False

    evaluate_patch = (
        {"side_effect": objective_result}
        if isinstance(objective_result, Exception)
        else {"return_value": objective_result}
    )
    with (
        patch(
            "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
            return_value=SimpleNamespace(basis_required_bars=1),
        ),
        patch.object(MDAMRHandler, "_compute_tpsl", return_value=tpsl_result),
        patch(
            "apps.reference.domains.decision_making.gates.objective_gate_evaluator.evaluate_objective_gate",
            **evaluate_patch,
        ),
        patch(
            "apps.reference.domains.strategies.runtimes.md_amr.handler.write_strategy_decision_blocked",
            side_effect=_strategy_blocked_payload,
        ),
    ):
        handler._on_process_strategy(_Event(_event_payload()))

    _assert_blocked_without_trade_reject(
        handler,
        fsm,
        expected_reason_code=expected_reason_code,
    )
    blocked = _payloads_for(fsm, "EVT:STRATEGY_DECISION_BLOCKED")[0]
    assert blocked["why"] == expected_why, objective_case
    assert blocked["details"] == expected_details, objective_case
