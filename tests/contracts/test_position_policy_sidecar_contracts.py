import json
from pathlib import Path

import jsonschema
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "apps" / "reference" / \
    "dictionaries" / "verb_registry_v1.yaml"
DOMAIN_DICT_PATH = PROJECT_ROOT / "apps" / "reference" / \
    "domains" / "execution_position" / "domain_dict.json"

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

MODE_ACTIVE_SCHEMA_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
    / "schemas" / "position_policy_sidecar_mode_active_v1.json"
)
EVALUATED_SCHEMA_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
    / "schemas" / "position_policy_sidecar_evaluated_v1.json"
)
SCORES_SCHEMA_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
    / "schemas" / "position_policy_sidecar_scores_v1.json"
)
SUPPRESSED_SCHEMA_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
    / "schemas" / "position_policy_sidecar_suppressed_v1.json"
)
RECOMMENDED_SCHEMA_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
    / "schemas" / "position_policy_sidecar_recommended_v1.json"
)
COMMON_PEAK_GIVEBACK_SCHEMA_PATH = (
    PROJECT_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "execution_position"
    / "contract_layer"
    / "schemas"
    / "common"
    / "peak_giveback_snapshot_v1.json"
)


def _validate_with_local_refs(schema: dict, payload: dict) -> None:
    common_schema = json.loads(
        COMMON_PEAK_GIVEBACK_SCHEMA_PATH.read_text(encoding="utf-8")
    )
    resolver = jsonschema.RefResolver.from_schema(
        schema,
        store={common_schema["$id"]: common_schema},
    )
    jsonschema.validate(instance=payload, schema=schema, resolver=resolver)


def test_position_policy_sidecar_verbs_are_registered_with_schema_paths() -> None:
    registry = yaml.safe_load(
        REGISTRY_PATH.read_text(encoding="utf-8"))["registry"]
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

    imports = {(row["event_name"], row["source_domain"])
               for row in domain_dict["imports"]}
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


def _sidecar_config_snapshot() -> dict:
    return {
        "mode": "shadow",
        "peak_giveback_close": {
            "enabled": True,
            "edge_arm_usd": 25.0,
            "giveback_trigger_pct": 50.0,
        },
        "shadow_percent_notional_arm": {
            "enabled": True,
            "candidate_pcts": [0.02, 0.05, 0.07],
            "candidate_unit": "percent",
        },
        "freshness": {
            "portfolio_max_age_ms": 15_000,
            "features_max_age_ms": 15_000,
            "regime_max_age_ms": 15_000,
            "order_state_max_age_ms": 15_000,
        },
        "source_config_path": "config/aurora/domains.yaml",
    }


def _peak_giveback_snapshot(*, null_economics: bool = False) -> dict:
    snapshot = {
        "policy_enabled": True,
        "mark_price": 110.0,
        "entry_price": 100.0,
        "position_qty": 1.0,
        "side": "BUY",
        "unrealized_pnl_usdt": 10.0,
        "unrealized_pnl_pct": 10.0,
        "peak_edge_usd": 30.0,
        "current_edge_usd": 10.0,
        "giveback_pct": 66.6666666667,
        "is_armed": True,
        "arm_threshold_usd": 25.0,
        "giveback_trigger_pct": 50.0,
        "threshold_crossed": True,
        "peak_giveback_state": "peak_giveback_threshold_met",
        "peak_giveback_shadow_arms": {
            "percent_notional": {
                "enabled": True,
                "candidate_unit": "percent",
                "giveback_trigger_pct": 50.0,
                "candidates": [
                    {
                        "candidate_pct": 0.02,
                        "arm_threshold_usd": 0.8,
                        "is_armed": True,
                        "first_arm_ts_ms": 1700000000001,
                        "peak_edge_usd": 30.0,
                        "giveback_pct": 66.6666666667,
                        "threshold_met_under_current_giveback_trigger_pct": True,
                        "would_trigger": True,
                        "state": "shadow_percent_notional_threshold_met",
                        "null_reasons": {},
                    }
                ],
            }
        },
        "reason_codes": ["peak_giveback_armed", "peak_giveback_threshold_met"],
        "null_reasons": {},
    }
    if null_economics:
        snapshot.update(
            {
                "mark_price": None,
                "unrealized_pnl_usdt": None,
                "unrealized_pnl_pct": None,
                "current_edge_usd": None,
                "giveback_pct": None,
                "threshold_crossed": None,
                "peak_giveback_state": "peak_giveback_unavailable_economics_missing",
                "peak_giveback_shadow_arms": {
                    "percent_notional": {
                        "enabled": True,
                        "candidate_unit": "percent",
                        "giveback_trigger_pct": 50.0,
                        "candidates": [
                            {
                                "candidate_pct": 0.02,
                                "arm_threshold_usd": None,
                                "is_armed": False,
                                "first_arm_ts_ms": None,
                                "peak_edge_usd": 0.0,
                                "giveback_pct": None,
                                "threshold_met_under_current_giveback_trigger_pct": None,
                                "would_trigger": None,
                                "state": "shadow_percent_notional_unavailable_economics_missing",
                                "null_reasons": {
                                    "arm_threshold_usd": "missing_position_notional_usdt",
                                    "giveback_pct": "missing_unrealized_pnl_usdt",
                                    "threshold_met_under_current_giveback_trigger_pct": "missing_giveback_pct",
                                },
                            }
                        ],
                        "null_reason": "missing_unrealized_pnl_usdt",
                    }
                },
                "reason_codes": ["peak_giveback_unavailable_economics_missing"],
                "null_reasons": {
                    "mark_price": "missing_mark_price",
                    "unrealized_pnl_usdt": "missing_unrealized_pnl_usdt",
                    "unrealized_pnl_pct": "missing_unrealized_pnl_pct",
                    "current_edge_usd": "missing_unrealized_pnl_usdt",
                    "giveback_pct": "missing_current_edge_usd",
                    "threshold_crossed": "threshold_not_evaluable",
                },
            }
        )
    return snapshot


def _policy_payload(*, event_type: str) -> dict:
    payload = {
        "ts_ms": 1_700_000_000_000,
        "trace_id": "pps:BTCUSDT:1:1",
        "symbol": "BTCUSDT",
        "sidecar_version": "1.0.0",
        "mode": "shadow",
        "evaluation_mode": "bounded_soft_close_policy",
        "event_type": event_type,
        "reason_codes": ["trigger:portfolio_state_updated", "peak_giveback_not_armed_below_edge"],
        "position_snapshot": {"symbol": "BTCUSDT"},
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {"portfolio_fresh": True, "features_fresh": True, "regime_fresh": True},
        "peak_giveback_snapshot": _peak_giveback_snapshot(null_economics=True),
    }
    if event_type in {
        "POSITION_POLICY_SIDECAR_SCORES",
        "POSITION_POLICY_SIDECAR_EVALUATED",
        "POSITION_POLICY_SIDECAR_RECOMMENDED",
    }:
        payload["score_snapshot"] = {"soft_close_pressure": 0.25}
    if event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
        payload["suppression_reason"] = "portfolio_stale"
        payload["score_snapshot"] = {"soft_close_pressure": 0.25}
    if event_type == "POSITION_POLICY_SIDECAR_RECOMMENDED":
        payload["policy_source"] = "position_policy_sidecar:peak_giveback"
    return payload


def _mode_active_payload() -> dict:
    return {
        "ts_ms": 1_700_000_000_000,
        "trace_id": "pps:__DOMAIN__:1:1",
        "symbol": "__DOMAIN__",
        "sidecar_version": "1.0.0",
        "mode": "shadow",
        "evaluation_mode": "bounded_soft_close_policy",
        "event_type": "POSITION_POLICY_SIDECAR_MODE_ACTIVE",
        "reason_codes": ["sidecar_initialized"],
        "position_snapshot": {},
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {},
        "sidecar_config_snapshot": _sidecar_config_snapshot(),
    }


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
        "peak_giveback_snapshot": _peak_giveback_snapshot(),
    }


def test_mode_active_payload_conforms_to_schema_with_sidecar_config_snapshot() -> None:
    schema = json.loads(MODE_ACTIVE_SCHEMA_PATH.read_text(encoding="utf-8"))
    _validate_with_local_refs(schema, _mode_active_payload())


def test_sidecar_policy_payloads_conform_to_schema_with_peak_giveback_snapshot() -> None:
    for schema_path, event_type in (
        (EVALUATED_SCHEMA_PATH, "POSITION_POLICY_SIDECAR_EVALUATED"),
        (SCORES_SCHEMA_PATH, "POSITION_POLICY_SIDECAR_SCORES"),
        (SUPPRESSED_SCHEMA_PATH, "POSITION_POLICY_SIDECAR_SUPPRESSED"),
        (RECOMMENDED_SCHEMA_PATH, "POSITION_POLICY_SIDECAR_RECOMMENDED"),
    ):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        _validate_with_local_refs(
            schema, _policy_payload(event_type=event_type))


def test_close_request_payload_conforms_to_schema_base_source() -> None:
    """Original scoring path: policy_source = 'position_policy_sidecar'."""
    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _close_request_payload(policy_source="position_policy_sidecar")
    _validate_with_local_refs(schema, payload)


def test_close_request_payload_conforms_to_schema_peak_giveback_source() -> None:
    """R7A peak-giveback path: policy_source = 'position_policy_sidecar:peak_giveback'."""
    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _close_request_payload(
        policy_source="position_policy_sidecar:peak_giveback")
    _validate_with_local_refs(schema, payload)


def test_close_request_schema_rejects_peak_giveback_snapshot_without_null_reasons() -> None:
    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _close_request_payload(
        policy_source="position_policy_sidecar:peak_giveback")
    del payload["peak_giveback_snapshot"]["null_reasons"]

    try:
        _validate_with_local_refs(schema, payload)
        raise AssertionError(
            "Schema should reject peak_giveback_snapshot without null_reasons")
    except jsonschema.ValidationError:
        pass


def test_close_request_schema_rejects_invalid_policy_source() -> None:
    """Schema must reject policy_source values outside the sidecar namespace."""
    schema = json.loads(CLOSE_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))

    for bad_source in ("random_policy", "", "position_policy_sidecar:", "roi_policy"):
        payload = _close_request_payload(policy_source=bad_source)
        try:
            _validate_with_local_refs(schema, payload)
            raise AssertionError(
                f"Schema should reject policy_source={bad_source!r}")
        except jsonschema.ValidationError:
            pass  # expected
