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


# ---------------------------------------------------------------------------
# R7A: Payload-vs-schema conformance tests for CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST
# ---------------------------------------------------------------------------

CLOSE_REQUEST_SCHEMA_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
    / "schemas" / "cmd_position_policy_sidecar_close_request_v1.json"
)


def _close_request_payload(*, policy_source: str = "position_policy_sidecar") -> dict:
    """Minimal valid CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST payload."""
    return {
        "ts_ms": 1_700_000_000_000,
        "request_id": "ppsreq:pps:BTCUSDT:1:1",
        "trace_id": "pps:BTCUSDT:1:1",
        "symbol": "BTCUSDT",
        "sidecar_version": "1.0.0",
        "mode": "enable",
        "evaluation_mode": "bounded_soft_close_policy",
        "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
        "requested_action": "SOFT_CLOSE",
        "target_mode": "symbol_current_net_only",
        "policy_source": policy_source,
        "action_package_version": "phase2_action_package_v1",
        "allowed_action_scope": {"soft_close_symbol_current_net_only": True},
        "reason_codes": ["trigger:portfolio_state_updated", "peak_giveback_threshold_met"],
        "score_snapshot": {"soft_close_pressure": 1.0},
        "position_snapshot": {"symbol": "BTCUSDT"},
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {},
        "fill_correlation": {},
        "portfolio_correlation": {},
    }


def test_close_request_payload_conforms_to_schema_base_source() -> None:
    """Original scoring path: policy_source = 'position_policy_sidecar'."""
    import jsonschema

    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _close_request_payload(policy_source="position_policy_sidecar")
    jsonschema.validate(payload, schema)  # must not raise


def test_close_request_payload_conforms_to_schema_peak_giveback_source() -> None:
    """R7A peak-giveback path: policy_source = 'position_policy_sidecar:peak_giveback'."""
    import jsonschema

    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _close_request_payload(policy_source="position_policy_sidecar:peak_giveback")
    jsonschema.validate(payload, schema)  # must not raise


def test_close_request_schema_rejects_invalid_policy_source() -> None:
    """Schema must reject policy_source values outside the sidecar namespace."""
    import jsonschema

    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))

    for bad_source in ("random_policy", "", "position_policy_sidecar:", "roi_policy"):
        payload = _close_request_payload(policy_source=bad_source)
        try:
            jsonschema.validate(payload, schema)
            raise AssertionError(f"Schema should reject policy_source={bad_source!r}")
        except jsonschema.ValidationError:
            pass  # expected
