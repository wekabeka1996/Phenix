"""
TopologyAuditor — Detects domain registration drift and missing domains.

Compares expected domain topology (from verb registry owners) against
actually registered domains in FSMCore. Emits EVT:TOPOLOGY_DRIFT_DETECTED
when discrepancies are found.

Usage:
    auditor = TopologyAuditor(bus)
    drift = auditor.audit()
    # drift.missing == {"risk_management", "account_balance"}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import yaml  # type: ignore[import-untyped]

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from vfoundation.core.protocol import Message

LOG = logging.getLogger(__name__)

# Default registry path
_DEFAULT_REGISTRY = "apps/reference/dictionaries/verb_registry_v1.yaml"


@dataclass
class DriftReport:
    """Result of a topology audit."""

    expected: Set[str]   # Domains listed in verb registry as owners
    registered: Set[str] # Domains registered in FSMCore
    missing: Set[str]    # Expected but not registered
    extra: Set[str]      # Registered but not in registry
    healthy: bool = True

    def __post_init__(self) -> None:
        self.missing = self.expected - self.registered
        self.extra = self.registered - self.expected
        self.healthy = len(self.missing) == 0


class TopologyAuditor:
    """
    Audits domain topology by comparing verb registry owners
    against FSMCore registered domains.

    Constitution v2.2 §7:
        TopologyAuditor generates EVT:TOPOLOGY_DRIFT_DETECTED
    """

    def __init__(
        self,
        bus: Optional[Any] = None,
        repo_root: Optional[Path] = None,
        registry_path: Optional[str] = None,
        ignore_owners: Optional[Set[str]] = None,
    ) -> None:
        """
        Args:
            bus: FSMCore instance (for reading registered domains and emitting)
            repo_root: Repository root directory. Auto-detected if None.
            registry_path: Override registry YAML path.
            ignore_owners: Set of owner names to ignore (e.g. "unknown").
        """
        self._bus = bus
        if repo_root is None:
            repo_root = self._detect_repo_root()
        self._root = repo_root
        self._registry_path = registry_path or _DEFAULT_REGISTRY
        self._ignore = ignore_owners or {"unknown"}

        # Load expected owners from verb registry
        self._expected_owners = self._load_owners()

    def audit(self) -> DriftReport:
        """
        Run topology audit.

        Returns:
            DriftReport with expected/registered/missing/extra sets.
        """
        registered: Set[str] = set()
        if self._bus is not None:
            registered = set(getattr(self._bus, "domains", {}).keys())

        report = DriftReport(
            expected=self._expected_owners,
            registered=registered,
            missing=set(),  # Computed in __post_init__
            extra=set(),
        )

        if not report.healthy:
            LOG.warning(
                "TopologyAuditor: DRIFT — missing domains: %s, extra: %s",
                report.missing, report.extra,
            )
            if self._bus is not None and hasattr(self._bus, "emit"):
                self._bus.emit(
                    "EVT:TOPOLOGY_DRIFT_DETECTED",
                    {
                        "missing": sorted(report.missing),
                        "extra": sorted(report.extra),
                    },
                    why=f"drift: {len(report.missing)} missing, {len(report.extra)} extra",
                )
        else:
            LOG.info(
                "TopologyAuditor: OK — %d domains registered, %d expected",
                len(registered), len(self._expected_owners),
            )

        return report

    def get_expected_owners(self) -> Set[str]:
        """Return the set of expected domain owners."""
        return set(self._expected_owners)

    # ── Private ──────────────────────────────────────────────────────

    def _load_owners(self) -> Set[str]:
        if not HAS_YAML:
            LOG.warning("PyYAML not installed; TopologyAuditor cannot load registry")
            return set()

        registry_file = self._root / self._registry_path
        if not registry_file.exists():
            LOG.warning("Verb registry not found: %s", registry_file)
            return set()

        with open(registry_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        owners: Set[str] = set()
        for entry in data.get("registry", []):
            owner = entry.get("owner", "unknown")
            if owner not in self._ignore:
                owners.add(owner)

        LOG.debug("TopologyAuditor: loaded %d expected owners", len(owners))
        return owners

    @staticmethod
    def _detect_repo_root() -> Path:
        p = Path(__file__).resolve()
        for parent in [p] + list(p.parents):
            if (parent / "pytest.ini").exists() or (parent / "pyproject.toml").exists():
                return parent
        return Path(__file__).resolve().parent.parent.parent
