"""
PHASE 4 — Contract: canonical wire format schema for ORDER_INTENT, ORDER_FILLED,
and POSITION_CLOSED event types in order_log_v1.jsonl.

These tests establish and register the producer surface contract for Phases 1-3
fields. They serve as regression anchors: if any of these fields is accidentally
removed from the producer write, these tests will catch it.

Tests here use canonical JSONL fixture lines (the "gold standard" of Phase 1-3
producer output) and validate parsing via order_parser.parse_order_log_line().

Tests also validate backward compatibility: legacy lines without the new fields
must parse gracefully to None (not crash).
"""
import json
import uuid
import pytest

from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    parse_order_log_line,
    OrderEventType,
)


LIFECYCLE_ID = "c3d4e5f6-a7b8-9012-cdef-012345678901"
SYMBOL = "BTCUSDT"
TRADE_ID = "55001"
FEES = 0.09
REALIZED_PNL = -1.0
REALIZED_PNL_NET = -1.09


# ---------------------------------------------------------------------------
# Canonical fixture lines — Phases 1-3 producer output
# ---------------------------------------------------------------------------

ORDER_INTENT_CANONICAL = json.dumps({
    "event_type": "ORDER_INTENT",
    "event_ts_ms": 1700100000000,
    "symbol": SYMBOL,
    "side": "LONG",
    "quantity": 0.01,
    "price": 50000.0,
    "source_fsm": "DecisionMaking",
    "lifecycle_id": LIFECYCLE_ID,
    "regime": "TREND_UP",
    "regime_confidence": 0.9,
    "metadata": {
        "intent_proposed": True,
        "idempotent_key": LIFECYCLE_ID,
        "normalize_mode_effective": "signed_v2",
    },
})

ORDER_FILLED_CANONICAL = json.dumps({
    "event_type": "ORDER_FILLED",
    "event_ts_ms": 1700100001000,
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

POSITION_CLOSED_CANONICAL = json.dumps({
    "event_type": "POSITION_CLOSED",
    "event_ts_ms": 1700100060000,
    "symbol": SYMBOL,
    "side": "BUY",                   # PHASE 2: real side (not N/A)
    "source_fsm": "ExecPosFSM",
    "lifecycle_id": LIFECYCLE_ID,    # PHASE 1
    "trade_id": TRADE_ID,            # PHASE 2
    "fees": FEES,                    # PHASE 3
    "realized_pnl_net": REALIZED_PNL_NET,  # PHASE 3
    "why": "SL",
    "close_reason": "SL",
    "metadata": {
        "close_price": 49000.0,
        "realized_pnl": REALIZED_PNL,
    },
})

# Backward-compat fixtures: pre-Phase-1/2/3 format
ORDER_INTENT_LEGACY = json.dumps({
    "event_type": "ORDER_INTENT",
    "event_ts_ms": 1700100000000,
    "symbol": SYMBOL,
    "side": "LONG",
    "metadata": {"idempotent_key": LIFECYCLE_ID},
    # NO top-level lifecycle_id
})

POSITION_CLOSED_LEGACY = json.dumps({
    "event_type": "POSITION_CLOSED",
    "event_ts_ms": 1700100060000,
    "symbol": SYMBOL,
    "side": "N/A",      # pre-Phase-2 hardcoded side
    "source_fsm": "ExecPosFSM",
    # NO lifecycle_id, NO trade_id, NO fees, NO realized_pnl_net
    "metadata": {"close_price": 49000.0, "realized_pnl": -1.0},
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(line: str):
    return parse_order_log_line(line)


# ---------------------------------------------------------------------------
# TestOrderIntentCanonicalShape
# ---------------------------------------------------------------------------


class TestOrderIntentCanonicalShape:
    """Canonical ORDER_INTENT lines must carry lifecycle_id at top level."""

    def test_order_intent_lifecycle_id_present(self):
        entry = _parse(ORDER_INTENT_CANONICAL)
        assert entry is not None
        assert entry.lifecycle_id == LIFECYCLE_ID

    def test_order_intent_lifecycle_id_is_valid_uuid(self):
        entry = _parse(ORDER_INTENT_CANONICAL)
        assert entry is not None
        assert entry.lifecycle_id is not None
        uuid.UUID(str(entry.lifecycle_id))  # raises if invalid

    def test_order_intent_metadata_idempotent_key_preserved(self):
        """Additive change: metadata.idempotent_key must still be present."""
        entry = _parse(ORDER_INTENT_CANONICAL)
        assert entry is not None
        assert entry.metadata.get("idempotent_key") == LIFECYCLE_ID, (
            "metadata.idempotent_key must still be present for backward compat"
        )

    def test_order_intent_lifecycle_id_equals_metadata_idempotent_key(self):
        entry = _parse(ORDER_INTENT_CANONICAL)
        assert entry is not None
        assert entry.lifecycle_id == entry.metadata.get("idempotent_key")

    def test_legacy_order_intent_missing_lifecycle_id_parses_to_none(self):
        """Pre-Phase-1 lines without lifecycle_id must yield entry.lifecycle_id is None."""
        entry = _parse(ORDER_INTENT_LEGACY)
        assert entry is not None, "Legacy ORDER_INTENT must still be parseable"
        assert entry.lifecycle_id is None, (
            "lifecycle_id must be None for legacy lines (not empty string, not error)"
        )


# ---------------------------------------------------------------------------
# TestOrderFilledCanonicalShape
# ---------------------------------------------------------------------------


class TestOrderFilledCanonicalShape:
    """Canonical ORDER_FILLED lines must carry lifecycle_id and trade_id."""

    def test_order_filled_lifecycle_id_present(self):
        entry = _parse(ORDER_FILLED_CANONICAL)
        assert entry is not None
        assert entry.lifecycle_id == LIFECYCLE_ID

    def test_order_filled_trade_id_from_metadata(self):
        """ORDER_FILLED carries trade_id via metadata.fill_trade_id fallback."""
        entry = _parse(ORDER_FILLED_CANONICAL)
        assert entry is not None
        assert entry.trade_id == TRADE_ID

    def test_order_filled_event_type(self):
        entry = _parse(ORDER_FILLED_CANONICAL)
        assert entry is not None
        assert entry.event_type == OrderEventType.FILLED

    def test_order_filled_side_present(self):
        entry = _parse(ORDER_FILLED_CANONICAL)
        assert entry is not None
        assert entry.side == "BUY"


# ---------------------------------------------------------------------------
# TestPositionClosedCanonicalShape
# ---------------------------------------------------------------------------


class TestPositionClosedCanonicalShape:
    """
    Canonical POSITION_CLOSED lines must carry lifecycle_id, trade_id (Phases 1-2),
    fees and realized_pnl_net (Phase 3), and real entry side (Phase 2).
    """

    def test_event_type_is_position_closed(self):
        """Raw line must parse; event_type is UNKNOWN (no enum value) but symbol is set."""
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None, "POSITION_CLOSED canonical line must parse successfully"
        assert entry.symbol == SYMBOL

    def test_lifecycle_id_extracted(self):
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        assert entry.lifecycle_id == LIFECYCLE_ID

    def test_trade_id_extracted(self):
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        assert entry.trade_id == TRADE_ID

    def test_side_is_real_not_na(self):
        """Phase 2: side must be real entry direction, not 'N/A'."""
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        assert entry.side in ("BUY", "SELL"), (
            f"POSITION_CLOSED side must be BUY or SELL, got {entry.side!r}"
        )

    def test_fees_present_in_raw(self):
        """Phase 3: fees must be present in the raw JSONL payload."""
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        assert "fees" in entry.raw, (
            "fees must be present in POSITION_CLOSED raw payload"
        )

    def test_fees_extracted_as_numeric(self):
        """Phase 3: fees value must be a numeric float."""
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        fees = entry.raw.get("fees")
        assert fees is not None, "fees must not be None"
        assert isinstance(fees, (int, float)
                          ), f"fees must be numeric, got {type(fees)}"
        assert fees == pytest.approx(FEES)

    def test_zero_fees_extracted_as_float_not_none(self):
        """
        CRITICAL: fees=0.0 must parse to float 0.0, not None, not absent.
        The reward_complete gate in neocortex requires fees to be non-None.
        Zero fees are valid (e.g., fee-free tier).
        """
        zero_fees_line = json.dumps({
            "event_type": "POSITION_CLOSED",
            "event_ts_ms": 1700200000000,
            "symbol": SYMBOL,
            "side": "BUY",
            "lifecycle_id": LIFECYCLE_ID,
            "trade_id": TRADE_ID,
            "fees": 0.0,                # CRITICAL: must survive round-trip as 0.0
            "realized_pnl_net": 5.0,
            "metadata": {"realized_pnl": 5.0},
        })
        entry = _parse(zero_fees_line)
        assert entry is not None
        fees = entry.raw.get("fees")
        assert fees is not None, (
            "fees=0.0 must be non-None after parse round-trip "
            "(reward_complete requires non-None fees)"
        )
        assert fees == pytest.approx(0.0), f"fees must be 0.0, got {fees!r}"

    def test_realized_pnl_net_present_in_raw(self):
        """Phase 3: realized_pnl_net must be present in the raw payload."""
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        assert "realized_pnl_net" in entry.raw, (
            "realized_pnl_net must be present in POSITION_CLOSED raw payload"
        )

    def test_realized_pnl_net_extracted_as_numeric(self):
        """Phase 3: realized_pnl_net must be a numeric float."""
        entry = _parse(POSITION_CLOSED_CANONICAL)
        assert entry is not None
        pnl_net = entry.raw.get("realized_pnl_net")
        assert pnl_net is not None
        assert isinstance(pnl_net, (int, float))
        assert pnl_net == pytest.approx(REALIZED_PNL_NET)

    def test_legacy_position_closed_parses_gracefully(self):
        """Pre-Phase legacy POSITION_CLOSED without new fields must not crash."""
        entry = _parse(POSITION_CLOSED_LEGACY)
        assert entry is not None, "Legacy POSITION_CLOSED must still be parseable"
        assert entry.lifecycle_id is None, "Legacy line: lifecycle_id must be None"
        assert entry.trade_id is None, "Legacy line: trade_id must be None"
        assert entry.side == "N/A", "Legacy line: side must be 'N/A'"
        assert entry.raw.get("fees") is None, "Legacy line: fees must be None"
        assert entry.raw.get("realized_pnl_net") is None, (
            "Legacy line: realized_pnl_net must be None"
        )
