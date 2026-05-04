"""Tests for vfoundation.core.fsm_v2 — Phase 3.1."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from vfoundation.core.fsm_v2 import FSMv2, MAX_STATES_PER_FSM
from vfoundation.core.protocol import Message


def _msg(op: str = "CMD", verb: str = "OPEN", **pld: Any) -> Message:
    return Message(op=op, verb=verb, src="test", dst="any", pld=pld, why="test")


# ─── Registration ────────────────────────────────────────────────────

class TestRegistration:
    def test_register_states(self) -> None:
        fsm = FSMv2("test")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("ACTIVE")
        fsm.register_state("DONE", terminal=True)
        assert set(fsm.get_registered_states()) == {"IDLE", "ACTIVE", "DONE"}

    def test_duplicate_state_raises(self) -> None:
        fsm = FSMv2("test")
        fsm.register_state("A")
        with pytest.raises(ValueError, match="already registered"):
            fsm.register_state("A")

    def test_two_initial_states_raises(self) -> None:
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        with pytest.raises(ValueError, match="already has initial state"):
            fsm.register_state("B", initial=True)

    def test_max_states_limit(self) -> None:
        fsm = FSMv2("test")
        for i in range(MAX_STATES_PER_FSM):
            fsm.register_state(f"S{i}")
        with pytest.raises(ValueError, match="max"):
            fsm.register_state("TOO_MANY")

    def test_transition_from_unknown_state_raises(self) -> None:
        fsm = FSMv2("test")
        fsm.register_state("A")
        with pytest.raises(ValueError, match="Unknown from_state"):
            fsm.register_transition("NOPE", "CMD:GO", "A")

    def test_transition_to_unknown_state_raises(self) -> None:
        fsm = FSMv2("test")
        fsm.register_state("A")
        with pytest.raises(ValueError, match="Unknown to_state"):
            fsm.register_transition("A", "CMD:GO", "NOPE")

    def test_transition_from_terminal_raises(self) -> None:
        fsm = FSMv2("test")
        fsm.register_state("END", terminal=True)
        fsm.register_state("X")
        with pytest.raises(ValueError, match="terminal"):
            fsm.register_transition("END", "CMD:GO", "X")


# ─── Handle (core transitions) ──────────────────────────────────────

class TestHandle:
    @staticmethod
    def _make_order_fsm() -> FSMv2:
        fsm = FSMv2("order")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("PENDING")
        fsm.register_state("PLACED")
        fsm.register_state("FILLED", terminal=True)
        fsm.register_state("CANCELLED", terminal=True)

        fsm.register_transition("IDLE", "CMD:OPEN", "PENDING")
        fsm.register_transition("PENDING", "EVT:ORDER_PLACED", "PLACED")
        fsm.register_transition("PLACED", "EVT:ORDER_FILL", "FILLED")
        fsm.register_transition("PLACED", "CMD:CANCEL", "CANCELLED")
        return fsm

    def test_basic_lifecycle(self) -> None:
        fsm = self._make_order_fsm()
        key = "order-1"

        state, _ = fsm.handle(key, _msg("CMD", "OPEN"))
        assert state == "PENDING"

        state, _ = fsm.handle(key, _msg("EVT", "ORDER_PLACED"))
        assert state == "PLACED"

        state, _ = fsm.handle(key, _msg("EVT", "ORDER_FILL"))
        assert state == "FILLED"

    def test_cancel_from_placed(self) -> None:
        fsm = self._make_order_fsm()
        fsm.handle("o1", _msg("CMD", "OPEN"))
        fsm.handle("o1", _msg("EVT", "ORDER_PLACED"))
        state, _ = fsm.handle("o1", _msg("CMD", "CANCEL"))
        assert state == "CANCELLED"

    def test_no_transition_returns_error(self) -> None:
        fsm = self._make_order_fsm()
        state, err = fsm.handle("o1", _msg("EVT", "ORDER_FILL"))
        # IDLE has no EVT:ORDER_FILL transition
        assert state == "IDLE"
        assert err is not None
        assert err.op == "ERR"
        assert err.verb == "NO_TRANSITION"

    def test_no_initial_state_returns_error(self) -> None:
        fsm = FSMv2("broken")
        fsm.register_state("X")  # No initial=True
        _, err = fsm.handle("k", _msg())
        assert err is not None
        assert err.verb == "NO_INITIAL_STATE"

    def test_independent_keys(self) -> None:
        fsm = self._make_order_fsm()
        fsm.handle("a", _msg("CMD", "OPEN"))
        fsm.handle("b", _msg("CMD", "OPEN"))
        fsm.handle("a", _msg("EVT", "ORDER_PLACED"))
        assert fsm.get_state("a") == "PLACED"
        assert fsm.get_state("b") == "PENDING"

    def test_unknown_key_returns_none(self) -> None:
        fsm = self._make_order_fsm()
        assert fsm.get_state("nonexistent") is None

    def test_metrics_tracked(self) -> None:
        fsm = self._make_order_fsm()
        fsm.handle("k", _msg("CMD", "OPEN"))
        assert fsm.metrics.transitions == 1
        fsm.handle("k", _msg("EVT", "GARBAGE"))
        assert fsm.metrics.rejected == 1


# ─── Guards ──────────────────────────────────────────────────────────

class TestGuards:
    def test_guard_allows_transition(self) -> None:
        fsm = FSMv2("guarded")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_transition(
            "A", "CMD:GO", "B",
            guard=lambda m: m.pld.get("qty", 0) > 0,
        )
        state, _ = fsm.handle("k", _msg("CMD", "GO", qty=10))
        assert state == "B"

    def test_guard_blocks_transition(self) -> None:
        fsm = FSMv2("guarded")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_transition(
            "A", "CMD:GO", "B",
            guard=lambda m: m.pld.get("qty", 0) > 0,
        )
        state, err = fsm.handle("k", _msg("CMD", "GO", qty=0))
        assert state == "A"
        assert err is not None
        assert err.verb == "GUARD_REJECTED"
        assert fsm.metrics.guard_rejected == 1

    def test_multiple_transitions_first_guard_wins(self) -> None:
        fsm = FSMv2("multi")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_state("C")
        fsm.register_transition(
            "A", "CMD:GO", "B",
            guard=lambda m: m.pld.get("mode") == "fast",
        )
        fsm.register_transition(
            "A", "CMD:GO", "C",
            guard=lambda m: m.pld.get("mode") == "slow",
        )
        state1, _ = fsm.handle("k1", _msg("CMD", "GO", mode="fast"))
        assert state1 == "B"
        state2, _ = fsm.handle("k2", _msg("CMD", "GO", mode="slow"))
        assert state2 == "C"


# ─── Actions ─────────────────────────────────────────────────────────

class TestActions:
    def test_action_returns_response(self) -> None:
        fsm = FSMv2("act")
        fsm.register_state("X", initial=True)
        fsm.register_state("Y")
        fsm.register_transition(
            "X", "CMD:DO", "Y",
            action=lambda m: Message(
                op="EVT", verb="DONE", src="fsm", dst=m.src,
                rid=m.rid, why="action"
            ),
        )
        state, resp = fsm.handle("k", _msg("CMD", "DO"))
        assert state == "Y"
        assert resp is not None
        assert resp.verb == "DONE"

    def test_action_exception_does_not_block_transition(self) -> None:
        def bad_action(m: Message) -> Optional[Message]:
            raise RuntimeError("boom")

        fsm = FSMv2("act_err")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_transition("A", "CMD:GO", "B", action=bad_action)
        state, resp = fsm.handle("k", _msg("CMD", "GO"))
        # Transition still happens even if action fails
        assert state == "B"
        assert fsm.metrics.errors == 1


# ─── Callbacks (on_enter / on_exit) ─────────────────────────────────

class TestCallbacks:
    def test_on_enter_called(self) -> None:
        log: List[str] = []
        fsm = FSMv2("cb")
        fsm.register_state("A", initial=True, on_exit=lambda k, s, m: log.append(f"exit:{s}"))
        fsm.register_state("B", on_enter=lambda k, s, m: log.append(f"enter:{s}"))
        fsm.register_transition("A", "CMD:GO", "B")
        fsm.handle("k", _msg("CMD", "GO"))
        assert log == ["exit:A", "enter:B"]


# ─── Snapshot / Restore ──────────────────────────────────────────────

class TestSnapshotRestore:
    def test_snapshot_and_restore(self) -> None:
        fsm = FSMv2("snap")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("ACTIVE")
        fsm.register_transition("IDLE", "CMD:GO", "ACTIVE")

        fsm.handle("a", _msg("CMD", "GO"))
        fsm.handle("b", _msg("CMD", "GO"))

        snap = fsm.snapshot()
        assert snap == {"a": "ACTIVE", "b": "ACTIVE"}

        # Restore into a fresh FSM
        fsm2 = FSMv2("snap2")
        fsm2.register_state("IDLE", initial=True)
        fsm2.register_state("ACTIVE")
        fsm2.restore(snap)
        assert fsm2.get_state("a") == "ACTIVE"

    def test_restore_rejects_unknown_state(self) -> None:
        fsm = FSMv2("snap")
        fsm.register_state("X")
        with pytest.raises(ValueError, match="Unknown state"):
            fsm.restore({"k": "NONEXISTENT"})


# ─── Transition table introspection ─────────────────────────────────

class TestTransitionTable:
    def test_get_transition_table(self) -> None:
        fsm = FSMv2("t")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_transition("A", "CMD:GO", "B", guard=lambda m: True)
        table = fsm.get_transition_table()
        assert len(table) == 1
        assert table[0]["from"] == "A"
        assert table[0]["to"] == "B"
        assert table[0]["guarded"] is True

    def test_tracked_keys(self) -> None:
        fsm = FSMv2("t")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_transition("A", "CMD:GO", "B")
        fsm.handle("x", _msg("CMD", "GO"))
        fsm.handle("y", _msg("CMD", "GO"))
        assert fsm.tracked_keys() == {"x", "y"}
