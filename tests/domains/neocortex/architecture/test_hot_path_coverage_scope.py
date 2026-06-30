from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

import yaml

from tests.domains.neocortex.architecture.test_import_boundaries import (
    INVENTORY,
)


SCOPE_DOC = Path("docs/DeepMind/inventory/neocortex_hot_path_scope_phase4.md")

EXPECTED_MYPY_TARGET_FILES = sorted(
    [
        "apps/reference/domains/neocortex/main.py",
        "apps/reference/domains/neocortex/config_models.py",
        "apps/reference/domains/neocortex/contracts/causal_time.py",
        "apps/reference/domains/neocortex/contracts/control_decision.py",
        "apps/reference/domains/neocortex/contracts/decision_outcome_ledger.py",
        "apps/reference/domains/neocortex/contracts/failure_taxonomy.py",
        "apps/reference/domains/neocortex/contracts/observation_envelope.py",
        "apps/reference/domains/neocortex/logic/datasets/time_provenance.py",
        "apps/reference/domains/neocortex/logic/failure_ledger.py",
        "apps/reference/domains/neocortex/logic/gates/shadow.py",
        "apps/reference/domains/neocortex/logic/ledger/decision_outcome_ledger.py",
        "apps/reference/domains/neocortex/logic/ingest/normalizer.py",
        "apps/reference/domains/neocortex/logic/ingest/observation.py",
        "apps/reference/domains/neocortex/logic/ingest/parser.py",
        "apps/reference/domains/neocortex/logic/ingest/state_aggregator_v2.py",
        "apps/reference/domains/neocortex/logic/ingest/parsers/core_parser.py",
        "apps/reference/domains/neocortex/logic/ingest/parsers/feature_parser.py",
        "apps/reference/domains/neocortex/logic/ingest/parsers/order_parser.py",
        "apps/reference/domains/neocortex/logic/ingest/parsers/wallclock.py",
        "apps/reference/domains/neocortex/logic/brain/baseline_inference.py",
        "apps/reference/domains/neocortex/transport/authority_bridge.py",
    ]
)

EXPECTED_COVERAGE_TARGET_MODULES = sorted(
    [
        "apps.reference.domains.neocortex.config_models",
        "apps.reference.domains.neocortex.contracts.causal_time",
        "apps.reference.domains.neocortex.contracts.control_decision",
        "apps.reference.domains.neocortex.contracts.decision_outcome_ledger",
        "apps.reference.domains.neocortex.contracts.failure_taxonomy",
        "apps.reference.domains.neocortex.contracts.observation_envelope",
        "apps.reference.domains.neocortex.main",
        "apps.reference.domains.neocortex.logic.datasets.contracts",
        "apps.reference.domains.neocortex.logic.datasets.time_provenance",
        "apps.reference.domains.neocortex.logic.failure_ledger",
        "apps.reference.domains.neocortex.logic.gates.shadow",
        "apps.reference.domains.neocortex.logic.ledger.decision_outcome_ledger",
        "apps.reference.domains.neocortex.logic.ingest.normalizer",
        "apps.reference.domains.neocortex.logic.ingest.observation",
        "apps.reference.domains.neocortex.logic.ingest.parser",
        "apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2",
        "apps.reference.domains.neocortex.logic.ingest.parsers.core_parser",
        "apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser",
        "apps.reference.domains.neocortex.logic.ingest.parsers.order_parser",
        "apps.reference.domains.neocortex.logic.ingest.parsers.wallclock",
        "apps.reference.domains.neocortex.logic.brain.baseline_inference",
        "apps.reference.domains.neocortex.transport.authority_bridge",
    ]
)

ALLOWED_NON_COVERAGE_HOT_PATH = {
    "__init__.py",
    "contracts/__init__.py",
    "logic/__init__.py",
    "logic/datasets/__init__.py",
    "logic/gates/__init__.py",
    "logic/ledger/__init__.py",
    "logic/ingest/__init__.py",
    "logic/brain/__init__.py",
    "logic/ingest/parsers/__init__.py",
    "transport/__init__.py",
}


def _load_scope() -> dict[str, object]:
    text = SCOPE_DOC.read_text(encoding="utf-8")
    start = text.index("```yaml") + len("```yaml")
    end = text.index("```", start)
    return yaml.safe_load(text[start:end])


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch(normalized, pattern) for pattern in patterns)


def _relative_path_to_module(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").removesuffix(".py")
    normalized = normalized.removesuffix("/__init__")
    normalized = normalized.replace("/", ".")
    if normalized == "__init__":
        normalized = ""
    prefix = "apps.reference.domains.neocortex"
    return prefix if not normalized else f"{prefix}.{normalized}"


def test_hot_path_scope_matches_inventory() -> None:
    scope = _load_scope()["hot_path_scope"]
    included_entries = list(scope["included_modules"])  # type: ignore[index]
    included = [entry["path"] for entry in included_entries]
    excluded = [entry["path"]
                for entry in scope["excluded_modules"]]  # type: ignore[index]
    mypy_target_files = sorted(
        scope["mypy_target_files"])  # type: ignore[index]
    coverage_target_modules = sorted(
        scope["coverage_target_modules"])  # type: ignore[index]

    hot_path_files = sorted(
        path for path, cls in INVENTORY.items() if cls == "hot_path")
    non_hot_path_files = sorted(
        path for path, cls in INVENTORY.items() if cls != "hot_path")
    coverage_included_files = sorted(
        entry["path"]
        for entry in included_entries
        if bool(entry["coverage_included"])
    )
    mypy_included_files = sorted(
        entry["path"]
        for entry in included_entries
        if bool(entry["mypy_included"])
    )

    missing_includes = [
        path for path in hot_path_files if not _matches_any(path, included)
    ]
    unexpected_includes = [
        path for path in non_hot_path_files if _matches_any(path, included)
    ]
    missing_excludes = [
        path for path in non_hot_path_files if not _matches_any(path, excluded)
    ]

    assert missing_includes == [
    ], f"hot-path files not covered by scope artifact: {missing_includes}"
    assert unexpected_includes == [
    ], f"non-hot-path files incorrectly included: {unexpected_includes}"
    assert missing_excludes == [
    ], f"non-hot-path files missing from exclusions: {missing_excludes}"
    assert mypy_target_files == EXPECTED_MYPY_TARGET_FILES, (
        f"mypy target files drifted: {mypy_target_files}"
    )
    assert sorted(
        f"apps/reference/domains/neocortex/{path}" for path in mypy_included_files
    ) == EXPECTED_MYPY_TARGET_FILES, (
        f"included_modules mypy flags drifted: {mypy_included_files}"
    )
    assert set(path for path in hot_path_files if path not in coverage_included_files) == ALLOWED_NON_COVERAGE_HOT_PATH, (
        f"unexpected hot-path coverage exclusions: {sorted(set(hot_path_files) - set(coverage_included_files))}"
    )
    assert coverage_target_modules == EXPECTED_COVERAGE_TARGET_MODULES, (
        f"coverage target modules drifted: {coverage_target_modules}"
    )
    assert sorted(_relative_path_to_module(path) for path in coverage_included_files) == EXPECTED_COVERAGE_TARGET_MODULES, (
        f"included_modules coverage flags drifted: {coverage_included_files}"
    )
    # type: ignore[index]
    assert scope["source_of_truth"] == "docs/DeepMind/inventory/neocortex_surface_inventory.md"
    # type: ignore[index]
    assert scope["coverage_target"]["branch_coverage"] == "100% on declared hot-path"
    # type: ignore[index]
    assert scope["type_target"]["mypy"] == "0 errors on declared hot-path"
