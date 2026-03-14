"""
EP-DOMAIN-AUDIT-01 — execution_position domain structural guardrails.

Enforces:
- No stale pycache ghosts for deleted source files
- No imports of deleted modules
- domain_dict.json consistency with live file tree
- No empty ghost subpackages (aggregator_oco, observability, shadow_execpos)
- Triple OrderStatus enum remains layered (not accidentally merged)
- reasons.py completeness (ALL_REASONS matches defined constants)
- No broken test fixture imports
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"


class TestNoPycacheGhosts:
    """Guard: no __pycache__ entries for files that no longer exist."""

    def test_no_stale_root_pycache_entries(self):
        pycache = EP_DIR / "__pycache__"
        if not pycache.exists():
            return

        live_stems = {p.stem for p in EP_DIR.glob("*.py")}
        pycache_stems = set()
        for p in pycache.glob("*.pyc"):
            stem = p.name.split(".")[0]
            pycache_stems.add(stem)

        ghosts = pycache_stems - live_stems
        assert not ghosts, (
            f"Stale __pycache__ entries for deleted files: {sorted(ghosts)}. "
            "Delete these .pyc files."
        )

    def test_no_stale_infra_pycache_entries(self):
        pycache = EP_DIR / "infra" / "__pycache__"
        if not pycache.exists():
            return

        live_stems = {p.stem for p in (EP_DIR / "infra").glob("*.py")}
        pycache_stems = set()
        for p in pycache.glob("*.pyc"):
            stem = p.name.split(".")[0]
            pycache_stems.add(stem)

        ghosts = pycache_stems - live_stems
        assert not ghosts, (
            f"Stale infra/__pycache__ entries: {sorted(ghosts)}. "
            "Delete these .pyc files."
        )


class TestNoGhostSubpackages:
    """Guard: deleted subpackages must be fully removed (no pycache-only dirs)."""

    DELETED_PACKAGES = ["aggregator_oco", "observability", "shadow_execpos"]

    def test_ghost_packages_fully_removed(self):
        surviving = []
        for pkg in self.DELETED_PACKAGES:
            pkg_dir = EP_DIR / pkg
            if pkg_dir.exists():
                surviving.append(pkg)
        assert not surviving, (
            f"Ghost subpackages still exist (pycache-only): {surviving}. "
            "Remove these directories entirely."
        )


class TestNoDeletedModuleImports:
    """Guard: no live .py file imports deleted modules."""

    DELETED_FQ_PREFIXES = [
        "apps.reference.domains.execution_position.binance_execution_adapter",
        "apps.reference.domains.execution_position.brackets_config",
        "apps.reference.domains.execution_position.config",
        "apps.reference.domains.execution_position.internal_types",
        "apps.reference.domains.execution_position.manage_config",
        "apps.reference.domains.execution_position.runtime_factory",
    ]

    def _get_imports(self, filepath: Path) -> list[str]:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.level > 0:
                    names.append(
                        f"apps.reference.domains.execution_position.{node.module}")
                else:
                    names.append(node.module)
        return names

    def test_no_imports_of_deleted_modules(self):
        violations = []
        for py_file in EP_DIR.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            for imp in self._get_imports(py_file):
                for prefix in self.DELETED_FQ_PREFIXES:
                    if imp == prefix or imp.startswith(prefix + "."):
                        violations.append(f"{py_file.name} imports {imp}")

        assert not violations, (
            f"Live files import deleted modules: {violations}"
        )


class TestDomainDictConsistency:
    """Guard: domain_dict.json matches live domain state."""

    def test_domain_dict_exists(self):
        dd_path = EP_DIR / "domain_dict.json"
        assert dd_path.exists(), "domain_dict.json is missing"

    def test_domain_dict_has_ssot_notes(self):
        dd = json.loads(
            (EP_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        assert "ssot_notes" in dd, "domain_dict.json must have ssot_notes section"
        assert "order_state" in dd["ssot_notes"]
        assert "position_state" in dd["ssot_notes"]
        assert "reasons" in dd["ssot_notes"]

    def test_domain_dict_exports_match_registry_owner(self):
        """Critical EP exports must be present in domain_dict."""
        dd = json.loads(
            (EP_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        dd_exports = {e["event_name"] for e in dd.get("exports", [])}

        critical = {
            "DEC:OPEN",
            "DEC:CLOSE",
            "EVT:EXECUTION_GUARD_BLOCKED",
            "EVT:EXECUTION_CLOSE_RECONCILED",
        }
        missing_critical = critical - dd_exports
        assert not missing_critical, (
            f"Critical EP exports missing from domain_dict: {missing_critical}"
        )


class TestTripleOrderStatusLayered:
    """Guard: 3 OrderStatus enums remain separate (domain, wire, persistence)."""

    def test_contracts_order_status_exists(self):
        from apps.reference.domains.execution_position.contracts import OrderStatus
        assert hasattr(
            OrderStatus, "PLACED"), "contracts.OrderStatus must have PLACED"
        assert hasattr(
            OrderStatus, "PARTIAL"), "contracts.OrderStatus must have PARTIAL"

    def test_idempotent_cancel_order_status_exists(self):
        from apps.reference.domains.execution_position.idempotent_cancel import OrderStatus
        # Binance wire format uses different naming
        assert hasattr(
            OrderStatus, "NEW"), "idempotent_cancel.OrderStatus must have NEW"
        assert hasattr(OrderStatus, "PARTIALLY_FILLED"), (
            "idempotent_cancel.OrderStatus must have PARTIALLY_FILLED"
        )

    def test_ledger_order_status_exists(self):
        from apps.reference.domains.execution_position.infra.order_ledger import OrderStatus
        assert hasattr(
            OrderStatus, "ACTIVE"), "ledger.OrderStatus must have ACTIVE"
        assert hasattr(
            OrderStatus, "UNKNOWN"), "ledger.OrderStatus must have UNKNOWN"

    def test_order_status_enums_are_distinct(self):
        from apps.reference.domains.execution_position.contracts import (
            OrderStatus as DomainOS,
        )
        from apps.reference.domains.execution_position.idempotent_cancel import (
            OrderStatus as WireOS,
        )
        from apps.reference.domains.execution_position.infra.order_ledger import (
            OrderStatus as LedgerOS,
        )
        assert DomainOS is not WireOS, "Domain and Wire OrderStatus must be distinct"
        assert DomainOS is not LedgerOS, "Domain and Ledger OrderStatus must be distinct"
        assert WireOS is not LedgerOS, "Wire and Ledger OrderStatus must be distinct"


class TestReasonsCompleteness:
    """Guard: reasons.py ALL_REASONS matches defined constants."""

    def test_all_reasons_list_complete(self):
        from apps.reference.domains.execution_position import reasons

        # Get all uppercase string constants
        defined = {
            name for name in dir(reasons)
            if name.isupper()
            and not name.startswith("_")
            and isinstance(getattr(reasons, name), str)
            and name != "ALL_REASONS"
            and name != "BINANCE_POST_ONLY_REJECT_CODES"
        }

        listed = set(reasons.ALL_REASONS)
        missing = defined - listed
        assert not missing, (
            f"Reason constants not in ALL_REASONS: {sorted(missing)}"
        )


class TestNoEmptyTestFiles:
    """Guard: no 0-byte test files in EP test directories."""

    def test_no_empty_ep_tests(self):
        test_dir = PROJECT_ROOT / "tests" / "domains" / "execution_position"
        if not test_dir.exists():
            return

        empty = [
            p.name for p in test_dir.glob("test_*.py")
            if p.stat().st_size == 0
        ]
        assert not empty, f"Empty test files found: {empty}"
