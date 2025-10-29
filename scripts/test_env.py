#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path.cwd() / ".env"
print(f"Looking for .env at: {env_path}")
print(f"Exists: {env_path.exists()}")

if env_path.exists():
    load_dotenv(env_path)
    print(f"Loaded .env")
    print(f"BINANCE_FUTURES_API_KEY_LIVE: {os.environ.get('BINANCE_FUTURES_API_KEY_LIVE', 'NOT SET')[:20]}...")
    print(f"BINANCE_TESTNET_API_KEY: {os.environ.get('BINANCE_TESTNET_API_KEY', 'NOT SET')[:20]}...")
