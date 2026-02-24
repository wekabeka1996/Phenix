"""
Tests for fsm_manage.py bracket bug fixes:
- Fix 1: -1102 — stopPrice must be set for TAKE_PROFIT_MARKET
- Fix 2: -4015 — clientOrderId must be <= 36 chars (Binance limit)
- Fix 3: -1111 — price quantization must use side-aware rounding
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.domains.execution_position.utils import (
    generate_client_order_id,
    quantize_stop_price,
)


# ---------------------------------------------------------------------------
# Fix 1: -1102 — stopPrice presence for conditional order types
# ---------------------------------------------------------------------------


class TestStopPricePresence:
    """Verify stopPrice is set for all conditional order types (fix for -1102)."""

    def _build_manage(self, fsm_config) -> ManageFlowFSM:
        m = ManageFlowFSM(config=fsm_config)
        m.symbol = "BTCUSDT"
        m.position_side = "BUY"
        m._manage_cfg = fsm_config.trading.execution.manage
        return m

    @pytest.mark.parametrize("order_type,expect_stop_price", [
        ("STOP_MARKET", True),
        ("TAKE_PROFIT_MARKET", True),
        ("STOP", True),
        ("TAKE_PROFIT", True),
        ("LIMIT", False),
        ("MARKET", False),
    ])
    def test_stop_price_set_correctly(self, fsm_config, order_type, expect_stop_price):
        """stopPrice must be non-None for conditional orders, None for LIMIT/MARKET."""
        m = self._build_manage(fsm_config)

        msg = Message(
            op="DEC", verb="PLACE_ORDER", src="test", dst="test",
            pld={"symbol": "BTCUSDT"},
        )

        result = m._emit_place_order(
            msg, "CID-test-01", order_type, "SELL", "0.01", "50000.0", "test",
        )
        pld = result.pld

        if expect_stop_price:
            assert pld["stopPrice"] is not None, (
                f"{order_type} must have stopPrice, got None"
            )
            assert pld["stopPrice"] == "50000.0"
        else:
            assert pld["stopPrice"] is None, (
                f"{order_type} must NOT have stopPrice"
            )


# ---------------------------------------------------------------------------
# Fix 2: -4015 — clientOrderId length <= 36 chars
# ---------------------------------------------------------------------------


class TestClientOrderIdLength:
    """Verify generated client order IDs never exceed Binance's 36-char limit."""

    BINANCE_MAX_LEN = 36

    @pytest.mark.parametrize("rid,ts", [
        ("aurora_BTCUSDT_1771850999715", 1771850735),
        ("a64015ed-406e-4037-abfd-dd921cf3a9b4", 1771850735),
        ("x" * 60, 9999999999),
        ("rid-short", 1),
    ])
    def test_bracket_client_ids_within_limit(self, rid, ts):
        """SL/TP1/TP2 client IDs must be <= 36 chars regardless of input length."""
        idem_base = f"{rid}_{ts}"
        sl_id = generate_client_order_id(
            "SL", "BTCUSDT", idempotent_key=idem_base)
        tp1_id = generate_client_order_id(
            "TP", "BTCUSDT", idempotent_key=f"{idem_base}_1")
        tp2_id = generate_client_order_id(
            "TP", "BTCUSDT", idempotent_key=f"{idem_base}_2")

        assert len(
            sl_id) <= self.BINANCE_MAX_LEN, f"SL id too long: {len(sl_id)}"
        assert len(
            tp1_id) <= self.BINANCE_MAX_LEN, f"TP1 id too long: {len(tp1_id)}"
        assert len(
            tp2_id) <= self.BINANCE_MAX_LEN, f"TP2 id too long: {len(tp2_id)}"

    @pytest.mark.parametrize("rid,ts,trail_ts", [
        ("aurora_BTCUSDT_1771850999715", 1771850735, 1771850800),
        ("a64015ed-406e-4037-abfd-dd921cf3a9b4", 1771850735, 1771850800),
        ("x" * 60, 9999999999, 9999999999),
    ])
    def test_trailing_stop_client_id_within_limit(self, rid, ts, trail_ts):
        """Trailing-stop SL client ID must also be <= 36 chars."""
        idem_trail = f"{rid}_{ts}_trail_{trail_ts}"
        trail_id = generate_client_order_id(
            "SL", "BTCUSDT", idempotent_key=idem_trail)

        assert len(
            trail_id) <= self.BINANCE_MAX_LEN, f"Trail id too long: {len(trail_id)}"

    def test_deterministic_same_inputs(self):
        """Same inputs must produce same output (idempotency)."""
        a = generate_client_order_id("SL", "BTCUSDT", idempotent_key="key1")
        b = generate_client_order_id("SL", "BTCUSDT", idempotent_key="key1")
        assert a == b

    def test_different_inputs_produce_different_ids(self):
        """Different idempotent_key must produce different IDs."""
        a = generate_client_order_id("SL", "BTCUSDT", idempotent_key="key1")
        b = generate_client_order_id("SL", "BTCUSDT", idempotent_key="key2")
        assert a != b


# ---------------------------------------------------------------------------
# Fix 3: -1111 — side-aware price quantization
# ---------------------------------------------------------------------------


class TestQuantizePricesSideAware:
    """Verify _quantize_prices uses directional rounding via quantize_stop_price."""

    def _build_manage(self, fsm_config, position_side: str) -> ManageFlowFSM:
        m = ManageFlowFSM(config=fsm_config)
        m.symbol = "BTCUSDT"
        m.position_side = position_side
        return m

    def test_buy_position_uses_floor_rounding(self, fsm_config):
        """BUY position -> SELL brackets -> FLOOR (round down)."""
        m = self._build_manage(fsm_config, "BUY")

        # tick_size = 0.01 from conftest btc_spec
        sl, tp1, tp2 = m._quantize_prices(
            "BTCUSDT",
            Decimal("50000.126"),  # Not on tick boundary
            Decimal("51000.789"),
            None,
        )

        # SELL side -> FLOOR: 50000.126 -> 50000.12, 51000.789 -> 51000.78
        assert sl == Decimal("50000.12")
        assert tp1 == Decimal("51000.78")
        assert tp2 is None

    def test_sell_position_uses_ceil_rounding(self, fsm_config):
        """SELL position -> BUY brackets -> CEIL (round up)."""
        m = self._build_manage(fsm_config, "SELL")

        sl, tp1, tp2 = m._quantize_prices(
            "BTCUSDT",
            Decimal("50000.121"),
            Decimal("49000.001"),
            None,
        )

        # BUY side -> CEIL: 50000.121 -> 50000.13, 49000.001 -> 49000.01
        assert sl == Decimal("50000.13")
        assert tp1 == Decimal("49000.01")
        assert tp2 is None

    def test_exact_tick_boundary_unchanged(self, fsm_config):
        """Prices already on tick boundary must not change."""
        m = self._build_manage(fsm_config, "BUY")

        sl, tp1, _ = m._quantize_prices(
            "BTCUSDT",
            Decimal("50000.10"),
            Decimal("51000.00"),
            None,
        )

        assert sl == Decimal("50000.1")
        assert tp1 == Decimal("51000.0")

    def test_missing_symbol_raises(self, fsm_config):
        """FAIL-CLOSED: missing symbol must raise ValueError."""
        m = self._build_manage(fsm_config, "BUY")

        with pytest.raises(ValueError, match="symbol is required"):
            m._quantize_prices(None, Decimal("100"), Decimal("200"), None)

    def test_missing_instrument_raises(self, fsm_config):
        """FAIL-CLOSED: unknown instrument must raise ValueError."""
        m = self._build_manage(fsm_config, "BUY")

        with pytest.raises(ValueError, match="tick_size is required"):
            m._quantize_prices("UNKNOWNUSDT", Decimal(
                "100"), Decimal("200"), None)
