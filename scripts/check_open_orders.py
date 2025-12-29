"""Check open orders on Binance testnet."""
import asyncio
import httpx
import os
import time
import hmac
import hashlib
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('BINANCE_TESTNET_API_KEY')
API_SECRET = os.getenv('BINANCE_TESTNET_API_SECRET')


async def get_open_orders():
    timestamp = int(time.time() * 1000)
    params = {'timestamp': timestamp}
    query = urlencode(params)
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = signature

    async with httpx.AsyncClient() as client:
        # Open orders
        r = await client.get(
            'https://testnet.binancefuture.com/fapi/v1/openOrders',
            params=params,
            headers={'X-MBX-APIKEY': API_KEY}
        )
        orders = r.json()
        print(f"Open orders: {len(orders)}")
        for o in orders:
            print(f"  {o['symbol']} {o['orderId']} {o['type']} {o['side']} stop={o.get('stopPrice')} closePos={o.get('closePosition')}")

        # All orders for SOLUSDT (recent)
        params2 = {'timestamp': int(time.time() * 1000), 'symbol': 'SOLUSDT', 'limit': 20}
        query2 = urlencode(params2)
        sig2 = hmac.new(API_SECRET.encode(), query2.encode(), hashlib.sha256).hexdigest()
        params2['signature'] = sig2

        r2 = await client.get(
            'https://testnet.binancefuture.com/fapi/v1/allOrders',
            params=params2,
            headers={'X-MBX-APIKEY': API_KEY}
        )
        all_orders = r2.json()
        print(f"\nRecent SOLUSDT orders: {len(all_orders)}")
        for o in all_orders[-10:]:
            print(f"  {o['orderId']} {o['type']} {o['side']} status={o['status']} stop={o.get('stopPrice')} closePos={o.get('closePosition')}")


if __name__ == "__main__":
    asyncio.run(get_open_orders())
