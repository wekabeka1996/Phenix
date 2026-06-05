from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import joblib
import numpy as np
import pytest

from apps.reference.domains.decision_making.authority_bridge import (
    NeocortexAuthorityBridge,
)
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
)
from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcome,
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    record_failure_outcome,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.contracts.causal_time import (
    reset_non_causal_counter,
)
from apps.reference.domains.neocortex.logic.datasets.hygiene import (
    DatasetPolicyEngine,
)
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser import (
    parse_feature_log_line,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)
from apps.reference.domains.neocortex.logic.telemetry import TelemetryLogger
from apps.reference.domains.neocortex.main import (
    FatalStartupError,
    NeocortexShadowRuntime,
    ShadowGateViolationError,
    build_shadow_baseline_runtime,
    evaluate_startup_shadow_gates,
)
from apps.reference.telemetry.metrics import generate_latest
from tests.domains.neocortex.architecture.test_import_boundaries import (
    HOT_PATH_FILES,
    NEOCORTEX_ROOT,
    REPO_ROOT,
)


CONFIG_DIR = REPO_ROOT / "apps" / "reference" / "domains" / "neocortex" / "config"


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    label_fragments = [f'{key}="{value}"' for key, value in labels.items()]
    pattern = re.compile(r" (-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)$")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(fragment in line for fragment in label_fragments):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        match = pattern.search(line)
        if match is not None:
            return float(match.group(1))
    return 0.0


def _load_config():
    return load_config(CONFIG_DIR)


class _FixedToxicModel:
    classes_ = np.array([0, 1])

    def __init__(self, toxic_probability: float) -> None:
        self.toxic_probability = toxic_probability

    def predict_proba(self, _frame):
        return np.array([[1.0 - self.toxic_probability, self.toxic_probability]])


def _dataset_engine(policy_training_mode: str | None = None) -> DatasetPolicyEngine:
    config = _load_config()
    return DatasetPolicyEngine(
        config.neuro.dataset,
        policy_training_mode=policy_training_mode or config.neuro.ppo.policy_training_mode,
        representation_training_mode=config.neuro.sequence.representation_training_mode,
        sequence_inference_mode=config.neuro.sequence.inference_mode,
    )


def _write_baseline_artifact(path: Path, *, toxic_probability: float = 0.9) -> None:
    joblib.dump(
        {
            "artifact_version": "test_baseline_logreg_v1",
            "model": _FixedToxicModel(toxic_probability),
            "feature_columns": [
                "f_symbol",
                "f_snapshot_contract",
                "f_trigger_event_type",
            ],
            "threshold": 0.835,
        },
        path,
    )


def _make_request(*, state_vector=None, decision_id: str = "decision-1") -> ControlDecisionRequest:
    snapshot: dict[str, object] = {}
    if state_vector is not None:
        snapshot["state_vector"] = state_vector
    return ControlDecisionRequest(
        decision_id=decision_id,
        rid="rid-1",
        symbol="BTCUSDT",
        proposed_action="OPEN_LONG",
        deadline_ms=1_700_000_000_050,
        decision_basis_ts=1_700_000_000_000,
        causal_state_snapshot=snapshot,
    )


def _live_shadow_legacy_config():
    config = _load_config()
    neuro = config.neuro.model_copy(
        update={
            "performance": config.neuro.performance.model_copy(
                update={"operating_mode": "live_shadow"}
            ),
            "shadow_gates": config.neuro.shadow_gates.model_copy(
                update={"startup_enforcement": "strict"}
            ),
        }
    )
    replay = config.replay.model_copy(
        update={"feature_missing_timestamp_policy": "legacy_non_causal_file_offset"}
    )
    return config.model_copy(update={"neuro": neuro, "replay": replay})


def setup_function() -> None:
    reset_failure_outcomes()
    reset_non_causal_counter()


def test_failure_taxonomy_values_are_stable() -> None:
    assert {member.value for member in FailureOutcomeTaxonomy} == {
        "BLOCK",
        "FALLBACK",
        "SKIP_ROW",
        "DEGRADED_OBSERVABILITY",
        "FATAL_STARTUP",
        "LEGACY_DIAGNOSTIC_ONLY",
    }


def test_required_failure_reason_codes_exist() -> None:
    required = {
        "NON_CAUSAL_TIME",
        "MISSING_REQUIRED_STATE",
        "UNJOINABLE_LIFECYCLE",
        "LOW_SUPPORT",
        "INSUFFICIENT_REAL_EXECUTED_ROWS",
        "SYNTHETIC_FALLBACK_PRESENT",
        "REWARD_INVALID",
        "REWARD_METHODOLOGY_MISSING",
        "TERMINAL_OUTCOME_INCOMPLETE",
        "BASELINE_UNAVAILABLE",
        "MALFORMED_JSON",
        "HANDLER_FAILURE",
        "BRIDGE_UNAVAILABLE",
        "MODEL_ARTIFACT_MISMATCH",
        "TELEMETRY_FLUSH_FAILED",
        "UNCLEAN_SHUTDOWN",
    }
    available = {member.value for member in FailureReasonCode}
    assert required.issubset(available)


def test_failure_outcome_is_frozen_and_typed() -> None:
    outcome = FailureOutcome(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
        source="test",
        message="missing required state",
        recoverable=False,
        fallback_applied=False,
    )
    assert dataclasses.is_dataclass(outcome)
    assert outcome.taxonomy is FailureOutcomeTaxonomy.BLOCK
    assert outcome.reason_code is FailureReasonCode.MISSING_REQUIRED_STATE
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.message = "mutated"  # type: ignore[misc]


def test_failure_ledger_increments_counter() -> None:
    metric_before = _metric_value(
        "neocortex_failure_outcomes_total",
        taxonomy="FALLBACK",
        reason_code="BRIDGE_TIMEOUT",
    )
    record_failure_outcome(
        FailureOutcomeTaxonomy.FALLBACK,
        FailureReasonCode.BRIDGE_TIMEOUT,
        source="test",
    )
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code=FailureReasonCode.BRIDGE_TIMEOUT,
    ) == 1
    assert _metric_value(
        "neocortex_failure_outcomes_total",
        taxonomy="FALLBACK",
        reason_code="BRIDGE_TIMEOUT",
    ) == metric_before + 1.0


def test_failure_taxonomy_string_inputs_are_coerced() -> None:
    outcome = record_failure_outcome(
        "fallback",
        "handler_failure",
        source="tests",
        location="tests.neocortex.failure_taxonomy",
    )

    assert outcome.taxonomy is FailureOutcomeTaxonomy.FALLBACK
    assert outcome.reason_code is FailureReasonCode.HANDLER_FAILURE
    assert get_failure_outcome_total(
        taxonomy="fallback",
        reason_code="handler_failure",
    ) == 1


def test_bridge_timeout_records_fallback_reason() -> None:
    reset_failure_outcomes()

    async def slow_authority(_req):
        await asyncio.sleep(0.05)
        return None

    bridge = NeocortexAuthorityBridge(authority_fn=slow_authority)

    response = asyncio.run(
        bridge.request_authority(
            _make_request(decision_id="decision-bridge-timeout"),
            timeout_ms=1,
        )
    )

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "BRIDGE_TIMEOUT"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code=FailureReasonCode.BRIDGE_TIMEOUT,
    ) == 1


def test_malformed_json_records_skip_row_reason() -> None:
    result = parse_feature_log_line('{"obi": 1,', symbol="BTCUSDT")
    assert result is None
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MALFORMED_JSON,
    ) == 1


def test_missing_required_state_records_typed_failure() -> None:
    parser = FeatureParser(_load_config().ingest)
    with pytest.raises(ValueError, match="Payload missing timestamp"):
        parser.parse({"features": {"price": 1.0}})
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1


def test_legacy_non_causal_feature_log_records_diagnostic_only() -> None:
    line = '{"obi": "0.5", "tfi": "0.9"}'
    entry = parse_feature_log_line(
        line,
        symbol="BTCUSDT",
        missing_timestamp_policy="legacy_non_causal_file_offset",
        synthetic_event_ts_ms=1_700_000_000_000,
    )
    assert entry is not None
    assert entry.time_source == "legacy_non_causal_file_offset"
    assert entry.time_is_causal is False
    assert entry.dataset_visibility == "diagnostics_only"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.LEGACY_DIAGNOSTIC_ONLY,
        reason_code=FailureReasonCode.NON_CAUSAL_TIME,
    ) == 1


def test_low_support_records_skip_row_reason() -> None:
    engine = _dataset_engine()
    evaluated = engine.evaluate_sample(
        {
            "event_ts_ms": 1_700_000_000_200,
            "symbol": "BTCUSDT",
            "trade_id": "trade-1",
            "lifecycle_id": "life-1",
            "reward_complete": False,
            "reward_missing": True,
        },
        objective_family="execution_quality",
        source_type="episode_close",
        source_ref="close:btc:2",
        source_event_type="POSITION_CLOSED",
        ingestion_mode="replay",
    )
    assert evaluated.eligibility_status == "diagnostics_only"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.LOW_SUPPORT,
    ) == 1


def test_unjoinable_lifecycle_records_skip_row_reason() -> None:
    engine = _dataset_engine()
    evaluated = engine.evaluate_sample(
        {
            "event_ts_ms": 1_700_000_000_300,
            "symbol": "ETHUSDT",
            "trade_id": "trade-2",
            "unresolved_lifecycle": True,
            "reward_complete": True,
        },
        objective_family="execution_quality",
        source_type="episode_close",
        source_ref="close:eth:1",
        source_event_type="POSITION_CLOSED",
        ingestion_mode="replay",
    )
    assert evaluated.eligibility_status == "quarantined"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.UNJOINABLE_LIFECYCLE,
    ) == 1


def test_invalid_baseline_vector_maps_to_missing_required_state(tmp_path: Path) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path)
    bridge = NeocortexAuthorityBridge(model_path=model_path)

    response = asyncio.run(
        bridge.request_authority(
            _make_request(state_vector=[1.0],
                          decision_id="decision-invalid-vector"),
            timeout_ms=10,
        )
    )

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "MISSING_REQUIRED_STATE"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1


def test_baseline_unavailable_does_not_return_synthetic_flat(tmp_path: Path) -> None:
    reset_failure_outcomes()
    bridge = NeocortexAuthorityBridge(
        model_path=tmp_path / "missing_baseline.pkl",
    )

    response = asyncio.run(
        bridge.request_authority(_make_request(
            decision_id="decision-missing-baseline"), timeout_ms=10)
    )

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "BASELINE_UNAVAILABLE"
    assert response.model_action is None
    assert response.apply_result is None


@pytest.mark.parametrize("artifact_kind", ["missing", "corrupt"])
def test_model_artifact_mismatch_fails_startup_without_zero_latent(
    tmp_path: Path, artifact_kind: str
) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    if artifact_kind == "corrupt":
        model_path.write_text("not a joblib artifact", encoding="utf-8")

    with pytest.raises(FatalStartupError) as excinfo:
        build_shadow_baseline_runtime(model_path=model_path)

    assert excinfo.value.reason_code == "MODEL_ARTIFACT_MISMATCH"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FATAL_STARTUP,
        reason_code=FailureReasonCode.MODEL_ARTIFACT_MISMATCH,
    ) == 1


def test_telemetry_flush_failure_becomes_degraded_observability(tmp_path: Path, monkeypatch) -> None:
    reset_failure_outcomes()
    telemetry = TelemetryLogger(log_dir=tmp_path, flush_threshold=1)
    monkeypatch.setattr(
        telemetry,
        "_rotate_if_needed",
        MagicMock(side_effect=OSError("telemetry disk unavailable")),
    )

    telemetry.log_step({"last_reward": 1.25, "total_train_steps": 1})

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.TELEMETRY_FLUSH_FAILED,
    ) == 1


def test_non_causal_snapshot_does_not_enter_inference_as_trainable_zero_vector(
) -> None:
    reset_failure_outcomes()
    config = _load_config()
    aggregator = NeocortexStateAggregator(
        config.ingest,
        strict_clock=True,
        neocortex_enforcement_mode="disabled",
    )
    runtime = NeocortexShadowRuntime(
        config=config,
        aggregator=aggregator,
        baseline_controller=SimpleNamespace(model_path=Path("unused")),
        shadow_emit_fn=MagicMock(),
        logger=logging.getLogger("tests.neocortex.failure_taxonomy"),
    )
    runtime.authority_bridge.request_authority = AsyncMock(
        side_effect=AssertionError(
            "bridge should not be invoked for non-trainable snapshots")
    )

    feature_event = {
        "event_name": "EVT:FEATURES_CALCULATED",
        "captured_ts_ms": 1_700_000_000_000,
        "payload": {
            "symbol": "BTCUSDT",
            "timestamp_ms": 1_700_000_000_000,
            "time_provenance": "captured_wallclock",
            "features": {
                "price": 100.0,
                "obi": 0.25,
                "delta_price": 1.0,
            },
        },
    }
    trigger_event = {
        "event_name": "EVT:BAR_CLOSED",
        "captured_ts_ms": 1_700_000_000_100,
        "payload": {
            "symbol": "BTCUSDT",
            "timestamp_ms": 1_700_000_000_100,
        },
    }

    assert asyncio.run(runtime.handle_event_frame(feature_event)) is None
    assert asyncio.run(runtime.handle_event_frame(trigger_event)) is None
    assert runtime.events_seen == 2
    assert runtime.snapshots_emitted == 0
    assert runtime.authority_bridge.request_authority.await_count == 0
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.NON_CAUSAL_TIME,
    ) == 2


def test_live_shadow_with_legacy_timestamp_remains_fatal() -> None:
    config = _live_shadow_legacy_config()
    with pytest.raises(ShadowGateViolationError):
        evaluate_startup_shadow_gates(
            config, logger=logging.getLogger("tests.neocortex.failure_taxonomy"))


def test_missing_runtime_config_remains_fatal(tmp_path: Path) -> None:
    reset_failure_outcomes()
    with pytest.raises(FatalStartupError) as excinfo:
        build_shadow_baseline_runtime(
            neocortex_config_dir=tmp_path / "missing-config")
    assert excinfo.value.reason_code == "CONFIG_MISSING"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FATAL_STARTUP,
        reason_code=FailureReasonCode.CONFIG_MISSING,
    ) == 1


def test_hot_path_broad_exception_audit() -> None:
    offenders = []
    for relative_path in HOT_PATH_FILES:
        content = (NEOCORTEX_ROOT / relative_path).read_text(encoding="utf-8")
        if "except Exception" in content or "except BaseException" in content or "except:" in content:
            offenders.append(relative_path)
    assert offenders == []


def test_bridge_unavailable_runtime_path_is_pending() -> None:
    pytest.skip("Phase 5 bridge-unavailable runtime mapping is pending")
