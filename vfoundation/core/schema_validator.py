"""
Schema Validator — validates Message payloads against JSON schemas from verb registry.

Loads verb_registry_v1.yaml at startup, caches JSON schemas,
and exposes a validate_payload(op, verb, pld) function.

Usage:
    validator = SchemaValidator()
    errors = validator.validate("EVT", "BAR_CLOSED", {"symbol": "BTCUSDT", ...})
    # errors == [] means valid; non-empty list = validation errors

Integration with FSMCore:
    See `patch_emit_validation(bus, validator)` for optional wiring.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema  # type: ignore[import-untyped]

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    import yaml  # type: ignore[import-untyped]

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


LOG = logging.getLogger(__name__)

# Default registry path (relative to repo root)
_DEFAULT_REGISTRY = "apps/reference/dictionaries/verb_registry_v1.yaml"


class SchemaValidator:
    """
    Validates Message payloads against JSON schemas defined in the verb registry.

    Thread-safe: all state is populated at __init__ and then read-only.
    """

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        registry_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            repo_root: Repository root directory. Auto-detected if None.
            registry_path: Override registry YAML path (relative to repo_root).
        """
        if repo_root is None:
            repo_root = self._detect_repo_root()
        self._root = repo_root
        self._registry_path = registry_path or _DEFAULT_REGISTRY

        # (op, verb) → loaded JSON schema dict; only populated for verbs that have schema != null
        self._schemas: Dict[Tuple[str, str], dict] = {}
        # (op, verb) → schema file path string (for diagnostics)
        self._schema_paths: Dict[Tuple[str, str], str] = {}

        self._load_registry()

    # ── Public API ───────────────────────────────────────────────────

    def validate(self, op: str, verb: str, pld: Dict[str, Any]) -> List[str]:
        """
        Validate payload against the schema for (op, verb).

        Returns:
            Empty list if valid (or no schema defined).
            List of error strings if validation fails.
        """
        key = (op, verb)
        schema = self._schemas.get(key)
        if schema is None:
            return []  # No schema → always passes (lenient)

        if not HAS_JSONSCHEMA:
            LOG.warning("jsonschema not installed; cannot validate %s:%s", op, verb)
            return []

        try:
            jsonschema.validate(instance=pld, schema=schema)
            return []
        except jsonschema.ValidationError as e:
            return [f"{op}:{verb} — {e.message}"]
        except jsonschema.SchemaError as e:
            LOG.error("Invalid schema for %s:%s — %s", op, verb, e.message)
            return [f"{op}:{verb} — invalid schema: {e.message}"]

    def has_schema(self, op: str, verb: str) -> bool:
        """Check if a schema is registered for (op, verb)."""
        return (op, verb) in self._schemas

    def registered_verbs_with_schema(self) -> List[Tuple[str, str]]:
        """Return list of (op, verb) that have a schema."""
        return list(self._schemas.keys())

    # ── Private ──────────────────────────────────────────────────────

    def _load_registry(self) -> None:
        if not HAS_YAML:
            LOG.warning("PyYAML not installed; schema validation disabled")
            return

        registry_file = self._root / self._registry_path
        if not registry_file.exists():
            LOG.warning("Verb registry not found: %s", registry_file)
            return

        with open(registry_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        entries = data.get("registry", [])
        loaded = 0
        for entry in entries:
            schema_path_str = entry.get("schema")
            if not schema_path_str or schema_path_str == "null":
                continue

            op = entry["op"]
            verb = entry["verb"]
            full_path = self._root / schema_path_str

            if not full_path.exists():
                LOG.warning(
                    "Schema file missing for %s:%s — %s", op, verb, full_path
                )
                continue

            try:
                with open(full_path, encoding="utf-8") as sf:
                    schema_dict = json.load(sf)
                self._schemas[(op, verb)] = schema_dict
                self._schema_paths[(op, verb)] = schema_path_str
                loaded += 1
            except (json.JSONDecodeError, OSError) as e:
                LOG.error("Failed to load schema for %s:%s: %s", op, verb, e)

        LOG.info(
            "SchemaValidator: loaded %d schemas from %d registry entries",
            loaded, len(entries),
        )

    @staticmethod
    def _detect_repo_root() -> Path:
        """Walk up from this file to find the repo root."""
        p = Path(__file__).resolve()
        for parent in [p] + list(p.parents):
            if (parent / "pytest.ini").exists() or (parent / "pyproject.toml").exists():
                return parent
        # Fallback: 3 levels up from vfoundation/core/schema_validator.py
        return Path(__file__).resolve().parent.parent.parent


def patch_emit_validation(
    bus: Any,
    validator: Optional[SchemaValidator] = None,
    *,
    strict: bool = False,
) -> None:
    """
    Monkey-patch FSMCore.emit() to add schema validation.

    Args:
        bus: FSMCore instance
        validator: SchemaValidator instance (auto-created if None)
        strict: If True, skip emit on validation error (fail-closed).
                If False, log warning and emit anyway (fail-open, default).
    """
    if validator is None:
        validator = SchemaValidator()

    original_emit = bus.emit

    def validated_emit(
        event_name: str,
        payload: Dict[str, Any],
        why: str,
        data_ref: Optional[list] = None,
    ) -> None:
        parts = event_name.split(":", 1)
        if len(parts) == 2:
            op, verb = parts
            errors = validator.validate(op, verb, payload)
            if errors:
                LOG.warning(
                    "Schema validation failed for %s: %s", event_name, errors
                )
                if strict:
                    return  # Drop the message
        original_emit(event_name, payload, why, data_ref)

    bus.emit = validated_emit  # type: ignore[attr-defined]
