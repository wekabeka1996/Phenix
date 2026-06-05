"""Tests for vfoundation.core.routing — Router + SimpleIdempotencyStore."""
from __future__ import annotations

import json
import time
from unittest.mock import patch, MagicMock

import pytest

from vfoundation.core.protocol import Message
from vfoundation.core.routing import Router, SimpleIdempotencyStore


# ── SimpleIdempotencyStore ────────────────────────────────────────────────


class TestSimpleIdempotencyStore:
    def test_seen_false_initially(self) -> None:
        store = SimpleIdempotencyStore()
        assert store.seen("key-1") is False

    def test_remember_then_seen(self) -> None:
        store = SimpleIdempotencyStore()
        msg = Message(op="EVT", verb="TEST", src="a", dst="b")
        store.remember("key-1", msg)
        assert store.seen("key-1") is True
        assert store.get("key-1") is msg

    def test_begin_acquire_lifecycle(self) -> None:
        store = SimpleIdempotencyStore()
        r1 = store.begin("k1")
        assert r1 == {"acquired": True}
        r2 = store.begin("k1")
        assert r2 == {"inflight": True}

    def test_complete_then_dedup(self) -> None:
        store = SimpleIdempotencyStore()
        msg = Message(op="EVT", verb="DONE", src="a", dst="b")
        store.begin("k1")
        store.complete("k1", msg)
        r = store.begin("k1")
        assert r == {"dedup": True}

    def test_get_if_done(self) -> None:
        store = SimpleIdempotencyStore()
        assert store.get_if_done("nope") is None
        msg = Message(op="EVT", verb="OK", src="a", dst="b")
        store.begin("k1")
        store.complete("k1", msg)
        assert store.get_if_done("k1") is msg


# ── Router ────────────────────────────────────────────────────────────────


def _echo_handler(msg: Message) -> Message:
    return Message(op="EVT", verb="ECHO", src="handler", dst=msg.src,
                   rid=msg.rid, pld=msg.pld)


class TestRouterBasic:
    def test_register_and_route(self) -> None:
        router = Router()
        router.register("CMD", "TEST", _echo_handler)
        msg = Message(op="CMD", verb="TEST", src="client", dst="router",
                      sig="aa" * 64)  # dummy sig — patched below
        # Patch verify to allow through
        with patch("vfoundation.core.routing.verify", return_value=True), \
             patch("vfoundation.core.routing.wal_append"):
            res = router.route(msg)
        assert res.op == "EVT"
        assert res.verb == "ECHO"

    def test_no_route(self) -> None:
        router = Router()
        msg = Message(op="EVT", verb="UNKNOWN", src="c", dst="r")
        with patch("vfoundation.core.routing.wal_append"):
            res = router.route(msg)
        assert res.op == "ERR"
        assert res.verb == "NO_ROUTE"


class TestRouterSigVerification:
    def test_dec_without_sig_rejected(self) -> None:
        router = Router()
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b")
        res = router.route(msg)
        assert res.op == "ERR"
        assert res.verb == "SIGNATURE_REQUIRED"

    def test_cmd_invalid_sig_rejected(self) -> None:
        router = Router()
        msg = Message(op="CMD", verb="OPEN", src="a", dst="b", sig="badbad")
        with patch("vfoundation.core.routing.verify", side_effect=ValueError("bad hex")):
            res = router.route(msg)
        assert res.op == "ERR"
        assert res.verb == "SIGNATURE_ERROR"


class TestRouterWhyLength:
    def test_why_over_80_rejected_at_message_level(self) -> None:
        """Message model itself rejects why > 80 chars (Pydantic validator)."""
        with pytest.raises(Exception):  # Pydantic validation
            Message(op="EVT", verb="X", src="a", dst="b", why="x" * 81)


class TestRouterIdempotency:
    def test_rid_dedup(self) -> None:
        router = Router()
        router.register("EVT", "PING", _echo_handler)
        msg = Message(op="EVT", verb="PING", src="a", dst="b")
        with patch("vfoundation.core.routing.wal_append"):
            r1 = router.route(msg)
            r2 = router.route(msg)
        # Second should return cached
        assert r2.rid == r1.rid

    def test_idempotent_key_dedup(self) -> None:
        router = Router()
        router.register("EVT", "PING", _echo_handler)
        msg = Message(op="EVT", verb="PING", src="a", dst="b",
                      idempotent_key="ik-1")
        with patch("vfoundation.core.routing.wal_append"):
            r1 = router.route(msg)
        assert r1.verb == "ECHO"
        with patch("vfoundation.core.routing.wal_append"):
            r2 = router.route(msg)
        assert r2.pld.get("dedup") is True


class TestRouterCB:
    def test_circuit_breaker_open(self) -> None:
        router = Router()
        router.register("EVT", "X", _echo_handler)
        # Force CB open with recent open_ts so cool_down hasn't passed
        router.cb.state = "OPEN"
        router.cb.open_ts = time.time()
        msg = Message(op="EVT", verb="X", src="a", dst="b")
        with patch("vfoundation.core.routing.wal_append"):
            res = router.route(msg)
        assert res.op == "ERR"
        assert res.verb == "CB_OPEN"


class TestRouterMetrics:
    def test_get_idempotency_metrics(self) -> None:
        router = Router()
        m = router.get_idempotency_metrics()
        assert "idem_acquired" in m
        assert "idem_dedup" in m
