#!/usr/bin/env python3
"""
Script to cancel all SL/TP bracket orders that are blocking new position openings.
"""
import asyncio
import logging
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vfoundation.adapters.binance_adapter import BinanceAdapter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

async def cancel_bracket_orders():
    """Cancel all SL/TP bracket orders."""

    # Load config - you'll need to set these environment variables or modify
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'

    if not api_key or not api_secret:
        LOG.error("Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")
        return

    base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"

    adapter = BinanceAdapter(api_key=api_key, api_secret=api_secret, base_url=base_url)

    try:
        # Get all open orders
        open_orders = await adapter.get_open_orders()
        LOG.info(f"Found {len(open_orders)} total open orders")

        # Filter for bracket orders (SL/TP)
        bracket_orders = []
        for order in open_orders:
            order_type = order.get('type', '')
            close_position = order.get('closePosition', False)
            reduce_only = order.get('reduceOnly', False)

            if (order_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET'] and
                (str(close_position).lower() == 'true' or str(reduce_only).lower() == 'true')):
                bracket_orders.append(order)

        LOG.info(f"Found {len(bracket_orders)} bracket orders to cancel")

        # Cancel each bracket order
        cancelled_count = 0
        for order in bracket_orders:
            symbol = order['symbol']
            order_id = order['orderId']
            try:
                result = await adapter.cancel_order(symbol, order_id)
                LOG.info(f"Cancelled bracket order: {symbol} {order_id}")
                cancelled_count += 1
            except Exception as e:
                LOG.error(f"Failed to cancel order {symbol} {order_id}: {e}")

        LOG.info(f"Successfully cancelled {cancelled_count} bracket orders")

    except Exception as e:
        LOG.error(f"Error during bracket order cleanup: {e}")
    finally:
        if adapter._session:
            await adapter._session.close()

if __name__ == "__main__":
    asyncio.run(cancel_bracket_orders())