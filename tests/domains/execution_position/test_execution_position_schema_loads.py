"""
Phase 1 — Contract Registry Closure

Schema load test: every JSON schema file in execution_position/schemas/ must
be parseable as valid JSON and conform to basic JSON Schema structure
(has "$schema" or "type" or "properties" at root level).

This ensures schemas are not silently corrupt and load correctly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_SCHEMAS_DIR = (
    PROJECT_ROOT / "apps" / "reference" /
    "domains" / "execution_position" / "schemas"
)

# Minimum required fields — at least one must be present at schema root
_VALID_ROOT_KEYS = {"$schema", "type", "properties",
                    "allOf", "anyOf", "oneOf", "$ref", "$defs"}

# Schemas known to reference surfaces that must exist in EP schemas dir
_REQUIRED_SCHEMA_FILES = {
    "bracket_placement_failed_v1.json",
    "cmd_open_v1.json",
    "cmd_position_policy_sidecar_close_request_v1.json",
    "dec_open_v1.json",
    "execution_close_reconciled_v1.json",
    "execution_guard_blocked_v1.json",
    "execution_tidy_performed_v1.json",
    "exit_match_attempted_v1.json",
    "exit_match_failed_v1.json",
    "exposure_summary_updated_v1.json",
    "order_placed_v1.json",
    "order_rejected_v1.json",
    "order_state_changed_v1.json",
    "pending_brackets_cleared_v1.json",
    "pending_brackets_stored_v1.json",
    "position_closed_v1.json",
    "position_policy_sidecar_action_skipped_v1.json",
    "position_policy_sidecar_close_request_state_v1.json",
    "position_policy_sidecar_evaluated_v1.json",
    "position_policy_sidecar_mode_active_v1.json",
    "position_policy_sidecar_recommended_v1.json",
    "position_policy_sidecar_scores_v1.json",
    "position_policy_sidecar_suppressed_v1.json",
    "symbol_tidy_v1.json",
}


def _get_schema_files():
    """Return all .json files in EP schemas dir."""
    if not EP_SCHEMAS_DIR.exists():
        return []
    return list(EP_SCHEMAS_DIR.glob("*.json"))


def _load_schema(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class TestSchemaLoads:
    """All EP JSON schema files must load without error and have valid structure."""

    def test_schemas_directory_exists(self):
        assert EP_SCHEMAS_DIR.exists(), (
            f"EP schemas directory not found: {EP_SCHEMAS_DIR}. "
            "Create it and populate with schemas."
        )

    def test_schemas_directory_not_empty(self):
        files = _get_schema_files()
        assert len(files) >= 20, (
            f"Only {len(files)} schema files found — expected at least 20. "
            f"Directory: {EP_SCHEMAS_DIR}"
        )

    def test_required_schema_files_exist(self):
        existing = {f.name for f in _get_schema_files()}
        missing = _REQUIRED_SCHEMA_FILES - existing
        assert not missing, (
            f"{len(missing)} required schema file(s) missing from execution_position/schemas/:\n"
            + "\n".join(f"  - {name}" for name in sorted(missing))
        )

    @pytest.mark.parametrize("schema_path", _get_schema_files(), ids=lambda p: p.name)
    def test_schema_is_valid_json(self, schema_path: Path):
        """Each schema file must parse as valid JSON."""
        try:
            schema = _load_schema(schema_path)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"Schema {schema_path.name} is not valid JSON: {exc}"
            )
        assert isinstance(schema, dict), (
            f"Schema {schema_path.name} root must be a JSON object (dict), "
            f"got {type(schema).__name__}"
        )

    @pytest.mark.parametrize("schema_path", _get_schema_files(), ids=lambda p: p.name)
    def test_schema_has_valid_structure(self, schema_path: Path):
        """Each schema must have at least one valid root-level JSON Schema key."""
        schema = _load_schema(schema_path)
        has_valid_key = bool(_VALID_ROOT_KEYS.intersection(schema.keys()))
        assert has_valid_key, (
            f"Schema {schema_path.name} has no recognized JSON Schema root key. "
            f"Found keys: {list(schema.keys())}. "
            f"Expected one of: {sorted(_VALID_ROOT_KEYS)}"
        )

    @pytest.mark.parametrize("schema_path", _get_schema_files(), ids=lambda p: p.name)
    def test_schema_has_title_or_description(self, schema_path: Path):
        """Each schema should have a title or description for documentation purposes."""
        schema = _load_schema(schema_path)
        has_docs = "title" in schema or "description" in schema
        if not has_docs:
            pytest.xfail(
                f"Schema {schema_path.name} has no title or description — "
                "documentation gap (non-blocking)."
            )

    def test_schema_names_match_event_verbs(self):
        """
        Schema filenames should follow the pattern <verb_lower>_v<N>.json.

        E.g., bracket_placement_failed_v1.json corresponds to EVT:BRACKET_PLACEMENT_FAILED.
        This test cross-checks that filenames are not obviously wrong.
        """
        files = _get_schema_files()
        bad_names = []
        for f in files:
            name = f.stem  # e.g. bracket_placement_failed_v1
            parts = name.rsplit("_v", 1)
            if len(parts) != 2:
                bad_names.append(f.name)
                continue
            try:
                int(parts[1])
            except ValueError:
                bad_names.append(f.name)

        assert not bad_names, (
            f"Schema files with non-standard naming (expected <verb>_v<N>.json):\n"
            + "\n".join(f"  - {name}" for name in sorted(bad_names))
        )
