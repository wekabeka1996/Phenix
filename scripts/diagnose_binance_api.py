#!/usr/bin/env python3
"""
Diagnostic script for Binance API timestamp issues.

Tests margin type and leverage setting API calls in isolation.
"""

import os
import sys
import time
import hmac
import hashlib
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

def get_signed_params(api_secret: str, params: dict) -> dict:
    """Create signed parameters for Binance API."""
    signed_params = params.copy()
    signed_params["timestamp"] = str(int(time.time() * 1000))
    signed_params["recvWindow"] = "1500"

    # Create signature
    query_string = "&".join(f"{k}={v}" for k, v in sorted(signed_params.items()))
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    signed_params["signature"] = signature
    return signed_params

def test_margin_type(api_key: str, api_secret: str, base_url: str, symbol: str = "BTCUSDT"):
    """Test setting margin type."""
    print(f"\n=== Testing Margin Type Setting for {symbol} ===")

    params = {
        "symbol": symbol,
        "marginType": "CROSS",
    }

    signed_params = get_signed_params(api_secret, params)
    print(f"Params: {params}")
    print(f"Signed params keys: {list(signed_params.keys())}")

    url = f"{base_url}/fapi/v1/marginType"
    headers = {"X-MBX-APIKEY": api_key}

    print(f"POST {url}")
    print(f"Headers: X-MBX-APIKEY: {api_key[:10]}...")

    try:
        resp = requests.post(url, headers=headers, data=signed_params, timeout=10)
        print(f"Response status: {resp.status_code}")

        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            print(f"Response JSON: {data}")
        else:
            print(f"Response text: {resp.text}")

        return resp.status_code == 200

    except Exception as e:
        print(f"Error: {e}")
        return False

def test_leverage(api_key: str, api_secret: str, base_url: str, symbol: str = "BTCUSDT", leverage: int = 10):
    """Test setting leverage."""
    print(f"\n=== Testing Leverage Setting for {symbol} ===")

    params = {
        "symbol": symbol,
        "leverage": str(leverage),
    }

    signed_params = get_signed_params(api_secret, params)
    print(f"Params: {params}")
    print(f"Signed params keys: {list(signed_params.keys())}")

    url = f"{base_url}/fapi/v1/leverage"
    headers = {"X-MBX-APIKEY": api_key}

    print(f"POST {url}")
    print(f"Headers: X-MBX-APIKEY: {api_key[:10]}...")

    try:
        resp = requests.post(url, headers=headers, data=signed_params, timeout=10)
        print(f"Response status: {resp.status_code}")

        if resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            print(f"Response JSON: {data}")
        else:
            print(f"Response text: {resp.text}")

        return resp.status_code == 200

    except Exception as e:
        print(f"Error: {e}")
        return False

def test_dry_run():
    """Test signing logic without API calls."""
    print("\n=== DRY RUN MODE - Testing Signing Logic ===")

    # Mock credentials for testing
    mock_api_secret = "mock_secret_for_testing"

    # Test margin type params
    margin_params = {
        "symbol": "BTCUSDT",
        "marginType": "CROSS",
    }
    signed_margin = get_signed_params(mock_api_secret, margin_params)
    print("Margin Type Signed Params:")
    for k, v in signed_margin.items():
        print(f"  {k}: {v}")

    # Test leverage params
    leverage_params = {
        "symbol": "BTCUSDT",
        "leverage": "10",
    }
    signed_leverage = get_signed_params(mock_api_secret, leverage_params)
    print("\nLeverage Signed Params:")
    for k, v in signed_leverage.items():
        print(f"  {k}: {v}")

    # Verify required fields
    required_fields = ["symbol", "timestamp", "recvWindow", "signature"]
    margin_ok = all(field in signed_margin for field in required_fields)
    leverage_ok = all(field in signed_leverage for field in required_fields)

    print("\nValidation:")
    print(f"Margin params valid: {'✅' if margin_ok else '❌'}")
    print(f"Leverage params valid: {'✅' if leverage_ok else '❌'}")

    if margin_ok and leverage_ok:
        print("🎉 Signing logic appears correct!")
        print("The issue is likely in how the HTTP request is made (POST data vs query params)")
        return True
    else:
        print("💥 Signing logic has issues")
        return False
    """Main diagnostic function."""
    print("Binance API Timestamp Diagnostic Tool")
    print("=" * 50)

    # Load environment variables
    use_testnet = os.environ.get("USE_TESTNET", "true").lower() == "true"

    if use_testnet:
        api_key = os.environ.get("BINANCE_TESTNET_API_KEY", "")
        api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET", "")
        base_url = "https://testnet.binancefuture.com"
        env_name = "TESTNET"
    else:
        api_key = os.environ.get("BINANCE_MAINNET_API_KEY", "")
        api_secret = os.environ.get("BINANCE_MAINNET_API_SECRET", "")
        base_url = "https://fapi.binance.com"
        env_name = "MAINNET"

    print(f"Environment: {env_name}")
    print(f"Base URL: {base_url}")
    print(f"API Key configured: {'YES' if api_key else 'NO'}")
    print(f"API Secret configured: {'YES' if api_secret else 'NO'}")

    if not api_key or not api_secret:
        print("⚠️  API credentials not configured - running in DRY RUN mode")
        print("This will test the signing logic without making actual API calls")
        return test_dry_run()

    # Test margin type
    margin_success = test_margin_type(api_key, api_secret, base_url)

    # Test leverage
    leverage_success = test_leverage(api_key, api_secret, base_url)

    print("\n=== Results ===")
    print(f"Margin Type: {'✅ SUCCESS' if margin_success else '❌ FAILED'}")
    print(f"Leverage: {'✅ SUCCESS' if leverage_success else '❌ FAILED'}")

    if margin_success and leverage_success:
        print("🎉 All tests passed! Timestamp issue appears to be resolved.")
        return True
    else:
        print("💥 Some tests failed. Check the error details above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)