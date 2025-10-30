#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from pathlib import Path
import yaml
import re

env_path = Path.cwd() / ".env"
load_dotenv(env_path)

yaml_path = Path.cwd() / "config" / "aurora" / "trading.yaml"
with open(yaml_path) as f:
    data = yaml.safe_load(f)

binance_api = data.get("binance_api", {})
print("Raw YAML binance_api.live:")
print(f"  api_key: {binance_api.get('live', {}).get('api_key')}")

# Test regex substitution
pattern = re.compile(r"\$\{\s*(\w+)\s*\}")

api_key_str = binance_api.get("live", {}).get("api_key", "")
print(f"\nBefore substitution: {api_key_str}")


def resolve(s):
    if isinstance(s, str):
        return pattern.sub(lambda m: os.environ.get(m.group(1), m.group(0)), s)
    return s


result = resolve(api_key_str)
print(f"After substitution: {result[:30]}...")
