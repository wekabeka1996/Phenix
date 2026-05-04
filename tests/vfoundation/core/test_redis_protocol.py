"""
Phase 10.2: Tests for redis_protocol.py (Protocol + TypedDict definitions).
Tests structural correctness and Protocol compliance.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from vfoundation.core.idempotency.backends.redis_protocol import (
    RecordTD,
    RedisClientProtocol,
)


class TestRecordTD:
    """Tests for RecordTD TypedDict structure."""

    def test_create_minimal(self) -> None:
        """RecordTD should be creatable with only required/optional fields."""
        record: RecordTD = {}
        assert isinstance(record, dict)

    def test_create_full(self) -> None:
        """RecordTD should accept all defined fields."""
        record: RecordTD = {
            "owner": "worker-1",
            "payload_digest": "sha256-abc",
            "status": "HELD",
            "ts_ns": "1234567890000",
            "lease_ms": 5000,
            "result": None,
        }
        assert record["owner"] == "worker-1"
        assert record["status"] == "HELD"

    def test_get_missing_key_returns_none(self) -> None:
        """TypedDict.get() on missing field should return None."""
        record: RecordTD = {"owner": "w1"}
        result = record.get("status")
        assert result is None

    def test_record_update(self) -> None:
        """RecordTD fields should be mutable (dict semantics)."""
        record: RecordTD = {"owner": "w1", "status": "HELD"}
        record["status"] = "CONFIRMED"
        assert record["status"] == "CONFIRMED"


class TestRedisClientProtocol:
    """Structural tests for RedisClientProtocol interface."""

    def test_protocol_has_ping(self) -> None:
        """RedisClientProtocol should declare ping method."""
        assert hasattr(RedisClientProtocol, "ping")

    def test_protocol_has_eval(self) -> None:
        """RedisClientProtocol should declare eval method."""
        assert hasattr(RedisClientProtocol, "eval")

    def test_protocol_has_evalsha(self) -> None:
        """RedisClientProtocol should declare evalsha method."""
        assert hasattr(RedisClientProtocol, "evalsha")

    def test_protocol_has_get(self) -> None:
        """RedisClientProtocol should declare get method."""
        assert hasattr(RedisClientProtocol, "get")

    def test_protocol_has_exists(self) -> None:
        """RedisClientProtocol should declare exists method."""
        assert hasattr(RedisClientProtocol, "exists")
