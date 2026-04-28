from __future__ import annotations

import ast
from pathlib import Path

from tests.domains.neocortex.architecture.test_import_boundaries import (
    HOT_PATH_FILES,
    NEOCORTEX_ROOT,
)


ALLOWED_ANY_BOUNDARY_FILES = {
    "main.py": "json_ingress_egress",
    "logic/telemetry.py": "json_ingress_egress",
    "logic/datasets/contracts.py": "json_boundary_contract",
    "logic/datasets/hygiene.py": "json_ingress_egress",
    "logic/datasets/time_provenance.py": "json_boundary_coercion",
    "logic/evaluation/contracts.py": "json_boundary_contract",
    "logic/evaluation/evaluator.py": "json_boundary_readonly",
    "logic/gates/shadow.py": "json_boundary_config_payload",
    "logic/ingest/observation.py": "third_party_torch_boundary",
    "logic/ingest/parser.py": "json_ingress_egress",
    "logic/ingest/state_aggregator_v2.py": "json_ingress_egress",
    "logic/ingest/parsers/core_parser.py": "json_ingress_egress",
    "logic/ingest/parsers/feature_parser.py": "json_ingress_egress",
    "logic/ingest/parsers/order_parser.py": "json_ingress_egress",
    "logic/brain/baseline_inference.py": "json_ingress_egress",
}


def _find_any_occurrences(relative_path: str) -> list[int]:
    filepath = NEOCORTEX_ROOT / relative_path
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            lines.append(int(node.lineno))
    return sorted(set(lines))


def test_any_annotations_are_confined_to_allowed_boundary_files() -> None:
    offenders: list[str] = []
    allowed_hits: list[tuple[str, int]] = []
    for relative_path in HOT_PATH_FILES:
        lines = _find_any_occurrences(relative_path)
        if not lines:
            continue
        if relative_path not in ALLOWED_ANY_BOUNDARY_FILES:
            offenders.append(f"{relative_path}: {lines}")
            continue
        allowed_hits.extend((relative_path, line) for line in lines)

    assert offenders == [], f"Unexpected Any usage in hot-path business logic: {offenders}"
    assert allowed_hits, "Expected at least one boundary Any occurrence for audit evidence"

