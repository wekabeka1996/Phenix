from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from vfoundation.core.fsm_emit_compat import Message, _get, emit_compat


class TestGetHelper:
    def test_get_attribute(self) -> None:
        class Obj:
            x = 42

        assert _get(Obj(), "x") == 42

    def test_get_dict(self) -> None:
        assert _get({"key": "val"}, "key") == "val"

    def test_get_default(self) -> None:
        assert _get(object(), "nonexistent", "default") == "default"


class TestEmitCompatResolvedModes:
    @pytest.mark.asyncio
    async def test_emit_message_sync_via_signature(self) -> None:
        calls: list[object] = []

        class Fsm:
            def emit(self, msg):
                calls.append(msg)

        msg = Message(op="EVT", verb="TEST", src="a", dst="b")

        await emit_compat(Fsm(), msg)

        assert calls == [msg]

    @pytest.mark.asyncio
    async def test_emit_message_async_via_signature(self) -> None:
        calls: list[object] = []

        class Fsm:
            async def emit(self, msg):
                calls.append(msg)

        msg = Message(op="EVT", verb="TEST", src="a", dst="b")

        await emit_compat(Fsm(), msg)

        assert calls == [msg]

    @pytest.mark.asyncio
    async def test_emit_4arg_via_signature(self) -> None:
        calls: list[tuple] = []

        class Fsm:
            def emit(self, op, verb, payload, why):
                calls.append((op, verb, payload, why))

        msg = Message(op="EVT", verb="TEST", src="a", dst="b", pld={"data": 1}, why="w")
        await emit_compat(Fsm(), msg)

        assert len(calls) == 1
        op, verb, payload, why = calls[0]
        assert op == "EVT"
        assert verb == "TEST"
        assert payload["data"] == 1
        assert payload["verb"] == "TEST"
        assert payload["src"] == "a"
        assert payload["dst"] == "b"
        assert "rid" in payload
        assert why == "w"

    @pytest.mark.asyncio
    async def test_emit_3arg_via_signature(self) -> None:
        calls: list[tuple] = []

        class Fsm:
            def emit(self, op, payload, why):
                calls.append((op, payload, why))

        msg = Message(op="EVT", verb="TEST", src="a", dst="b", rid="rid-1", pld={"data": 1}, why="w")
        await emit_compat(Fsm(), msg)

        assert calls == [
            (
                "EVT",
                {"data": 1, "verb": "TEST", "rid": "rid-1", "src": "a", "dst": "b"},
                "w",
            )
        ]


class TestEmitCompatContractFailures:
    @pytest.mark.asyncio
    async def test_no_emit_attribute_logs_once(self) -> None:
        logger = MagicMock()

        await emit_compat(object(), Message(op="EVT", verb="X", src="a", dst="b"), logger=logger)

        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_uninspectable_varargs_without_override_fails_closed(self) -> None:
        logger = MagicMock()
        calls: list[tuple] = []

        class Fsm:
            def emit(self, *args):
                calls.append(args)

        await emit_compat(Fsm(), Message(op="EVT", verb="X", src="a", dst="b"), logger=logger)

        assert calls == []
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_explicit_override_allows_varargs_emitter(self) -> None:
        calls: list[tuple] = []

        class Fsm:
            _emit_compat_mode = "op_verb_payload_why"

            def emit(self, *args):
                calls.append(args)

        msg = Message(op="EVT", verb="X", src="a", dst="b", why="w")
        await emit_compat(Fsm(), msg)

        assert len(calls) == 1
        op, verb, payload, why = calls[0]
        assert op == "EVT"
        assert verb == "X"
        assert payload["verb"] == "X"
        assert payload["src"] == "a"
        assert payload["dst"] == "b"
        assert "rid" in payload
        assert why == "w"

    @pytest.mark.asyncio
    async def test_internal_typeerror_in_message_mode_is_not_retried(self) -> None:
        calls: list[object] = []

        class Fsm:
            def emit(self, msg):
                calls.append(msg)
                raise TypeError("internal bug")

        msg = Message(op="EVT", verb="X", src="a", dst="b")
        with pytest.raises(TypeError, match="internal bug"):
            await emit_compat(Fsm(), msg)

        assert calls == [msg]
