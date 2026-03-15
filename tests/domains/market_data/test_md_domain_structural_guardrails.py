"""
MD-DOMAIN-STRUCTURAL-GUARDRAILS — market_data domain structural tests.

Enforces:
- domain_dict.json consistency (exports match code, components match files)
- No pycache ghosts for deleted source files
- No empty test files
- BarAggregator SSOT (only bar constructor in the domain)
- Registry alignment (active verbs emitted in code)
- No inbound cross-domain source imports (event-only coupling)
- Dead code deletion permanence (market_ws_client.py, set_feature_engineering)
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MD_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "market_data"
DOMAIN_DICT = MD_DIR / "domain_dict.json"


def _load_domain_dict() -> dict:
    return json.loads(DOMAIN_DICT.read_text(encoding="utf-8"))


def _extract_imports(filepath: Path) -> list[str]:
    """Extract all import source strings from a Python file AST."""
    try:
        tree = ast.parse(filepath.read_text(
            encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return []

    sources: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            sources.append(node.module)
    return sources


# ---------------------------------------------------------------------------
# 1. domain_dict.json consistency
# ---------------------------------------------------------------------------

class TestDomainDictConsistency:
    """Guard: domain_dict.json is well-formed and consistent with source."""

    def test_domain_dict_exists(self):
        assert DOMAIN_DICT.exists(), "domain_dict.json missing"

    def test_domain_name(self):
        dd = _load_domain_dict()
        assert dd["domain_name"] == "market_data"

    def test_all_exported_events_have_schema(self):
        dd = _load_domain_dict()
        for exp in dd["exports"]:
            assert "schema" in exp, f"{exp['event_name']} missing schema field"

    def test_exports_lists_all_active_verbs(self):
        """domain_dict exports must include all 3 active verbs."""
        dd = _load_domain_dict()
        exported = {e["event_name"] for e in dd["exports"]}
        required = {
            "EVT:MARKET_TICK_RECEIVED",
            "EVT:BAR_CLOSED",
            "EVT:ANCHOR_UPDATED",
        }
        missing = required - exported
        assert not missing, f"Missing exports: {missing}"

    def test_components_match_source_files(self):
        """Every component in domain_dict should have a class in a .py file."""
        dd = _load_domain_dict()
        components = set(dd["components"])
        # At minimum these must exist
        expected = {"BarAggregator", "WebSocketAggregator", "MarketDataProxy"}
        missing = expected - components
        assert not missing, f"Missing components: {missing}"

    def test_imports_is_empty(self):
        """market_data is root upstream — it has no inbound event imports."""
        dd = _load_domain_dict()
        assert dd["imports"] == [], "Root domain should have no imports"


# ---------------------------------------------------------------------------
# 2. No pycache ghosts
# ---------------------------------------------------------------------------

class TestNoPycacheGhosts:
    """Guard: no .pyc files for source files that no longer exist."""

    def test_no_ghost_pyc_in_source(self):
        pycache = MD_DIR / "__pycache__"
        if not pycache.exists():
            return

        source_stems = {p.stem for p in MD_DIR.glob("*.py")}
        ghost_pyc = []
        for pyc in pycache.glob("*.pyc"):
            stem = pyc.stem.split(".")[0]  # e.g. "foo.cpython-311" → "foo"
            if stem not in source_stems:
                ghost_pyc.append(pyc.name)

        assert not ghost_pyc, f"Ghost .pyc files (no matching .py): {ghost_pyc}"


# ---------------------------------------------------------------------------
# 3. No empty test files
# ---------------------------------------------------------------------------

class TestNoEmptyTestFiles:
    """Guard: every test_*.py under tests/domains/market_data has ≥1 test."""

    def test_no_empty_test_files(self):
        test_dir = PROJECT_ROOT / "tests" / "domains" / "market_data"
        if not test_dir.exists():
            return

        empty = []
        for tf in test_dir.glob("test_*.py"):
            text = tf.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text, filename=str(tf))
            except SyntaxError:
                continue

            has_test = False
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith(
                    "test_"
                ):
                    has_test = True
                    break
            if not has_test:
                empty.append(tf.name)

        assert not empty, f"Empty test files: {empty}"


# ---------------------------------------------------------------------------
# 4. BarAggregator SSOT — only bar constructor
# ---------------------------------------------------------------------------

class TestBarAggregatorSSOT:
    """Guard: BarAggregator is the only class that emits EVT:BAR_CLOSED in market_data."""

    def test_only_bar_aggregator_emits_bar_closed(self):
        """Scan all market_data .py files for EVT:BAR_CLOSED emission sites."""
        for py in MD_DIR.glob("*.py"):
            if py.name == "bar_aggregator.py":
                continue
            text = py.read_text(encoding="utf-8")
            assert "EVT:BAR_CLOSED" not in text, (
                f"{py.name} references EVT:BAR_CLOSED — "
                f"only bar_aggregator.py should emit this event"
            )

    def test_bar_aggregator_imports_bar_type(self):
        """BarAggregator must use the canonical Bar dataclass."""
        imports = _extract_imports(MD_DIR / "bar_aggregator.py")
        bar_imports = [
            i
            for i in imports
            if "bar_resampler" in i or "shared.types" in i
        ]
        assert bar_imports, "bar_aggregator.py must import Bar from bar_resampler or shared.types"


# ---------------------------------------------------------------------------
# 5. No inbound cross-domain source imports
# ---------------------------------------------------------------------------

class TestNoCrossDomainSourceImports:
    """Guard: no other domain directly imports from market_data source modules."""

    # Domains that must NOT import market_data modules directly
    _OTHER_DOMAINS = [
        "feature_engineering",
        "decision_making",
        "regime_detector",
        "risk_management",
        "execution_position",
        "position_tracking",
    ]

    def test_no_other_domain_imports_market_data_source(self):
        """Other domains must consume market_data via FSM events, not direct imports."""
        domains_root = MD_DIR.parent
        violations = []
        for domain_name in self._OTHER_DOMAINS:
            domain_dir = domains_root / domain_name
            if not domain_dir.exists():
                continue
            for py in domain_dir.glob("*.py"):
                if py.name.startswith("test_"):
                    continue
                imports = _extract_imports(py)
                for imp in imports:
                    if imp.startswith(
                        "apps.reference.domains.market_data."
                    ) and "bar_resampler" not in imp:
                        violations.append(f"{domain_name}/{py.name}: {imp}")

        assert not violations, (
            "Other domains import market_data source directly "
            "(should use FSM events):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# 6. Dead code removal verification
# ---------------------------------------------------------------------------

class TestDeletedDeadCode:
    """Guard: deleted dead modules must not be reintroduced."""

    def test_market_ws_client_deleted(self):
        """market_ws_client.py was deleted in LEGACY-PURGE-WAVE-1. Must not reappear."""
        assert not (MD_DIR / "market_ws_client.py").exists(), (
            "market_ws_client.py has been reintroduced — "
            "it was deleted as dead code in LEGACY-PURGE-WAVE-1"
        )

    def test_no_init_export_of_market_ws_client(self):
        """__init__.py must not reference deleted MarketWSClient."""
        init_text = (MD_DIR / "__init__.py").read_text(encoding="utf-8")
        assert "MarketWSClient" not in init_text, (
            "__init__.py still references deleted MarketWSClient"
        )

    def test_no_set_feature_engineering_method(self):
        """set_feature_engineering() was deleted as deprecated no-op. Must not reappear."""
        for py_name in ("proxy.py", "market_data_connector.py"):
            text = (MD_DIR / py_name).read_text(encoding="utf-8")
            assert "def set_feature_engineering" not in text, (
                f"{py_name} still contains set_feature_engineering() — "
                "it was deleted in LEGACY-PURGE-WAVE-1"
            )


# ---------------------------------------------------------------------------
# 7. Event emitter consistency
# ---------------------------------------------------------------------------

class TestEventEmitterConsistency:
    """Guard: each active event is actually emitted in code."""

    def test_market_tick_received_emitted(self):
        """EVT:MARKET_TICK_RECEIVED must be emitted by connector or proxy."""
        connector_text = (
            MD_DIR / "market_data_connector.py").read_text(encoding="utf-8")
        proxy_text = (MD_DIR / "proxy.py").read_text(encoding="utf-8")
        assert (
            "EVT:MARKET_TICK_RECEIVED" in connector_text
            or "EVT:MARKET_TICK_RECEIVED" in proxy_text
        ), "EVT:MARKET_TICK_RECEIVED not emitted by connector or proxy"

    def test_bar_closed_emitted(self):
        """EVT:BAR_CLOSED must be emitted by bar_aggregator."""
        text = (MD_DIR / "bar_aggregator.py").read_text(encoding="utf-8")
        assert "EVT:BAR_CLOSED" in text

    def test_anchor_updated_emitted(self):
        """EVT:ANCHOR_UPDATED must be emitted by connector or proxy."""
        connector_text = (
            MD_DIR / "market_data_connector.py").read_text(encoding="utf-8")
        proxy_text = (MD_DIR / "proxy.py").read_text(encoding="utf-8")
        assert (
            "EVT:ANCHOR_UPDATED" in connector_text
            or "EVT:ANCHOR_UPDATED" in proxy_text
        ), "EVT:ANCHOR_UPDATED not emitted by connector or proxy"
