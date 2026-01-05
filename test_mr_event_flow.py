"""
Тест для перевірки чому MR handler не обробляє події.

Перевіряє:
1. Чи зареєстровано listener
2. Чи є події для MR symbols
3. Чи проходять події через handler
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig
import logging

logging.basicConfig(level=logging.DEBUG)

def test_mr_config():
    """Перевірка конфігурації MR."""
    print("=" * 80)
    print("TEST 1: MR Configuration")
    print("=" * 80)
    
    loader = ConfigLoader()
    config = loader.load_config()  # Вже повертає AuroraConfig
    
    print(f"\n1. Strategies Registry:")
    if hasattr(config, 'strategies_registry') and config.strategies_registry:
        assignments = config.strategies_registry.assignments
        print(f"   Assignments: {assignments}")
        
        mr_symbols = []
        for symbol, strategies in assignments.items():
            if "mean_reversion" in strategies:
                mr_symbols.append(symbol)
        print(f"   MR Assigned Symbols: {mr_symbols}")
    else:
        print("   ❌ No strategies_registry found")
    
    print(f"\n2. MR Strategy Config:")
    if hasattr(config.strategies, 'mean_reversion'):
        mr_cfg = config.strategies.mean_reversion
        print(f"   Enabled: {mr_cfg.enabled}")
        print(f"   Timeframe: {mr_cfg.timeframe_sec}s")
        print(f"   Emit Direct: {mr_cfg.emit_trade_intent_directly}")
        print(f"   Assets:")
        for symbol, asset_cfg in mr_cfg.assets.items():
            print(f"     - {symbol}: enabled={asset_cfg.enabled}, position_mode={asset_cfg.position_mode}")
    else:
        print("   ❌ No mean_reversion config found")
    
    print(f"\n3. Check for Hybrid Symbols (multi-strategy):")
    if hasattr(config, 'strategies_registry') and config.strategies_registry:
        for symbol, strategies in config.strategies_registry.assignments.items():
            if len(strategies) > 1:
                print(f"   HYBRID: {symbol} → {strategies}")
    
    return config


def test_mr_handler_init(config):
    """Перевірка ініціалізації MR handler."""
    print("\n" + "=" * 80)
    print("TEST 2: MR Handler Initialization")
    print("=" * 80)
    
    from vfoundation.core import FSMCore
    from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
    
    fsm = FSMCore()
    
    try:
        handler = MeanReversionHandler(fsm=fsm, config=config)
        print(f"✅ Handler created successfully")
        print(f"   Enabled: {handler._enabled}")
        print(f"   Enabled Symbols: {handler._enabled_symbols}")
        print(f"   Strategies: {list(handler._strategies.keys())}")
        
        # Перевірка чи є strategies для символів
        if not handler._strategies:
            print(f"\n⚠️  WARNING: No strategies initialized!")
            print(f"   This means MR will NOT process any ticks")
        
        return handler
    except Exception as e:
        print(f"❌ Handler creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_event_registration(handler):
    """Перевірка реєстрації listeners."""
    print("\n" + "=" * 80)
    print("TEST 3: Event Listener Registration")
    print("=" * 80)
    
    if handler is None:
        print("❌ Handler is None, skipping")
        return
    
    if not handler._enabled:
        print("❌ Handler is disabled, skipping registration")
        return
    
    # Register listeners
    handler.register()
    print(f"   ✅ Listeners registered (check logs above)")


def test_tick_processing(handler, config):
    """Симуляція обробки tick події."""
    print("\n" + "=" * 80)
    print("TEST 4: Tick Processing Simulation")
    print("=" * 80)
    
    if handler is None or not handler._enabled:
        print("❌ Handler disabled, skipping")
        return
    
    # Симуляція tick події
    from vfoundation.core.protocol import Message
    import time
    
    test_symbol = "DOGEUSDT"
    
    tick_msg = Message(
        evt="EVT:MARKET_TICK_RECEIVED",
        pld={
            "symbol": test_symbol,
            "price": 0.12345,
            "volume": 1000.0,
            "ts": int(time.time()),
            "ts_ms": int(time.time() * 1000),
            "bid": 0.12340,
            "ask": 0.12350,
            "bid_size": 5000,
            "ask_size": 4000,
        }
    )
    
    print(f"\n   Sending test tick for {test_symbol}...")
    try:
        handler._on_market_tick(tick_msg)
        print(f"   ✅ Tick processed (check logs above)")
    except Exception as e:
        print(f"   ❌ Tick processing failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("MEAN REVERSION EVENT FLOW DIAGNOSTIC")
    print("=" * 80)
    
    # Test 1: Config
    config = test_mr_config()
    
    # Test 2: Handler init
    handler = test_mr_handler_init(config)
    
    # Test 3: Event registration
    test_event_registration(handler)
    
    # Test 4: Tick processing
    test_tick_processing(handler, config)
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)
