"""Typed additive result surfaces for Phase 8A contract-layer helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EmittedSurfaceAuditResult:
    """Snapshot of the active emitted-surface audit state."""

    emitted_surfaces: frozenset[str]
    domain_dict_surfaces: frozenset[str]
    registry_surfaces: frozenset[str]
    missing_from_domain_dict: frozenset[str]
    missing_from_registry: frozenset[str]
    scanned_files: tuple[Path, ...]


__all__ = ["EmittedSurfaceAuditResult"]
