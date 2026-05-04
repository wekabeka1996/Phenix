"""Tests for FSMv2 Phase 14B enhancements: reachability, dot export, stats."""
import pytest
from vfoundation.core.fsm_v2 import FSMv2
from vfoundation.core.protocol import Message


def _msg(verb: str = "INIT") -> Message:
    return Message(op="EVT", verb=verb, src="test", dst="test", why="test")


class TestValidateReachability:
    def test_linear_chain_all_reachable(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_state("C", terminal=True)
        fsm.register_transition("A", "EVT:GO", "B")
        fsm.register_transition("B", "EVT:DONE", "C")

        result = fsm.validate_reachability()
        assert result["valid"] is True
        assert result["unreachable"] == set()
        assert {"A", "B", "C"} == result["reachable"]

    def test_orphan_state_detected(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_state("ORPHAN")
        fsm.register_transition("A", "EVT:GO", "B")

        result = fsm.validate_reachability()
        assert result["valid"] is False
        assert "ORPHAN" in result["unreachable"]
        assert "A" in result["reachable"]
        assert "B" in result["reachable"]

    def test_no_initial_state_returns_invalid(self):
        fsm = FSMv2("test")
        fsm.register_state("A")
        result = fsm.validate_reachability()
        assert result["valid"] is False

    def test_single_initial_terminal_state_valid(self):
        fsm = FSMv2("test")
        fsm.register_state("ONLY", initial=True, terminal=True)
        result = fsm.validate_reachability()
        assert result["valid"] is True

    def test_branching_all_reachable(self):
        fsm = FSMv2("test")
        fsm.register_state("START", initial=True)
        fsm.register_state("LEFT", terminal=True)
        fsm.register_state("RIGHT", terminal=True)
        fsm.register_transition("START", "EVT:LEFT", "LEFT")
        fsm.register_transition("START", "EVT:RIGHT", "RIGHT")
        result = fsm.validate_reachability()
        assert result["valid"] is True
        assert result["unreachable"] == set()

    def test_multi_orphan_all_detected(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_state("X")
        fsm.register_state("Y")
        fsm.register_transition("A", "EVT:GO", "B")
        result = fsm.validate_reachability()
        assert "X" in result["unreachable"]
        assert "Y" in result["unreachable"]


class TestToDot:
    def test_dot_contains_all_states(self):
        fsm = FSMv2("machine")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("RUNNING")
        fsm.register_state("STOPPED", terminal=True)
        fsm.register_transition("IDLE", "CMD:START", "RUNNING")
        fsm.register_transition("RUNNING", "CMD:STOP", "STOPPED")
        dot = fsm.to_dot()
        assert "IDLE" in dot
        assert "RUNNING" in dot
        assert "STOPPED" in dot

    def test_dot_contains_transition_label(self):
        fsm = FSMv2("machine")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_transition("A", "EVT:TRIGGER", "B")
        dot = fsm.to_dot()
        assert "EVT:TRIGGER" in dot

    def test_dot_terminal_has_doublecircle(self):
        fsm = FSMv2("machine")
        fsm.register_state("START", initial=True)
        fsm.register_state("DONE", terminal=True)
        fsm.register_transition("START", "EVT:FIN", "DONE")
        dot = fsm.to_dot()
        assert "doublecircle" in dot

    def test_dot_initial_has_bold(self):
        fsm = FSMv2("machine")
        fsm.register_state("INIT", initial=True)
        fsm.register_state("END", terminal=True)
        fsm.register_transition("INIT", "EVT:GO", "END")
        dot = fsm.to_dot()
        assert "bold" in dot

    def test_dot_is_valid_graphviz_structure(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_transition("A", "EVT:X", "B")
        dot = fsm.to_dot()
        assert dot.strip().startswith("digraph")
        assert "{" in dot and "}" in dot
        assert "->" in dot

    def test_dot_arrow_connects_correct_states(self):
        fsm = FSMv2("machine")
        fsm.register_state("SRC", initial=True)
        fsm.register_state("DST", terminal=True)
        fsm.register_transition("SRC", "EVT:MOVE", "DST")
        dot = fsm.to_dot()
        assert "SRC -> DST" in dot


class TestGetStats:
    def test_stats_all_states_present_with_zero_counts(self):
        fsm = FSMv2("test")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("ACTIVE", terminal=True)
        stats = fsm.get_stats()
        assert "IDLE" in stats
        assert "ACTIVE" in stats

    def test_stats_initial_state_has_count_after_key_created(self):
        fsm = FSMv2("test")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("DONE", terminal=True)
        fsm.register_transition("IDLE", "EVT:FINISH", "DONE")

        # Create a key that stays in IDLE (invalid event)
        fsm.handle("key1", _msg("NOOP"))
        stats = fsm.get_stats()
        assert stats["IDLE"] == 1

    def test_stats_counts_after_transition(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_state("C", terminal=True)
        fsm.register_transition("A", "EVT:STEP1", "B")
        fsm.register_transition("B", "EVT:STEP2", "C")

        fsm.handle("k1", _msg("STEP1"))  # k1: A→B
        fsm.handle("k2", _msg("NOOP"))   # k2: stays at A
        fsm.handle("k1", _msg("STEP2"))  # k1: B→C

        stats = fsm.get_stats()
        assert stats["A"] == 1  # k2
        assert stats["B"] == 0
        assert stats["C"] == 1  # k1
