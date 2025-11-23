
import os
from pathlib import Path
from dotenv import load_dotenv


def test_env():
    root = Path("c:/Users/user/Music/Phenix")
    env_path = root / ".env"
    print(f"Env path: {env_path}")
    print(f"Exists: {env_path.exists()}")

    load_dotenv(env_path)

    key = os.environ.get("BINANCE_TESTNET_API_KEY")
    print(f"BINANCE_TESTNET_API_KEY: {key}")


if __name__ == "__main__":
    test_env()
