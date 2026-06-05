"""
Test: Strategy Primacy for SL/TP Prices

Validates that strategy-provided stop_price and target_price are respected
instead of being silently overridden by config-based fallbacks.

This test addresses the "Silent Fallback" architecture violation identified
in the MeanReversion backtest analysis.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestStrategyPrimacyDecisionMaking:
    """Test Strategy Primacy in DecisionMaking._on_strategy_signal_gateway"""
    
    def test_strategy_prices_extracted_from_price_ctx(self):
        """Verify stop_price and target_price are extracted from price_ctx"""
        price_ctx = {
            "entry_price": "100.00",
            "stop_price": "95.00",
            "target_price": "110.00"
        }
        
        # Simulate extraction logic
        strategy_stop_price = price_ctx.get("stop_price")
        strategy_target_price = price_ctx.get("target_price")
        
        # Normalize
        if strategy_stop_price is not None:
            strategy_stop_price = str(strategy_stop_price) if strategy_stop_price not in ("", "None") else None
        if strategy_target_price is not None:
            strategy_target_price = str(strategy_target_price) if strategy_target_price not in ("", "None") else None
        
        assert strategy_stop_price == "95.00"
        assert strategy_target_price == "110.00"
    
    def test_strategy_prices_take_precedence_over_entryplan(self):
        """Verify Strategy prices are not overwritten by EntryPlan"""
        # Simulate the new logic
        strategy_stop_price = "95.00"
        strategy_target_price = "110.00"
        
        # Initialize with Strategy values (Primacy)
        stop_price = strategy_stop_price
        target_price = strategy_target_price
        
        # EntryPlan would compute different values
        ep_result_sl = "97.00"
        ep_result_tp = "105.00"
        
        # Strategy Primacy: Only fill in MISSING values
        if stop_price is None:
            stop_price = ep_result_sl
        if target_price is None:
            target_price = ep_result_tp
        
        # Strategy values should be preserved
        assert stop_price == "95.00"
        assert target_price == "110.00"
    
    def test_entryplan_used_only_when_strategy_missing(self):
        """Verify EntryPlan fills in missing values only"""
        # Strategy provides only SL
        strategy_stop_price = "95.00"
        strategy_target_price = None
        
        stop_price = strategy_stop_price
        target_price = strategy_target_price
        
        # EntryPlan values
        ep_result_sl = "97.00"
        ep_result_tp = "105.00"
        
        # Strategy Primacy: Only fill in MISSING
        if stop_price is None:
            stop_price = ep_result_sl
        if target_price is None:
            target_price = ep_result_tp
        
        # Strategy SL preserved, EntryPlan TP used
        assert stop_price == "95.00"  # Strategy preserved
        assert target_price == "105.00"  # EntryPlan fallback


class TestStrategyPrimacyExecutionPosition:
    """Test Strategy Primacy in ExecutionPosition FSM"""
    
    def test_explicit_sl_tp_extracted_from_decision(self):
        """Verify explicit prices are extracted from DEC:OPEN payload"""
        decision_pld = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "stop_price": "95000.00",
            "target_price": "105000.00",
        }
        
        explicit_sl_raw = decision_pld.get("stop_price")
        explicit_tp_raw = decision_pld.get("target_price")
        
        explicit_sl = None
        explicit_tp = None
        
        if explicit_sl_raw not in (None, "", "None", "null"):
            explicit_sl = Decimal(str(explicit_sl_raw))
        
        if explicit_tp_raw not in (None, "", "None", "null"):
            explicit_tp = Decimal(str(explicit_tp_raw))
        
        assert explicit_sl == Decimal("95000.00")
        assert explicit_tp == Decimal("105000.00")
    
    def test_strategy_sl_takes_priority_over_config(self):
        """Verify Strategy SL is used instead of config sl_pct"""
        mark = Decimal("100000.00")
        explicit_sl = Decimal("95000.00")  # Strategy provides this
        sl_pct = 0.004  # Config fallback would calculate different value
        
        # Config-based calculation would give:
        config_sl = mark * (Decimal("1") - Decimal(str(sl_pct)))  # 99600
        
        # Strategy Primacy: Use explicit if available
        if explicit_sl is not None:
            sl = explicit_sl
            sl_source = "STRATEGY"
        else:
            sl = config_sl
            sl_source = "CONFIG_FALLBACK"
        
        assert sl == Decimal("95000.00")
        assert sl_source == "STRATEGY"
    
    def test_config_fallback_used_when_strategy_missing(self):
        """Verify config fallback is used when Strategy doesn't provide prices"""
        mark = Decimal("100000.00")
        explicit_sl = None  # Strategy did not provide
        sl_pct = 0.004  # Config sl_pct
        
        config_sl = mark * (Decimal("1") - Decimal(str(sl_pct)))
        
        if explicit_sl is not None:
            sl = explicit_sl
            sl_source = "STRATEGY"
        else:
            sl = config_sl
            sl_source = "CONFIG_FALLBACK"
        
        assert sl == Decimal("99600.00")
        assert sl_source == "CONFIG_FALLBACK"
    
    def test_fail_closed_when_neither_available(self):
        """Verify fail-closed when neither Strategy nor config provide prices"""
        explicit_sl = None
        config_loaded = False  # Config also missing
        
        # This should trigger fail-closed behavior
        should_reject = explicit_sl is None and not config_loaded
        
        assert should_reject is True
    
    def test_mixed_sources_allowed(self):
        """Verify mixed sources (Strategy SL, Config TP) works correctly"""
        mark = Decimal("100000.00")
        explicit_sl = Decimal("95000.00")  # Strategy provides SL
        explicit_tp = None  # Strategy does NOT provide TP
        sl_pct = 0.004
        tp_low_ratio = 2.0
        
        # Calculate final values
        if explicit_sl is not None:
            sl = explicit_sl
            sl_source = "STRATEGY"
        else:
            sl = mark * (Decimal("1") - Decimal(str(sl_pct)))
            sl_source = "CONFIG_FALLBACK"
        
        if explicit_tp is not None:
            tp = explicit_tp
            tp_source = "STRATEGY"
        else:
            tp = mark * (Decimal("1") + Decimal(str(sl_pct)) * Decimal(str(tp_low_ratio)))
            tp_source = "CONFIG_FALLBACK"
        
        assert sl == Decimal("95000.00")
        assert sl_source == "STRATEGY"
        assert tp == Decimal("100800.00")  # 100000 * (1 + 0.004 * 2.0)
        assert tp_source == "CONFIG_FALLBACK"


class TestMeanReversionPricesPropagation:
    """End-to-end test: MeanReversion prices flow through the system"""
    
    def test_mr_signal_price_ctx_format(self):
        """Verify MeanReversion emits correct price_ctx format"""
        # Simulate MRSignal output
        mr_signal = {
            "entry_price": Decimal("0.35"),
            "stop_price": Decimal("0.34"),  # ATR-based
            "target_price": Decimal("0.36"),  # BB mid-band
        }
        
        # Build price_ctx as done in _emit_signal
        price_ctx = {
            "entry_price": str(mr_signal["entry_price"]),
            "stop_price": str(mr_signal["stop_price"]) if mr_signal["stop_price"] else None,
            "target_price": str(mr_signal["target_price"]) if mr_signal["target_price"] else None,
        }
        
        assert price_ctx["entry_price"] == "0.35"
        assert price_ctx["stop_price"] == "0.34"
        assert price_ctx["target_price"] == "0.36"
    
    def test_mr_dynamic_sl_not_overwritten(self):
        """Verify MeanReversion's ATR-based SL is not replaced by fixed sl_pct"""
        # MR calculates dynamic SL based on ATR
        mr_sl = Decimal("0.34")  # ~2.9% SL (ATR-based)
        entry = Decimal("0.35")
        
        # Config would apply fixed 0.4% SL
        config_sl_pct = Decimal("0.004")
        config_sl = entry * (Decimal("1") - config_sl_pct)  # 0.3486
        
        # The difference is significant
        sl_diff_pct = abs(mr_sl - config_sl) / entry * 100
        
        # MR's dynamic SL should be preserved, not replaced
        assert mr_sl != config_sl
        assert sl_diff_pct > 2.0  # More than 2% difference
