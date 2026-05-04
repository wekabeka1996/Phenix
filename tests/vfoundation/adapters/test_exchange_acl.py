"""Tests for vfoundation.adapters.exchange.acl — Exchange Anti-Corruption Layer."""
from __future__ import annotations

import pytest

from vfoundation.adapters.exchange.acl import (
    ExchangeACL,
    OrderCommand,
    OrderEvent,
    get_acl_metrics,
)
from vfoundation.core.protocol import Message


def _cmd(verb: str = "OPEN", **pld_kw: object) -> Message:
    return Message(
        op="CMD", verb=verb, src="test", dst="exchange",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": 0.01, "price": 42000, **pld_kw},
        why="test",
    )


# ─── Dataclasses ──────────────────────────────────────────────────────

class TestDataclasses:
    def test_order_command(self) -> None:
        cmd = OrderCommand(symbol="BTCUSDT", side="BUY", qty=1.0, order_type="MARKET")
        assert cmd.symbol == "BTCUSDT"
        assert cmd.tif == "GTC"

    def test_order_event(self) -> None:
        evt = OrderEvent(
            event_type="FILL", symbol="BTCUSDT", side="BUY", qty=1.0,
            filled_qty=1.0, price=42000.0, order_id="123",
            client_order_id="c1", timestamp_ms=1700000000000,
        )
        assert evt.event_type == "FILL"
        assert evt.reason is None


# ─── Submit ───────────────────────────────────────────────────────────

class TestSubmit:
    def test_valid_cmd_open(self) -> None:
        acl = ExchangeACL(shadow_mode=True)
        resp = acl.submit(_cmd("OPEN"))
        assert resp.op == "EVT"
        assert resp.verb == "ORDER_PLACED"
        assert resp.pld["status"] == "ACCEPTED"

    def test_valid_cmd_close(self) -> None:
        acl = ExchangeACL()
        resp = acl.submit(_cmd("CLOSE"))
        assert resp.op == "EVT"
        assert resp.verb == "ORDER_PLACED"

    def test_valid_cmd_adjust(self) -> None:
        acl = ExchangeACL()
        resp = acl.submit(_cmd("ADJUST"))
        assert resp.op == "EVT"
        assert resp.verb == "ORDER_PLACED"

    def test_invalid_op_rejected(self) -> None:
        acl = ExchangeACL()
        msg = Message(op="EVT", verb="OPEN", src="t", dst="x", why="test")
        resp = acl.submit(msg)
        assert resp.op == "ERR"
        assert resp.verb == "INVALID_OP"

    def test_invalid_verb_rejected(self) -> None:
        acl = ExchangeACL()
        msg = Message(op="CMD", verb="UNKNOWN_VERB", src="t", dst="x", why="test")
        resp = acl.submit(msg)
        assert resp.op == "ERR"
        assert resp.verb == "INVALID_VERB"

    def test_submit_populates_pld(self) -> None:
        acl = ExchangeACL()
        resp = acl.submit(_cmd("OPEN", symbol="ETHUSDT", side="SELL", qty=5.0))
        assert resp.pld["symbol"] == "ETHUSDT"
        assert resp.pld["side"] == "SELL"
        assert resp.pld["qty"] == 5.0


# ─── Cancel ───────────────────────────────────────────────────────────

class TestCancel:
    def test_cancel_close(self) -> None:
        acl = ExchangeACL()
        resp = acl.cancel(_cmd("CLOSE"))
        assert resp.op == "EVT"
        assert resp.verb == "CANCELLED"

    def test_cancel_invalid_verb(self) -> None:
        acl = ExchangeACL()
        resp = acl.cancel(_cmd("OPEN"))
        assert resp.op == "ERR"
        assert resp.verb == "INVALID_VERB"


# ─── Stream ───────────────────────────────────────────────────────────

class TestStreamEvents:
    def test_stub_yields_events(self) -> None:
        acl = ExchangeACL()
        events = list(acl.stream_events())
        assert len(events) == 2
        assert all(e.op == "EVT" for e in events)


# ─── Idempotency key ─────────────────────────────────────────────────

class TestIdempotencyKey:
    def test_deterministic_key(self) -> None:
        acl = ExchangeACL()
        cmd = _cmd("OPEN")
        k1 = acl._generate_idempotent_key(cmd)
        k2 = acl._generate_idempotent_key(cmd)
        assert k1 == k2
        assert len(k1) == 16  # SHA256 truncated to 16 hex chars

    def test_different_cmds_different_keys(self) -> None:
        acl = ExchangeACL()
        k1 = acl._generate_idempotent_key(_cmd("OPEN"))
        k2 = acl._generate_idempotent_key(_cmd("CLOSE"))
        assert k1 != k2


class TestIdempotencyDedup:
    """Tests for actual dedup via IdempotencyLedger wiring."""

    def test_second_submit_returns_dedup(self) -> None:
        acl = ExchangeACL()
        cmd = _cmd("OPEN")
        r1 = acl.submit(cmd)
        assert r1.verb == "ORDER_PLACED"
        # Same command again → should dedup
        r2 = acl.submit(cmd)
        assert r2.verb == "DEDUP"
        assert r2.pld["dedup"] is True


# ─── Metrics ──────────────────────────────────────────────────────────

class TestACLMetrics:
    def test_metrics_has_keys(self) -> None:
        m = get_acl_metrics()
        assert "events_rx_total" in m
        assert "events_tx_total" in m
        assert "rejects_total" in m
        assert "dedup_total" in m
