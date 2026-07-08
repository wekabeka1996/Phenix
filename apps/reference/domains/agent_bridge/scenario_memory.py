"""Read-only ScenarioMemoryIndexV0 over the append-only ActionReviewV1 ledger."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .action_review import (
    ActionReviewV1,
    LEDGER_FILENAME,
    LEDGER_REF,
    SCENARIO_IDS,
    lint_action_review,
    review_ref,
)
from .contracts import ActionReviewMemorySummaryV1, ActionReviewScenarioMemoryV1


INDEX_FILENAME = "scenario_memory_index_v0.json"
INDEX_REF = "aurora-publication://scenario-memory/index/v0"
MAX_INDEX_BYTES = 128 * 1024
MAX_QUERY_TOKENS = 1_200
MAX_SUMMARY_TOKENS = 600
MAX_ITEMS = 20

QueryType = Literal[
    "latest",
    "completed",
    "unresolved",
    "scenario_accuracy",
    "confusion",
    "lessons",
    "packet",
]


class RetentionSummaryV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_rows_retained: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    invalid_rows_excluded: int = Field(ge=0)
    latest_revisions_indexed: int = Field(ge=0)
    unresolved_retained: int = Field(ge=0)
    full_ledger_bytes: int = Field(ge=0)
    deletion_performed: Literal[False] = False
    archival_recommended: bool
    archival_reason: Optional[str] = None


class CalibrationStatisticsV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed_count: int = Field(ge=0)
    expected_scenario_count: int = Field(ge=0)
    realized_scenario_count: int = Field(ge=0)
    expected_scenario_realized_count: int = Field(ge=0)
    unexpected_outcome_count: int = Field(ge=0)
    no_clear_scenario_count: int = Field(ge=0)
    completed_by_symbol: dict[str, int] = Field(default_factory=dict, max_length=64)
    completed_by_horizon: dict[str, int] = Field(default_factory=dict, max_length=32)
    unresolved_count: int = Field(ge=0)
    sample_size_warning: bool
    warning: Optional[str] = None
    descriptive_only: Literal[True] = True


class ScenarioMemoryItemV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    revision: int = Field(ge=1)
    symbol: str
    horizon: str
    updated_ts_ms: int
    completed: bool
    unresolved: bool
    expected_scenarios: list[str] = Field(default_factory=list, max_length=3)
    realized_scenario: Optional[str] = None
    expected_result_achieved: Optional[bool] = None
    lesson: Optional[str] = Field(default=None, max_length=240)
    packet_ref: str
    raw_ref: str


class ScenarioMemoryIndexV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scenario-memory-index/v0"] = "scenario-memory-index/v0"
    built_ts_ms: int
    ledger_ref: str = LEDGER_REF
    review_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    completed_by_provenance: dict[str, int] = Field(default_factory=dict, max_length=8)
    completed_by_session: dict[str, int] = Field(default_factory=dict, max_length=32)
    symbols: list[str] = Field(default_factory=list, max_length=64)
    horizons: list[str] = Field(default_factory=list, max_length=32)
    scenario_counts: dict[str, dict[str, int]] = Field(default_factory=dict, max_length=32)
    expected_realized_matrix: dict[str, dict[str, int]] = Field(default_factory=dict, max_length=32)
    latest_reviews_by_symbol: dict[str, list[ScenarioMemoryItemV0]] = Field(default_factory=dict, max_length=64)
    latest_lessons_by_symbol: dict[str, str] = Field(default_factory=dict, max_length=64)
    calibration: CalibrationStatisticsV0
    retention_summary: RetentionSummaryV0
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal["valid", "degraded", "invalid"]
    validation_errors: list[str] = Field(default_factory=list, max_length=32)


class ScenarioMemoryQueryResultV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scenario-memory-query-result/v0"] = "scenario-memory-query-result/v0"
    query_id: str
    query_type: QueryType
    symbol: Optional[str] = None
    horizon: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict, max_length=8)
    result_count: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    items: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_ITEMS)
    raw_refs: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    truncated: bool = False
    omitted_sections: list[str] = Field(default_factory=list, max_length=8)


class ScenarioMemorySymbolSummaryV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    unresolved_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    latest_lesson: Optional[str] = Field(default=None, max_length=160)
    latest_review_ref: Optional[str] = None


class ScenarioMemorySummaryV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scenario-memory-summary/v0"] = "scenario-memory-summary/v0"
    built_ts_ms: int
    symbols: list[str]
    items: list[ScenarioMemorySymbolSummaryV0]
    index_ref: str = INDEX_REF
    estimated_tokens: int = Field(ge=0)
    truncated: bool = False
    omitted_sections: list[str] = Field(default_factory=list, max_length=8)


def _estimated_tokens(value: BaseModel) -> int:
    return math.ceil(len(value.model_dump_json(exclude_none=True).encode("utf-8")) / 4)


def _compact(row: ActionReviewV1) -> ScenarioMemoryItemV0:
    outcome = row.outcome_review
    return ScenarioMemoryItemV0(
        review_id=row.review_id,
        revision=row.revision,
        symbol=row.symbol,
        horizon=row.horizon,
        updated_ts_ms=row.updated_ts_ms,
        completed=outcome is not None,
        unresolved=outcome is None or outcome.future_review_needed,
        expected_scenarios=[item.scenario_id for item in row.pre_action_note.expected_scenarios],
        realized_scenario=outcome.realized_scenario if outcome else None,
        expected_result_achieved=outcome.expected_result_achieved if outcome else None,
        lesson=outcome.lesson_to_remember[:240] if outcome else None,
        packet_ref=row.packet_ref,
        raw_ref=review_ref(row.review_id, row.revision),
    )


class ScenarioMemoryStore:
    """Pure local read/query owner; the source ledger is never modified."""

    def __init__(self, project_root: Path, *, now_ms_fn=None) -> None:
        self.project_root = Path(project_root).resolve()
        self.ledger_path = self.project_root / "ops" / "agent_bridge" / "action_reviews" / LEDGER_FILENAME
        self.index_dir = self.project_root / "ops" / "agent_bridge" / "scenario_memory"
        self.index_path = self.index_dir / INDEX_FILENAME
        self.now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))
        self._cache_lock = threading.RLock()
        self._latest_cache: Optional[tuple[tuple[int, int], tuple[list[ActionReviewV1], int, int, list[str], bytes]]] = None
        self._index_cache: Optional[tuple[tuple[int, int], ScenarioMemoryIndexV0]] = None
        self._cache_hits = 0
        self._cache_misses = 0

    def _ledger_signature(self) -> Optional[tuple[int, int]]:
        try:
            stat = self.ledger_path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def cache_info(self) -> dict[str, Any]:
        """Bounded diagnostics; never exposes review payloads."""

        with self._cache_lock:
            return {
                "latest_cached": self._latest_cache is not None,
                "index_cached": self._index_cache is not None,
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "signature": list(self._latest_cache[0]) if self._latest_cache else None,
                "source_hash": self._index_cache[1].source_hash if self._index_cache else None,
            }

    def _parse(self) -> tuple[list[ActionReviewV1], int, int, list[str], bytes]:
        try:
            raw = self.ledger_path.read_bytes()
        except FileNotFoundError:
            return [], 0, 0, ["ledger_missing"], b""
        except OSError as exc:
            return [], 0, 0, [f"ledger_unavailable:{type(exc).__name__}"], b""
        valid: list[ActionReviewV1] = []
        invalid = 0
        errors: list[str] = []
        lines = raw.splitlines()
        for line_no, line in enumerate(lines, 1):
            try:
                row = ActionReviewV1.model_validate_json(line)
                lint = lint_action_review(row)
                if lint:
                    raise ValueError(";".join(lint))
                valid.append(row)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                invalid += 1
                errors.append(f"line_{line_no}:{type(exc).__name__}")
        return valid, len(lines), invalid, errors[:32], raw

    def latest_rows(self) -> tuple[list[ActionReviewV1], int, int, list[str], bytes]:
        with self._cache_lock:
            signature = self._ledger_signature()
            if signature is not None and self._latest_cache and self._latest_cache[0] == signature:
                self._cache_hits += 1
                return self._latest_cache[1]
            self._cache_misses += 1
            rows, raw_count, invalid, errors, raw = self._parse()
            latest: dict[str, ActionReviewV1] = {}
            for row in rows:
                current = latest.get(row.review_id)
                if current is None or row.revision > current.revision:
                    latest[row.review_id] = row
            result = sorted(latest.values(), key=lambda row: (row.updated_ts_ms, row.review_id), reverse=True)
            value = (result, raw_count, invalid, errors, raw)
            final_signature = self._ledger_signature()
            if signature is not None and final_signature == signature:
                self._latest_cache = (signature, value)
                if self._index_cache and self._index_cache[0] != signature:
                    self._index_cache = None
            return value

    def build_index(self, *, persist: bool = False) -> ScenarioMemoryIndexV0:
        signature = self._ledger_signature()
        with self._cache_lock:
            if not persist and signature is not None and self._index_cache and self._index_cache[0] == signature:
                self._cache_hits += 1
                return self._index_cache[1]
        rows, raw_count, invalid, errors, raw = self.latest_rows()
        completed = [row for row in rows if row.outcome_review is not None]
        unresolved = [row for row in rows if row.outcome_review is None or row.outcome_review.future_review_needed]
        scenario_counts = {
            scenario: {"expected": 0, "realized": 0, "expected_realized": 0}
            for scenario in SCENARIO_IDS
        }
        matrix: dict[str, Counter[str]] = defaultdict(Counter)
        expected_total = 0
        expected_realized = 0
        unexpected = 0
        no_clear = 0
        by_symbol: Counter[str] = Counter()
        by_horizon: Counter[str] = Counter()
        by_provenance: Counter[str] = Counter()
        by_session: Counter[str] = Counter()
        for row in rows:
            for expected in row.pre_action_note.expected_scenarios:
                scenario_counts[expected.scenario_id]["expected"] += 1
        for row in completed:
            outcome = row.outcome_review
            assert outcome is not None
            expected_ids = [item.scenario_id for item in row.pre_action_note.expected_scenarios]
            expected_total += len(expected_ids)
            scenario_counts[outcome.realized_scenario]["realized"] += 1
            if outcome.expected_result_achieved:
                expected_realized += 1
                scenario_counts[outcome.realized_scenario]["expected_realized"] += 1
            if outcome.outcome_unexpected:
                unexpected += 1
            if outcome.realized_scenario == "no_clear_scenario":
                no_clear += 1
            for expected in expected_ids:
                matrix[expected][outcome.realized_scenario] += 1
            by_symbol[row.symbol] += 1
            by_horizon[row.horizon] += 1
            if row.agent_id.startswith("p17."):
                provenance = "p17_fresh_runtime"
                parts = row.agent_id.split(".")
                if len(parts) > 1:
                    by_session[parts[1]] += 1
            elif row.agent_id.startswith("p16."):
                provenance = "p16_fresh_runtime"
                parts = row.agent_id.split(".")
                if len(parts) > 1:
                    by_session[parts[1]] += 1
            elif row.agent_id.startswith("p15."):
                provenance = "p15_fresh_runtime"
                parts = row.agent_id.split(".")
                if len(parts) > 1:
                    by_session[parts[1]] += 1
            elif row.agent_id.startswith("p14."):
                provenance = "p14_fresh_runtime"
                parts = row.agent_id.split(".")
                if len(parts) > 1:
                    by_session[parts[1]] += 1
            elif row.agent_id.startswith("p13."):
                provenance = "p13_fresh_runtime"
            elif row.agent_id.startswith("p12."):
                provenance = "p12_fresh_runtime"
            else:
                provenance = "archived_or_prior"
            by_provenance[provenance] += 1
        latest_by_symbol: dict[str, list[ScenarioMemoryItemV0]] = {}
        latest_lessons: dict[str, str] = {}
        for symbol in sorted({row.symbol for row in rows}):
            symbol_rows = [row for row in rows if row.symbol == symbol]
            latest_by_symbol[symbol] = [_compact(row) for row in symbol_rows[:5]]
            lesson_row = next((row for row in symbol_rows if row.outcome_review and row.outcome_review.lesson_to_remember), None)
            if lesson_row and lesson_row.outcome_review:
                latest_lessons[symbol] = lesson_row.outcome_review.lesson_to_remember[:240]
        ledger_bytes = len(raw)
        archival = ledger_bytes >= 3 * 1024 * 1024 or raw_count >= 10_000
        calibration = CalibrationStatisticsV0(
            completed_count=len(completed),
            expected_scenario_count=expected_total,
            realized_scenario_count=len(completed),
            expected_scenario_realized_count=expected_realized,
            unexpected_outcome_count=unexpected,
            no_clear_scenario_count=no_clear,
            completed_by_symbol=dict(sorted(by_symbol.items())),
            completed_by_horizon=dict(sorted(by_horizon.items())),
            unresolved_count=len(unresolved),
            sample_size_warning=len(completed) < 30,
            warning="descriptive sample is smaller than 30 completed reviews" if len(completed) < 30 else None,
        )
        retention = RetentionSummaryV0(
            raw_rows_retained=raw_count,
            valid_rows=raw_count - invalid,
            invalid_rows_excluded=invalid,
            latest_revisions_indexed=len(rows),
            unresolved_retained=len(unresolved),
            full_ledger_bytes=ledger_bytes,
            archival_recommended=archival,
            archival_reason="ledger reached 3 MiB or 10,000 raw rows" if archival else None,
        )
        index = ScenarioMemoryIndexV0(
            built_ts_ms=self.now_ms_fn(),
            review_count=len(rows),
            completed_count=len(completed),
            unresolved_count=len(unresolved),
            completed_by_provenance=dict(sorted(by_provenance.items())),
            completed_by_session=dict(sorted(by_session.items())),
            symbols=sorted({row.symbol for row in rows}),
            horizons=sorted({row.horizon for row in rows}),
            scenario_counts={key: value for key, value in scenario_counts.items() if any(value.values())},
            expected_realized_matrix={key: dict(sorted(value.items())) for key, value in sorted(matrix.items())},
            latest_reviews_by_symbol=latest_by_symbol,
            latest_lessons_by_symbol=latest_lessons,
            calibration=calibration,
            retention_summary=retention,
            source_hash=hashlib.sha256(raw).hexdigest(),
            validation_status="invalid" if not raw and errors else "degraded" if invalid else "valid",
            validation_errors=errors,
        )
        if persist:
            self._write_index(index)
        final_signature = self._ledger_signature()
        with self._cache_lock:
            if signature is not None and final_signature == signature:
                self._index_cache = (signature, index)
        return index

    def query(
        self,
        *,
        query_type: QueryType,
        symbol: Optional[str] = None,
        horizon: Optional[str] = None,
        scenario: Optional[str] = None,
        packet_id: Optional[str] = None,
        limit: int = 5,
        max_tokens: int = MAX_QUERY_TOKENS,
    ) -> ScenarioMemoryQueryResultV0:
        if not 1 <= limit <= MAX_ITEMS:
            raise ValueError(f"limit must be between 1 and {MAX_ITEMS}")
        if not 100 <= max_tokens <= MAX_QUERY_TOKENS:
            raise ValueError(f"max_tokens must be between 100 and {MAX_QUERY_TOKENS}")
        if scenario is not None and scenario not in SCENARIO_IDS:
            raise ValueError("unknown scenario filter")
        rows, _, _, errors, raw = self.latest_rows()
        if not raw and errors:
            raise FileNotFoundError(errors[0])
        symbol_key = symbol.strip().upper() if symbol else None
        horizon_key = horizon.strip() if horizon else None
        filtered = [
            row for row in rows
            if (symbol_key is None or row.symbol == symbol_key)
            and (horizon_key is None or row.horizon == horizon_key)
            and (scenario is None or scenario in {item.scenario_id for item in row.pre_action_note.expected_scenarios}
                 or (row.outcome_review is not None and row.outcome_review.realized_scenario == scenario))
        ]
        if query_type == "completed":
            filtered = [row for row in filtered if row.outcome_review is not None]
        elif query_type == "unresolved":
            filtered = [row for row in filtered if row.outcome_review is None or row.outcome_review.future_review_needed]
        elif query_type == "lessons":
            filtered = [row for row in filtered if row.outcome_review and row.outcome_review.lesson_to_remember]
        elif query_type == "packet":
            if not packet_id:
                raise ValueError("packet_id is required for packet query")
            packet_ref = f"agent-feed://packet/{packet_id}"
            filtered = [row for row in filtered if row.packet_ref == packet_ref or (
                row.outcome_review is not None and packet_ref in row.outcome_review.evidence_refs
            )]
        if query_type == "scenario_accuracy":
            index = self.build_index()
            items: list[dict[str, Any]] = [index.calibration.model_dump(mode="json", exclude_none=True)]
        elif query_type == "confusion":
            index = self.build_index()
            items = [{"expected_realized_matrix": index.expected_realized_matrix}]
        else:
            items = [_compact(row).model_dump(mode="json", exclude_none=True) for row in filtered[:limit]]
        result = ScenarioMemoryQueryResultV0(
            query_id=f"smq_{uuid.uuid4().hex}",
            query_type=query_type,
            symbol=symbol_key,
            horizon=horizon_key,
            filters={key: value for key, value in {"scenario": scenario, "packet_id": packet_id, "limit": limit}.items() if value is not None},
            result_count=len(items),
            estimated_tokens=0,
            items=items,
            raw_refs=[item.get("raw_ref", INDEX_REF) for item in items],
        )
        while result.items:
            result.estimated_tokens = _estimated_tokens(result)
            if result.estimated_tokens <= max_tokens:
                break
            result.items.pop()
            result.raw_refs = result.raw_refs[:len(result.items)]
            result.truncated = True
            if "items_tail" not in result.omitted_sections:
                result.omitted_sections.append("items_tail")
            result.result_count = len(result.items)
        result.estimated_tokens = _estimated_tokens(result)
        return result

    def summary(self, symbols: Iterable[str], *, max_tokens: int = MAX_SUMMARY_TOKENS) -> ScenarioMemorySummaryV0:
        if not 100 <= max_tokens <= MAX_SUMMARY_TOKENS:
            raise ValueError(f"max_tokens must be between 100 and {MAX_SUMMARY_TOKENS}")
        requested = list(dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip()))[:12]
        if not requested:
            raise ValueError("at least one symbol is required")
        rows, _, _, errors, raw = self.latest_rows()
        if not raw and errors:
            raise FileNotFoundError(errors[0])
        items: list[ScenarioMemorySymbolSummaryV0] = []
        for symbol in requested:
            matches = [row for row in rows if row.symbol == symbol]
            completed = [row for row in matches if row.outcome_review is not None]
            unresolved = [row for row in matches if row.outcome_review is None or row.outcome_review.future_review_needed]
            lesson_row = next((row for row in matches if row.outcome_review and row.outcome_review.lesson_to_remember), None)
            items.append(ScenarioMemorySymbolSummaryV0(
                symbol=symbol,
                unresolved_count=len(unresolved),
                completed_count=len(completed),
                latest_lesson=(lesson_row.outcome_review.lesson_to_remember[:160] if lesson_row and lesson_row.outcome_review else None),
                latest_review_ref=review_ref(matches[0].review_id, matches[0].revision) if matches else None,
            ))
        result = ScenarioMemorySummaryV0(
            built_ts_ms=self.now_ms_fn(), symbols=requested, items=items, estimated_tokens=0
        )
        while result.items:
            result.estimated_tokens = _estimated_tokens(result)
            if result.estimated_tokens <= max_tokens:
                break
            last = result.items[-1]
            if last.latest_lesson is not None:
                result.items[-1] = last.model_copy(update={"latest_lesson": None})
                result.truncated = True
                if "latest_lessons" not in result.omitted_sections:
                    result.omitted_sections.append("latest_lessons")
            else:
                result.items.pop()
                result.truncated = True
                if "symbol_tail" not in result.omitted_sections:
                    result.omitted_sections.append("symbol_tail")
        result.estimated_tokens = _estimated_tokens(result)
        return result

    def packet_summary(self, symbols: Iterable[str]) -> ActionReviewMemorySummaryV1:
        requested = list(dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip()))[:12]
        rows, _, _, _, _ = self.latest_rows()
        filtered = [row for row in rows if row.symbol in set(requested)]
        # P11 corpus growth must not consume the remaining AgentFeed budget.
        # The packet carries one newest compact row; per-symbol lessons stay on
        # the bounded GET summary/index surfaces.
        selected = filtered[:1]
        memories: list[ActionReviewScenarioMemoryV1] = []
        for row in selected:
            outcome = row.outcome_review
            memories.append(ActionReviewScenarioMemoryV1(
                review_id=row.review_id,
                revision=row.revision,
                symbol=row.symbol,
                proposed_action=row.pre_action_note.proposed_action,
                execution_status=row.execution_note.status,
                expected_scenarios=[item.scenario_id for item in row.pre_action_note.expected_scenarios],
                realized_scenario=outcome.realized_scenario if outcome else None,
                lesson=outcome.lesson_to_remember[:160] if outcome else None,
                unresolved=outcome is None or outcome.future_review_needed,
                packet_ref=row.packet_ref,
                review_ref=review_ref(row.review_id, row.revision),
            ))
        return ActionReviewMemorySummaryV1(
            latest_review_ids_by_symbol={row.symbol: row.review_id for row in selected},
            latest_scenario_memory=memories,
            unresolved_review_count=sum(
                row.outcome_review is None or row.outcome_review.future_review_needed
                for row in filtered
            ),
            unresolved_by_symbol={
                symbol: sum(
                    (row.outcome_review is None or row.outcome_review.future_review_needed)
                    and row.symbol == symbol
                    for row in filtered
                )
                for symbol in requested
            },
            scenario_memory_index_ref=INDEX_REF,
            raw_ledger_ref=LEDGER_REF,
        )

    def _write_index(self, index: ScenarioMemoryIndexV0) -> None:
        encoded = index.model_dump_json(exclude_none=True).encode("utf-8")
        if len(encoded) > MAX_INDEX_BYTES:
            raise ValueError("scenario memory index exceeds byte cap")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{INDEX_FILENAME}.", suffix=".tmp", dir=str(self.index_dir))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temp_path), str(self.index_path))
        finally:
            temp_path.unlink(missing_ok=True)


__all__ = [
    "CalibrationStatisticsV0", "INDEX_FILENAME", "INDEX_REF", "MAX_QUERY_TOKENS",
    "MAX_SUMMARY_TOKENS", "QueryType", "RetentionSummaryV0", "ScenarioMemoryIndexV0",
    "ScenarioMemoryItemV0", "ScenarioMemoryQueryResultV0", "ScenarioMemoryStore",
    "ScenarioMemorySummaryV0",
]
