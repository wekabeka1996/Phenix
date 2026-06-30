"""
Phase 1 — Contract Registry Closure

Static test: every (CMD|EVT|ERR|DEC):<VERB> string literal found in execution_position source
must be registered in verb_registry_v1.yaml AND present in domain_dict.json
(either as an import OR an export).

This prevents registry/domain-dict drift as the domain evolves.
"""
from __future__ import annotations

import json
import re
import ast
from pathlib import Path
from typing import Set

import yaml
import pytest

from apps.reference.domains.execution_position.contract_layer.emitted_surface_audit import (
    _KNOWN_DOMAIN_DICT_EXCEPTIONS,
    _KNOWN_REGISTRY_EXCEPTIONS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
VERB_REGISTRY = PROJECT_ROOT / "apps" / "reference" / \
    "dictionaries" / "verb_registry_v1.yaml"
DOMAIN_DICT = EP_DIR / "domain_dict.json"

# Pattern matching action-bearing surface identifiers
_SURFACE_RE = re.compile(r'\b(CMD|EVT|ERR|DEC|ASK):[A-Z][A-Z0-9_]+')

# Surfaces that appear in EP source as string literals but are NOT emitted by EP
# (they are consumed/received or are path labels, not emitted event names).
_KNOWN_CONSUMED_OR_LABEL: Set[str] = {
    # Consumed imports (EP is listener/handler, not emitter)
    "EVT:TRADE_INTENT_PROPOSED",
    "EVT:PORTFOLIO_STATE_UPDATED",
    "EVT:FEATURES_CALCULATED",
    "EVT:REGIME_DETECTED",
    "EVT:ORDER_ACK",
    "EVT:ORDER_FILL",
    "CMD:CLOSE",            # EP receives this; decision_making emits it
    "CMD:EXTERNAL_OPEN_REQUEST_V1",  # EP listens to this from shadow_telemetry
    # Path/trace labels (string constants used in log messages, not actual event names)
    "EVT:",                 # bare prefix used in format strings
}


def _get_docstring_nodes(tree: ast.AST) -> Set[int]:
    """Return line numbers of AST nodes that are docstrings (first expr in module/class/func)."""
    docstring_lines: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                val = body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    docstring_lines.add(val.lineno)
    return docstring_lines


def _collect_emitted_surfaces() -> Set[str]:
    """
    Collect all surface identifiers found as non-docstring string literals in EP .py source.

    Returns surfaces that EP owns/emits — after excluding known consumed/label strings
    and strings that appear only in docstrings or comments.
    """
    found: Set[str] = set()
    py_files = list(EP_DIR.rglob("*.py"))

    for py_file in py_files:
        if "__pycache__" in str(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            # Fall back to regex on raw text if AST parse fails (should not happen)
            for m in _SURFACE_RE.finditer(source):
                found.add(m.group())
            continue

        # Identify docstring line numbers to exclude them
        docstring_lines = _get_docstring_nodes(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Skip docstrings — they appear in narrative text, not as actual emitted names
                if node.lineno in docstring_lines:
                    continue
                for m in _SURFACE_RE.finditer(node.value):
                    found.add(m.group())

    return found - _KNOWN_CONSUMED_OR_LABEL


def _load_registry() -> Set[str]:
    """Parse verb_registry_v1.yaml and return set of registered surface IDs like 'CMD:OPEN'.

    The YAML structure is: {version: 1, registry: [{op: CMD, verb: OPEN, ...}, ...]}
    """
    with VERB_REGISTRY.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    # Handle both list-at-root and {registry: [...]} wrapper
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("registry", [])
    else:
        return set()

    registered: Set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        op = entry.get("op", "")
        verb = entry.get("verb", "")
        if op and verb:
            registered.add(f"{op}:{verb}")
    return registered


def _load_domain_dict_surfaces() -> Set[str]:
    """Return all event_name values from domain_dict.json (imports + exports)."""
    with DOMAIN_DICT.open(encoding="utf-8") as fh:
        dd = json.load(fh)

    surfaces: Set[str] = set()
    for entry in dd.get("imports", []):
        surfaces.add(entry["event_name"])
    for entry in dd.get("exports", []):
        surfaces.add(entry["event_name"])
    return surfaces


class TestRegistrySurfaceSync:
    """Every surface emitted in EP source must be registered in registry + domain_dict."""

    def test_all_emitted_surfaces_in_verb_registry(self):
        emitted = _collect_emitted_surfaces()
        registered = _load_registry()

        # Co-emitters: EP legitimately emits these but owner is another domain
        co_emitter_surfaces = {
            "EVT:TRADE_EXECUTED",       # owner: position_tracking, EP watchdog co-emits
            "EVT:TRADE_INTENT_REJECTED",  # owner: decision_making, EP co-emits at intake
            "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1",  # EP emits but schema not in EP dir
        }

        unregistered = (
            emitted - registered - co_emitter_surfaces - _KNOWN_REGISTRY_EXCEPTIONS
        )
        assert not unregistered, (
            f"execution_position emits {len(unregistered)} surface(s) missing from "
            f"verb_registry_v1.yaml:\n"
            + "\n".join(f"  - {s}" for s in sorted(unregistered))
            + "\n\nFix: add these to apps/reference/dictionaries/verb_registry_v1.yaml "
            "with correct op, verb, owner, status, schema."
        )

    def test_all_emitted_surfaces_in_domain_dict(self):
        emitted = _collect_emitted_surfaces()
        domain_dict_surfaces = _load_domain_dict_surfaces()

        # Surfaces that EP emits but are documented as co-emitter (owner is elsewhere)
        co_emitter_or_external = {
            "EVT:TRADE_EXECUTED",
            "EVT:TRADE_INTENT_REJECTED",
            "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1",
            # Listening to its own events (bus loopback internal)
            "EVT:ORDER_STATE_CHANGED",
            "EVT:EXECUTION_CLOSE_RECONCILED",
            "EVT:SYMBOL_TIDY",
        }

        missing_from_dd = (
            emitted
            - domain_dict_surfaces
            - co_emitter_or_external
            - _KNOWN_DOMAIN_DICT_EXCEPTIONS
        )
        assert not missing_from_dd, (
            f"execution_position emits {len(missing_from_dd)} surface(s) missing from "
            f"domain_dict.json (neither in imports nor exports):\n"
            + "\n".join(f"  - {s}" for s in sorted(missing_from_dd))
            + "\n\nFix: add these to domain_dict.json under 'exports' with correct target_domains."
        )

    def test_emitter_inventory_is_non_empty(self):
        """Sanity: the scan must find at least the known core surfaces."""
        emitted = _collect_emitted_surfaces()
        must_find = {
            "EVT:EXECUTION_GUARD_BLOCKED",
            "EVT:BRACKET_PLACEMENT_FAILED",
            "DEC:OPEN",
            "CMD:OPEN",
        }
        missing = must_find - emitted
        assert not missing, (
            f"Emitter scan failed to find expected surfaces: {missing}. "
            "Check _SURFACE_RE pattern or _KNOWN_CONSUMED_OR_LABEL exclusion list."
        )

    def test_registry_loads_without_error(self):
        """Registry file must parse without error."""
        registered = _load_registry()
        assert len(registered) > 50, (
            f"Registry loaded only {len(registered)} entries — suspiciously low. "
            "Check verb_registry_v1.yaml structure."
        )

    def test_domain_dict_has_required_exports(self):
        """domain_dict.json exports must include the known P0/P1 surfaces."""
        dd_exports = set()
        with DOMAIN_DICT.open(encoding="utf-8") as fh:
            dd = json.load(fh)
        for entry in dd.get("exports", []):
            dd_exports.add(entry["event_name"])

        required = {
            "EVT:BRACKET_PLACEMENT_FAILED",
            "EVT:EXECUTION_GUARD_BLOCKED",
            "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE",
            "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST",
            "DEC:OPEN",
            "DEC:CLOSE",
            "EVT:ORDER_PLACED",
            "EVT:ORDER_REJECTED",
            "EVT:POSITION_CLOSED",
            "EVT:EXPOSURE_SUMMARY_UPDATED",
        }
        missing = required - dd_exports
        assert not missing, (
            f"domain_dict.json missing required exports: {sorted(missing)}. "
            "These surfaces are P0/P1 from execution_position_defect_ledger.md."
        )
