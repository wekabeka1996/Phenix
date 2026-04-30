from __future__ import annotations

from pathlib import Path

import yaml


SCOPE_DOC = Path("docs/DeepMind/inventory/neocortex_hot_path_scope_phase5.md")

EXPECTED_MYPY_TARGET_FILES = [
    "apps/reference/domains/neocortex/contracts/control_decision.py",
    "apps/reference/domains/neocortex/logic/failure_ledger.py",
    "apps/reference/domains/neocortex/transport/authority_bridge.py",
]

EXPECTED_COVERAGE_TARGET_MODULES = [
    "apps.reference.domains.neocortex.contracts.control_decision",
    "apps.reference.domains.neocortex.logic.failure_ledger",
    "apps.reference.domains.neocortex.transport.authority_bridge",
]

EXPECTED_INCLUDED_PATHS = [
    "contracts/control_decision.py",
    "logic/failure_ledger.py",
    "transport/authority_bridge.py",
]

REQUIRED_EXCLUDED_PATHS = {
    "apps/reference/domains/neocortex/PPO/**/*.py",
    "apps/reference/domains/neocortex/experiments/*.py",
    "apps/reference/domains/neocortex/transport/adapter.py",
    "apps/reference/domains/neocortex/logic/telemetry.py",
}


def _load_scope() -> dict[str, object]:
    text = SCOPE_DOC.read_text(encoding="utf-8")
    start = text.index("```yaml") + len("```yaml")
    end = text.index("```", start)
    return yaml.safe_load(text[start:end])


def test_phase5_scope_matches_expected_authority_surface() -> None:
    scope = _load_scope()["phase5_hot_path_scope"]
    included_entries = list(scope["included_modules"])  # type: ignore[index]
    included_paths = [entry["path"] for entry in included_entries]
    excluded_entries = list(scope["excluded_patterns"])  # type: ignore[index]
    excluded_paths = {entry["path"] for entry in excluded_entries}

    assert included_paths == EXPECTED_INCLUDED_PATHS
    # type: ignore[index]
    assert scope["mypy_target_files"] == EXPECTED_MYPY_TARGET_FILES
    # type: ignore[index]
    assert scope["coverage_target_modules"] == EXPECTED_COVERAGE_TARGET_MODULES
    assert REQUIRED_EXCLUDED_PATHS.issubset(excluded_paths)
    # type: ignore[index]
    assert scope["coverage_target"]["branch_coverage"] == "100% on declared Phase 5 authority seam files"
    # type: ignore[index]
    assert scope["type_target"]["mypy"] == "0 errors on declared Phase 5 authority seam files"


def test_phase5_scope_marks_strategy_gateway_as_validation_only() -> None:
    scope = _load_scope()["phase5_hot_path_scope"]
    # type: ignore[index]
    validation_only = list(scope["validation_only_modules"])

    assert validation_only == [
        {
            "path": "apps/reference/domains/decision_making/gateway/strategy_gateway.py",
            "reason": "Inline authority apply/journal behavior is functionally regressed by Phase 5 seam tests, but the file is broader than the Neocortex-owned coverage target.",
        }
    ]
