"""
Test placing a real LIMIT order on demo-fapi.binance.com
"""
from decimal import Decimal, ROUND_DOWN
import time
import hmac
import hashlib
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_API_SECRET")
BASE_URL = "https://demo-fapi.binance.com"

print(f"Testing LIMIT order placement on demo-fapi.binance.com...")

# Step 1: Get current price for SOLUSDT
print("\n1. Fetching current SOLUSDT price...")
resp = httpx.get(f"{BASE_URL}/fapi/v1/ticker/price?symbol=SOLUSDT", timeout=5)
if resp.status_code != 200:
    print(f"❌ Failed to get price: {resp.json()}")
    exit(1)
current_price = float(resp.json()["price"])
print(f"   Current price: {current_price} USDT")

# Step 2: Place LIMIT BUY order 5% below market
# SOLUSDT: tickSize=0.01 (price), quantityPrecision=0 (quantity must be integer)
limit_price_dec = Decimal(str(current_price * 0.95)
                          ).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
limit_price = str(limit_price_dec)
quantity = "1"  # Must be integer for SOLUSDT
print(f"\n2. Placing LIMIT BUY order: {quantity} SOLUSDT @ {limit_price} USDT")

timestamp = int(time.time() * 1000)
params = {
    "symbol": "SOLUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "quantity": quantity,
    "price": str(limit_price),
    "timeInForce": "GTC",
    "timestamp": timestamp,
    "recvWindow": 5000,
}

# Sign request
query_string = "&".join(f"{k}={v}" for k, v in params.items())
signature = hmac.new(
    API_SECRET.encode("utf-8"),
    query_string.encode("utf-8"),
    hashlib.sha256
).hexdigest()
params["signature"] = signature

headers = {"X-MBX-APIKEY": API_KEY}

print(f"   Sending POST {BASE_URL}/fapi/v1/order with timeout=30s...")
start = time.time()
try:
    resp = httpx.post(f"{BASE_URL}/fapi/v1/order",
                      params=params, headers=headers, timeout=30.0)
    elapsed = time.time() - start
    print(f"   Response time: {elapsed:.2f}s")
    print(f"   Status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ Order placed successfully!")
        print(f"   Order ID: {data.get('orderId')}")
        print(f"   Client Order ID: {data.get('clientOrderId')}")
        print(f"   Status: {data.get('status')}")
    else:
        print(f"   ❌ Error: {resp.json()}")
except httpx.TimeoutException as e:
    elapsed = time.time() - start
    print(f"   ❌ TIMEOUT after {elapsed:.2f}s: {e}")
except Exception as e:
    elapsed = time.time() - start
    print(f"   ❌ Exception after {elapsed:.2f}s: {type(e).__name__}: {e}")
