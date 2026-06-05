from __future__ import annotations

from pathlib import Path

from apps.reference.domains.alpha_search.judge.central_brain.envelope_builder import (
    build_judge_evidence_envelope,
)
from apps.reference.domains.alpha_search.judge.central_brain.meta_scorer import (
    score_judge_envelope,
)

from tests.domains.alpha_search.judge.central_brain.test_judge_policy_verdict_contract import (
    valid_config,
)


CENTRAL_BRAIN_FILES = (
    Path("apps/reference/domains/alpha_search/judge/central_brain/contracts.py"),
    Path("apps/reference/domains/alpha_search/judge/central_brain/envelope_builder.py"),
    Path("apps/reference/domains/alpha_search/judge/central_brain/meta_scorer.py"),
    Path("apps/reference/domains/alpha_search/judge/central_brain/verdict.py"),
)
FORBIDDEN_TEXT = (
    "execution_position",
    "judge_bridge",
    "QuadraticScoringKernel",
    "CMD:",
    "DEC:",
    "PLACE_ORDER",
    "OrderExecutor",
    "canonical_intent",
    "intent_builder",
    "verdict_synthesizer",
    "policy_cortex",
)


def _central_brain_runtime_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in CENTRAL_BRAIN_FILES
    )


def test_meta_scorer_imports_no_authority_or_execution_surfaces():
    text = _central_brain_runtime_text()
    for forbidden in FORBIDDEN_TEXT:
        assert forbidden not in text


def test_scorer_output_is_shadow_only_and_never_applied():
    verdict = score_judge_envelope(
        build_judge_evidence_envelope(symbol="BTCUSDT", created_ts_ms=1000),
        valid_config(),
    )
    assert verdict.authority_status == "shadow_only"
    assert verdict.applied is False
    assert verdict.policy_context.bridge_mode == "none"


def test_no_yaml_or_registry_dependency_introduced():
    text = _central_brain_runtime_text()
    assert "verb_registry" not in text
    assert "config/aurora" not in text
    assert "yaml" not in text.lower()
