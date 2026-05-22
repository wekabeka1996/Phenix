from __future__ import annotations

import decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.decision_making.contracts.core_models import (
    ProcessStrategyCmd,
    WarmupState,
)
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler


def _kernel_result(*, side: str = "buy") -> SimpleNamespace:
    return SimpleNamespace(
        side=side,
        score=decimal.Decimal("0.6"),
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        why_chain=[f"enter:{side}"],
        psi_vector={
            "s_linear": 0.6,
            "multiplier": 1.25,
            "s_scaled_raw": 0.75,
            "s_clamped": 0.75,
            "raw_exposure": 0.56,
            "final_score": 0.6,
            "final_exposure": 0.6,
            "shield_multiplier": 1.0,
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "side_why": f"enter:{side}",
        },
        deferred=False,
        defer_reason=None,
        shield_multiplier=decimal.Decimal("1.0"),
        regime="LOW_VOLATILITY",
    )


def _build_handler(
    *,
    emit_fn,
    anti_flat_sigma: float = 0.1,
    anti_fomo_sigma: float = 10.0,
) -> AuroraHandler:
    scoring_result = _kernel_result()
    scoring_kernel_cls = type(
        "StubAuroraKernel",
        (),
        {"compute": staticmethod(lambda **_kwargs: scoring_result)},
    )

    with (
        patch.object(AuroraHandler, "_load_config", lambda self: None),
        patch(
            "apps.reference.domains.strategies.runtimes.aurora.decision.evaluate_quadratic_shadow",
            return_value=SimpleNamespace(state="NOT_REQUESTED"),
        ),
    ):
        handler = AuroraHandler(
            config=SimpleNamespace(
                strategies=SimpleNamespace(
                    aurora=SimpleNamespace(
                        decision=SimpleNamespace(scoring_version="quadratic"),
                    )
                ),
                regime_shift_inception=None,
                instruments=None,
            ),
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler.motion_window_sec = 300
    handler.vol_gates_enabled = True
    handler.anti_flat_sigma = anti_flat_sigma
    handler.anti_fomo_sigma = anti_fomo_sigma
    handler._basis_required_bars_override = 0
    handler._is_symbol_enabled = lambda symbol: True
    handler._check_regime_liveness = lambda symbol, state: None
    handler._get_instrument_config = lambda symbol: SimpleNamespace(
        allowed_regimes=["LOW_VOLATILITY"],
        tick_size=None,
        volatility_entry_logic=None,
    )
    handler._get_signal_weights = lambda symbol, instr_cfg: {}
    handler._get_feature_neutrals = lambda symbol, instr_cfg: {}
    handler._get_essential_features = lambda symbol, instr_cfg: []
    handler._check_liquidity_gate = lambda **_kwargs: (True, {})
    handler._get_side_bias_state = lambda symbol: None
    handler._get_regime_thresholds = lambda symbol, instr_cfg: {
        "LOW_VOLATILITY": 1.0,
        "DEFAULT": 1.0,
    }
    handler._should_suppress_soft_exit = lambda *args, **kwargs: False
    handler._get_reentry_cooldown_sec = lambda symbol: 0.0
    handler._update_side_bias = lambda *args, **kwargs: None
    handler._compute_regime_tpsl = lambda **_kwargs: None
    handler._get_tpsl_owner_loss_reason = lambda: None
    handler.scoring_kernel_cls = scoring_kernel_cls
    handler.signal_threshold = decimal.Decimal("0.1")
    handler.neutral_threshold = decimal.Decimal("0.05")
    handler.direction_strength_cfg = {}
    handler.delta_price_cap_pct = decimal.Decimal("0.01")
    handler.normalize_signals_mode = "signed_v2"
    handler.score_multiplier = 1.25
    handler._quadratic_shadow_shield_fn = None
    handler._regime_smoother = None
    handler.objective_engine = None
    handler.execution_gate = None
    handler.entry_plan_calculator = None
    handler.exit_manager = SimpleNamespace(
        check_exit=lambda **_kwargs: (False, None, None)
    )

    state = handler._symbol_states["BTCUSDT"]
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42
    return handler


def _payloads(emitted: list[tuple[str, dict]], name: str) -> list[dict]:
    return [payload for event_name, payload in emitted if event_name == name]


def _base_cmd(*, close_boundary_ts_ms: int, price_motion: dict | None = None) -> dict:
    payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": close_boundary_ts_ms,
        "close_boundary_ts_ms": close_boundary_ts_ms,
        "warmup": {"full_ready": True, "ready": {}},
        "features": {
            "price": "100.0",
            "pillar_sum": 0.6,
            "pillar_tactician": 0.3,
            "pillar_operator": 0.2,
            "pillar_strategist": 0.1,
            "pillar_contribs": {"tactician": 0.3, "operator": 0.2, "strategist": 0.1},
        },
    }
    if price_motion is not None:
        payload["price_motion"] = dict(price_motion)
    return payload


def test_same_bar_typed_cmd_transport_propagates_trace_and_signal_provenance() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)))

    handler._process_decision(
        "BTCUSDT",
        _base_cmd(
            close_boundary_ts_ms=1_700_000_000_000,
            price_motion={"pm_norm_300s": 0.8, "ret_300s": 0.002},
        ),
    )

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "cmd_typed"
    assert trace["price_motion_age_ms"] == 0
    assert trace["price_motion_ready"] is True
    assert signal["scoring"]["price_motion"] == {
        "source": "cmd_typed",
        "age_ms": 0,
        "ready": True,
        "consumed_by_vol_gate": True,
    }


def test_nested_features_price_motion_is_labeled_features_when_typed_transport_is_absent() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)))
    payload = _base_cmd(close_boundary_ts_ms=1_700_000_000_000)
    payload["features"]["price_motion"] = {
        "pm_norm_300s": 0.8,
        "ret_300s": 0.002,
    }

    handler._process_decision("BTCUSDT", payload)

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "features"
    assert trace["price_motion_age_ms"] == 0
    assert trace["price_motion_ready"] is True
    assert signal["scoring"]["price_motion"] == {
        "source": "features",
        "age_ms": 0,
        "ready": True,
        "consumed_by_vol_gate": True,
    }


def test_typed_cmd_transport_wins_over_conflicting_nested_features_price_motion() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        anti_flat_sigma=0.5,
    )
    payload = _base_cmd(
        close_boundary_ts_ms=1_700_000_000_000,
        price_motion={"pm_norm_300s": 0.8, "ret_300s": 0.002},
    )
    payload["features"]["price_motion"] = {
        "pm_norm_300s": 0.2,
        "ret_300s": 0.001,
    }

    handler._process_decision("BTCUSDT", payload)

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "cmd_typed"
    assert trace["price_motion_age_ms"] == 0
    assert trace["price_motion_ready"] is True
    assert signal["scoring"]["price_motion"] == {
        "source": "cmd_typed",
        "age_ms": 0,
        "ready": True,
        "consumed_by_vol_gate": True,
    }
    assert not _payloads(emitted, "EVT:STRATEGY_DECISION_BLOCKED")


def test_same_bar_typed_cmd_transport_vol_gate_block_preserves_matching_provenance() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        anti_flat_sigma=0.5,
    )

    handler._process_decision(
        "BTCUSDT",
        _base_cmd(
            close_boundary_ts_ms=1_700_000_000_000,
            price_motion={"pm_norm_300s": 0.2, "ret_300s": 0.001},
        ),
    )

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    blocked = _payloads(emitted, "EVT:STRATEGY_DECISION_BLOCKED")[0]
    assert blocked["reason_code"] == "GATE_ANTI_FLAT_SIGMA"
    assert trace["price_motion_source"] == "cmd_typed"
    assert blocked["details"]["price_motion"] == {
        "source": trace["price_motion_source"],
        "age_ms": trace["price_motion_age_ms"],
        "ready": trace["price_motion_ready"],
        "consumed_by_vol_gate": True,
    }
    anti_peak = blocked["details"]["anti_peak_observability"]
    assert anti_peak["motion_classification"] == "anti_flat_triggered"
    assert anti_peak["consumed_by_gate"] is True
    assert anti_peak["source"] == "cmd_typed"


def test_same_bar_cache_fallback_marks_price_motion_ready() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)))
    handler.on_features_data_only(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "close_boundary_ts_ms": 1_700_000_000_000,
            "price_motion": {"pm_norm_300s": 0.7, "ret_300s": 0.002},
        }
    )

    handler._process_decision(
        "BTCUSDT",
        _base_cmd(close_boundary_ts_ms=1_700_000_000_000),
    )

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "cache"
    assert trace["price_motion_age_ms"] == 0
    assert trace["price_motion_ready"] is True
    assert signal["scoring"]["price_motion"] == {
        "source": "cache",
        "age_ms": 0,
        "ready": True,
        "consumed_by_vol_gate": True,
    }


def test_stale_cache_stays_visible_but_is_not_consumed() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        anti_flat_sigma=0.5,
    )
    handler.on_features_data_only(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "close_boundary_ts_ms": 1_699_999_700_000,
            "price_motion": {"pm_norm_300s": 0.2, "ret_300s": 0.001},
        }
    )

    handler._process_decision(
        "BTCUSDT",
        _base_cmd(close_boundary_ts_ms=1_700_000_000_000),
    )

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "cache"
    assert trace["price_motion_age_ms"] == 300000
    assert trace["price_motion_ready"] is False
    assert signal["scoring"]["price_motion"] == {
        "source": "cache",
        "age_ms": 300000,
        "ready": False,
        "consumed_by_vol_gate": False,
    }
    assert not _payloads(emitted, "EVT:STRATEGY_DECISION_BLOCKED")


def test_missing_everywhere_emits_missing_without_hidden_fallback() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        anti_flat_sigma=0.5,
    )

    handler._process_decision(
        "BTCUSDT",
        _base_cmd(close_boundary_ts_ms=1_700_000_000_000),
    )

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "missing"
    assert trace["price_motion_age_ms"] is None
    assert trace["price_motion_ready"] is False
    assert signal["scoring"]["price_motion"] == {
        "source": "missing",
        "age_ms": None,
        "ready": False,
        "consumed_by_vol_gate": False,
    }


def test_raw_fallback_works_when_typed_price_motion_is_absent() -> None:
    emitted: list[tuple[str, dict]] = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)))
    cmd = ProcessStrategyCmd(
        symbol="BTCUSDT",
        tf_sec=300,
        bar_close_ts=1_700_000_000_000,
        rid="rid-raw-fallback",
        features={
            "price": "100.0",
            "pillar_sum": 0.6,
            "pillar_tactician": 0.3,
            "pillar_operator": 0.2,
            "pillar_strategist": 0.1,
            "pillar_contribs": {"tactician": 0.3, "operator": 0.2, "strategist": 0.1},
        },
        warmup=WarmupState(full_ready=True, ticks_seen=0,
                           ready={}, reasons=()),
        raw={
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "close_boundary_ts_ms": 1_700_000_000_000,
            "price_motion": {"pm_norm_300s": 0.8, "ret_300s": 0.002},
        },
        price_motion=None,
    )

    handler._process_decision("BTCUSDT", cmd)

    trace = _payloads(emitted, "EVT:QUADRATIC_DECISION_TRACE")[0]
    signal = _payloads(emitted, "EVT:STRATEGY_SIGNAL_PRODUCED")[0]
    assert trace["price_motion_source"] == "cmd_raw_fallback"
    assert trace["price_motion_age_ms"] == 0
    assert trace["price_motion_ready"] is True
    assert signal["scoring"]["price_motion"] == {
        "source": "cmd_raw_fallback",
        "age_ms": 0,
        "ready": True,
        "consumed_by_vol_gate": True,
    }
