"""Phase 9C compatibility stub ledger guardrails for execution_position."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


LEDGER_PATH = Path(
    "apps/reference/domains/execution_position/docs/compatibility_stub_ledger.json"
)
ROOT_ANCHORS = {
    "apps/reference/domains/execution_position/fsm.py",
    "apps/reference/domains/execution_position/contracts.py",
    "apps/reference/domains/execution_position/reasons.py",
    "apps/reference/domains/execution_position/utils.py",
}
KNOWN_SENTINEL_TOKENS = ("coerce_exchange_bool", "_ClosePositionTruth")


def _load_ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _module_name_from_stub_path(stub_path: str) -> str:
    return stub_path.removesuffix(".py").replace("/", ".")


def test_ledger_stub_entries_exist_and_root_anchors_are_excluded() -> None:
    ledger = _load_ledger()
    entries = ledger["entries"]

    assert LEDGER_PATH.exists()
    assert ledger["schema_version"] == 1
    assert set(ledger["root_anchor_exclusions"]) == ROOT_ANCHORS

    stub_paths = {entry["stub_path"] for entry in entries}
    assert stub_paths.isdisjoint(ROOT_ANCHORS)

    for entry in entries:
        stub_path = Path(entry["stub_path"])
        assert stub_path.exists()
        assert stub_path.is_file()


def test_stub_imports_resolve_to_same_module_objects_as_targets() -> None:
    ledger = _load_ledger()

    # Use the same preload path already exercised by the package tests to avoid
    # unrelated cold-start import cycles in moved modules.
    importlib.import_module("vfoundation.core.protocol")
    importlib.import_module("apps.reference.domains.execution_position.fsm")

    for entry in ledger["entries"]:
        old_name = _module_name_from_stub_path(entry["stub_path"])
        target_name = entry["target_module"]

        old_module = importlib.import_module(old_name)
        target_module = importlib.import_module(target_name)

        assert old_module is target_module


def test_known_source_text_sentinel_debt_is_explicitly_listed() -> None:
    ledger = _load_ledger()

    for entry in ledger["entries"]:
        stub_text = Path(entry["stub_path"]).read_text(encoding="utf-8")
        expected_tokens = [token for token in KNOWN_SENTINEL_TOKENS if token in stub_text]

        assert entry["source_text_sentinel_debt"] == bool(expected_tokens)
        assert sorted(entry["source_text_sentinel_tokens"]) == sorted(expected_tokens)


def test_docstring_only_and_pure_reexport_flags_match_stub_surface() -> None:
    ledger = _load_ledger()

    for entry in ledger["entries"]:
        stub_text = Path(entry["stub_path"]).read_text(encoding="utf-8")
        has_docstring = stub_text.startswith('"""Compatibility alias')
        has_sentinel = any(token in stub_text for token in KNOWN_SENTINEL_TOKENS)

        assert entry["compatibility_docstring_only_debt"] == (has_docstring and not has_sentinel)
        assert entry["pure_reexport"] == (not has_docstring and not has_sentinel)
