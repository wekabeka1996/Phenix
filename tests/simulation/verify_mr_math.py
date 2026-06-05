
# tests/simulation/verify_mr_math.py
import sys
import os
import logging
from decimal import Decimal
import logging

# Add project root
sys.path.append(os.getcwd())

# Import strategy and config
# Note: config_models.py does NOT seem to export MRStrategyConfig, 
# it is defined in mean_reversion_strategy.py
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy, 
    MRStrategyConfig,
    MRSymbolState
)

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("MathAudit")

def check_indicators(state: MRSymbolState):
    """Deep inspection of internal indicator state."""
    if not state.bars:
        return

    # Check Bollinger Bands
    if state.bb:
        bb = state.bb
        # 1. Non-negative checks (Price implies these should be positive)
        if bb.upper < 0 or bb.lower < 0 or bb.mid < 0:
             logger.error(f"❌ FATAL: Negative BB values detected! U:{bb.upper} L:{bb.lower} M:{bb.mid}")
        
        # 2. Logic checks
        if bb.upper < bb.lower:
             logger.error(f"❌ FATAL: BB Upper < Lower! U:{bb.upper} L:{bb.lower}")
             
        if bb.width < 0:
             logger.error(f"❌ FATAL: Negative BB Width! {bb.width}")
             
        if bb.width == 0.0 and len(state.bars) > 20: 
             # Warning only, could happen in absolute flat line, but strictly 0.0 float is rare
             logger.warning(f"⚠️ Warning: Zero BB Width (Price flatline? or error?)")

    # Check ATR
    if state.atr is not None:
        if state.atr < 0:
             logger.error(f"❌ FATAL: Negative ATR! {state.atr}")
        if state.atr == 0:
             logger.warning(f"⚠️ ATR is Zero (Flatline or error?)")

    # Check RSI
    if state.rsi is not None:
        if state.rsi < 0 or state.rsi > 100:
             logger.error(f"❌ FATAL: RSI out of bounds (0-100)! {state.rsi}")


def run_math_check():
    logger.info("🧪 STARTING MR MATH AUDIT...")
    
    # 1. Init Strategy
    config = MRStrategyConfig(
        min_bars=5, # Fast start for test (default is 25)
        bb_window=20,
        bb_num_std=2.0
    )
    # Pass empty dict for regime_sizing, testing defaults
    strategy = MeanReversion1mStrategy(config, timeframe_sec=1) 
    
    # Force regime to NORMAL so logic actually runs once we have bars
    # "FLAT_NORMAL" maps to suitable
    # Real regime mapping expects "MEAN_REVERSION" + atr_pct or similar
    # But strategy.on_tick calls map_to_flat_regime internally.
    # To test Math, we need it to NOT skip early.
    
    # Note on Strategy Flow:
    # on_tick -> get_regime -> map_to_flat_regime
    # We must set external regime to something valid like "MEAN_REVERSION"
    # AND ensure ATR is calculated so _atr_pct is populated.
    
    symbol = "DOGE_TEST"
    strategy.set_regime(symbol, "MEAN_REVERSION") # Needs ATR to resolve to FLAT_x

    # 2. Mock Data Generator (Simulating Price Action)
    # We generate a sine wave to force BB expansion/contraction
    import math
    base_price = 100.0
    
    logger.info("🔄 Feeding 200 ticks (1 tick/sec = 200 bars since we set timeframe_sec=1)...")
    
    # Wait, strategy defaults timeframe_sec=60. I set it to 1s.
    # So every tick with distinct timestamp > 1000ms diff will create a bar.
    
    start_ts = 1700000000000
    
    for i in range(200): 
        ts = start_ts + (i * 1000) # 1 sec increments
        
        # Price wave: Base + Sine Wave + Random Noise
        # Adding noise to ensure ATR isn't zero
        noise = (i % 3) * 0.1 
        price_val = base_price + math.sin(i/10.0) * 5 + noise
        price = Decimal(str(price_val))
        
        # Volume
        volume = Decimal("1.0")
        
        # Feed Tick
        # Note: on_tick returns Signal ONLY if bar completed AND regime valid AND ...
        signal = strategy.on_tick(symbol, price, volume, ts)
        
        # 3. Introspect State
        state = strategy.get_state(symbol)
        
        # Check Indicators every step
        check_indicators(state)
        
        if signal:
             logger.info(f"⚡ Signal Generated at step {i}: {signal.signal_type} {signal.why}")

    # 4. Crash Test: Division by Zero / Garbage
    logger.info("\n🧪 CRASH TEST: Feeding Garbage Data (Zeros)...")
    try:
        strategy.on_tick(symbol, Decimal("0"), Decimal("0"), start_ts + 200000)
        # 0 price might screw up % calculations (e.g. ATR%) or BB Width / mid
        check_indicators(strategy.get_state(symbol))
        logger.info("✅ Survived Zero Price Tick")
    except Exception as e:
        logger.error(f"❌ CRASH on Zero Price: {e}")
        import traceback
        traceback.print_exc()

    logger.info("\n✅ Math Simulation Finished.")

if __name__ == "__main__":
    run_math_check()
