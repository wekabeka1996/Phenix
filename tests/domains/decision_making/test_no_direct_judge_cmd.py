from __future__ import annotations

from pathlib import Path


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_judge_bridge_has_no_direct_execution_or_command_path():
    text = _text("apps/reference/domains/decision_making/judge_bridge.py")
    forbidden = (
        "execution_position",
        "OrderExecutor",
        "PLACE_ORDER",
        "CMD:OPEN",
        "CMD:CLOSE",
        "exchange_adapter",
        "binance",
        "intent.emitter",
        "canonical_intent",
    )
    for item in forbidden:
        assert item not in text


def test_phase_6_central_brain_still_has_no_decisionmaking_bridge_import():
    phase6_files = (
        Path("apps/reference/domains/alpha_search/judge/central_brain/contracts.py"),
        Path("apps/reference/domains/alpha_search/judge/central_brain/envelope_builder.py"),
        Path("apps/reference/domains/alpha_search/judge/central_brain/meta_scorer.py"),
        Path("apps/reference/domains/alpha_search/judge/central_brain/verdict.py"),
    )
    central_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in phase6_files
    )
    assert "judge_bridge" not in central_text
    assert "decision_making" not in central_text
