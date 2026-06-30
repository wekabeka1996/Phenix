"""Active emitted-surface audit helpers for the Phase 8A contract layer.

The new ``contract_layer`` package is intentionally excluded from the default
scan until a later phase rewires runtime imports to this package. That keeps
Phase 8A additive and avoids treating scaffold files as active emitters.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Iterable

import yaml

from apps.reference.domains.execution_position.contract_layer.typed_results import (
    EmittedSurfaceAuditResult,
)

DOMAIN_DIR = Path(__file__).resolve().parents[1]
DOMAIN_DICT_PATH = DOMAIN_DIR / "domain_dict.json"
VERB_REGISTRY_PATH = (
    DOMAIN_DIR.parents[1] / "dictionaries" / "verb_registry_v1.yaml"
)

_SURFACE_RE = re.compile(r"\b(CMD|EVT|ERR|DEC|ASK):[A-Z][A-Z0-9_]+")
_ACTIVE_SOURCE_EXCLUDES = frozenset({"__pycache__", "contract_layer"})

_KNOWN_CONSUMED_OR_LABEL = frozenset(
    {
        "EVT:TRADE_INTENT_PROPOSED",
        "EVT:PORTFOLIO_STATE_UPDATED",
        "EVT:FEATURES_CALCULATED",
        "EVT:REGIME_DETECTED",
        "EVT:ORDER_ACK",
        "EVT:ORDER_FILL",
        "CMD:CLOSE",
        "CMD:EXTERNAL_OPEN_REQUEST_V1",
        "EVT:",
    }
)

_KNOWN_DOMAIN_DICT_EXCEPTIONS = frozenset(
    {
        "EVT:TRADE_EXECUTED",
        "EVT:TRADE_INTENT_REJECTED",
        "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1",
        "EVT:ORDER_STATE_CHANGED",
        "EVT:EXECUTION_CLOSE_RECONCILED",
        "EVT:SYMBOL_TIDY",
        # Runtime-owned shadow/external execution surfaces intentionally live
        # outside the current domain dict surface inventory.
        "CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1",
        "CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1",
        "EVT:CLOSE_SHADOW_BRIDGE",
        "EVT:CLOSE_SHADOW_BRIDGE_REJECT",
        "EVT:CLOSE_SHADOW_SUBMISSION",
        "EVT:CLOSE_SHADOW_SUBMISSION_REJECT",
        "EVT:CLOSE_SHADOW_SUBMIT_BOUNDARY",
        "EVT:CLOSE_SHADOW_TRUTH_GATE",
        "EVT:LLM_BRACKET_AMEND_COMPLETED_V1",
        "EVT:LLM_BRACKET_AMEND_REJECTED_V1",
        "EVT:LLM_CLOSE_REJECTED_V1",
        "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE",
    }
)

_KNOWN_REGISTRY_EXCEPTIONS = frozenset(
    {
        "EVT:TRADE_EXECUTED",
        "EVT:TRADE_INTENT_REJECTED",
        "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1",
        "CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1",
        "CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1",
        "EVT:CLOSE_SHADOW_BRIDGE",
        "EVT:CLOSE_SHADOW_BRIDGE_REJECT",
        "EVT:CLOSE_SHADOW_SUBMISSION",
        "EVT:CLOSE_SHADOW_SUBMISSION_REJECT",
        "EVT:CLOSE_SHADOW_SUBMIT_BOUNDARY",
        "EVT:CLOSE_SHADOW_TRUTH_GATE",
        "EVT:LLM_BRACKET_AMEND_COMPLETED_V1",
        "EVT:LLM_BRACKET_AMEND_REJECTED_V1",
        "EVT:LLM_CLOSE_REJECTED_V1",
    }
)


def _iter_active_python_files(domain_dir: Path) -> tuple[Path, ...]:
    files = []
    for py_file in domain_dir.rglob("*.py"):
        if any(part in _ACTIVE_SOURCE_EXCLUDES for part in py_file.parts):
            continue
        files.append(py_file)
    return tuple(sorted(files))


def _docstring_lines(tree: ast.AST) -> frozenset[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        body = getattr(node, "body", [])
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            lines.add(value.lineno)
    return frozenset(lines)


def _collect_surface_literals(paths: Iterable[Path]) -> frozenset[str]:
    found: set[str] = set()
    for py_file in paths:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        docstring_lines = _docstring_lines(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.lineno in docstring_lines:
                continue
            for match in _SURFACE_RE.finditer(node.value):
                found.add(match.group())
    return frozenset(found)


def collect_emitted_surfaces(domain_dir: Path | None = None) -> frozenset[str]:
    """Collect active emitted-surface literals from current runtime-owned source."""
    active_domain_dir = domain_dir or DOMAIN_DIR
    surfaces = _collect_surface_literals(_iter_active_python_files(active_domain_dir))
    return frozenset(sorted(surfaces - _KNOWN_CONSUMED_OR_LABEL))


def load_domain_dict_surfaces(
    domain_dict_path: Path | None = None,
) -> frozenset[str]:
    """Load all import/export surfaces declared in ``domain_dict.json``."""
    payload = json.loads((domain_dict_path or DOMAIN_DICT_PATH).read_text(encoding="utf-8"))
    surfaces: set[str] = set()
    for entry in payload.get("imports", []):
        surfaces.add(str(entry["event_name"]))
    for entry in payload.get("exports", []):
        surfaces.add(str(entry["event_name"]))
    return frozenset(sorted(surfaces))


def load_registered_surfaces(
    registry_path: Path | None = None,
) -> frozenset[str]:
    """Load all surfaces declared in the shared verb registry."""
    payload = yaml.safe_load((registry_path or VERB_REGISTRY_PATH).read_text(encoding="utf-8"))
    entries = payload.get("registry", []) if isinstance(payload, dict) else payload
    surfaces: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        op = str(entry.get("op") or "").strip()
        verb = str(entry.get("verb") or "").strip()
        if op and verb:
            surfaces.add(f"{op}:{verb}")
    return frozenset(sorted(surfaces))


def audit_emitted_surfaces(
    *,
    domain_dir: Path | None = None,
    domain_dict_path: Path | None = None,
    registry_path: Path | None = None,
) -> EmittedSurfaceAuditResult:
    """Audit active runtime emitters against domain_dict and the verb registry."""
    active_domain_dir = domain_dir or DOMAIN_DIR
    scanned_files = _iter_active_python_files(active_domain_dir)
    emitted_surfaces = collect_emitted_surfaces(active_domain_dir)
    domain_dict_surfaces = load_domain_dict_surfaces(domain_dict_path)
    registry_surfaces = load_registered_surfaces(registry_path)

    missing_from_domain_dict = frozenset(
        sorted(
            emitted_surfaces
            - domain_dict_surfaces
            - _KNOWN_DOMAIN_DICT_EXCEPTIONS
        )
    )
    missing_from_registry = frozenset(
        sorted(
            emitted_surfaces
            - registry_surfaces
            - _KNOWN_REGISTRY_EXCEPTIONS
        )
    )

    return EmittedSurfaceAuditResult(
        emitted_surfaces=emitted_surfaces,
        domain_dict_surfaces=domain_dict_surfaces,
        registry_surfaces=registry_surfaces,
        missing_from_domain_dict=missing_from_domain_dict,
        missing_from_registry=missing_from_registry,
        scanned_files=scanned_files,
    )


__all__ = [
    "DOMAIN_DICT_PATH",
    "DOMAIN_DIR",
    "VERB_REGISTRY_PATH",
    "audit_emitted_surfaces",
    "collect_emitted_surfaces",
    "load_domain_dict_surfaces",
    "load_registered_surfaces",
]
