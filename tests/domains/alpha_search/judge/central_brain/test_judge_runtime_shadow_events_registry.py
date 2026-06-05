from __future__ import annotations

import json
from pathlib import Path

import yaml


REGISTRY = Path("apps/reference/dictionaries/verb_registry_v1.yaml")
EVENTS = {
    "JUDGE_EVIDENCE_ENVELOPE_BUILT_V2": "evidence_only",
    "JUDGE_POLICY_VERDICT_EMITTED_V2": "shadow_only",
    "JUDGE_BRIDGE_DECISION_EVALUATED_V1": "no_effect",
    "JUDGE_SHADOW_CALIBRATION_ROW_BUILT_V1": "runtime_shadow_only",
}


def registry_entries():
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return data["registry"]


def test_shadow_events_registered_exactly_once():
    entries = registry_entries()
    for verb in EVENTS:
        matches = [entry for entry in entries if entry.get("op") == "EVT" and entry.get("verb") == verb]
        assert len(matches) == 1


def test_shadow_event_schemas_exist_and_parse():
    for entry in registry_entries():
        if entry.get("verb") not in EVENTS:
            continue
        schema = Path(entry["schema"])
        assert schema.exists()
        assert json.loads(schema.read_text(encoding="utf-8"))["type"] == "object"


def test_shadow_events_are_not_live_authority():
    for entry in registry_entries():
        if entry.get("verb") in EVENTS:
            assert entry.get("status") == "experimental"
            assert entry.get("authority") == EVENTS[entry["verb"]]
            assert entry.get("op") == "EVT"
