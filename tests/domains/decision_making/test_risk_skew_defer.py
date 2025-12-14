"""
Test for Risk Skew Guard.

Commit 5: DEFER + limiter for stale risk data.
DoD:
- Skew detection: |features.ts - risk.ts| > threshold triggers DEFER
- After max_defer_count DEFERs → NO_TRADE_UNTIL_REFRESH
- NRR-RISK-STALE logged
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
        fsm.emitted_events.append({"event": event_name, "payload": payload})
    
    fsm.emit = MagicMock(side_effect=track_emit)
    fsm.listen = MagicMock()
    return fsm


@pytest.fixture
def base_config():
    """Base config with MR in gateway mode and risk_skew config."""
    return {
        "trading": {
            "decision": {"mode": "standard"},
            "tca_prefs": {"max_slippage_bps": 10},
            "risk_budgets": {"trade_cvar95_max_bps": 100},
            "mean_reversion_1m": {
                "enabled": True,
                "emit_trade_intent_directly": False,
                "assets": {"DOGEUSDT": {"enabled": True}}
            }
        },
        "domains": {
            "decision_making": {
                "risk_skew": {
                    "max_skew_sec": 5,
                    "max_defer_count": 3,
                    "defer_cooldown_sec": 2
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
            "why_chain": ["bb_lower"],
            "cooldown_class": "mr_entry",
            "price_ctx": {"entry_price": "0.08"},
            "flat_regime": "FLAT_NORMAL",
            "rid": "test-skew-001",
            "position_size_usd": 100.0
        }
    )


class TestRiskSkewDefer:
    """Test risk skew detection and DEFER logic."""
    
    def test_skew_within_threshold_passes(self, mock_fsm, base_config, mr_signal_event):
        """If skew within threshold, signal passes risk skew gate."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        current_ts = int(time.time() * 1000)
        
        # Risk and features are in sync (2 sec skew, max is 5)
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "ts": current_ts - 2000,  # 2 seconds ago
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3},
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": current_ts}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        dm.latest_portfolio = {"positions": []}
        
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should emit TRADE_INTENT_PROPOSED
        emitted = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" in emitted
    
    def test_skew_exceeds_threshold_defers(self, mock_fsm, base_config, mr_signal_event):
        """If skew exceeds threshold, signal is DEFERRED with NRR-RISK-STALE."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        current_ts = int(time.time() * 1000)
        
        # Risk is stale (10 sec skew, max is 5)
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "ts": current_ts - 10000,  # 10 seconds ago
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3},
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": current_ts}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        dm.latest_portfolio = {"positions": []}
        
        dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should NOT emit TRADE_INTENT_PROPOSED
        emitted = [e["event"] for e in mock_fsm.emitted_events]
        assert "EVT:TRADE_INTENT_PROPOSED" not in emitted
    
    def test_defer_count_increments(self, mock_fsm, base_config, mr_signal_event):
        """Each DEFER should increment the defer count."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        current_ts = int(time.time() * 1000)
        
        # Stale risk
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "ts": current_ts - 10000,
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3},
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": current_ts}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        dm.latest_portfolio = {"positions": []}
        
        # First defer
        dm._on_mr_signal_gateway(mr_signal_event)
        assert dm._qos_state.get("risk_skew_defer_DOGEUSDT") == 1
        
        # Second defer
        dm._on_mr_signal_gateway(mr_signal_event)
        assert dm._qos_state.get("risk_skew_defer_DOGEUSDT") == 2
        
        # Third defer
        dm._on_mr_signal_gateway(mr_signal_event)
        assert dm._qos_state.get("risk_skew_defer_DOGEUSDT") == 3
    
    def test_after_max_defer_escalates_to_no_trade(self, mock_fsm, base_config, mr_signal_event, caplog):
        """After max_defer_count, should escalate to NO_TRADE_UNTIL_REFRESH."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        import logging
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        current_ts = int(time.time() * 1000)
        
        dm.symbol_states["DOGEUSDT"]["risk"] = {
            "ts": current_ts - 10000,
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3},
        }
        dm.symbol_states["DOGEUSDT"]["features"] = {"ts": current_ts}
        dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
        dm.latest_portfolio = {"positions": []}
        
        # Trigger max_defer_count (3) DEFERs
        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                dm._on_mr_signal_gateway(mr_signal_event)
        
        # Should have logged NO_TRADE_UNTIL_REFRESH on the 3rd attempt
        assert dm._qos_state.get("risk_skew_defer_DOGEUSDT") == 3
        assert "NO_TRADE_UNTIL_REFRESH" in caplog.text
        assert "NRR-RISK-STALE" in caplog.text


class TestGetRiskSkewConfig:
    """Test _get_risk_skew_config helper."""
    
    def test_returns_default_when_no_config(self, mock_fsm):
        """Should return default when config is missing."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        minimal_config = {
            "trading": {
                "decision": {"mode": "standard"},
                "tca_prefs": {},
                "risk_budgets": {},
            }
        }
        dm = DecisionMaking(config=minimal_config, fsm=mock_fsm)
        
        assert dm._get_risk_skew_config("max_skew_sec", 99) == 99
    
    def test_reads_from_dict_config(self, mock_fsm, base_config):
        """Should read values from dict config."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        dm = DecisionMaking(config=base_config, fsm=mock_fsm)
        
        # Should read 5 from config (not default 99)
        assert dm._get_risk_skew_config("max_skew_sec", 99) == 5
        assert dm._get_risk_skew_config("max_defer_count", 99) == 3
