"""
TASK47c-C: Bridge Capacity Gate Tests.

Tests for max_notional capacity gate in AuroraBridge.
TDD approach: Write failing tests first, then implement the gate.
"""
import pytest
pytestmark = pytest.mark.skip(reason="Refactoring: AuroraBridge class deleted")

import time
from unittest.mock import MagicMock, patch, AsyncMock
from vfoundation.core.protocol import Message
from vfoundation.dr import wal as wal_mod


class TestBridgeCapacityGate:
    """Tests for capacity gate in AuroraBridge."""

    @pytest.fixture(autouse=True)
    def _isolate_wal_dir(self, tmp_path):
        """Prevent tests from writing into real ops/wal."""
        prev = wal_mod.WAL_DIR
        wal_mod.set_wal_dir(tmp_path)
        try:
            yield
        finally:
            wal_mod.set_wal_dir(prev)
    
    def _make_bridge_with_mocks(
        self,
        equity_free_usdt: float = 10000.0,
        target_leverage: int = 20,
        max_notional_utilization: float = 0.5,
        margin_mode: str = "isolated",
        leverage_policy: str = "verify_only",
    ):
        """Create AuroraBridge with mocked config and portfolio."""
        from apps.reference.main import AuroraBridge
        from apps.reference.config_models import AuroraConfig, InstrumentExecutionConfig
        from vfoundation.core.fsm_core import FSMCore
        
        # Mock FSM
        fsm = MagicMock(spec=FSMCore)
        fsm.emit = MagicMock()
        fsm.listen = MagicMock()
        
        # Create config with per-instrument execution config
        config = MagicMock(spec=AuroraConfig)
        config.instruments = {
            "BTCUSDT": MagicMock(
                tick_size=0.1,
                step_size=0.001,
                execution=InstrumentExecutionConfig(
                    margin_mode=margin_mode,
                    target_leverage=target_leverage,
                    leverage_policy=leverage_policy,
                    max_notional_utilization=max_notional_utilization,
                ),
            )
        }
        
        # Mock domains
        config.domains = MagicMock()
        config.domains.execution_position = MagicMock()
        config.domains.execution_position.execution = MagicMock()
        config.domains.execution_position.execution.exposure = MagicMock()
        config.domains.execution_position.execution.exposure.positions_stale_ttl_sec = 60
        config.domains.debug = None
        
        # Mock bridge config
        config.bridge = MagicMock()
        config.bridge.retry_scheduler = MagicMock()
        config.bridge.retry_scheduler.max_attempts = 3
        config.bridge.retry_scheduler.min_retry_delay_ms = 1000
        config.bridge.retry_scheduler.backoff_factor = 2.0
        config.bridge.retry_scheduler.jitter_ms = 100
        
        bridge = AuroraBridge(fsm=fsm, config=config)
        
        # Set portfolio state (fresh)
        bridge._last_portfolio = {
            "equity_free_usdt": equity_free_usdt,
            "positions_last_ts_ms": int(time.time() * 1000),
        }
        bridge._last_portfolio_ts = int(time.time() * 1000)
        
        return bridge, fsm, config
    
    def test_bridge_drops_when_notional_exceeds_capacity_live(self):
        """
        When notional > max_notional (equity * leverage * utilization),
        bridge should emit INTENT_DROPPED with reason=capacity_exceeded.
        """
        bridge, fsm, config = self._make_bridge_with_mocks(
            equity_free_usdt=10000.0,
            target_leverage=20,
            max_notional_utilization=0.5,
        )
        # max_notional = 10000 * 20 * 0.5 = 100,000 USDT
        
        # Intent with notional > 100,000
        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid="test-rid-001",
            pld={
                "instrument": "BTCUSDT",
                "side": "buy",
                "order": {
                    "qty": "3.0",  # 3 BTC
                    "price_ref": 50000.0,  # @ 50k = 150,000 notional > 100k max
                },
            },
        )
        
        # Process intent
        bridge.on_trade_intent_proposed_sync(intent)
        
        # Should emit INTENT_DROPPED with capacity_exceeded
        emit_calls = [c for c in fsm.emit.call_args_list if c[0][0] == "EVT:INTENT_DROPPED"]
        assert len(emit_calls) > 0, "Expected INTENT_DROPPED event for capacity exceeded"
        
        dropped_pld = emit_calls[0][0][1]  # First call, second arg is payload
        assert dropped_pld.get("reason") == "capacity_exceeded"
        
    def test_bridge_allows_when_within_capacity(self):
        """
        When notional <= max_notional, bridge should dispatch CMD:OPEN normally.
        """
        bridge, fsm, config = self._make_bridge_with_mocks(
            equity_free_usdt=10000.0,
            target_leverage=20,
            max_notional_utilization=0.5,
        )
        # max_notional = 10000 * 20 * 0.5 = 100,000 USDT
        
        # Intent with notional <= 100,000
        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid="test-rid-002",
            pld={
                "instrument": "BTCUSDT",
                "side": "buy",
                "order": {
                    "qty": "1.0",  # 1 BTC
                    "price_ref": 50000.0,  # @ 50k = 50,000 notional <= 100k max
                },
            },
        )
        
        # Process intent
        bridge.on_trade_intent_proposed_sync(intent)
        
        # Should NOT emit INTENT_DROPPED
        drop_calls = [c for c in fsm.emit.call_args_list if c[0][0] == "EVT:INTENT_DROPPED"]
        assert len(drop_calls) == 0, "Should not drop when within capacity"

        # WAL should contain CMD:OPEN record (bridge persists it best-effort)
        entries = wal_mod.read_all()
        cmd_open = [e for e in entries if e.get("op") == "CMD" and e.get("verb") == "OPEN"]
        assert len(cmd_open) >= 1, "Expected CMD:OPEN persisted to WAL"

    def test_bridge_accepts_equity_free_usdt_as_string(self):
        """Regression: portfolio equity often arrives as string; must not crash capacity gate."""
        bridge, fsm, config = self._make_bridge_with_mocks(
            equity_free_usdt="10000.0",
            target_leverage=20,
            max_notional_utilization=0.5,
        )

        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid="test-rid-002b",
            pld={
                "instrument": "BTCUSDT",
                "side": "buy",
                "order": {
                    "qty": "1.0",
                    "price_ref": 50000.0,
                },
            },
        )

        bridge.on_trade_intent_proposed_sync(intent)

        drop_calls = [c for c in fsm.emit.call_args_list if c[0][0] == "EVT:INTENT_DROPPED"]
        assert len(drop_calls) == 0, "Should not drop when equity is a numeric string"
        
    def test_bridge_denies_when_missing_price_ref_for_notional(self):
        """
        When intent has no notional and no way to calculate it (missing qty/price_ref),
        bridge should deny with reason=missing_price_ref (fail-closed).
        """
        bridge, fsm, config = self._make_bridge_with_mocks()
        
        # Intent without price_ref or notional
        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid="test-rid-003",
            pld={
                "instrument": "BTCUSDT",
                "side": "buy",
                "order": {
                    "qty": "1.0",
                    # No price_ref!
                },
            },
        )
        
        # Process intent
        bridge.on_trade_intent_proposed_sync(intent)
        
        # Should emit INTENT_DROPPED with missing_price_ref
        drop_calls = [c for c in fsm.emit.call_args_list if c[0][0] == "EVT:INTENT_DROPPED"]
        assert len(drop_calls) > 0, "Expected INTENT_DROPPED for missing price_ref"
        
        dropped_pld = drop_calls[0][0][1]
        assert "missing" in dropped_pld.get("reason", "").lower() or "price" in dropped_pld.get("reason", "").lower()
        
    def test_bridge_denies_when_missing_execution_config(self):
        """
        When per-instrument execution config is missing for LIVE mode,
        bridge should deny (defensive fail-closed).
        """
        bridge, fsm, config = self._make_bridge_with_mocks()
        
        # Remove execution config for BTCUSDT
        config.instruments["BTCUSDT"].execution = None
        
        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid="test-rid-004",
            pld={
                "instrument": "BTCUSDT",
                "side": "buy",
                "order": {
                    "qty": "1.0",
                    "price_ref": 50000.0,
                },
            },
        )
        
        # Process intent
        bridge.on_trade_intent_proposed_sync(intent)
        
        # Should emit INTENT_DROPPED with missing execution config
        drop_calls = [c for c in fsm.emit.call_args_list if c[0][0] == "EVT:INTENT_DROPPED"]
        assert len(drop_calls) > 0, "Expected INTENT_DROPPED for missing execution config"
        
    def test_bridge_does_not_use_stale_portfolio_for_capacity(self):
        """
        Existing stale portfolio gate should still work - capacity gate doesn't override it.
        """
        bridge, fsm, config = self._make_bridge_with_mocks()
        
        # Make portfolio stale
        bridge._last_portfolio_ts = 0  # Very old
        
        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid="test-rid-005",
            pld={
                "instrument": "BTCUSDT",
                "side": "buy",
                "order": {
                    "qty": "1.0",
                    "price_ref": 50000.0,
                },
            },
        )
        
        # Process intent (should defer due to stale portfolio, not fail-closed)
        bridge.on_trade_intent_proposed_sync(intent)
        
        # Should emit INTENT_DEFERRED (stale portfolio) rather than capacity gate rejection
        defer_calls = [c for c in fsm.emit.call_args_list if "DEFERRED" in c[0][0]]
        # Original stale behavior should still trigger
        assert len(defer_calls) > 0 or len(bridge._deferred) > 0, \
            "Stale portfolio should still trigger defer, not capacity gate first"
