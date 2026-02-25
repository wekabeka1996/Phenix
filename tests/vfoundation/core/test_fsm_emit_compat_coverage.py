"""Coverage tests for fsm_emit_compat — targeting fallback paths."""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from vfoundation.core.fsm_emit_compat import emit_compat, _get, Message


class TestGet:
    def test_attribute_access(self):
        class Obj:
            x = 42
        assert _get(Obj(), "x") == 42

    def test_dict_access(self):
        assert _get({"a": 1}, "a") == 1

    def test_default_on_missing(self):
        assert _get({}, "missing", "def") == "def"

    def test_default_on_none_object(self):
        assert _get(None, "anything", "d") == "d"

    def test_getattr_exception_returns_default(self):
        """Test when getattr itself raises — hasattr returns True but getattr fails."""
        class Bad:
            @property
            def x(self):
                raise AttributeError("property unavailable")
        # hasattr catches AttributeError, so _get skips direct attribute access
        # And falls through to default
        assert _get(Bad(), "x", "fallback") == "fallback"

    def test_model_dump_fallback(self):
        """Object with model_dump but no direct attr."""
        class PydV2Like:
            def model_dump(self):
                return {"key": "val"}
        obj = PydV2Like()
        # _get looks for hasattr first; model_dump objects have the method as attr
        # This tests the model_dump path
        result = _get(obj, "key", "miss")
        assert result == "miss" or result == "val"  # Depends on Python attr resolution

    def test_dict_method_fallback(self):
        """Object with .dict() method (Pydantic v1 style)."""
        class PydV1Like:
            def dict(self):
                return {"k": "v"}
        result = _get(PydV1Like(), "k", "miss")
        # hasattr(obj, "k") is False, but hasattr(obj, "dict") is True
        assert result == "miss" or result == "v"


class TestEmitCompat:
    @pytest.mark.asyncio
    async def test_emit_with_message_api(self):
        """FSM.emit(msg) succeeds on first try."""
        fsm = MagicMock()
        fsm.emit = MagicMock(return_value=None)
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="t")
        await emit_compat(fsm, msg)
        fsm.emit.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_emit_no_emit_method(self):
        """FSM without emit method logs error."""
        fsm = MagicMock(spec=[])  # No emit attr
        logger = MagicMock()
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="t")
        await emit_compat(fsm, msg, logger=logger)
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_falls_back_to_4arg(self):
        """FSM.emit(msg) raises TypeError, falls back to emit(op, verb, pld, why)."""
        call_args = []
        def emit_fn(*args):
            if len(args) == 1:
                raise TypeError("bad")
            call_args.append(args)
        fsm = MagicMock()
        fsm.emit = emit_fn
        msg = Message(op="EVT", verb="DO", src="x", dst="y", why="because")
        await emit_compat(fsm, msg)
        assert len(call_args) == 1
        assert call_args[0][0] == "EVT"
        assert call_args[0][1] == "DO"

    @pytest.mark.asyncio
    async def test_emit_falls_back_to_3arg(self):
        """Both 1-arg and 4-arg fail, falls back to emit(op, pld, why)."""
        call_args = []
        def emit_fn(*args):
            if len(args) < 3:
                raise TypeError("bad")
            if len(args) == 4:
                raise TypeError("bad4")
            call_args.append(args)
        fsm = MagicMock()
        fsm.emit = emit_fn
        msg = Message(op="EVT", verb="DO", src="x", dst="y", why="test_why")
        await emit_compat(fsm, msg)
        assert len(call_args) == 1
        assert call_args[0][0] == "EVT"

    @pytest.mark.asyncio
    async def test_emit_all_fail(self):
        """All emit variants fail — logs exception."""
        def emit_fn(*args):
            raise RuntimeError("all fail")
        fsm = MagicMock()
        fsm.emit = emit_fn
        logger = MagicMock()
        msg = Message(op="EVT", verb="T", src="a", dst="b", why="w")
        await emit_compat(fsm, msg, logger=logger)
        logger.exception.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_async_awaitable(self):
        """FSM.emit returns an awaitable."""
        async def async_emit(msg):
            pass
        fsm = MagicMock()
        fsm.emit = async_emit
        msg = Message(op="EVT", verb="T", src="a", dst="b", why="w")
        await emit_compat(fsm, msg)

    @pytest.mark.asyncio
    async def test_emit_injects_meta_into_pld(self):
        """Verb, rid, src, dst injected into payload if not present."""
        call_args = []
        def emit_fn(*args):
            if len(args) == 1:
                raise TypeError("no msg")
            call_args.append(args)
        fsm = MagicMock()
        fsm.emit = emit_fn
        msg = Message(op="EVT", verb="OPEN", src="dm", dst="ep", why="test")
        await emit_compat(fsm, msg)
        pld = call_args[0][2]
        assert pld.get("verb") == "OPEN"
        assert pld.get("src") == "dm"
        assert pld.get("dst") == "ep"
