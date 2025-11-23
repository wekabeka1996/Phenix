"""
Quick test to verify demo-fapi.binance.com API key validity
"""
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

print(f"Testing demo-fapi.binance.com with API_KEY: {API_KEY[:20]}...")

# Test 1: Server time (no auth)
print("\n1. Testing /fapi/v1/time (no auth)...")
resp = httpx.get(f"{BASE_URL}/fapi/v1/time", timeout=5)
print(f"   Status: {resp.status_code}")
print(f"   Response: {resp.json()}")

# Test 2: Account info (requires auth + signature)
print("\n2. Testing /fapi/v2/account (with auth + signature)...")
timestamp = int(time.time() * 1000)
params = {"timestamp": timestamp, "recvWindow": 5000}
query_string = "&".join(f"{k}={v}" for k, v in params.items())
signature = hmac.new(
    API_SECRET.encode("utf-8"),
    query_string.encode("utf-8"),
    hashlib.sha256
).hexdigest()
params["signature"] = signature

headers = {"X-MBX-APIKEY": API_KEY}
resp = httpx.get(f"{BASE_URL}/fapi/v2/account",
                 params=params, headers=headers, timeout=10)
print(f"   Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"   ✅ Account connected!")
    print(f"   Balance: {data.get('totalWalletBalance', '?')} USDT")
    print(f"   Available: {data.get('availableBalance', '?')} USDT")
else:
    print(f"   ❌ Error: {resp.json()}")
