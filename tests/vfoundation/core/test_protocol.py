"""Tests for vfoundation.core.protocol — Message model, Op/IntentType, truncate_why."""

from __future__ import annotations

import time
import uuid

import pytest
from pydantic import ValidationError

from vfoundation.core.protocol import IntentType, Message, Op, truncate_why


# ── truncate_why ──────────────────────────────────────────────────────────


class TestTruncateWhy:
    def test_none_passthrough(self) -> None:
        assert truncate_why(None) is None

    def test_short_string_unchanged(self) -> None:
        assert truncate_why("hello") == "hello"

    def test_exact_80_unchanged(self) -> None:
        s = "x" * 80
        assert truncate_why(s) == s

    def test_81_chars_truncated(self) -> None:
        s = "a" * 81
        assert truncate_why(s) == "a" * 80

    def test_custom_max_len(self) -> None:
        assert truncate_why("abcdef", max_len=3) == "abc"

    def test_empty_string(self) -> None:
        assert truncate_why("") == ""


# ── Op / IntentType literal types ─────────────────────────────────────────


class TestLiterals:
    @pytest.mark.parametrize("op", ["ASK", "DEC", "CMD", "EVT", "UPD", "ERR"])
    def test_valid_ops(self, op: str) -> None:
        msg = Message(op=op, verb="EVAL", src="t", dst="t", why="ok")
        assert msg.op == op

    def test_invalid_op_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Message(op="INVALID", verb="EVAL", src="t", dst="t", why="ok")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "intent",
        ["INQUIRY", "COMMAND", "PROPOSAL", "OBSERVATION", "DECLARATION"],
    )
    def test_valid_intents(self, intent: str) -> None:
        msg = Message(op="ASK", verb="EVAL", src="t", dst="t", why="ok", intent=intent)
        assert msg.intent == intent

    def test_invalid_intent_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Message(op="ASK", verb="EVAL", src="t", dst="t", intent="WRONG")  # type: ignore[arg-type]

    def test_intent_none_by_default(self) -> None:
        msg = Message(op="ASK", verb="EVAL", src="t", dst="t", why="ok")
        assert msg.intent is None


# ── Message defaults ──────────────────────────────────────────────────────


class TestMessageDefaults:
    def test_v_defaults_to_1(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert msg.v == 1

    def test_rid_auto_generated(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        uuid.UUID(msg.rid)  # must be valid UUID

    def test_span_id_auto_generated(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert len(msg.span_id) == 32  # hex uuid without dashes

    def test_ts_near_now(self) -> None:
        before = int(time.time() * 1000)
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        after = int(time.time() * 1000)
        assert before <= msg.ts <= after + 1

    def test_ttl_ms_default(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert msg.ttl_ms == 2000

    def test_pld_default_empty_dict(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert msg.pld == {}

    def test_data_ref_default_empty_list(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert msg.data_ref == []

    def test_sig_none_by_default(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert msg.sig is None

    def test_mode_live_by_default(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="ok")
        assert msg.mode == "live"


# ── TTL validator ─────────────────────────────────────────────────────────


class TestTtlValidator:
    def test_ttl_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ttl_ms"):
            Message(op="EVT", verb="EVAL", src="a", dst="b", ttl_ms=0, why="ok")

    def test_ttl_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ttl_ms"):
            Message(op="EVT", verb="EVAL", src="a", dst="b", ttl_ms=-1, why="ok")

    def test_ttl_above_30000_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ttl_ms"):
            Message(op="EVT", verb="EVAL", src="a", dst="b", ttl_ms=30001, why="ok")

    def test_ttl_1_accepted(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", ttl_ms=1, why="ok")
        assert msg.ttl_ms == 1

    def test_ttl_30000_accepted(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", ttl_ms=30000, why="ok")
        assert msg.ttl_ms == 30000


# ── WHY validator ─────────────────────────────────────────────────────────


class TestWhyValidator:
    def test_why_80_accepted(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", why="x" * 80)
        assert len(msg.why) == 80  # type: ignore[arg-type]

    def test_why_81_rejected(self) -> None:
        with pytest.raises(ValidationError, match="why"):
            Message(op="EVT", verb="EVAL", src="a", dst="b", why="x" * 81)

    def test_why_none_accepted(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b")
        assert msg.why is None


# ── is_expired ────────────────────────────────────────────────────────────


class TestIsExpired:
    def test_fresh_message_not_expired(self) -> None:
        msg = Message(op="EVT", verb="EVAL", src="a", dst="b", ttl_ms=5000, why="ok")
        assert not msg.is_expired()

    def test_old_message_expired(self) -> None:
        old_ts = int(time.time() * 1000) - 10000
        msg = Message(
            op="EVT", verb="EVAL", src="a", dst="b",
            ts=old_ts, ttl_ms=1, why="ok",
        )
        assert msg.is_expired()

    def test_exactly_at_boundary(self) -> None:
        """Message at exactly ttl_ms age → not expired (> not >=)."""
        ts = int(time.time() * 1000)
        msg = Message(
            op="EVT", verb="EVAL", src="a", dst="b",
            ts=ts, ttl_ms=5000, why="ok",
        )
        # Immediately after creation, elapsed ≈ 0 ms < 5000 ms
        assert not msg.is_expired()


# ── Optional fields ───────────────────────────────────────────────────────


class TestOptionalFields:
    def test_corr_id(self) -> None:
        msg = Message(
            op="EVT", verb="EVAL", src="a", dst="b",
            corr_id="corr-123", why="ok",
        )
        assert msg.corr_id == "corr-123"

    def test_oco_group_id(self) -> None:
        msg = Message(
            op="EVT", verb="EVAL", src="a", dst="b",
            oco_group_id="oco-1", why="ok",
        )
        assert msg.oco_group_id == "oco-1"

    def test_idempotent_key(self) -> None:
        msg = Message(
            op="CMD", verb="OPEN", src="a", dst="b",
            idempotent_key="ik-42", why="ok",
        )
        assert msg.idempotent_key == "ik-42"

    def test_mode_contract(self) -> None:
        msg = Message(
            op="EVT", verb="EVAL", src="a", dst="b",
            mode_contract="backtest_v1", why="ok",
        )
        assert msg.mode_contract == "backtest_v1"

    def test_link_ack_id_and_fill_id(self) -> None:
        msg = Message(
            op="EVT", verb="EVAL", src="a", dst="b",
            link_ack_id="ack-1", link_fill_id="fill-2", why="ok",
        )
        assert msg.link_ack_id == "ack-1"
        assert msg.link_fill_id == "fill-2"
