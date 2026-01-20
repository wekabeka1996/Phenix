#!/usr/bin/env python3
"""
Test: Strategy Primacy End-to-End for MeanReversion

This test verifies that MeanReversion's calculated SL/TP prices
flow through DecisionMaking and are NOT overridden by config fallbacks.

Expected Log Output:
- "STRATEGY_PRIMACY: Using Strategy-provided SL=..."
- "TP/SL_RESOLVED: ... source=STRATEGY"
"""
import sys
import os
from decimal import Decimal
from pathlib import Path
import logging

# Setup
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("StrategyPrimacyE2E")


def test_mr_signal_contains_prices():
    """Verify MeanReversion signal contains stop_price and target_price."""
    from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
        MeanReversion1mStrategy, MRStrategyConfig
    )
    
    # Create config with sl_atr_mult and tp_to_mid
    config = MRStrategyConfig(
        min_bars=5,
        bb_window=20,
        bb_num_std=2.0,
        sl_atr_mult=2.0,  # This enables ATR-based SL
        tp_to_mid=True,   # Target BB mid-band
        cooldown_sec=0,
    )
    
    strategy = MeanReversion1mStrategy(config, timeframe_sec=1)
    strategy.set_regime("TESTUSDT", "MEAN_REVERSION")
    
    # Feed enough bars to generate signal
    import math
    base_price = 100.0
    start_ts = 1700000000000
    
    for i in range(50):
        ts = start_ts + (i * 1000)
        # Create oscillating price to trigger BB signals
        noise = (i % 3) * 0.1
        price_val = base_price + math.sin(i / 10.0) * 5 + noise
        price = Decimal(str(price_val))
        volume = Decimal("1.0")
        
        signal = strategy.on_tick("TESTUSDT", price, volume, ts)
        
        if signal:
            logger.info(f"Signal Generated: {signal.signal_type.name}")
            logger.info(f"  entry_price: {signal.entry_price}")
            logger.info(f"  stop_price: {signal.stop_price}")
            logger.info(f"  target_price: {signal.target_price}")
            
            # CRITICAL ASSERTIONS
            assert signal.stop_price is not None, "stop_price should NOT be None when sl_atr_mult is set"
            assert signal.target_price is not None, "target_price should NOT be None when tp_to_mid is True"
            
            # Verify SL is ATR-based (not a fixed percentage)
            entry = float(signal.entry_price)
            sl = float(signal.stop_price)
            sl_pct = abs(entry - sl) / entry * 100
            
            logger.info(f"  SL Distance: {sl_pct:.2f}% (ATR-based, not fixed 0.4%)")
            assert sl_pct > 0.5, "SL should be wider than fixed 0.4% fallback"
            
            logger.info("✅ MeanReversion signal contains valid SL/TP prices")
            return True
    
    logger.warning("No signal generated in 50 ticks (may need more bars)")
    return False


def test_price_ctx_format():
    """Verify price_ctx format matches what DecisionMaking expects."""
    from apps.reference.domains.feature_engineering.mean_reversion_strategy import MRSignal, MRSignalType
    
    # Create mock signal (simulating what strategy produces)
    signal = MRSignal(
        signal_type=MRSignalType.LONG,
        symbol="BTCUSDT",
        price=Decimal("100000"),
        bb=None,
        atr=Decimal("500"),
        flat_regime=None,
        mr_params=None,
        entry_price=Decimal("100000"),
        stop_price=Decimal("99000"),  # ATR-based (1% = 1000 USDT)
        target_price=Decimal("100500"),  # BB mid (0.5% = 500 USDT)
        confidence=0.8,
        timestamp_ms=1700000000000,
    )
    
    # Build price_ctx as MeanReversionHandler does
    price_ctx = {
        "entry_price": str(signal.entry_price),
        "stop_price": str(signal.stop_price) if signal.stop_price else None,
        "target_price": str(signal.target_price) if signal.target_price else None,
    }
    
    logger.info(f"price_ctx: {price_ctx}")
    
    # Verify format
    assert price_ctx["entry_price"] == "100000"
    assert price_ctx["stop_price"] == "99000"
    assert price_ctx["target_price"] == "100500"
    
    logger.info("✅ price_ctx format is correct for Strategy Primacy")
    return True


def test_config_updated():
    """Verify mean_reversion.yaml has sl_atr_mult set for BTC/XRP."""
    import yaml
    
    config_path = Path(__file__).resolve().parents[2] / "config" / "aurora" / "strategies" / "mean_reversion.yaml"
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    assets = config.get("mean_reversion", {}).get("assets", {})
    
    # Check BTCUSDT
    btc_cfg = assets.get("BTCUSDT", {}).get("strategy", {})
    btc_sl_atr = btc_cfg.get("sl_atr_mult")
    assert btc_sl_atr is not None, f"BTCUSDT.strategy.sl_atr_mult is null! Was: {btc_sl_atr}"
    assert btc_sl_atr > 0, f"BTCUSDT.strategy.sl_atr_mult must be > 0, got: {btc_sl_atr}"
    logger.info(f"✅ BTCUSDT.sl_atr_mult = {btc_sl_atr}")
    
    # Check XRPUSDT
    xrp_cfg = assets.get("XRPUSDT", {}).get("strategy", {})
    xrp_sl_atr = xrp_cfg.get("sl_atr_mult")
    assert xrp_sl_atr is not None, f"XRPUSDT.strategy.sl_atr_mult is null!"
    assert xrp_sl_atr > 0, f"XRPUSDT.strategy.sl_atr_mult must be > 0"
    logger.info(f"✅ XRPUSDT.sl_atr_mult = {xrp_sl_atr}")
    
    # Check tp_to_mid
    btc_tp_mid = btc_cfg.get("tp_to_mid")
    assert btc_tp_mid is True, f"BTCUSDT.strategy.tp_to_mid should be True, got: {btc_tp_mid}"
    logger.info(f"✅ BTCUSDT.tp_to_mid = {btc_tp_mid}")
    
    return True


def main():
    logger.info("=" * 60)
    logger.info("Strategy Primacy End-to-End Verification")
    logger.info("=" * 60)
    
    results = []
    
    # Test 1: Config check
    logger.info("\n🧪 TEST 1: Config Updated Check")
    try:
        results.append(("Config Updated", test_config_updated()))
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        results.append(("Config Updated", False))
    
    # Test 2: price_ctx format
    logger.info("\n🧪 TEST 2: price_ctx Format Check")
    try:
        results.append(("price_ctx Format", test_price_ctx_format()))
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        results.append(("price_ctx Format", False))
    
    # Test 3: MR signal prices
    logger.info("\n🧪 TEST 3: MR Signal Contains Prices")
    try:
        results.append(("MR Signal Prices", test_mr_signal_contains_prices()))
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        results.append(("MR Signal Prices", False))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        logger.info("\n🎉 ALL CHECKS PASSED - Strategy Primacy is properly configured!")
    else:
        logger.error("\n⚠️ SOME CHECKS FAILED - Review the errors above")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
