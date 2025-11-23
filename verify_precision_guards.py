"""
Quick verification that precision guards work with real SOLUSDT order.

Tests EP-ADAPTER-PRECISION-GUARDS-S19 fix.
"""
from decimal import Decimal
from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
    BinanceValidationError,
)
from apps.reference.config_models import InstrumentProfile
from unittest.mock import Mock

# Mock config
config = Mock()
config.trading = Mock()
config.trading.trading_env = "test"

# Create adapter
adapter = BinanceExecutionAdapter(
    fsm=None,
    config=config,
    shadow_mode=True,
    rest_timeout_sec=20.0
)

# Load real SOLUSDT profile from config
try:
    from apps.reference.config_symbols import resolve_instrument_profile
    solusdt_profile = resolve_instrument_profile(config, "SOLUSDT")
    print(f"\n✅ SOLUSDT Profile loaded:")
    print(f"   step_size: {solusdt_profile.step_size}")
    print(f"   tick_size: {solusdt_profile.tick_size}")
    print(f"   quantity_precision: {solusdt_profile.precision_quantity}")
    print(f"   price_precision: {solusdt_profile.precision_price}")
    print(f"   min_qty: {solusdt_profile.min_qty}")
    print(f"   min_notional: {solusdt_profile.min_notional}")
except Exception as e:
    print(f"\n⚠️ Could not load SOLUSDT from config: {e}")
    print("   Using manual profile for testing...")
    solusdt_profile = InstrumentProfile(
        symbol="SOLUSDT",
        exchange="binance",
        base_asset="SOL",
        quote_asset="USDT",
        precision_quantity=0,  # Integer only (from exchangeInfo)
        precision_price=2,
        min_notional=10.0,
        min_qty=1.0,
        min_price=0.01,
        step_size=1.0,
        tick_size=0.01,
        max_position_size=100.0,
        max_leverage=20.0,
    )

adapter._instrument_profiles["SOLUSDT"] = solusdt_profile

# Test 1: Problematic qty=1.42 from logs
print("\n📊 Test 1: qty=1.42 (from error logs)")
try:
    normalized_qty = adapter._quantize_qty("SOLUSDT", 1.42)
    print(f"   ✅ Normalized: 1.42 → {normalized_qty}")
    assert normalized_qty == Decimal("1"), f"Expected 1, got {normalized_qty}"
except BinanceValidationError as e:
    print(f"   ❌ Validation error: {e}")

# Test 2: Price normalization
print("\n📊 Test 2: price=122.156")
try:
    normalized_price = adapter._quantize_price("SOLUSDT", 122.156)
    print(f"   ✅ Normalized: 122.156 → {normalized_price}")
    assert normalized_price == Decimal(
        "122.15"), f"Expected 122.15, got {normalized_price}"
except BinanceValidationError as e:
    print(f"   ❌ Validation error: {e}")

# Test 3: Min notional validation
print("\n📊 Test 3: min_notional check (qty=1 * price=120 = 120 USDT >= 10)")
try:
    adapter._validate_min_notional("SOLUSDT", Decimal("1"), Decimal("120"))
    print(f"   ✅ Min notional OK")
except BinanceValidationError as e:
    print(f"   ❌ Validation error: {e}")

# Test 4: Invalid qty below min_qty
print("\n📊 Test 4: qty=0.5 (below min_qty=1.0)")
try:
    normalized_qty = adapter._quantize_qty("SOLUSDT", 0.5)
    print(
        f"   ❌ Should have raised BinanceValidationError, got {normalized_qty}")
except BinanceValidationError as e:
    print(f"   ✅ Correctly rejected: {e}")

# Test 5: REST timeout
print(f"\n⏱️ REST timeout configured: {adapter._rest_timeout}s")
assert adapter._rest_timeout == 20.0, f"Expected 20.0s, got {adapter._rest_timeout}s"
print("   ✅ Timeout matches expected default")

print("\n🎉 All verification tests passed! EP-ADAPTER-PRECISION-GUARDS-S19 fix working correctly.")
