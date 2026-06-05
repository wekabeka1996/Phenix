from __future__ import annotations

from pathlib import Path

from tests.domains.alpha_search.judge.central_brain.test_judge_runtime_shadow_pipeline import (
    build,
)


FILES = (
    Path("apps/reference/domains/alpha_search/judge/central_brain/shadow_pipeline.py"),
    Path("apps/reference/domains/alpha_search/judge/central_brain/runtime_capture.py"),
    Path("apps/reference/domains/alpha_search/judge/central_brain/shadow_capture_writer.py"),
    Path("tools/judge/enrich_shadow_calibration_outcomes.py"),
)


def text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in FILES)


def test_runtime_shadow_files_have_no_order_or_exchange_path():
    combined = text()
    for forbidden in (
        "execution_position",
        "OrderExecutor",
        "exchange_adapter",
        "PLACE_ORDER",
        "CMD:OPEN",
        "CMD:CLOSE",
        "binance",
    ):
        assert forbidden not in combined


def test_bridge_decision_is_no_effect():
    artifacts = build()
    assert artifacts.bridge_decision.applied is False
    assert artifacts.bridge_decision.no_effect is True
    assert artifacts.bridge_decision.bridge_action in {"record_only", "skip", "blocked"}


def test_runtime_capture_does_not_enable_live_or_hybrid_modes():
    combined = text()
    assert "live_gated" not in combined
    assert "hybrid_gated" not in combined
