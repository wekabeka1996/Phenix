import json
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "apps" / "reference" / "dictionaries" / "verb_registry_v1.yaml"
DOMAIN_DICT_PATH = PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position" / "domain_dict.json"

SIDECAR_EVENT_VERBS = {
    "POSITION_POLICY_SIDECAR_MODE_ACTIVE": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_mode_active_v1.json",
    "POSITION_POLICY_SIDECAR_EVALUATED": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_evaluated_v1.json",
    "POSITION_POLICY_SIDECAR_SCORES": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_scores_v1.json",
    "POSITION_POLICY_SIDECAR_SUPPRESSED": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_suppressed_v1.json",
    "POSITION_POLICY_SIDECAR_RECOMMENDED": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_recommended_v1.json",
    "POSITION_POLICY_MICROSTRUCTURE_PRESSURE_EVALUATED": "apps/reference/domains/execution_position/schemas/position_policy_microstructure_pressure_evaluated_v1.json",
    "POSITION_POLICY_SIDECAR_ACTION_SKIPPED": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_action_skipped_v1.json",
    "POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE": "apps/reference/domains/execution_position/schemas/position_policy_sidecar_close_request_state_v1.json",
}

SIDECAR_COMMAND_VERBS = {
    "POSITION_POLICY_SIDECAR_CLOSE_REQUEST": "apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json",
}


def test_position_policy_sidecar_verbs_are_registered_with_schema_paths() -> None:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))["registry"]
    by_op_verb = {(entry["op"], entry["verb"]): entry for entry in registry}

    for verb, schema_path in SIDECAR_EVENT_VERBS.items():
        assert ("EVT", verb) in by_op_verb
        assert by_op_verb[("EVT", verb)]["owner"] == "execution_position"
        assert by_op_verb[("EVT", verb)]["schema"] == schema_path
        assert (PROJECT_ROOT / schema_path).exists()

    for verb, schema_path in SIDECAR_COMMAND_VERBS.items():
        assert ("CMD", verb) in by_op_verb
        assert by_op_verb[("CMD", verb)]["owner"] == "execution_position"
        assert by_op_verb[("CMD", verb)]["schema"] == schema_path
        assert (PROJECT_ROOT / schema_path).exists()


def test_execution_position_domain_dict_exports_sidecar_events_and_self_imports() -> None:
    domain_dict = json.loads(DOMAIN_DICT_PATH.read_text(encoding="utf-8"))

    imports = {(row["event_name"], row["source_domain"]) for row in domain_dict["imports"]}
    exports = {row["event_name"] for row in domain_dict["exports"]}
    components = set(domain_dict["components"])

    assert ("EVT:ORDER_STATE_CHANGED", "self") in imports
    assert ("EVT:EXECUTION_CLOSE_RECONCILED", "self") in imports
    assert ("CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST", "self") in imports

    for verb in SIDECAR_EVENT_VERBS:
        assert f"EVT:{verb}" in exports
    for verb in SIDECAR_COMMAND_VERBS:
        assert f"CMD:{verb}" in exports

    assert "PositionPolicySidecar" in components
