"""Phase 5 Package 5A simulator engine core.

This module is intentionally offline-only. It reads verdict JSONL artifacts and
external outcome data, correlates them deterministically by cycle identity, and
computes a minimal accuracy summary.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field as dataclass_field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Sequence

from jsonschema import Draft7Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.reference.domains.alpha_search.judge.contracts import (
    EntryVerdict,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
)

from .calibration_dataset_writer import build_calibration_records
from .config_models import SimulatorConfig
from .summary_report_writer import build_summary_report
from .disagreement_analyzer import (
    build_disagreement_record,
    compute_disagreement,
    determine_optimal_action,
)
from .expert_accuracy_reporter import (
    aggregate_expert_accuracy,
    compute_expert_accuracy_for_cycle,
)
from .fee_slippage_calculator import (
    compute_fee_cost_bps,
    compute_net_return,
    compute_slippage_cost_pct,
)

LOG = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / \
    "schemas" / "outcome_input_v1.json"
_SUPPORTED_DIRECTIONAL_VERDICTS = (
    "OPEN_LONG",
    "OPEN_SHORT",
    "NO_ENTRY",
    "SUPPRESS",
)


@dataclass(frozen=True)
class CorrelationKey:
    strategy_id: str
    symbol: str
    tf_sec: int
    bar_close_ts: int


@dataclass(frozen=True)
class VerdictRecord:
    verdict_id: str
    correlation_key: CorrelationKey
    entry_verdict: EntryVerdict
    confidence: float
    dissent_noted: bool = False


@dataclass(frozen=True)
class OutcomeRecord:
    correlation_key: CorrelationKey
    matched_trade: bool
    entry_price: float | None
    exit_price: float | None
    exit_ts_ms: int | None


@dataclass(frozen=True)
class _EnvelopeExpertContext:
    correlation_key: CorrelationKey
    expert_outputs: tuple[ExpertOutput, ...]


@dataclass(frozen=True)
class CorrelatedVerdictOutcome:
    verdict: VerdictRecord
    outcome: OutcomeRecord | None
    side: Literal["LONG", "SHORT"] | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    raw_return: float | None = None
    fee_cost: float | None = None
    slippage_cost: float | None = None
    net_return: float | None = None


@dataclass(frozen=True)
class AccuracyBucket:
    evaluated_count: int
    correct_count: int
    incorrect_count: int
    accuracy: float | None


@dataclass(frozen=True)
class BasicAccuracySummary:
    evaluated_count: int
    correct_count: int
    incorrect_count: int
    skipped_count: int
    by_verdict: dict[str, AccuracyBucket]


@dataclass(frozen=True)
class SimulationResult:
    total_verdict_records_loaded: int
    total_outcome_records_loaded: int
    matched_count: int
    unmatched_count: int
    accuracy_summary: BasicAccuracySummary
    correlations: tuple[CorrelatedVerdictOutcome, ...]
    disagreements: tuple[dict[str, object], ...] = ()
    expert_accuracy_records: tuple[dict[str, object], ...] = ()
    expert_accuracy_summary: dict[str, object] = dataclass_field(
        default_factory=dict
    )
    calibration_records: tuple[dict[str, object], ...] = ()
    summary_report: dict[str, object] = dataclass_field(
        default_factory=dict
    )


class _OutcomeEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    bar_close_ts: int = Field(..., gt=0)
    matched_trade: bool
    entry_price: float | None = Field(default=None, gt=0.0)
    exit_price: float | None = Field(default=None, gt=0.0)
    exit_ts_ms: int | None = Field(default=None, gt=0)

    @field_validator("strategy_id", "symbol")
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity fields must not be blank")
        return value

    @model_validator(mode="after")
    def validate_trade_payload(self) -> "_OutcomeEntryModel":
        if self.matched_trade:
            missing_fields = []
            if self.entry_price is None:
                missing_fields.append("entry_price")
            if self.exit_price is None:
                missing_fields.append("exit_price")
            if self.exit_ts_ms is None:
                missing_fields.append("exit_ts_ms")
            if missing_fields:
                raise ValueError(
                    "matched_trade=true requires " + ", ".join(missing_fields)
                )
        return self


class _OutcomeInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"]
    outcomes: tuple[_OutcomeEntryModel, ...] = ()


@lru_cache(maxsize=1)
def _load_outcome_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft7Validator.check_schema(schema)
    return schema


def _format_jsonschema_error(error: Any) -> str:
    if error.path:
        segments = []
        for segment in error.path:
            if isinstance(segment, int):
                segments.append(f"[{segment}]")
            else:
                segments.append(f".{segment}")
        location = "$" + "".join(segments)
    else:
        location = "$"
    return f"{location}: {error.message}"


def _format_key(key: CorrelationKey) -> str:
    return (
        f"strategy_id={key.strategy_id}, symbol={key.symbol}, "
        f"tf_sec={key.tf_sec}, bar_close_ts={key.bar_close_ts}"
    )


def _iter_verdict_files(judge_logs_path: str | Path) -> list[Path]:
    path = Path(judge_logs_path)
    if not path.exists():
        raise FileNotFoundError(f"judge logs path does not exist: {path}")

    if path.is_file():
        return [path]

    verdict_files = sorted(
        candidate
        for candidate in path.glob("verdict_*.jsonl")
        if candidate.is_file()
    )
    if not verdict_files:
        LOG.warning("No verdict JSONL files found under %s", path)
    return verdict_files


def _normalize_verdict(verdict: JudgeVerdict) -> VerdictRecord:
    if verdict.entry_verdict is None:
        raise ValueError(
            "entry_verdict is required for Package 5A correlation")
    return VerdictRecord(
        verdict_id=verdict.verdict_id,
        correlation_key=CorrelationKey(
            strategy_id=verdict.strategy_id,
            symbol=verdict.symbol,
            tf_sec=verdict.tf_sec,
            bar_close_ts=verdict.ts_ms,
        ),
        entry_verdict=verdict.entry_verdict,
        confidence=verdict.confidence,
        dissent_noted=verdict.dissent_noted,
    )


def load_verdict_records(judge_logs_path: str | Path) -> list[VerdictRecord]:
    """Load entry verdict records from one JSONL file or a verdict directory."""

    verdict_records: list[VerdictRecord] = []
    for file_path in _iter_verdict_files(judge_logs_path):
        with open(file_path, "r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    LOG.warning(
                        "Skipping malformed verdict JSONL line %s:%s: %s",
                        file_path,
                        line_number,
                        exc,
                    )
                    continue

                try:
                    verdict = JudgeVerdict.model_validate(payload)
                except Exception as exc:
                    LOG.warning(
                        "Skipping invalid verdict payload %s:%s: %s",
                        file_path,
                        line_number,
                        exc,
                    )
                    continue

                if verdict.verdict_scope != "ENTRY" or verdict.entry_verdict is None:
                    LOG.warning(
                        "Skipping non-entry verdict %s:%s (verdict_id=%s, scope=%s)",
                        file_path,
                        line_number,
                        verdict.verdict_id,
                        verdict.verdict_scope,
                    )
                    continue

                verdict_records.append(_normalize_verdict(verdict))

    return verdict_records


def load_outcome_data(outcome_data_path: str | Path) -> list[OutcomeRecord]:
    """Load and validate outcome data from the Package 5A schema."""

    path = Path(outcome_data_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"outcome data path does not exist: {path}")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Outcome data file is not valid JSON: {exc}") from exc

    validator = Draft7Validator(_load_outcome_schema())
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        formatted_errors = "; ".join(
            _format_jsonschema_error(error) for error in errors[:5]
        )
        raise ValueError(
            f"Outcome data failed schema validation: {formatted_errors}"
        )

    parsed = _OutcomeInputModel.model_validate(payload)
    return [
        OutcomeRecord(
            correlation_key=CorrelationKey(
                strategy_id=outcome.strategy_id,
                symbol=outcome.symbol,
                tf_sec=outcome.tf_sec,
                bar_close_ts=outcome.bar_close_ts,
            ),
            matched_trade=outcome.matched_trade,
            entry_price=outcome.entry_price,
            exit_price=outcome.exit_price,
            exit_ts_ms=outcome.exit_ts_ms,
        )
        for outcome in parsed.outcomes
    ]


def _iter_optional_shadow_files(
    judge_logs_path: str | Path,
    prefix: str,
) -> list[Path]:
    path = Path(judge_logs_path)
    if not path.exists():
        return []

    if path.is_file() and path.name.startswith(f"{prefix}_"):
        return [path]

    search_dir = path if path.is_dir() else path.parent
    return sorted(
        candidate
        for candidate in search_dir.glob(f"{prefix}_*.jsonl")
        if candidate.is_file()
    )


def _load_envelope_contexts(
    judge_logs_path: str | Path,
) -> list[_EnvelopeExpertContext]:
    contexts: list[_EnvelopeExpertContext] = []
    for file_path in _iter_optional_shadow_files(judge_logs_path, "envelope"):
        with open(file_path, "r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    LOG.warning(
                        "Skipping malformed envelope JSONL line %s:%s: %s",
                        file_path,
                        line_number,
                        exc,
                    )
                    continue

                try:
                    envelope = JudgeEvidenceEnvelope.model_validate(payload)
                except Exception as exc:
                    LOG.warning(
                        "Skipping invalid envelope payload %s:%s: %s",
                        file_path,
                        line_number,
                        exc,
                    )
                    continue

                if envelope.verdict_scope != "ENTRY":
                    continue

                contexts.append(
                    _EnvelopeExpertContext(
                        correlation_key=CorrelationKey(
                            strategy_id=envelope.strategy_id,
                            symbol=envelope.symbol,
                            tf_sec=envelope.tf_sec,
                            bar_close_ts=envelope.ts_ms,
                        ),
                        expert_outputs=tuple(
                            envelope.chamber_aggregate.expert_outputs),
                    )
                )
    return contexts


def _build_envelope_index(
    contexts: Sequence[_EnvelopeExpertContext],
) -> dict[CorrelationKey, _EnvelopeExpertContext]:
    context_index: dict[CorrelationKey, _EnvelopeExpertContext] = {}
    for context in contexts:
        if context.correlation_key in context_index:
            LOG.warning(
                "Duplicate envelope correlation key encountered; keeping first record for %s",
                _format_key(context.correlation_key),
            )
            continue
        context_index[context.correlation_key] = context
    return context_index


def _build_outcome_index(
    outcomes: Sequence[OutcomeRecord],
) -> dict[CorrelationKey, OutcomeRecord]:
    outcome_index: dict[CorrelationKey, OutcomeRecord] = {}
    for outcome in outcomes:
        if outcome.correlation_key in outcome_index:
            LOG.warning(
                "Duplicate outcome correlation key encountered; keeping first record for %s",
                _format_key(outcome.correlation_key),
            )
            continue
        outcome_index[outcome.correlation_key] = outcome
    return outcome_index


def correlate_verdicts_to_outcomes(
    verdicts: Sequence[VerdictRecord],
    outcomes: Sequence[OutcomeRecord],
) -> tuple[CorrelatedVerdictOutcome, ...]:
    """Correlate verdicts to outcomes by exact same-cycle identity."""

    outcome_index = _build_outcome_index(outcomes)
    correlations: list[CorrelatedVerdictOutcome] = []
    seen_verdict_keys: set[CorrelationKey] = set()

    for verdict in verdicts:
        if verdict.correlation_key in seen_verdict_keys:
            LOG.warning(
                "Duplicate verdict correlation key encountered; evaluating independently for %s",
                _format_key(verdict.correlation_key),
            )
        else:
            seen_verdict_keys.add(verdict.correlation_key)

        correlations.append(
            CorrelatedVerdictOutcome(
                verdict=verdict,
                outcome=outcome_index.get(verdict.correlation_key),
            )
        )

    return tuple(correlations)


def _map_entry_verdict_to_side(
    entry_verdict: EntryVerdict,
) -> Literal["LONG", "SHORT"] | None:
    if entry_verdict == "OPEN_LONG":
        return "LONG"
    if entry_verdict == "OPEN_SHORT":
        return "SHORT"
    return None


def _compute_raw_return(
    entry_price: float,
    exit_price: float,
    side: Literal["LONG", "SHORT"],
) -> float:
    if side == "LONG":
        return (exit_price - entry_price) / entry_price
    return (entry_price - exit_price) / entry_price


def enrich_correlations_with_economics(
    correlations: Sequence[CorrelatedVerdictOutcome],
    config: SimulatorConfig,
) -> tuple[CorrelatedVerdictOutcome, ...]:
    """Add minimal Package 5B economic fields to actionable matched records."""

    enriched: list[CorrelatedVerdictOutcome] = []
    fee_cost = compute_fee_cost_bps(config.fee_per_cycle_bps)
    slippage_cost = compute_slippage_cost_pct(config.slippage_pct)

    for correlation in correlations:
        side = _map_entry_verdict_to_side(correlation.verdict.entry_verdict)
        outcome = correlation.outcome

        if (
            side is None
            or outcome is None
            or not outcome.matched_trade
            or outcome.entry_price is None
            or outcome.exit_price is None
        ):
            enriched.append(correlation)
            continue

        raw_return = _compute_raw_return(
            outcome.entry_price,
            outcome.exit_price,
            side,
        )
        net_return = compute_net_return(
            outcome.entry_price,
            outcome.exit_price,
            side,
            config.fee_per_cycle_bps,
            config.slippage_pct,
        )
        enriched.append(
            CorrelatedVerdictOutcome(
                verdict=correlation.verdict,
                outcome=outcome,
                side=side,
                entry_price=outcome.entry_price,
                exit_price=outcome.exit_price,
                raw_return=raw_return,
                fee_cost=fee_cost,
                slippage_cost=slippage_cost,
                net_return=net_return,
            )
        )

    return tuple(enriched)


def build_disagreement_records(
    correlations: Sequence[CorrelatedVerdictOutcome],
    config: SimulatorConfig,
) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for correlation in correlations:
        outcome = correlation.outcome
        if outcome is None:
            continue

        disagreement = compute_disagreement(
            verdict_action=correlation.verdict.entry_verdict,
            matched_trade=outcome.matched_trade,
            entry_price=outcome.entry_price,
            exit_price=outcome.exit_price,
            fee_per_cycle_bps=config.fee_per_cycle_bps,
            slippage_pct=config.slippage_pct,
            verdict_net_return=correlation.net_return,
        )
        if disagreement is None:
            continue

        records.append(
            build_disagreement_record(
                verdict_id=correlation.verdict.verdict_id,
                strategy_id=correlation.verdict.correlation_key.strategy_id,
                symbol=correlation.verdict.correlation_key.symbol,
                tf_sec=correlation.verdict.correlation_key.tf_sec,
                bar_close_ts=correlation.verdict.correlation_key.bar_close_ts,
                verdict_action=correlation.verdict.entry_verdict,
                optimal_action=str(disagreement["optimal_action"]),
                cost_of_disagreement=float(
                    disagreement["cost_of_disagreement"]),
                confidence=correlation.verdict.confidence,
                dissent_noted=correlation.verdict.dissent_noted,
            )
        )
    return tuple(records)


def build_expert_accuracy_records(
    correlations: Sequence[CorrelatedVerdictOutcome],
    judge_logs_path: str | Path,
    config: SimulatorConfig,
) -> tuple[dict[str, object], ...]:
    envelope_index = _build_envelope_index(
        _load_envelope_contexts(judge_logs_path))
    records: list[dict[str, object]] = []

    for correlation in correlations:
        outcome = correlation.outcome
        if outcome is None:
            continue

        context = envelope_index.get(correlation.verdict.correlation_key)
        if context is None:
            continue

        optimal_action = determine_optimal_action(
            matched_trade=outcome.matched_trade,
            entry_price=outcome.entry_price,
            exit_price=outcome.exit_price,
            fee_per_cycle_bps=config.fee_per_cycle_bps,
            slippage_pct=config.slippage_pct,
        )
        records.extend(
            compute_expert_accuracy_for_cycle(
                strategy_id=correlation.verdict.correlation_key.strategy_id,
                symbol=correlation.verdict.correlation_key.symbol,
                tf_sec=correlation.verdict.correlation_key.tf_sec,
                bar_close_ts=correlation.verdict.correlation_key.bar_close_ts,
                expert_outputs=context.expert_outputs,
                optimal_action=optimal_action,
            )
        )

    return tuple(records)


def _evaluate_directional_accuracy(
    verdict: EntryVerdict,
    outcome: OutcomeRecord,
) -> bool | None:
    if verdict == "OPEN_LONG":
        if not outcome.matched_trade:
            return False
        return bool(
            outcome.entry_price is not None
            and outcome.exit_price is not None
            and outcome.exit_price > outcome.entry_price
        )
    if verdict == "OPEN_SHORT":
        if not outcome.matched_trade:
            return False
        return bool(
            outcome.entry_price is not None
            and outcome.exit_price is not None
            and outcome.exit_price < outcome.entry_price
        )
    if verdict in {"NO_ENTRY", "SUPPRESS"}:
        return not outcome.matched_trade
    return None


def _make_accuracy_bucket(correct_count: int, incorrect_count: int) -> AccuracyBucket:
    evaluated_count = correct_count + incorrect_count
    accuracy = None
    if evaluated_count:
        accuracy = correct_count / evaluated_count
    return AccuracyBucket(
        evaluated_count=evaluated_count,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        accuracy=accuracy,
    )


def compute_basic_accuracy(
    correlations: Sequence[CorrelatedVerdictOutcome],
) -> BasicAccuracySummary:
    """Compute the minimal directional accuracy summary for Package 5A."""

    verdict_totals = {
        verdict: {"correct": 0, "incorrect": 0}
        for verdict in _SUPPORTED_DIRECTIONAL_VERDICTS
    }
    skipped_count = 0

    for correlation in correlations:
        if correlation.outcome is None:
            continue

        is_correct = _evaluate_directional_accuracy(
            correlation.verdict.entry_verdict,
            correlation.outcome,
        )
        if is_correct is None:
            skipped_count += 1
            continue

        bucket = verdict_totals[correlation.verdict.entry_verdict]
        if is_correct:
            bucket["correct"] += 1
        else:
            bucket["incorrect"] += 1

    by_verdict = {
        verdict: _make_accuracy_bucket(
            counts["correct"],
            counts["incorrect"],
        )
        for verdict, counts in verdict_totals.items()
    }
    correct_count = sum(bucket.correct_count for bucket in by_verdict.values())
    incorrect_count = sum(
        bucket.incorrect_count for bucket in by_verdict.values())

    return BasicAccuracySummary(
        evaluated_count=correct_count + incorrect_count,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        skipped_count=skipped_count,
        by_verdict=by_verdict,
    )


def run_simulation(config: SimulatorConfig) -> SimulationResult:
    """Run the offline Package 5A simulator foundation."""

    verdicts = load_verdict_records(config.judge_logs_path)
    outcomes = load_outcome_data(config.outcome_data_path)
    correlations = enrich_correlations_with_economics(
        correlate_verdicts_to_outcomes(verdicts, outcomes),
        config,
    )

    matched_count = sum(
        1 for correlation in correlations if correlation.outcome is not None)
    unmatched_count = len(correlations) - matched_count
    disagreements = build_disagreement_records(correlations, config)
    expert_accuracy_records = build_expert_accuracy_records(
        correlations,
        config.judge_logs_path,
        config,
    )
    calibration_records = tuple(
        build_calibration_records(
            correlations=correlations,
            disagreements=disagreements,
            config=config,
        )
    )

    expert_accuracy_summary = aggregate_expert_accuracy(
        expert_accuracy_records)

    partial_result = SimulationResult(
        total_verdict_records_loaded=len(verdicts),
        total_outcome_records_loaded=len(outcomes),
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        accuracy_summary=compute_basic_accuracy(correlations),
        correlations=correlations,
        disagreements=disagreements,
        expert_accuracy_records=expert_accuracy_records,
        expert_accuracy_summary=expert_accuracy_summary,
        calibration_records=calibration_records,
    )

    deterministic_ts = max(
        (c.verdict.correlation_key.bar_close_ts for c in correlations),
        default=0,
    )
    summary_report = build_summary_report(
        partial_result, generated_at_ms=deterministic_ts,
    )

    return SimulationResult(
        total_verdict_records_loaded=partial_result.total_verdict_records_loaded,
        total_outcome_records_loaded=partial_result.total_outcome_records_loaded,
        matched_count=partial_result.matched_count,
        unmatched_count=partial_result.unmatched_count,
        accuracy_summary=partial_result.accuracy_summary,
        correlations=partial_result.correlations,
        disagreements=partial_result.disagreements,
        expert_accuracy_records=partial_result.expert_accuracy_records,
        expert_accuracy_summary=partial_result.expert_accuracy_summary,
        calibration_records=partial_result.calibration_records,
        summary_report=summary_report,
    )
