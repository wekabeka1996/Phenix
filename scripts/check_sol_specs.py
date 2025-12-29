"""Check SOLUSDT specs from Binance testnet."""
import asyncio
import httpx


async def get_sol_info():
    async with httpx.AsyncClient() as client:
        r = await client.get('https://testnet.binancefuture.com/fapi/v1/exchangeInfo')
        data = r.json()
        for s in data['symbols']:
            if s['symbol'] == 'SOLUSDT':
                print(f"Symbol: {s['symbol']}")
                print(f"quantityPrecision: {s['quantityPrecision']}")
                print(f"pricePrecision: {s['pricePrecision']}")
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        print(f"LOT_SIZE: stepSize={f['stepSize']}, minQty={f['minQty']}")
                    if f['filterType'] == 'PRICE_FILTER':
                        print(f"PRICE_FILTER: tickSize={f['tickSize']}")
                break


if __name__ == "__main__":
    asyncio.run(get_sol_info())
