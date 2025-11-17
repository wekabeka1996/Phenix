"""
Tests for Execution Position domain component.

Tests the 3-FSM architecture: OpenFlowFSM, ManageFlowFSM, CloseFlowFSM
and the main ExecPosFSM wrapper with exposure guards, watchdog, and cleanup.
"""

import asyncio
import logging
import time
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM, OpenState
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM, CloseState
from apps.reference.telemetry.order_logger import order_logger
from vfoundation.core.protocol import Message


class TestExecutionPositionDomain:
    """Test suite for execution_position domain components."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return {
            "trading": {
                "mode": "testnet",
                "execution": {
                    "cooldown_ms": 1000,
                    "guard_enabled": True,
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000,
                    },
                    "manage": {
                        "orphan_monitor": {
                            "enabled": True,
                            "run_on_startup": True,
                            "periodic_interval_sec": 300,
                            "min_order_age_sec": 0,
                            "batch_cancel_limit": 50,
                            "rate_limit_per_min": 120,
                        }
                    }
                },
                "orders": {
                    "default_ttl_seconds": 30,
                },
                "brackets": {
                    "sl": {"fixed_bps": 50},
                    "tp": {"fixed_bps": 100},
                }
            },
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "rest_url": "https://testnet.binance.vision",
                }
            },
            "execution": {
                "fsm_periodic_cleanup_enabled": True,
                "allow_trade_with_guardian_tidy_only": False,
            },
            "guardian": {
                "cleanup_ttl_ms": 6000,
                "symbol_cooldown_ms": 4000,
                "unified": True,
            }
        }

    @pytest.fixture
    def mock_fsm_core(self):
        """Mock FSM core for event handling."""
        fsm = MagicMock()
        fsm.listen = MagicMock()
        fsm.emit = AsyncMock()
        return fsm

    @pytest.fixture
    def exec_pos_fsm(self, mock_config, mock_fsm_core):
        """ExecPosFSM instance with mocked dependencies."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter') as mock_adapter, \
                patch('apps.reference.domains.execution_position.fsm.OrderGuardian') as mock_guardian, \
                patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog') as mock_watchdog:

            mock_adapter_instance = MagicMock()
            mock_adapter.return_value = mock_adapter_instance

            mock_guardian_instance = MagicMock()
            mock_guardian.return_value = mock_guardian_instance

            mock_watchdog_instance = MagicMock()
            mock_watchdog.return_value = mock_watchdog_instance

            fsm = ExecPosFSM(mock_config, mock_fsm_core, shadow_mode=True)
            return fsm

    def test_exec_pos_initialization(self, mock_config, mock_fsm_core):
        """Test ExecPosFSM initialization."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter'), \
                patch('apps.reference.domains.execution_position.fsm.OrderGuardian'), \
                patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog'):

            fsm = ExecPosFSM(mock_config, mock_fsm_core, shadow_mode=True)

            assert fsm.config == mock_config
            assert fsm.fsm == mock_fsm_core
            assert fsm.shadow_mode is True
            assert hasattr(fsm, 'open_flows')
            assert hasattr(fsm, 'manage_flows')
            assert hasattr(fsm, 'close_flows')
            assert hasattr(fsm, 'exposure_guard')
            assert hasattr(fsm, 'metrics_collector')

    def test_get_or_create_flows(self, exec_pos_fsm):
        """Test per-symbol FSM creation and retrieval."""
        symbol = "BTCUSDT"

        # First call should create flows
        open_flow, manage_flow, close_flow = exec_pos_fsm._get_or_create_flows(
            symbol)

        assert isinstance(open_flow, OpenFlowFSM)
        assert isinstance(manage_flow, ManageFlowFSM)
        assert isinstance(close_flow, CloseFlowFSM)

        # Second call should return same instances
        open_flow2, manage_flow2, close_flow2 = exec_pos_fsm._get_or_create_flows(
            symbol)

        assert open_flow is open_flow2
        assert manage_flow is manage_flow2
        assert close_flow is close_flow2

    def test_handle_open_command(self, exec_pos_fsm):
        """Test handling CMD:OPEN messages."""
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price": "50000.0",
                "price_ref": "50000.0"  # Required for exposure check
            }
        )

        with patch.object(exec_pos_fsm.exposure_guard, 'can_open', return_value={"allowed": True, "reason": None}), \
                patch.object(exec_pos_fsm.exposure_guard, 'reserve') as mock_reserve:

            result = exec_pos_fsm.handle(msg)

            # Should return a decision message
            assert result is not None
            assert result.op == "DEC"
            assert result.verb == "OPEN"
            assert result.pld["symbol"] == "BTCUSDT"
            assert result.pld["side"] == "BUY"

            # Should reserve exposure
            mock_reserve.assert_called_once()

    def test_handle_close_command(self, exec_pos_fsm):
        """Test handling CMD:CLOSE messages."""
        # First set up an active position
        _, manage_flow, close_flow = exec_pos_fsm._get_or_create_flows(
            "BTCUSDT")
        close_flow.position_active = True
        close_flow.state = CloseState.OPENED

        msg = Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            pld={"symbol": "BTCUSDT"}
        )

        result = exec_pos_fsm.handle(msg)

        # Should return a decision message
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "CLOSE"
        assert result.pld["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_dec_close_by_entry_cancels_only_parent_entry(self, mock_config, mock_fsm_core):
        """Test DEC:CLOSE for a specific parent_entry_id cancels only that entry's brackets and places reduce-only close for remaining qty."""
        # Use a real OrderGuardian to exercise per-entry cleanup
        from apps.reference.services.order_guardian import OrderGuardian

        adapter = AsyncMock()
        # Simulate a combined position of 3 units (two entries: 1 + 2)
        adapter.get_open_positions.return_value = [
            {"symbol": "SOLUSDT", "positionAmt": "3.0"}]

        # Setup adapter open orders for both entries (A & B)
        adapter.get_open_orders.return_value = [
            {"orderId": "SLA", "symbol": "SOLUSDT", "status": "NEW", "type": "STOP_MARKET",
                "reduceOnly": True, "closePosition": True, "parentEntryId": "A"},
            {"orderId": "TPA", "symbol": "SOLUSDT", "status": "NEW", "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True, "closePosition": True, "parentEntryId": "A"},
            {"orderId": "SLB", "symbol": "SOLUSDT", "status": "NEW", "type": "STOP_MARKET",
                "reduceOnly": True, "closePosition": True, "parentEntryId": "B"},
            {"orderId": "TPB", "symbol": "SOLUSDT", "status": "NEW", "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True, "closePosition": True, "parentEntryId": "B"},
        ]

        adapter.cancel_order.return_value = {"status": "CANCELED"}
        adapter.place_market_reduce_only.return_value = {"orderId": "CLOSE1"}
        adapter.base_url = "https://testnet.binance.vision"

        # Create guardian & register entries + brackets
        guardian = OrderGuardian(adapter=adapter, poll_interval_ms=0)
        # Entry A: qty 1
        guardian.register_entry(
            symbol="SOLUSDT", order_id="A", client_order_id="client_A", side="BUY", qty=1.0)
        guardian.register_bracket(symbol="SOLUSDT", parent_order_id="A",
                                  order_id="SLA", client_order_id="client_sla", kind="SL")
        guardian.register_bracket(symbol="SOLUSDT", parent_order_id="A",
                                  order_id="TPA", client_order_id="client_tpa", kind="TP")
        # Entry B: qty 2
        guardian.register_entry(
            symbol="SOLUSDT", order_id="B", client_order_id="client_B", side="BUY", qty=2.0)
        guardian.register_bracket(symbol="SOLUSDT", parent_order_id="B",
                                  order_id="SLB", client_order_id="client_slb", kind="SL")
        guardian.register_bracket(symbol="SOLUSDT", parent_order_id="B",
                                  order_id="TPB", client_order_id="client_tpb", kind="TP")

        # Create FSM and inject our adapter & guardian
        with patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog'):
            fsm = ExecPosFSM(mock_config, mock_fsm_core, shadow_mode=False)

        # Stop the guardian created during FSM init to avoid double-polling
        try:
            await fsm.order_guardian.stop()
        except Exception:
            pass

        fsm.adapter = adapter
        fsm.order_guardian = guardian
        # Set multi-entry mode - disable symbol-wide reconcile which cancels other entries
        try:
            fsm.config["trading"]["execution"]["manage"]["brackets"]["keep_single_bracket_set"] = False
        except Exception:
            pass

        # Sanity-check: guardian has entry + brackets
        assert guardian.get_brackets_for_entry(
            "A") and "sl" in guardian.get_brackets_for_entry("A")

        # Sanity-check: guardian.close_entry cancels A's brackets outside of FSM
        adapter.cancel_order.reset_mock()
        res_close = await guardian.close_entry(symbol="SOLUSDT", parent_order_id="A")
        assert res_close.get("cancelled_brackets", 0) >= 1
        assert adapter.cancel_order.call_count >= 1

        # DEC:CLOSE by entry A
        close_decision = Message(op="DEC", verb="CLOSE", src="decision_making", dst="execution_position", pld={
            "symbol": "SOLUSDT", "parent_order_id": "A"}, timestamp_utc=datetime.utcnow())

        await fsm._execute_decision(close_decision)

        # Assert adapter.cancel_order called for A's brackets but not for B's
    # Debug prints removed
        adapter.cancel_order.assert_any_call("SOLUSDT", "SLA")
        adapter.cancel_order.assert_any_call("SOLUSDT", "TPA")
        # Ensure B's brackets were not cancelled
        assert not any(
            call.args[1] == "SLB" for call in adapter.cancel_order.call_args_list), "SLB should not be cancelled"
        assert not any(
            call.args[1] == "TPB" for call in adapter.cancel_order.call_args_list), "TPB should not be cancelled"

        # Assert place_market_reduce_only called to close remaining qty for entry A (1.0 units)
        assert adapter.place_market_reduce_only.call_count == 1
        args, kwargs = adapter.place_market_reduce_only.call_args
        # Validate we're closing roughly '1.0' units (args[2] is qty)
        qty_arg = args[2] if len(args) > 2 else kwargs.get('qty')
        assert float(qty_arg or 0) == pytest.approx(1.0)

    def test_handle_portfolio_state_update(self, exec_pos_fsm):
        """Test handling portfolio state updates."""
        msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="account_balance",
            dst="execution_position",
            pld={"open_positions_usd": "10000.0"}
        )

        result = exec_pos_fsm.handle(msg)

        # Should not return a decision (handled internally)
        assert result is None

        # Should update latest portfolio state
        assert exec_pos_fsm._latest_portfolio_state == {
            "open_positions_usd": "10000.0"}

    def test_exposure_fail_closed(self, exec_pos_fsm):
        """Test exposure guard fail-closed behavior."""
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={
                "symbol": "BTCUSDT",
                "qty": "1.0",
                "price": "50000.0",
                "price_ref": "50000.0"
            }
        )

        with patch.object(exec_pos_fsm.exposure_guard, 'can_open', return_value={"allowed": False, "reason": "exposure_limit"}), \
                patch.object(exec_pos_fsm.exposure_guard, 'reserve') as mock_reserve, \
                patch.object(exec_pos_fsm, '_emit_error_async') as mock_emit, \
                patch('asyncio.get_running_loop', return_value=asyncio.new_event_loop()):

            result = exec_pos_fsm._check_exposure_fail_closed(msg)

            # Should return True (blocked)
            assert result is True

            # Should still reserve exposure (fail-closed)
            mock_reserve.assert_called_once()

            # Should emit error
            mock_emit.assert_called_once()

    def test_symbol_tidy_gate(self, exec_pos_fsm):
        """Test SYMBOL_TIDY entry gating."""
        symbol = "BTCUSDT"

        # Initially should allow (no gate configured)
        assert exec_pos_fsm._entry_tidy_gate_allow(symbol) is True

        # With gate enabled but no recent tidy - should block
        exec_pos_fsm.config["execution"] = exec_pos_fsm.config.get(
            "execution", {})
        exec_pos_fsm.config["execution"]["allow_trade_with_guardian_tidy_only"] = True

        # Should block if no recent tidy
        assert exec_pos_fsm._entry_tidy_gate_allow(symbol) is False

        # Should allow after tidy event
        exec_pos_fsm._on_symbol_tidy_event({"symbol": symbol})
        assert exec_pos_fsm._entry_tidy_gate_allow(symbol) is True

    def test_metrics_aggregation(self, exec_pos_fsm):
        """Test metrics collection from all FSMs."""
        # Create some flows
        exec_pos_fsm._get_or_create_flows("BTCUSDT")
        exec_pos_fsm._get_or_create_flows("ETHUSDT")

        metrics = exec_pos_fsm.get_metrics()

        # Should include metrics from all flows
        assert "BTCUSDT_open" in metrics
        assert "BTCUSDT_manage" in metrics
        assert "BTCUSDT_close" in metrics
        assert "ETHUSDT_open" in metrics

        # Should include orphan monitor metrics
        assert "orphan_monitor" in metrics
        assert "gate" in metrics

    def test_hydration(self, exec_pos_fsm):
        """Test FSM state hydration from snapshots."""
        position_data = {
            "symbol": "BTCUSDT",
            "positionAmt": "0.5",
            "entryPrice": "45000.0"
        }

        exec_pos_fsm.hydrate(position_data)

        # Should create and hydrate flows
        assert "BTCUSDT" in exec_pos_fsm.manage_flows
        assert "BTCUSDT" in exec_pos_fsm.close_flows

    def test_watchdog_timeout_handling(self, exec_pos_fsm):
        """Test order timeout handling."""
        # Mock watchdog deadline
        deadline = MagicMock()
        deadline.order_id = "12345"
        deadline.symbol = "BTCUSDT"
        deadline.timeout_type.value = "ack_timeout"
        deadline.corr_id = "test_corr"
        deadline.rid = "test_rid"

        with patch.object(exec_pos_fsm, 'adapter', None), \
                patch.object(order_logger, 'write') as mock_log:

            # Run timeout handling
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    exec_pos_fsm._handle_order_timeout(deadline))
            finally:
                loop.close()

            # Should log timeout
            mock_log.assert_called()

    def test_cleanup_orphans_startup(self, exec_pos_fsm):
        """Test orphaned order cleanup on startup."""
        mock_adapter = MagicMock()
        mock_adapter.get_open_orders = AsyncMock(return_value=[])
        mock_adapter.get_open_positions = AsyncMock(return_value=[])

        with patch.object(exec_pos_fsm, 'adapter', mock_adapter), \
                patch.object(exec_pos_fsm.order_guardian, 'cleanup_orphans', new_callable=AsyncMock) as mock_cleanup:

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    exec_pos_fsm.sync_open_orders_and_positions())
            finally:
                loop.close()

            # Should attempt cleanup
            mock_cleanup.assert_called_once()


class TestOpenFlowFSM:
    """Test suite for OpenFlowFSM component."""

    @pytest.fixture
    def open_fsm(self):
        """OpenFlowFSM instance for testing."""
        return OpenFlowFSM(cooldown_sec=0.1, guard_enabled=True)

    def test_open_flow_initialization(self, open_fsm):
        """Test OpenFlowFSM initialization."""
        assert open_fsm.state == OpenState.IDLE
        assert hasattr(open_fsm, 'cooldown_sec')
        assert hasattr(open_fsm, 'guard_enabled')

    def test_open_flow_handle_open_command(self, open_fsm):
        """Test handling CMD:OPEN in OpenFlowFSM."""
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="exec_pos_wrapper",
            dst="open_flow",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price": "50000.0"
            }
        )

        result = open_fsm.handle(msg)

        # Should transition through states and emit decision
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"
        assert result.pld["symbol"] == "BTCUSDT"

    def test_open_flow_guards(self, open_fsm):
        """Test guard conditions in OpenFlowFSM."""
        # Test minimum notional guard
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="exec_pos_wrapper",
            dst="open_flow",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.000001",  # Too small
                "price": "50000.0"
            }
        )

        result = open_fsm.handle(msg)

        # Should be blocked by guards
        assert result is None or result.op == "ERR"

    def test_open_flow_cooldown(self, open_fsm):
        """Test cooldown mechanism in OpenFlowFSM."""
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="exec_pos_wrapper",
            dst="open_flow",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price": "50000.0"
            }
        )

        # First command should work
        result1 = open_fsm.handle(msg)
        assert result1 is not None

        # Immediate second command should be blocked by cooldown
        result2 = open_fsm.handle(msg)
        assert result2 is None or result2.op == "ERR"


class TestManageFlowFSM:
    """Test suite for ManageFlowFSM component."""

    @pytest.fixture
    def manage_fsm(self):
        """ManageFlowFSM instance for testing."""
        config = {
            "trading": {
                "execution": {
                    "manage": {
                        "auto": True,
                        "brackets": {
                            "enable": True
                        }
                    }
                }
            }
        }
        return ManageFlowFSM(config=config)

    def test_manage_flow_initialization(self, manage_fsm):
        """Test ManageFlowFSM initialization."""
        assert manage_fsm.state == ManageState.FLAT
        assert hasattr(manage_fsm, 'position_qty')
        assert hasattr(manage_fsm, 'position_entry_price')
        assert hasattr(manage_fsm, 'sl_order_id')
        assert hasattr(manage_fsm, 'tp_order_id')

    def test_manage_flow_position_tracking(self, manage_fsm):
        """Test position tracking in ManageFlowFSM."""
        # Simulate position opening
        fill_msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="manage_flow",
            pld={
                "symbol": "BTCUSDT",
                "orderId": "12345",
                "side": "BUY",
                "qty": "0.001",  # Changed to qty to match adapter emission
                "price": "50000.0"
            }
        )

        result = manage_fsm.handle(fill_msg)

        # Should update position tracking
        # Should transition to BRACKETS_PENDING
        assert manage_fsm.state == ManageState.BRACKETS_PENDING
        assert manage_fsm.position_qty == Decimal("0.001")
        assert manage_fsm.position_entry_price == Decimal("50000.0")
        assert manage_fsm.position_side == "BUY"

    def test_manage_flow_bracket_placement(self, manage_fsm):
        """Test bracket order placement logic."""
        # Set up position by simulating a fill event
        fill_msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="manage_flow",
            pld={
                "symbol": "BTCUSDT",
                "orderId": "12345",
                "side": "BUY",
                "qty": "0.001",
                "price": "50000.0"
            }
        )

        # Mock config to enable brackets
        manage_fsm.config = {
            "trading": {
                "execution": {
                    "manage": {
                        "brackets": {
                            "enable": True,
                            "sl": {"fixed_bps": 50},
                            "tp": {"fixed_bps": 100}
                        }
                    }
                }
            }
        }

        result = manage_fsm.handle(fill_msg)

        # Should place bracket orders
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "PLACE_ORDER"
        assert "SL bracket" in result.why

    def test_manage_flow_hydration(self, manage_fsm):
        """Test state hydration from position data."""
        position_data = {
            "symbol": "BTCUSDT",
            "qty": "0.5",
            "entry_price": "45000.0",
            "side": "BUY",
            "open_ts": 1234567890.0,
            "sl_order_id": "sl123",
            "tp_order_id": "tp456"
        }

        manage_fsm.hydrate(position_data)

        assert manage_fsm.position_qty == Decimal("0.5")
        assert manage_fsm.position_entry_price == Decimal("45000.0")
        assert manage_fsm.position_side == "BUY"
        assert manage_fsm.sl_order_id == "sl123"
        assert manage_fsm.tp_order_id == "tp456"


class TestCloseFlowFSM:
    """Test suite for CloseFlowFSM component."""

    @pytest.fixture
    def close_fsm(self):
        """CloseFlowFSM instance for testing."""
        return CloseFlowFSM(max_hold_sec=7200.0)

    def test_close_flow_initialization(self, close_fsm):
        """Test CloseFlowFSM initialization."""
        assert close_fsm.state == CloseState.FLAT
        assert close_fsm.max_hold_sec == 7200.0
        assert not close_fsm.position_active

    def test_close_flow_position_opening(self, close_fsm):
        """Test position opening detection in CloseFlowFSM."""
        fill_msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="close_flow",
            pld={
                "symbol": "BTCUSDT",
                "qty": "0.001",  # Changed to qty to match adapter emission
                "price": "50000.0"
            }
        )

        result = close_fsm.handle(fill_msg)

        # Should detect position opening
        assert close_fsm.position_active
        assert close_fsm.state == CloseState.OPENED

    def test_close_flow_close_command(self, close_fsm):
        """Test CMD:CLOSE handling in CloseFlowFSM."""
        # Set up active position
        close_fsm.position_active = True
        close_fsm.state = CloseState.OPENED

        close_msg = Message(
            op="CMD",
            verb="CLOSE",
            src="exec_pos_wrapper",
            dst="close_flow",
            pld={"symbol": "BTCUSDT"}
        )

        result = close_fsm.handle(close_msg)

        # Should emit close decision
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "CLOSE"

    def test_close_flow_hydration(self, close_fsm):
        """Test state hydration in CloseFlowFSM."""
        position_data = {
            "symbol": "BTCUSDT",
            "positionAmt": "0.5",
            "entryPrice": "45000.0",
            "openTime": time.time() - 3600  # 1 hour ago
        }

        close_fsm.hydrate(position_data)

        assert close_fsm.position_active
        assert close_fsm.state == CloseState.OPENED

    def test_close_flow_time_based_close(self, close_fsm):
        """Test time-based close conditions."""
        # Set up position older than max_hold_sec
        close_fsm.position_active = True
        close_fsm.state = CloseState.OPENED
        close_fsm.position_open_ts = time.time() - 8000  # 8 seconds ago
        close_fsm.max_hold_sec = 5  # 5 seconds max

        # Simulate time check (would be called by timer)
        # In real implementation, this would trigger close decision
        assert close_fsm.position_active  # Position should still be active until checked

    def test_close_flow_metrics(self, close_fsm):
        """Test metrics collection in CloseFlowFSM."""
        metrics = close_fsm.get_metrics()

        assert "fsm_close_decisions_total" in metrics
        assert "fsm_errors_total" in metrics
        assert isinstance(metrics["fsm_close_decisions_total"], int)


class TestIntegrationScenarios:
    """Integration tests for complete execution_position flows."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return {
            "trading": {
                "mode": "testnet",
                "execution": {
                    "cooldown_ms": 1000,
                    "guard_enabled": True,
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000,
                    },
                    "manage": {
                        "orphan_monitor": {
                            "enabled": True,
                            "run_on_startup": True,
                            "periodic_interval_sec": 300,
                            "min_order_age_sec": 0,
                            "batch_cancel_limit": 50,
                            "rate_limit_per_min": 120,
                        }
                    }
                },
                "orders": {
                    "default_ttl_seconds": 30,
                }
            }
        }

    @pytest.fixture
    def mock_fsm_core(self):
        """Mock FSM core for event handling."""
        fsm = MagicMock()
        fsm.listen = MagicMock()
        fsm.emit = AsyncMock()
        return fsm

    @pytest.fixture
    def full_exec_pos_fsm(self, mock_config, mock_fsm_core):
        """Fully configured ExecPosFSM for integration testing."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter'), \
                patch('apps.reference.domains.execution_position.fsm.OrderGuardian'), \
                patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog'):

            fsm = ExecPosFSM(mock_config, mock_fsm_core, shadow_mode=True)
            return fsm

    def test_complete_trade_lifecycle(self, full_exec_pos_fsm):
        """Test complete trade lifecycle: OPEN → MANAGE → CLOSE."""
        symbol = "BTCUSDT"

        # 1. OPEN position
        open_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={
                "symbol": symbol,
                "side": "BUY",
                "qty": "0.001",
                "price": "50000.0"
            }
        )

        with patch.object(full_exec_pos_fsm.exposure_guard, 'can_open', return_value={"allowed": True}), \
                patch.object(full_exec_pos_fsm.exposure_guard, 'reserve'):

            open_decision = full_exec_pos_fsm.handle(open_msg)
            assert open_decision.op == "DEC"
            assert open_decision.verb == "OPEN"

        # 2. Simulate FILL event
        fill_msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="execution_position",
            pld={
                "symbol": symbol,
                "orderId": "12345",
                "qty": "0.001",  # Changed to qty to match adapter emission
                "price": "50000.0"
            }
        )

        fill_result = full_exec_pos_fsm.handle(fill_msg)
        # FILL should be handled by manage flow

        # 3. CLOSE position
        close_msg = Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            pld={"symbol": symbol}
        )

        close_decision = full_exec_pos_fsm.handle(close_msg)
        assert close_decision.op == "DEC"
        assert close_decision.verb == "CLOSE"

    def test_multiple_symbols_concurrent(self, full_exec_pos_fsm):
        """Test concurrent operations on multiple symbols."""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]

        # Open positions for all symbols
        for symbol in symbols:
            open_msg = Message(
                op="CMD",
                verb="OPEN",
                src="decision_making",
                dst="execution_position",
                pld={
                    "symbol": symbol,
                    "side": "BUY",
                    "qty": "0.001",
                    "price": "50000.0"
                }
            )

            with patch.object(full_exec_pos_fsm.exposure_guard, 'can_open', return_value={"allowed": True}), \
                    patch.object(full_exec_pos_fsm.exposure_guard, 'reserve'):

                decision = full_exec_pos_fsm.handle(open_msg)
                assert decision.op == "DEC"
                assert decision.pld["symbol"] == symbol

        # Verify separate FSMs created for each symbol
        for symbol in symbols:
            assert symbol in full_exec_pos_fsm.open_flows
            assert symbol in full_exec_pos_fsm.manage_flows
            assert symbol in full_exec_pos_fsm.close_flows

    def test_error_handling_and_recovery(self, full_exec_pos_fsm):
        """Test error handling and recovery mechanisms."""
        # Test invalid message
        invalid_msg = Message(
            op="CMD",
            verb="INVALID",
            src="test",
            dst="execution_position",
            pld={}
        )

        result = full_exec_pos_fsm.handle(invalid_msg)
        # Should handle gracefully (may return None or error)

        # Test message without symbol
        no_symbol_msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={"side": "BUY", "qty": "0.001"}
        )

        result = full_exec_pos_fsm.handle(no_symbol_msg)
        assert result is None  # Should be ignored

    @pytest.mark.asyncio
    async def test_ws_snapshot_preflight_skips_rest(self, mock_fsm_core):
        ws_config = {
            "trading": {
                "mode": "testnet",
                "execution": {
                    "manage": {
                        "positions": {
                            "ws_snapshot": {
                                "enabled": True,
                                "max_age_ms": 2000,
                                "rest_fallback_enabled": True,
                            }
                        }
                    }
                }
            }
        }

        fsm = ExecPosFSM(ws_config, mock_fsm_core, shadow_mode=True)

        class NoopAdapter:
            def __init__(self):
                self.calls = 0

            def get_open_positions(self, symbol=None):
                self.calls += 1
                return []

        adapter = NoopAdapter()
        fsm.adapter = adapter

        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="portfolio",
            dst="execution_position",
            pld={
                "positions": [
                    {
                        "symbol": "BNBUSDT",
                        "positionAmt": "0.3",
                        "entryPrice": "600",
                        "positionSide": "LONG",
                    }
                ],
                "positions_last_ts_ms": int(time.time() * 1000),
            },
        )
        fsm._on_portfolio_state_updated(portfolio_msg)

        assert (
            await fsm._preflight_position_check("BNBUSDT", "LONG")
        ) is True
        assert adapter.calls == 0

    def test_exposure_guard_integration(self, full_exec_pos_fsm):
        """Test exposure guard integration with trading decisions."""
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={
                "symbol": "BTCUSDT",
                "qty": "1.0",
                "price": "50000.0",
                "price_ref": "50000.0"
            }
        )

        # Test allowed exposure
        with patch.object(full_exec_pos_fsm.exposure_guard, 'can_open', return_value={"allowed": True}), \
                patch.object(full_exec_pos_fsm.exposure_guard, 'reserve'):

            result = full_exec_pos_fsm._check_exposure_fail_closed(msg)
            assert result is False  # Should allow

        # Test blocked exposure
        with patch.object(full_exec_pos_fsm.exposure_guard, 'can_open', return_value={"allowed": False, "reason": "limit"}), \
                patch.object(full_exec_pos_fsm.exposure_guard, 'reserve'), \
                patch.object(full_exec_pos_fsm, '_emit_error_async'):

            result = full_exec_pos_fsm._check_exposure_fail_closed(msg)
            assert result is True  # Should block
