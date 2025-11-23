
import os
import asyncio
import logging
import yaml
import time
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)


async def main():
    # Load config
    try:
        with open("system_config.yaml", "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            config_data = {}
            for doc in docs:
                if isinstance(doc, dict):
                    config_data.update(doc)
    except Exception as e:
        print(f"Failed to load config: {e}")
        return

    adapter = BinanceExecutionAdapter(config=config_data, shadow_mode=False)
    print(f"Adapter initialized. Testnet: {adapter.use_testnet}")
    print(f"Shadow Mode: {adapter.shadow_mode}")

    if adapter.shadow_mode:
        print("Still in Shadow Mode. Credentials missing in system_config.yaml.")
        return

    symbol = "ETHUSDT"
    orig_client_order_id = "a225d85e-b696-430f-b48d-0126ddf2c5ca"

    print(f"Checking order {orig_client_order_id} on {symbol}...")

    try:
        base_url = "https://testnet.binancefuture.com"
        endpoint = "/fapi/v1/allOrders"
        params = {
            "symbol": symbol,
            "limit": 10,
            "timestamp": int(time.time() * 1000)
        }

        signed_params, _, _, _ = adapter._build_signed_request(
            params, log_ctx="CHECK_ORDER")

        import httpx
        headers = {"X-MBX-APIKEY": adapter.api_key}

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{base_url}{endpoint}", params=signed_params, headers=headers)
            if resp.status_code == 200:
                orders = resp.json()
                found = False
                for o in orders:
                    if o.get("clientOrderId") == orig_client_order_id:
                        print(f"Found in HISTORY: {o}")
                        print(f"Status: {o.get('status')}")
                        print(f"Executed Qty: {o.get('executedQty')}")
                        found = True
                        break
                if not found:
                    print("Order not found in last 10 orders.")
                    if orders:
                        print(f"Last order: {orders[-1]}")
            else:
                print(f"Failed to fetch history: {resp.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
