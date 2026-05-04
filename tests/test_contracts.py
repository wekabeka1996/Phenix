from __future__ import annotations
import pytest
from vfoundation.core.protocol import Message


def test_message_ttl_validation():
    with pytest.raises(ValueError):
        Message(op="ASK", verb="EVAL", src="a", dst="b", ttl_ms=0)


def test_why_len():
    with pytest.raises(ValueError):
        Message(op="ASK", verb="EVAL", src="a", dst="b", why="x" * 81)


def test_valid_message():
    m = Message(op="ASK", verb="EVAL", src="a", dst="b", ttl_ms=200)
    assert m.op == "ASK"
    assert not m.is_expired()
