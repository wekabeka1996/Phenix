"""Tests for FSMv2 Phase 14B: Transactional Rollback + WAL Integration."""
import pytest
from unittest.mock import MagicMock, call
from vfoundation.core.fsm_v2 import FSMv2
from vfoundation.core.protocol import Message


def _msg(verb: str = "GO") -> Message:
    return Message(op="EVT", verb=verb, src="test", dst="test", why="test")


def _build_fsm(*, on_exit=None, on_enter=None, wal_writer=None):
    """Helper: 2-state FSM  A --EVT:GO--> B  with optional callbacks."""
    fsm = FSMv2("test", wal_writer=wal_writer)
    fsm.register_state("A", initial=True, on_exit=on_exit)
    fsm.register_state("B", terminal=True, on_enter=on_enter)
    fsm.register_transition("A", "EVT:GO", "B")
    return fsm


# ── Transactional Rollback ────────────────────────────────────────────


class TestOnExitRollback:
    def test_on_exit_error_keeps_old_state(self):
        """on_exit exception → state stays at old_state (transition aborted)."""
        fsm = _build_fsm(on_exit=lambda k, s, m: (_ for _ in ()).throw(RuntimeError("boom")))
        state, resp = fsm.handle("k1", _msg())
        assert state == "A"
        assert fsm.get_state("k1") == "A"

    def test_on_exit_error_returns_err_message(self):
        """on_exit exception → returns ERR:ON_EXIT_ERROR message."""
        fsm = _build_fsm(on_exit=lambda k, s, m: (_ for _ in ()).throw(ValueError("bad")))
        state, resp = fsm.handle("k1", _msg())
        assert resp is not None
        assert resp.op == "ERR"
        assert resp.verb == "ON_EXIT_ERROR"
        assert "bad" in resp.why

    def test_on_exit_error_increments_metrics(self):
        """on_exit exception → errors + rollbacks incremented."""
        fsm = _build_fsm(on_exit=lambda k, s, m: (_ for _ in ()).throw(RuntimeError("x")))
        fsm.handle("k1", _msg())
        assert fsm.metrics.errors == 1
        assert fsm.metrics.rollbacks == 1
        assert fsm.metrics.transitions == 0


class TestOnEnterRollback:
    def test_on_enter_error_rolls_back_to_old_state(self):
        """on_enter exception → state rolled back to old_state."""
        fsm = _build_fsm(on_enter=lambda k, s, m: (_ for _ in ()).throw(RuntimeError("boom")))
        state, resp = fsm.handle("k1", _msg())
        assert state == "A"
        assert fsm.get_state("k1") == "A"

    def test_on_enter_error_returns_err_message(self):
        """on_enter exception → returns ERR:ON_ENTER_ERROR message."""
        fsm = _build_fsm(on_enter=lambda k, s, m: (_ for _ in ()).throw(TypeError("bad_type")))
        state, resp = fsm.handle("k1", _msg())
        assert resp is not None
        assert resp.op == "ERR"
        assert resp.verb == "ON_ENTER_ERROR"
        assert "bad_type" in resp.why

    def test_on_enter_error_increments_metrics(self):
        """on_enter exception → errors + rollbacks incremented, transitions not."""
        fsm = _build_fsm(on_enter=lambda k, s, m: (_ for _ in ()).throw(RuntimeError("x")))
        fsm.handle("k1", _msg())
        assert fsm.metrics.errors == 1
        assert fsm.metrics.rollbacks == 1
        assert fsm.metrics.transitions == 0


class TestActionNoRollback:
    def test_action_error_preserves_new_state(self):
        """action exception → state stays at new_state (post-commit behavior)."""
        def boom(msg):
            raise RuntimeError("action_fail")

        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_transition("A", "EVT:GO", "B", action=boom)
        state, resp = fsm.handle("k1", _msg())
        assert state == "B"
        assert fsm.get_state("k1") == "B"
        assert fsm.metrics.errors == 1
        assert fsm.metrics.rollbacks == 0


# ── WAL Integration ──────────────────────────────────────────────────


class TestWALIntegration:
    def test_wal_writer_called_on_transition(self):
        """WAL writer receives record with required fields on successful transition."""
        wal = MagicMock()
        fsm = _build_fsm(wal_writer=wal)
        fsm.handle("k1", _msg())
        assert wal.call_count == 1
        record = wal.call_args[0][0]
        assert record["event"] == "EVT:STATE_TRANSITION"
        assert record["fsm"] == "test"
        assert record["key"] == "k1"
        assert record["from_state"] == "A"
        assert record["to_state"] == "B"
        assert record["trigger"] == "EVT:GO"
        assert "ts_ms" in record

    def test_wal_writer_not_called_when_none(self):
        """Without wal_writer, transitions work normally (backward compat)."""
        fsm = _build_fsm(wal_writer=None)
        state, resp = fsm.handle("k1", _msg())
        assert state == "B"

    def test_wal_failure_does_not_block_transition(self):
        """WAL write failure → transition still succeeds (warn-only)."""
        wal = MagicMock(side_effect=IOError("disk full"))
        fsm = _build_fsm(wal_writer=wal)
        state, resp = fsm.handle("k1", _msg())
        assert state == "B"
        assert fsm.get_state("k1") == "B"
        assert fsm.metrics.transitions == 1

    def test_backward_compat_no_wal_arg(self):
        """FSMv2('name') without wal_writer argument works as before."""
        fsm = FSMv2("compat")
        fsm.register_state("X", initial=True)
        fsm.register_state("Y", terminal=True)
        fsm.register_transition("X", "EVT:GO", "Y")
        state, _ = fsm.handle("k1", _msg())
        assert state == "Y"
