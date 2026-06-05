"""Tests for vfoundation.core.intent_layer — Phase 5.2."""
from __future__ import annotations

import pytest

from vfoundation.core.intent_layer import IntentLayer, INTENT_PRIORITY
from vfoundation.core.protocol import Message


def _msg(op: str = "CMD", verb: str = "OPEN", intent: str | None = None) -> Message:
    return Message(op=op, verb=verb, src="test", dst="any", why="test", intent=intent)


class TestPriority:
    def test_command_highest_priority(self) -> None:
        layer = IntentLayer()
        msg = _msg("CMD", "OPEN", intent="COMMAND")
        assert layer.priority(msg) == 0

    def test_inquiry_lowest_priority(self) -> None:
        layer = IntentLayer()
        msg = _msg("ASK", "HEALTH", intent="INQUIRY")
        assert layer.priority(msg) == 4

    def test_inferred_from_op(self) -> None:
        layer = IntentLayer()
        cmd = _msg("CMD", "OPEN")
        dec = _msg("DEC", "OPEN")
        ask = _msg("ASK", "READ")
        evt = _msg("EVT", "BAR_CLOSED")

        assert layer.priority(cmd) == INTENT_PRIORITY["COMMAND"]
        assert layer.priority(dec) == INTENT_PRIORITY["DECLARATION"]
        assert layer.priority(ask) == INTENT_PRIORITY["INQUIRY"]
        assert layer.priority(evt) == INTENT_PRIORITY["OBSERVATION"]

    def test_explicit_intent_overrides_op(self) -> None:
        layer = IntentLayer()
        # EVT but marked COMMAND
        msg = _msg("EVT", "URGENT", intent="COMMAND")
        assert layer.priority(msg) == 0


class TestDegradation:
    def test_all_pass_when_not_degraded(self) -> None:
        layer = IntentLayer()
        for intent in ["COMMAND", "DECLARATION", "PROPOSAL", "OBSERVATION", "INQUIRY"]:
            assert layer.should_process(_msg(intent=intent), degraded=False)

    def test_inquiry_dropped_when_degraded(self) -> None:
        layer = IntentLayer()
        msg = _msg("ASK", "HEALTH", intent="INQUIRY")
        assert not layer.should_process(msg, degraded=True)

    def test_command_survives_degradation(self) -> None:
        layer = IntentLayer()
        msg = _msg("CMD", "OPEN", intent="COMMAND")
        assert layer.should_process(msg, degraded=True)

    def test_inferred_inquiry_dropped(self) -> None:
        """ASK op without explicit intent → inferred INQUIRY → dropped."""
        layer = IntentLayer()
        msg = _msg("ASK", "READ")
        assert not layer.should_process(msg, degraded=True)


class TestTTL:
    def test_command_gets_fast_ttl(self) -> None:
        layer = IntentLayer()
        msg = _msg("CMD", "OPEN", intent="COMMAND")
        assert layer.ttl_for(msg) == 200

    def test_inquiry_gets_slow_ttl(self) -> None:
        layer = IntentLayer()
        msg = _msg("ASK", "READ", intent="INQUIRY")
        assert layer.ttl_for(msg) == 10000

    def test_default_ttl_for_unknown(self) -> None:
        layer = IntentLayer()
        msg = _msg("EVT", "SOMETHING")  # OBSERVATION → 2000
        assert layer.ttl_for(msg) == 2000


class TestClassify:
    def test_explicit_intent(self) -> None:
        layer = IntentLayer()
        assert layer.classify(_msg(intent="PROPOSAL")) == "PROPOSAL"

    def test_inferred_intent(self) -> None:
        layer = IntentLayer()
        assert layer.classify(_msg("CMD", "X")) == "COMMAND"
        assert layer.classify(_msg("DEC", "X")) == "DECLARATION"
        assert layer.classify(_msg("EVT", "X")) == "OBSERVATION"
        assert layer.classify(_msg("ERR", "X")) == "OBSERVATION"
