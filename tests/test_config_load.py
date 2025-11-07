#!/usr/bin/env python3
from apps.reference.config_loader import get_config

cfg = get_config()
print("✅ Config loaded successfully")
print(f"Trading Mode: {cfg.trading_mode}")

api_cfg = cfg.binance_api
print(f"\nBinance API Config:")

# Access Pydantic objects directly (not via .get())
live_key = api_cfg.live.api_key if hasattr(
    api_cfg, 'live') and api_cfg.live else ""
testnet_key = api_cfg.testnet.api_key if hasattr(
    api_cfg, 'testnet') and api_cfg.testnet else ""

print(
    f"  Live API Key: {live_key[:20]}..." if live_key else "  Live API Key: None")
print(
    f"  Live Rest URL: {api_cfg.live.rest_url if hasattr(api_cfg, 'live') and api_cfg.live else 'None'}")

print(
    f"  Testnet API Key: {testnet_key[:20]}..."
    if testnet_key
    else "  Testnet API Key: None"
)
print(
    f"  Testnet Rest URL: {api_cfg.testnet.rest_url if hasattr(api_cfg, 'testnet') and api_cfg.testnet else 'None'}")
