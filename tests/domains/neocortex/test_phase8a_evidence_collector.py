from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    ObservationEnvelope,
    build_observation_envelope,
)
from apps.reference.domains.neocortex.contracts.causal_time import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.datasets.contracts import (
    DatasetCutoverDecision,
)
from apps.reference.domains.neocortex.logic.evidence_collection import (
    NeocortexEvidenceCollector,
    write_evidence_collection_bundle,
)
from apps.reference.domains.neocortex.logic.evidence_collection.summary import (
    render_evidence_collection_markdown,
)


CONFIG_DIR = Path("apps/reference/domains/neocortex/config")


def _collector() -> NeocortexEvidenceCollector:
    config = load_config(CONFIG_DIR)
    return NeocortexEvidenceCollector(cutover_config=config.neuro.dataset.cutover)


def _trainable_snapshot():
    config = load_config(CONFIG_DIR)
    from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
        NeocortexStateAggregator,
    )

    aggregator = NeocortexStateAggregator(
        config.ingest,
        strict_clock=True,
        neocortex_enforcement_mode="disabled",
    )
    snapshot = aggregator.ingest_event(
        {
            "event_name": "EVT:FEATURES_CALCULATED",
            "captured_ts_ms": 1_700_000_000_000,
            "payload": {
                "symbol": "BTCUSDT",
                "timestamp_ms": 1_700_000_000_000,
                "time_provenance": CausalTimeProvenance.AURORA_EVENT.value,
                "features": {
                    "price": 100.0,
                    "obi": 0.25,
                    "delta_price": 1.0,
                },
            },
        }
    )
    assert snapshot is not None
    return snapshot


def _trainable_observation() -> ObservationEnvelope:
    snapshot = _trainable_snapshot()
    return build_observation_envelope(
        snapshot,
        {
            "decision_id": "decision-trainable",
            "event_name": "EVT:BAR_CLOSED",
            "observation": {"features": {"price": 100.0}},
            "intent": {"side": "BUY"},
        },
    )


def _diagnostics_only_observation() -> ObservationEnvelope:
    payload = _trainable_observation().model_dump(mode="json")
    payload.update(
        {
            "event_time_source": CausalTimeProvenance.CAPTURED_WALLCLOCK.value,
            "event_time_is_causal": False,
            "trainable": False,
            "dataset_visibility": "diagnostics_only",
        }
    )
    return ObservationEnvelope.model_validate(payload)


def _decision_row(
    *,
    decision_id: str,
    terminal_status: DecisionOutcomeTerminalStatus,
    dataset_visibility: str = "trainable",
    joined_by: str = "decision_id",
    invalid_reason_code: str | None = None,
    fallback: bool = False,
) -> DecisionOutcomeLedgerRow:
    payload = {
        "decision_id": decision_id,
        "rid": f"rid-{decision_id}",
        "symbol": "BTCUSDT",
        "authority_mode": "shadow",
        "request_ts_ms": 1_700_000_000_000,
        "response_ts_ms": 1_700_000_000_010,
        "terminal_status": terminal_status,
        "dataset_visibility": dataset_visibility,
        "invalid_reason_code": invalid_reason_code,
        "neocortex_action": "FALLBACK" if fallback else "ALLOW",
        "fallback_reason": "baseline_fallback" if fallback else None,
        "apply_result": "FALLBACK_BASELINE" if fallback else "GATED_ALLOW",
        "support_quality": {"joined_by": joined_by} if joined_by != "no_join" else {},
    }
    if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET and invalid_reason_code is None:
        payload["invalid_reason_code"] = "MISSING_REQUIRED_STATE"
    return DecisionOutcomeLedgerRow.model_validate(payload)


def test_valid_causal_observation_is_counted_as_trainable() -> None:
    collector = _collector()
    collector.collect_observation(_trainable_observation())

    bundle = collector.finalize()

    assert bundle.summary.observation.observation_envelope_count == 1
    assert bundle.summary.observation.causal_valid_count == 1
    assert bundle.summary.observation.trainable_count == 1
    assert bundle.summary.observation.diagnostics_only_count == 0
    assert bundle.summary.observation.invalid_count == 0


def test_non_causal_observation_is_excluded_from_trainable_count() -> None:
    collector = _collector()
    collector.collect_observation(_diagnostics_only_observation())

    bundle = collector.finalize()

    assert bundle.summary.observation.observation_envelope_count == 1
    assert bundle.summary.observation.causal_valid_count == 0
    assert bundle.summary.observation.trainable_count == 0
    assert bundle.summary.observation.diagnostics_only_count == 1
    assert bundle.summary.observation.invalid_count == 0


def test_diagnostics_only_ledger_row_is_excluded_from_trainable_count() -> None:
    collector = _collector()
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="diag-1",
            terminal_status=DecisionOutcomeTerminalStatus.VETOED,
            dataset_visibility="diagnostics_only",
            joined_by="rid",
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=False, reward_methodology="ope_v1")

    assert bundle.summary.decision_outcome.decision_row_count == 1
    assert bundle.summary.decision_outcome.trainable_count == 0
    assert bundle.summary.decision_outcome.diagnostics_only_count == 1
    assert bundle.summary.decision_outcome.rid_join_count == 1


def test_synthetic_fallback_rows_do_not_enter_trainable_counts() -> None:
    collector = _collector()
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="fallback-1",
            terminal_status=DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
            dataset_visibility="trainable",
            joined_by="trade_id",
            fallback=True,
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=True, reward_methodology="ope_v1")

    assert bundle.summary.decision_outcome.synthetic_fallback_count == 1
    assert bundle.summary.decision_outcome.trainable_count == 0
    assert bundle.summary.dataset_cutover_decision.cutover_allowed is False
    assert "SYNTHETIC_FALLBACK_PRESENT" in bundle.summary.dataset_cutover_decision.blocking_reasons


def test_missing_terminal_join_is_counted() -> None:
    collector = _collector()
    collector.collect_decision_outcome(
        {
            "decision_id": "no-terminal-1",
            "rid": "rid-no-terminal-1",
            "symbol": "BTCUSDT",
            "authority_mode": "shadow",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "dataset_visibility": "diagnostics_only",
            "neocortex_action": "ALLOW",
            "support_quality": {"joined_by": "decision_id"},
        }
    )

    bundle = collector.finalize(
        reward_valid_requested=False, reward_methodology="ope_v1")

    assert bundle.summary.decision_outcome.terminal_missing_count == 1
    assert bundle.summary.decision_outcome.decision_id_join_count == 1
    assert bundle.summary.invalid_reason_histogram["TERMINAL_EVENT_MISSING"] == 1


def test_decision_id_and_alias_joins_are_counted_separately() -> None:
    collector = _collector()
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="decision-id-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="decision_id",
        )
    )
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="alias-rid-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="rid",
        )
    )
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="alias-lifecycle-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="lifecycle_id",
        )
    )
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="alias-trade-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="trade_id",
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=True, reward_methodology="ope_v1")

    assert bundle.summary.decision_outcome.decision_id_join_count == 1
    assert bundle.summary.decision_outcome.rid_join_count == 1
    assert bundle.summary.decision_outcome.lifecycle_id_join_count == 1
    assert bundle.summary.decision_outcome.trade_id_join_count == 1
    assert bundle.summary.decision_outcome.no_join_count == 0


def test_reward_valid_without_methodology_is_blocked() -> None:
    collector = _collector()
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="real-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="decision_id",
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=True, reward_methodology=None)

    assert bundle.summary.reward_valid_requested is True
    assert bundle.summary.reward_methodology_present is False
    assert bundle.summary.reward_valid is False
    assert bundle.summary.dataset_cutover_decision.cutover_allowed is False
    assert "REWARD_INVALID" in bundle.summary.dataset_cutover_decision.blocking_reasons
    assert "REWARD_METHODOLOGY_MISSING" in bundle.summary.dataset_cutover_decision.blocking_reasons


def test_dataset_cutover_decision_blocks_unsafe_promotion() -> None:
    collector = _collector()
    collector.collect_observation(_trainable_observation())
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="real-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="decision_id",
        )
    )
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="fallback-2",
            terminal_status=DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
            dataset_visibility="trainable",
            joined_by="trade_id",
            fallback=True,
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=True, reward_methodology="ope_v1")

    assert isinstance(bundle.summary.dataset_cutover_decision,
                      DatasetCutoverDecision)
    assert bundle.summary.dataset_cutover_decision.cutover_allowed is False
    assert "SYNTHETIC_FALLBACK_PRESENT" in bundle.summary.dataset_cutover_decision.blocking_reasons


def test_legacy_experiments_package_is_not_imported_by_runtime_collector() -> None:
    collector = _collector()
    collector.collect_observation(_trainable_observation())
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="real-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="decision_id",
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=True, reward_methodology="ope_v1")

    assert bundle.summary.legacy_experiments_imported is False
    assert bundle.summary.legacy_experiments_modules == ()
    assert bundle.summary.evidence_bundle_complete is True


def test_writer_emits_deterministic_json_and_markdown_summary(tmp_path: Path) -> None:
    collector = _collector()
    collector.collect_observation(_trainable_observation())
    collector.collect_decision_outcome(
        _decision_row(
            decision_id="real-1",
            terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            joined_by="decision_id",
        )
    )

    bundle = collector.finalize(
        reward_valid_requested=True, reward_methodology="ope_v1")
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first_paths = write_evidence_collection_bundle(bundle, first_dir)
    second_paths = write_evidence_collection_bundle(bundle, second_dir)

    assert first_paths.json_path.read_text(
        encoding="utf-8") == second_paths.json_path.read_text(encoding="utf-8")
    assert first_paths.markdown_path.read_text(
        encoding="utf-8") == second_paths.markdown_path.read_text(encoding="utf-8")
    assert render_evidence_collection_markdown(bundle).startswith(
        "# Neocortex Phase 8A.1 Evidence Collection Bundle")
