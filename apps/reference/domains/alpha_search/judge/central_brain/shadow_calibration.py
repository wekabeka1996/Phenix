from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.reference.domains.alpha_search.judge.central_brain.calibration import (
    JudgeCalibrationOutcome,
    JudgeCalibrationOutcomeRow,
    JudgeCalibrationSourceRefs,
)


SCHEMA_VERSION = "1.0.0"
LIVE_GATED_MODE = "live" + "_gated"

SourceKind = Literal["runtime_shadow", "replay", "simulator", "testnet"]
Side = Literal["BUY", "SELL", "NONE", "UNKNOWN"]
PolicyVerdict = Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"]
AuthorityMode = str
BridgeAction = Literal["record_only", "allow", "suppress", "skip", "blocked"]
OutcomeStatus = Literal["RESOLVED", "UNRESOLVED", "MISSING", "NOT_APPLICABLE"]
JoinQuality = Literal["EXACT", "RID_EXACT", "FUZZY", "UNJOINED", "SYNTHETIC"]


class ShadowCalibrationEnvelopeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_id: str | None = None
    present: bool
    missing_reason: str | None = None

    @model_validator(mode="after")
    def validate_presence(self) -> "ShadowCalibrationEnvelopeBlock":
        if self.present and not self.envelope_id:
            raise ValueError("present envelope requires envelope_id")
        if not self.present and not self.missing_reason:
            raise ValueError("missing envelope requires missing_reason")
        return self


class ShadowCalibrationVerdictBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict_id: str | None = None
    verdict: PolicyVerdict | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    authority_status: Literal["shadow_only"] | None = None
    applied: Literal[False] | None = None


class ShadowCalibrationBridgeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bridge_decision_id: str | None = None
    authority_mode: AuthorityMode | None = None
    bridge_action: BridgeAction | None = None
    applied: Literal[False] | None = None
    no_effect: Literal[True] | None = None

    @field_validator("authority_mode")
    @classmethod
    def validate_authority_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in {"shadow", "advisory", "hybrid_gated", LIVE_GATED_MODE}:
            raise ValueError("unsupported authority_mode")
        return value

    @model_validator(mode="after")
    def validate_no_effect_when_present(self) -> "ShadowCalibrationBridgeBlock":
        present = any(
            value is not None
            for value in (
                self.bridge_decision_id,
                self.authority_mode,
                self.bridge_action,
                self.applied,
                self.no_effect,
            )
        )
        if present and self.no_effect is not True:
            raise ValueError("present bridge block requires no_effect=true")
        return self


class ShadowCalibrationOutcomeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome_status: OutcomeStatus
    outcome_ts_ms: int | None = Field(default=None, ge=0)
    horizon_sec: int | None = Field(default=None, gt=0)
    gross_pnl_usd: float | None = None
    net_pnl_usd: float | None = None
    fees_usd: float | None = None
    slippage_usd: float | None = None
    max_favorable_usd: float | None = None
    max_adverse_usd: float | None = None
    terminal_status: str | None = None

    @model_validator(mode="after")
    def validate_resolved_economics(self) -> "ShadowCalibrationOutcomeBlock":
        if self.outcome_status == "RESOLVED" and self.net_pnl_usd is None:
            raise ValueError("RESOLVED outcome requires net_pnl_usd")
        if self.outcome_status in {"RESOLVED", "UNRESOLVED"} and self.horizon_sec is None:
            raise ValueError("resolved or unresolved outcome requires horizon_sec")
        return self


class ShadowCalibrationSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    rid: str | None = None
    lifecycle_id: str | None = None
    order_id: str | None = None
    trace_id: str | None = None
    input_paths: list[str] = Field(default_factory=list)


class ShadowCalibrationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    missing_fields: list[str] = Field(default_factory=list)
    join_quality: JoinQuality
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_join_reason_consistency(self) -> "ShadowCalibrationDiagnostics":
        joined_by_fuzzy = "joined_by_fuzzy_window" in self.reason_codes
        if joined_by_fuzzy and self.join_quality == "EXACT":
            raise ValueError("fuzzy joins cannot be marked EXACT")
        return self


class JudgeShadowCalibrationRowV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    row_id: str = Field(min_length=1)
    source_kind: SourceKind
    created_ts_ms: int = Field(ge=0)
    decision_ts_ms: int = Field(ge=0)
    symbol: str = Field(min_length=1)
    side: Side
    regime_label: str | None = None
    regime_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    envelope: ShadowCalibrationEnvelopeBlock
    verdict: ShadowCalibrationVerdictBlock
    bridge: ShadowCalibrationBridgeBlock
    outcome: ShadowCalibrationOutcomeBlock
    source_refs: ShadowCalibrationSourceRefs
    diagnostics: ShadowCalibrationDiagnostics

    @model_validator(mode="after")
    def validate_time_order(self) -> "JudgeShadowCalibrationRowV1":
        if self.outcome.outcome_ts_ms is not None and self.outcome.outcome_ts_ms < self.decision_ts_ms:
            raise ValueError("outcome_ts_ms must not precede decision_ts_ms")
        return self


def side_from_verdict(verdict: str | None) -> Side:
    if verdict == "OPEN_LONG":
        return "BUY"
    if verdict == "OPEN_SHORT":
        return "SELL"
    if verdict in {"NO_ENTRY", "SUPPRESS"}:
        return "NONE"
    return "UNKNOWN"


def identity_missing_fields(source_refs: ShadowCalibrationSourceRefs) -> list[str]:
    missing: list[str] = []
    for field in ("decision_id", "rid", "lifecycle_id"):
        if getattr(source_refs, field) in (None, ""):
            missing.append(f"source_refs.{field}")
    return missing


def to_phase8_calibration_row(row: JudgeShadowCalibrationRowV1) -> JudgeCalibrationOutcomeRow:
    return JudgeCalibrationOutcomeRow(
        row_id=row.row_id,
        decision_ts_ms=row.decision_ts_ms,
        outcome_ts_ms=row.outcome.outcome_ts_ms,
        symbol=row.symbol,
        side=row.side,
        regime_label=row.regime_label,
        regime_confidence=row.regime_confidence,
        verdict=row.verdict.verdict or "UNKNOWN",
        judge_confidence=row.verdict.confidence,
        bridge_action=row.bridge.bridge_action,
        authority_mode=row.bridge.authority_mode,
        applied=False,
        missingness_state=",".join(row.diagnostics.missing_fields) if row.diagnostics.missing_fields else None,
        freshness_state=None,
        outcome=JudgeCalibrationOutcome(
            horizon_sec=row.outcome.horizon_sec or 1,
            gross_pnl_usd=row.outcome.gross_pnl_usd,
            net_pnl_usd=row.outcome.net_pnl_usd,
            fees_usd=row.outcome.fees_usd,
            slippage_usd=row.outcome.slippage_usd,
            max_favorable_usd=row.outcome.max_favorable_usd,
            max_adverse_usd=row.outcome.max_adverse_usd,
            terminal_status=row.outcome.terminal_status,
        ),
        source_refs=JudgeCalibrationSourceRefs(
            verdict_id=row.verdict.verdict_id,
            envelope_id=row.envelope.envelope_id,
            decision_id=row.source_refs.decision_id,
            rid=row.source_refs.rid,
            lifecycle_id=row.source_refs.lifecycle_id,
        ),
    )
