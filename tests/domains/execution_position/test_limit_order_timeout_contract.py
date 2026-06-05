"""J4 contract tests for EVT:LIMIT_ORDER_TIMEOUT staged deprecation.

Replaces J2 "preserve active contract" assertions with J4 "preserve
deprecated public surface until final retirement" semantics.

J3 FACTS:
- EVT:LIMIT_ORDER_TIMEOUT has zero live emitters after LimitOrderMonitor retirement.
- Active timeout event is EVT:ORDER_TIMEOUT (entry_manager.py, verb=ORDER_TIMEOUT).
- EVT:LIMIT_ORDER_TIMEOUT is deprecated in verb_registry_v1.yaml (J4, 2026-04-30).
- domain_dict.json retains the export with deprecation_notes.
- README.md annotates the event as deprecated.
"""
import json
from pathlib import Path

import yaml


DOMAIN_DICT_PATH = Path(
    "apps/reference/domains/execution_position/domain_dict.json")
README_PATH = Path("apps/reference/domains/execution_position/README.md")
VERB_REGISTRY_PATH = Path(
    "apps/reference/dictionaries/verb_registry_v1.yaml")


# ---------------------------------------------------------------------------
# Surface preservation: deprecated event stays in public surfaces
# until final retirement (J5/Phase C).
# ---------------------------------------------------------------------------

def test_limit_order_timeout_stays_in_domain_dict_exports() -> None:
    """EVT:LIMIT_ORDER_TIMEOUT export must remain until final retirement."""
    domain_dict = json.loads(DOMAIN_DICT_PATH.read_text(encoding="utf-8"))
    exported_events = {
        entry["event_name"]
        for entry in domain_dict["exports"]
        if isinstance(entry, dict) and "event_name" in entry
    }

    assert "EVT:LIMIT_ORDER_TIMEOUT" in exported_events


def test_limit_order_timeout_domain_dict_has_deprecation_note() -> None:
    """domain_dict.json ssot_notes must document the deprecation."""
    domain_dict = json.loads(DOMAIN_DICT_PATH.read_text(encoding="utf-8"))
    deprecation_notes = domain_dict.get("ssot_notes", {}).get("deprecation_notes", {})

    assert "EVT:LIMIT_ORDER_TIMEOUT" in deprecation_notes
    note = deprecation_notes["EVT:LIMIT_ORDER_TIMEOUT"]
    assert "DEPRECATED" in note.upper()
    assert "ORDER_TIMEOUT" in note


def test_limit_order_timeout_verb_registry_deprecated() -> None:
    """verb_registry must mark EVT:LIMIT_ORDER_TIMEOUT as deprecated (not active)."""
    registry = yaml.safe_load(VERB_REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = registry.get("registry", [])

    matching = [
        e for e in entries
        if e.get("op") == "EVT" and e.get("verb") == "LIMIT_ORDER_TIMEOUT"
    ]

    assert len(matching) == 1, (
        f"Expected exactly 1 EVT:LIMIT_ORDER_TIMEOUT entry, found {len(matching)}"
    )
    entry = matching[0]
    assert entry["status"] == "deprecated", (
        f"EVT:LIMIT_ORDER_TIMEOUT should be deprecated, got status={entry['status']}"
    )
    assert "deprecated_since" in entry
    assert entry["owner"] == "execution_position"


def test_active_timeout_event_is_order_timeout_in_registry() -> None:
    """EVT:ORDER_TIMEOUT must remain active in verb_registry (it is the live emitter)."""
    registry = yaml.safe_load(VERB_REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = registry.get("registry", [])

    matching = [
        e for e in entries
        if e.get("op") == "EVT" and e.get("verb") == "ORDER_TIMEOUT"
    ]

    assert len(matching) == 1, (
        f"Expected exactly 1 EVT:ORDER_TIMEOUT entry, found {len(matching)}"
    )
    assert matching[0]["status"] == "active"
    assert matching[0]["owner"] == "execution_position"


def test_execution_position_component_list_keeps_watchdog_not_tombstone_monitor() -> None:
    """OrderTimeoutWatchdog must be in components; LimitOrderMonitor must not."""
    domain_dict = json.loads(DOMAIN_DICT_PATH.read_text(encoding="utf-8"))
    components = set(domain_dict.get("components") or [])

    assert "OrderTimeoutWatchdog" in components
    assert "LimitOrderMonitor" not in components


def test_readme_annotates_limit_order_timeout_as_deprecated() -> None:
    """README must mention EVT:LIMIT_ORDER_TIMEOUT as deprecated."""
    readme = README_PATH.read_text(encoding="utf-8")

    assert "EVT:LIMIT_ORDER_TIMEOUT" in readme
    assert "deprecated" in readme.lower()
    # J2: LimitOrderMonitor module must not be advertised
    assert "limit_order_monitor.py" not in readme


def test_readme_points_active_timeout_to_order_timeout() -> None:
    """README deprecation note must reference EVT:ORDER_TIMEOUT as active path."""
    readme = README_PATH.read_text(encoding="utf-8")

    assert "EVT:ORDER_TIMEOUT" in readme
    assert "EntryManager" in readme or "OrderTimeoutWatchdog" in readme
