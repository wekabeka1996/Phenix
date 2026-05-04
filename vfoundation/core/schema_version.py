"""
Schema Version Registry — Phase 16.1.

Lifecycle management for versioned schemas per Constitution §10.4.
Tracks schema versions with deprecation windows and removal targets.

NOT to be confused with VerbSchemaRegistry (schema_registry.py) which
handles JSON Schema compilation for runtime validation. This module
handles schema *lifecycle* (active → deprecated → removed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SchemaStatus(Enum):
    """Lifecycle status of a versioned schema."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


@dataclass(frozen=True)
class SchemaVersion:
    """Tracked schema version with lifecycle metadata."""
    name: str                                  # e.g., "cmd_open_v1"
    version: int                               # e.g., 1
    status: SchemaStatus = SchemaStatus.ACTIVE
    deprecated_since: Optional[str] = None     # ISO date
    removal_target: Optional[str] = None       # ISO date
    successor: Optional[str] = None            # e.g., "cmd_open_v2"


class SchemaRegistry:
    """
    In-memory schema version registry with deprecation tracking.

    Constitution §10.4 requires:
    - Versioning all schemas (_v1, _v2)
    - Deprecation windows minimum 2 releases
    - Schema-budget per domain
    """

    def __init__(self) -> None:
        self._schemas: Dict[str, SchemaVersion] = {}

    def register(self, sv: SchemaVersion) -> None:
        """Register a schema version. Raises ValueError on duplicate name."""
        if sv.name in self._schemas:
            raise ValueError(f"Schema '{sv.name}' already registered")
        self._schemas[sv.name] = sv

    def get(self, name: str) -> Optional[SchemaVersion]:
        """Retrieve schema version by name. Returns None if not found."""
        return self._schemas.get(name)

    def deprecate(
        self,
        name: str,
        successor: str,
        removal_target: str,
        deprecated_since: Optional[str] = None,
    ) -> None:
        """
        Mark a schema as deprecated.

        Args:
            name: Schema to deprecate.
            successor: Name of the replacement schema.
            removal_target: ISO date when this schema will be removed.
            deprecated_since: ISO date when deprecation started. Defaults to None.

        Raises:
            KeyError: If schema not found.
        """
        old = self._schemas.get(name)
        if old is None:
            raise KeyError(f"Schema '{name}' not found in registry")
        # Replace with updated frozen dataclass instance
        self._schemas[name] = SchemaVersion(
            name=old.name,
            version=old.version,
            status=SchemaStatus.DEPRECATED,
            deprecated_since=deprecated_since,
            removal_target=removal_target,
            successor=successor,
        )

    def remove(self, name: str) -> None:
        """
        Mark a schema as removed.

        Raises:
            KeyError: If schema not found.
        """
        old = self._schemas.get(name)
        if old is None:
            raise KeyError(f"Schema '{name}' not found in registry")
        self._schemas[name] = SchemaVersion(
            name=old.name,
            version=old.version,
            status=SchemaStatus.REMOVED,
            deprecated_since=old.deprecated_since,
            removal_target=old.removal_target,
            successor=old.successor,
        )

    def active_schemas(self) -> List[SchemaVersion]:
        """Return all schemas with ACTIVE status."""
        return [sv for sv in self._schemas.values() if sv.status == SchemaStatus.ACTIVE]

    def deprecated_schemas(self) -> List[SchemaVersion]:
        """Return all schemas with DEPRECATED status."""
        return [sv for sv in self._schemas.values() if sv.status == SchemaStatus.DEPRECATED]

    def is_active(self, name: str) -> bool:
        """Check if a schema is currently active."""
        sv = self._schemas.get(name)
        return sv is not None and sv.status == SchemaStatus.ACTIVE

    def validate_no_removed_in_use(self, used_schemas: set) -> List[str]:
        """
        Check if any REMOVED schemas are still being used.

        Args:
            used_schemas: Set of schema names currently referenced in code.

        Returns:
            List of warning strings for removed schemas still in use.
        """
        warnings_list: List[str] = []
        for name in used_schemas:
            sv = self._schemas.get(name)
            if sv is not None and sv.status == SchemaStatus.REMOVED:
                warnings_list.append(
                    f"Schema '{name}' is REMOVED but still in use. "
                    f"Successor: {sv.successor or 'none'}"
                )
        return warnings_list

    def all_schemas(self) -> List[SchemaVersion]:
        """Return all registered schemas."""
        return list(self._schemas.values())
