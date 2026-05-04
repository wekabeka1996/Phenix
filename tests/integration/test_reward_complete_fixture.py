"""
PHASE 3 — TDD anchor: canonical fixture lines carry fees, realized_pnl_net, and
lifecycle_id extractable by neocortex parsers.

Contracts:
1. order_parser extracts 'lifecycle_id' from ORDER_INTENT and ORDER_FILLED.
2. core_parser extracts 'fees' and 'realized_pnl_net' from POSITION_CLOSED log lines.
3. Both 'fees' and 'realized_pnl_net' must be non-None (required for reward_complete=True).
4. fees=0.0 must be extractable as float 0.0 (not None — critical for reward_complete gate).

These tests cover the producer→consumer parse path for Phase 3 fields.
Some tests verify parser behavior on *canonical fixture lines* (representing Phase 3
producer output). These pass when the parsers support the fields (which they already do
for order_parser re lifecycle_id; core_parser already has fees and realized_pnl_net).
The key TDD red tests are in test_fees_accumulation.py and test_net_pnl_computation.py.
"""
import json
import pytest


LIFECYCLE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
SYMBOL = "BTCUSDT"
TRADE_ID = "99001"
FEES = 0.09
REALIZED_PNL = -1.0
REALIZED_PNL_NET = REALIZED_PNL - FEES  # -1.09


# ---------------------------------------------------------------------------
# Canonical fixture lines — order_log_v1.jsonl format (order_parser)
# ---------------------------------------------------------------------------

ORDER_INTENT_LINE = json.dumps({
    "event_type": "ORDER_INTENT",
    "event_ts_ms": 1700000000000,
    "symbol": SYMBOL,
    "side": "LONG",
    "quantity": 0.01,
    "price": 50000.0,
    "source_fsm": "DecisionMaking",
    "lifecycle_id": LIFECYCLE_ID,
    "regime": "TREND_UP",
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
    "lifecycle_id": LIFECYCLE_ID,
    "order_kind": "ENTRY",
    "metadata": {
        "fill_trade_id": TRADE_ID,
        "realized_pnl": 0.0,
        "commission": 0.05,
        "commissionAsset": "USDT",
    },
})

POSITION_CLOSED_JSONL = json.dumps({
    "event_type": "POSITION_CLOSED",
    "event_ts_ms": 1700000060000,
    "symbol": SYMBOL,
    "side": "BUY",
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,
    "trade_id": TRADE_ID,
    "fees": FEES,                           # PHASE 3: accumulated fees
    "realized_pnl_net": REALIZED_PNL_NET,   # PHASE 3: net pnl
    "why": "SL",
    "close_reason": "SL",
    "metadata": {
        "close_price": 49000.0,
        "realized_pnl": REALIZED_PNL,
    },
})

# Canonical POSITION_CLOSED in aurora_core.log format (with timestamp prefix)
# core_parser uses _extract_field() which matches "key": value JSON patterns
POSITION_CLOSED_CORE_LOG_LINE = (
    f'2026-01-01 12:00:00,000 - aurora_core - INFO - POSITION_CLOSED: '
    f'{{"symbol": "{SYMBOL}", "event_type": "POSITION_CLOSED", '
    f'"trade_id": "{TRADE_ID}", '
    f'"realized_pnl": {REALIZED_PNL}, '
    f'"realized_pnl_net": {REALIZED_PNL_NET}, '
    f'"fees": {FEES}, '
    f'"lifecycle_id": "{LIFECYCLE_ID}"}}'
)

# Same but with fees=0.0 (critical edge case)
POSITION_CLOSED_ZERO_FEES_LOG_LINE = (
    '2026-01-01 12:00:00,000 - aurora_core - INFO - POSITION_CLOSED: '
    '{"symbol": "BTCUSDT", "event_type": "POSITION_CLOSED", '
    '"trade_id": "99002", '
    '"realized_pnl": 5.0, '
    '"realized_pnl_net": 5.0, '
    '"fees": 0.0, '
    '"lifecycle_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901"}'
)


# ---------------------------------------------------------------------------
# Tests: order_parser extracts lifecycle_id
# ---------------------------------------------------------------------------


class TestOrderParserLifecycleIdPresent:
    """Phase 3 regression: order_parser correctly extracts lifecycle_id (Phase 1 contract)."""

    def _parse(self, line):
        from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
            parse_order_log_line,
        )
        return parse_order_log_line(line)

    def test_order_intent_lifecycle_id_extracted(self):
        """ORDER_INTENT lifecycle_id must be extractable (regression from Phase 1)."""
        entry = self._parse(ORDER_INTENT_LINE)
        assert entry is not None
        assert entry.lifecycle_id == LIFECYCLE_ID

    def test_order_filled_lifecycle_id_extracted(self):
        """ORDER_FILLED lifecycle_id must be extractable (regression from Phase 1)."""
        entry = self._parse(ORDER_FILLED_LINE)
        assert entry is not None
        assert entry.lifecycle_id == LIFECYCLE_ID

    def test_position_closed_jsonl_lifecycle_id_extracted(self):
        """Phase 3 POSITION_CLOSED JSONL line must yield lifecycle_id via order_parser."""
        entry = self._parse(POSITION_CLOSED_JSONL)
        assert entry is not None
        assert entry.lifecycle_id == LIFECYCLE_ID


# ---------------------------------------------------------------------------
# Tests: core_parser extracts fees and realized_pnl_net
# ---------------------------------------------------------------------------


class TestCoreParserFeesExtraction:
    """Phase 3: core_parser must extract fees and realized_pnl_net from log lines."""

    def _parse(self, line):
        from apps.reference.domains.neocortex.logic.ingest.parsers.core_parser import (
            parse_core_log_line,
        )
        return parse_core_log_line(line)

    def test_position_closed_fees_extracted(self):
        """
        core_parser must extract 'fees' from canonical POSITION_CLOSED core log line.
        This validates the structured close surface is consumable by neocortex.
        """
        entry = self._parse(POSITION_CLOSED_CORE_LOG_LINE)
        assert entry is not None, (
            f"POSITION_CLOSED core log line must be parseable; line={POSITION_CLOSED_CORE_LOG_LINE!r}"
        )
        assert entry.fees is not None, (
            "core_parser must extract fees from POSITION_CLOSED log line"
        )
        assert entry.fees == pytest.approx(FEES), (
            f"Expected fees={FEES}, got {entry.fees}"
        )

    def test_position_closed_realized_pnl_net_extracted(self):
        """
        core_parser must extract 'realized_pnl_net' from canonical POSITION_CLOSED line.
        """
        entry = self._parse(POSITION_CLOSED_CORE_LOG_LINE)
        assert entry is not None
        assert entry.realized_pnl_net is not None, (
            "core_parser must extract realized_pnl_net"
        )
        assert entry.realized_pnl_net == pytest.approx(REALIZED_PNL_NET), (
            f"Expected realized_pnl_net={REALIZED_PNL_NET}, got {entry.realized_pnl_net}"
        )

    def test_fees_and_pnl_net_both_non_none(self):
        """
        Both 'fees' and 'realized_pnl_net' must be non-None in the same entry.
        This is the reward_complete gate condition in multi_tailer.
        """
        entry = self._parse(POSITION_CLOSED_CORE_LOG_LINE)
        assert entry is not None
        assert entry.fees is not None, "fees must be non-None"
        assert entry.realized_pnl_net is not None, "realized_pnl_net must be non-None"

    def test_zero_fees_extracted_as_float_not_none(self):
        """
        fees=0.0 must be extractable as float 0.0, not None.
        This is CRITICAL — the reward_complete gate requires fees to be non-None.
        fees=0.0 is a valid trade outcome (e.g., fee-free execution tier).
        """
        entry = self._parse(POSITION_CLOSED_ZERO_FEES_LOG_LINE)
        assert entry is not None, "Zero-fees POSITION_CLOSED line must be parseable"
        assert entry.fees is not None, (
            "fees=0.0 must be extracted as float 0.0, not None "
            "(reward_complete gate requires non-None fees)"
        )
        assert entry.fees == pytest.approx(
            0.0), f"Expected fees=0.0, got {entry.fees}"

    def test_core_parser_extracts_trade_id(self):
        """Phase 2+3 regression: core_parser must also extract trade_id from log line."""
        entry = self._parse(POSITION_CLOSED_CORE_LOG_LINE)
        assert entry is not None
        assert entry.trade_id == TRADE_ID, (
            f"Expected trade_id={TRADE_ID!r}, got {entry.trade_id!r}"
        )
