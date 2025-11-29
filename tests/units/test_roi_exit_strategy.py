import pytest
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.roi_exit_strategy import ROIExitStrategy


class TestROIExitStrategy:
    
    def test_initialization(self):
        strategy = ROIExitStrategy(target_roi_pct=50.0)
        assert strategy.target_roi_decimal == Decimal("0.50")
        assert strategy.get_metrics()["roi_close_commands_total"] == 0

    def test_ignores_irrelevant_events(self):
        strategy = ROIExitStrategy()
        msg = Message(op="EVT", verb="TRADE_EXECUTED", pld={}, src="test", dst="test")
        assert strategy.handle(msg) is None

    def test_no_positions(self):
        strategy = ROIExitStrategy()
        msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", pld={"positions": []}, src="test", dst="test")
        assert strategy.handle(msg) is None

    def test_roi_below_target(self):
        strategy = ROIExitStrategy(target_roi_pct=50.0)
        # Long position: Entry 100, Current ~104 (PnL 4), Lev 10
        # Margin = (1 * 100) / 10 = 10
        # ROI = 4 / 10 = 40% < 50%
        pos = {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "entryPrice": "100.0",
            "unRealizedProfit": "4.0",
            "leverage": "10"
        }
        msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", pld={"positions": [pos]}, src="test", dst="test")
        assert strategy.handle(msg) is None

    def test_roi_meets_target(self):
        strategy = ROIExitStrategy(target_roi_pct=50.0)
        # Long position: Entry 100, Current ~105 (PnL 5), Lev 10
        # Margin = (1 * 100) / 10 = 10
        # ROI = 5 / 10 = 50% >= 50%
        pos = {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "entryPrice": "100.0",
            "unRealizedProfit": "5.0",
            "leverage": "10"
        }
        msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", pld={"positions": [pos]}, src="test", dst="test")
        
        cmd = strategy.handle(msg)
        assert cmd is not None
        assert cmd.op == "CMD"
        assert cmd.verb == "CLOSE"
        assert cmd.pld["symbol"] == "BTCUSDT"
        assert cmd.pld["reason"] == "ROI_TARGET_MET"
        assert cmd.pld["roi"] == 0.5
        assert strategy.get_metrics()["roi_close_commands_total"] == 1

    def test_roi_exceeds_target(self):
        strategy = ROIExitStrategy(target_roi_pct=50.0)
        # ROI 100%
        pos = {
            "symbol": "ETHUSDT",
            "positionAmt": "10.0",
            "entryPrice": "2000.0",
            "unRealizedProfit": "200.0", # PnL
            "leverage": "10"
        }
        # Margin = (10 * 2000) / 10 = 2000
        # ROI = 200 / 2000 = 10% ... wait math check
        # Margin = 20000 / 10 = 2000. PnL 200. ROI 0.1.
        
        # Let's make ROI 60%
        # Margin 2000. Need PnL 1200.
        pos["unRealizedProfit"] = "1200.0"
        
        msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", pld={"positions": [pos]}, src="test", dst="test")
        cmd = strategy.handle(msg)
        assert cmd is not None
        assert cmd.pld["roi"] == 0.6

    def test_handles_zero_amount(self):
        strategy = ROIExitStrategy()
        pos = {"symbol": "BTC", "positionAmt": "0", "entryPrice": "100", "unRealizedProfit": "0"}
        msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", pld={"positions": [pos]}, src="test", dst="test")
        assert strategy.handle(msg) is None

    def test_handles_bad_data(self):
        strategy = ROIExitStrategy()
        # Missing required fields for Pydantic validation
        pos = {"symbol": "BTC", "positionAmt": "invalid"} 
        msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", pld={"positions": [pos]}, src="test", dst="test")
        assert strategy.handle(msg) is None
        assert strategy.get_metrics()["validation_errors"] > 0
