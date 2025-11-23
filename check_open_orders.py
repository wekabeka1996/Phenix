#!/usr/bin/env python3
"""Quick script to check open orders on Binance Testnet."""

import asyncio
import os
from dotenv import load_dotenv
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter

load_dotenv()


async def main():
    adapter = BinanceExecutionAdapter({
        'api_key': os.getenv('BINANCE_API_KEY'),
        'api_secret': os.getenv('BINANCE_API_SECRET'),
        'testnet': True
    })

    symbols = ['SOLUSDT', 'ETHUSDT', 'BTCUSDT']

    for symbol in symbols:
        try:
            orders = await adapter.get_open_orders(symbol)
            print(f"\n{'='*60}")
            print(f"Symbol: {symbol}")
            print(f"Open Orders: {len(orders) if orders else 0}")
            if orders:
                for order in orders:
                    print(f"  - OrderID: {order.get('orderId')}, Side: {order.get('side')}, "
                          f"Price: {order.get('price')}, Qty: {order.get('origQty')}, "
                          f"Type: {order.get('type')}, Status: {order.get('status')}")
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")

    # Also check positions
    print(f"\n{'='*60}")
    print("Current Positions:")
    try:
        positions = await adapter.get_open_positions()
        if positions:
            for pos in positions:
                if float(pos.get('positionAmt', 0)) != 0:
                    print(
                        f"  - {pos.get('symbol')}: {pos.get('positionAmt')} @ {pos.get('entryPrice')}")
        else:
            print("  No open positions")
    except Exception as e:
        print(f"Error fetching positions: {e}")

if __name__ == "__main__":
    asyncio.run(main())
