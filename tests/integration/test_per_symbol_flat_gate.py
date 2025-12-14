"""
Integration test: Flip is Close -> Fill -> Open sequence.

Commit 4: Strict sequential trading contract.
DoD:
- OPEN blocked when position exists (per-symbol)  
- After CLOSE fill confirmed, cooldown applied, then OPEN allowed
"""

import pytest
from unittest.mock import MagicMock
from decimal import Decimal
import time

from vfoundation.core.protocol import Message


@pytest.fixture
def mock_fsm():
    """Create mock FSM with emit tracking."""
    fsm = MagicMock()
    fsm.emitted_events = []
    
    def track_emit(event_name, payload, why=None, data_ref=None):
        fsm.emitted_events.append({
            "event": event_name,
            "payload": payload,
        })
    
    fsm.emit = MagicMock(side_effect=track_emit)
    fsm.listen = MagicMock()
    return fsm


@pytest.fixture
def base_config():
    """Base config with MR in gateway mode."""
    return {
        "trading": {
            "decision": {"mode": "standard"},
            "tca_prefs": {"max_slippage_bps": 10},
            "risk_budgets": {"trade_cvar95_max_bps": 100},
            "mean_reversion_1m": {
                "enabled": True,
                "emit_trade_intent_directly": False,
                "assets": {
                    "DOGEUSDT": {"enabled": True},
                    "XRPUSDT": {"enabled": True}
                }
            }
        }
    }


@pytest.fixture
def mr_signal_event():
    """Valid MR signal event."""
    return Message(
        op="EVT",
        verb="MR_SIGNAL_PRODUCED",
        src="mr_handler",
        dst="decision_making",
        pld={
            "strategy_id": "MR",
            "symbol": "DOGEUSDT",
            "ts": int(time.time() * 1000),
            "side": "BUY",
            "confidence": 0.8,
            "qty_hint": "100.0",
            "why_chain": ["bb_lower", "rsi_oversold"],
            "cooldown_class": "mr_entry",
            "price_ctx": {
                "entry_price": "0.08",
                "stop_price": "0.075",
                "target_price": "0.085"
            },
            "flat_regime": "FLAT_NORMAL",
            "rid": "test-flat-gate",
            "position_size_usd": 100.0
        }
    )


class TestPerSymbolFlatGate:
    """Test per-symbol FLAT gate enforcement."""
    
    def test_open_blocked_when_position_exists(self, mock_fsm, base_config, mr_signal_event):
        """OPEN should be blocked when position exists for symbol."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        # Set portfolio with existing DOGEUSDT position
        dm.latest_portfolio = {
            "positions": [
                {"symbol": "DOGEUSDT", "positionAmt": "1000.0"}  # Long position
            ]
        }
        # Set passing conditions for other gates
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3}
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": int(time.time() * 1000)}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should NOT emit TRADE_INTENT_PROPOSED due to FLAT gate
        emitted = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" not in emitted
    
    def test_open_allowed_when_flat(self, mock_fsm, base_config, mr_signal_event):
        """OPEN should be allowed when position is FLAT."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        # Set portfolio with NO DOGEUSDT position
        dm.latest_portfolio = {
            "positions": []  # No positions
        }
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3}
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": int(time.time() * 1000)}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should emit TRADE_INTENT_PROPOSED
        emitted = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" in emitted
    
    def test_per_symbol_isolation(self, mock_fsm, base_config, mr_signal_event):
        """ETH position should NOT block DOGE OPEN (per-symbol isolation)."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        # Set portfolio with ETHUSDT position (different symbol)
        dm.latest_portfolio = {
            "positions": [
                {"symbol": "ETHUSDT", "positionAmt": "0.5"}  # ETH position
            ]
        }
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3}
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": int(time.time() * 1000)}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        
        # Request DOGEUSDT OPEN
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should emit TRADE_INTENT_PROPOSED (ETH doesn't block DOGE)
        emitted = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" in emitted
    
    def test_zero_position_is_flat(self, mock_fsm, base_config, mr_signal_event):
        """Zero position (positionAmt=0) should be treated as FLAT."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        # Set portfolio with zero DOGEUSDT position
        dm.latest_portfolio = {
            "positions": [
                {"symbol": "DOGEUSDT", "positionAmt": "0"}  # Closed position
            ]
        }
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3}
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": int(time.time() * 1000)}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should emit TRADE_INTENT_PROPOSED
        emitted = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" in emitted
    
    def test_unknown_portfolio_blocks_open_fail_closed(self, mock_fsm, base_config, mr_signal_event):
        """MR_SIGNAL with unknown portfolio should DEFER, not OPEN (fail-closed).
        
        Commit 4.1: NRR-PORTFOLIO-UNKNOWN enforcement.
        """
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        # NO portfolio data (simulates startup before first portfolio sync)
        dm.latest_portfolio = None
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3}
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": int(time.time() * 1000)}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should NOT emit TRADE_INTENT_PROPOSED (FAIL-CLOSED)
        emitted_types = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" not in emitted_types
        
        # Verify DEFERRED event (Commit 4.1 Fix)
        deferred_events = [e for e in mock_fsm.emitted_events if e["event"] == "EVT:INTENT_DEFERRED"]
        assert len(deferred_events) == 1
        assert deferred_events[0]["payload"]["reason"] == "NRR-PORTFOLIO-UNKNOWN"


class TestCheckSymbolIsFlat:
    """Test _check_symbol_is_flat helper method."""
    
    def test_no_portfolio_returns_not_flat_fail_closed(self, mock_fsm, base_config):
        """No portfolio data should return NOT FLAT (fail-closed)."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        dm.latest_portfolio = None
        
        # FAIL-CLOSED: Unknown portfolio = NOT FLAT
        assert dm._check_symbol_is_flat("DOGEUSDT") is False
    
    def test_empty_positions_returns_flat(self, mock_fsm, base_config):
        """Empty positions list should return FLAT."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        dm.latest_portfolio = {"positions": []}
        
        assert dm._check_symbol_is_flat("DOGEUSDT") is True
    
    def test_position_exists_returns_not_flat(self, mock_fsm, base_config):
        """Existing position should return NOT FLAT."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        dm.latest_portfolio = {
            "positions": [{"symbol": "DOGEUSDT", "positionAmt": "100.0"}]
        }
        
        assert dm._check_symbol_is_flat("DOGEUSDT") is False
    
    def test_negative_position_returns_not_flat(self, mock_fsm, base_config):
        """Short position (negative qty) should return NOT FLAT."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        dm.latest_portfolio = {
            "positions": [{"symbol": "DOGEUSDT", "positionAmt": "-100.0"}]
        }
        
        assert dm._check_symbol_is_flat("DOGEUSDT") is False
