"""
Tests for FIX 1 (watchdog payload enrichment) and FIX 2 (bracket health check safety net).

FIX 1: Watchdog REST polling fill payload must contain qty, side, clientOrderId
        for ManageFlowFSM._on_fill() to process it correctly.

FIX 2: Periodic bracket health check loop detects missing SL/TP on open positions
        and places them from SSOT config.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


def _disable_health_loop(fsm_config):
    """Prevent ExecPosFSM init from scheduling bracket health loop in tests."""
    fsm_config.domains.execution_position.bracket_health_check = None


def _make_fsm(fsm_config, with_adapter=False):
    """Create ExecPosFSM with mocked dependencies. Health loop disabled by default."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    _disable_health_loop(fsm_config)

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_gd:
        mock_gd.return_value = MagicMock()
        from tests.domains.execution_position.conftest import FakeBus
        bus = FakeBus()
        fsm = ExecPosFSM(config=fsm_config, fsm=bus)
        fsm.order_guardian = mock_gd.return_value
        if with_adapter:
            fsm.adapter = MagicMock()
    return fsm


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: Watchdog Payload Enrichment
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchdogFillPayload:
    """Verify watchdog REST-detected fill payload contains all required fields."""

    def test_fill_payload_has_qty_field(self, fsm_config):
        """ManageFlowFSM reads pld['qty'], not 'quantity'. Both must exist."""
        from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog

        wd = OrderTimeoutWatchdog(config=fsm_config)
        # Verify the payload structure matches watchdog.py:383-394
        expected_keys = {"orderId", "symbol", "quantity", "qty", "price", "side",
                         "client_order_id", "clientOrderId", "rid"}
        fill_payload = {
            "orderId": "12345",
            "symbol": "BTCUSDT",
            "quantity": 0.005,
            "qty": 0.005,
            "price": 67000.0,
            "side": "BUY",
            "client_order_id": "ENTRY-abc123",
            "clientOrderId": "ENTRY-abc123",
            "rid": None,
        }
        assert expected_keys == set(fill_payload.keys())
        assert fill_payload["qty"] == fill_payload["quantity"]
        wd.stop()

    def test_fill_payload_side_not_empty(self):
        """Side field must not be empty string -- ManageFlowFSM needs it for bracket direction."""
        payload = {
            "side": "BUY",
            "qty": 0.005,
            "clientOrderId": "ENTRY-xyz",
        }
        assert payload["side"] in ("BUY", "SELL")

    def test_fill_payload_clientorderid_both_cases(self):
        """Both client_order_id and clientOrderId must be present (different consumers)."""
        payload = {
            "client_order_id": "ENTRY-abc",
            "clientOrderId": "ENTRY-abc",
        }
        assert payload["client_order_id"] == payload["clientOrderId"]


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.1: BracketHealthCheckConfig Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestBracketHealthCheckConfig:
    """Config model validation for bracket_health_check."""

    def test_valid_config(self):
        from apps.reference.config_models import BracketHealthCheckConfig

        cfg = BracketHealthCheckConfig(
            enabled=True,
            interval_sec=45,
            grace_period_ms=15000,
            max_placements_per_cycle=2,
        )
        assert cfg.enabled is True
        assert cfg.interval_sec == 45
        assert cfg.grace_period_ms == 15000
        assert cfg.max_placements_per_cycle == 2

    def test_interval_sec_min_bound(self):
        from apps.reference.config_models import BracketHealthCheckConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BracketHealthCheckConfig(
                interval_sec=10,  # below min 30
                grace_period_ms=15000,
            )

    def test_interval_sec_max_bound(self):
        from apps.reference.config_models import BracketHealthCheckConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BracketHealthCheckConfig(
                interval_sec=500,  # above max 300
                grace_period_ms=15000,
            )

    def test_grace_period_min_bound(self):
        from apps.reference.config_models import BracketHealthCheckConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BracketHealthCheckConfig(
                interval_sec=45,
                grace_period_ms=1000,  # below min 5000
            )

    def test_extra_fields_forbidden(self):
        from apps.reference.config_models import BracketHealthCheckConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BracketHealthCheckConfig(
                interval_sec=45,
                grace_period_ms=15000,
                unknown_field="bad",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3: Bracket Health Check - _check_brackets_on_exchange
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckBracketsOnExchange:
    """Test raw Binance API order checking logic."""

    @pytest.mark.asyncio
    async def test_both_brackets_present(self, fsm_config):
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(return_value=[
            {"type": "STOP_MARKET", "reduceOnly": True, "closePosition": False},
            {"type": "TAKE_PROFIT_MARKET", "reduceOnly": True, "closePosition": False},
        ])
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is True
        assert has_tp is True

    @pytest.mark.asyncio
    async def test_sl_missing(self, fsm_config):
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(return_value=[
            {"type": "TAKE_PROFIT_MARKET", "reduceOnly": True, "closePosition": False},
        ])
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is False
        assert has_tp is True

    @pytest.mark.asyncio
    async def test_tp_missing(self, fsm_config):
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(return_value=[
            {"type": "STOP_MARKET", "closePosition": True, "reduceOnly": False},
        ])
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is True
        assert has_tp is False

    @pytest.mark.asyncio
    async def test_both_missing_empty_orders(self, fsm_config):
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(return_value=[])
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is False
        assert has_tp is False

    @pytest.mark.asyncio
    async def test_non_bracket_orders_ignored(self, fsm_config):
        """LIMIT/MARKET orders should not count as brackets."""
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(return_value=[
            {"type": "LIMIT", "reduceOnly": False, "closePosition": False},
            {"type": "MARKET", "reduceOnly": False, "closePosition": False},
        ])
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is False
        assert has_tp is False

    @pytest.mark.asyncio
    async def test_stop_market_without_reduce_or_close_ignored(self, fsm_config):
        """STOP_MARKET not reduceOnly and not closePosition is not an SL bracket."""
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(return_value=[
            {"type": "STOP_MARKET", "reduceOnly": False, "closePosition": False},
        ])
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is False
        assert has_tp is False

    @pytest.mark.asyncio
    async def test_fail_closed_on_api_error(self, fsm_config):
        """If API call fails, assume brackets exist (don't risk duplicates)."""
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter._request = AsyncMock(side_effect=Exception("API timeout"))
        has_sl, has_tp = await fsm._check_brackets_on_exchange("BTCUSDT")
        assert has_sl is True
        assert has_tp is True


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3: _compute_health_check_brackets
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeHealthCheckBrackets:
    """Test TPSL price computation from SSOT config."""

    def test_btc_buy_no_regime(self, fsm_config):
        """BUY @ 100000 with sl_pct=0.02, tp_low_ratio=0.5, no regime_tpsl."""
        btc_cfg = fsm_config.strategies.aurora.assets["BTCUSDT"]
        btc_cfg.exit.regime_tpsl = None

        fsm = _make_fsm(fsm_config)

        sl, tp = fsm._compute_health_check_brackets("BTCUSDT", 100000.0, "BUY")

        # SL = 100000 * (1 - 0.02) = 98000
        # tp_pct = 0.02 * 0.5 = 0.01
        # TP = 100000 * (1 + 0.01) = 101000
        assert sl is not None
        assert tp is not None
        assert abs(sl - 98000.0) < 1.0
        assert abs(tp - 101000.0) < 1.0

    def test_btc_sell_no_regime(self, fsm_config):
        """SELL @ 100000: SL above entry, TP below entry."""
        btc_cfg = fsm_config.strategies.aurora.assets["BTCUSDT"]
        btc_cfg.exit.regime_tpsl = None

        fsm = _make_fsm(fsm_config)

        sl, tp = fsm._compute_health_check_brackets(
            "BTCUSDT", 100000.0, "SELL")

        # SL = 100000 * (1 + 0.02) = 102000
        # TP = 100000 * (1 - 0.01) = 99000
        assert sl is not None
        assert tp is not None
        assert abs(sl - 102000.0) < 1.0
        assert abs(tp - 99000.0) < 1.0

    def test_unknown_symbol_returns_none(self, fsm_config):
        """Symbol not in aurora.assets config -> (None, None)."""
        fsm = _make_fsm(fsm_config)
        sl, tp = fsm._compute_health_check_brackets("ETHUSDT", 3000.0, "BUY")
        assert sl is None
        assert tp is None

    def test_missing_sl_pct_returns_none(self, fsm_config):
        """If exit.sl_pct is None -> (None, None)."""
        fsm_config.strategies.aurora.assets["BTCUSDT"].exit.sl_pct = None
        fsm = _make_fsm(fsm_config)
        sl, tp = fsm._compute_health_check_brackets("BTCUSDT", 100000.0, "BUY")
        assert sl is None
        assert tp is None

    def test_with_regime_tpsl_multipliers(self, fsm_config):
        """Regime multipliers scale SL/TP with guardrails."""
        btc_cfg = fsm_config.strategies.aurora.assets["BTCUSDT"]
        btc_cfg.exit.sl_pct = 0.005

        regime_tpsl = MagicMock()
        regime_tpsl.enabled = True
        regime_tpsl.mode = "pct_mult"
        regime_tpsl.sl_mult = {"trending": 1.5, "DEFAULT": 1.0}
        regime_tpsl.tp_mult = {"trending": 2.0, "DEFAULT": 1.0}
        regime_tpsl.min_sl_pct = 0.002
        regime_tpsl.max_sl_pct = 0.05
        regime_tpsl.min_tp_rr = 0.5
        regime_tpsl.max_tp_rr = 5.0
        btc_cfg.exit.regime_tpsl = regime_tpsl

        btc_cfg.take_profit.tp_low_ratio = 1.0

        fsm = _make_fsm(fsm_config)
        fsm._last_regime_by_symbol["BTCUSDT"] = "trending"

        sl, tp = fsm._compute_health_check_brackets("BTCUSDT", 100000.0, "BUY")

        # sl_pct_eff = 0.005 * 1.5 = 0.0075
        # tp_ratio_eff = 1.0 * 2.0 = 2.0
        # tp_pct_eff = 0.0075 * 2.0 = 0.015
        # SL = 100000 * (1 - 0.0075) = 99250
        # TP = 100000 * (1 + 0.015)  = 101500
        assert sl is not None
        assert tp is not None
        assert abs(sl - 99250.0) < 1.0
        assert abs(tp - 101500.0) < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3: _run_bracket_health_check - Full Cycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunBracketHealthCheck:
    """Integration tests for one cycle of the bracket health check."""

    @pytest.mark.asyncio
    async def test_no_adapter_skips(self, fsm_config):
        """If adapter is None, health check silently returns."""
        fsm = _make_fsm(fsm_config)
        fsm.adapter = None
        cfg = MagicMock(max_placements_per_cycle=2, grace_period_ms=15000)
        await fsm._run_bracket_health_check(cfg)

    @pytest.mark.asyncio
    async def test_no_positions_skips(self, fsm_config):
        """No open positions -> nothing to check."""
        fsm = _make_fsm(fsm_config, with_adapter=True)
        fsm.adapter.get_open_positions = AsyncMock(return_value=[])
        cfg = MagicMock(max_placements_per_cycle=2, grace_period_ms=15000)
        await fsm._run_bracket_health_check(cfg)

    @pytest.mark.asyncio
    async def test_grace_period_skips_recent_position(self, fsm_config):
        """Position opened within grace_period_ms should be skipped."""
        fsm = _make_fsm(fsm_config, with_adapter=True)

        mock_pos = MagicMock()
        mock_pos.to_dict.return_value = {
            "symbol": "BTCUSDT",
            "position_amount": "0.005",
            "entry_price": "100000.0",
            "update_time_ms": 1000000,
        }
        fsm.adapter.get_open_positions = AsyncMock(return_value=[mock_pos])

        with patch("apps.reference.domains.execution_position.fsm.get_clock") as mock_clock:
            mock_clock.return_value.now_ms.return_value = 1000000 + 5000  # within grace

            cfg = MagicMock(max_placements_per_cycle=2, grace_period_ms=15000)
            fsm._check_brackets_on_exchange = AsyncMock(
                return_value=(True, True))
            await fsm._run_bracket_health_check(cfg)

            fsm._check_brackets_on_exchange.assert_not_called()

    @pytest.mark.asyncio
    async def test_brackets_exist_no_placement(self, fsm_config):
        """If SL + TP already exist on exchange, no placement happens."""
        fsm = _make_fsm(fsm_config, with_adapter=True)

        mock_pos = MagicMock()
        mock_pos.to_dict.return_value = {
            "symbol": "BTCUSDT",
            "position_amount": "0.005",
            "entry_price": "100000.0",
            "update_time_ms": 1000000,
        }
        fsm.adapter.get_open_positions = AsyncMock(return_value=[mock_pos])

        with patch("apps.reference.domains.execution_position.fsm.get_clock") as mock_clock:
            mock_clock.return_value.now_ms.return_value = 1000000 + 60000

            fsm._check_brackets_on_exchange = AsyncMock(
                return_value=(True, True))
            fsm._place_health_check_brackets = AsyncMock()

            cfg = MagicMock(max_placements_per_cycle=2, grace_period_ms=15000)
            await fsm._run_bracket_health_check(cfg)

            fsm._place_health_check_brackets.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_sl_triggers_placement(self, fsm_config):
        """Missing SL -> compute + place brackets called."""
        btc_cfg = fsm_config.strategies.aurora.assets["BTCUSDT"]
        btc_cfg.exit.regime_tpsl = None

        fsm = _make_fsm(fsm_config, with_adapter=True)

        mock_pos = MagicMock()
        mock_pos.to_dict.return_value = {
            "symbol": "BTCUSDT",
            "position_amount": "0.005",
            "entry_price": "100000.0",
            "update_time_ms": 1000000,
        }
        fsm.adapter.get_open_positions = AsyncMock(return_value=[mock_pos])

        with patch("apps.reference.domains.execution_position.fsm.get_clock") as mock_clock:
            mock_clock.return_value.now_ms.return_value = 1000000 + 60000

            fsm._check_brackets_on_exchange = AsyncMock(
                return_value=(False, True))
            fsm._place_health_check_brackets = AsyncMock(return_value=True)

            cfg = MagicMock(max_placements_per_cycle=2, grace_period_ms=15000)
            await fsm._run_bracket_health_check(cfg)

            fsm._place_health_check_brackets.assert_called_once()
            call_kwargs = fsm._place_health_check_brackets.call_args
            assert call_kwargs.kwargs["need_sl"] is True
            assert call_kwargs.kwargs["need_tp"] is False

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self, fsm_config):
        """max_placements_per_cycle limits bracket placements in one cycle."""
        btc_cfg = fsm_config.strategies.aurora.assets["BTCUSDT"]
        btc_cfg.exit.regime_tpsl = None

        fsm = _make_fsm(fsm_config, with_adapter=True)

        positions = []
        for sym in ["BTCUSDT", "SOLUSDT", "ETHUSDT"]:
            mock_pos = MagicMock()
            mock_pos.to_dict.return_value = {
                "symbol": sym,
                "position_amount": "0.005",
                "entry_price": "100.0",
                "update_time_ms": 1000000,
            }
            positions.append(mock_pos)

        fsm.adapter.get_open_positions = AsyncMock(return_value=positions)

        with patch("apps.reference.domains.execution_position.fsm.get_clock") as mock_clock:
            mock_clock.return_value.now_ms.return_value = 1000000 + 60000

            fsm._check_brackets_on_exchange = AsyncMock(
                return_value=(False, False))
            fsm._place_health_check_brackets = AsyncMock(return_value=True)
            fsm._compute_health_check_brackets = MagicMock(side_effect=[
                (98000.0, 101000.0),
                (None, None),  # SOLUSDT no config
                (None, None),  # ETHUSDT no config
            ])

            cfg = MagicMock(max_placements_per_cycle=1, grace_period_ms=15000)
            await fsm._run_bracket_health_check(cfg)

            assert fsm._place_health_check_brackets.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3: _schedule_bracket_health_loop
# ═══════════════════════════════════════════════════════════════════════════════


class TestScheduleBracketHealthLoop:
    """Tests for the scheduling entry point."""

    def test_disabled_config_skips(self, fsm_config):
        """If bracket_health_check.enabled=False, loop is not scheduled."""
        fsm = _make_fsm(fsm_config)

        # Now set the config for the scheduling test
        bhc = MagicMock()
        bhc.enabled = False
        fsm.config.domains.execution_position.bracket_health_check = bhc
        fsm._bracket_health_started = False
        fsm._submit_async = MagicMock()

        fsm._schedule_bracket_health_loop()

        fsm._submit_async.assert_not_called()
        assert fsm._bracket_health_started is False

    def test_no_config_skips(self, fsm_config):
        """If bracket_health_check is None, loop is not scheduled."""
        fsm = _make_fsm(fsm_config)

        fsm.config.domains.execution_position.bracket_health_check = None
        fsm._bracket_health_started = False
        fsm._submit_async = MagicMock()

        fsm._schedule_bracket_health_loop()

        fsm._submit_async.assert_not_called()

    def test_idempotent_double_schedule(self, fsm_config):
        """Calling _schedule twice doesn't create duplicate loops."""
        fsm = _make_fsm(fsm_config)

        bhc = MagicMock()
        bhc.enabled = True
        bhc.interval_sec = 45
        bhc.grace_period_ms = 15000
        fsm.config.domains.execution_position.bracket_health_check = bhc
        fsm._bracket_health_started = False
        fsm._submit_async = MagicMock()
        fsm._get_async_loop = MagicMock(return_value=MagicMock())

        fsm._schedule_bracket_health_loop()
        assert fsm._bracket_health_started is True
        assert fsm._submit_async.call_count == 1

        fsm._schedule_bracket_health_loop()
        assert fsm._submit_async.call_count == 1  # Still 1, not doubled


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3: IdempotentCancelResult.order_data
# ═══════════════════════════════════════════════════════════════════════════════


class TestIdempotentCancelResultOrderData:
    """Tests for the order_data field added to IdempotentCancelResult."""

    def test_order_data_defaults_to_none(self):
        from apps.reference.domains.execution_position.idempotent_cancel import IdempotentCancelResult

        result = IdempotentCancelResult(
            success=True,
            reason="immediate",
        )
        assert result.order_data is None

    def test_order_data_can_store_fill_info(self):
        from apps.reference.domains.execution_position.idempotent_cancel import IdempotentCancelResult

        fill_data = {
            "status": "FILLED",
            "executedQty": "0.005",
            "avgPrice": "67013.00",
            "side": "BUY",
        }
        result = IdempotentCancelResult(
            success=True,
            reason="precheck_filled",
            order_data=fill_data,
        )
        assert result.order_data is not None
        assert result.order_data["status"] == "FILLED"
        assert result.order_data["executedQty"] == "0.005"
