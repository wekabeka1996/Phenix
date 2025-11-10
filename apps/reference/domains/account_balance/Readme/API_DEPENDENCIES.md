# API та Залежності - Account Balance Domain

## Зовнішні API

### Binance Futures API

**Base URL:**
- Production: `https://fapi.binance.com`
- Testnet: `https://testnet.binancefuture.com`

**Аутентифікація:**
- API Key: `X-MBX-APIKEY` header
- Signature: HMAC-SHA256 з API Secret
- Timestamp: обов'язковий для всіх запитів

#### Ендпоінти

##### 1. GET /fapi/v2/balance
**Опис:** Отримання балансу всіх активів

**Параметри:**
- `timestamp` (required): Unix timestamp в ms
- `signature` (required): HMAC-SHA256 signature

**Response:**
```json
[
  {
    "accountAlias": "SgsR",
    "asset": "USDT",
    "balance": "122607.35137903",
    "crossWalletBalance": "122607.35137903",
    "crossUnPnl": "0.00000000",
    "availableBalance": "122607.35137903",
    "maxWithdrawAmount": "122607.35137903",
    "marginAvailable": true,
    "updateTime": 1617939110373
  }
]
```

**Rate Limits:** 10 requests per second

##### 2. GET /fapi/v2/positionRisk
**Опис:** Отримання інформації про позиції та ризик

**Параметри:**
- `timestamp` (required): Unix timestamp в ms
- `signature` (required): HMAC-SHA256 signature

**Response:**
```json
[
  {
    "symbol": "BTCUSDT",
    "positionAmt": "0.001",
    "entryPrice": "45000.00",
    "markPrice": "45125.30104489",
    "unRealizedProfit": "12.50630104",
    "liquidationPrice": "42750.00000000",
    "leverage": "10",
    "maxNotionalValue": "5000000",
    "marginType": "cross",
    "isolatedMargin": "0.00000000",
    "isAutoAddMargin": "false",
    "positionSide": "BOTH",
    "notional": "45.12530104",
    "isolatedWallet": "0",
    "updateTime": 1703123456789
  }
]
```

**Rate Limits:** 10 requests per second

## Python Залежності

### Core Dependencies

#### 1. decimal
**Версія:** Built-in (Python 3.11)
**Використання:** Точні фінансові розрахунки

```python
from decimal import Decimal

# Правильні розрахунки
balance = Decimal("1000.50")
profit = Decimal("25.30")
total = balance + profit  # 1025.80 exactly
```

#### 2. threading
**Версія:** Built-in (Python 3.11)
**Використання:** Фонова обробка API polling

```python
import threading
import time

class AccountConnector:
    def __init__(self):
        self._thread = None
        self._running = False

    def _monitor_loop(self):
        while self._running:
            # API polling logic
            time.sleep(30)
```

#### 3. time
**Версія:** Built-in (Python 3.11)
**Використання:** Timestamp генерація та delays

```python
import time

# Unix timestamp in milliseconds
timestamp = int(time.time() * 1000)
```

#### 4. typing
**Версія:** Built-in (Python 3.11)
**Використання:** Type hints для кращої розробки

```python
from typing import List, Dict, Optional, Any

def _emit_balance_update(self, balance_data: List[Dict[str, Any]]) -> None:
    pass
```

### Framework Dependencies

#### 1. FSMCore
**Джерело:** `vfoundation/`
**Використання:** Event-driven communication

```python
from vfoundation.fsm import FSMCore

class AccountConnector:
    def __init__(self, fsm: FSMCore):
        self.fsm = fsm

    def _emit_balance_update(self, data):
        self.fsm.emit(
            event_name="EVT:BALANCE_UPDATE_RECEIVED",
            payload=data,
            why="Balance data updated from Binance API."
        )
```

#### 2. BinanceAdapter
**Джерело:** `bridge/binance_adapter.py`
**Використання:** API communication wrapper

```python
from bridge.binance_adapter import BinanceAdapter

class AccountConnector:
    def __init__(self):
        self.binance = BinanceAdapter()

    def get_balance_data(self):
        return self.binance.get_balance()

    def get_positions_data(self):
        return self.binance.get_positions()
```

## Конфігурація

### Environment Variables

#### Required
```bash
# API Credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# Environment
BINANCE_TESTNET=true  # або false для production
```

#### Optional
```bash
# Polling Configuration
ACCOUNT_BALANCE_POLL_INTERVAL=30  # секунди
ACCOUNT_BALANCE_TIMEOUT=10  # секунди

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Configuration Class

```python
from pydantic import BaseSettings, Field

class AccountBalanceConfig(BaseSettings):
    # API Settings
    binance_api_key: str = Field(..., env="BINANCE_API_KEY")
    binance_api_secret: str = Field(..., env="BINANCE_API_SECRET")
    binance_testnet: bool = Field(True, env="BINANCE_TESTNET")

    # Polling Settings
    poll_interval: int = Field(30, env="ACCOUNT_BALANCE_POLL_INTERVAL")
    api_timeout: int = Field(10, env="ACCOUNT_BALANCE_TIMEOUT")

    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_format: str = Field("json", env="LOG_FORMAT")

    class Config:
        env_file = ".env"
        case_sensitive = False
```

## Data Schemas

### JSON Schema Definitions

#### Balance Asset Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://quantumtraderx.com/schemas/account_balance/asset.json",
  "type": "object",
  "properties": {
    "asset": {
      "type": "string",
      "minLength": 1,
      "description": "Asset symbol (e.g., USDT, BTC)"
    },
    "balance": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d+$",
      "description": "Total balance in asset"
    },
    "crossUnPnl": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d+$",
      "description": "Cross margin unrealized profit/loss"
    },
    "crossWalletBalance": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d+$",
      "description": "Cross wallet balance"
    },
    "updateTime": {
      "type": "integer",
      "minimum": 0,
      "description": "Update timestamp in milliseconds"
    }
  },
  "required": ["asset", "balance", "crossUnPnl", "crossWalletBalance", "updateTime"]
}
```

#### Position Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://quantumtraderx.com/schemas/account_balance/position.json",
  "type": "object",
  "properties": {
    "symbol": {
      "type": "string",
      "minLength": 1,
      "description": "Trading pair symbol"
    },
    "positionAmt": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d+$",
      "description": "Position amount"
    },
    "entryPrice": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$",
      "description": "Average entry price"
    },
    "unRealizedProfit": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d+$",
      "description": "Unrealized profit/loss"
    },
    "leverage": {
      "type": "integer",
      "minimum": 1,
      "maximum": 125,
      "description": "Position leverage"
    },
    "marginType": {
      "enum": ["cross", "isolated"],
      "description": "Margin type"
    },
    "markPrice": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$",
      "description": "Current mark price"
    },
    "liquidationPrice": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$",
      "description": "Liquidation price"
    }
  },
  "required": ["symbol", "positionAmt", "entryPrice", "unRealizedProfit", "leverage", "marginType", "markPrice", "liquidationPrice"]
}
```

## Error Handling

### API Errors

#### HTTP Status Codes
- **400 Bad Request:** Invalid parameters
- **401 Unauthorized:** Invalid API key
- **403 Forbidden:** API key doesn't have permission
- **429 Too Many Requests:** Rate limit exceeded
- **500 Internal Server Error:** Binance server error

#### Custom Exceptions
```python
class BinanceAPIError(Exception):
    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class RateLimitError(BinanceAPIError):
    pass

class AuthenticationError(BinanceAPIError):
    pass
```

### Retry Logic

```python
import backoff
import requests

@backoff.on_exception(
    backoff.expo,
    (requests.exceptions.RequestException, RateLimitError),
    max_tries=3,
    max_time=30
)
def api_call_with_retry(self, endpoint: str) -> dict:
    return self.binance.request(endpoint)
```

## Monitoring

### Health Checks

#### API Connectivity
```python
def check_api_connectivity(self) -> bool:
    try:
        # Ping Binance API
        response = self.binance.ping()
        return response.status_code == 200
    except Exception:
        return False
```

#### Data Freshness
```python
def check_data_freshness(self) -> bool:
    if not self._latest_balance_data:
        return False

    # Check if data is less than 5 minutes old
    latest_update = max(
        asset.get("updateTime", 0)
        for asset in self._latest_balance_data
    )
    return (time.time() * 1000 - latest_update) < 300_000
```

### Metrics

#### Prometheus Metrics
```python
from prometheus_client import Counter, Gauge, Histogram

API_REQUESTS = Counter('account_balance_api_requests_total', 'Total API requests')
API_ERRORS = Counter('account_balance_api_errors_total', 'Total API errors')
DATA_FRESHNESS = Gauge('account_balance_data_freshness_seconds', 'Data freshness in seconds')
REQUEST_LATENCY = Histogram('account_balance_request_latency_seconds', 'Request latency')
```

## Security

### API Key Management
- Зберігання в environment variables
- Ротація ключів кожні 90 днів
- Least privilege principle

### Data Protection
- Шифрування sensitive logs
- Redaction PII data
- Secure communication (HTTPS only)

### Rate Limiting
- Client-side rate limiting
- Exponential backoff on errors
- Circuit breaker pattern

---

**Версія документації:** 1.0
**Дата:** $(date +%Y-%m-%d)</content>
<filePath">c:\Users\user\Music\Phenix\apps\reference\domains\account_balance\Readme\API_DEPENDENCIES.md
