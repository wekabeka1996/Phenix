from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vfoundation.core.fsm_emit_compat import (
    EMIT_COMPAT_MODE_ATTR,
    Message,
    _get,
    emit_compat,
    resolve_emit_compat_mode,
)


class TestGetCoverage:
    def test_default_on_none_object(self):
        assert _get(None, "anything", "d") == "d"

    def test_getattr_exception_returns_default(self):
        class Bad:
            @property
            def x(self):
                raise AttributeError("property unavailable")

        assert _get(Bad(), "x", "fallback") == "fallback"

    def test_model_dump_fallback(self):
        class PydV2Like:
            def model_dump(self):
                return {"key": "val"}

        result = _get(PydV2Like(), "key", "miss")
        assert result in {"miss", "val"}

    def test_dict_method_fallback(self):
        class PydV1Like:
            def dict(self):
                return {"k": "v"}

        result = _get(PydV1Like(), "k", "miss")
        assert result in {"miss", "v"}


class TestEmitModeResolution:
    def test_resolve_message_mode_from_signature(self):
        class Fsm:
            def emit(self, msg):
                return None

        assert resolve_emit_compat_mode(Fsm()) == "message"

    def test_resolve_4arg_mode_from_signature(self):
        class Fsm:
            def emit(self, op, verb, payload, why):
                return None

        assert resolve_emit_compat_mode(Fsm()) == "op_verb_payload_why"

    def test_resolve_3arg_mode_from_signature(self):
        class Fsm:
            def emit(self, op, payload, why):
                return None

        assert resolve_emit_compat_mode(Fsm()) == "op_payload_why"

    def test_owner_override_beats_signature(self):
        class Fsm:
            _emit_compat_mode = "message"

            def emit(self, op, payload, why):
                return None

        assert resolve_emit_compat_mode(Fsm()) == "message"

    def test_invalid_override_fails_closed(self):
        logger = MagicMock()

        class Fsm:
            _emit_compat_mode = "bad-mode"

            def emit(self, msg):
                return None

        assert resolve_emit_compat_mode(Fsm(), logger=logger) is None
        logger.error.assert_called_once()

    def test_bound_callable_override_is_honored(self):
        def emit(*args):
            return None

        setattr(emit, EMIT_COMPAT_MODE_ATTR, "message")
        fsm = MagicMock()
        fsm.emit = emit
        assert resolve_emit_compat_mode(fsm) == "message"


class TestEmitCompatExecutionCoverage:
    @pytest.mark.asyncio
    async def test_emit_compat_handles_non_mapping_payload_when_injecting_meta(self):
        observed: list[tuple] = []

        class Fsm:
            _emit_compat_mode = "op_verb_payload_why"

            def emit(self, *args):
                observed.append(args)

        msg = Message(op="EVT", verb="TEST", src="a", dst="b", rid="r1")
        msg.pld = ["not", "a", "dict"]

        await emit_compat(Fsm(), msg)

        assert observed[0][2] == {"verb": "TEST", "rid": "r1", "src": "a", "dst": "b"}
