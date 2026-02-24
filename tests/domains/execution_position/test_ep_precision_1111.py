"""
EP-ORDER-PRECISION-1111 regression tests.

Focus:
- post-offset tick realignment in manage path
- deferred/WAL replay re-quantization
- SL/TP rounding-direction truth-table aligned with open-flow SSOT
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.contracts import TPSLValidationRules
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from apps.reference.domains.execution_position.utils import quantize_stop_price


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decimal_places(value_str: str) -> int:
    """Return number of significant decimal places in a numeric string."""
    if "." not in str(value_str):
        return 0
    _integer_part, frac_part = str(value_str).split(".", 1)
    return len(frac_part.rstrip("0")) if frac_part.rstrip("0") else 0



def _build_manage(fsm_config, position_side: str = "BUY") -> ManageFlowFSM:
    m = ManageFlowFSM(config=fsm_config)
    m.symbol = "BTCUSDT"
    m.position_side = position_side
    m.position_entry_price = Decimal("50000.0")
    m.position_qty = Decimal("0.001")
    m.position_open_ts = 1_000_000
    return m


# ---------------------------------------------------------------------------
# A) Safety offset breaks tick alignment
# ---------------------------------------------------------------------------


class TestSafetyOffsetBreaksTick:
    """Documents root cause: add_safety_offset can produce non-tick multiples."""

    @pytest.mark.parametrize(
        "price_str,tick_str,offset_bps",
        [
            ("62890.9", "0.1", 5),
            ("76.07", "0.01", 5),
            ("0.09048", "0.00001", 5),
            ("1.3402", "0.0001", 5),
        ],
    )
    def test_safety_offset_is_not_tick_multiple(self, price_str, tick_str, offset_bps):
        price = Decimal(price_str)
        tick = Decimal(tick_str)
        offset = TPSLValidationRules.add_safety_offset(price, tick, offset_bps)

        if offset > tick:
            remainder = offset % tick
            assert remainder != 0

    def test_offset_subtraction_destroys_alignment_btcusdt(self):
        sl = Decimal("62890.9")
        tick = Decimal("0.1")
        offset = TPSLValidationRules.add_safety_offset(sl, tick, 5)
        raw_sl = sl - offset

        dp = _decimal_places(str(raw_sl))
        tick_dp = _decimal_places(str(tick))
        assert dp > tick_dp

    def test_offset_subtraction_destroys_alignment_solusdt(self):
        sl = Decimal("76.07")
        tick = Decimal("0.01")
        offset = TPSLValidationRules.add_safety_offset(sl, tick, 5)
        raw_sl = sl - offset

        dp = _decimal_places(str(raw_sl))
        tick_dp = _decimal_places(str(tick))
        assert dp > tick_dp


# ---------------------------------------------------------------------------
# B) _place_brackets() must emit tick-aligned stopPrice
# ---------------------------------------------------------------------------


class TestPlaceBracketsQuantizesAfterOffset:
    """Manage path: post-offset prices must be tick-aligned and direction-correct."""

    def _get_stop_prices(self, result: Message) -> dict:
        assert result is not None, "_place_brackets returned None"
        assert result.verb == "BATCH", f"Expected BATCH, got {result.verb}"
        prices = {}
        for msg_dict in result.pld["messages"]:
            ot = msg_dict["pld"]["order_type"]
            sp = msg_dict["pld"]["stopPrice"]
            prices[ot] = str(sp)
        return prices

    def test_sl_stopPrice_tick_aligned_buy_position(self, fsm_config):
        m = _build_manage(fsm_config, "BUY")
        m._intent_sl_price = Decimal("49975.10")
        m._intent_tp_price = Decimal("50025.10")

        msg = Message(
            op="EVT",
            verb="POSITION_OPENED",
            src="test",
            dst="execution_position",
            pld={"symbol": "BTCUSDT"},
        )
        result = m._place_brackets(msg)

        prices = self._get_stop_prices(result)
        sl_str = prices.get("STOP_MARKET")
        assert sl_str is not None

        dp = _decimal_places(sl_str)
        assert dp <= 2
        # LONG SL: SELL/FLOOR
        assert sl_str == "49950.11"

    def test_tp_stopPrice_tick_aligned_buy_position(self, fsm_config):
        m = _build_manage(fsm_config, "BUY")
        m._intent_sl_price = Decimal("49975.10")
        m._intent_tp_price = Decimal("50025.10")

        msg = Message(
            op="EVT",
            verb="POSITION_OPENED",
            src="test",
            dst="execution_position",
            pld={"symbol": "BTCUSDT"},
        )
        result = m._place_brackets(msg)

        prices = self._get_stop_prices(result)
        tp_str = prices.get("TAKE_PROFIT_MARKET")
        assert tp_str is not None

        dp = _decimal_places(tp_str)
        assert dp <= 2
        # LONG TP: BUY/CEIL
        assert tp_str == "50050.12"

    def test_sl_stopPrice_tick_aligned_sell_position(self, fsm_config):
        m = _build_manage(fsm_config, "SELL")
        m._intent_sl_price = Decimal("50025.10")
        m._intent_tp_price = Decimal("49975.10")

        msg = Message(
            op="EVT",
            verb="POSITION_OPENED",
            src="test",
            dst="execution_position",
            pld={"symbol": "BTCUSDT"},
        )
        result = m._place_brackets(msg)

        prices = self._get_stop_prices(result)
        sl_str = prices.get("STOP_MARKET")
        assert sl_str is not None

        dp = _decimal_places(sl_str)
        assert dp <= 2
        # SHORT SL: BUY/CEIL
        assert sl_str == "50050.12"

    def test_tp_stopPrice_rounding_direction_sell_position(self, fsm_config):
        m = _build_manage(fsm_config, "SELL")
        m._intent_sl_price = Decimal("50025.10")
        m._intent_tp_price = Decimal("49975.10")

        msg = Message(
            op="EVT",
            verb="POSITION_OPENED",
            src="test",
            dst="execution_position",
            pld={"symbol": "BTCUSDT"},
        )
        result = m._place_brackets(msg)

        prices = self._get_stop_prices(result)
        tp_str = prices.get("TAKE_PROFIT_MARKET")
        assert tp_str is not None
        # SHORT TP: SELL/FLOOR
        assert tp_str == "49950.11"

    def test_stopPrice_is_exact_tick_multiple(self, fsm_config):
        m = _build_manage(fsm_config, "BUY")
        m._intent_sl_price = Decimal("49975.10")
        m._intent_tp_price = Decimal("50025.10")

        msg = Message(
            op="EVT",
            verb="POSITION_OPENED",
            src="test",
            dst="execution_position",
            pld={"symbol": "BTCUSDT"},
        )
        result = m._place_brackets(msg)
        prices = self._get_stop_prices(result)

        tick = Decimal(str(fsm_config.instruments["BTCUSDT"].tick_size))
        for _order_type, price_str in prices.items():
            price_dec = Decimal(price_str)
            assert price_dec % tick == 0


# ---------------------------------------------------------------------------
# C) _place_deferred_brackets() must re-quantize raw bracket_data
# ---------------------------------------------------------------------------


class TestPlaceDeferredBracketsRequantizes:
    """Deferred path: re-quantize before adapter calls (including WAL replay)."""

    def _configure_fsm(self, fsm) -> None:
        bc = MagicMock()
        bc.tp_widen_first_bps = 5
        bc.tp_widen_second_bps = 10
        bc.retry_backoff_ms = [100, 200, 400]
        fsm.config.domains.execution_position.bracket_placement = bc

    @pytest.mark.asyncio
    async def test_unquantized_sl_gets_quantized(self, fsm_harness):
        fsm, _bus, _cfg = fsm_harness
        self._configure_fsm(fsm)

        mock_adapter = MagicMock()
        mock_adapter.place_stop_market_close_position = AsyncMock(
            return_value={"orderId": "SL-111", "clientOrderId": "SL-cid"}
        )
        mock_adapter.place_take_profit_market_close_position = AsyncMock(
            return_value={"orderId": "TP-222", "clientOrderId": "TP-cid"}
        )
        fsm.adapter = mock_adapter
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm._preflight_position_check = AsyncMock(return_value=True)

        bracket_data = {
            "symbol": "BTCUSDT",
            "side": "BUY",  # LONG
            "sl": 76.031965,
            "tp": 76.419035,
            "qty": 5.0,
            "rid": "test-rid-deferred",
            "idem_key": "test-idem-1",
            "tick_size": 0.01,
            "corr_id": None,
            "oco_group_id": None,
            "entry_client_order_id": None,
        }

        await fsm._place_deferred_brackets("entry-ord-100", bracket_data)

        sl_str = mock_adapter.place_stop_market_close_position.call_args[0][2]
        assert _decimal_places(sl_str) <= 2
        assert sl_str == "76.03"  # LONG SL: SELL/FLOOR

    @pytest.mark.asyncio
    async def test_unquantized_tp_gets_quantized(self, fsm_harness):
        fsm, _bus, _cfg = fsm_harness
        self._configure_fsm(fsm)

        mock_adapter = MagicMock()
        mock_adapter.place_stop_market_close_position = AsyncMock(
            return_value={"orderId": "SL-333", "clientOrderId": "SL-cid"}
        )
        mock_adapter.place_take_profit_market_close_position = AsyncMock(
            return_value={"orderId": "TP-444", "clientOrderId": "TP-cid"}
        )
        fsm.adapter = mock_adapter
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm._preflight_position_check = AsyncMock(return_value=True)

        bracket_data = {
            "symbol": "BTCUSDT",
            "side": "BUY",  # LONG
            "sl": 76.03,
            "tp": 76.419035,
            "qty": 5.0,
            "rid": "test-rid-deferred-tp",
            "idem_key": "test-idem-2",
            "tick_size": 0.01,
            "corr_id": None,
            "oco_group_id": None,
            "entry_client_order_id": None,
        }

        await fsm._place_deferred_brackets("entry-ord-200", bracket_data)

        tp_str = mock_adapter.place_take_profit_market_close_position.call_args[0][2]
        assert _decimal_places(tp_str) <= 2
        assert tp_str == "76.42"  # LONG TP: BUY/CEIL

    @pytest.mark.asyncio
    async def test_already_quantized_values_pass_through(self, fsm_harness):
        fsm, _bus, _cfg = fsm_harness
        self._configure_fsm(fsm)

        mock_adapter = MagicMock()
        mock_adapter.place_stop_market_close_position = AsyncMock(
            return_value={"orderId": "SL-555"}
        )
        mock_adapter.place_take_profit_market_close_position = AsyncMock(
            return_value={"orderId": "TP-666"}
        )
        fsm.adapter = mock_adapter
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm._preflight_position_check = AsyncMock(return_value=True)

        bracket_data = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "sl": 76.03,
            "tp": 76.42,
            "qty": 5.0,
            "rid": "test-rid-pass",
            "idem_key": "test-idem-3",
            "tick_size": 0.01,
            "corr_id": None,
            "oco_group_id": None,
            "entry_client_order_id": None,
        }

        await fsm._place_deferred_brackets("entry-ord-300", bracket_data)

        sl_call = mock_adapter.place_stop_market_close_position.call_args
        tp_call = mock_adapter.place_take_profit_market_close_position.call_args
        assert sl_call[0][2] == "76.03"
        assert tp_call[0][2] == "76.42"

    @pytest.mark.asyncio
    async def test_short_side_quantization_directions(self, fsm_harness):
        fsm, _bus, _cfg = fsm_harness
        self._configure_fsm(fsm)

        mock_adapter = MagicMock()
        mock_adapter.place_stop_market_close_position = AsyncMock(
            return_value={"orderId": "SL-777"}
        )
        mock_adapter.place_take_profit_market_close_position = AsyncMock(
            return_value={"orderId": "TP-888"}
        )
        fsm.adapter = mock_adapter
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm._preflight_position_check = AsyncMock(return_value=True)

        bracket_data = {
            "symbol": "BTCUSDT",
            "side": "SELL",  # SHORT
            "sl": 50050.111,
            "tp": 49950.119,
            "qty": 5.0,
            "rid": "test-rid-short",
            "idem_key": "test-idem-short",
            "tick_size": 0.01,
            "corr_id": None,
            "oco_group_id": None,
            "entry_client_order_id": None,
        }

        await fsm._place_deferred_brackets("entry-ord-400", bracket_data)

        sl_call = mock_adapter.place_stop_market_close_position.call_args
        tp_call = mock_adapter.place_take_profit_market_close_position.call_args
        assert sl_call[0][2] == "50050.12"  # SHORT SL: BUY/CEIL
        assert tp_call[0][2] == "49950.11"  # SHORT TP: SELL/FLOOR

    @pytest.mark.asyncio
    async def test_wal_replay_requantizes_before_adapter_call(self, fsm_harness, tmp_path):
        from vfoundation import config as vf_config
        from vfoundation.dr import wal as wal_mod
        from apps.reference.domains.execution_position.pending_brackets_wal import (
            read_pending_brackets_from_wal,
            write_pending_brackets_stored,
        )

        wal_dir = tmp_path / "ep1111_wal"
        wal_dir.mkdir(parents=True, exist_ok=True)
        old_cfg_wal_dir = vf_config.config.wal_dir
        old_wal_dir = wal_mod.WAL_DIR

        try:
            vf_config.config.wal_dir = wal_dir
            wal_mod.set_wal_dir(wal_dir)
            write_pending_brackets_stored(
                entry_order_id="entry-wal-001",
                symbol="BTCUSDT",
                side="BUY",
                sl=76.031965,
                tp=76.419035,
                qty=5.0,
                rid="rid-wal-001",
                idem_key="idem-wal-001",
                tick_size=0.01,
                corr_id=None,
                oco_group_id=None,
                entry_client_order_id=None,
            )
            restored = read_pending_brackets_from_wal()
        finally:
            vf_config.config.wal_dir = old_cfg_wal_dir
            wal_mod.set_wal_dir(old_wal_dir)

        assert "entry-wal-001" in restored

        fsm, _bus, _cfg = fsm_harness
        self._configure_fsm(fsm)
        mock_adapter = MagicMock()
        mock_adapter.place_stop_market_close_position = AsyncMock(
            return_value={"orderId": "SL-WAL"}
        )
        mock_adapter.place_take_profit_market_close_position = AsyncMock(
            return_value={"orderId": "TP-WAL"}
        )
        fsm.adapter = mock_adapter
        fsm.order_guardian.should_place_brackets = AsyncMock(return_value=True)
        fsm._preflight_position_check = AsyncMock(return_value=True)

        await fsm._place_deferred_brackets("entry-wal-001", restored["entry-wal-001"])

        sl_str = mock_adapter.place_stop_market_close_position.call_args[0][2]
        tp_str = mock_adapter.place_take_profit_market_close_position.call_args[0][2]
        tick = Decimal("0.01")

        assert Decimal(sl_str) % tick == 0
        assert Decimal(tp_str) % tick == 0
        assert sl_str == "76.03"
        assert tp_str == "76.42"


# ---------------------------------------------------------------------------
# D) WAL storage: bracket_data stored in _pending_brackets must be tick-aligned
# ---------------------------------------------------------------------------


class TestWalPendingBracketsStoreQuantized:
    """
    D) Values written to _pending_brackets (which feeds the WAL) must be tick-aligned.

    fsm.py quantizes sl/tp before storing in _pending_brackets.
    """

    @pytest.mark.parametrize(
        "raw_sl,raw_tp,tick_size,side,tick_dp",
        [
            ("49950.11245", "50050.112550", 0.01, "BUY", 2),
            ("76.031965", "76.419035", 0.01, "BUY", 2),
            ("50025.112450", "49974.887450", 0.01, "SELL", 2),
        ],
    )
    def test_quantize_before_storage_produces_tick_aligned(
        self, raw_sl, raw_tp, tick_size, side, tick_dp
    ):
        sl_stored = quantize_stop_price(
            float(raw_sl), tick_size, side="SELL" if side == "BUY" else "BUY"
        )
        tp_stored = quantize_stop_price(
            float(raw_tp), tick_size, side="BUY" if side == "BUY" else "SELL"
        )

        sl_dp = _decimal_places(str(sl_stored))
        tp_dp = _decimal_places(str(tp_stored))

        assert sl_dp <= tick_dp
        assert tp_dp <= tick_dp

    def test_quantize_parametrized_from_forensic_doc(self):
        cases = [
            # (raw_stopPrice, tick_size, quantizer_side, expected_quantized)
            ("62859.45455", 0.1, "SELL", "62859.4"),
            ("63712.8405", 0.1, "BUY", "63712.9"),
            ("76.031965", 0.01, "SELL", "76.03"),
            ("76.419035", 0.01, "BUY", "76.42"),
            ("0.09043476", 0.00001, "SELL", "0.09043"),
            ("0.091495725", 0.00001, "BUY", "0.09150"),
            ("1.3395299", 0.0001, "SELL", "1.3395"),
            # SHORT direction checks
            ("50050.111", 0.01, "BUY", "50050.12"),
            ("49950.119", 0.01, "SELL", "49950.11"),
        ]
        for raw, tick, side, expected in cases:
            result = quantize_stop_price(float(raw), tick, side=side)
            tick_dp = _decimal_places(str(Decimal(str(tick))))
            result_str = f"{result:.{tick_dp}f}"
            assert result_str == expected
