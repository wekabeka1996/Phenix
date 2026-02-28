"""Tests for vfoundation.core.payloads — VERB_PAYLOAD_MAP + validate_pld."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from vfoundation.core.payloads import (
    OpenPayload,
    FillPayload,
    resolve_payload_cls,
)
from vfoundation.core.protocol import Message


class TestVerbPayloadMap:
    """Phase 14.4 — discriminated union via VERB_PAYLOAD_MAP."""

    def test_map_dec_open_resolves(self) -> None:
        assert resolve_payload_cls("DEC", "OPEN") is OpenPayload

    def test_map_evt_fill_resolves(self) -> None:
        assert resolve_payload_cls("EVT", "FILL") is FillPayload

    def test_map_unknown_returns_none(self) -> None:
        assert resolve_payload_cls("EVT", "UNKNOWN") is None

    def test_validate_pld_success(self) -> None:
        msg = Message(
            op="DEC",
            verb="OPEN",
            src="test",
            dst="exec",
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": 0.1},
        )
        result = msg.validate_pld()
        assert isinstance(result, OpenPayload)
        assert result.symbol == "BTCUSDT"
        assert result.side == "BUY"
        assert result.qty == 0.1

    def test_validate_pld_invalid_raises(self) -> None:
        msg = Message(
            op="DEC",
            verb="OPEN",
            src="test",
            dst="exec",
            pld={"symbol": "BTCUSDT"},  # missing required 'side' and 'qty'
        )
        with pytest.raises(ValidationError):
            msg.validate_pld()

    def test_validate_pld_unmapped_returns_none(self) -> None:
        msg = Message(
            op="UPD",
            verb="EVAL",
            src="test",
            dst="any",
            pld={"data": 42},
        )
        assert msg.validate_pld() is None
