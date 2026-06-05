from __future__ import annotations

from pathlib import Path

from apps.reference.domains.alpha_search.judge.central_brain.envelope_builder import (
    build_judge_evidence_envelope,
)


CENTRAL_BRAIN_FILES = (
    Path("apps/reference/domains/alpha_search/judge/central_brain/contracts.py"),
    Path("apps/reference/domains/alpha_search/judge/central_brain/envelope_builder.py"),
)
FORBIDDEN_TEXT = (
    "execution_position",
    "judge_bridge",
    "QuadraticScoringKernel",
    "CMD:",
    "DEC:",
    "PLACE_ORDER",
    "OrderExecutor",
    "verdict_synthesizer",
    "chamber_aggregator",
    "policy_cortex",
)


def _central_brain_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in CENTRAL_BRAIN_FILES
    )


def test_central_brain_imports_no_authority_or_execution_surfaces():
    text = _central_brain_text()
    for forbidden in FORBIDDEN_TEXT:
        assert forbidden not in text


def test_envelope_output_has_no_final_authority_fields():
    envelope = build_judge_evidence_envelope(symbol="BTCUSDT", created_ts_ms=1000)
    dumped = envelope.model_dump()
    forbidden = {
        "verdict",
        "judge_confidence",
        "final_confidence",
        "action",
        "allow",
        "suppress",
        "cmd",
        "command",
    }
    assert forbidden.isdisjoint(dumped)
    assert dumped["authority_status"] == "evidence_only"


def test_central_brain_has_no_yaml_or_registry_dependency():
    text = _central_brain_text()
    assert "verb_registry" not in text
    assert "config/aurora" not in text
    assert "yaml" not in text.lower()
