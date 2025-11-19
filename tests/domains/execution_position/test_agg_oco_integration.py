import pytest
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from vfoundation.core.protocol import Message


@pytest.fixture
def mock_config():
    return {
        "execution": {
            "manage": {
                "mode": "aggregated_only",
                "auto": True,
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_scale_in": True,
                        "recalc_on_partial_close": True,
                        "ttl_protect_new_bracket_ms": 0,
                        "sl": {"fixed_bps": 100},
                        "tp": {"fixed_bps": 200}
                    }
                },
                "guardian": {
                    "unified": True,
                    "poll_interval_ms": 100,
                    "cleanup_ttl_ms": 6000,
                    "symbol_cooldown_ms": 4000,
                    "emit_tidy_event": True
                },
                "watchdog": {
                    "ack_ttl_ms": 5000,
                    "fill_ttl_ms": 10000,
                    "source": "config"
                }
            }
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {"min_qty": "0.001", "tick_size": "0.01"}
            }
        },
        # Add fake API config to prevent shadow_mode fallback
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binance.vision/api"
            }
        }
    }


@pytest.fixture
def fsm(mock_config):
    with patch("apps.reference.domains.execution_position.fsm.BinanceAdapter"), \
            patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), \
            patch("apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"), \
            patch("apps.reference.domains.execution_position.fsm.ExposureGuard"), \
            patch("apps.reference.domains.execution_position.fsm.LocalBus"):

        fsm_instance = ExecPosFSM(config=mock_config, shadow_mode=False)

        # Force shadow_mode off in case init turned it on
        fsm_instance.shadow_mode = False

        # Mock parent FSM for emit_compat
        fsm_instance.fsm = MagicMock()
        fsm_instance.fsm.emit = MagicMock()

        # Mock Adapter
        fsm_instance.adapter = MagicMock()
        fsm_instance.adapter.get_open_positions = AsyncMock(return_value=[])
        fsm_instance.adapter.get_open_orders = AsyncMock(return_value=[])
        fsm_instance.adapter.cancel_order = AsyncMock(
            return_value={"status": "CANCELED"})
        fsm_instance.adapter.place_order = AsyncMock(side_effect=lambda **kwargs: {
            "orderId": "12345",
            "status": "NEW",
            "symbol": kwargs.get("symbol"),
            "side": kwargs.get("side"),
            "type": kwargs.get("type")
        })
        fsm_instance.adapter.place_stop_market_close_position = AsyncMock(return_value={
            "orderId": "SL-NEW", "status": "NEW", "clientOrderId": "sl_cid"
        })
        fsm_instance.adapter.place_take_profit_market_close_position = AsyncMock(return_value={
            "orderId": "TP-NEW", "status": "NEW", "clientOrderId": "tp_cid"
        })
        fsm_instance.adapter.place_limit_reduce_only = AsyncMock(return_value={
            "orderId": "TP-LIMIT-NEW", "status": "NEW", "clientOrderId": "tp_limit_cid"
        })

        # Fix for Guardrail check in _execute_decision
        fsm_instance.adapter.base_url = "https://testnet.binance.vision/api"

        # Mock OrderGuardian async methods
        fsm_instance.order_guardian = MagicMock()
        fsm_instance.order_guardian.cleanup_orphans = AsyncMock(return_value=0)
        fsm_instance.order_guardian.reconcile_symbol = AsyncMock()
        fsm_instance.order_guardian.link_existing_from_rest = AsyncMock()
        fsm_instance.order_guardian.register_bracket_set = MagicMock()
        fsm_instance.order_guardian.should_place_brackets = AsyncMock(
            return_value=True)

        # Mock bus
        fsm_instance.bus = MagicMock()
        fsm_instance.bus.emit = MagicMock()

        # Mock fsm property on flows (needed for emit_compat)
        # We need to patch _get_or_create_flows to attach fsm to created flows
        original_get_flows = fsm_instance._get_or_create_flows

        # Shared state for position provider
        fsm_instance._test_position_state = {}

        def side_effect_get_flows(symbol):
            open_flow, manage_flow, close_flow = original_get_flows(symbol)
            # Attach fsm reference for emit_compat
            manage_flow.fsm = fsm_instance
            # Mock live position provider to return what we want
            manage_flow._live_position_provider = lambda: fsm_instance._test_position_state.get(symbol, {
                "symbol": symbol,
                "qty": Decimal("0"),
                "avg_price": Decimal("0"),
                "side": "FLAT",
                "source": "mock_provider"
            })
            return open_flow, manage_flow, close_flow

        fsm_instance._get_or_create_flows = MagicMock(
            side_effect=side_effect_get_flows)

        # Ensure _get_async_loop returns the running loop
        fsm_instance._get_async_loop = MagicMock(
            side_effect=asyncio.get_running_loop)

        return fsm_instance


@pytest.mark.asyncio
async def test_nominal_flow_open_position(fsm):
    """
    Test that a standard ENTRY FILL triggers bracket placement.
    """
    symbol = "BTCUSDT"
    qty = "1.0"
    price = "50000.0"

    # 1. Send FILL event (Entry)
    msg = Message(
        op="EVT",
        verb="FILL",
        src="adapter",
        dst="execution_position",
        pld={
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "side": "BUY",
            "order_type": "MARKET",
            "orderId": "1001"
        }
    )

    # Spy on _dispatch_decision
    with patch.object(fsm, '_dispatch_decision', wraps=fsm._dispatch_decision) as mock_dispatch:
        fsm.handle(msg)

        # 1.5 Send PORTFOLIO_STATE_UPDATED to update position
        # Update the mock state first so ManageFlow sees it
        fsm._test_position_state[symbol] = {
            "symbol": symbol,
            "qty": Decimal(qty),
            "avg_price": Decimal(price),
            "side": "BUY",
            "source": "mock_provider"
        }

        msg_portfolio = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="adapter",
            dst="execution_position",
            pld={
                "positions": [
                    {"symbol": symbol, "positionAmt": qty,
                        "entryPrice": price, "positionSide": "LONG"}
                ]
            }
        )
        fsm.handle(msg_portfolio)

        # Allow async tasks to run
        await asyncio.sleep(0.1)

        # Check if dispatch was called
        if not mock_dispatch.called:
            pytest.fail("_dispatch_decision was NOT called!")

        # Check decision content
        args, _ = mock_dispatch.call_args
        decision = args[0]
        print(f"Decision: {decision}")

    # 2. Verify ManageFlowFSM state
    _, manage_flow, _ = fsm._get_or_create_flows(symbol)
    assert manage_flow.position_qty == Decimal(qty)
    assert manage_flow.state == ManageState.BRACKETS_PENDING or manage_flow.state == ManageState.BRACKETS_PLACED

    # 3. Verify brackets were placed
    # Expect 2 calls: SL and TP
    # Note: place_order might be called via _emit_place_order -> _execute_decision -> adapter.place_stop_market...
    # We mocked place_stop_market_close_position and place_take_profit_market_close_position

    assert fsm.adapter.place_stop_market_close_position.called
    assert fsm.adapter.place_limit_reduce_only.called or fsm.adapter.place_take_profit_market_close_position.called


@pytest.mark.asyncio
async def test_recalc_duplication_bug(fsm):
    """
    Verify Defect #6 Fix: Recalc cancels old orders before placing new ones.
    """
    symbol = "BTCUSDT"

    # 1. Setup initial state (Position open, brackets placed)
    fsm._test_position_state[symbol] = {
        "symbol": symbol,
        "qty": Decimal("1.0"),
        "avg_price": Decimal("50000.0"),
        "side": "BUY",
        "source": "mock_provider"
    }
    _, manage_flow, _ = fsm._get_or_create_flows(symbol)
    manage_flow.position_qty = Decimal("1.0")
    manage_flow.position_entry_price = Decimal("50000.0")
    manage_flow.position_side = "BUY"
    manage_flow.sl_order_id = "SL-1"
    manage_flow.tp_order_id = "TP-1"
    manage_flow.state = ManageState.BRACKETS_PLACED

    # Reset mock counts
    fsm.adapter.place_stop_market_close_position.reset_mock()
    fsm.adapter.place_limit_reduce_only.reset_mock()
    fsm.adapter.cancel_order.reset_mock()

    # 2. Trigger Scale-In (FILL event)
    # Update mock state to reflect new position
    fsm._test_position_state[symbol] = {
        "symbol": symbol,
        "qty": Decimal("1.5"),
        "avg_price": Decimal("50333.33"),
        "side": "BUY",
        "source": "mock_provider"
    }

    # This should trigger _recalc_aggregated_brackets
    msg = Message(
        op="EVT",
        verb="FILL",
        src="adapter",
        dst="execution_position",
        pld={
            "symbol": symbol,
            "qty": "0.5",  # Scale in
            "price": "51000.0",
            "side": "BUY",
            "order_type": "MARKET",
            "orderId": "1002"
        }
    )

    fsm.handle(msg)
    await asyncio.sleep(0.1)

    # 3. Verify Recalc Logic

    # Check Cancellation of OLD brackets (The Fix)
    assert fsm.adapter.cancel_order.called
    assert fsm.adapter.cancel_order.call_count >= 2  # SL and TP

    # Check Placed Orders (Should be 2 new brackets)
    assert fsm.adapter.place_stop_market_close_position.called
    assert fsm.adapter.place_limit_reduce_only.called or fsm.adapter.place_take_profit_market_close_position.called


@pytest.mark.asyncio
async def test_startup_missing_brackets_bug(fsm):
    """Verify Defect #1 Fix: Startup reconciliation triggers bracket creation."""
    symbol = "BTCUSDT"

    # Mock adapter to return position but NO orders
    fsm.adapter.get_open_positions = AsyncMock(return_value=[
        {"symbol": symbol, "positionAmt": "1.0",
            "entryPrice": "50000", "positionSide": "LONG"}
    ])
    fsm.adapter.get_open_orders = AsyncMock(return_value=[])

    # Mock guardian to return empty bracket set (unprotected)
    fsm.order_guardian.get_bracket_set = MagicMock(return_value=None)

    # Run startup reconcile
    await fsm._startup_order_guardian_reconcile()

    # Allow async tasks
    await asyncio.sleep(0.1)

    # Check if brackets were placed (The Fix)
    assert fsm.adapter.place_stop_market_close_position.called is True, "Brackets should be placed on startup for unprotected position"
    assert fsm.adapter.place_limit_reduce_only.called is True or fsm.adapter.place_take_profit_market_close_position.called is True
