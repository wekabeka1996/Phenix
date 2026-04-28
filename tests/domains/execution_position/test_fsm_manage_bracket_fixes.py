"""
FIX-1102 / FIX-4015 / FIX-1111: Bracket placement bug fix tests.

Covers:
  Bug 1 (FIX-1102) — stopPrice missing for TAKE_PROFIT_MARKET
  Bug 2 (FIX-4015) — client order ID > 36 chars
  Bug 3 (FIX-1111) — price quantization without side-aware rounding
"""
import re
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from types import SimpleNamespace

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from apps.reference.domains.execution_position.utils import generate_client_order_id


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

BINANCE_CID_MAX = 36


def _msg(symbol: str = "BTCUSDT", rid: str = "rid-test-001") -> Message:
    return Message(
        op="EVT", verb="FILL", src="adapter", dst="execution_position",
        why="test bracket fix", rid=rid,
        pld={"symbol": symbol, "qty": "0.01", "price": "50000"},
    )


def _manage(position_side: str = "BUY", symbol: str = "BTCUSDT",
            tick_size: float = 0.1) -> ManageFlowFSM:
    """Minimal ManageFlowFSM fixture for unit-testing individual methods."""
    cfg = MagicMock()
    spec = MagicMock()
    spec.tick_size = Decimal(str(tick_size))
    cfg.instruments = {symbol: spec}

    fsm = ManageFlowFSM(config=cfg)
    fsm.position_side = position_side
    fsm.symbol = symbol
    fsm.position_open_ts = 1700000000.0
    return fsm


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — stopPrice presence (Bug 1: FIX-1102)
# ─────────────────────────────────────────────────────────────────────────────

class TestStopPricePresence:
    """FIX-1102: stopPrice must be populated for every conditional order type."""

    @pytest.mark.parametrize("order_type,expect_stop", [
        ("STOP_MARKET",        True),   # classic SL — always worked
        ("TAKE_PROFIT_MARKET", True),   # FIX: "STOP" not in "TAKE_PROFIT_MARKET" was False
        ("STOP",               True),   # legacy alias
        ("TAKE_PROFIT",        True),   # legacy alias
        ("LIMIT",              False),  # no stopPrice for limit orders
        ("MARKET",             False),  # no stopPrice for market orders
    ])
    def test_stop_price_field_by_order_type(self, order_type, expect_stop):
        fsm = _manage()
        msg = _msg()
        result = fsm._emit_place_order(
            msg, "cid-test-01", order_type, "SELL", "0.01", "64000.0", "unit test"
        )
        pld = result.pld
        if expect_stop:
            assert pld["stopPrice"] == "64000.0", (
                f"{order_type}: expected stopPrice='64000.0', got {pld['stopPrice']!r}"
            )
        else:
            assert pld["stopPrice"] is None, (
                f"{order_type}: expected stopPrice=None, got {pld['stopPrice']!r}"
            )

    def test_take_profit_market_without_fix_would_have_been_none(self):
        """Regression guard: the old condition 'STOP' in 'TAKE_PROFIT_MARKET' is False."""
        assert "STOP" not in "TAKE_PROFIT_MARKET"  # documents the original bug

    def test_stop_price_equals_passed_price_arg(self):
        fsm = _manage()
        result = fsm._emit_place_order(
            _msg(), "cid-test-02", "TAKE_PROFIT_MARKET", "SELL", "0.01", "55555.5", "test"
        )
        assert result.pld["stopPrice"] == "55555.5"


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Client order ID length ≤ 36 chars (Bug 2: FIX-4015)
# ─────────────────────────────────────────────────────────────────────────────

class TestClientOrderIdLength:
    """FIX-4015: All bracket client order IDs must respect Binance 36-char limit."""

    # Realistic rid values that produced >36 char IDs before the fix
    RID_EXAMPLES = [
        "aurora_BTCUSDT_1771850999715",
        "aurora_SOLUSDT_1771850999715",
        "decision-rid-2026-02-23T14:30:00",
        "x" * 64,  # extreme case
    ]
    SYMBOLS = ["BTCUSDT", "DOGEUSDT", "SOLUSDT", "XRPUSDT"]

    @pytest.mark.parametrize("role", ["SL", "TP1", "TP2"])
    @pytest.mark.parametrize("symbol", SYMBOLS)
    def test_bracket_id_within_binance_limit(self, role, symbol):
        idem_base = f"aurora_{symbol}_1771850999715_1771850735"
        cid = generate_client_order_id(role, symbol, idempotent_key=idem_base)
        assert len(cid) <= BINANCE_CID_MAX, (
            f"[{role}/{symbol}] '{cid}' is {len(cid)} chars, limit is {BINANCE_CID_MAX}"
        )

    @pytest.mark.parametrize("symbol", SYMBOLS)
    def test_trailing_stop_id_within_limit(self, symbol):
        """Trailing stop idem key includes timestamp suffix — still must fit."""
        ts = 1771850864
        idem_base = f"aurora_{symbol}_1771850999715_1771850735_trail_{ts}"
        cid = generate_client_order_id("SL", symbol, idempotent_key=idem_base)
        assert len(cid) <= BINANCE_CID_MAX

    def test_ids_are_deterministic_for_same_input(self):
        """Idempotency: same inputs → same ID across multiple calls."""
        base = "aurora_BTCUSDT_12345_67890"
        ids = [generate_client_order_id("SL", "BTCUSDT", idempotent_key=base)
               for _ in range(5)]
        assert len(set(ids)) == 1, f"Expected deterministic ID, got {ids}"

    def test_sl_tp1_tp2_ids_are_distinct(self):
        """Different roles from the same position must produce different IDs."""
        base = "aurora_BTCUSDT_12345_67890"
        sl  = generate_client_order_id("SL",  "BTCUSDT", idempotent_key=base)
        tp1 = generate_client_order_id("TP1", "BTCUSDT", idempotent_key=base)
        tp2 = generate_client_order_id("TP2", "BTCUSDT", idempotent_key=base)
        assert sl != tp1
        assert sl != tp2
        assert tp1 != tp2

    def test_id_chars_allowed_by_binance(self):
        """Result must match Binance allowed character set: [A-Za-z0-9_-]."""
        cid = generate_client_order_id("SL", "ETHUSDT", idempotent_key="test_idem_456")
        assert re.match(r"^[A-Za-z0-9_\-]+$", cid), (
            f"Disallowed chars in client order ID: '{cid}'"
        )

    @pytest.mark.parametrize("rid", RID_EXAMPLES)
    def test_old_f_string_approach_would_exceed_limit(self, rid):
        """Documents why the fix was needed: raw f-string IDs exceeded limit."""
        position_id = f"{rid}_1771850735"
        old_sl_id  = f"{position_id}_sl"
        old_tp1_id = f"{position_id}_tp1"
        # At least one of these would have been > 36 chars for realistic rids
        exceeded = any(len(x) > BINANCE_CID_MAX for x in [old_sl_id, old_tp1_id])
        assert exceeded, (
            "Expected old-style IDs to exceed limit for this rid — test data may need update"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Side-aware price quantization (Bug 3: FIX-1111)
# ─────────────────────────────────────────────────────────────────────────────

class TestQuantizePricesSideAware:
    """FIX-1111: bracket prices must round in direction that avoids premature trigger."""

    def test_buy_position_sl_rounds_floor(self):
        """BUY position → SL is SELL bracket → FLOOR → no premature trigger."""
        fsm = _manage(position_side="BUY", tick_size=1.0)
        sl, _, _ = fsm._quantize_prices("BTCUSDT",
                                         Decimal("49999.7"), Decimal("51000.0"), None)
        assert sl == Decimal("49999"), f"Expected floor 49999, got {sl}"

    def test_sell_position_sl_rounds_ceil(self):
        """SELL position → SL is BUY bracket → CEIL → no premature trigger."""
        fsm = _manage(position_side="SELL", tick_size=1.0)
        sl, _, _ = fsm._quantize_prices("BTCUSDT",
                                         Decimal("50000.2"), Decimal("49000.0"), None)
        assert sl == Decimal("50001"), f"Expected ceil 50001, got {sl}"

    def test_price_on_tick_boundary_unchanged(self):
        """Prices already aligned to tick must not change under any side."""
        for side in ("BUY", "SELL"):
            fsm = _manage(position_side=side, tick_size=1.0)
            sl, _, _ = fsm._quantize_prices("BTCUSDT",
                                             Decimal("64000"), Decimal("65000"), None)
            assert sl == Decimal("64000"), f"side={side}: boundary price mutated to {sl}"

    def test_tp1_quantized_same_direction_as_sl(self):
        """TP1 uses the same bracket_side rounding as SL."""
        fsm = _manage(position_side="BUY", tick_size=1.0)
        # BUY → bracket_side = SELL → FLOOR
        _, tp1, _ = fsm._quantize_prices("BTCUSDT",
                                          Decimal("49000.0"), Decimal("51000.7"), None)
        assert tp1 == Decimal("51000"), f"TP1 should floor for BUY position, got {tp1}"

    def test_invalid_tick_size_raises_value_error(self):
        """Zero tick_size is fail-closed — must raise ValueError immediately."""
        cfg = MagicMock()
        spec = MagicMock()
        spec.tick_size = Decimal("0")
        cfg.instruments = {"BTCUSDT": spec}
        fsm = ManageFlowFSM(config=cfg)
        fsm.position_side = "BUY"
        with pytest.raises(ValueError, match="tick_size must be > 0"):
            fsm._quantize_prices("BTCUSDT", Decimal("50000"), None, None)


class TestBracketEmissionAfterSafetyOffset:
    """Regression for post-offset bracket prices staying on the tick lattice."""

    def test_place_brackets_resnaps_sl_and_tp1_after_offset(self, fsm_config):
        eth_spec = SimpleNamespace(
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("20"),
        )
        eth_spec.execution = SimpleNamespace(target_leverage=20)
        fsm_config.instruments["ETHUSDT"] = eth_spec
        fsm_config.trading.execution.manage.brackets = SimpleNamespace(
            offset_bps=5,
            working_type_default="MARK_PRICE",
            price_protect=True,
            oco_emulation=True,
        )

        fsm = ManageFlowFSM(config=fsm_config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_qty = Decimal("3.332")
        fsm.position_entry_price = Decimal("2359.54")
        fsm.position_open_ts = 1777230633.6956818
        fsm.closePosition = True
        fsm._intent_sl_price = Decimal("2351.39")
        fsm._intent_tp_price = Decimal("2382.08")

        result = fsm._place_brackets(
            _msg(symbol="ETHUSDT", rid="aurora_ETHUSDT_1777230600530")
        )

        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "BATCH"

        orders = result.pld["messages"]
        assert len(orders) == 2

        sl_pld = orders[0]["pld"]
        tp_pld = orders[1]["pld"]
        assert sl_pld["order_type"] == "STOP_MARKET"
        assert tp_pld["order_type"] == "TAKE_PROFIT_MARKET"
        assert "qty" not in sl_pld
        assert "qty" not in tp_pld
        assert sl_pld["reduceOnly"] is True
        assert tp_pld["reduceOnly"] is True

        for payload, expected_stop in (
            (sl_pld, Decimal("2350.21")),
            (tp_pld, Decimal("2383.27")),
        ):
            stop_price = payload["stopPrice"]
            assert stop_price == str(expected_stop)
            assert "e" not in stop_price.lower()
            assert Decimal(stop_price) % Decimal("0.01") == 0
