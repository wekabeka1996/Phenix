"""
PHASE 2 — TDD anchor: order_parser correctly extracts trade_id and real side
from POSITION_CLOSED JSONL lines.

Contract: The canonical Phase 2 POSITION_CLOSED wire format must include top-level
'trade_id' and a real 'side' (BUY/SELL). order_parser.parse_order_log_line() must
extract both fields into OrderLogEntry.trade_id and OrderLogEntry.side.

These integration tests validate the producer→consumer parse chain.
- Tests against canonical fixture lines (representing Phase 2 producer output) PASS
  as soon as the parser supports the fields (parser already supports them).
- The key TDD red tests are in test_position_closed_identity.py (producer-side).
"""
import json
import pytest


LIFECYCLE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
SYMBOL = "BTCUSDT"
TRADE_ID = "99001"


# ---------------------------------------------------------------------------
# Canonical fixture lines (representing Phase 2 producer output)
# ---------------------------------------------------------------------------

# Phase 2 POSITION_CLOSED: has real side and top-level trade_id
POSITION_CLOSED_LINE = json.dumps({
    "event_type": "POSITION_CLOSED",
    "event_ts_ms": 1700000060000,
    "symbol": SYMBOL,
    "side": "BUY",              # PHASE 2: real side (not N/A)
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,
    "trade_id": TRADE_ID,       # PHASE 2: top-level trade_id
    "why": "SL",
    "close_reason": "SL",
    "metadata": {
        "close_price": 49000.0,
        "realized_pnl": -10.0,
    },
})

# Phase 1+2 ORDER_FILLED: trade_id in metadata.fill_trade_id (existing path)
ORDER_FILLED_LINE = json.dumps({
    "event_type": "ORDER_FILLED",
    "event_ts_ms": 1700000001000,
    "symbol": SYMBOL,
    "side": "BUY",
    "quantity": 0.01,
    "price": 50000.0,
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,
    "order_kind": "ENTRY",
    "metadata": {
        "fill_trade_id": TRADE_ID,
        "realized_pnl": 0.0,
        "commission": 0.05,
        "commissionAsset": "USDT",
    },
})

# Legacy POSITION_CLOSED line (pre-Phase-2): no trade_id, side="N/A"
POSITION_CLOSED_LEGACY = json.dumps({
    "event_type": "POSITION_CLOSED",
    "event_ts_ms": 1700000060000,
    "symbol": SYMBOL,
    "side": "N/A",
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,
    "why": "SL",
    "metadata": {"close_price": 49000.0, "realized_pnl": -10.0},
})


# ---------------------------------------------------------------------------
# Tests: parser extraction of trade_id and side
# ---------------------------------------------------------------------------


class TestCloseStructuredIdentityEndToEnd:
    """order_parser must extract trade_id and real side from Phase 2 POSITION_CLOSED."""

    def _parse(self, line: str):
        from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
            parse_order_log_line,
        )
        return parse_order_log_line(line)

    def test_position_closed_trade_id_extracted(self):
        """
        order_parser must extract top-level 'trade_id' from POSITION_CLOSED line.
        Validates the canonical Phase 2 wire format is correctly consumed by parser.
        """
        entry = self._parse(POSITION_CLOSED_LINE)
        assert entry is not None, "POSITION_CLOSED line must be parseable"
        assert entry.trade_id == TRADE_ID, (
            f"Expected trade_id={TRADE_ID!r}, got {entry.trade_id!r}"
        )

    def test_position_closed_side_is_real(self):
        """
        order_parser must extract real 'side' (BUY/SELL) from Phase 2 POSITION_CLOSED.
        """
        entry = self._parse(POSITION_CLOSED_LINE)
        assert entry is not None
        assert entry.side == "BUY", (
            f"Expected side='BUY', got {entry.side!r}"
        )

    def test_order_filled_trade_id_from_metadata_fallback(self):
        """
        For ORDER_FILLED without top-level trade_id, parser falls back to
        metadata.fill_trade_id (existing behavior — backward compat must be preserved).
        """
        entry = self._parse(ORDER_FILLED_LINE)
        assert entry is not None
        assert entry.trade_id == TRADE_ID, (
            f"ORDER_FILLED: expected trade_id from metadata.fill_trade_id={TRADE_ID!r}, "
            f"got {entry.trade_id!r}"
        )

    def test_trade_id_consistent_across_filled_and_closed(self):
        """
        The trade_id in ORDER_FILLED and POSITION_CLOSED must match when
        producers correctly propagate the exchange tradeId.
        """
        filled = self._parse(ORDER_FILLED_LINE)
        closed = self._parse(POSITION_CLOSED_LINE)
        assert filled is not None
        assert closed is not None
        assert filled.trade_id == closed.trade_id == TRADE_ID, (
            "trade_id must be consistent between ORDER_FILLED and POSITION_CLOSED"
        )

    def test_legacy_position_closed_side_na_parses_gracefully(self):
        """
        Legacy POSITION_CLOSED with side='N/A' must parse without crash.
        entry.side == 'N/A' is acceptable for pre-Phase-2 data.
        """
        entry = self._parse(POSITION_CLOSED_LEGACY)
        assert entry is not None, "Legacy POSITION_CLOSED must be parseable"
        assert entry.side == "N/A", (
            f"Legacy POSITION_CLOSED side expected 'N/A', got {entry.side!r}"
        )

    def test_legacy_position_closed_missing_trade_id_returns_none(self):
        """
        Legacy POSITION_CLOSED without trade_id must parse to entry.trade_id is None.
        Old logs must not crash, and missing trade_id must yield None gracefully.
        """
        entry = self._parse(POSITION_CLOSED_LEGACY)
        assert entry is not None
        assert entry.trade_id is None, (
            f"Legacy POSITION_CLOSED without trade_id should yield None, "
            f"got {entry.trade_id!r}"
        )
