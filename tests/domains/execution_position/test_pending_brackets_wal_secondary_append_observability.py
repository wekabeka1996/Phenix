"""
tests/domains/execution_position/test_pending_brackets_wal_secondary_append_observability.py

METAFSM2_P12_D4 — Secondary append failure observability hardening tests.

Verifies:
A. Success path  — _append_daily_wal_record returns True, counter unchanged
B. None-return   — returns False, WARNING emitted with enriched fields, counter increments
C. Exception     — returns False, WARNING includes exception type/msg, counter increments
D. Dedicated authority — write_pending_brackets_stored/cleared succeed even when
                         secondary append fails; no exception propagated to caller
E. Rehydration   — existing rehydration contract unchanged; dedicated corruption
                   policy and shared best-effort policy unchanged
F. Diagnostic artifact — artifact row written on failure; includes authority=diagnostic_only;
                         artifact write failure is non-fatal
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_counter_and_wal_dir(tmp_path, monkeypatch):
    """Redirect WAL to tmp dir and reset the failure counter before each test."""
    wal_dir = tmp_path / "wal"
    wal_dir.mkdir()

    from vfoundation import config as vf_config
    vf_config.config.wal_dir = wal_dir

    from vfoundation.dr import wal as wal_mod
    wal_mod.set_wal_dir(wal_dir)

    # Reset D4 counter for test isolation
    from apps.reference.domains.execution_position.flows.manage import (
        pending_brackets_wal as pb_wal,
    )
    pb_wal._reset_secondary_daily_append_failure_count_for_tests()

    yield wal_dir


@pytest.fixture
def pb_wal():
    from apps.reference.domains.execution_position.flows.manage import (
        pending_brackets_wal,
    )
    return pending_brackets_wal


@pytest.fixture
def minimal_stored_record():
    """Minimal valid record dict as produced by write_pending_brackets_stored."""
    return {
        "op": "EVT",
        "verb": "PENDING_BRACKETS_STORED",
        "src": "execution_position",
        "dst": "wal",
        "rid": "aurora_BTCUSDT_111111111",
        "ts": 1781473806000,
        "why": "limit_entry_deferred_brackets:BTCUSDT",
        "pld": {
            "ts_ms": 1781473806000,
            "entry_order_id": "55001234",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "sl": 60000.0,
            "tp": 62000.0,
            "qty": 0.1,
            "rid": "aurora_BTCUSDT_111111111",
            "idem_key": "aabb-ccdd-eeff-0011",
            "tick_size": 0.01,
        },
    }


@pytest.fixture
def minimal_cleared_record():
    """Minimal valid record dict as produced by write_pending_brackets_cleared."""
    return {
        "op": "EVT",
        "verb": "PENDING_BRACKETS_CLEARED",
        "src": "execution_position",
        "dst": "wal",
        "rid": "clear:55001234:1781474000000",
        "ts": 1781474000000,
        "why": "brackets_cleared:filled",
        "pld": {
            "ts_ms": 1781474000000,
            "entry_order_id": "55001234",
            "symbol": "BTCUSDT",
            "reason": "filled",
        },
    }


# ===========================================================================
# A. Success path
# ===========================================================================

class TestSuccessPath:

    def test_returns_true_on_successful_append(self, pb_wal, minimal_stored_record):
        """_append_daily_wal_record returns True when wal.append returns a hash."""
        result = pb_wal._append_daily_wal_record(minimal_stored_record)
        assert result is True, "Expected True on successful wal.append"

    def test_counter_unchanged_on_success(self, pb_wal, minimal_stored_record):
        """Failure counter must NOT increment on a successful append."""
        pb_wal._append_daily_wal_record(minimal_stored_record)
        count = pb_wal.get_secondary_daily_append_failure_count()
        assert count == 0, f"Counter should be 0 after success, got {count}"

    def test_returns_true_for_cleared_record(self, pb_wal, minimal_cleared_record):
        """Success path works for CLEARED verb too."""
        result = pb_wal._append_daily_wal_record(minimal_cleared_record)
        assert result is True

    def test_no_warning_logged_on_success(self, pb_wal, minimal_stored_record, caplog):
        """No WARNING must be emitted on a successful secondary append."""
        with caplog.at_level(logging.WARNING):
            pb_wal._append_daily_wal_record(minimal_stored_record)
        warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert all(
            "pending_brackets_secondary_daily_append_failed" not in m
            for m in warning_msgs
        ), f"Unexpected failure WARNING on success path: {warning_msgs}"


# ===========================================================================
# B. None-return failure path
# ===========================================================================

class TestNoneReturnFailure:

    def test_returns_false_when_wal_append_returns_none(
        self, pb_wal, minimal_stored_record
    ):
        """_append_daily_wal_record returns False when wal.append returns None."""
        with patch.object(pb_wal.wal, "append", return_value=None):
            result = pb_wal._append_daily_wal_record(minimal_stored_record)
        assert result is False, "Expected False when wal.append returns None"

    def test_counter_increments_on_none_return(self, pb_wal, minimal_stored_record):
        """Failure counter increments when wal.append returns None."""
        with patch.object(pb_wal.wal, "append", return_value=None):
            pb_wal._append_daily_wal_record(minimal_stored_record)
        assert pb_wal.get_secondary_daily_append_failure_count() == 1

    def test_counter_increments_multiple_times(self, pb_wal, minimal_stored_record):
        """Counter accumulates correctly across multiple failures."""
        with patch.object(pb_wal.wal, "append", return_value=None):
            pb_wal._append_daily_wal_record(minimal_stored_record)
            pb_wal._append_daily_wal_record(minimal_stored_record)
            pb_wal._append_daily_wal_record(minimal_stored_record)
        assert pb_wal.get_secondary_daily_append_failure_count() == 3

    def test_warning_emitted_on_none_return(
        self, pb_wal, minimal_stored_record, caplog
    ):
        """WARNING log is emitted when wal.append returns None."""
        with patch.object(pb_wal.wal, "append", return_value=None):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        assert any(
            "pending_brackets_secondary_daily_append_failed" in r.message
            for r in caplog.records
        ), "Expected WARNING with pending_brackets_secondary_daily_append_failed marker"

    def test_warning_includes_verb(self, pb_wal, minimal_stored_record, caplog):
        with patch.object(pb_wal.wal, "append", return_value=None):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "PENDING_BRACKETS_STORED" in warn_msgs, "WARNING must include verb"

    def test_warning_includes_symbol(self, pb_wal, minimal_stored_record, caplog):
        with patch.object(pb_wal.wal, "append", return_value=None):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "BTCUSDT" in warn_msgs, "WARNING must include symbol"

    def test_warning_includes_entry_order_id(
        self, pb_wal, minimal_stored_record, caplog
    ):
        with patch.object(pb_wal.wal, "append", return_value=None):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "55001234" in warn_msgs, "WARNING must include entry_order_id"

    def test_warning_includes_rid(self, pb_wal, minimal_stored_record, caplog):
        with patch.object(pb_wal.wal, "append", return_value=None):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "aurora_BTCUSDT_111111111" in warn_msgs, "WARNING must include rid"


# ===========================================================================
# C. Exception failure path
# ===========================================================================

class TestExceptionFailure:

    def test_returns_false_when_wal_append_raises(
        self, pb_wal, minimal_stored_record
    ):
        """_append_daily_wal_record returns False when wal.append raises."""
        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("lock timeout")
        ):
            result = pb_wal._append_daily_wal_record(minimal_stored_record)
        assert result is False, "Expected False when wal.append raises"

    def test_no_exception_propagated_to_caller_on_wal_raise(
        self, pb_wal, minimal_stored_record
    ):
        """Exception from wal.append must NOT propagate to _append_daily_wal_record caller."""
        with patch.object(
            pb_wal.wal, "append", side_effect=OSError("permission denied")
        ):
            # Must not raise
            result = pb_wal._append_daily_wal_record(minimal_stored_record)
        assert result is False

    def test_counter_increments_on_exception(self, pb_wal, minimal_stored_record):
        """Failure counter increments when wal.append raises."""
        with patch.object(
            pb_wal.wal, "append", side_effect=TimeoutError("wal lock timed out")
        ):
            pb_wal._append_daily_wal_record(minimal_stored_record)
        assert pb_wal.get_secondary_daily_append_failure_count() == 1

    def test_warning_emitted_on_exception(
        self, pb_wal, minimal_stored_record, caplog
    ):
        """WARNING is emitted when wal.append raises."""
        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("daily wal offline")
        ):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        assert any(
            "pending_brackets_secondary_daily_append_failed" in r.message
            for r in caplog.records
        )

    def test_warning_includes_exception_type(
        self, pb_wal, minimal_stored_record, caplog
    ):
        """WARNING includes exception type name."""
        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("daily wal offline")
        ):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "RuntimeError" in warn_msgs, "WARNING must include exception type"

    def test_warning_includes_exception_message(
        self, pb_wal, minimal_stored_record, caplog
    ):
        """WARNING includes exception message text."""
        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("daily wal offline")
        ):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "daily wal offline" in warn_msgs, "WARNING must include exception message"

    def test_warning_includes_symbol_on_exception(
        self, pb_wal, minimal_stored_record, caplog
    ):
        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("fail")
        ):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "BTCUSDT" in warn_msgs

    def test_warning_includes_rid_on_exception(
        self, pb_wal, minimal_stored_record, caplog
    ):
        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("fail")
        ):
            with caplog.at_level(logging.WARNING):
                pb_wal._append_daily_wal_record(minimal_stored_record)
        warn_msgs = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "aurora_BTCUSDT_111111111" in warn_msgs


# ===========================================================================
# D. Dedicated WAL authority preserved
# ===========================================================================

class TestDedicatedAuthorityPreserved:

    def test_write_stored_dedicated_survives_secondary_exception(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """write_pending_brackets_stored writes to dedicated WAL even if secondary raises."""
        wal_dir = _reset_counter_and_wal_dir
        dedicated_path = wal_dir / pb_wal.PENDING_BRACKETS_WAL_FILENAME

        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("daily wal offline")
        ):
            pb_wal.write_pending_brackets_stored(
                entry_order_id="EOID-D4-001",
                symbol="XRPUSDT",
                side="BUY",
                sl=0.50,
                tp=0.55,
                qty=1000.0,
                rid="rid-d4-001",
                idem_key="idem-d4-001",
                tick_size=0.0001,
            )

        assert dedicated_path.exists(), "Dedicated WAL must be written"
        records = [
            json.loads(line)
            for line in dedicated_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(records) == 1
        assert records[0]["verb"] == "PENDING_BRACKETS_STORED"
        assert records[0]["pld"]["entry_order_id"] == "EOID-D4-001"

    def test_write_cleared_dedicated_survives_secondary_exception(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """write_pending_brackets_cleared writes dedicated WAL even if secondary raises."""
        wal_dir = _reset_counter_and_wal_dir
        dedicated_path = wal_dir / pb_wal.PENDING_BRACKETS_WAL_FILENAME

        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("daily wal offline")
        ):
            pb_wal.write_pending_brackets_cleared(
                entry_order_id="EOID-D4-001",
                symbol="XRPUSDT",
                reason="cancelled",
                rid="clear-d4-001",
            )

        records = [
            json.loads(line)
            for line in dedicated_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(records) == 1
        assert records[0]["verb"] == "PENDING_BRACKETS_CLEARED"
        assert records[0]["pld"]["reason"] == "cancelled"

    def test_no_exception_propagated_from_write_stored_on_secondary_fail(
        self, pb_wal
    ):
        """write_pending_brackets_stored must not raise when secondary append fails."""
        with patch.object(
            pb_wal.wal, "append", side_effect=OSError("permission denied")
        ):
            # Must not raise
            pb_wal.write_pending_brackets_stored(
                entry_order_id="EOID-D4-002",
                symbol="BNBUSDT",
                side="SELL",
                sl=590.0,
                tp=580.0,
                qty=1.0,
                rid="rid-d4-002",
                idem_key="idem-d4-002",
                tick_size=0.01,
            )

    def test_no_exception_propagated_from_write_cleared_on_secondary_fail(
        self, pb_wal
    ):
        """write_pending_brackets_cleared must not raise when secondary append fails."""
        with patch.object(
            pb_wal.wal, "append", side_effect=OSError("permission denied")
        ):
            pb_wal.write_pending_brackets_cleared(
                entry_order_id="EOID-D4-002",
                symbol="BNBUSDT",
                reason="filled",
            )

    def test_counter_accessible_via_public_accessor(self, pb_wal):
        """get_secondary_daily_append_failure_count() is publicly callable and returns int."""
        count = pb_wal.get_secondary_daily_append_failure_count()
        assert isinstance(count, int)
        assert count == 0  # Reset by fixture


# ===========================================================================
# E. Rehydration contract unchanged
# ===========================================================================

class TestRehydrationUnchanged:

    def test_rehydration_reads_dedicated_when_secondary_never_written(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """Even with secondary append fully broken, rehydration reads dedicated WAL."""
        wal_dir = _reset_counter_and_wal_dir

        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("daily wal dead")
        ):
            pb_wal.write_pending_brackets_stored(
                entry_order_id="EOID-REHY-001",
                symbol="SOLUSDT",
                side="BUY",
                sl=100.0,
                tp=110.0,
                qty=5.0,
                rid="rid-rehy-d4-001",
                idem_key="idem-rehy-d4-001",
                tick_size=0.01,
            )

        restored = pb_wal.read_pending_brackets_from_wal()
        assert "EOID-REHY-001" in restored, "Dedicated WAL must be rehydrated"
        assert restored["EOID-REHY-001"]["symbol"] == "SOLUSDT"

    def test_rehydration_deduplicated_when_secondary_succeeds(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """When both writes succeed, rehydration deduplicates correctly."""
        pb_wal.write_pending_brackets_stored(
            entry_order_id="EOID-DEDUP-D4",
            symbol="BTCUSDT",
            side="BUY",
            sl=60000.0,
            tp=62000.0,
            qty=0.01,
            rid="rid-dedup-d4",
            idem_key="idem-dedup-d4",
            tick_size=0.01,
        )
        restored = pb_wal.read_pending_brackets_from_wal()
        assert "EOID-DEDUP-D4" in restored
        # Only one entry despite two WAL writes (dedicated + shared)
        assert restored["EOID-DEDUP-D4"]["symbol"] == "BTCUSDT"

    def test_dedicated_corruption_still_raises_critical_error(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """CriticalStartupError must still be raised on dedicated WAL corruption."""
        wal_dir = _reset_counter_and_wal_dir
        ded_path = wal_dir / pb_wal.PENDING_BRACKETS_WAL_FILENAME
        # Write a corrupt line to the dedicated WAL
        ded_path.write_text(
            json.dumps({"verb": "PENDING_BRACKETS_STORED",
                        "pld": {"entry_order_id": "x"}}) + "\n"
            + "{corrupt line!!!\n",
            encoding="utf-8",
        )
        with pytest.raises(pb_wal.CriticalStartupError, match="pending brackets WAL corruption"):
            pb_wal.read_pending_brackets_from_wal()

    def test_shared_corruption_best_effort_does_not_raise(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """Corrupt shared daily WAL must not raise on rehydration (best-effort)."""
        import time as _time
        wal_dir = _reset_counter_and_wal_dir
        shared_path = wal_dir / f"{_time.strftime('%Y-%m-%d')}.jsonl"
        shared_path.write_text(
            json.dumps({"verb": "UNRELATED_VERB", "pld": {}}) + "\n"
            + "{corrupt!!!\n"
            + json.dumps({"verb": "PENDING_BRACKETS_STORED",
                          "pld": {"entry_order_id": "GHOST-001",
                                  "symbol": "BTCUSDT",
                                  "side": "BUY",
                                  "sl": 1.0, "tp": 2.0, "qty": 1.0,
                                  "rid": "r", "idem_key": "k",
                                  "tick_size": 0.01}}) + "\n",
            encoding="utf-8",
        )
        # Must not raise
        restored = pb_wal.read_pending_brackets_from_wal()
        # The corrupt shared file should trigger CriticalStartupError
        # because best-effort for shared means it catches CriticalStartupError
        # Actually re-raises CriticalStartupError so this tests that
        # a corrupt shared file with PB verb raises
        # Per code: fail_closed_on_any_corrupt_line=False for shared
        # so corrupt lines in shared that are NOT PB verbs are skipped
        # but if a PB line is corrupt it raises CriticalStartupError
        # which is then re-raised. Let's check actual behavior.
        # The corrupt line "{corrupt!!!" doesn't contain PB verb token,
        # so it's skipped (best-effort). GHOST-001 should appear.
        assert "GHOST-001" in restored


# ===========================================================================
# F. Diagnostic artifact
# ===========================================================================

class TestDiagnosticArtifact:

    def test_artifact_file_created_on_none_return_failure(
        self, pb_wal, _reset_counter_and_wal_dir, minimal_stored_record
    ):
        """Diagnostic artifact file is created when wal.append returns None."""
        wal_dir = _reset_counter_and_wal_dir
        artifact_path = wal_dir / pb_wal.SECONDARY_APPEND_FAILURES_FILENAME

        with patch.object(pb_wal.wal, "append", return_value=None):
            pb_wal._append_daily_wal_record(minimal_stored_record)

        assert artifact_path.exists(), "Diagnostic artifact file must be created on failure"

    def test_artifact_row_has_diagnostic_only_authority(
        self, pb_wal, _reset_counter_and_wal_dir, minimal_stored_record
    ):
        """Artifact row must have authority=diagnostic_only."""
        wal_dir = _reset_counter_and_wal_dir
        artifact_path = wal_dir / pb_wal.SECONDARY_APPEND_FAILURES_FILENAME

        with patch.object(pb_wal.wal, "append", return_value=None):
            pb_wal._append_daily_wal_record(minimal_stored_record)

        rows = [json.loads(l) for l in artifact_path.read_text().splitlines() if l.strip()]
        assert rows, "Artifact must have at least one row"
        assert rows[0]["authority"] == "diagnostic_only", (
            f"authority must be 'diagnostic_only', got {rows[0].get('authority')!r}"
        )

    def test_artifact_row_contains_required_fields(
        self, pb_wal, _reset_counter_and_wal_dir, minimal_stored_record
    ):
        """Artifact row contains verb, symbol, entry_order_id, rid, source_component."""
        wal_dir = _reset_counter_and_wal_dir
        artifact_path = wal_dir / pb_wal.SECONDARY_APPEND_FAILURES_FILENAME

        with patch.object(pb_wal.wal, "append", return_value=None):
            pb_wal._append_daily_wal_record(minimal_stored_record)

        row = json.loads(artifact_path.read_text().splitlines()[0])
        assert row["verb"] == "PENDING_BRACKETS_STORED"
        assert row["symbol"] == "BTCUSDT"
        assert row["entry_order_id"] == "55001234"
        assert row["rid"] == "aurora_BTCUSDT_111111111"
        assert row["source_component"] == "execution_position.pending_brackets_wal"
        assert row["wal_append_result"] == "none"

    def test_artifact_row_on_exception_includes_exception_type(
        self, pb_wal, _reset_counter_and_wal_dir, minimal_stored_record
    ):
        """Artifact row on exception path includes exception_type and exception_message."""
        wal_dir = _reset_counter_and_wal_dir
        artifact_path = wal_dir / pb_wal.SECONDARY_APPEND_FAILURES_FILENAME

        with patch.object(
            pb_wal.wal, "append", side_effect=RuntimeError("lock timed out")
        ):
            pb_wal._append_daily_wal_record(minimal_stored_record)

        row = json.loads(artifact_path.read_text().splitlines()[0])
        assert row["wal_append_result"] == "exception"
        assert row["exception_type"] == "RuntimeError"
        assert "lock timed out" in (row["exception_message"] or "")

    def test_artifact_appends_multiple_rows(
        self, pb_wal, _reset_counter_and_wal_dir, minimal_stored_record
    ):
        """Each failure appends a new row; artifact is append-only."""
        wal_dir = _reset_counter_and_wal_dir
        artifact_path = wal_dir / pb_wal.SECONDARY_APPEND_FAILURES_FILENAME

        with patch.object(pb_wal.wal, "append", return_value=None):
            pb_wal._append_daily_wal_record(minimal_stored_record)
            pb_wal._append_daily_wal_record(minimal_stored_record)

        rows = [json.loads(l) for l in artifact_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 2, f"Expected 2 artifact rows, got {len(rows)}"

    def test_artifact_write_failure_does_not_raise_or_break_return(
        self, pb_wal, _reset_counter_and_wal_dir, minimal_stored_record
    ):
        """If the diagnostic artifact write itself fails, _append_daily_wal_record still returns False."""
        with patch.object(pb_wal.wal, "append", return_value=None):
            # Patch open to fail only for the artifact file
            original_open = open

            def _sabotage_artifact_open(path, *args, **kwargs):
                if pb_wal.SECONDARY_APPEND_FAILURES_FILENAME in str(path):
                    raise PermissionError("cannot write artifact")
                return original_open(path, *args, **kwargs)

            import builtins
            with patch.object(builtins, "open", side_effect=_sabotage_artifact_open):
                result = pb_wal._append_daily_wal_record(minimal_stored_record)

        assert result is False, "Must return False even when artifact write fails"
        # Counter should still have incremented
        assert pb_wal.get_secondary_daily_append_failure_count() == 1

    def test_artifact_not_read_during_rehydration(
        self, pb_wal, _reset_counter_and_wal_dir
    ):
        """Diagnostic artifact must not influence rehydration result."""
        wal_dir = _reset_counter_and_wal_dir
        artifact_path = wal_dir / pb_wal.SECONDARY_APPEND_FAILURES_FILENAME

        # Write a fake artifact row that looks like a stored event
        fake_artifact = {
            "ts_ms": 1781473806000,
            "verb": "PENDING_BRACKETS_STORED",
            "symbol": "FAKEUSDT",
            "entry_order_id": "FAKE-9999",
            "rid": "rid-fake",
            "idem_key": None,
            "reason": None,
            "wal_append_result": "none",
            "exception_type": None,
            "exception_message": None,
            "source_component": "execution_position.pending_brackets_wal",
            "authority": "diagnostic_only",
        }
        artifact_path.write_text(
            json.dumps(fake_artifact) + "\n", encoding="utf-8"
        )

        # Rehydration must not include FAKE-9999
        restored = pb_wal.read_pending_brackets_from_wal()
        assert "FAKE-9999" not in restored, (
            "Diagnostic artifact must never be read as restore-authoritative"
        )
