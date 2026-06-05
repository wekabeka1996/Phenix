"""Offline Phase 6 review artifact generation."""

from __future__ import annotations

import math
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

from apps.reference.domains.alpha_search.judge.contracts import (
    EntryVerdict,
    LifecycleVerdict,
)
from apps.reference.domains.alpha_search.judge.identity import build_cycle_key
from apps.reference.domains.alpha_search.judge.review.config_models import (
    ReviewConfig,
    SegmentDimension,
)
from apps.reference.domains.alpha_search.judge.review.loaders import (
    LoadedChamber,
    LoadedEnvelope,
    LoadedVerdict,
    load_all_verdicts,
    load_chambers,
    load_envelopes,
    load_existing_calibration_dataset,
    load_existing_summary_report,
)
from apps.reference.domains.alpha_search.judge.simulator.cli import load_simulator_config
from apps.reference.domains.alpha_search.judge.simulator.disagreement_analyzer import (
    determine_optimal_action,
)
from apps.reference.domains.alpha_search.judge.simulator.fee_slippage_calculator import (
    compute_net_return,
)
from apps.reference.domains.alpha_search.judge.simulator.simulator_engine import (
    CorrelatedVerdictOutcome,
    SimulationResult,
    run_simulation,
)


_ENTRY_VERDICTS: tuple[EntryVerdict, ...] = (
    "OPEN_LONG",
    "OPEN_SHORT",
    "NO_ENTRY",
    "SUPPRESS",
    "UNKNOWN",
)
_LIFECYCLE_VERDICTS: tuple[LifecycleVerdict, ...] = (
    "HOLD",
    "PROTECT",
    "EXIT",
    "SUPPRESS",
    "UNKNOWN",
)
_COMPARISON_FIELDS = [
    "segment_type",
    "segment_value",
    "entry_verdict_count",
    "matched_outcome_count",
    "chamber_only_available_count",
    "final_judge_available_count",
    "incumbent_available",
    "null_baseline_available_count",
    "final_avg_modeled_net_return",
    "chamber_avg_modeled_net_return",
    "null_baseline_avg_modeled_net_return",
    "final_minus_chamber_avg_modeled_net_return",
    "final_minus_null_avg_modeled_net_return",
    "final_vs_chamber_action_diff_count",
    "final_vs_chamber_action_same_count",
    "final_vs_chamber_avg_confidence_delta",
    "final_unknown_count",
    "final_suppress_count",
]
_SUPPRESSION_FIELDS = [
    "segment_type",
    "segment_value",
    "entry_verdict_count",
    "unknown_count",
    "unknown_rate",
    "unknown_total_opportunity_cost",
    "unknown_avg_opportunity_cost",
    "suppress_count",
    "suppress_rate",
    "suppress_total_opportunity_cost",
    "suppress_avg_opportunity_cost",
    "no_entry_count",
    "chamber_inadmissible_count",
    "chamber_quorum_insufficient_count",
]
_DISAGREEMENT_FIELDS = [
    "segment_type",
    "segment_value",
    "verdict_action",
    "optimal_action",
    "count",
    "avg_cost_of_disagreement",
    "total_cost_of_disagreement",
    "avg_confidence",
    "dissent_noted_rate",
]
_CALIBRATION_FIELDS = [
    "segment_type",
    "segment_value",
    "confidence_bucket",
    "record_count",
    "avg_confidence",
    "avg_net_return",
    "correct_entry_count",
    "incorrect_entry_count",
    "correct_abstain_count",
    "missed_opportunity_count",
    "inconclusive_count",
    "disagreement_count",
]
_SURFACE_FIELDS = ["surface", "status", "observed_count", "note"]

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChamberProjection:
    action: EntryVerdict
    confidence: float
    admissibility: str
    consensus_direction: str | None


@dataclass(frozen=True)
class EntryReviewRecord:
    verdict_id: str
    strategy_id: str
    symbol: str
    tf_sec: int
    bar_close_ts: int
    source_file: str
    regime: str | None
    regime_confidence: float | None
    final_action: EntryVerdict
    final_confidence: float
    final_dissent_noted: bool
    final_authority_mode: str
    final_applied: bool
    chamber_available: bool
    chamber_admissibility: str | None
    chamber_consensus_direction: str | None
    chamber_consensus_strength: float | None
    chamber_action: EntryVerdict | None
    chamber_confidence: float | None
    chamber_expert_count: int | None
    chamber_responding_count: int | None
    chamber_abstaining_count: int | None
    outcome_available: bool
    matched_trade: bool | None
    optimal_action: str | None
    final_modeled_net_return: float | None
    chamber_modeled_net_return: float | None
    null_baseline_net_return: float | None
    final_minus_chamber_net_return: float | None
    final_minus_null_net_return: float | None
    has_disagreement: bool
    cost_of_disagreement: float | None
    final_cohort: str | None
    suppression_unknown_opportunity_cost: float | None


def _safe_mean(values: Iterable[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _round_or_none(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _entry_cycle_key(symbol: str, tf_sec: int, ts_ms: int) -> str:
    return build_cycle_key("ENTRY", symbol, tf_sec, ts_ms)


def _cycle_key_from_record(record: dict[str, object]) -> str | None:
    symbol = record.get("symbol")
    tf_sec = record.get("tf_sec")
    bar_close_ts = record.get("bar_close_ts")
    if not isinstance(symbol, str):
        return None
    try:
        return _entry_cycle_key(symbol, int(tf_sec), int(bar_close_ts))
    except (TypeError, ValueError):
        return None


def _register_unique_stage_id(
    unique_map: dict[str, tuple[str, object]],
    collisions: dict[str, set[str]],
    *,
    stage_id: str,
    cycle_key: str,
    loaded: object,
) -> None:
    existing = unique_map.get(stage_id)
    if existing is None:
        unique_map[stage_id] = (cycle_key, loaded)
        return
    existing_cycle_key, _ = existing
    if existing_cycle_key == cycle_key:
        return
    collisions.setdefault(stage_id, {existing_cycle_key}).add(cycle_key)
    unique_map.pop(stage_id, None)


def _finalize_unique_stage_index(
    surface: str,
    unique_map: dict[str, tuple[str, object]],
    collisions: dict[str, set[str]],
) -> dict[str, object]:
    for stage_id, cycle_keys in sorted(collisions.items()):
        LOG.warning(
            "Judge review detected %s collision for stage-local id '%s' across "
            "cycle_keys=%s; cycle_key joins remain authoritative",
            surface,
            stage_id,
            sorted(cycle_keys),
        )
    return {
        stage_id: loaded
        for stage_id, (_, loaded) in unique_map.items()
    }


def _build_chamber_index(
    chambers: Sequence[LoadedChamber],
    envelopes: Sequence[LoadedEnvelope],
) -> tuple[dict[str, LoadedChamber], dict[str, LoadedChamber]]:
    index: dict[str, LoadedChamber] = {}
    unique_by_id: dict[str, tuple[str, object]] = {}
    collisions: dict[str, set[str]] = {}
    for loaded in chambers:
        index.setdefault(loaded.chamber.cycle_key, loaded)
        _register_unique_stage_id(
            unique_by_id,
            collisions,
            stage_id=loaded.chamber.chamber_id,
            cycle_key=loaded.chamber.cycle_key,
            loaded=loaded,
        )
    for loaded in envelopes:
        chamber = LoadedChamber(
            chamber=loaded.envelope.chamber_aggregate,
            source_file=loaded.source_file,
        )
        index.setdefault(
            loaded.envelope.chamber_aggregate.cycle_key,
            chamber,
        )
        _register_unique_stage_id(
            unique_by_id,
            collisions,
            stage_id=loaded.envelope.chamber_aggregate.chamber_id,
            cycle_key=loaded.envelope.chamber_aggregate.cycle_key,
            loaded=chamber,
        )
    return index, _finalize_unique_stage_index(
        "chamber_id",
        unique_by_id,
        collisions,
    )


def _build_envelope_indices(
    envelopes: Sequence[LoadedEnvelope],
) -> tuple[
    dict[str, LoadedEnvelope],
    dict[str, LoadedEnvelope],
    dict[str, LoadedEnvelope],
]:
    by_cycle_key: dict[str, LoadedEnvelope] = {}
    unique_by_id: dict[str, tuple[str, object]] = {}
    unique_by_chamber_id: dict[str, tuple[str, object]] = {}
    envelope_id_collisions: dict[str, set[str]] = {}
    chamber_id_collisions: dict[str, set[str]] = {}
    for loaded in envelopes:
        by_cycle_key.setdefault(loaded.envelope.cycle_key, loaded)
        _register_unique_stage_id(
            unique_by_id,
            envelope_id_collisions,
            stage_id=loaded.envelope.envelope_id,
            cycle_key=loaded.envelope.cycle_key,
            loaded=loaded,
        )
        _register_unique_stage_id(
            unique_by_chamber_id,
            chamber_id_collisions,
            stage_id=loaded.envelope.chamber_aggregate.chamber_id,
            cycle_key=loaded.envelope.cycle_key,
            loaded=loaded,
        )
    return (
        by_cycle_key,
        _finalize_unique_stage_index(
            "envelope_id",
            unique_by_id,
            envelope_id_collisions,
        ),
        _finalize_unique_stage_index(
            "envelope.chamber_id",
            unique_by_chamber_id,
            chamber_id_collisions,
        ),
    )


def _derive_chamber_projection(loaded: LoadedChamber | None) -> ChamberProjection | None:
    if loaded is None or loaded.chamber.verdict_scope != "ENTRY":
        return None
    chamber = loaded.chamber
    if chamber.admissibility != "ADMISSIBLE" or chamber.consensus_direction is None:
        return ChamberProjection(
            action="UNKNOWN",
            confidence=0.0,
            admissibility=chamber.admissibility,
            consensus_direction=chamber.consensus_direction,
        )
    if chamber.consensus_direction == "LONG":
        action: EntryVerdict = "OPEN_LONG"
    elif chamber.consensus_direction == "SHORT":
        action = "OPEN_SHORT"
    else:
        action = "NO_ENTRY"
    return ChamberProjection(
        action=action,
        confidence=chamber.consensus_strength,
        admissibility=chamber.admissibility,
        consensus_direction=chamber.consensus_direction,
    )


def _compute_modeled_action_return(
    *,
    action: str,
    correlation: CorrelatedVerdictOutcome | None,
    fee_per_cycle_bps: float,
    slippage_pct: float,
) -> float | None:
    if correlation is None or correlation.outcome is None:
        return None

    outcome = correlation.outcome
    if action == "NO_ENTRY":
        return 0.0
    if action == "OPEN_LONG":
        if (
            not outcome.matched_trade
            or outcome.entry_price is None
            or outcome.exit_price is None
        ):
            return 0.0
        return compute_net_return(
            outcome.entry_price,
            outcome.exit_price,
            "LONG",
            fee_per_cycle_bps,
            slippage_pct,
        )
    if action == "OPEN_SHORT":
        if (
            not outcome.matched_trade
            or outcome.entry_price is None
            or outcome.exit_price is None
        ):
            return 0.0
        return compute_net_return(
            outcome.entry_price,
            outcome.exit_price,
            "SHORT",
            fee_per_cycle_bps,
            slippage_pct,
        )
    return None


def _compute_optimal_action(
    correlation: CorrelatedVerdictOutcome | None,
    *,
    fee_per_cycle_bps: float,
    slippage_pct: float,
) -> str | None:
    if correlation is None or correlation.outcome is None:
        return None
    outcome = correlation.outcome
    return determine_optimal_action(
        matched_trade=outcome.matched_trade,
        entry_price=outcome.entry_price,
        exit_price=outcome.exit_price,
        fee_per_cycle_bps=fee_per_cycle_bps,
        slippage_pct=slippage_pct,
    )


def _build_entry_records(
    *,
    verdicts: Sequence[LoadedVerdict],
    chamber_by_cycle_key: dict[str, LoadedChamber],
    chamber_by_id: dict[str, LoadedChamber],
    envelope_by_cycle_key: dict[str, LoadedEnvelope],
    envelope_by_id: dict[str, LoadedEnvelope],
    envelope_by_chamber_id: dict[str, LoadedEnvelope],
    simulation_result: SimulationResult,
    fee_per_cycle_bps: float,
    slippage_pct: float,
) -> list[EntryReviewRecord]:
    correlation_by_cycle_key = {
        _entry_cycle_key(
            correlation.verdict.correlation_key.symbol,
            correlation.verdict.correlation_key.tf_sec,
            correlation.verdict.correlation_key.bar_close_ts,
        ): correlation
        for correlation in simulation_result.correlations
    }
    disagreement_by_cycle_key = {
        cycle_key: record
        for record in simulation_result.disagreements
        for cycle_key in [_cycle_key_from_record(record)]
        if cycle_key is not None
    }
    calibration_by_cycle_key = {
        cycle_key: record
        for record in simulation_result.calibration_records
        for cycle_key in [_cycle_key_from_record(record)]
        if cycle_key is not None
    }

    records: list[EntryReviewRecord] = []
    for loaded in verdicts:
        verdict = loaded.verdict
        if verdict.verdict_scope != "ENTRY" or verdict.entry_verdict is None:
            continue

        envelope = envelope_by_cycle_key.get(verdict.cycle_key)
        if envelope is None:
            envelope = envelope_by_id.get(verdict.envelope_id)
        if envelope is None:
            envelope = envelope_by_chamber_id.get(verdict.chamber_id)
        chamber = chamber_by_cycle_key.get(verdict.cycle_key)
        if chamber is None:
            chamber = chamber_by_id.get(verdict.chamber_id)
        projection = _derive_chamber_projection(chamber)
        correlation = correlation_by_cycle_key.get(verdict.cycle_key)
        disagreement = disagreement_by_cycle_key.get(verdict.cycle_key)
        calibration = calibration_by_cycle_key.get(verdict.cycle_key)
        optimal_action = _compute_optimal_action(
            correlation,
            fee_per_cycle_bps=fee_per_cycle_bps,
            slippage_pct=slippage_pct,
        )
        final_modeled = _compute_modeled_action_return(
            action=verdict.entry_verdict,
            correlation=correlation,
            fee_per_cycle_bps=fee_per_cycle_bps,
            slippage_pct=slippage_pct,
        )
        chamber_modeled = None
        chamber_delta = None
        if projection is not None:
            chamber_modeled = _compute_modeled_action_return(
                action=projection.action,
                correlation=correlation,
                fee_per_cycle_bps=fee_per_cycle_bps,
                slippage_pct=slippage_pct,
            )
            if final_modeled is not None and chamber_modeled is not None:
                chamber_delta = final_modeled - chamber_modeled

        null_baseline = None
        if correlation is not None and correlation.outcome is not None:
            null_baseline = 0.0

        suppression_unknown_opportunity_cost = None
        if verdict.entry_verdict in {"SUPPRESS", "UNKNOWN"}:
            optimal_net = None
            if optimal_action is not None:
                optimal_net = _compute_modeled_action_return(
                    action=optimal_action,
                    correlation=correlation,
                    fee_per_cycle_bps=fee_per_cycle_bps,
                    slippage_pct=slippage_pct,
                )
            suppression_unknown_opportunity_cost = 0.0
            if optimal_net is not None:
                suppression_unknown_opportunity_cost = max(0.0, optimal_net)

        records.append(
            EntryReviewRecord(
                verdict_id=verdict.verdict_id,
                strategy_id=verdict.strategy_id,
                symbol=verdict.symbol,
                tf_sec=verdict.tf_sec,
                bar_close_ts=verdict.ts_ms,
                source_file=loaded.source_file,
                regime=envelope.envelope.regime if envelope is not None else None,
                regime_confidence=(
                    envelope.envelope.regime_confidence
                    if envelope is not None
                    else None
                ),
                final_action=verdict.entry_verdict,
                final_confidence=verdict.confidence,
                final_dissent_noted=verdict.dissent_noted,
                final_authority_mode=verdict.authority_mode,
                final_applied=verdict.applied,
                chamber_available=projection is not None,
                chamber_admissibility=(
                    projection.admissibility if projection is not None else None
                ),
                chamber_consensus_direction=(
                    projection.consensus_direction if projection is not None else None
                ),
                chamber_consensus_strength=(
                    projection.confidence if projection is not None else None
                ),
                chamber_action=projection.action if projection is not None else None,
                chamber_confidence=(
                    projection.confidence if projection is not None else None
                ),
                chamber_expert_count=(
                    chamber.chamber.expert_count if chamber is not None else None
                ),
                chamber_responding_count=(
                    chamber.chamber.responding_count if chamber is not None else None
                ),
                chamber_abstaining_count=(
                    chamber.chamber.abstaining_count if chamber is not None else None
                ),
                outcome_available=correlation is not None and correlation.outcome is not None,
                matched_trade=(
                    correlation.outcome.matched_trade
                    if correlation is not None and correlation.outcome is not None
                    else None
                ),
                optimal_action=optimal_action,
                final_modeled_net_return=final_modeled,
                chamber_modeled_net_return=chamber_modeled,
                null_baseline_net_return=null_baseline,
                final_minus_chamber_net_return=chamber_delta,
                final_minus_null_net_return=(
                    final_modeled if final_modeled is not None and null_baseline is not None else None
                ),
                has_disagreement=disagreement is not None,
                cost_of_disagreement=(
                    float(disagreement["cost_of_disagreement"])
                    if disagreement is not None
                    else None
                ),
                final_cohort=(
                    str(calibration["cohort"])
                    if calibration is not None and "cohort" in calibration
                    else None
                ),
                suppression_unknown_opportunity_cost=suppression_unknown_opportunity_cost,
            )
        )

    return records


def _segment_value(record: EntryReviewRecord, dimension: SegmentDimension) -> str | None:
    if dimension == "symbol":
        return record.symbol
    if dimension == "regime":
        return record.regime
    if dimension == "tf_sec":
        return str(record.tf_sec)
    return record.source_file


def _group_records(
    records: Sequence[EntryReviewRecord],
    dimension: SegmentDimension,
) -> dict[str, list[EntryReviewRecord]]:
    grouped: dict[str, list[EntryReviewRecord]] = defaultdict(list)
    for record in records:
        value = _segment_value(record, dimension)
        if value is None:
            continue
        grouped[value].append(record)
    return dict(grouped)


def _build_comparison_rows(
    records: Sequence[EntryReviewRecord],
    dimensions: Sequence[SegmentDimension],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for dimension in dimensions:
        for value, group in sorted(_group_records(records, dimension).items()):
            chamber_pairs = [
                record for record in group if record.chamber_action is not None
            ]
            action_diff_count = sum(
                1
                for record in chamber_pairs
                if record.final_action != record.chamber_action
            )
            action_same_count = sum(
                1
                for record in chamber_pairs
                if record.final_action == record.chamber_action
            )
            rows.append(
                {
                    "segment_type": dimension,
                    "segment_value": value,
                    "entry_verdict_count": len(group),
                    "matched_outcome_count": sum(
                        1 for record in group if record.outcome_available
                    ),
                    "chamber_only_available_count": len(chamber_pairs),
                    "final_judge_available_count": len(group),
                    "incumbent_available": False,
                    "null_baseline_available_count": sum(
                        1
                        for record in group
                        if record.null_baseline_net_return is not None
                    ),
                    "final_avg_modeled_net_return": _round_or_none(
                        _safe_mean(
                            record.final_modeled_net_return for record in group)
                    ),
                    "chamber_avg_modeled_net_return": _round_or_none(
                        _safe_mean(
                            record.chamber_modeled_net_return for record in chamber_pairs
                        )
                    ),
                    "null_baseline_avg_modeled_net_return": _round_or_none(
                        _safe_mean(
                            record.null_baseline_net_return for record in group
                        )
                    ),
                    "final_minus_chamber_avg_modeled_net_return": _round_or_none(
                        _safe_mean(
                            record.final_minus_chamber_net_return for record in chamber_pairs
                        )
                    ),
                    "final_minus_null_avg_modeled_net_return": _round_or_none(
                        _safe_mean(
                            record.final_minus_null_net_return for record in group
                        )
                    ),
                    "final_vs_chamber_action_diff_count": action_diff_count,
                    "final_vs_chamber_action_same_count": action_same_count,
                    "final_vs_chamber_avg_confidence_delta": _round_or_none(
                        _safe_mean(
                            (
                                record.final_confidence - record.chamber_confidence
                                if record.chamber_confidence is not None
                                else None
                            )
                            for record in chamber_pairs
                        )
                    ),
                    "final_unknown_count": sum(
                        1 for record in group if record.final_action == "UNKNOWN"
                    ),
                    "final_suppress_count": sum(
                        1 for record in group if record.final_action == "SUPPRESS"
                    ),
                }
            )
    return rows


def _build_suppression_rows(
    records: Sequence[EntryReviewRecord],
    dimensions: Sequence[SegmentDimension],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for dimension in dimensions:
        for value, group in sorted(_group_records(records, dimension).items()):
            unknown_group = [
                record for record in group if record.final_action == "UNKNOWN"
            ]
            suppress_group = [
                record for record in group if record.final_action == "SUPPRESS"
            ]
            rows.append(
                {
                    "segment_type": dimension,
                    "segment_value": value,
                    "entry_verdict_count": len(group),
                    "unknown_count": len(unknown_group),
                    "unknown_rate": _round_or_none(
                        len(unknown_group) / len(group) if group else None
                    ),
                    "unknown_total_opportunity_cost": _round_or_none(
                        sum(
                            record.suppression_unknown_opportunity_cost or 0.0
                            for record in unknown_group
                        )
                    ),
                    "unknown_avg_opportunity_cost": _round_or_none(
                        _safe_mean(
                            record.suppression_unknown_opportunity_cost
                            for record in unknown_group
                        )
                    ),
                    "suppress_count": len(suppress_group),
                    "suppress_rate": _round_or_none(
                        len(suppress_group) / len(group) if group else None
                    ),
                    "suppress_total_opportunity_cost": _round_or_none(
                        sum(
                            record.suppression_unknown_opportunity_cost or 0.0
                            for record in suppress_group
                        )
                    ),
                    "suppress_avg_opportunity_cost": _round_or_none(
                        _safe_mean(
                            record.suppression_unknown_opportunity_cost
                            for record in suppress_group
                        )
                    ),
                    "no_entry_count": sum(
                        1 for record in group if record.final_action == "NO_ENTRY"
                    ),
                    "chamber_inadmissible_count": sum(
                        1
                        for record in group
                        if record.chamber_admissibility == "INADMISSIBLE"
                    ),
                    "chamber_quorum_insufficient_count": sum(
                        1
                        for record in group
                        if record.chamber_admissibility == "QUORUM_INSUFFICIENT"
                    ),
                }
            )
    return rows


def _build_disagreement_rows(
    records: Sequence[EntryReviewRecord],
    dimensions: Sequence[SegmentDimension],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    actionable = [record for record in records if record.has_disagreement]
    for dimension in dimensions:
        buckets: dict[tuple[str, str, str],
                      list[EntryReviewRecord]] = defaultdict(list)
        for record in actionable:
            value = _segment_value(record, dimension)
            if value is None or record.optimal_action is None:
                continue
            buckets[(value, record.final_action,
                     record.optimal_action)].append(record)
        for (value, verdict_action, optimal_action), group in sorted(buckets.items()):
            rows.append(
                {
                    "segment_type": dimension,
                    "segment_value": value,
                    "verdict_action": verdict_action,
                    "optimal_action": optimal_action,
                    "count": len(group),
                    "avg_cost_of_disagreement": _round_or_none(
                        _safe_mean(
                            record.cost_of_disagreement for record in group)
                    ),
                    "total_cost_of_disagreement": _round_or_none(
                        sum(record.cost_of_disagreement or 0.0 for record in group)
                    ),
                    "avg_confidence": _round_or_none(
                        _safe_mean(record.final_confidence for record in group)
                    ),
                    "dissent_noted_rate": _round_or_none(
                        sum(1 for record in group if record.final_dissent_noted) / len(group)
                        if group
                        else None
                    ),
                }
            )
    return rows


def _bucket_label(edges: Sequence[float], confidence: float) -> str:
    for index in range(len(edges) - 1):
        lower = edges[index]
        upper = edges[index + 1]
        is_last = index == len(edges) - 2
        if lower <= confidence < upper or (is_last and math.isclose(confidence, upper)):
            return f"[{lower:.2f},{upper:.2f}]"
    return f"[{edges[-2]:.2f},{edges[-1]:.2f}]"


def _build_calibration_rows(
    records: Sequence[EntryReviewRecord],
    dimensions: Sequence[SegmentDimension],
    bucket_edges: Sequence[float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    calibration_records = [
        record for record in records if record.final_cohort is not None
    ]
    for dimension in dimensions:
        buckets: dict[tuple[str, str],
                      list[EntryReviewRecord]] = defaultdict(list)
        for record in calibration_records:
            value = _segment_value(record, dimension)
            if value is None:
                continue
            buckets[(value, _bucket_label(bucket_edges,
                     record.final_confidence))].append(record)

        for (value, bucket), group in sorted(buckets.items()):
            cohort_counts = Counter(record.final_cohort for record in group)
            rows.append(
                {
                    "segment_type": dimension,
                    "segment_value": value,
                    "confidence_bucket": bucket,
                    "record_count": len(group),
                    "avg_confidence": _round_or_none(
                        _safe_mean(record.final_confidence for record in group)
                    ),
                    "avg_net_return": _round_or_none(
                        _safe_mean(
                            record.final_modeled_net_return for record in group)
                    ),
                    "correct_entry_count": cohort_counts.get("CORRECT_ENTRY", 0),
                    "incorrect_entry_count": cohort_counts.get("INCORRECT_ENTRY", 0),
                    "correct_abstain_count": cohort_counts.get("CORRECT_ABSTAIN", 0),
                    "missed_opportunity_count": cohort_counts.get("MISSED_OPPORTUNITY", 0),
                    "inconclusive_count": cohort_counts.get("INCONCLUSIVE", 0),
                    "disagreement_count": sum(
                        1 for record in group if record.has_disagreement
                    ),
                }
            )
    return rows


def _build_surface_support(
    *,
    entry_records: Sequence[EntryReviewRecord],
    lifecycle_verdicts: Sequence[LoadedVerdict],
    chambers: Sequence[LoadedChamber],
    envelopes: Sequence[LoadedEnvelope],
    simulation_result: SimulationResult,
) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    lifecycle_actionable = sum(
        1
        for loaded in lifecycle_verdicts
        if loaded.verdict.verdict_scope == "LIFECYCLE"
        and loaded.verdict.lifecycle_verdict not in {None, "UNKNOWN", "SUPPRESS"}
    )
    entry_chamber_observed = sum(
        1 for record in entry_records if record.chamber_available)
    support = {
        "entry_chamber": {
            "status": "supported" if entry_chamber_observed else "insufficient",
            "observed_count": entry_chamber_observed,
            "note": (
                "Entry chamber comparison is reconstructable from chamber or envelope artifacts."
                if entry_chamber_observed
                else "No entry chamber artifacts were joined for chamber-only comparison."
            ),
        },
        "lifecycle_chamber": {
            "status": "insufficient" if lifecycle_actionable == 0 else "partial",
            "observed_count": lifecycle_actionable,
            "note": (
                "No actionable lifecycle verdict evidence observed; current lifecycle review remains nominal."
                if lifecycle_actionable == 0
                else "Lifecycle artifacts exist, but coverage remains weaker than entry review."
            ),
        },
        "final_judge": {
            "status": "supported" if entry_records else "insufficient",
            "observed_count": len(entry_records),
            "note": "Final judge entry verdicts were loaded from shadow verdict artifacts.",
        },
        "verdict_mapping": {
            "status": "supported" if entry_chamber_observed else "partial",
            "observed_count": entry_chamber_observed,
            "note": (
                "Chamber-to-verdict mapping can be compared where chamber artifacts exist."
                if entry_chamber_observed
                else "Verdict mapping review is blocked by missing chamber-side artifacts."
            ),
        },
        "simulator_derived_economics": {
            "status": "supported" if simulation_result.matched_count > 0 else "insufficient",
            "observed_count": simulation_result.matched_count,
            "note": (
                "Simulator-derived economics are available from matched verdict-outcome correlations."
                if simulation_result.matched_count > 0
                else "No matched verdict-outcome correlations; economics review is unavailable."
            ),
        },
        "disagreement_analysis": {
            "status": "supported" if simulation_result.matched_count > 0 else "insufficient",
            "observed_count": len(simulation_result.disagreements),
            "note": "Disagreement buckets are derived from the existing Phase 5 cost model.",
        },
        "calibration_confidence": {
            "status": "supported" if simulation_result.calibration_records else "insufficient",
            "observed_count": len(simulation_result.calibration_records),
            "note": (
                "Calibration slices are available from matched calibration records."
                if simulation_result.calibration_records
                else "No calibration records were derived from the current evidence set."
            ),
        },
    }
    rows = [
        {
            "surface": surface,
            "status": payload["status"],
            "observed_count": payload["observed_count"],
            "note": payload["note"],
        }
        for surface, payload in support.items()
    ]
    return support, rows


def _build_evidence_class_support(
    *,
    entry_records: Sequence[EntryReviewRecord],
    support: dict[str, dict[str, object]],
    comparison_rows: Sequence[dict[str, object]],
    suppression_rows: Sequence[dict[str, object]],
    disagreement_rows: Sequence[dict[str, object]],
    calibration_rows: Sequence[dict[str, object]],
) -> dict[str, dict[str, object]]:
    non_shadow_count = sum(
        1 for record in entry_records if record.final_authority_mode != "shadow"
    )
    applied_count = sum(1 for record in entry_records if record.final_applied)
    chamber_available_count = sum(
        1 for record in entry_records if record.chamber_available
    )
    return {
        "structural": {
            "status": "partial",
            "note": (
                "Artifact-level structural checks cover shadow authority_mode and applied=false counts; ownership and docs alignment still require manual review."
            ),
            "artifact_support": {
                "non_shadow_count": non_shadow_count,
                "applied_true_count": applied_count,
            },
        },
        "behavioral": {
            "status": "automated",
            "note": "Verdict classes, chamber admissibility, and suppression/UNKNOWN accounting are directly derived from stored artifacts.",
            "artifact_support": {
                "comparison_rows": len(comparison_rows),
                "suppression_rows": len(suppression_rows),
            },
        },
        "replay": {
            "status": "partial",
            "note": "The tooling consumes replay artifacts and exact-key simulator joins, but does not independently prove cross-run reproducibility beyond current artifact consistency checks.",
            "artifact_support": {
                "entry_records": len(entry_records),
            },
        },
        "economic": {
            "status": (
                "automated"
                if support["simulator_derived_economics"]["status"] == "supported"
                else "blocked"
            ),
            "note": support["simulator_derived_economics"]["note"],
            "artifact_support": {
                "disagreement_rows": len(disagreement_rows),
            },
        },
        "comparative": {
            "status": "partial" if chamber_available_count else "manual_only",
            "note": (
                "Chamber-only, final-judge, and no-judge abstain baselines are automated where chamber artifacts exist; incumbent baseline remains unavailable from current repo-supported evidence."
            ),
            "artifact_support": {
                "chamber_available_count": chamber_available_count,
                "comparison_rows": len(comparison_rows),
            },
        },
        "operator_observability": {
            "status": "automated",
            "note": "Machine-readable bundle, markdown summary, and CSV tables make missing surfaces and partial joins explicit.",
            "artifact_support": {
                "calibration_rows": len(calibration_rows),
            },
        },
    }


def _build_segmentation_coverage(
    records: Sequence[EntryReviewRecord],
    dimensions: Sequence[SegmentDimension],
) -> dict[str, object]:
    coverage: dict[str, object] = {
        "requested_dimensions": list(dimensions),
        "dimensions": {},
    }
    for dimension in dimensions:
        values = [_segment_value(record, dimension) for record in records]
        non_missing = [value for value in values if value is not None]
        coverage["dimensions"][dimension] = {
            "supported": bool(non_missing),
            "distinct_count": len(set(non_missing)),
            "non_missing_count": len(non_missing),
            "missing_count": len(values) - len(non_missing),
        }
    return coverage


def _count_entry_verdicts(records: Sequence[EntryReviewRecord]) -> dict[str, int]:
    counts = Counter(record.final_action for record in records)
    return {verdict: counts.get(verdict, 0) for verdict in _ENTRY_VERDICTS}


def _count_lifecycle_verdicts(verdicts: Sequence[LoadedVerdict]) -> dict[str, int]:
    counts = Counter(
        loaded.verdict.lifecycle_verdict
        for loaded in verdicts
        if loaded.verdict.verdict_scope == "LIFECYCLE"
    )
    return {verdict: counts.get(verdict, 0) for verdict in _LIFECYCLE_VERDICTS}


def _count_chamber_classes(chambers: Sequence[LoadedChamber]) -> dict[str, object]:
    scope_counts: dict[str, dict[str, int]] = {
        "ENTRY": Counter(),
        "LIFECYCLE": Counter(),
    }
    direction_counts: dict[str, dict[str, int]] = {
        "ENTRY": Counter(),
        "LIFECYCLE": Counter(),
    }
    for loaded in chambers:
        scope = loaded.chamber.verdict_scope
        scope_counts[scope][loaded.chamber.admissibility] += 1
        direction = loaded.chamber.consensus_direction or "NONE"
        direction_counts[scope][direction] += 1
    return {
        "admissibility": {
            scope: dict(counts) for scope, counts in scope_counts.items()
        },
        "consensus_direction": {
            scope: dict(counts) for scope, counts in direction_counts.items()
        },
    }


def _build_baseline_availability(
    records: Sequence[EntryReviewRecord],
) -> dict[str, dict[str, object]]:
    chamber_count = sum(
        1 for record in records if record.chamber_action is not None)
    matched_outcomes = sum(1 for record in records if record.outcome_available)
    return {
        "incumbent_only": {
            "status": "unavailable",
            "note": "No repo-produced incumbent-only baseline artifact was discovered in the current review inputs.",
            "available_count": 0,
        },
        "chamber_only": {
            "status": (
                "available"
                if chamber_count == len(records) and records
                else "partial" if chamber_count else "unavailable"
            ),
            "note": (
                "Chamber-only baseline is reconstructed from stored chamber or envelope artifacts."
                if chamber_count
                else "No chamber-side artifact was available to reconstruct a chamber-only baseline."
            ),
            "available_count": chamber_count,
        },
        "final_judge": {
            "status": "available" if records else "unavailable",
            "note": "Final judge baseline is loaded from stored verdict artifacts.",
            "available_count": len(records),
        },
        "no_judge_abstain": {
            "status": "available" if matched_outcomes else "partial",
            "note": "The no-judge abstain baseline is the bounded NO_ENTRY return of 0.0 where outcome coverage exists.",
            "available_count": matched_outcomes,
        },
    }


def _build_input_coverage(
    *,
    simulator_config_path: str,
    simulator_config_path_resolved: str,
    judge_logs_path: str,
    outcome_data_path: str,
    simulation_result: SimulationResult,
    verdicts: Sequence[LoadedVerdict],
    chambers: Sequence[LoadedChamber],
    envelopes: Sequence[LoadedEnvelope],
    entry_records: Sequence[EntryReviewRecord],
    existing_calibration_present: bool,
    existing_summary_present: bool,
) -> dict[str, object]:
    chamber_joined = sum(
        1 for record in entry_records if record.chamber_available)
    regime_joined = sum(
        1 for record in entry_records if record.regime is not None)
    return {
        "judge_simulator_config_path": simulator_config_path,
        "judge_simulator_config_path_resolved": simulator_config_path_resolved,
        "judge_logs_path": judge_logs_path,
        "outcome_data_path": outcome_data_path,
        "verdict_file_count": len({loaded.source_file for loaded in verdicts}),
        "chamber_file_count": len({loaded.source_file for loaded in chambers}),
        "envelope_file_count": len({loaded.source_file for loaded in envelopes}),
        "entry_verdict_count": len(entry_records),
        "lifecycle_verdict_count": sum(
            1
            for loaded in verdicts
            if loaded.verdict.verdict_scope == "LIFECYCLE"
        ),
        "matched_count": simulation_result.matched_count,
        "unmatched_count": simulation_result.unmatched_count,
        "chamber_joined_count": chamber_joined,
        "chamber_join_rate": _round_or_none(
            chamber_joined / len(entry_records) if entry_records else None
        ),
        "regime_joined_count": regime_joined,
        "regime_join_rate": _round_or_none(
            regime_joined / len(entry_records) if entry_records else None
        ),
        "existing_phase5_calibration_present": existing_calibration_present,
        "existing_phase5_summary_present": existing_summary_present,
    }


def _build_existing_phase5_artifact_summary(
    *,
    simulator_config,
    derived_calibration_records: Sequence[dict[str, object]],
    derived_summary_report: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str]]:
    flags: list[str] = []
    notes: list[str] = []

    calibration_path = Path(simulator_config.calibration_dataset_path)
    summary_path = Path(simulator_config.summary_report_path)

    calibration_payload: dict[str, object] = {
        "path": str(calibration_path),
        "present": calibration_path.is_file(),
        "record_count": None,
        "count_matches_derived": None,
        "verdict_overlap_rate": None,
    }
    if calibration_path.is_file():
        existing_calibration = load_existing_calibration_dataset(
            calibration_path)
        existing_ids = {
            _cycle_key_from_record(record) or str(record["verdict_id"])
            for record in existing_calibration
        }
        derived_ids = {
            _cycle_key_from_record(record) or str(record["verdict_id"])
            for record in derived_calibration_records
        }
        overlap_rate = None
        if derived_ids:
            overlap_rate = len(existing_ids & derived_ids) / len(derived_ids)
        calibration_payload.update(
            {
                "record_count": len(existing_calibration),
                "count_matches_derived": len(existing_calibration)
                == len(derived_calibration_records),
                "verdict_overlap_rate": _round_or_none(overlap_rate),
            }
        )
        if len(existing_calibration) != len(derived_calibration_records):
            flags.append("phase5_calibration_consistency_gap")
            notes.append(
                "Existing Phase 5 calibration dataset count differs from the derived review calibration count.")
    else:
        flags.append("existing_phase5_calibration_missing")
        notes.append(
            "Existing Phase 5 calibration dataset file is absent; review uses derived calibration records only.")

    summary_payload: dict[str, object] = {
        "path": str(summary_path),
        "present": summary_path.is_file(),
        "matched_count_matches_derived": None,
        "disagreement_count_matches_derived": None,
    }
    if summary_path.is_file():
        existing_summary = load_existing_summary_report(summary_path)
        derived_input_counts = dict(
            derived_summary_report.get("input_counts", {}))
        derived_disagreements = dict(
            derived_summary_report.get("disagreement_stats", {}))
        summary_payload.update(
            {
                "matched_count_matches_derived": (
                    existing_summary.get(
                        "input_counts", {}).get("matched_count")
                    == derived_input_counts.get("matched_count")
                ),
                "disagreement_count_matches_derived": (
                    existing_summary.get("disagreement_stats", {}).get(
                        "disagreement_count")
                    == derived_disagreements.get("disagreement_count")
                ),
            }
        )
        if not bool(summary_payload["matched_count_matches_derived"]):
            flags.append("phase5_summary_consistency_gap")
            notes.append(
                "Existing Phase 5 summary matched_count differs from the derived review summary.")
    else:
        flags.append("existing_phase5_summary_missing")
        notes.append(
            "Existing Phase 5 summary report is absent; review uses derived simulator summary only.")

    return {
        "calibration_dataset": calibration_payload,
        "summary_report": summary_payload,
    }, flags, notes


def _build_fact_sections(
    *,
    entry_records: Sequence[EntryReviewRecord],
    lifecycle_verdict_count: int,
    chamber_join_count: int,
    regime_join_count: int,
    baseline_availability: dict[str, dict[str, object]],
    support: dict[str, dict[str, object]],
    comparison_rows: Sequence[dict[str, object]],
    suppression_rows: Sequence[dict[str, object]],
    disagreement_rows: Sequence[dict[str, object]],
    existing_notes: Sequence[str],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    facts = [
        f"Loaded {len(entry_records)} entry verdict records for review generation.",
        f"Chamber-side artifacts were joined for {chamber_join_count} entry verdicts.",
        f"Regime metadata was joined for {regime_join_count} entry verdicts.",
        f"Lifecycle verdict count observed: {lifecycle_verdict_count}.",
        "This tooling does not emit a promotion verdict.",
    ]
    inferences: list[str] = []
    if chamber_join_count:
        action_diff_total = sum(
            int(row["final_vs_chamber_action_diff_count"])
            for row in comparison_rows
        )
        if action_diff_total == 0:
            inferences.append(
                "No action-level delta was observed between chamber-only reconstruction and final judge on the joined entry surface."
            )
        else:
            inferences.append(
                f"Observed {action_diff_total} action-level chamber-vs-final deltas across joined entry records."
            )
    else:
        inferences.append(
            "Chamber-only vs final-judge comparison remains incomplete because no chamber-side artifact was joined."
        )
    assumptions = [
        "Outcome data correctness is assumed beyond schema validation.",
        "Incumbent strategy baseline requires a separate repo-supported artifact surface that is not present in the current review inputs.",
    ]
    unknowns = [
        "Incumbent-vs-judge value remains unproven without an incumbent baseline artifact.",
    ]
    if support["lifecycle_chamber"]["status"] == "insufficient":
        unknowns.append(
            "Lifecycle verdict usefulness remains unproven because no actionable lifecycle evidence was observed."
        )

    caution_notes = list(existing_notes)
    if not chamber_join_count:
        caution_notes.append(
            "Chamber-only comparison is unavailable without joined chamber or envelope artifacts."
        )
    if not bool(baseline_availability["incumbent_only"]["available_count"]):
        caution_notes.append(
            "Incumbent-only baseline is unavailable and is not inferred by this tooling."
        )
    if suppression_rows:
        total_unknown = sum(int(row["unknown_count"])
                            for row in suppression_rows)
        total_suppress = sum(int(row["suppress_count"])
                             for row in suppression_rows)
        caution_notes.append(
            f"UNKNOWN count={total_unknown}; SUPPRESS count={total_suppress}. Review these separately from disagreement metrics."
        )
    return facts, inferences, assumptions, unknowns, caution_notes, list(existing_notes)


def _render_markdown_table(
    rows: Sequence[dict[str, object]],
    columns: Sequence[str],
) -> list[str]:
    if not rows:
        return ["No rows."]

    def _fmt(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return str(value)

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(_fmt(row.get(column))
                              for column in columns) + " |"
        )
    return lines


def _build_markdown_summary(
    *,
    bundle: dict[str, object],
    comparison_rows: Sequence[dict[str, object]],
    suppression_rows: Sequence[dict[str, object]],
    calibration_rows: Sequence[dict[str, object]],
) -> str:
    facts = list(bundle["facts"])
    inferences = list(bundle["inferences"])
    assumptions = list(bundle["assumptions"])
    unknowns = list(bundle["unknowns"])
    caution_notes = list(bundle["caution_notes"])

    lines = [
        "# Judge Review Summary",
        "",
        "This tooling does not produce a promotion verdict.",
        "",
        "## Inputs Present",
        "",
        f"- Simulator config: {bundle['simulator_config_path']}",
        f"- Entry verdict count: {bundle['input_coverage']['entry_verdict_count']}",
        f"- Matched outcome count: {bundle['input_coverage']['matched_count']}",
        f"- Chamber join count: {bundle['input_coverage']['chamber_joined_count']}",
        f"- Regime join count: {bundle['input_coverage']['regime_joined_count']}",
        "",
        "## FACTS",
        "",
    ]
    lines.extend(f"- {item}" for item in facts)
    lines.extend(["", "## INFERENCES", ""])
    lines.extend(f"- {item}" for item in inferences)
    lines.extend(["", "## ASSUMPTIONS", ""])
    lines.extend(f"- {item}" for item in assumptions)
    lines.extend(["", "## UNKNOWNS", ""])
    lines.extend(f"- {item}" for item in unknowns)
    lines.extend(["", "## Baseline Availability", ""])
    for key, value in dict(bundle["baseline_availability"]).items():
        lines.append(
            f"- {key}: status={value['status']}; available_count={value['available_count']}; note={value['note']}"
        )
    lines.extend(["", "## Key Segmented Comparison Table", ""])
    lines.extend(
        _render_markdown_table(comparison_rows[:8], _COMPARISON_FIELDS[:8])
    )
    lines.extend(["", "## UNKNOWN / SUPPRESS Table", ""])
    lines.extend(
        _render_markdown_table(suppression_rows[:8], _SUPPRESSION_FIELDS[:8])
    )
    lines.extend(["", "## Calibration Slice Table", ""])
    lines.extend(
        _render_markdown_table(calibration_rows[:8], _CALIBRATION_FIELDS[:8])
    )
    lines.extend(["", "## Caution Notes", ""])
    lines.extend(f"- {item}" for item in caution_notes)
    return "\n".join(lines)


def run_review(config: ReviewConfig) -> dict[str, object]:
    """Run offline Phase 6 review generation without widening authority."""

    simulator_config = load_simulator_config(
        config.judge_simulator_config_path)
    simulation_result = run_simulation(simulator_config)
    loaded_verdicts = load_all_verdicts(simulator_config.judge_logs_path)
    loaded_chambers = load_chambers(simulator_config.judge_logs_path)
    loaded_envelopes = load_envelopes(simulator_config.judge_logs_path)

    chamber_by_cycle_key, chamber_by_id = _build_chamber_index(
        loaded_chambers,
        loaded_envelopes,
    )
    envelope_by_cycle_key, envelope_by_id, envelope_by_chamber_id = (
        _build_envelope_indices(loaded_envelopes)
    )
    entry_records = _build_entry_records(
        verdicts=loaded_verdicts,
        chamber_by_cycle_key=chamber_by_cycle_key,
        chamber_by_id=chamber_by_id,
        envelope_by_cycle_key=envelope_by_cycle_key,
        envelope_by_id=envelope_by_id,
        envelope_by_chamber_id=envelope_by_chamber_id,
        simulation_result=simulation_result,
        fee_per_cycle_bps=simulator_config.fee_per_cycle_bps,
        slippage_pct=simulator_config.slippage_pct,
    )
    if not entry_records:
        raise ValueError("No entry review records could be constructed")

    comparison_rows = _build_comparison_rows(
        entry_records, config.segment_dimensions)
    suppression_rows = _build_suppression_rows(
        entry_records, config.segment_dimensions)
    disagreement_rows = _build_disagreement_rows(
        entry_records, config.segment_dimensions)
    calibration_rows = _build_calibration_rows(
        entry_records,
        config.segment_dimensions,
        config.confidence_bucket_edges,
    )

    support, surface_rows = _build_surface_support(
        entry_records=entry_records,
        lifecycle_verdicts=loaded_verdicts,
        chambers=list(chamber_by_cycle_key.values()),
        envelopes=loaded_envelopes,
        simulation_result=simulation_result,
    )
    evidence_support = _build_evidence_class_support(
        entry_records=entry_records,
        support=support,
        comparison_rows=comparison_rows,
        suppression_rows=suppression_rows,
        disagreement_rows=disagreement_rows,
        calibration_rows=calibration_rows,
    )
    baseline_availability = _build_baseline_availability(entry_records)
    existing_phase5_artifacts, artifact_flags, artifact_notes = (
        _build_existing_phase5_artifact_summary(
            simulator_config=simulator_config,
            derived_calibration_records=simulation_result.calibration_records,
            derived_summary_report=simulation_result.summary_report,
        )
    )

    chamber_join_count = sum(
        1 for record in entry_records if record.chamber_available)
    regime_join_count = sum(
        1 for record in entry_records if record.regime is not None)
    facts, inferences, assumptions, unknowns, caution_notes, _ = _build_fact_sections(
        entry_records=entry_records,
        lifecycle_verdict_count=sum(
            1
            for loaded in loaded_verdicts
            if loaded.verdict.verdict_scope == "LIFECYCLE"
        ),
        chamber_join_count=chamber_join_count,
        regime_join_count=regime_join_count,
        baseline_availability=baseline_availability,
        support=support,
        comparison_rows=comparison_rows,
        suppression_rows=suppression_rows,
        disagreement_rows=disagreement_rows,
        existing_notes=artifact_notes,
    )

    flags = list(dict.fromkeys(
        artifact_flags
        + (["chamber_comparison_unavailable"]
           if chamber_join_count == 0 else [])
        + (["partial_chamber_join_coverage"] if 0 <
           chamber_join_count < len(entry_records) else [])
        + (["regime_segmentation_unavailable"]
           if regime_join_count == 0 else [])
        + (["lifecycle_surface_insufficient"] if support["lifecycle_chamber"]
           ["status"] == "insufficient" else [])
        + (["incumbent_baseline_unavailable"]
           if baseline_availability["incumbent_only"]["status"] == "unavailable" else [])
        + (["no_observed_final_judge_action_delta"]
           if chamber_join_count > 0
           and sum(int(row["final_vs_chamber_action_diff_count"]) for row in comparison_rows) == 0
           else [])
    ))

    output_dir = Path(config.output_dir)
    artifact_paths = {
        "review_bundle_json": str(output_dir / "review_bundle.json"),
        "review_summary_md": str(output_dir / "review_summary.md"),
        "comparison_segments_csv": str(output_dir / "comparison_by_segment.csv"),
        "suppression_unknown_csv": str(output_dir / "suppression_unknown_by_segment.csv"),
        "disagreement_buckets_csv": str(output_dir / "disagreement_buckets.csv"),
        "calibration_slices_csv": str(output_dir / "calibration_slices.csv"),
        "surface_support_csv": str(output_dir / "surface_support.csv"),
    }

    bundle: dict[str, object] = {
        "schema_version": "1",
        "tooling_scope": "phase6_validation_artifact_tooling",
        "generated_at_ms": int(time.time() * 1000),
        "no_automatic_promotion_verdict": True,
        "simulator_config_path": config.judge_simulator_config_path,
        "output_dir": str(output_dir),
        "input_coverage": _build_input_coverage(
            simulator_config_path=config.judge_simulator_config_path,
            simulator_config_path_resolved=str(
                Path(config.judge_simulator_config_path).resolve()
            ),
            judge_logs_path=simulator_config.judge_logs_path,
            outcome_data_path=simulator_config.outcome_data_path,
            simulation_result=simulation_result,
            verdicts=loaded_verdicts,
            chambers=list(chamber_by_cycle_key.values()),
            envelopes=loaded_envelopes,
            entry_records=entry_records,
            existing_calibration_present=bool(
                existing_phase5_artifacts["calibration_dataset"]["present"]
            ),
            existing_summary_present=bool(
                existing_phase5_artifacts["summary_report"]["present"]
            ),
        ),
        "baseline_availability": baseline_availability,
        "segmentation_coverage": _build_segmentation_coverage(
            entry_records,
            config.segment_dimensions,
        ),
        "review_surface_support": support,
        "evidence_class_support": evidence_support,
        "verdict_class_counts": {
            "ENTRY": _count_entry_verdicts(entry_records),
            "LIFECYCLE": _count_lifecycle_verdicts(loaded_verdicts),
        },
        "chamber_class_counts": _count_chamber_classes(
            list(chamber_by_cycle_key.values())
        ),
        "suppression_unknown_accounting": {
            "unknown_count": sum(
                1 for record in entry_records if record.final_action == "UNKNOWN"
            ),
            "suppress_count": sum(
                1 for record in entry_records if record.final_action == "SUPPRESS"
            ),
            "unknown_total_opportunity_cost": _round_or_none(
                sum(
                    record.suppression_unknown_opportunity_cost or 0.0
                    for record in entry_records
                    if record.final_action == "UNKNOWN"
                )
            ),
            "suppress_total_opportunity_cost": _round_or_none(
                sum(
                    record.suppression_unknown_opportunity_cost or 0.0
                    for record in entry_records
                    if record.final_action == "SUPPRESS"
                )
            ),
        },
        "disagreement_metrics": {
            "count": len(simulation_result.disagreements),
            "rate": _round_or_none(
                len(simulation_result.disagreements) /
                simulation_result.matched_count
                if simulation_result.matched_count
                else None
            ),
            "total_cost_of_disagreement": _round_or_none(
                sum(
                    float(record.get("cost_of_disagreement", 0.0))
                    for record in simulation_result.disagreements
                )
            ),
            "table_path": artifact_paths["disagreement_buckets_csv"],
        },
        "calibration_support": {
            "record_count": len(simulation_result.calibration_records),
            "confidence_bucket_edges": list(config.confidence_bucket_edges),
            "table_path": artifact_paths["calibration_slices_csv"],
        },
        "existing_phase5_artifacts": existing_phase5_artifacts,
        "not_enough_evidence_flags": flags,
        "caution_notes": caution_notes,
        "facts": facts,
        "inferences": inferences,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "artifact_paths": artifact_paths,
    }
    markdown_summary = _build_markdown_summary(
        bundle=bundle,
        comparison_rows=comparison_rows,
        suppression_rows=suppression_rows,
        calibration_rows=calibration_rows,
    )
    return {
        "bundle": bundle,
        "summary_markdown": markdown_summary,
        "comparison_rows": comparison_rows,
        "suppression_rows": suppression_rows,
        "disagreement_rows": disagreement_rows,
        "calibration_rows": calibration_rows,
        "surface_rows": surface_rows,
        "fieldnames": {
            "comparison_rows": _COMPARISON_FIELDS,
            "suppression_rows": _SUPPRESSION_FIELDS,
            "disagreement_rows": _DISAGREEMENT_FIELDS,
            "calibration_rows": _CALIBRATION_FIELDS,
            "surface_rows": _SURFACE_FIELDS,
        },
    }
