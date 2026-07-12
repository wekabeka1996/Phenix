"""Runtime adapter that routes agent memory writes to one canonical store."""
from __future__ import annotations

from typing import Any

from .collective_memory import CanonicalMemoryStore, DuplicateMemoryRecordError
from .collective_memory_models import (
    CanonicalMemoryKind,
    CanonicalMemoryRecord,
    SourceReference,
)


class CanonicalMemoryRuntime:
    def __init__(self, *, store: CanonicalMemoryStore) -> None:
        self.store = store

    def attach_identity(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        instruction_version: str,
    ) -> dict[str, Any]:
        self._require(instruction_version, "instruction_version")
        self.store.validate_identity(agent_id, agent_number)
        return self.read_memory(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )

    def append_instruction_ack(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        event_id: str,
        instruction_version: str,
        created_at: str,
    ) -> dict[str, Any]:
        return self._append(
            record_id=f"instruction-ack:{agent_id}:{self._require(event_id, 'event_id')}",
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            kind="instruction_ack",
            created_at=created_at,
            content=f"Instructions acknowledged: {instruction_version}",
            instruction_version=instruction_version,
            event_ids=[event_id],
            command_ids=[],
        )

    def append_rationale_event(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        event_id: str,
        command_id: str,
        rationale: str,
        instruction_version: str,
        created_at: str,
    ) -> dict[str, Any]:
        event = self._require(event_id, "event_id")
        command = self._require(command_id, "command_id")
        return self._append(
            record_id=f"rationale:{agent_id}:{event}:{command}",
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            kind="reflection",
            created_at=created_at,
            content=self._require(rationale, "rationale"),
            instruction_version=instruction_version,
            event_ids=[event],
            command_ids=[command],
        )

    def append_fsm_decision(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        event_id: str,
        command_id: str,
        accepted: bool,
        reason: str,
        instruction_version: str,
        created_at: str,
    ) -> dict[str, Any]:
        event = self._require(event_id, "event_id")
        command = self._require(command_id, "command_id")
        detail = self._require(reason, "reason")
        return self._append(
            record_id=f"fsm-decision:{agent_id}:{event}:{command}",
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            kind="decision",
            created_at=created_at,
            content=f"FSM handoff {'accepted' if accepted else 'rejected'}: {detail}",
            instruction_version=instruction_version,
            event_ids=[event],
            command_ids=[command],
        )

    def read_memory(
        self, *, session_id: str, agent_id: str, agent_number: int
    ) -> dict[str, Any]:
        self.store.validate_identity(agent_id, agent_number)
        records = [
            record
            for record in self.store.read(session_id)
            if record.agent_id == agent_id and record.agent_number == agent_number
        ]
        return self._view(session_id, agent_id, agent_number, records)

    def finalize_session(
        self, *, session_id: str, agent_id: str, agent_number: int
    ) -> dict[str, Any]:
        memory = self.read_memory(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )
        return {
            "memory": memory,
            "summary": memory["summary"],
            "carryover": memory["summary"],
        }

    def _append(
        self,
        *,
        record_id: str,
        session_id: str,
        agent_id: str,
        agent_number: int,
        kind: CanonicalMemoryKind,
        created_at: str,
        content: str,
        instruction_version: str,
        event_ids: list[str],
        command_ids: list[str],
    ) -> dict[str, Any]:
        self._require(session_id, "session_id")
        self._require(agent_id, "agent_id")
        self._require(instruction_version, "instruction_version")
        self._require(created_at, "created_at")
        self.store.validate_identity(agent_id, agent_number)
        existing = self.store.read(session_id)
        duplicate = next((item for item in existing if item.record_id == record_id), None)
        if duplicate is not None:
            expected = {
                "session_id": session_id,
                "agent_id": agent_id,
                "agent_number": agent_number,
                "kind": kind,
                "created_at": created_at,
                "content": content,
                "instruction_version": instruction_version,
                "event_ids": event_ids,
                "command_ids": command_ids,
            }
            actual = {key: getattr(duplicate, key) for key in expected}
            if actual != expected:
                raise DuplicateMemoryRecordError(
                    f"conflicting duplicate record_id: {record_id}"
                )
            return self.read_memory(
                session_id=session_id,
                agent_id=agent_id,
                agent_number=agent_number,
            )
        record = CanonicalMemoryRecord(
            record_id=record_id,
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            sequence=len(existing) + 1,
            kind=kind,
            created_at=created_at,
            content=content,
            instruction_version=instruction_version,
            event_ids=event_ids,
            command_ids=command_ids,
            source_refs=[
                SourceReference(
                    source_id=event_id,
                    source_type="session_event",
                    event_id=event_id,
                    created_at=created_at,
                )
                for event_id in event_ids
            ],
        )
        self.store.append(record)
        return self.read_memory(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )

    @staticmethod
    def _view(
        session_id: str,
        agent_id: str,
        agent_number: int,
        records: list[CanonicalMemoryRecord],
    ) -> dict[str, Any]:
        event_ids = list(dict.fromkeys(item for record in records for item in record.event_ids))
        command_ids = list(
            dict.fromkeys(item for record in records for item in record.command_ids)
        )
        instruction_version = records[-1].instruction_version if records else None
        summary = {
            "session_id": session_id,
            "agent_id": agent_id,
            "agent_number": agent_number,
            "record_count": len(records),
            "record_ids": [record.record_id for record in records],
            "event_ids": event_ids,
            "command_ids": command_ids,
            "instruction_version": instruction_version,
        }
        return {
            "session_id": session_id,
            "agent_id": agent_id,
            "agent_number": agent_number,
            "records": [record.model_dump(mode="json") for record in records],
            "summary": summary,
        }

    @staticmethod
    def _require(value: str, field: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError(f"{field} is required")
        return cleaned
