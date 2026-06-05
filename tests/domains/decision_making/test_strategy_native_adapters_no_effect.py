from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MR_ADAPTER = PROJECT_ROOT / "apps/reference/domains/strategies/runtimes/mean_reversion/native_expert_adapter.py"
MD_ADAPTER = PROJECT_ROOT / "apps/reference/domains/strategies/runtimes/md_amr/native_expert_adapter.py"
MR_HANDLER = PROJECT_ROOT / "apps/reference/domains/strategies/runtimes/mean_reversion/handler.py"
MD_HANDLER = PROJECT_ROOT / "apps/reference/domains/strategies/runtimes/md_amr/handler.py"
REGISTRY = PROJECT_ROOT / "apps/reference/dictionaries/verb_registry_v1.yaml"


FORBIDDEN_ADAPTER_PATTERNS = (
    "execution_position",
    "judge_bridge",
    "QuadraticScoringKernel",
    "CMD:",
    "DEC:",
    "PLACE_ORDER",
    "OrderExecutor",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_strategy_native_adapters_have_no_forbidden_authority_references() -> None:
    for path in (MR_ADAPTER, MD_ADAPTER):
        content = _text(path)
        for pattern in FORBIDDEN_ADAPTER_PATTERNS:
            assert pattern not in content, f"{path} contains forbidden pattern {pattern!r}"


def test_strategy_handlers_are_not_wired_to_phase_4_adapters() -> None:
    assert "native_expert_adapter" not in _text(MR_HANDLER)
    assert "native_expert_adapter" not in _text(MD_HANDLER)


def test_phase_4_events_are_not_registered() -> None:
    registry = _text(REGISTRY)

    assert "EVT:MEAN_REVERSION_EXPERT_OUTPUT_V1" not in registry
    assert "EVT:MDAMR_EXPERT_OUTPUT_V1" not in registry
