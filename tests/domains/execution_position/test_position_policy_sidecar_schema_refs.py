from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest

from vfoundation.core.schema_registry import VerbSchemaRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_SCHEMA_DIR = (
    PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position" / "schemas"
)
COMMON_SCHEMA_PATH = (
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
COMMON_SCHEMA_REF = "https://aurora.internal/schemas/common/peak_giveback_snapshot_v1.json"
REGISTRY_PATH = "apps/reference/dictionaries/verb_registry_v1.yaml"
AFFECTED_SCHEMAS = (
    "cmd_position_policy_sidecar_close_request_v1.json",
    "position_policy_sidecar_evaluated_v1.json",
    "position_policy_sidecar_recommended_v1.json",
    "position_policy_sidecar_scores_v1.json",
    "position_policy_sidecar_suppressed_v1.json",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_schema(name: str) -> dict:
    return _load_json(EP_SCHEMA_DIR / name)


def _resolver_for(schema: dict) -> jsonschema.RefResolver:
    common_schema = _load_json(COMMON_SCHEMA_PATH)
    return jsonschema.RefResolver.from_schema(
        schema,
        store={common_schema["$id"]: common_schema},
    )


def _validate(name: str, payload: dict) -> None:
    schema = _load_schema(name)
    jsonschema.validate(
        instance=payload,
        schema=schema,
        resolver=_resolver_for(schema),
    )


def _peak_giveback_snapshot() -> dict:
    return {
        "policy_enabled": True,
        "mark_price": 120.0,
        "entry_price": 100.0,
        "position_qty": 1.0,
        "side": "BUY",
        "unrealized_pnl_usdt": 20.0,
        "unrealized_pnl_pct": 20.0,
        "peak_edge_usd": 30.0,
        "current_edge_usd": 20.0,
        "giveback_pct": 33.333333,
        "is_armed": True,
        "arm_threshold_usd": 25.0,
        "giveback_trigger_pct": 50.0,
        "threshold_crossed": False,
        "peak_giveback_state": "peak_giveback_below_trigger",
        "reason_codes": ["peak_giveback_armed", "peak_giveback_below_trigger"],
        "null_reasons": {},
    }


def _base_sidecar_event(event_type: str) -> dict:
    return {
        "ts_ms": 1_700_000_000_000,
        "trace_id": "trace-1",
        "symbol": "BTCUSDT",
        "sidecar_version": "v1",
        "mode": "enable",
        "evaluation_mode": "live",
        "event_type": event_type,
        "reason_codes": ["peak_giveback_armed"],
        "position_snapshot": {"position_qty": 1.0},
        "feature_ref": {"feature_ts_ms": 1_700_000_000_001},
        "regime_ref": {"regime": "TREND_UP"},
        "freshness_snapshot": {"portfolio_age_ms": 10},
        "score_snapshot": {"soft_close_pressure": 0.55},
        "peak_giveback_snapshot": _peak_giveback_snapshot(),
    }


def _payload_for_schema(name: str) -> dict:
    if name == "position_policy_sidecar_evaluated_v1.json":
        return _base_sidecar_event("POSITION_POLICY_SIDECAR_EVALUATED")
    if name == "position_policy_sidecar_scores_v1.json":
        return _base_sidecar_event("POSITION_POLICY_SIDECAR_SCORES")
    if name == "position_policy_sidecar_recommended_v1.json":
        payload = _base_sidecar_event("POSITION_POLICY_SIDECAR_RECOMMENDED")
        payload["policy_source"] = "position_policy_sidecar:peak_giveback"
        return payload
    if name == "position_policy_sidecar_suppressed_v1.json":
        payload = _base_sidecar_event("POSITION_POLICY_SIDECAR_SUPPRESSED")
        payload["suppression_reason"] = "profitability_guard"
        payload["incumbent_owner"] = None
        return payload
    if name == "cmd_position_policy_sidecar_close_request_v1.json":
        return {
            "ts_ms": 1_700_000_000_000,
            "request_id": "ppsreq:pps:BTCUSDT:1",
            "trace_id": "trace-1",
            "symbol": "BTCUSDT",
            "sidecar_version": "v1",
            "mode": "enable",
            "evaluation_mode": "live",
            "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
            "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
            "requested_action": "SOFT_CLOSE",
            "requested_qty": None,
            "target_mode": "symbol_current_net_only",
            "policy_source": "position_policy_sidecar:peak_giveback",
            "action_package_version": "v1",
            "allowed_action_scope": {
                "soft_close_symbol_current_net_only": True,
                "partial_reduce": False,
                "bracket_mutation": False,
                "exact_targeting": False,
            },
            "reason_codes": ["peak_giveback_threshold_met"],
            "score_snapshot": {
                "soft_close_pressure": 0.91,
                "peak_edge_usd": 30.0,
                "current_edge_usd": 10.0,
                "giveback_pct": 66.666666,
                "giveback_trigger_pct": 50.0,
            },
            "position_snapshot": {"position_qty": 1.0},
            "feature_ref": {"feature_ts_ms": 1_700_000_000_001},
            "regime_ref": {"regime": "TREND_UP"},
            "freshness_snapshot": {"portfolio_age_ms": 10},
            "fill_correlation": {"fill_rid": "fill-1"},
            "portfolio_correlation": {"positions_last_ts_ms": 1_700_000_000_002},
            "peak_giveback_snapshot": _peak_giveback_snapshot(),
        }
    raise AssertionError(f"Unhandled schema name: {name}")


def _registry_validator(registry: VerbSchemaRegistry, schema_name: str):
    if schema_name == "cmd_position_policy_sidecar_close_request_v1.json":
        return registry.get_validator("CMD", "POSITION_POLICY_SIDECAR_CLOSE_REQUEST")
    if schema_name == "position_policy_sidecar_evaluated_v1.json":
        return registry.get_validator("EVT", "POSITION_POLICY_SIDECAR_EVALUATED")
    if schema_name == "position_policy_sidecar_recommended_v1.json":
        return registry.get_validator("EVT", "POSITION_POLICY_SIDECAR_RECOMMENDED")
    if schema_name == "position_policy_sidecar_scores_v1.json":
        return registry.get_validator("EVT", "POSITION_POLICY_SIDECAR_SCORES")
    if schema_name == "position_policy_sidecar_suppressed_v1.json":
        return registry.get_validator("EVT", "POSITION_POLICY_SIDECAR_SUPPRESSED")
    raise AssertionError(f"Unhandled registry schema name: {schema_name}")


@pytest.fixture(scope="module")
def registry() -> VerbSchemaRegistry:
    loaded = VerbSchemaRegistry(project_root=".")
    loaded.load_registry(REGISTRY_PATH)
    return loaded


class TestPeakGivebackSnapshotSchemaRefDedup:
    @pytest.mark.parametrize("schema_name", AFFECTED_SCHEMAS)
    def test_affected_schema_uses_common_peak_giveback_ref(self, schema_name: str) -> None:
        schema = _load_schema(schema_name)
        assert schema["properties"]["peak_giveback_snapshot"] == {"$ref": COMMON_SCHEMA_REF}

    @pytest.mark.parametrize("schema_name", AFFECTED_SCHEMAS)
    def test_valid_existing_sidecar_payload_examples_still_pass(self, schema_name: str) -> None:
        _validate(schema_name, _payload_for_schema(schema_name))

    @pytest.mark.parametrize("schema_name", AFFECTED_SCHEMAS)
    def test_invalid_peak_giveback_snapshot_examples_still_fail(self, schema_name: str) -> None:
        payload = _payload_for_schema(schema_name)
        invalid_snapshot = dict(payload["peak_giveback_snapshot"])
        invalid_snapshot.pop("peak_giveback_state")
        payload["peak_giveback_snapshot"] = invalid_snapshot

        with pytest.raises(jsonschema.ValidationError):
            _validate(schema_name, payload)

    def test_common_peak_giveback_ref_resolves_for_all_affected_schemas(self) -> None:
        common_schema = _load_json(COMMON_SCHEMA_PATH)

        for schema_name in AFFECTED_SCHEMAS:
            schema = _load_schema(schema_name)
            resolver = _resolver_for(schema)
            resolved = resolver.resolve(COMMON_SCHEMA_REF)[1]
            assert resolved == common_schema


class TestSidecarSchemaRegistryResolution:
    @pytest.mark.parametrize("schema_name", AFFECTED_SCHEMAS)
    def test_registry_store_contains_common_peak_giveback_uri(
        self,
        registry: VerbSchemaRegistry,
        schema_name: str,
    ) -> None:
        validator = _registry_validator(registry, schema_name)
        assert validator is not None
        assert COMMON_SCHEMA_REF in validator.resolver.store

    @pytest.mark.parametrize("schema_name", AFFECTED_SCHEMAS)
    def test_registry_validates_affected_sidecar_payloads_without_network_fallback(
        self,
        registry: VerbSchemaRegistry,
        schema_name: str,
    ) -> None:
        validator = _registry_validator(registry, schema_name)
        assert validator is not None

        with patch("requests.get", side_effect=AssertionError("network fallback not allowed")), patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("network fallback not allowed"),
        ):
            validator.validate(_payload_for_schema(schema_name))

    @pytest.mark.parametrize("schema_name", AFFECTED_SCHEMAS)
    def test_invalid_nested_peak_giveback_snapshot_still_fails(
        self,
        registry: VerbSchemaRegistry,
        schema_name: str,
    ) -> None:
        validator = _registry_validator(registry, schema_name)
        assert validator is not None

        payload = _payload_for_schema(schema_name)
        payload["peak_giveback_snapshot"] = dict(payload["peak_giveback_snapshot"])
        payload["peak_giveback_snapshot"].pop("peak_giveback_state")

        with pytest.raises(jsonschema.ValidationError, match="peak_giveback_state"):
            validator.validate(payload)

    @pytest.mark.parametrize(
        "schema_name",
        (
            "cmd_position_policy_sidecar_close_request_v1.json",
            "position_policy_sidecar_action_skipped_v1.json",
            "position_policy_sidecar_close_request_state_v1.json",
            "position_policy_sidecar_evaluated_v1.json",
            "position_policy_sidecar_mode_active_v1.json",
            "position_policy_sidecar_recommended_v1.json",
            "position_policy_sidecar_scores_v1.json",
            "position_policy_sidecar_suppressed_v1.json",
        ),
    )
    def test_sidecar_schema_ids_align_with_registry_expectations(
        self,
        schema_name: str,
    ) -> None:
        schema = _load_schema(schema_name)
        assert schema["$id"] == f"https://aurora.internal/schemas/{schema_name}"

    def test_common_peak_giveback_schema_id_is_registered_locally(self) -> None:
        common_schema = _load_json(COMMON_SCHEMA_PATH)
        assert common_schema["$id"] == COMMON_SCHEMA_REF
