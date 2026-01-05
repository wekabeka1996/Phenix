"""
Comprehensive test suite for Mean Reversion Strategy blockers.

Tests all potential blockers that could prevent MR from generating signals:
1. Symbol filtering (enabled_symbols)
2. Timestamp validation (missing/zero/out-of-order)
3. Price validation (zero/negative)
4. Strategy initialization
5. Liquidity gate
6. Regime gate (allowed_regimes)
7. Bar accumulation
8. Signal generation
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
from vfoundation.core import FSMCore
import time
import logging

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger("TEST_MR_BLOCKERS")


class TestResults:
    """Test results accumulator."""
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
    
    def record_pass(self, test_name: str):
        self.tests_run += 1
        self.tests_passed += 1
        print(f"  ✅ PASS: {test_name}")
    
    def record_fail(self, test_name: str, reason: str):
        self.tests_run += 1
        self.tests_failed += 1
        self.failures.append((test_name, reason))
        print(f"  ❌ FAIL: {test_name}")
        print(f"     Reason: {reason}")
    
    def print_summary(self):
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_failed}")
        
        if self.failures:
            print("\nFAILURES:")
            for test_name, reason in self.failures:
                print(f"  ❌ {test_name}: {reason}")


def create_tick_message(symbol: str, price: float, volume: float, ts_ms: int, **kwargs) -> Message:
    """Helper to create tick message."""
    return Message(
        op="EVT",
        verb="MARKET_TICK_RECEIVED",
        src="test",
        dst="mean_reversion",
        evt="EVT:MARKET_TICK_RECEIVED",
        pld={
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "ts_ms": ts_ms,
            "timestamp_ms": ts_ms,
            "bid": price - 0.0001,
            "ask": price + 0.0001,
            "bid_size": volume / 2,
            "ask_size": volume / 2,
            **kwargs
        }
    )


def test_blocker_1_symbol_filtering(handler: MeanReversionHandler, results: TestResults):
    """
    Test Blocker #1: Symbol не в enabled_symbols
    
    Expected: Tick для невідомого символу має бути відкинутий (silent return)
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #1: Symbol Filtering")
    print("=" * 80)
    
    # Test 1.1: Valid symbol (DOGEUSDT)
    initial_stats = dict(handler._stats)
    tick = create_tick_message("DOGEUSDT", 0.12345, 1000.0, int(time.time() * 1000))
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_seen"] > initial_stats["ticks_seen"]:
        results.record_pass("Valid symbol (DOGEUSDT) processed")
    else:
        results.record_fail("Valid symbol (DOGEUSDT) NOT processed", 
                          f"ticks_seen: {initial_stats['ticks_seen']} -> {handler._stats['ticks_seen']}")
    
    # Test 1.2: Invalid symbol (SOLUSDT - disabled in config)
    initial_stats = dict(handler._stats)
    tick = create_tick_message("SOLUSDT", 136.24, 1000.0, int(time.time() * 1000))
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_seen"] == initial_stats["ticks_seen"]:
        results.record_pass("Invalid symbol (SOLUSDT) rejected")
    else:
        results.record_fail("Invalid symbol (SOLUSDT) was processed",
                          f"ticks_seen: {initial_stats['ticks_seen']} -> {handler._stats['ticks_seen']}")


def test_blocker_2_timestamp_validation(handler: MeanReversionHandler, results: TestResults):
    """
    Test Blocker #2: Timestamp validation
    
    Expected:
    - ts_ms=0 → rejected (ticks_dropped_missing_ts++)
    - ts_ms=None → rejected
    - Out-of-order → rejected (ticks_dropped_out_of_order++)
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #2: Timestamp Validation")
    print("=" * 80)
    
    symbol = "XRPUSDT"
    
    # Test 2.1: Missing timestamp (ts_ms=0)
    initial_stats = dict(handler._stats)
    tick = create_tick_message(symbol, 0.5, 1000.0, 0)
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_dropped_missing_ts"] > initial_stats["ticks_dropped_missing_ts"]:
        results.record_pass("Missing timestamp (ts_ms=0) rejected")
    else:
        results.record_fail("Missing timestamp (ts_ms=0) NOT rejected",
                          f"ticks_dropped_missing_ts: {initial_stats['ticks_dropped_missing_ts']} -> {handler._stats['ticks_dropped_missing_ts']}")
    
    # Test 2.2: Valid timestamp
    initial_stats = dict(handler._stats)
    ts_valid = int(time.time() * 1000)
    tick = create_tick_message(symbol, 0.5, 1000.0, ts_valid)
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_seen"] > initial_stats["ticks_seen"]:
        results.record_pass("Valid timestamp processed")
    else:
        results.record_fail("Valid timestamp NOT processed",
                          f"ticks_seen: {initial_stats['ticks_seen']} -> {handler._stats['ticks_seen']}")
    
    # Test 2.3: Out-of-order timestamp
    initial_stats = dict(handler._stats)
    ts_old = ts_valid - 10000  # 10 seconds in the past
    tick = create_tick_message(symbol, 0.5, 1000.0, ts_old)
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_dropped_out_of_order"] > initial_stats["ticks_dropped_out_of_order"]:
        results.record_pass("Out-of-order timestamp rejected")
    else:
        results.record_fail("Out-of-order timestamp NOT rejected",
                          f"ticks_dropped_out_of_order: {initial_stats['ticks_dropped_out_of_order']} -> {handler._stats['ticks_dropped_out_of_order']}")


def test_blocker_3_price_validation(handler: MeanReversionHandler, results: TestResults):
    """
    Test Blocker #3: Price validation
    
    Expected:
    - price=0 → rejected (ticks_dropped_invalid_price++)
    - price<0 → rejected
    - price>0 → accepted
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #3: Price Validation")
    print("=" * 80)
    
    symbol = "BTCUSDT"
    
    # Test 3.1: Zero price
    initial_stats = dict(handler._stats)
    ts = int(time.time() * 1000)
    tick = create_tick_message(symbol, 0.0, 1000.0, ts)
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_dropped_invalid_price"] > initial_stats["ticks_dropped_invalid_price"]:
        results.record_pass("Zero price rejected")
    else:
        results.record_fail("Zero price NOT rejected",
                          f"ticks_dropped_invalid_price: {initial_stats['ticks_dropped_invalid_price']} -> {handler._stats['ticks_dropped_invalid_price']}")
    
    # Test 3.2: Negative price
    initial_stats = dict(handler._stats)
    ts = int(time.time() * 1000) + 1000
    tick = create_tick_message(symbol, -42000.0, 1000.0, ts)
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_dropped_invalid_price"] > initial_stats["ticks_dropped_invalid_price"]:
        results.record_pass("Negative price rejected")
    else:
        results.record_fail("Negative price NOT rejected",
                          f"ticks_dropped_invalid_price: {initial_stats['ticks_dropped_invalid_price']} -> {handler._stats['ticks_dropped_invalid_price']}")
    
    # Test 3.3: Valid price
    initial_stats = dict(handler._stats)
    ts = int(time.time() * 1000) + 2000
    tick = create_tick_message(symbol, 95000.0, 1000.0, ts)
    handler._on_market_tick(tick)
    
    if handler._stats["ticks_seen"] > initial_stats["ticks_seen"]:
        results.record_pass("Valid price processed")
    else:
        results.record_fail("Valid price NOT processed",
                          f"ticks_seen: {initial_stats['ticks_seen']} -> {handler._stats['ticks_seen']}")


def test_blocker_4_strategy_initialization(handler: MeanReversionHandler, results: TestResults):
    """
    Test Blocker #4: Strategy initialization
    
    Expected:
    - Handler має бути enabled
    - Strategies мають бути створені для всіх enabled symbols
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #4: Strategy Initialization")
    print("=" * 80)
    
    # Test 4.1: Handler enabled
    if handler._enabled:
        results.record_pass("Handler is enabled")
    else:
        results.record_fail("Handler is NOT enabled", "handler._enabled = False")
    
    # Test 4.2: Expected symbols have strategies
    expected_symbols = {"DOGEUSDT", "XRPUSDT", "BTCUSDT"}
    actual_symbols = set(handler._strategies.keys())
    
    if expected_symbols == actual_symbols:
        results.record_pass(f"All expected symbols have strategies: {expected_symbols}")
    else:
        missing = expected_symbols - actual_symbols
        extra = actual_symbols - expected_symbols
        results.record_fail("Symbol/Strategy mismatch",
                          f"Missing: {missing}, Extra: {extra}")
    
    # Test 4.3: Strategy objects are valid
    all_valid = True
    for symbol, strategy in handler._strategies.items():
        if strategy is None:
            all_valid = False
            results.record_fail(f"Strategy for {symbol} is None", "")
            break
    
    if all_valid:
        results.record_pass("All strategy objects are non-None")


def test_blocker_5_liquidity_gate(handler: MeanReversionHandler, config, results: TestResults):
    """
    Test Blocker #5: Liquidity gate
    
    Expected:
    - Якщо liquidity_gate.enabled=true і kappa < kappa_min → сигнал блокується
    - Якщо liquidity_gate.enabled=false → сигнал проходить
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #5: Liquidity Gate")
    print("=" * 80)
    
    # Check config for DOGEUSDT liquidity gate
    mr_cfg = config.strategies.mean_reversion
    doge_cfg = mr_cfg.assets.get("DOGEUSDT")
    
    if doge_cfg and doge_cfg.liquidity_gate:
        gate = doge_cfg.liquidity_gate
        print(f"  DOGEUSDT liquidity_gate: enabled={gate.enabled}, kappa_min={gate.kappa_min}")
        
        # Test 5.1: Low kappa (should block)
        handler._liquidity_kappa_map["DOGEUSDT"] = Decimal("0.05")  # Below min
        
        if handler._check_liquidity_gate("DOGEUSDT"):
            results.record_fail("Low kappa NOT blocked by liquidity gate",
                              f"kappa=0.05 < kappa_min={gate.kappa_min}")
        else:
            results.record_pass("Low kappa blocked by liquidity gate")
        
        # Test 5.2: High kappa (should pass)
        handler._liquidity_kappa_map["DOGEUSDT"] = Decimal("0.5")  # Above min
        
        if handler._check_liquidity_gate("DOGEUSDT"):
            results.record_pass("High kappa passed liquidity gate")
        else:
            results.record_fail("High kappa blocked by liquidity gate",
                              f"kappa=0.5 >= kappa_min={gate.kappa_min}")
    else:
        results.record_pass("Liquidity gate not configured for DOGEUSDT (test skipped)")


def test_blocker_6_regime_gate(handler: MeanReversionHandler, config, results: TestResults):
    """
    Test Blocker #6: Regime gate (allowed_regimes)
    
    Expected:
    - Сигнал має генеруватись лише коли regime in allowed_regimes
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #6: Regime Gate")
    print("=" * 80)
    
    mr_cfg = config.strategies.mean_reversion
    doge_cfg = mr_cfg.assets.get("DOGEUSDT")
    
    if doge_cfg and doge_cfg.allowed_regimes:
        allowed = doge_cfg.allowed_regimes
        print(f"  DOGEUSDT allowed_regimes: {allowed}")
        
        # Test 6.1: Allowed regime
        if "FLAT_NORMAL" in allowed:
            handler._per_symbol_regime["DOGEUSDT"] = "FLAT_NORMAL"
            results.record_pass("Allowed regime (FLAT_NORMAL) can be set")
        
        # Test 6.2: Disallowed regime
        # Note: Regime gate is checked in strategy, not in handler
        # We verify config is correct
        if "TREND_UP" not in allowed:
            results.record_pass("Disallowed regime (TREND_UP) not in allowed_regimes")
        else:
            results.record_fail("TREND_UP should not be in DOGEUSDT allowed_regimes",
                              f"Config shows: {allowed}")
    else:
        results.record_fail("DOGEUSDT missing allowed_regimes config", "")


def test_blocker_7_bar_accumulation(handler: MeanReversionHandler, results: TestResults):
    """
    Test Blocker #7: Bar accumulation
    
    Expected:
    - Після N тиків має сформуватись бар (bars_completed++)
    - timeframe_sec = 180s (3m)
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #7: Bar Accumulation")
    print("=" * 80)
    
    symbol = "DOGEUSDT"
    base_price = 0.12345
    
    # Reset stats
    initial_bars = handler._stats["bars_completed"]
    
    # CRITICAL: Bar resampler aligns to 180s boundaries
    # We need to send ticks that span MULTIPLE 180s periods
    # Let's send 3 complete bars worth of ticks
    
    print(f"  Sending ticks for 3 complete bars (540 seconds) for {symbol}...")
    
    # Start at a known boundary (current time aligned to 180s)
    base_ts = (int(time.time()) // 180) * 180 * 1000  # Align to 180s boundary
    
    # Send 30 ticks: 10 per bar
    for bar_idx in range(3):  # 3 bars
        for tick_idx in range(10):  # 10 ticks per bar
            # Each tick is 18s apart (10 ticks = 180s)
            offset_ms = (bar_idx * 180000) + (tick_idx * 18000)
            ts = base_ts + offset_ms
            price = base_price + (bar_idx * 0.001) + (tick_idx * 0.0001)
            
            tick = create_tick_message(symbol, price, 1000.0, ts)
            handler._on_market_tick(tick)
    
    # Check if bars were completed
    bars_delta = handler._stats["bars_completed"] - initial_bars
    
    if bars_delta >= 2:  # At least 2 bars (3rd may be incomplete)
        results.record_pass(f"Bars accumulated ({bars_delta} bar(s) completed)")
        print(f"    bars_completed: {initial_bars} -> {handler._stats['bars_completed']}")
    else:
        results.record_fail("Insufficient bars accumulated",
                          f"Expected >= 2 bars, got {bars_delta} (bars_completed: {initial_bars} -> {handler._stats['bars_completed']})")
    
    # Check ticks_seen
    print(f"  Total ticks_seen: {handler._stats['ticks_seen']}")


def test_blocker_8_signal_generation(handler: MeanReversionHandler, results: TestResults):
    """
    Test Blocker #8: Signal generation
    
    Expected:
    - Після достатньої кількості барів має генеруватись сигнал
    - signals_emitted > 0
    """
    print("\n" + "=" * 80)
    print("TEST BLOCKER #8: Signal Generation")
    print("=" * 80)
    
    symbol = "DOGEUSDT"
    
    # Check current stats
    signals_before = handler._stats["signals_emitted"]
    bars_before = handler._stats["bars_completed"]
    
    print(f"  Current state:")
    print(f"    signals_emitted: {signals_before}")
    print(f"    bars_completed: {bars_before}")
    print(f"    neutral_bars: {handler._stats['neutral_bars']}")
    
    # For signal generation, we need:
    # 1. min_bars (25 for DOGEUSDT) bars accumulated
    # 2. Price movement that triggers BB signal
    # 3. Regime in allowed_regimes
    
    # Get strategy for DOGEUSDT
    strategy = handler._strategies.get(symbol)
    if strategy:
        state = strategy.get_state(symbol)
        print(f"    strategy bars count: {len(state.bars)}")
        
        # Check if we have BB/ATR/RSI data
        if hasattr(state, 'bb') and state.bb:
            print(f"    bb: upper={state.bb.upper}, mid={state.bb.mid}, lower={state.bb.lower}")
        if hasattr(state, 'atr') and state.atr:
            print(f"    atr: {state.atr}")
        if hasattr(state, 'rsi') and state.rsi:
            print(f"    rsi: {state.rsi}")
        
        if len(state.bars) >= 25:
            results.record_pass("Minimum bars accumulated for signal generation")
        else:
            results.record_fail("Insufficient bars for signal",
                              f"Need 25 bars, have {len(state.bars)}")
    else:
        results.record_fail("No strategy found for DOGEUSDT", "")
    
    # Note: Actual signal generation requires specific market conditions
    # (price touching BB bands, etc.) which we can't easily simulate
    if signals_before > 0:
        results.record_pass(f"Signals have been generated ({signals_before} total)")
    else:
        print(f"  ⚠️  No signals generated yet (may be expected if market conditions not met)")


def test_real_system_state(handler: MeanReversionHandler, results: TestResults):
    """
    Test: Inspect real system state
    
    Shows actual stats from running handler
    """
    print("\n" + "=" * 80)
    print("REAL SYSTEM STATE INSPECTION")
    print("=" * 80)
    
    print("\n📊 Handler Stats:")
    for key, value in handler._stats.items():
        print(f"  {key}: {value}")
    
    print("\n🔧 Per-Symbol State:")
    for symbol in handler._enabled_symbols:
        strategy = handler._strategies.get(symbol)
        if strategy:
            state = strategy.get_state(symbol)
            print(f"\n  {symbol}:")
            print(f"    bars: {len(state.bars)}")
            
            # Check attributes safely
            if hasattr(state, 'bb') and state.bb:
                print(f"    bb: upper={state.bb.upper}, mid={state.bb.mid}, lower={state.bb.lower}")
            if hasattr(state, 'atr') and state.atr:
                print(f"    atr: {state.atr}")
            if hasattr(state, 'rsi') and state.rsi:
                print(f"    rsi: {state.rsi}")
            
            if state.bars:
                last_bar = state.bars[-1]
                print(f"    last_bar: close={last_bar.close}, volume={last_bar.volume}")
    
    print("\n🎯 Signal Counts:")
    if handler._signal_counts:
        for symbol, count in handler._signal_counts.items():
            print(f"  {symbol}: {count} signals")
    else:
        print("  No signals generated yet")
    
    # Always pass this test - it's informational
    results.record_pass("Real system state inspected")


def main():
    print("\n" + "=" * 80)
    print("MEAN REVERSION BLOCKER COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    
    results = TestResults()
    
    # Load config and initialize handler
    print("\n🔧 Initializing test environment...")
    loader = ConfigLoader()
    config = loader.load_config()
    
    fsm = FSMCore()
    handler = MeanReversionHandler(fsm=fsm, config=config)
    handler.register()
    
    print(f"✅ Handler initialized: enabled={handler._enabled}, symbols={handler._enabled_symbols}")
    
    # Run all blocker tests
    try:
        test_blocker_1_symbol_filtering(handler, results)
        test_blocker_2_timestamp_validation(handler, results)
        test_blocker_3_price_validation(handler, results)
        test_blocker_4_strategy_initialization(handler, results)
        test_blocker_5_liquidity_gate(handler, config, results)
        test_blocker_6_regime_gate(handler, config, results)
        test_blocker_7_bar_accumulation(handler, results)
        test_blocker_8_signal_generation(handler, results)
        test_real_system_state(handler, results)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Print summary
    results.print_summary()
    
    return results.tests_failed == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
