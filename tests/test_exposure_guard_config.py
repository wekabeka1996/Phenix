#!/usr/bin/env python3
"""
Test script to verify exposure guard configuration allows TP/SL placement for all symbols.
"""

import asyncio
import yaml
from decimal import Decimal
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard


async def test_exposure_guard():
    """Test exposure guard with updated configuration."""

    # Load config
    with open('configs/master_config_v1.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Create exposure guard
    guard = ExposureGuard(config)

    # Mock portfolio state (simulate fresh data)
    portfolio_state = {
        "equity_free_usdt": "1000.0",  # $1000 equity
        "open_positions_margin_usd": "100.0",  # $100 current margin usage
        # Fresh timestamp
        "positions_last_ts_ms": int(asyncio.get_event_loop().time() * 1000),
        "positions_by_side": {
            "long_margin": "50.0",
            "short_margin": "50.0"
        }
    }

    # Test symbols
    symbols = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]
    notional_usd = Decimal("50.0")  # $50 position

    print("🧪 Testing Exposure Guard with updated configuration:")
    print(f"   Equity: ${portfolio_state['equity_free_usdt']}")
    print(
        f"   Current margin: ${portfolio_state['open_positions_margin_usd']}")
    print(f"   Max utilization: {guard.max_equity_utilization_pct * 100}%")
    print(f"   Stale TTL: {guard.positions_stale_ttl_sec}s")
    print()

    for symbol in symbols:
        result = guard.can_open(symbol, notional_usd, portfolio_state)
        status = "✅ ALLOWED" if result["allowed"] else "❌ BLOCKED"
        reason = result.get("reason", "OK")

        print(f"{status} {symbol}: {reason}")

        if not result["allowed"]:
            print(f"   Details: {result}")

    print("\n✅ Exposure guard test completed")

if __name__ == "__main__":
    asyncio.run(test_exposure_guard())
