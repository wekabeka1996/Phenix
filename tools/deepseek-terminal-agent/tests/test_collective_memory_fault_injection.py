"""Windows-spawn fault injection for the P41X collective-memory kernel."""
from __future__ import annotations

import json
import multiprocessing
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.collective_memory import (
    CollectiveMemoryStore,
    StaleCollectiveStateError,
    SymbolAuthorityError,
)
from deepseek_terminal_agent.sessions.collective_memory_models import SourceReference
from deepseek_terminal_agent.sessions.coordination_config import (
    CoordinationConfig,
    load_coordination_config,
)
from deepseek_terminal_agent.sessions.models import ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


SPAWN = multiprocessing.get_context("spawn")


def _settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="fault-test-non-secret"))


def _child_store(
    root: str,
    config_payload: dict[str, Any],
    failure_injector=None,
) -> CollectiveMemoryStore:
    settings = _settings()
    sessions = SessionStore(settings, root_dir=root)
    return CollectiveMemoryStore(
        settings,
        root_dir=root,
        config=CoordinationConfig.model_validate(config_payload),
        session_store=sessions,
        failure_injector=failure_injector,
    )


def _exit_after_evidence_append(stage: str, _context: dict[str, Any]) -> None:
    if stage == "after_evidence_append":
        os._exit(91)


def _writer_process(
    root: str,
    session_id: str,
    config_payload: dict[str, Any],
    agent_id: str,
    agent_number: int,
    symbol: str,
    count: int,
    queue,
) -> None:
    try:
        store = _child_store(root, config_payload)
        for index in range(count):
            store.publish_observation(
                session_id=session_id,
                agent_id=agent_id,
                agent_number=agent_number,
                kind="peer_observation",
                summary=f"spawn-{agent_id}-{index}",
                symbol=symbol,
                source_refs=[],
                idempotency_key=f"spawn:{agent_id}:{index}",
            )
        queue.put({"ok": True})
    except BaseException as exc:  # pragma: no cover - child diagnostic
        queue.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _crash_on_state_publish_process(
    root: str,
    session_id: str,
    config_payload: dict[str, Any],
    operation: str,
) -> None:
    store = _child_store(root, config_payload, _exit_after_evidence_append)
    if operation == "publication":
        store.publish_observation(
            session_id=session_id,
            agent_id="api_agent_01",
            agent_number=1,
            kind="peer_observation",
            summary="evidence survives process death",
            symbol="ETHUSDT",
            source_refs=[],
            idempotency_key="crash-after-append",
        )
    elif operation == "cursor":
        state = store.get_state(session_id)
        store.ack_peer_publications(
            session_id=session_id,
            agent_id="cli_agent_01",
            agent_number=2,
            cursor_sequence=state.last_sequence,
            idempotency_key="cursor-crash-after-append",
        )
    raise AssertionError("crash injection did not terminate process")


def _die_while_holding_lock_process(
    root: str,
    session_id: str,
    config_payload: dict[str, Any],
) -> None:
    store = _child_store(root, config_payload)
    with store._session_lock(session_id):
        os._exit(92)


def _interrupted_checkpoint_process(
    root: str,
    session_id: str,
    config_payload: dict[str, Any],
) -> None:
    import deepseek_terminal_agent.sessions.collective_memory as module

    original = module.write_json_atomic

    def interrupted_write(path: Path, payload: dict[str, Any]):
        if path.parent.name == "checkpoints" and "private" not in path.parts:
            temp_path = path.with_name(f".{path.name}.fault.tmp")
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
            os._exit(93)
        return original(path, payload)

    module.write_json_atomic = interrupted_write
    _child_store(root, config_payload).create_checkpoint(session_id)


def _slow_checkpoint_process(
    root: str,
    session_id: str,
    config_payload: dict[str, Any],
    checkpoint_entered,
) -> None:
    import deepseek_terminal_agent.sessions.collective_memory as module

    original = module.write_json_atomic

    def slow_write(path: Path, payload: dict[str, Any]):
        if path.parent.name == "checkpoints" and "private" not in path.parts:
            checkpoint_entered.set()
            time.sleep(0.5)
        return original(path, payload)

    module.write_json_atomic = slow_write
    _child_store(root, config_payload).create_checkpoint(session_id)


def _instruction_writer_process(
    root: str,
    session_id: str,
    config_payload: dict[str, Any],
    checkpoint_entered,
) -> None:
    if not checkpoint_entered.wait(10):
        raise RuntimeError("checkpoint did not enter publish phase")
    store = _child_store(root, config_payload)
    store.ack_instructions(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
        manifest_version="manifest-during-checkpoint",
        idempotency_key="instruction-during-checkpoint",
    )


def _join(process, timeout: float = 20.0) -> int:
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(5)
        pytest.fail(f"spawn process timed out: pid={process.pid}")
    assert process.exitcode is not None
    return process.exitcode


@pytest.fixture
def fault_kernel(tmp_path):
    settings = _settings()
    sessions = SessionStore(settings, root_dir=tmp_path)
    session = sessions.create_session(
        default_profile=ModelProfile(
            profile_id="fault",
            name="Fault Injection",
            model_id="deepseek-v4-pro",
        )
    )
    base = load_coordination_config()
    config = base.model_copy(
        update={
            "memory": base.memory.model_copy(
                update={"lock_timeout_seconds": 3.0, "lock_stale_seconds": 0.2}
            )
        }
    )
    store = CollectiveMemoryStore(
        settings,
        root_dir=tmp_path,
        config=config,
        session_store=sessions,
    )
    store.initialize_session(session.session_id)
    return store, session.session_id, config, tmp_path


def test_true_windows_spawn_two_writers_do_not_corrupt_memory(fault_kernel):
    store, session_id, config, root = fault_kernel
    queue = SPAWN.Queue()
    args = config.model_dump()
    writers = [
        SPAWN.Process(
            target=_writer_process,
            args=(str(root), session_id, args, "api_agent_01", 1, "ETHUSDT", 30, queue),
        ),
        SPAWN.Process(
            target=_writer_process,
            args=(str(root), session_id, args, "cli_agent_01", 2, "XRPUSDT", 30, queue),
        ),
    ]
    for writer in writers:
        writer.start()
    assert [_join(writer) for writer in writers] == [0, 0]
    assert all(queue.get(timeout=3)["ok"] for _ in writers)

    events = store.list_events(session_id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert len({event.event_id for event in events}) == len(events)
    assert len([event for event in events if event.event_type == "PUBLICATION_CREATED"]) == 60


def test_process_death_after_append_replays_missing_state(fault_kernel):
    store, session_id, config, root = fault_kernel
    process = SPAWN.Process(
        target=_crash_on_state_publish_process,
        args=(str(root), session_id, config.model_dump(), "publication"),
    )
    process.start()
    assert _join(process) == 91

    state = store.get_state(session_id)
    events = store.list_events(session_id)
    assert state.last_sequence == events[-1].sequence
    assert any(event.idempotency_key == "crash-after-append" for event in events)
    assert any(item.summary == "evidence survives process death" for item in state.publications)


def test_process_death_while_holding_lock_recovers_stale_lock(fault_kernel):
    store, session_id, config, root = fault_kernel
    process = SPAWN.Process(
        target=_die_while_holding_lock_process,
        args=(str(root), session_id, config.model_dump()),
    )
    process.start()
    assert _join(process) == 92
    time.sleep(config.memory.lock_stale_seconds + 0.1)

    result = store.append_evidence(
        session_id=session_id,
        event_type="LOCK_RECOVERY_PROVEN",
        category="fault_injection",
        payload={"recovered": True},
        idempotency_key="lock-recovery",
    )
    assert result.event.sequence == store.get_state(session_id).last_sequence


def test_partial_final_jsonl_line_is_quarantined_without_losing_next_event(fault_kernel):
    store, session_id, _, _ = fault_kernel
    with store._events_path(session_id).open("ab") as handle:
        handle.write(b'{"event_id":"partial-tail"')
        handle.flush()
        os.fsync(handle.fileno())

    result = store.append_evidence(
        session_id=session_id,
        event_type="AFTER_PARTIAL_TAIL",
        category="fault_injection",
        payload={"accepted": True},
        idempotency_key="after-partial-tail",
    )
    events = store.list_events(session_id)
    assert events[-1].event_id == result.event.event_id
    assert store.get_state(session_id).last_sequence == events[-1].sequence
    assert list(store.quarantine_root.rglob("*.jsonl"))


def test_duplicate_idempotency_after_restart_and_version_conflict(fault_kernel):
    store, session_id, config, root = fault_kernel
    first = store.append_evidence(
        session_id=session_id,
        event_type="RETRY_SAFE_WRITE",
        category="fault_injection",
        payload={"attempt": 1},
        idempotency_key="retry-safe-key",
    )
    restarted = _child_store(str(root), config.model_dump())
    duplicate = restarted.append_evidence(
        session_id=session_id,
        event_type="RETRY_SAFE_WRITE",
        category="fault_injection",
        payload={"attempt": 2},
        idempotency_key="retry-safe-key",
    )
    assert duplicate.deduplicated is True
    assert duplicate.event.event_id == first.event.event_id

    stale_version = restarted.get_state(session_id).version
    restarted.append_evidence(
        session_id=session_id,
        event_type="VERSION_ADVANCED",
        category="fault_injection",
        payload={},
        idempotency_key="version-advance",
    )
    with pytest.raises(StaleCollectiveStateError):
        restarted.append_evidence(
            session_id=session_id,
            event_type="STALE_WRITE",
            category="fault_injection",
            payload={},
            idempotency_key="stale-write",
            expected_version=stale_version,
        )


def test_lease_expiring_during_turn_fails_closed(tmp_path):
    settings = _settings()
    sessions = SessionStore(settings, root_dir=tmp_path)
    session = sessions.create_session(
        default_profile=ModelProfile(profile_id="lease", name="Lease", model_id="deepseek-v4-pro")
    )
    config = load_coordination_config()
    store = CollectiveMemoryStore(settings, root_dir=tmp_path, config=config, session_store=sessions)
    turn_start = datetime.now(timezone.utc)
    store.initialize_session(
        session.session_id,
        now=turn_start - timedelta(seconds=config.symbol_leases.ttl_seconds - 1),
    )
    with pytest.raises(SymbolAuthorityError, match="expired"):
        store.request_command(
            session_id=session.session_id,
            agent_id="api_agent_01",
            agent_number=1,
            command_kind="REQUEST_ORDER",
            symbol="ETHUSDT",
            rationale="lease expired during reasoning turn",
            intent_ref="intent://lease-expired",
            sizing_ref="config://llm_microstructure/execution",
            idempotency_key="lease-expired-during-turn",
            now=turn_start + timedelta(seconds=2),
        )


def test_interrupted_checkpoint_is_not_published_and_recovery_uses_previous(fault_kernel):
    store, session_id, config, root = fault_kernel
    stable = store.create_checkpoint(session_id)
    store.append_evidence(
        session_id=session_id,
        event_type="POST_CHECKPOINT_EVENT",
        category="fault_injection",
        payload={"replay": True},
        idempotency_key="post-checkpoint-event",
    )
    process = SPAWN.Process(
        target=_interrupted_checkpoint_process,
        args=(str(root), session_id, config.model_dump()),
    )
    process.start()
    assert _join(process) == 93

    assert store.latest_checkpoint(session_id).checkpoint_id == stable.checkpoint_id
    report = store.recover_session(session_id)
    assert report.checkpoint_id == stable.checkpoint_id
    assert report.replayed_event_count >= 2


def _make_dispatch_in_doubt(store: CollectiveMemoryStore, session_id: str, command_id: str) -> None:
    store.request_command(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        command_kind="REQUEST_ORDER",
        symbol="ETHUSDT",
        rationale="fault injection dispatch",
        intent_ref=f"intent://{command_id}",
        sizing_ref="config://llm_microstructure/execution",
        command_id=command_id,
        idempotency_key=f"request:{command_id}",
    )
    with pytest.raises(RuntimeError, match="response lost"):
        store.dispatch_command_to_fsm(
            session_id=session_id,
            command_id=command_id,
            fsm_gateway=lambda _command: (_ for _ in ()).throw(RuntimeError("response lost")),
        )


def test_pending_dispatch_in_doubt_never_automatically_redispatches(fault_kernel):
    store, session_id, _, _ = fault_kernel
    _make_dispatch_in_doubt(store, session_id, "cmd-in-doubt")
    report = store.recover_session(session_id)
    assert report.ready is False
    assert report.exchange_reconciliation_status == "required_hook_missing"
    calls = {"count": 0}

    def must_not_run(_command):
        calls["count"] += 1
        raise AssertionError("duplicate dispatch")

    result = store.dispatch_command_to_fsm(
        session_id=session_id,
        command_id="cmd-in-doubt",
        fsm_gateway=must_not_run,
    )
    assert result.deduplicated is True
    assert calls["count"] == 0


def test_reconciliation_not_submitted_makes_explicit_retry_safe(fault_kernel):
    store, session_id, _, _ = fault_kernel
    _make_dispatch_in_doubt(store, session_id, "cmd-not-submitted")
    report = store.recover_session(
        session_id,
        exchange_reconciler=lambda commands: {
            commands[0].command_id: {
                "status": "not_submitted",
                "reason": "venue lookup found no external order",
                "source_refs": [
                    SourceReference(
                        source_id="reconcile-no-order-1",
                        source_type="exchange_reconciliation",
                    ).model_dump()
                ],
            }
        },
    )
    command = store.get_state(session_id).pending_commands["cmd-not-submitted"]
    assert report.ready is True
    assert report.exchange_reconciliation_status == "not_submitted"
    assert command.dispatch_state == "not_dispatched"


def test_reconciliation_externally_submitted_prevents_duplicate(fault_kernel):
    store, session_id, _, _ = fault_kernel
    _make_dispatch_in_doubt(store, session_id, "cmd-external")
    report = store.recover_session(
        session_id,
        exchange_reconciler=lambda commands: {
            commands[0].command_id: {
                "status": "externally_submitted",
                "reason": "venue order located",
                "source_refs": [
                    SourceReference(
                        source_id="testnet-order-ack-1",
                        source_type="exchange_reconciliation",
                    ).model_dump()
                ],
            }
        },
    )
    command = store.get_state(session_id).pending_commands["cmd-external"]
    assert report.ready is True
    assert report.exchange_reconciliation_status == "externally_submitted"
    assert command.dispatch_state == "fsm_accepted"
    assert command.resolution_refs[0].source_id == "testnet-order-ack-1"
    assert store.dispatch_command_to_fsm(
        session_id=session_id,
        command_id="cmd-external",
        fsm_gateway=lambda _command: pytest.fail("must not redispatch"),
    ).deduplicated is True


def test_unverifiable_external_submission_is_explicitly_blocked(fault_kernel):
    store, session_id, _, _ = fault_kernel
    _make_dispatch_in_doubt(store, session_id, "cmd-ambiguous-reconcile")
    report = store.recover_session(
        session_id,
        exchange_reconciler=lambda commands: {
            commands[0].command_id: {
                "status": "externally_submitted",
                "reason": "claimed without a source reference",
                "source_refs": [],
            }
        },
    )
    state = store.get_state(session_id)
    command = state.pending_commands["cmd-ambiguous-reconcile"]
    assert report.ready is False
    assert report.exchange_reconciliation_status == "ambiguous"
    assert state.recovery_state == "blocked"
    assert command.dispatch_state == "dispatch_started"


class _FailStatePublishOnce:
    def __init__(self) -> None:
        self.failed = False

    def __call__(self, stage: str, _context: dict[str, Any]) -> None:
        if stage == "before_state_publish" and not self.failed:
            self.failed = True
            raise OSError("simulated disk write failure")


def test_injectable_disk_failure_recovers_retry_safe(fault_kernel):
    store, session_id, config, root = fault_kernel
    injector = _FailStatePublishOnce()
    failing = CollectiveMemoryStore(
        _settings(),
        root_dir=root,
        config=config,
        session_store=store.session_store,
        failure_injector=injector,
    )
    with pytest.raises(OSError, match="simulated disk write failure"):
        failing.append_evidence(
            session_id=session_id,
            event_type="DISK_FAILURE_WRITE",
            category="fault_injection",
            payload={"durable": True},
            idempotency_key="disk-failure-write",
        )
    restarted = _child_store(str(root), config.model_dump())
    retry = restarted.append_evidence(
        session_id=session_id,
        event_type="DISK_FAILURE_WRITE",
        category="fault_injection",
        payload={"durable": True},
        idempotency_key="disk-failure-write",
    )
    assert retry.deduplicated is True
    assert store.get_state(session_id).last_sequence == store.list_events(session_id)[-1].sequence


def test_instruction_update_waits_for_checkpoint_then_replays(fault_kernel):
    store, session_id, config, root = fault_kernel
    checkpoint_entered = SPAWN.Event()
    checkpoint_process = SPAWN.Process(
        target=_slow_checkpoint_process,
        args=(str(root), session_id, config.model_dump(), checkpoint_entered),
    )
    instruction_process = SPAWN.Process(
        target=_instruction_writer_process,
        args=(str(root), session_id, config.model_dump(), checkpoint_entered),
    )
    checkpoint_process.start()
    instruction_process.start()
    assert _join(checkpoint_process) == 0
    assert _join(instruction_process) == 0

    checkpoint = store.latest_checkpoint(session_id)
    report = store.recover_session(session_id)
    state = store.get_state(session_id)
    assert checkpoint is not None
    assert report.replayed_event_count >= 1
    assert state.instruction_versions["cli_agent_01"].manifest_version == "manifest-during-checkpoint"


def test_peer_publication_cursor_replays_after_process_crash(fault_kernel):
    store, session_id, config, root = fault_kernel
    publication = store.publish_observation(
        session_id=session_id,
        agent_id="api_agent_01",
        agent_number=1,
        kind="peer_observation",
        summary="cursor crash fact",
        symbol="ETHUSDT",
        source_refs=[],
        idempotency_key="cursor-crash-publication",
    )
    process = SPAWN.Process(
        target=_crash_on_state_publish_process,
        args=(str(root), session_id, config.model_dump(), "cursor"),
    )
    process.start()
    assert _join(process) == 91

    state = store.get_state(session_id)
    assert state.publication_cursors["cli_agent_01"].cursor_sequence >= publication.event.sequence
    assert store.get_peer_publications(
        session_id=session_id,
        agent_id="cli_agent_01",
        agent_number=2,
    ) == []
