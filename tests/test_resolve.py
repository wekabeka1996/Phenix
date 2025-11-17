#!/usr/bin/env python3
"""Simple script to verify AuroraConfig picks up binance credentials."""

import os
from dotenv import load_dotenv

from apps.reference.config_loader import load_config

load_dotenv()

cfg = load_config(config_root="config")
binance_api = cfg.binance_api

print("Resolved Binance API keys via AuroraConfig:")
print(f"  Live API key : {binance_api.live.api_key}")
print(f"  Testnet API key : {binance_api.testnet.api_key}")
print("Environment snapshot:")
print(f"  BINANCE_TESTNET_API_KEY = {os.environ.get('BINANCE_TESTNET_API_KEY')}")
print(f"  BINANCE_LIVE_API_KEY = {os.environ.get('BINANCE_LIVE_API_KEY')}")
