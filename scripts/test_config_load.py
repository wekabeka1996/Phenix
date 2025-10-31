#!/usr/bin/env python3
from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pathlib import Path
import sys

# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.config_loader import get_config

cfg = get_config()
print('✅ Config loaded successfully')
print(f'Trading Mode: {cfg.get("trading_mode")}')

api_cfg = cfg.get('binance_api')
print(f'\nBinance API Config:')

live_key = api_cfg.get('live', {}).get('api_key', '')
testnet_key = api_cfg.get('testnet', {}).get('api_key', '')

print(f'  Live API Key: {live_key[:20]}...' if live_key else '  Live API Key: None')
print(f'  Live Rest URL: {api_cfg.get("live", {}).get("rest_url", "None")}')

print(f'  Testnet API Key: {testnet_key[:20]}...' if testnet_key else '  Testnet API Key: None')
print(f'  Testnet Rest URL: {api_cfg.get("testnet", {}).get("rest_url", "None")}')
