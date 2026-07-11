"""Single-writer append-only memory kernel for agent/session records.

The JSONL ledger is authoritative. Summaries and carryover payloads are
deterministic read models and are never written as a second source of truth.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .collective_memory_models import (
    CanonicalMemoryRecord,
    CanonicalMemorySummary,
    SourceReference,
)
from .coordination_config import CoordinationConfig
from .persistence import append_jsonl_record


class DuplicateMemoryRecordError(ValueError):
    pass


class MemoryIntegrityError(RuntimeError):
    pass


class CanonicalMemoryStore:
    """The only canonical writer for durable agent/session memory records."""

    DIRECTORY_NAME = "canonical_memory"
    RECORDS_NAME = "records.jsonl"

    def __init__(self, *, storage_root: str | Path, config: CoordinationConfig) -> None:
        raw_root = str(storage_root).strip()
        if not raw_root:
            raise ValueError("storage_root must be explicit")
        self.storage_root = Path(storage_root)
        if not self.storage_root.is_absolute():
            raise ValueError("storage_root must be an absolute path")
        self.config = config

    def append(self, record: CanonicalMemoryRecord) -> CanonicalMemoryRecord:
        self._validate_identity(record.agent_id, record.agent_number)
        path = self._records_path(record.session_id)
        existing = self.read(record.session_id)
        if any(item.record_id == record.record_id for item in existing):
            raise DuplicateMemoryRecordError(f"duplicate record_id: {record.record_id}")
        expected_sequence = len(existing) + 1
        if record.sequence != expected_sequence:
            raise MemoryIntegrityError(
                f"sequence must be {expected_sequence}, received {record.sequence}"
            )
        append_jsonl_record(path, record.model_dump())
        return record

    def read(self, session_id: str) -> list[CanonicalMemoryRecord]:
        normalized_session = self._validate_session_id(session_id)
        path = self._records_path(normalized_session)
        if not path.exists():
            return []
        records: list[CanonicalMemoryRecord] = []
        seen_ids: set[str] = set()
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
                record = CanonicalMemoryRecord.model_validate(payload)
            except (json.JSONDecodeError, ValueError) as exc:
                raise MemoryIntegrityError(
                    f"invalid canonical memory record at line {line_number}: {exc}"
                ) from exc
            if record.session_id != normalized_session:
                raise MemoryIntegrityError(
                    f"record session mismatch at line {line_number}"
                )
            self._validate_identity(record.agent_id, record.agent_number)
            if record.record_id in seen_ids:
                raise MemoryIntegrityError(
                    f"duplicate record_id in ledger: {record.record_id}"
                )
            expected_sequence = len(records) + 1
            if record.sequence != expected_sequence:
                raise MemoryIntegrityError(
                    f"non-monotonic sequence at line {line_number}: "
                    f"expected {expected_sequence}, received {record.sequence}"
                )
            seen_ids.add(record.record_id)
            records.append(record)
        return records

    def summarize(self, session_id: str) -> CanonicalMemorySummary:
        records = self.read(session_id)
        instruction_versions: dict[str, str] = {}
        event_ids: list[str] = []
        command_ids: list[str] = []
        source_refs: list[SourceReference] = []
        seen_events: set[str] = set()
        seen_commands: set[str] = set()
        seen_sources: set[tuple[str, str, int | None, str | None]] = set()

        for record in records:
            instruction_versions[record.agent_id] = record.instruction_version
            self._extend_unique(event_ids, seen_events, record.event_ids)
            self._extend_unique(command_ids, seen_commands, record.command_ids)
            for source_ref in record.source_refs:
                key = (
                    source_ref.source_id,
                    source_ref.source_type,
                    source_ref.sequence,
                    source_ref.event_id,
                )
                if key not in seen_sources:
                    seen_sources.add(key)
                    source_refs.append(source_ref)

        return CanonicalMemorySummary(
            session_id=self._validate_session_id(session_id),
            record_count=len(records),
            first_sequence=records[0].sequence if records else None,
            last_sequence=records[-1].sequence if records else None,
            record_ids=[record.record_id for record in records],
            instruction_versions=dict(sorted(instruction_versions.items())),
            event_ids=event_ids,
            command_ids=command_ids,
            source_refs=source_refs,
        )

    def carryover(self, session_id: str) -> dict[str, object]:
        """Return a deterministic, source-referenced carryover read model."""

        summary = self.summarize(session_id)
        return summary.model_dump(mode="json")

    def _records_path(self, session_id: str) -> Path:
        normalized = self._validate_session_id(session_id)
        return self.storage_root / normalized / self.DIRECTORY_NAME / self.RECORDS_NAME

    def _validate_identity(self, agent_id: str, agent_number: int) -> None:
        normalized_agent = str(agent_id).strip()
        if not normalized_agent:
            raise ValueError("agent_id is required")
        configured = self.config.agent(normalized_agent)
        if configured.agent_number != agent_number:
            raise ValueError("agent_number does not match configured identity")

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        normalized = str(session_id).strip()
        if not normalized:
            raise ValueError("session_id is required")
        if normalized in {".", ".."} or Path(normalized).name != normalized:
            raise ValueError("session_id must be a path-safe identifier")
        return normalized

    @staticmethod
    def _extend_unique(target: list[str], seen: set[str], values: Iterable[str]) -> None:
        for value in values:
            if value not in seen:
                seen.add(value)
                target.append(value)
