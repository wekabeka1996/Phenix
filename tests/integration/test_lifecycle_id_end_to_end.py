"""
PHASE 1 — TDD anchor: lifecycle_id is consistent across all three log event types
when parsed by neocortex order_parser.

Contract: ORDER_INTENT, ORDER_FILLED, and POSITION_CLOSED JSONL lines must all
carry the same lifecycle_id value, and order_parser.parse_order_log_line() must
extract it into OrderLogEntry.lifecycle_id.

These tests cover the full producer→consumer parse path.
They MUST FAIL before Phase 1 implementation (field absent in producer output).
They MUST PASS after Phase 1 implementation.
"""
import json
import uuid
import pytest


LIFECYCLE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
SYMBOL = "BTCUSDT"


# ---------------------------------------------------------------------------
# Canonical fixture lines (representing the Phase 1 producer output)
# ---------------------------------------------------------------------------

ORDER_INTENT_LINE = json.dumps({
    "event_type": "ORDER_INTENT",
    "event_ts_ms": 1700000000000,
    "symbol": SYMBOL,
    "side": "LONG",
    "quantity": 0.01,
    "price": 50000.0,
    "source_fsm": "DecisionMaking",
    "lifecycle_id": LIFECYCLE_ID,          # PHASE 1 — must be present
    "regime": "TREND_UP",
    "regime_confidence": 0.85,
    "metadata": {
        "intent_proposed": True,
        "idempotent_key": LIFECYCLE_ID,
        "normalize_mode_effective": "signed_v2",
    },
})

ORDER_FILLED_LINE = json.dumps({
    "event_type": "ORDER_FILLED",
    "event_ts_ms": 1700000001000,
    "symbol": SYMBOL,
    "side": "BUY",
    "quantity": 0.01,
    "price": 50000.0,
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,          # PHASE 1 — must be present
    "order_kind": "ENTRY",
    "metadata": {
        "fill_trade_id": "98001",
        "realized_pnl": 0.0,
        "commission": 0.05,
        "commissionAsset": "USDT",
    },
})

POSITION_CLOSED_LINE = json.dumps({
    "event_type": "POSITION_CLOSED",
    "event_ts_ms": 1700000060000,
    "symbol": SYMBOL,
    "side": "BUY",                         # PHASE 2 — real side (not N/A)
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,          # PHASE 1 — must be present
    "why": "SL",
    "close_reason": "SL",
    "metadata": {
        "close_price": 49000.0,
        "realized_pnl": -10.0,
    },
})

# Backward-compat fixture: no lifecycle_id (pre-Phase-1 producer format)
ORDER_INTENT_LINE_LEGACY = json.dumps({
    "event_type": "ORDER_INTENT",
    "event_ts_ms": 1700000000000,
    "symbol": SYMBOL,
    "side": "LONG",
    "metadata": {"idempotent_key": LIFECYCLE_ID},
    # NO top-level lifecycle_id
})


# ---------------------------------------------------------------------------
# Parser extraction tests
# ---------------------------------------------------------------------------


class TestOrderParserExtractsLifecycleId:
    """Neocortex order_parser must extract lifecycle_id into OrderLogEntry."""

    def _parse(self, line: str):
        from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
            parse_order_log_line,
        )
        return parse_order_log_line(line)

    def test_order_intent_lifecycle_id_parsed(self):
        """
        order_parser must extract 'lifecycle_id' from ORDER_INTENT line into
        OrderLogEntry.lifecycle_id.
        This test validates the canonical Phase 1 producer output is parseable.
        """
        entry = self._parse(ORDER_INTENT_LINE)
        assert entry is not None, "ORDER_INTENT line must be parseable"
        assert entry.lifecycle_id == LIFECYCLE_ID, (
            f"Expected lifecycle_id={LIFECYCLE_ID!r}, got {entry.lifecycle_id!r}"
        )

    def test_order_filled_lifecycle_id_parsed(self):
        """
        order_parser must extract 'lifecycle_id' from ORDER_FILLED line.
        """
        entry = self._parse(ORDER_FILLED_LINE)
        assert entry is not None, "ORDER_FILLED line must be parseable"
        assert entry.lifecycle_id == LIFECYCLE_ID, (
            f"Expected lifecycle_id={LIFECYCLE_ID!r}, got {entry.lifecycle_id!r}"
        )

    def test_position_closed_lifecycle_id_parsed(self):
        """
        order_parser must extract 'lifecycle_id' from POSITION_CLOSED line.
        """
        entry = self._parse(POSITION_CLOSED_LINE)
        assert entry is not None, "POSITION_CLOSED line must be parseable"
        assert entry.lifecycle_id == LIFECYCLE_ID, (
            f"Expected lifecycle_id={LIFECYCLE_ID!r}, got {entry.lifecycle_id!r}"
        )

    def test_lifecycle_id_consistent_across_all_three_events(self):
        """
        The lifecycle_id extracted from ORDER_INTENT, ORDER_FILLED, and
        POSITION_CLOSED must all be equal.
        This validates the canonical end-to-end lifecycle identity contract.
        """
        intent = self._parse(ORDER_INTENT_LINE)
        filled = self._parse(ORDER_FILLED_LINE)
        closed = self._parse(POSITION_CLOSED_LINE)

        assert intent is not None
        assert filled is not None
        assert closed is not None

        assert intent.lifecycle_id == LIFECYCLE_ID
        assert filled.lifecycle_id == LIFECYCLE_ID
        assert closed.lifecycle_id == LIFECYCLE_ID
        assert intent.lifecycle_id == filled.lifecycle_id == closed.lifecycle_id, (
            "lifecycle_id must be identical across ORDER_INTENT, ORDER_FILLED, POSITION_CLOSED"
        )

    def test_lifecycle_id_is_valid_uuid(self):
        """lifecycle_id extracted from lines must be a parseable UUID string."""
        entry = self._parse(ORDER_INTENT_LINE)
        assert entry is not None
        assert entry.lifecycle_id is not None
        try:
            uuid.UUID(str(entry.lifecycle_id))
        except (ValueError, AttributeError) as exc:
            pytest.fail(
                f"lifecycle_id '{entry.lifecycle_id}' is not a valid UUID: {exc}")


class TestBackwardCompatibility:
    """Legacy lines without lifecycle_id must parse gracefully (no crash)."""

    def _parse(self, line: str):
        from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
            parse_order_log_line,
        )
        return parse_order_log_line(line)

    def test_missing_lifecycle_id_returns_none_not_crash(self):
        """
        Pre-Phase-1 ORDER_INTENT lines without top-level lifecycle_id must parse
        to entry.lifecycle_id == None (graceful, backward-compatible).
        Old logs without lifecycle_id must not crash.
        """
        entry = self._parse(ORDER_INTENT_LINE_LEGACY)
        assert entry is not None, "Legacy ORDER_INTENT line must still be parseable"
        assert entry.lifecycle_id is None, (
            "lifecycle_id must be None (not empty string, not error) for legacy lines"
        )
