from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    build_aurora_expert_output,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = (
    REPO_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "strategies"
    / "runtimes"
    / "aurora"
    / "native_expert_adapter.py"
)


def _representative_payload() -> dict:
    return {
        "strategy_id": "aurora",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "ts_ms": 1_700_000_010_000,
        "tf_sec": 300,
        "rid": "aurora_BTCUSDT_1700000010000",
        "decision_id": "decision-123",
        "trace_id": "trace-123",
        "source_event": "EVT:STRATEGY_SIGNAL_PRODUCED",
        "features": {
            "ts_ms": 1_700_000_009_500,
            "obi": 0.19,
            "tfi": 0.09,
            "absorption": 0.31,
            "liquidity_kappa": 0.85,
            "spread_bps": 1.8,
            "macro_resid": 0.14,
            "delta_price": 0.07,
            "volatility_state": 0.11,
            "large_trade_imbalance": -0.04,
            "pillar_sum": 0.41,
        },
        "regime_ctx": {
            "regime": "LOW_VOLATILITY",
            "confidence": 0.73,
            "regime_age_sec": 12.5,
        },
        "scoring": {
            "raw_score": 0.41,
            "decision_score": 0.41,
            "sizing_score": 0.1681,
            "score": 0.41,
            "admission_mode": "linear",
            "sizing_mode": "quadratic",
            "psi_vector": {"s_linear": 0.41},
            "score_lineage": {"records": [{"field": "decision_score"}]},
        },
        "invalidates_if": ["features_stale", "regime_stale"],
    }


def test_adapter_builds_output_from_representative_aurora_payload() -> None:
    output = build_aurora_expert_output(
        _representative_payload(),
        now_ms=1_700_000_010_500,
    )

    assert output.strategy_id == "aurora"
    assert output.question_type == "entry"
    assert output.side_opinion == "BUY"
    assert output.source_refs.rid == "aurora_BTCUSDT_1700000010000"


def test_adapter_output_is_opinion_only() -> None:
    output = build_aurora_expert_output(_representative_payload())

    assert output.authority_status == "opinion_only"


def test_adapter_does_not_mutate_input_payload() -> None:
    payload = _representative_payload()
    before = deepcopy(payload)

    build_aurora_expert_output(payload, now_ms=1_700_000_010_500)

    assert payload == before


def test_adapter_does_not_import_execution_position_or_judge_bridge() -> None:
    source = ADAPTER_PATH.read_text(encoding="utf-8")

    assert "execution_position" not in source
    assert "judge_bridge" not in source


def test_adapter_does_not_emit_cmd_or_dec_authority() -> None:
    source = ADAPTER_PATH.read_text(encoding="utf-8")

    for forbidden in ("CMD:", "DEC:", "PLACE_ORDER", "OrderExecutor"):
        assert forbidden not in source


def test_adapter_preserves_microstructure_values_exactly() -> None:
    output = build_aurora_expert_output(_representative_payload())
    evidence = output.microstructure_evidence

    assert evidence.obi == 0.19
    assert evidence.tfi == 0.09
    assert evidence.absorption == 0.31
    assert evidence.liquidity_kappa == 0.85
    assert evidence.spread_bps == 1.8
    assert evidence.macro_resid == 0.14
    assert evidence.delta_price == 0.07
    assert evidence.volatility_state == 0.11
    assert evidence.large_trade_imbalance == -0.04


def test_adapter_puts_legacy_scores_only_in_legacy_score_trace() -> None:
    output = build_aurora_expert_output(_representative_payload())
    dumped = output.model_dump()

    assert output.legacy_score_trace.pillar_sum == 0.41
    assert output.legacy_score_trace.raw_score == 0.41
    assert output.legacy_score_trace.decision_score == 0.41
    assert output.legacy_score_trace.sizing_score == 0.1681
    for forbidden in ("pillar_sum", "raw_score", "decision_score", "sizing_score"):
        assert forbidden not in dumped["microstructure_evidence"]


def test_adapter_labels_missing_fields() -> None:
    payload = _representative_payload()
    del payload["features"]["tfi"]

    output = build_aurora_expert_output(payload)

    assert output.microstructure_evidence.tfi is None
    assert output.missingness.per_field["tfi"] == "MISSING"


def test_adapter_labels_confidence_source() -> None:
    output = build_aurora_expert_output(_representative_payload())

    assert output.confidence == 0.41
    assert output.confidence_source == "decision_score_abs_legacy_trace"
    assert "CONFIDENCE_FROM_LEGACY_DECISION_SCORE" in output.reason_codes


def test_adapter_is_deterministic() -> None:
    payload = _representative_payload()
    first = build_aurora_expert_output(payload, now_ms=1_700_000_010_500)
    second = build_aurora_expert_output(payload, now_ms=1_700_000_010_500)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
