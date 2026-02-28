#!/usr/bin/env python3
"""Перевірити openOrders на біржі."""
import asyncio
import json
from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.config_loader import get_config


async def main():
    cfg = get_config()
    adapter = BinanceAdapter(cfg, 'testnet')

    # Перевірити BTCUSDT
    orders = await adapter.get_open_orders('BTCUSDT')
    print("\n=== BTCUSDT openOrders ===")
    print(f"Total: {len(orders)}")
    for o in orders:
        print(f"  Type: {o.get('type')}, Status: {o.get('status')}, Qty: {o.get('origQty')}, Price: {o.get('price')}, ClientOrderId: {o.get('clientOrderId')}")

    # Перевірити всі позиції
    positions = await adapter.get_open_positions()
    print(f"\n=== open_positions ===")
    print(f"Total: {len(positions)}")
    for p in positions:
        print(f"  {p}")

if __name__ == '__main__':
    asyncio.run(main())
