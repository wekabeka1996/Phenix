from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.collective_memory import (
    CanonicalMemoryStore,
    DuplicateMemoryRecordError,
)
from deepseek_terminal_agent.sessions.collective_memory_models import (
    CanonicalMemoryRecord,
    SourceReference,
)
from deepseek_terminal_agent.sessions.coordination_config import load_coordination_config


def _store(tmp_path: Path) -> CanonicalMemoryStore:
    return CanonicalMemoryStore(
        storage_root=tmp_path.resolve(),
        config=load_coordination_config(),
    )


def _record(
    record_id: str,
    sequence: int,
    *,
    kind: str = "decision",
    agent_id: str = "api_agent_01",
    agent_number: int = 1,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        record_id=record_id,
        session_id="session-1",
        agent_id=agent_id,
        agent_number=agent_number,
        sequence=sequence,
        kind=kind,
        created_at=f"2026-07-11T00:00:0{sequence}+00:00",
        content=f"memory {sequence}",
        instruction_version=f"manifest-v{sequence}",
        event_ids=[f"event-{sequence}"],
        command_ids=[f"command-{sequence}"],
        source_refs=[
            SourceReference(
                source_id=f"source-{sequence}",
                source_type="arena_event",
                sequence=sequence,
                event_id=f"event-{sequence}",
                created_at=f"2026-07-11T00:00:0{sequence}+00:00",
            )
        ],
    )


def test_append_and_ordered_read_preserve_event_and_command_refs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(_record("record-1", 1))
    store.append(_record("record-2", 2, kind="reflection"))

    records = store.read("session-1")

    assert [record.record_id for record in records] == ["record-1", "record-2"]
    assert records[1].event_ids == ["event-2"]
    assert records[1].command_ids == ["command-2"]


def test_duplicate_id_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(_record("record-1", 1))

    with pytest.raises(DuplicateMemoryRecordError):
        store.append(_record("record-1", 2))


def test_missing_or_mismatched_identity_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _record("record-1", 1, agent_id="")
    with pytest.raises(ValueError, match="agent_number"):
        _store(tmp_path).append(_record("record-1", 1, agent_number=2))


def test_restart_reopens_authoritative_ledger(tmp_path: Path) -> None:
    first = _store(tmp_path)
    first.append(_record("record-1", 1))

    reopened = _store(tmp_path)

    assert reopened.read("session-1") == first.read("session-1")


def test_summary_and_carryover_are_deterministic(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(_record("record-1", 1))
    store.append(_record("record-2", 2, kind="instruction_ack"))

    first_summary = store.summarize("session-1")
    second_summary = store.summarize("session-1")

    assert first_summary == second_summary
    assert store.carryover("session-1") == store.carryover("session-1")
    assert first_summary.event_ids == ["event-1", "event-2"]
    assert first_summary.command_ids == ["command-1", "command-2"]
    assert [ref.source_id for ref in first_summary.source_refs] == [
        "source-1",
        "source-2",
    ]


def test_storage_and_config_are_explicit_and_no_dual_writer_is_created(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        CanonicalMemoryStore()  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="absolute"):
        CanonicalMemoryStore(
            storage_root=Path("relative-memory"),
            config=load_coordination_config(),
        )

    store = _store(tmp_path)
    assert set(vars(store)) == {"storage_root", "config"}
    assert not hasattr(store, "session_store")
    assert not hasattr(store, "agent_memory_lifecycle")
