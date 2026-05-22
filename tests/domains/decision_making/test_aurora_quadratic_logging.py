import json
import decimal
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.shared.decision_primitives.scoring_kernel import (
    ScoringResult,
)


def _load_registered_quadratic_trace_contract() -> tuple[dict, dict]:
    repo_root = Path(__file__).resolve().parents[3]
    registry_path = repo_root / "apps" / "reference" / \
        "dictionaries" / "verb_registry_v1.yaml"
    registry_doc = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry = registry_doc.get("registry")
    if not isinstance(registry, list):
        raise AssertionError(
            "verb registry: expected top-level 'registry' list")

    entry = next(
        (
            item
            for item in registry
            if isinstance(item, dict)
            and item.get("op") == "EVT"
            and item.get("verb") == "QUADRATIC_DECISION_TRACE"
        ),
        None,
    )
    if entry is None:
        raise AssertionError(
            "Missing EVT:QUADRATIC_DECISION_TRACE registry entry")

    schema_path = repo_root / entry["schema"]
    return entry, json.loads(schema_path.read_text(encoding="utf-8"))


def _build_handler(*, emit_fn, scoring_result: ScoringResult) -> AuroraHandler:
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
    handler._apply_vol_adj_gates = lambda *args, **kwargs: False
    handler._should_suppress_soft_exit = lambda *args, **kwargs: False
    handler._get_reentry_cooldown_sec = lambda symbol: 0.0
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
    handler.exit_manager = SimpleNamespace(
        check_exit=lambda **_kwargs: (False, None, None)
    )

    state = handler._symbol_states["BTCUSDT"]
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42
    return handler


def test_quadratic_decision_trace_logs_on_deferred_path(caplog) -> None:
    emitted: list[tuple[str, dict]] = []
    scoring_result = ScoringResult(
        score=decimal.Decimal("0"),
        side="",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "s_linear": 0.2,
            "multiplier": 1.25,
            "s_scaled_raw": 0.25,
            "s_clamped": 0.25,
            "raw_exposure": 0.0625,
            "final_score": 0.0,
            "final_exposure": 0.0,
            "shield_multiplier": 0.0,
            "shield_reasons": ["PILLAR_WARMUP"],
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "buy_bias_mult": 1.0,
            "sell_bias_mult": 1.0,
            "side_why": "neutral:score=0.0000",
        },
        deferred=True,
        defer_reason="PILLAR_WARMUP",
        shield_multiplier=decimal.Decimal("0"),
    )
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=scoring_result,
    )

    with caplog.at_level(logging.DEBUG, logger="aurora_handler.aurora"):
        handler._process_decision(
            "BTCUSDT",
            {
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1_700_000_000_000,
                "warmup": {"full_ready": True, "ready": {}},
                "features": {
                    "price": "100.0",
                    "pillar_sum": 0.2,
                    "pillar_tactician": 0.1,
                    "pillar_operator": 0.05,
                    "pillar_strategist": 0.05,
                    "pillar_contribs": {"tactician": 0.1, "operator": 0.05, "strategist": 0.05},
                },
            },
        )

    assert "QUADRATIC_DECISION_TRACE" in caplog.text
    blocked = [payload for name, payload in emitted if name ==
               "EVT:STRATEGY_DECISION_BLOCKED"]
    deferred = [payload for name,
                payload in emitted if name == "EVT:INTENT_DEFERRED"]
    assert not blocked
    assert deferred[0]["reason_code"] == "NRR-DATA-NOT-READY"
    assert deferred[0]["raw_reason"] == "PILLAR_WARMUP"
    assert deferred[0]["details"]["decision_trace"]["defer_reason"] == "PILLAR_WARMUP"
    assert deferred[0]["details"]["decision_trace"]["raw_sum"] == 0.2


def test_quadratic_decision_trace_payload_matches_registered_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")

    emitted: list[tuple[str, dict]] = []
    scoring_result = ScoringResult(
        score=decimal.Decimal("0"),
        side="",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "s_linear": 0.2,
            "multiplier": 1.25,
            "s_scaled_raw": 0.25,
            "s_clamped": 0.25,
            "raw_exposure": 0.0625,
            "final_score": 0.0,
            "final_exposure": 0.0,
            "shield_multiplier": 0.0,
            "shield_reasons": ["PILLAR_WARMUP"],
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "buy_bias_mult": 1.0,
            "sell_bias_mult": 1.0,
            "side_why": "neutral:score=0.0000",
        },
        deferred=True,
        defer_reason="PILLAR_WARMUP",
        shield_multiplier=decimal.Decimal("0"),
    )
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=scoring_result,
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None

    handler._process_decision(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "warmup": {"full_ready": True, "ready": {}},
            "features": {
                "price": "100.0",
                "pillar_sum": 0.2,
                "pillar_tactician": 0.1,
                "pillar_operator": 0.05,
                "pillar_strategist": 0.05,
                "pillar_contribs": {"tactician": 0.1, "operator": 0.05, "strategist": 0.05},
            },
        },
    )

    trace_payloads = [
        payload for name, payload in emitted if name == "EVT:QUADRATIC_DECISION_TRACE"]
    assert len(trace_payloads) == 1

    entry, schema = _load_registered_quadratic_trace_contract()
    assert entry["owner"] == "decision_making"
    assert entry["status"] == "active"

    payload = trace_payloads[0]
    assert payload["quadratic_path_reached"] is True
    assert payload["defer_reason"] == "PILLAR_WARMUP"
    assert payload["price_motion_source"] == "missing"
    assert payload["price_motion_age_ms"] is None
    assert payload["price_motion_ready"] is False
    assert payload["compact_trace"]["defer_reason"] == "PILLAR_WARMUP"
    assert payload["compact_trace"]["admission_result"] == "neutral"
    assert payload["score_lineage"]["path"]
    lineage_fields = {
        record["field"] for record in payload["score_lineage"]["records"]
    }
    assert {"pillar_sum", "raw_score", "decision_score", "score", "final_score"}.issubset(
        lineage_fields
    )

    jsonschema.validate(instance=payload, schema=schema)


def test_execution_gate_block_includes_compact_decision_trace() -> None:
    blocked: list[dict] = []
    scoring_result = ScoringResult(
        score=decimal.Decimal("0.36"),
        side="buy",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "s_linear": 0.6,
            "multiplier": 1.25,
            "s_scaled_raw": 0.75,
            "s_clamped": 0.75,
            "raw_exposure": 0.5625,
            "final_score": 0.36,
            "final_exposure": 0.36,
            "shield_multiplier": 0.64,
            "shield_reasons": ["SOFT_ATTENUATION"],
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "buy_bias_mult": 1.0,
            "sell_bias_mult": 1.0,
            "side_why": "enter:buy",
        },
        deferred=False,
        defer_reason=None,
        shield_multiplier=decimal.Decimal("0.64"),
    )
    handler = _build_handler(emit_fn=lambda *_args, **
                             _kwargs: None, scoring_result=scoring_result)
    handler._emit_strategy_blocked = lambda **kwargs: blocked.append(kwargs)
    handler.execution_gate = SimpleNamespace(
        check_entry=lambda **_kwargs: (False, "ORDERBOOK_THIN")
    )
    handler.entry_plan_calculator = SimpleNamespace(
        compute=lambda **_kwargs: SimpleNamespace(
            entry_price=decimal.Decimal("100.0"),
            stop_loss_price=decimal.Decimal("99.0"),
            take_profit_price=decimal.Decimal("101.0"),
        )
    )

    handler._process_decision(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "warmup": {"full_ready": True, "ready": {}},
            "features": {
                "price": "100.0",
                "pillar_sum": 0.6,
                "atr": 1.0,
                "obi": 0.1,
                "pillar_tactician": 0.3,
                "pillar_operator": 0.2,
                "pillar_strategist": 0.1,
                "pillar_contribs": {"tactician": 0.3, "operator": 0.2, "strategist": 0.1},
            },
        },
    )

    assert blocked[0]["reason_code"] == "EXECUTION_GATE_BLOCKED"
    trace = blocked[0]["details"]["decision_trace"]
    assert trace["final_score"] == 0.36
    assert trace["shield_multiplier"] == 0.64
    assert trace["side"] == "buy"
    assert blocked[0]["details"]["price_motion"] == {
        "source": "missing",
        "age_ms": None,
        "ready": False,
        "consumed_by_vol_gate": False,
    }


def test_anti_peak_observability_uses_admission_pre_shield_without_stage_reconstruction() -> None:
    emitted: list[tuple[str, dict]] = []
    scoring_result = ScoringResult(
        score=decimal.Decimal("0.36"),
        side="buy",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "s_linear": 0.6,
            "multiplier": 1.25,
            "s_scaled_raw": 0.75,
            "s_clamped": 0.75,
            "raw_exposure": 0.5625,
            "admission_pre_shield": 0.44,
            "sizing_pre_shield": 0.77,
            "final_score": 0.36,
            "final_exposure": 0.36,
            "shield_multiplier": 0.64,
            "shield_reasons": ["SOFT_ATTENUATION"],
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "buy_bias_mult": 1.0,
            "sell_bias_mult": 1.0,
            "side_why": "enter:buy",
        },
        deferred=False,
        defer_reason=None,
        shield_multiplier=decimal.Decimal("0.64"),
    )
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=scoring_result,
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None

    handler._process_decision(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "warmup": {"full_ready": True, "ready": {}},
            "features": {
                "price": "100.0",
                "pillar_sum": 0.6,
                "pillar_tactician": 0.3,
                "pillar_operator": 0.2,
                "pillar_strategist": 0.1,
                "pillar_contribs": {"tactician": 0.3, "operator": 0.2, "strategist": 0.1},
            },
        },
    )

    signal = [payload for name, payload in emitted if name ==
              "EVT:STRATEGY_SIGNAL_PRODUCED"][0]
    anti_peak = signal["scoring"]["anti_peak_observability"]
    assert anti_peak["score_path"]["score_before_shields"] == 0.44
    assert anti_peak["score_path"]["score_after_danger_zone"] is None
    assert anti_peak["score_path"]["score_after_context_shield"] is None
    assert anti_peak["classification"]["attenuated_below_threshold"] is False


def test_anti_peak_observability_disabled_vol_gate_snapshot_is_non_authoritative() -> None:
    emitted: list[tuple[str, dict]] = []
    scoring_result = ScoringResult(
        score=decimal.Decimal("0.36"),
        side="buy",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "admission_pre_shield": 0.44,
            "sizing_pre_shield": 0.77,
            "shield_reasons": ["SOFT_ATTENUATION"],
            "side_why": "enter:buy:score=0.3600>=thr_buy=0.1000",
        },
        deferred=False,
        defer_reason=None,
        shield_multiplier=decimal.Decimal("0.64"),
    )
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=scoring_result,
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None
    handler.vol_gates_enabled = False
    handler.anti_flat_sigma = 0.48
    handler.anti_fomo_sigma = 10.0
    handler.motion_window_sec = 300
    handler.vol_gates_config_state = {
        "enabled": False,
        "anti_flat_sigma": 0.48,
        "anti_fomo_sigma": 10.0,
        "motion_window_sec": 300,
        "anti_flat_sigma_value_source": "disabled_config_snapshot",
        "anti_fomo_sigma_value_source": "disabled_config_snapshot",
        "motion_window_sec_value_source": "disabled_config_snapshot",
        "missing_reason": "gate_disabled",
    }

    handler._process_decision(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "warmup": {"full_ready": True, "ready": {}},
            "features": {
                "price": "100.0",
                "pillar_sum": 0.6,
                "pillar_tactician": 0.3,
                "pillar_operator": 0.2,
                "pillar_strategist": 0.1,
                "pillar_contribs": {"tactician": 0.3, "operator": 0.2, "strategist": 0.1},
                "price_motion": {"pm_norm_300s": 12.0},
            },
        },
    )

    signal = [payload for name, payload in emitted if name ==
              "EVT:STRATEGY_SIGNAL_PRODUCED"][0]
    motion = signal["scoring"]["anti_peak_observability"]["motion"]
    assert motion["enabled"] is False
    assert motion["window_sec"] == 300
    assert motion["window_sec_value_source"] == "disabled_config_snapshot"
    assert motion["anti_fomo_sigma"] == 10.0
    assert motion["anti_fomo_sigma_value_source"] == "disabled_config_snapshot"
    assert motion["anti_flat_sigma"] == 0.48
    assert motion["anti_flat_sigma_value_source"] == "disabled_config_snapshot"
    assert motion["motion_norm_sigma"] == 12.0
    assert motion["anti_fomo_triggered"] is None
    assert motion["anti_flat_triggered"] is None
    assert motion["missing_reason"] == "gate_disabled"
