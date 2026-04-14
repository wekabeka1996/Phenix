from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler


class _FSMStub:
    def __init__(self) -> None:
        self.listeners: list[tuple[str, object]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.append((event, handler))

    def emit(self, *args, **kwargs) -> None:
        return None

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
        ],
        exit=SimpleNamespace(sl_pct=0.005, tp_rr=1.0, regime_tpsl=None),
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
        reconciliation=SimpleNamespace(
            enabled=True, interval_sec=300, drift_tolerance=1e-6),
        concentration_guard=SimpleNamespace(
            enabled=False, max_simultaneous_entries_per_bar=2),
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


class _Event:
    def __init__(self, payload: dict) -> None:
        self.pld = payload


def test_md_amr_init_strategies_passes_c4_contract() -> None:
    handler = MDAMRHandler(fsm=_FSMStub(), config=_make_config())

    strategy = handler._strategies["BNBUSDT"]
    assert strategy.progress_tracking_partial_progress_max_pct == 0.70
    assert strategy.setup_quality_channel_width_pct_full_scale == 1.00
    assert strategy.context_validity_regime_confidence_floor == 0.35
    assert strategy.context_validity_regime_confidence_valid == 0.60
    assert strategy.context_validity_valid_score_min == 0.70
    assert strategy.context_validity_invalid_score_max == 0.35


def test_md_amr_on_process_strategy_passes_context_inputs_without_breaking_anchors() -> None:
    handler = object.__new__(MDAMRHandler)
    captured: list[dict] = []

    handler.logger = logging.getLogger("tests.md_amr.c4")
    handler.mlog = logging.getLogger("tests.md_amr.c4")
    handler._enabled = True
    handler._enabled_symbols = {"BNBUSDT"}
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=0.0,
            block_ttl_sec=0,
        ),
        assets={
            "BNBUSDT": SimpleNamespace(
                allowed_regimes=["MEAN_REVERSION", "LOW_VOLATILITY"],
            )
        },
    )
    handler.config = SimpleNamespace()
    handler._bars_seen_since_restart = {"BNBUSDT": 1}
    handler._pending_close = {}
    handler._position_qty = {"BNBUSDT": Decimal("1")}
    handler._bars_held = {"BNBUSDT": 4}
    handler._last_ingested_bar_ts_ms = {}
    handler._deferred = {}
    handler._entry_anchor = {
        "BNBUSDT": {
            "entry_price": 600.0,
            "entry_target_price": 610.0,
        }
    }
    handler._regime = {"BNBUSDT": "MEAN_REVERSION"}
    handler._regime_confidence = {"BNBUSDT": 0.77}
    handler._strategies = {
        "BNBUSDT": SimpleNamespace(
            on_bar=lambda **kwargs: captured.append(kwargs) or {
                "status": "NOOP"}
        )
    }
    handler._is_duplicate_live_event = lambda symbol, ts_ms: False
    handler._expire_defer_if_needed = lambda symbol, now_ms: None
    handler._is_mandatory_live_warmup_active = lambda now_ms: False
    handler._emit_trade_intent_rejected_gate = lambda **kwargs: None
    handler._rid = lambda **_kwargs: "md-amr-c4-anchor"
    handler._signal_ready_logged = set()

    event = _Event(
        {
            "symbol": "BNBUSDT",
            "tf_sec": 900,
            "warmup": {"full_ready": True},
            "bar": {
                "end_ts_ms": 1_700_000_000_000,
                "open": "600",
                "high": "601",
                "low": "599",
                "close": "600.5",
            },
            "features": {},
        }
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=1),
    ):
        handler._on_process_strategy(event)

    assert captured, "Expected handler to call strategy.on_bar()"
    position_ctx = captured[0]["position_ctx"]
    assert position_ctx["bars_held"] == 5
    assert position_ctx["entry_price"] == 600.0
    assert position_ctx["entry_target_price"] == 610.0
    assert position_ctx["context_regime"] == "MEAN_REVERSION"
    assert position_ctx["context_regime_confidence"] == 0.77
    assert position_ctx["context_regime_allowed"] is True
