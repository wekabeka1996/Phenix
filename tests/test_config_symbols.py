#!/usr/bin/env python3
"""Test config_symbols utility and system integration."""

from apps.reference.config_symbols import get_trading_symbols, get_first_symbol, get_symbol_config
from apps.reference.config_loader import get_config

print("=" * 60)
print("✅ Config Symbols Tests")
print("=" * 60)

# Test 1: get_trading_symbols()
symbols = get_trading_symbols()
print(f"\n1. get_trading_symbols():")
print(f"   Result: {symbols}")
assert isinstance(symbols, list), "Should return list"
assert len(symbols) > 0, "Should have symbols"
print(f"   ✅ Pass")

# Test 2: get_first_symbol()
first = get_first_symbol()
print(f"\n2. get_first_symbol():")
print(f"   Result: {first}")
assert isinstance(first, str), "Should return string"
assert first in symbols, "Should be in symbols list"
print(f"   ✅ Pass")

# Test 3: get_symbol_config()
for symbol in symbols:
    config = get_symbol_config(symbol)
    print(f"\n3. get_symbol_config('{symbol}'):")
    print(f"   Result: {config}")
    assert config is not None, f"Should have config for {symbol}"
    print(f"   ✅ Pass")

print("\n" + "=" * 60)
print("✅ AuroraConfig Tests")
print("=" * 60)

config = get_config()
# Access Pydantic object directly
instruments = config.trading.instruments if hasattr(
    config.trading, 'instruments') else {}
print(f"\n1. Instruments from config:")
print(f"   Result: {list(instruments.keys())}")
assert list(instruments.keys()) == symbols, "Should match config symbols"
print(f"   ✅ Pass")

print(f"\n2. Trading mode:")
mode = config.trading_mode  # Direct attribute access
print(f"   Result: {mode}")
assert mode is not None, "Should have trading_mode"
print(f"   ✅ Pass")

print("\n" + "=" * 60)
print("✅✅✅ ALL TESTS PASSED ✅✅✅")
print("=" * 60)
print("\nSystem is configuration-driven:")
print(f"  - Symbols: {symbols}")
print(f"  - Mode: {mode}")
print("\nTo change symbols: edit config/aurora/trading.yaml → instruments")
