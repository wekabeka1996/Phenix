"""Tests for P11-B1 Package B: W5 replay summary persistence and WAL integrity integration.

Tests _persist_w5_replay_summary and _check_daily_wal_integrity on StartupTruthOrchestrator
without requiring a full FSM stack.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, call

import pytest
import yaml

from apps.reference.domains.execution_position.state.restore_artifact import (
    ExecutionPositionStartupTruthReplaySummary,
)
from apps.reference.domains.execution_position.state.startup_truth_orchestrator import (
    StartupTruthOrchestrator,
    _W5_REPLAY_SUMMARY_ARTIFACT_PATH,
)
from vfoundation.dr import wal


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
P11_B1_RESTORE_LABELS = (
    "RESTORE:EXECUTION_POSITION_WAL_CHAIN_INTEGRITY_CHECKED",
    "RESTORE:EXECUTION_POSITION_W5_REPLAY_SUMMARY_PERSISTED",
    "RESTORE:EXECUTION_POSITION_W5_REPLAY_SUMMARY_PERSIST_FAILED",
)


@pytest.fixture()
def mock_fsm() -> MagicMock:
    """Minimal FSM mock sufficient for StartupTruthOrchestrator init."""
    fsm = MagicMock()
    # _create_restore_artifact_writer checks isinstance(candidate, Config) → returns None
    # _create_startup_truth_artifact_writer same → None; fine for these unit tests
    return fsm


@pytest.fixture()
def orchestrator(mock_fsm: MagicMock) -> StartupTruthOrchestrator:
    return StartupTruthOrchestrator(mock_fsm)


@pytest.fixture()
def minimal_summary() -> ExecutionPositionStartupTruthReplaySummary:
    return ExecutionPositionStartupTruthReplaySummary(
        attempted=True,
        completed=True,
        scan_state="completed",
        symbols_considered=["BTCUSDT"],
        symbol_count=1,
        records_seen=100,
        records_accepted=42,
    )


def test_p11_b1_restore_labels_are_not_registered_runtime_verbs() -> None:
    registry_path = REPO_ROOT / "apps" / "reference" / \
        "dictionaries" / "verb_registry_v1.yaml"
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry = payload.get("registry")
    assert isinstance(registry, list)

    registered_tokens = {
        f"{entry.get('op')}:{entry.get('verb')}"
        for entry in registry
        if isinstance(entry, dict)
    }

    for label in P11_B1_RESTORE_LABELS:
        assert label not in registered_tokens


def test_p11_b1_restore_labels_are_not_shadow_journal_critical_events() -> None:
    observability_path = REPO_ROOT / "config" / "aurora" / "observability.yaml"
    payload = yaml.safe_load(observability_path.read_text(encoding="utf-8"))
    shadow_journal = payload.get("shadow_journal")
    assert isinstance(shadow_journal, dict)

    critical_events = shadow_journal.get("critical_events")
    assert isinstance(critical_events, list)

    for label in P11_B1_RESTORE_LABELS:
        assert label not in critical_events


# ── _persist_w5_replay_summary ────────────────────────────────────────────────


class TestPersistW5ReplaySummary:
    def test_writes_json_file(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        result = orchestrator._persist_w5_replay_summary(minimal_summary)
        assert result is True
        assert target.exists()

    def test_written_payload_is_valid_json(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        orchestrator._persist_w5_replay_summary(minimal_summary)
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)

    def test_restore_boundary_separation_invariant_preserved(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        orchestrator._persist_w5_replay_summary(minimal_summary)
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["restore_boundary_separation"] == "report_only"
        assert payload["authoritative_mutation_attempted"] is False

    def test_payload_fields_match_summary(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        orchestrator._persist_w5_replay_summary(minimal_summary)
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["completed"] is True
        assert payload["records_seen"] == 100
        assert payload["records_accepted"] == 42
        assert payload["symbols_considered"] == ["BTCUSDT"]

    def test_emits_persisted_observability_event(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        orchestrator._persist_w5_replay_summary(minimal_summary)
        event_calls = [
            str(c) for c in orchestrator._fsm._emit_observability_event.call_args_list
        ]
        assert any("W5_REPLAY_SUMMARY_PERSISTED" in s for s in event_calls)

    def test_none_summary_returns_false(
        self,
        orchestrator: StartupTruthOrchestrator,
    ) -> None:
        result = orchestrator._persist_w5_replay_summary(None)
        assert result is False

    def test_write_failure_returns_false_and_emits_failed_event(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Point at a path where mkdir cannot succeed (file as parent)
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            blocker = pathlib.Path(f.name)
        # Use the file itself as the directory (will fail mkdir)
        bad_path = blocker / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            bad_path,
        )
        result = orchestrator._persist_w5_replay_summary(minimal_summary)
        assert result is False
        event_calls = [
            str(c) for c in orchestrator._fsm._emit_observability_event.call_args_list
        ]
        assert any("W5_REPLAY_SUMMARY_PERSIST_FAILED" in s for s in event_calls)
        blocker.unlink(missing_ok=True)

    def test_atomic_write_via_tmp_rename(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        orchestrator._persist_w5_replay_summary(minimal_summary)
        # .tmp file must NOT linger after successful write
        assert not target.with_suffix(".tmp").exists()


# ── _check_daily_wal_integrity ─────────────────────────────────────────────────


class TestCheckDailyWalIntegrityOrchestrator:
    def test_emits_observability_event_on_ok_chain(
        self,
        orchestrator: StartupTruthOrchestrator,
        tmp_path: pathlib.Path,
    ) -> None:
        wal.set_wal_dir(tmp_path)
        wal.reset()
        wal.append({"verb": "TRADE_EXECUTED", "rid": "r1"})
        orchestrator._check_daily_wal_integrity()
        event_calls = [
            str(c) for c in orchestrator._fsm._emit_observability_event.call_args_list
        ]
        assert any("WAL_CHAIN_INTEGRITY_CHECKED" in s for s in event_calls)
        wal.reset()

    def test_returns_result_with_chain_ok_true(
        self,
        orchestrator: StartupTruthOrchestrator,
        tmp_path: pathlib.Path,
    ) -> None:
        wal.set_wal_dir(tmp_path)
        wal.reset()
        wal.append({"verb": "TRADE_EXECUTED", "rid": "r1"})
        result = orchestrator._check_daily_wal_integrity()
        assert result.chain_ok is True
        assert result.record_count == 1
        wal.reset()

    def test_never_raises_on_empty_wal(
        self,
        orchestrator: StartupTruthOrchestrator,
        tmp_path: pathlib.Path,
    ) -> None:
        wal.set_wal_dir(tmp_path)
        wal.reset()
        result = orchestrator._check_daily_wal_integrity()
        assert result.chain_ok is True
        wal.reset()

    def test_p11_b1_restore_diagnostics_use_observability_hook_only(
        self,
        orchestrator: StartupTruthOrchestrator,
        minimal_summary: ExecutionPositionStartupTruthReplaySummary,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "ops" / "restore" / "w5_replay_startup_summary_v1.json"
        monkeypatch.setattr(
            "apps.reference.domains.execution_position.state.startup_truth_orchestrator._W5_REPLAY_SUMMARY_ARTIFACT_PATH",
            target,
        )
        wal_dir = tmp_path / "wal"
        original_wal_dir = wal.WAL_DIR
        orchestrator._fsm.bus = MagicMock()
        orchestrator._fsm._shadow_journal = MagicMock()

        try:
            wal.set_wal_dir(wal_dir)
            wal.reset()
            wal.append({"verb": "TRADE_EXECUTED", "rid": "r1"})

            assert orchestrator._persist_w5_replay_summary(
                minimal_summary) is True
            result = orchestrator._check_daily_wal_integrity()

            assert result.chain_ok is True
            emitted_labels = [
                call.args[0]
                for call in orchestrator._fsm._emit_observability_event.call_args_list
            ]
            assert "RESTORE:EXECUTION_POSITION_W5_REPLAY_SUMMARY_PERSISTED" in emitted_labels
            assert "RESTORE:EXECUTION_POSITION_WAL_CHAIN_INTEGRITY_CHECKED" in emitted_labels
            orchestrator._fsm.bus.emit.assert_not_called()
            orchestrator._fsm._shadow_journal.record_transition.assert_not_called()
            orchestrator._fsm._shadow_journal.record_bus_emit.assert_not_called()
        finally:
            wal.set_wal_dir(original_wal_dir)
            wal.reset()
