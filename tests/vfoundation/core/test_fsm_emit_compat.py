"""Tests for vfoundation.core.fsm_emit_compat — emit compatibility layer."""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from unittest.mock import MagicMock, AsyncMock

import pytest

from vfoundation.core.fsm_emit_compat import emit_compat, _get, Message


class TestGetHelper:
    def test_get_attribute(self) -> None:
        class Obj:
            x = 42
        assert _get(Obj(), "x") == 42

    def test_get_dict(self) -> None:
        assert _get({"key": "val"}, "key") == "val"

    def test_get_default(self) -> None:
        assert _get(object(), "nonexistent", "default") == "default"


class TestEmitCompatPath1:
    """Test emit(msg) path — first fallback."""

    @pytest.mark.asyncio
    async def test_emit_message_sync(self) -> None:
        fsm = MagicMock()
        fsm.emit = MagicMock(return_value=None)
        msg = Message(op="EVT", verb="TEST", src="a", dst="b")
        await emit_compat(fsm, msg)
        fsm.emit.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_emit_message_async(self) -> None:
        fsm = MagicMock()
        fsm.emit = AsyncMock(return_value=None)
        msg = Message(op="EVT", verb="TEST", src="a", dst="b")
        await emit_compat(fsm, msg)
        fsm.emit.assert_called_once_with(msg)


class TestEmitCompatPath2:
    """Test emit(op, verb, pld, why) fallback."""

    @pytest.mark.asyncio
    async def test_fallback_to_4arg(self) -> None:
        call_args = []

        def custom_emit(*args):
            if len(args) == 1:
                raise TypeError("not supported")
            call_args.append(args)

        fsm = MagicMock()
        fsm.emit = custom_emit
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", pld={"data": 1})
        await emit_compat(fsm, msg)
        assert len(call_args) == 1
        assert call_args[0][0] == "EVT"  # op
        assert call_args[0][1] == "TEST"  # verb


class TestEmitCompatNoEmit:
    """Test FSM without emit method."""

    @pytest.mark.asyncio
    async def test_no_emit_attribute(self) -> None:
        fsm = object()  # no emit method
        msg = Message(op="EVT", verb="X", src="a", dst="b")
        # Should not raise
        await emit_compat(fsm, msg)

    @pytest.mark.asyncio
    async def test_no_emit_with_logger(self) -> None:
        fsm = object()
        logger = MagicMock()
        msg = Message(op="EVT", verb="X", src="a", dst="b")
        await emit_compat(fsm, msg, logger=logger)
        logger.error.assert_called_once()
