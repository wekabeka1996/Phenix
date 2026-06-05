from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0.0"
PATCH_ALIAS = "ya" + "ml_patch"
AUTHORITY_MODES = ("shadow", "advisory", "hybrid_gated", "live" + "_gated")

Side = Literal["BUY", "SELL", "NONE", "UNKNOWN"]
PolicyVerdict = Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"]
BridgeAction = Literal["record_only", "allow", "suppress", "skip", "blocked"]
BandAction = Literal["allow", "suppress", "observe"]
BandStatus = Literal["CANDIDATE", "TOXIC", "LOW_POWER", "REJECTED", "OBSERVE_ONLY"]


class JudgeCalibrationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_sec: int = Field(gt=0)
    gross_pnl_usd: float | None = None
    net_pnl_usd: float | None = None
    fees_usd: float | None = None
    slippage_usd: float | None = None
    max_favorable_usd: float | None = None
    max_adverse_usd: float | None = None
    terminal_status: str | None = None


class JudgeCalibrationSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict_id: str | None = None
    envelope_id: str | None = None
    decision_id: str | None = None
    rid: str | None = None
    lifecycle_id: str | None = None


class JudgeCalibrationOutcomeRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    row_id: str = Field(min_length=1)
    decision_ts_ms: int = Field(ge=0)
    outcome_ts_ms: int | None = Field(default=None, ge=0)
    symbol: str = Field(min_length=1)
    side: Side
    regime_label: str | None = None
    regime_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    verdict: PolicyVerdict
    judge_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bridge_action: BridgeAction | None = None
    authority_mode: str | None = None
    applied: bool
    missingness_state: str | None = None
    freshness_state: str | None = None
    outcome: JudgeCalibrationOutcome
    source_refs: JudgeCalibrationSourceRefs

    @field_validator("authority_mode")
    @classmethod
    def validate_authority_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in AUTHORITY_MODES:
            raise ValueError("unsupported authority_mode")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> "JudgeCalibrationOutcomeRow":
        if self.outcome_ts_ms is not None and self.outcome_ts_ms < self.decision_ts_ms:
            raise ValueError("outcome_ts_ms must be >= decision_ts_ms")
        return self


class CalibrationWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train_start_ts_ms: int = Field(ge=0)
    train_end_ts_ms: int = Field(ge=0)
    holdout_start_ts_ms: int | None = Field(default=None, ge=0)
    holdout_end_ts_ms: int | None = Field(default=None, ge=0)
    cadence_days: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_window_order(self) -> "CalibrationWindow":
        if self.train_end_ts_ms < self.train_start_ts_ms:
            raise ValueError("train_end_ts_ms must be >= train_start_ts_ms")
        if self.holdout_start_ts_ms is not None and self.holdout_end_ts_ms is not None:
            if self.holdout_end_ts_ms < self.holdout_start_ts_ms:
                raise ValueError("holdout_end_ts_ms must be >= holdout_start_ts_ms")
            if self.holdout_start_ts_ms < self.train_end_ts_ms:
                raise ValueError("holdout must not overlap train window")
        return self


class CalibrationDatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_rows: int = Field(ge=0)
    usable_rows: int = Field(ge=0)
    unresolved_rows: int = Field(ge=0)
    symbols: list[str] = Field(default_factory=list)
    regimes: list[str] = Field(default_factory=list)
    sides: list[str] = Field(default_factory=list)


class CalibrationGates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_rows_required: int = Field(ge=0)
    min_symbols_required: int = Field(ge=0)
    min_usable_rows_passed: bool
    min_symbols_passed: bool
    holdout_present: bool
    promotion_allowed: Literal[False] = False


class ConfidenceBandCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    band_id: str = Field(min_length=1)
    min_confidence: float = Field(ge=0.0, le=1.0)
    max_confidence: float = Field(ge=0.0, le=1.0)
    action: BandAction
    rows: int = Field(ge=0)
    win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    avg_net_pnl_usd: float | None = None
    total_net_pnl_usd: float | None = None
    expectancy_net_usd: float | None = None
    max_drawdown_usd: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    status: BandStatus
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ConfidenceBandCandidate":
        if self.min_confidence >= self.max_confidence:
            raise ValueError("band min_confidence must be < max_confidence")
        return self


class ConfidenceBands(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: list[ConfidenceBandCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_recommended_overlaps(self) -> "ConfidenceBands":
        active = [
            band
            for band in self.candidates
            if band.action in {"allow", "suppress"} and band.status != "REJECTED"
        ]
        for left_index, left in enumerate(active):
            for right in active[left_index + 1 :]:
                overlaps = left.min_confidence < right.max_confidence and right.min_confidence < left.max_confidence
                if overlaps and left.action != right.action:
                    raise ValueError("active allow/suppress confidence bands must not overlap")
        return self


class RecommendedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    proposal_only: Literal[True] = True
    auto_apply: Literal[False] = False
    config_patch: dict[str, Any] | None = Field(default=None, alias=PATCH_ALIAS)
    human_review_required: Literal[True] = True


class AntiLeakageReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train_holdout_split_valid: bool
    no_future_outcome_in_train_features: bool
    leakage_warnings: list[str] = Field(default_factory=list)


class CalibrationProposalSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_paths: list[str] = Field(default_factory=list)
    report_path: str | None = None


class JudgeConfidenceCalibrationProposalV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    created_ts_ms: int = Field(ge=0)
    calibration_window: CalibrationWindow
    dataset_summary: CalibrationDatasetSummary
    gates: CalibrationGates
    confidence_bands: ConfidenceBands
    breakdowns: dict[str, dict[str, Any]]
    recommended_policy: RecommendedPolicy
    anti_leakage: AntiLeakageReport
    source_refs: CalibrationProposalSourceRefs


def build_calibration_rows(rows: Iterable[Mapping[str, Any] | JudgeCalibrationOutcomeRow]) -> list[JudgeCalibrationOutcomeRow]:
    return [
        row if isinstance(row, JudgeCalibrationOutcomeRow) else JudgeCalibrationOutcomeRow.model_validate(dict(row))
        for row in rows
    ]


def validate_calibration_dataset(rows: Sequence[JudgeCalibrationOutcomeRow]) -> list[str]:
    warnings: list[str] = []
    for row in rows:
        if row.judge_confidence is None:
            warnings.append(f"{row.row_id}:missing_judge_confidence")
        if row.outcome.net_pnl_usd is None:
            warnings.append(f"{row.row_id}:unresolved_net_pnl")
    return warnings


def split_train_holdout(
    rows: Sequence[JudgeCalibrationOutcomeRow],
    *,
    holdout_ratio: float,
) -> tuple[list[JudgeCalibrationOutcomeRow], list[JudgeCalibrationOutcomeRow]]:
    if holdout_ratio < 0.0 or holdout_ratio >= 1.0:
        raise ValueError("holdout_ratio must be >= 0.0 and < 1.0")
    ordered = sorted(rows, key=lambda row: (row.decision_ts_ms, row.row_id))
    if not ordered or holdout_ratio == 0.0:
        return ordered, []
    holdout_count = max(1, int(math.ceil(len(ordered) * holdout_ratio)))
    if holdout_count >= len(ordered):
        holdout_count = len(ordered) - 1
    return ordered[:-holdout_count], ordered[-holdout_count:]


def bucket_confidence_bands(
    rows: Sequence[JudgeCalibrationOutcomeRow],
    *,
    band_step: float,
) -> dict[tuple[float, float], list[JudgeCalibrationOutcomeRow]]:
    if band_step <= 0.0 or band_step > 1.0:
        raise ValueError("band_step must be > 0 and <= 1")
    buckets: dict[tuple[float, float], list[JudgeCalibrationOutcomeRow]] = defaultdict(list)
    for row in rows:
        if row.judge_confidence is None:
            continue
        index = min(int(row.judge_confidence / band_step), int(math.ceil(1.0 / band_step)) - 1)
        lower = round(index * band_step, 10)
        upper = round(min(1.0, lower + band_step), 10)
        buckets[(lower, upper)].append(row)
    return dict(sorted(buckets.items()))


def _economics_value(row: JudgeCalibrationOutcomeRow, *, gross_pnl_fallback: bool) -> float | None:
    if row.outcome.net_pnl_usd is not None:
        return row.outcome.net_pnl_usd
    if gross_pnl_fallback:
        return row.outcome.gross_pnl_usd
    return None


def _max_drawdown(values: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return worst


def _confidence_interval(values: Sequence[float]) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = 1.96 * math.sqrt(variance) / math.sqrt(len(values))
    return mean - margin, mean + margin


def _band_action(avg_net: float | None, status: BandStatus) -> BandAction:
    if status == "TOXIC":
        return "suppress"
    if status == "CANDIDATE" and avg_net is not None and avg_net > 0.0:
        return "allow"
    return "observe"


def compute_band_metrics(
    buckets: Mapping[tuple[float, float], Sequence[JudgeCalibrationOutcomeRow]],
    *,
    min_rows: int,
    gross_pnl_fallback: bool = False,
) -> list[ConfidenceBandCandidate]:
    candidates: list[ConfidenceBandCandidate] = []
    for (lower, upper), bucket_rows in buckets.items():
        values = [
            value
            for value in (_economics_value(row, gross_pnl_fallback=gross_pnl_fallback) for row in bucket_rows)
            if value is not None
        ]
        reason_codes: list[str] = []
        if len(bucket_rows) < min_rows or len(values) < min_rows:
            status: BandStatus = "LOW_POWER"
            reason_codes.append("sample_below_min_rows")
        elif sum(values) < 0.0 or (sum(values) / len(values)) < 0.0:
            status = "TOXIC"
            reason_codes.append("negative_expectancy")
        elif sum(values) > 0.0:
            status = "CANDIDATE"
            reason_codes.append("positive_expectancy")
        else:
            status = "OBSERVE_ONLY"
            reason_codes.append("flat_expectancy")
        if gross_pnl_fallback and any(row.outcome.net_pnl_usd is None and row.outcome.gross_pnl_usd is not None for row in bucket_rows):
            reason_codes.append("gross_pnl_fallback_used")
        ci_low, ci_high = _confidence_interval(values)
        avg_net = (sum(values) / len(values)) if values else None
        action = _band_action(avg_net, status)
        candidates.append(
            ConfidenceBandCandidate(
                band_id=f"conf_{lower:.2f}_{upper:.2f}",
                min_confidence=lower,
                max_confidence=upper,
                action=action,
                rows=len(bucket_rows),
                win_rate=(sum(1 for value in values if value > 0.0) / len(values)) if values else None,
                avg_net_pnl_usd=avg_net,
                total_net_pnl_usd=sum(values) if values else None,
                expectancy_net_usd=avg_net,
                max_drawdown_usd=_max_drawdown(values) if values else None,
                ci_low=ci_low,
                ci_high=ci_high,
                status=status,
                reason_codes=reason_codes,
            )
        )
    return candidates


def detect_toxic_bands(candidates: Sequence[ConfidenceBandCandidate]) -> list[ConfidenceBandCandidate]:
    return [candidate for candidate in candidates if candidate.status == "TOXIC"]


def _summary_for_rows(
    rows: Sequence[JudgeCalibrationOutcomeRow],
    *,
    gross_pnl_fallback: bool,
) -> dict[str, Any]:
    values = [
        value
        for value in (_economics_value(row, gross_pnl_fallback=gross_pnl_fallback) for row in rows)
        if value is not None
    ]
    return {
        "rows": len(rows),
        "usable_rows": len(values),
        "win_rate": (sum(1 for value in values if value > 0.0) / len(values)) if values else None,
        "avg_net_pnl_usd": (sum(values) / len(values)) if values else None,
        "total_net_pnl_usd": sum(values) if values else None,
    }


def compute_breakdowns(
    rows: Sequence[JudgeCalibrationOutcomeRow],
    *,
    gross_pnl_fallback: bool = False,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, list[JudgeCalibrationOutcomeRow]]] = {
        "by_symbol": defaultdict(list),
        "by_regime": defaultdict(list),
        "by_side": defaultdict(list),
        "by_symbol_regime_side": defaultdict(list),
    }
    for row in rows:
        grouped["by_symbol"][row.symbol].append(row)
        grouped["by_regime"][row.regime_label or "UNKNOWN"].append(row)
        grouped["by_side"][row.side].append(row)
        grouped["by_symbol_regime_side"][f"{row.symbol}|{row.regime_label or 'UNKNOWN'}|{row.side}"].append(row)
    return {
        group_name: {
            key: _summary_for_rows(value, gross_pnl_fallback=gross_pnl_fallback)
            for key, value in sorted(group.items())
        }
        for group_name, group in grouped.items()
    }


def render_policy_patch_proposal(candidates: Sequence[ConfidenceBandCandidate]) -> dict[str, Any] | None:
    allow = [
        {"min": band.min_confidence, "max": band.max_confidence, "action": "allow"}
        for band in candidates
        if band.status == "CANDIDATE" and band.action == "allow"
    ]
    suppress = [
        {"min": band.min_confidence, "max": band.max_confidence, "action": "suppress"}
        for band in candidates
        if band.status == "TOXIC" and band.action == "suppress"
    ]
    if not allow and not suppress:
        return None
    return {
        "judge" + "_bridge": {
            "confidence_policy": {
                "open_bands": allow,
                "suppress_bands": suppress,
                "auto_apply": False,
            }
        }
    }


def _proposal_id(
    *,
    rows: Sequence[JudgeCalibrationOutcomeRow],
    band_step: float,
    cadence_days: int,
    min_rows: int,
    min_symbols: int,
) -> str:
    source = "|".join(row.row_id for row in sorted(rows, key=lambda row: row.row_id))
    digest = hashlib.sha256(
        f"{source}|{band_step}|{cadence_days}|{min_rows}|{min_symbols}".encode("utf-8")
    ).hexdigest()[:16]
    return f"judge_conf_cal_{digest}"


def _window(
    train_rows: Sequence[JudgeCalibrationOutcomeRow],
    holdout_rows: Sequence[JudgeCalibrationOutcomeRow],
    *,
    cadence_days: int,
) -> CalibrationWindow:
    all_train = list(train_rows)
    if not all_train:
        return CalibrationWindow(
            train_start_ts_ms=0,
            train_end_ts_ms=0,
            holdout_start_ts_ms=None,
            holdout_end_ts_ms=None,
            cadence_days=cadence_days,
        )
    return CalibrationWindow(
        train_start_ts_ms=min(row.decision_ts_ms for row in all_train),
        train_end_ts_ms=max(row.decision_ts_ms for row in all_train),
        holdout_start_ts_ms=min((row.decision_ts_ms for row in holdout_rows), default=None),
        holdout_end_ts_ms=max((row.decision_ts_ms for row in holdout_rows), default=None),
        cadence_days=cadence_days,
    )


def build_calibration_proposal(
    rows: Sequence[Mapping[str, Any] | JudgeCalibrationOutcomeRow],
    *,
    created_ts_ms: int,
    band_step: float,
    cadence_days: int,
    min_rows: int,
    min_symbols: int,
    holdout_ratio: float = 0.0,
    gross_pnl_fallback: bool = False,
    input_paths: Sequence[str] = (),
    report_path: str | None = None,
) -> JudgeConfidenceCalibrationProposalV1:
    parsed_rows = build_calibration_rows(rows)
    train_rows, holdout_rows = split_train_holdout(parsed_rows, holdout_ratio=holdout_ratio)
    warnings = validate_calibration_dataset(parsed_rows)
    buckets = bucket_confidence_bands(train_rows, band_step=band_step)
    candidates = compute_band_metrics(
        buckets,
        min_rows=min_rows,
        gross_pnl_fallback=gross_pnl_fallback,
    )
    usable_rows = sum(
        1
        for row in parsed_rows
        if row.judge_confidence is not None and _economics_value(row, gross_pnl_fallback=gross_pnl_fallback) is not None
    )
    symbols = sorted({row.symbol for row in parsed_rows})
    regimes = sorted({row.regime_label or "UNKNOWN" for row in parsed_rows})
    sides = sorted({row.side for row in parsed_rows})
    split_valid = True
    if train_rows and holdout_rows:
        split_valid = max(row.decision_ts_ms for row in train_rows) <= min(row.decision_ts_ms for row in holdout_rows)
    future_warnings = [
        f"{row.row_id}:outcome_before_decision"
        for row in parsed_rows
        if row.outcome_ts_ms is not None and row.outcome_ts_ms < row.decision_ts_ms
    ]
    return JudgeConfidenceCalibrationProposalV1(
        proposal_id=_proposal_id(
            rows=parsed_rows,
            band_step=band_step,
            cadence_days=cadence_days,
            min_rows=min_rows,
            min_symbols=min_symbols,
        ),
        created_ts_ms=created_ts_ms,
        calibration_window=_window(train_rows, holdout_rows, cadence_days=cadence_days),
        dataset_summary=CalibrationDatasetSummary(
            total_rows=len(parsed_rows),
            usable_rows=usable_rows,
            unresolved_rows=sum(1 for row in parsed_rows if row.outcome.net_pnl_usd is None),
            symbols=symbols,
            regimes=regimes,
            sides=sides,
        ),
        gates=CalibrationGates(
            min_rows_required=min_rows,
            min_symbols_required=min_symbols,
            min_usable_rows_passed=usable_rows >= min_rows,
            min_symbols_passed=len(symbols) >= min_symbols,
            holdout_present=bool(holdout_rows),
        ),
        confidence_bands=ConfidenceBands(candidates=candidates),
        breakdowns=compute_breakdowns(train_rows, gross_pnl_fallback=gross_pnl_fallback),
        recommended_policy=RecommendedPolicy(config_patch=render_policy_patch_proposal(candidates)),
        anti_leakage=AntiLeakageReport(
            train_holdout_split_valid=split_valid,
            no_future_outcome_in_train_features=not future_warnings,
            leakage_warnings=[*warnings, *future_warnings],
        ),
        source_refs=CalibrationProposalSourceRefs(
            input_paths=list(input_paths),
            report_path=report_path,
        ),
    )
