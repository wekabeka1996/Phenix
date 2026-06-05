"""
J6-S16 — Surface Evidence Registry

Loads the canonical surface_evidence_v1.json fixture and provides
typed lookup by surface key.

Fail-closed:
- Missing artifact → registry unavailable (raises on load)
- Malformed JSON → validation error on load
- Unknown surface key → returns UNKNOWN sentinel record
- Malformed record → validation error on load (all records validated at init)

Shadow-only. Does not affect runtime execution.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import ValidationError

from apps.reference.domains.alpha_search.judge.policy_cortex.evidence_models import (
    SurfaceEvidenceRecord,
)

LOG = logging.getLogger(__name__)

# Default path relative to repo root (resolved at import time)
_DEFAULT_FIXTURE_PATH = (
    Path(__file__).parent / "surface_evidence_v1.json"
)

# UNKNOWN sentinel — returned when a surface key has no evidence
_UNKNOWN_SENTINEL_KEY = "__unknown__"


def _build_unknown_sentinel(artifact_path: str, evidence_version: str) -> SurfaceEvidenceRecord:
    """Build a typed UNKNOWN sentinel for an unrecognised surface."""
    return SurfaceEvidenceRecord(
        surface_key=_UNKNOWN_SENTINEL_KEY,
        label="UNKNOWN",
        sample_size=0,
        filled_count=0,
        source_artifact=artifact_path,
        evidence_version=evidence_version,
        limitations=["Surface key not found in evidence registry."],
    )


class SurfaceEvidenceRegistry:
    """Typed Surface Evidence Registry.

    Loads and validates the canonical JSON fixture at construction.
    Provides O(1) lookup by surface_key.

    Fail-closed:
    - FileNotFoundError if fixture is missing.
    - ValidationError if any record fails Pydantic validation.
    - Returns UNKNOWN sentinel for unrecognised keys (does not silently pass).
    """

    def __init__(
        self,
        fixture_path: Optional[Path] = None,
    ) -> None:
        path = fixture_path or _DEFAULT_FIXTURE_PATH
        self._artifact_path = str(path)
        self._index: Dict[str, SurfaceEvidenceRecord] = {}
        self._evidence_version: str = "unknown"
        self._loaded_at: str = datetime.now(tz=timezone.utc).isoformat()
        self._load(path)

    def _load(self, path: Path) -> None:
        """Load and validate the fixture. Raises on any error (fail-closed)."""
        if not path.exists():
            raise FileNotFoundError(
                f"Surface evidence fixture not found: {path}. "
                "Registry unavailable — policy cortex will classify all candidates as UNKNOWN."
            )

        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        schema_version = raw.get("schema_version", "")
        if schema_version != "1":
            raise ValueError(
                f"Surface evidence fixture has unsupported schema_version={schema_version!r}. "
                "Expected '1'."
            )

        self._evidence_version = str(raw.get("evidence_version", "unknown"))
        surfaces_raw: List[dict] = raw.get("surfaces", [])

        validation_errors: List[str] = []
        for i, surface_raw in enumerate(surfaces_raw):
            # Stamp loaded_at
            surface_raw = dict(surface_raw)
            surface_raw["loaded_at"] = self._loaded_at

            try:
                record = SurfaceEvidenceRecord.model_validate(surface_raw)
            except ValidationError as exc:
                validation_errors.append(
                    f"Record[{i}] surface_key={surface_raw.get('surface_key', '?')!r}: {exc}"
                )
                continue

            if record.surface_key in self._index:
                raise ValueError(
                    f"Duplicate surface_key in fixture: {record.surface_key!r}"
                )
            self._index[record.surface_key] = record

        if validation_errors:
            raise ValueError(
                f"Surface evidence fixture validation failed ({len(validation_errors)} errors):\n"
                + "\n".join(validation_errors)
            )

        LOG.info(
            "SurfaceEvidenceRegistry loaded %d surfaces from %s (version=%s)",
            len(self._index),
            path,
            self._evidence_version,
        )

    @property
    def evidence_version(self) -> str:
        return self._evidence_version

    @property
    def artifact_path(self) -> str:
        return self._artifact_path

    @property
    def surface_keys(self) -> List[str]:
        return list(self._index.keys())

    def lookup(self, surface_key: str) -> SurfaceEvidenceRecord:
        """Lookup a surface by key.

        Returns the matched SurfaceEvidenceRecord, or an UNKNOWN sentinel
        if the key is not found. Does NOT silently allow unknown surfaces.
        """
        record = self._index.get(surface_key)
        if record is None:
            LOG.debug(
                "SurfaceEvidenceRegistry: surface_key=%r not found → returning UNKNOWN sentinel",
                surface_key,
            )
            return _build_unknown_sentinel(self._artifact_path, self._evidence_version)
        return record

    def is_available(self) -> bool:
        """True if the registry has loaded at least one surface."""
        return bool(self._index)


# Module-level singleton (lazy-initialized per process)
_DEFAULT_REGISTRY: Optional[SurfaceEvidenceRegistry] = None


def get_default_registry() -> SurfaceEvidenceRegistry:
    """Return the process-level default registry (lazy singleton).

    Raises on first access if the fixture is missing or malformed (fail-closed).
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = SurfaceEvidenceRegistry()
    return _DEFAULT_REGISTRY


def reset_default_registry() -> None:
    """Reset the lazy singleton (used in tests)."""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
