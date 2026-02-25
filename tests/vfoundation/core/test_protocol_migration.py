"""Tests for protocol migration helper (Phase 14C)."""
import pytest
from vfoundation.core.protocol import Message
from vfoundation.core.protocol_migration import migrate_pld_v1_to_v2, is_v2_message


class TestProtocolMigration:
    def test_migrate_v1_to_v2_moves_common_fields(self):
        msg = Message(
            op="DEC", verb="OPEN", src="any", dst="any", why="test",
            pld={"symbol": "BTC", "qty": 1.0, "ext_id": "123"}
        )
        # Migrate!
        migrate_pld_v1_to_v2(msg)
        
        # In V2, symbol/qty stay in pld, but let's say we want to verify 
        # it's still a valid message and we didn't corrupt it.
        assert msg.pld["symbol"] == "BTC"
        assert msg.pld["qty"] == 1.0

    def test_is_v2_message_detects_v2_flag(self):
        m1 = Message(op="EVT", verb="T", src="a", dst="b", pld={"v": 2})
        assert is_v2_message(m1) is True

    def test_is_v2_message_false_for_v1(self):
        m1 = Message(op="EVT", verb="T", src="a", dst="b", pld={"v": 1})
        assert is_v2_message(m1) is False
        
    def test_migrate_pld_is_idempotent(self):
        msg = Message(op="EVT", verb="T", src="a", dst="b", pld={"v": 2, "symbol": "BTC"})
        migrate_pld_v1_to_v2(msg)
        assert msg.pld["v"] == 2
        migrate_pld_v1_to_v2(msg)
        assert msg.pld["v"] == 2

    def test_migrate_unsupported_verb_no_op(self):
        msg = Message(op="EVT", verb="UNKNOWN", src="a", dst="b", pld={"data": 1})
        migrate_pld_v1_to_v2(msg)
        assert "v" not in msg.pld

    def test_migrate_open_v1_to_v2(self):
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", pld={"sym": "BTC", "q": 10})
        # Logic: maps 'sym' -> 'symbol', 'q' -> 'qty'
        migrate_pld_v1_to_v2(msg)
        assert msg.pld["symbol"] == "BTC"
        assert msg.pld["qty"] == 10
        assert msg.pld["v"] == 2

    def test_migrate_fill_v1_to_v2(self):
        msg = Message(op="EVT", verb="FILL", src="a", dst="b", pld={"oid": "order1", "p": 50000})
        migrate_pld_v1_to_v2(msg)
        assert msg.pld["order_id"] == "order1"
        assert msg.pld["price"] == 50000
        assert msg.pld["v"] == 2

    def test_is_v2_message_false_if_no_v_key(self):
        msg = Message(op="EVT", verb="T", src="a", dst="b", pld={})
        assert is_v2_message(msg) is False
