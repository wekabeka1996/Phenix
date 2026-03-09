"""
Tests for BacktestFastBus (Phase 4: Fast-Path EventBus Bypass)
"""
import pytest
from backtest_engine.fast_bus import BacktestFastBus, _FakeMessage


class TestBacktestFastBusBasic:
    """Core listener + emit semantics."""

    def test_emit_to_single_listener(self):
        bus = BacktestFastBus()
        received = []
        bus.listen("EVT:TEST", lambda msg: received.append(msg.pld))
        bus.emit("EVT:TEST", payload={"x": 1})
        assert received == [{"x": 1}]

    def test_emit_no_listeners_is_silent(self):
        bus = BacktestFastBus()
        # Must not raise
        bus.emit("EVT:NONEXISTENT", payload={"x": 1})

    def test_emit_multiple_listeners_all_called(self):
        bus = BacktestFastBus()
        log = []
        bus.listen("EVT:TEST", lambda msg: log.append("a"))
        bus.listen("EVT:TEST", lambda msg: log.append("b"))
        bus.emit("EVT:TEST")
        assert log == ["a", "b"]

    def test_emit_none_payload_becomes_empty_dict(self):
        bus = BacktestFastBus()
        received = []
        bus.listen("EVT:X", lambda msg: received.append(msg.pld))
        bus.emit("EVT:X", payload=None)
        assert received == [{}]

    def test_listener_exception_does_not_block_next_listener(self):
        bus = BacktestFastBus()
        log = []

        def bad(msg):
            raise RuntimeError("boom")

        bus.listen("EVT:X", bad)
        bus.listen("EVT:X", lambda msg: log.append("ok"))
        # Should not raise — exception is caught and logged
        bus.emit("EVT:X")
        assert log == ["ok"]


class TestBacktestFastBusRemoveListen:
    """remove_listener removes correctly."""

    def test_remove_listener_stops_calls(self):
        bus = BacktestFastBus()
        log = []
        cb = lambda msg: log.append(1)
        bus.listen("EVT:A", cb)
        bus.remove_listener("EVT:A", cb)
        bus.emit("EVT:A")
        assert log == []

    def test_remove_nonexistent_is_silent(self):
        bus = BacktestFastBus()
        # Must not raise
        bus.remove_listener("EVT:NEVER", lambda msg: None)


class TestBacktestFastBusCopyFrom:
    """copy_from registry cloning."""

    def test_copy_from_fsm_core(self):
        from vfoundation.core.fsm_core import FSMCore
        fsm = FSMCore()
        log = []
        fsm.listen("EVT:BAR_CLOSED", lambda msg: log.append("original"))

        bus = BacktestFastBus()
        bus.copy_from(fsm)
        bus.emit("EVT:BAR_CLOSED", payload={})

        # Original FSMCore listener is called via fast_bus
        assert log == ["original"]

    def test_copy_from_copies_domains(self):
        from vfoundation.core.fsm_core import FSMCore
        fsm = FSMCore()
        fake_domain = object()
        fsm.register_domain("my_domain", fake_domain)

        bus = BacktestFastBus()
        bus.copy_from(fsm)
        assert bus.get_domain("my_domain") is fake_domain

    def test_copy_from_is_independent_snapshot(self):
        """Adding listeners to fsm AFTER copy_from should NOT affect fast_bus."""
        from vfoundation.core.fsm_core import FSMCore
        fsm = FSMCore()
        log = []
        fsm.listen("EVT:A", lambda msg: log.append("first"))

        bus = BacktestFastBus()
        bus.copy_from(fsm)

        # New listener on fsm after snapshot
        fsm.listen("EVT:A", lambda msg: log.append("second"))

        bus.emit("EVT:A", payload={})
        # fast_bus only has the "first" listener
        assert log == ["first"]


class TestBacktestFastBusDomainRegistry:
    """register_domain and get_domain."""

    def test_register_and_get_domain(self):
        bus = BacktestFastBus()
        obj = object()
        bus.register_domain("fe", obj)
        assert bus.get_domain("fe") is obj

    def test_get_unknown_domain_returns_none(self):
        bus = BacktestFastBus()
        assert bus.get_domain("nonexistent") is None


class TestFakeMessage:
    """_FakeMessage attribute correctness."""

    def test_pld_attribute(self):
        msg = _FakeMessage(pld={"a": 1}, event_name="EVT:BAR_CLOSED")
        assert msg.pld == {"a": 1}

    def test_op_verb_split(self):
        msg = _FakeMessage(pld={}, event_name="CMD:PROCESS_STRATEGY")
        assert msg.op == "CMD"
        assert msg.verb == "PROCESS_STRATEGY"

    def test_op_verb_no_colon(self):
        msg = _FakeMessage(pld={}, event_name="NOCOLON")
        assert msg.op == "NOCOLON"
        assert msg.verb == "NOCOLON"

    def test_why_and_rid(self):
        msg = _FakeMessage(pld={}, why="test_why", rid="abc123", event_name="EVT:X")
        assert msg.why == "test_why"
        assert msg.rid == "abc123"


class TestBacktestFastBusListenerCache:
    """Snapshot cache consistency."""

    def test_cache_invalidated_after_new_listen(self):
        bus = BacktestFastBus()
        log = []

        bus.listen("EVT:C", lambda msg: log.append("first"))
        bus.emit("EVT:C", payload={})  # Populates cache

        bus.listen("EVT:C", lambda msg: log.append("second"))
        bus.emit("EVT:C", payload={})  # Should use fresh cache

        assert log == ["first", "first", "second"]

    def test_cache_invalidated_after_remove_listener(self):
        bus = BacktestFastBus()
        log = []
        cb1 = lambda msg: log.append("cb1")
        cb2 = lambda msg: log.append("cb2")

        bus.listen("EVT:D", cb1)
        bus.listen("EVT:D", cb2)
        bus.emit("EVT:D")  # -> ["cb1", "cb2"]

        bus.remove_listener("EVT:D", cb1)
        bus.emit("EVT:D")  # -> only cb2

        assert log == ["cb1", "cb2", "cb2"]
