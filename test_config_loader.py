
from apps.reference.config_loader import ConfigLoader
import sys
from pathlib import Path
# Add project root to path
sys.path.insert(0, "c:/Users/user/Music/Phenix")


def test_loader():
    print("Starting ConfigLoader test...")
    loader = ConfigLoader()
    config = loader.load_config()
    print("Config loaded.")

    print(f"Trading Mode: {config.trading_mode}")
    print(f"Binance API Key (from property): {config.binance_api_key}")

    import os
    print(
        f"Env BINANCE_TESTNET_API_KEY: {os.environ.get('BINANCE_TESTNET_API_KEY')}")


if __name__ == "__main__":
    test_loader()
