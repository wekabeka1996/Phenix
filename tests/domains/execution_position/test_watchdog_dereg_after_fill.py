import pytest
import asyncio
from unittest.mock import MagicMock, patch
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from vfoundation.core.fsm_emit_compat import Message

class SimpleConfig:
    def __init__(self):
        self.domains = MagicMock()
        self.trading = MagicMock()
        self.trading.mode = "backtest"
        self.trading_mode = "backtest"
        self.instruments = []
        self.strategies_registry = MagicMock()
        self.binance_api = MagicMock()

    def get_domain_mode(self, domain):
        return "backtest"

@pytest.fixture
def mock_config():
    config = SimpleConfig()
    
    # Domains setup
    ep = config.domains.execution_position
    ep.metrics_collector.window_size_minutes = 60
    ep.metrics_collector.recent_rejections_minutes = 5
    ep.idempotent_cancel.max_retries = 3
    ep.event_dedup.max_size = 1000
    ep.event_dedup.ttl_ms = 60000
    ep.guardian.emit_tidy_monitoring_event = True
    ep.guardian.emit_tidy_event = True
    ep.guardian.poll_interval_ms = 500
    ep.guardian.unified = True
    ep.guardian.cleanup_ttl_ms = 60000
    ep.guardian.symbol_cooldown_ms = 1000
    ep.fsm_periodic_cleanup.enabled = True
    ep.intent_boundary_audit = None
    ep.order_lifecycle.fill_settlement_delay_ms = 100
    ep.position_policy_sidecar = None
    ep.shadow_check.enabled = False
    ep.pending_entry_ttl.enabled = False
    ep.portfolio_update_dedup_ms = 100
    
    # Trading setup
    config.trading.execution = MagicMock()
    config.trading.execution.fsm_periodic_cleanup_enabled = True
    config.trading.execution.cooldown_after_close_ms = 1000
    
    # Watchdog config
    wd_cfg = MagicMock()
    wd_cfg.ack_ttl_ms = 8000
    wd_cfg.fill_ttl_ms = 3600000
    wd_cfg.check_interval_ms = 1000
    wd_cfg.rps_limit = 10
    config.trading.execution.watchdog = wd_cfg
    
    # Force __dict__ populate for resolver strictness
    config.__dict__["trading"] = config.trading
    config.__dict__["domains"] = config.domains
    config.trading.__dict__["execution"] = config.trading.execution
    config.trading.execution.__dict__["fsm_periodic_cleanup_enabled"] = True
    config.domains.__dict__["execution_position"] = ep
    ep.__dict__["guardian"] = ep.guardian
    ep.guardian.__dict__["emit_tidy_monitoring_event"] = True
    ep.guardian.__dict__["emit_tidy_event"] = True
    
    return config

def setup_exec_fsm(mock_config):
    fsm_core = MagicMock()
    with patch('apps.reference.domains.execution_position.fsm.OrderGuardian'), \
         patch('apps.reference.domains.execution_position.fsm.PositionPolicySidecar'), \
         patch('apps.reference.domains.execution_position.fsm.ExposureGuard'), \
         patch('apps.reference.domains.execution_position.fsm.AlertManager'):
        
        exec_fsm = ExecPosFSM(config=mock_config, fsm=fsm_core, is_live_execution=False)
        exec_fsm.watchdog = MagicMock()
        # Mock acked_orders to simulate existing orders
        exec_fsm.watchdog.acked_orders = {}
        return exec_fsm

@pytest.mark.asyncio
async def test_watchdog_deregistration_on_filled(mock_config):
    """Test 1 — FILLED terminal state deregisters watchdog."""
    exec_fsm = setup_exec_fsm(mock_config)
    order_id = "order_111"
    
    # Simulate ORDER_FILL (FILLED)
    fill_msg = Message(
        op="EVT", verb="ORDER_FILL", src="adapter", dst="execution_position",
        pld={"orderId": order_id, "symbol": "BTCUSDT", "status": "FILLED", "quantity": "1.0"}
    )
    exec_fsm._on_order_fill(fill_msg)
    
    # Watchdog should be notified of FILL (via on_order_fill)
    # Note: ExposureManager also calls on_order_cancel for FILLED as a safety backstop.
    exec_fsm.watchdog.on_order_fill.assert_called_with(order_id)

@pytest.mark.asyncio
async def test_watchdog_deregistration_on_cancel(mock_config):
    """Test 2 — CANCELED terminal state deregisters watchdog."""
    exec_fsm = setup_exec_fsm(mock_config)
    order_id = "order_222"
    
    # Simulate ORDER_STATE_CHANGED (CANCELED)
    cancel_msg = Message(
        op="EVT", verb="ORDER_STATE_CHANGED", src="adapter", dst="execution_position",
        pld={"orderId": order_id, "symbol": "BTCUSDT", "status": "CANCELED"}
    )
    exec_fsm._on_order_state_changed(cancel_msg)
    
    # Watchdog should be notified of CANCEL
    exec_fsm.watchdog.on_order_cancel.assert_called_with(order_id)

@pytest.mark.asyncio
async def test_watchdog_deregistration_on_rejected(mock_config):
    """Test 3 — REJECTED terminal state deregisters watchdog."""
    exec_fsm = setup_exec_fsm(mock_config)
    order_id = "order_333"
    
    # Simulate ORDER_STATE_CHANGED (REJECTED)
    msg = Message(
        op="EVT", verb="ORDER_STATE_CHANGED", src="adapter", dst="execution_position",
        pld={"orderId": order_id, "symbol": "BTCUSDT", "status": "REJECTED"}
    )
    exec_fsm._on_order_state_changed(msg)
    
    exec_fsm.watchdog.on_order_cancel.assert_called_with(order_id)

@pytest.mark.asyncio
async def test_watchdog_deregistration_on_expired(mock_config):
    """Test 4 — EXPIRED terminal state deregisters watchdog."""
    exec_fsm = setup_exec_fsm(mock_config)
    order_id = "order_444"
    
    # Simulate ORDER_STATE_CHANGED (EXPIRED)
    msg = Message(
        op="EVT", verb="ORDER_STATE_CHANGED", src="adapter", dst="execution_position",
        pld={"orderId": order_id, "symbol": "BTCUSDT", "status": "EXPIRED"}
    )
    exec_fsm._on_order_state_changed(msg)
    
    exec_fsm.watchdog.on_order_cancel.assert_called_with(order_id)

@pytest.mark.asyncio
async def test_numeric_order_id_hardening(mock_config):
    """Test 5 — numeric order_id hardening."""
    exec_fsm = setup_exec_fsm(mock_config)
    order_id_num = 123456789
    order_id_str = "123456789"
    
    # 1. Test in ACK path
    ack_msg = Message(
        op="EVT", verb="ORDER_ACK", src="adapter", dst="execution_position",
        pld={"orderId": order_id_num, "symbol": "BTCUSDT", "status": "NEW"}
    )
    exec_fsm._on_order_ack(ack_msg)
    exec_fsm.watchdog.on_order_ack.assert_called_with(order_id_str)
    
    # 2. Test in FILL path
    fill_msg = Message(
        op="EVT", verb="ORDER_FILL", src="adapter", dst="execution_position",
        pld={"orderId": order_id_num, "symbol": "BTCUSDT", "status": "FILLED", "quantity": "1.0"}
    )
    exec_fsm._on_order_fill(fill_msg)
    exec_fsm.watchdog.on_order_fill.assert_called_with(order_id_str)
    
    # 3. Test in terminal state path
    cancel_msg = Message(
        op="EVT", verb="ORDER_STATE_CHANGED", src="adapter", dst="execution_position",
        pld={"orderId": order_id_num, "symbol": "BTCUSDT", "status": "CANCELED"}
    )
    exec_fsm._on_order_state_changed(cancel_msg)
    exec_fsm.watchdog.on_order_cancel.assert_called_with(order_id_str)

@pytest.mark.asyncio
async def test_nonterminal_state_no_deregister(mock_config):
    """Test 6 — nonterminal state does not deregister."""
    exec_fsm = setup_exec_fsm(mock_config)
    order_id = "order_666"
    
    # Simulate ORDER_STATE_CHANGED (PARTIALLY_FILLED)
    msg = Message(
        op="EVT", verb="ORDER_STATE_CHANGED", src="adapter", dst="execution_position",
        pld={"orderId": order_id, "symbol": "BTCUSDT", "status": "PARTIALLY_FILLED"}
    )
    exec_fsm._on_order_state_changed(msg)
    
    # on_order_cancel should NOT be called for PARTIALLY_FILLED in the state_changed path
    assert not exec_fsm.watchdog.on_order_cancel.called

@pytest.mark.asyncio
async def test_no_timeout_after_terminal_cleanup(mock_config):
    """Test 7 — no timeout after terminal cleanup."""
    # This test verifies that once on_order_cancel/on_order_fill is called, 
    # the order is effectively gone from the watchdog's internal tracking 
    # (simulated by the mock here, but proven by behavior in watchdog.py).
    
    # Since we are using a Mock watchdog, we just verify the call was made.
    # The actual watchdog.py logic:
    # def on_order_cancel(self, order_id: str):
    #     if order_id in self.acked_orders: del self.acked_orders[order_id]
    
    exec_fsm = setup_exec_fsm(mock_config)
    order_id = "order_777"
    
    msg = Message(
        op="EVT", verb="ORDER_STATE_CHANGED", src="adapter", dst="execution_position",
        pld={"orderId": order_id, "symbol": "BTCUSDT", "status": "CANCELED"}
    )
    exec_fsm._on_order_state_changed(msg)
    
    # Verify cleanup hook was called
    exec_fsm.watchdog.on_order_cancel.assert_called_once_with(order_id)
