import logging
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
    MRSymbolState,
    BollingerBands,
    MRSignalType,
    FlatRegime,
    MRParameters
)

logging.basicConfig(level=logging.INFO)

class TestMeanReversionMath(unittest.TestCase):
    def setUp(self):
        self.config = MRStrategyConfig(
            sl_atr_mult=2.0,
            sl_buffer_pct=0.0,
            tp_buffer_pct=0.0,
            tp_to_mid=True,
            min_bb_width=0.001,
            max_bb_width=0.1,
            entry_threshold=0.05,
            rsi_overbought=70,
            rsi_oversold=30
        )
        self.strategy = MeanReversion1mStrategy(self.config, timeframe_sec=60)

    def test_short_stop_loss_calculation(self):
        """
        Verify that SHORT Stop Loss is calculated ABOVE the entry price.
        Logic: SL = Entry + (ATR * Mult)
        """
        symbol = "BTCUSDT"
        
        # Setup State
        # Price = 100
        # BB Upper = 102, Lower = 98 (Mid=100) -> Width=4, %B=0.5
        # To trigger SHORT, we need %B > (1 - entry_threshold) = 0.95
        # Let's set Price = 103 -> %B > 1.0 (Above upper band)
        
        current_price = Decimal("103.0")
        bb = BollingerBands(
            upper=Decimal("102.0"),
            mid=Decimal("100.0"),
            lower=Decimal("98.0"),
            width=Decimal("0.04"), # 4/100
            pct_b=Decimal("1.25")  # (103-98)/4 = 5/4 = 1.25
        )
        atr = Decimal("2.0")
        rsi = Decimal("75.0")
        
        state = MRSymbolState(symbol=symbol)
        state.bb = bb
        state.atr = atr
        state.rsi = rsi
        state.add_bar(MagicMock(close=current_price))
        
        # Params
        mr_params = MRParameters(
            flat_regime=FlatRegime.FLAT_NORMAL,
            sizing_mult=Decimal("1.0"),
            stop_mult=Decimal("1.0"), # Multiplier 1.0
            target_mult=Decimal("1.0")
        )
        
        # Regime (Arbitrary valid one)
        flat_regime = FlatRegime.FLAT_NORMAL
        
        # Execute
        signal = self.strategy._evaluate_signal(
            state=state,
            flat_regime=flat_regime,
            mr_params=mr_params,
            timestamp_ms=1000
        )
        
        # Assertions
        print(f"\nSign Type: {signal.signal_type}")
        print(f"Entry: {signal.entry_price}")
        print(f"ATR: {signal.atr}")
        print(f"SL Mult Config: {self.config.sl_atr_mult}")
        print(f"SL Mult Param: {mr_params.stop_mult}")
        print(f"Stop Price: {signal.stop_price}")
        print(f"Target Price: {signal.target_price}")
        
        # Verify Signal is SHORT
        self.assertEqual(signal.signal_type, MRSignalType.SHORT)
        
        # Verify SL Math
        # SL = Entry + (ATR * ConfigMult * ParamMult)
        # 103 + (2.0 * 2.0 * 1.0) = 103 + 4 = 107
        expected_sl = Decimal("107.0")
        
        self.assertEqual(signal.stop_price, expected_sl, 
                         f"SL Calculation Wrong! Got {signal.stop_price}, Expected {expected_sl}")
        
        self.assertGreater(signal.stop_price, signal.entry_price,
                           "SHORT SL must be GREATER than Entry Price")

if __name__ == '__main__':
    unittest.main()
