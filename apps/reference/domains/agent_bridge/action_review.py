"""Immutable, no-model, no-execution ActionReviewV1 memory ledger."""
from __future__ import annotations

import json
import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .contracts import ActionReviewMemorySummaryV1, ActionReviewScenarioMemoryV1


LEDGER_FILENAME = "action_review_ledger_v1.jsonl"
LEDGER_REF = "aurora-publication://action-reviews/ledger/v1"
MAX_LEDGER_BYTES = 4 * 1024 * 1024
MAX_ROW_BYTES = 16 * 1024
MAX_REVIEW_TOKENS = 1_200

SCENARIO_IDS = (
    "continuation",
    "mean_reversion",
    "fakeout_reversal",
    "chop_fee_trap",
    "late_entry_failure",
    "breakout_followthrough",
    "volatility_expansion",
    "volatility_compression",
    "unexpected_news_or_external",
    "data_stale_or_missing",
    "no_clear_scenario",
)
ScenarioId = Literal[
    "continuation",
    "mean_reversion",
    "fakeout_reversal",
    "chop_fee_trap",
    "late_entry_failure",
    "breakout_followthrough",
    "volatility_expansion",
    "volatility_compression",
    "unexpected_news_or_external",
    "data_stale_or_missing",
    "no_clear_scenario",
]
ProposedAction = Literal[
    "WAIT",
    "OBSERVE",
    "NO_ACTION",
    "HYPOTHETICAL_OPEN_LONG",
    "HYPOTHETICAL_OPEN_SHORT",
    "HYPOTHETICAL_CLOSE",
    "HYPOTHETICAL_PROTECT",
]
ExecutionStatus = Literal[
    "not_submitted_p9_no_execution",
    "not_submitted_hypothetical",
    "not_submitted_wait",
    "blocked_by_package_scope",
    "future_field_unset",
]


class ExpectedScenarioV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: ScenarioId
    confidence: float = Field(ge=0.0, le=1.0)
    thesis: str = Field(min_length=8, max_length=320)
    evidence_refs: list[str] = Field(min_length=1, max_length=8)


class PreActionNoteV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")
    packet_id: str = Field(min_length=8, max_length=128, pattern=r"^afp_[0-9a-f]+$")
    symbol: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    horizon: str = Field(min_length=2, max_length=32)
    proposed_action: ProposedAction
    thesis: str = Field(min_length=12, max_length=600)
    invalidation: str = Field(min_length=8, max_length=400)
    expected_scenarios: list[ExpectedScenarioV1] = Field(min_length=1, max_length=3)
    warnings_acknowledged: list[str] = Field(default_factory=list, max_length=12)
    data_refs_used: list[str] = Field(min_length=1, max_length=12)
    tool_refs_used: list[str] = Field(min_length=1, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    no_execution: Literal[True] = True

    @model_validator(mode="after")
    def unique_scenarios(self):
        ids = [item.scenario_id for item in self.expected_scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("expected scenario ids must be unique")
        hypothetical = self.proposed_action.startswith("HYPOTHETICAL_")
        if hypothetical and self.confidence > 0.95:
            raise ValueError("hypothetical confidence must remain bounded")
        return self


class ExecutionNoteV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExecutionStatus
    submitted: Literal[False] = False
    detail: str = Field(min_length=8, max_length=320)
    no_execution: Literal[True] = True


class OutcomeReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_from_packet_ref: str
    observed_to_packet_ref: str
    observation_window_ms: int = Field(ge=0)
    what_happened: str = Field(min_length=12, max_length=600)
    realized_scenario: ScenarioId
    scenario_confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=1, max_length=12)
    expected_result_achieved: bool
    outcome_unexpected: bool
    logical_explanation: str = Field(min_length=8, max_length=500)
    lesson_to_remember: str = Field(min_length=8, max_length=500)
    future_review_needed: bool
    no_trade_pnl_claim: Literal[True] = True


class ActionReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["action-review/v1"] = "action-review/v1"
    review_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")
    revision: int = Field(ge=1)
    supersedes_ref: Optional[str] = None
    created_ts_ms: int = Field(ge=0)
    updated_ts_ms: int = Field(ge=0)
    mode: Literal["no_execution", "hypothetical", "future_model_placeholder"]
    source: Literal["deterministic_fixture", "manual_operator", "no_model_local_sample"]
    agent_id: str = Field(min_length=3, max_length=128)
    model_id: None = None
    model_call_ref: None = None
    operator_ref: Optional[str] = Field(default=None, max_length=256)
    packet_ref: str
    symbol: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    horizon: str = Field(min_length=2, max_length=32)
    pre_action_note: PreActionNoteV1
    execution_note: ExecutionNoteV1
    outcome_review: Optional[OutcomeReviewV1] = None
    raw_refs: list[str] = Field(min_length=1, max_length=16)
    compact_summary: str = Field(min_length=12, max_length=600)
    token_estimate: int = Field(ge=1, le=MAX_REVIEW_TOKENS)
    validation_status: Literal["valid"] = "valid"

    @model_validator(mode="after")
    def enforce_p9_no_execution_contract(self):
        expected_packet_ref = f"agent-feed://packet/{self.pre_action_note.packet_id}"
        if self.review_id != self.pre_action_note.review_id:
            raise ValueError("top-level and pre-action review ids must match")
        if self.symbol != self.pre_action_note.symbol or self.horizon != self.pre_action_note.horizon:
            raise ValueError("top-level and pre-action symbol/horizon must match")
        if self.packet_ref != expected_packet_ref:
            raise ValueError("packet_ref must bind the pre-action packet id")
        if self.updated_ts_ms < self.created_ts_ms:
            raise ValueError("updated_ts_ms must not precede created_ts_ms")
        if self.revision == 1 and self.supersedes_ref is not None:
            raise ValueError("revision 1 cannot supersede another row")
        if self.revision > 1 and not self.supersedes_ref:
            raise ValueError("later revisions require supersedes_ref")
        hypothetical = self.pre_action_note.proposed_action.startswith("HYPOTHETICAL_")
        if hypothetical and self.mode != "hypothetical":
            raise ValueError("hypothetical actions require hypothetical mode")
        if not hypothetical and self.mode == "hypothetical":
            raise ValueError("hypothetical mode requires a hypothetical action")
        if hypothetical and self.execution_note.status not in {
            "not_submitted_hypothetical", "blocked_by_package_scope"
        }:
            raise ValueError("hypothetical action has incompatible no-execution status")
        if self.outcome_review is not None:
            expected_ids = {
                item.scenario_id for item in self.pre_action_note.expected_scenarios
            }
            achieved = self.outcome_review.realized_scenario in expected_ids
            if self.outcome_review.expected_result_achieved != achieved:
                raise ValueError("expected_result_achieved must match scenario realization")
            if self.outcome_review.outcome_unexpected == achieved:
                raise ValueError("outcome_unexpected must be the inverse of expected realization")
        return self


_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|secret|password)\s*[:=]\s*[^\s,]{8,}", re.IGNORECASE),
)
_FORBIDDEN_KEYS = {
    "order_id", "client_order_id", "exchange_order_id", "fill_id", "trade_id"
}


def review_ref(review_id: str, revision: int) -> str:
    return f"{LEDGER_REF}#review_id={review_id}&revision={revision}"


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def estimate_review_tokens(review: ActionReviewV1) -> int:
    return math.ceil(len(review.model_dump_json(exclude_none=True).encode("utf-8")) / 4)


def finalize_action_review(data: dict[str, Any]) -> ActionReviewV1:
    """Stabilize the bounded full-row token estimate without external tooling."""

    candidate = dict(data)
    candidate["token_estimate"] = int(candidate.get("token_estimate") or 1)
    for _ in range(8):
        model = ActionReviewV1.model_validate(candidate)
        estimate = estimate_review_tokens(model)
        if estimate == model.token_estimate:
            return model
        candidate["token_estimate"] = estimate
    return ActionReviewV1.model_validate(candidate)


def lint_action_review(review: ActionReviewV1) -> list[str]:
    errors: list[str] = []
    payload = review.model_dump(mode="json", exclude_none=True)
    keys = set(_walk_keys(payload))
    forbidden = sorted(keys & _FORBIDDEN_KEYS)
    if forbidden:
        errors.append(f"forbidden execution identity fields: {','.join(forbidden)}")
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if any(pattern.search(serialized) for pattern in _SECRET_PATTERNS):
        errors.append("secret-looking value detected")
    if not review.packet_ref.startswith("agent-feed://packet/afp_"):
        errors.append("packet_ref is missing or invalid")
    if estimate_review_tokens(review) != review.token_estimate:
        errors.append("token_estimate does not match serialized review")
    if len(review.compact_summary) > 600:
        errors.append("compact_summary exceeds 600 characters")
    if len(review.model_dump_json(exclude_none=True).encode("utf-8")) > MAX_ROW_BYTES:
        errors.append("review row exceeds maximum bytes")
    return errors


class ActionReviewLedger:
    """Append-only version ledger with per-process concurrency guard."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.path = self.directory / LEDGER_FILENAME
        self._lock = threading.RLock()

    def rows(self) -> list[ActionReviewV1]:
        try:
            if self.path.stat().st_size > MAX_LEDGER_BYTES:
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[ActionReviewV1] = []
        for line in lines:
            if len(line.encode("utf-8")) > MAX_ROW_BYTES:
                continue
            try:
                rows.append(ActionReviewV1.model_validate_json(line))
            except (ValidationError, ValueError):
                continue
        return rows

    def latest(self) -> dict[str, ActionReviewV1]:
        latest: dict[str, ActionReviewV1] = {}
        for row in self.rows():
            current = latest.get(row.review_id)
            if current is None or row.revision > current.revision:
                latest[row.review_id] = row
        return latest

    def append(self, review: ActionReviewV1) -> bool:
        errors = lint_action_review(review)
        if errors:
            raise ValueError("; ".join(errors))
        payload = review.model_dump_json(exclude_none=True)
        with self._lock:
            rows = self.rows()
            same_revision = [
                row for row in rows
                if row.review_id == review.review_id and row.revision == review.revision
            ]
            if same_revision:
                if same_revision[-1].model_dump() == review.model_dump():
                    return False
                raise ValueError("review_id/revision already exists with different content")
            prior = [row for row in rows if row.review_id == review.review_id]
            if not prior:
                if review.revision != 1:
                    raise ValueError("new review must start at revision 1")
            else:
                previous = max(prior, key=lambda row: row.revision)
                if review.revision != previous.revision + 1:
                    raise ValueError("revision must increase exactly by one")
                if review.supersedes_ref != review_ref(previous.review_id, previous.revision):
                    raise ValueError("supersedes_ref must point to the previous revision")
                immutable_fields = (
                    "created_ts_ms", "mode", "source", "agent_id", "model_id",
                    "model_call_ref", "operator_ref", "packet_ref", "symbol", "horizon",
                    "pre_action_note", "execution_note",
                )
                for name in immutable_fields:
                    if getattr(review, name) != getattr(previous, name):
                        raise ValueError(f"later revision changed immutable field: {name}")
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, (payload + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return True

    def packet_summary(self, symbols: Iterable[str]) -> ActionReviewMemorySummaryV1:
        allowed = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        latest = [row for row in self.latest().values() if row.symbol in allowed]
        latest.sort(key=lambda row: (row.updated_ts_ms, row.review_id), reverse=True)
        memories = []
        for row in latest[:12]:
            outcome = row.outcome_review
            memories.append(ActionReviewScenarioMemoryV1(
                review_id=row.review_id,
                revision=row.revision,
                symbol=row.symbol,
                proposed_action=row.pre_action_note.proposed_action,
                execution_status=row.execution_note.status,
                expected_scenarios=[item.scenario_id for item in row.pre_action_note.expected_scenarios],
                realized_scenario=outcome.realized_scenario if outcome else None,
                lesson=outcome.lesson_to_remember if outcome else None,
                unresolved=outcome is None or outcome.future_review_needed,
                packet_ref=row.packet_ref,
                review_ref=review_ref(row.review_id, row.revision),
            ))
        return ActionReviewMemorySummaryV1(
            latest_review_ids_by_symbol={row.symbol: row.review_id for row in latest[:12]},
            latest_scenario_memory=memories,
            unresolved_review_count=sum(item.unresolved for item in memories),
            raw_ledger_ref=LEDGER_REF,
        )


def validate_ledger(path: Path) -> list[str]:
    errors: list[str] = []
    ledger = ActionReviewLedger(Path(path).parent)
    if ledger.path != Path(path):
        errors.append("ledger filename must be action_review_ledger_v1.jsonl")
        return errors
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"ledger unavailable: {type(exc).__name__}"]
    parsed: list[ActionReviewV1] = []
    for index, line in enumerate(lines, 1):
        try:
            review = ActionReviewV1.model_validate_json(line)
        except (ValidationError, ValueError) as exc:
            errors.append(f"line {index}: invalid schema: {exc}")
            continue
        for issue in lint_action_review(review):
            errors.append(f"line {index}: {issue}")
        parsed.append(review)
    seen: set[tuple[str, int]] = set()
    for row in parsed:
        identity = (row.review_id, row.revision)
        if identity in seen:
            errors.append(f"duplicate review revision: {row.review_id}/{row.revision}")
        seen.add(identity)
    grouped: dict[str, list[ActionReviewV1]] = {}
    for row in parsed:
        grouped.setdefault(row.review_id, []).append(row)
    for review_id, revisions in grouped.items():
        ordered = sorted(revisions, key=lambda row: row.revision)
        for index, row in enumerate(ordered, 1):
            if row.revision != index:
                errors.append(f"non-contiguous revision: {review_id}/{row.revision}")
            if index > 1 and row.supersedes_ref != review_ref(review_id, index - 1):
                errors.append(f"invalid supersedes_ref: {review_id}/{row.revision}")
    return errors


__all__ = [
    "ActionReviewLedger", "ActionReviewV1", "ExecutionNoteV1", "ExpectedScenarioV1",
    "LEDGER_FILENAME", "LEDGER_REF", "OutcomeReviewV1", "PreActionNoteV1",
    "SCENARIO_IDS", "estimate_review_tokens", "finalize_action_review",
    "lint_action_review", "review_ref", "validate_ledger",
]
