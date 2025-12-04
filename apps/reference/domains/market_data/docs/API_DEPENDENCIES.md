# Market Data API Dependencies

## Overview

The `market_data` domain integrates with multiple external APIs and internal components to provide real-time market data and feature engineering. This document outlines all dependencies, integration patterns, and operational requirements.

**Integration Type:** Hybrid (REST API + WebSocket streams)
**Primary Provider:** Binance API
**Fallback Strategy:** REST polling when WebSocket unavailable
**Data Sources:** Live trading data, testnet simulation

## External API Dependencies

### Binance API

#### REST API Integration

**Purpose:** Fallback data source for comprehensive market information when WebSocket is unavailable.

**Base URLs:**
- **Live Trading:** `https://api.binance.com`
- **Testnet:** `https://testnet.binance.vision`

**Key Endpoints:**

##### Market Data Endpoints
```http
GET /api/v3/ticker/bookTicker
```
**Purpose:** Get best bid/ask prices and sizes for all symbols
**Rate Limit:** 100 requests/second (IP-based)
**Response Format:**
```json
{
  "symbol": "SOLUSDT",
  "bidPrice": "123.40",
  "bidQty": "150.5",
  "askPrice": "123.50",
  "askQty": "200.3"
}
```

```http
GET /api/v3/ticker/price
```
**Purpose:** Get latest price for all symbols
**Rate Limit:** 100 requests/second (IP-based)
**Response Format:**
```json
[
  {
    "symbol": "SOLUSDT",
    "price": "123.45"
  }
]
```

```http
GET /api/v3/trades
```
**Purpose:** Get recent trades for volume and flow analysis
**Parameters:** `symbol`, `limit` (max 1000)
**Rate Limit:** 100 requests/second (IP-based)
**Response Format:**
```json
[
  {
    "id": 123456789,
    "price": "123.45",
    "qty": "10.5",
    "time": 1703123456789,
    "isBuyerMaker": false,
    "isBestMatch": true
  }
]
```

##### Kline/Candlestick Data
```http
GET /api/v3/klines
```
**Purpose:** Get historical price data for delta calculations
**Parameters:** `symbol`, `interval`, `limit`
**Rate Limit:** 100 requests/second (IP-based)
**Response Format:**
```json
[
  [
    1703123400000,  // Open time
    "123.40",        // Open price
    "123.60",        // High price
    "123.20",        // Low price
    "123.45",        // Close price
    "1000.5",        // Volume
    1703123456789,   // Close time
    "123450.67",     // Quote asset volume
    100,             // Number of trades
    "500.25",        // Taker buy base asset volume
    "61530.84",      // Taker buy quote asset volume
    "0"              // Unused field
  ]
]
```

#### WebSocket Integration

**Purpose:** Real-time data streaming for low-latency market data.

**WebSocket URLs:**
- **Live Trading:** `wss://stream.binance.com:9443/ws/`
- **Testnet:** `wss://testnet.binance.vision/ws/`

**Stream Types:**

##### Individual Symbol Book Ticker
```websocket
wss://stream.binance.com:9443/ws/solusdt@bookTicker
```
**Update Frequency:** Real-time (whenever order book changes)
**Message Format:**
```json
{
  "stream": "solusdt@bookTicker",
  "data": {
    "u": 400900217,      // Order book update ID
    "s": "SOLUSDT",      // Symbol
    "b": "123.40",       // Best bid price
    "B": "150.5",        // Best bid quantity
    "a": "123.50",       // Best ask price
    "A": "200.3"         // Best ask quantity
  }
}
```

##### Individual Symbol Trades
```websocket
wss://stream.binance.com:9443/ws/solusdt@trade
```
**Update Frequency:** Real-time (on every trade)
**Message Format:**
```json
{
  "stream": "solusdt@trade",
  "data": {
    "e": "trade",        // Event type
    "E": 1703123456789,  // Event time
    "s": "SOLUSDT",      // Symbol
    "t": 123456789,      // Trade ID
    "p": "123.45",       // Price
    "q": "10.5",         // Quantity
    "T": 1703123456789,  // Trade time
    "m": false,          // Is buyer the market maker?
    "M": true            // Ignore
  }
}
```

##### Multi-Symbol Streams
```websocket
wss://stream.binance.com:9443/stream?streams=solusdt@bookTicker/ethusdt@bookTicker
```
**Purpose:** Subscribe to multiple symbols in single connection
**Benefits:** Reduced connection overhead, better rate limit management

#### Authentication & Rate Limits

##### API Key Authentication
```python
# Required headers for authenticated endpoints
headers = {
    'X-MBX-APIKEY': api_key
}

# Signature generation for private endpoints
def create_signature(query_string, secret_key):
    return hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
```

##### Rate Limits
- **REST API:** 1200 requests/minute (API key), 100 requests/second (IP)
- **WebSocket:** No explicit limits, but 100 connections/minute max
- **Order Limits:** Vary by endpoint and account tier

**Rate Limit Headers:**
```http
X-MBX-USED-WEIGHT-1M: 50      # Requests used in 1 minute
X-MBX-ORDER-COUNT-1M: 0       # Orders used in 1 minute
Retry-After: 30               # Seconds to wait when limit exceeded
```

### Fallback Strategy

#### Automatic Fallback Logic
```python
async def _fetch_market_data(self):
    """Fetch data with automatic fallback from WebSocket to REST"""
    try:
        # Try WebSocket first (preferred)
        if self.websocket_aggregator.has_recent_data():
            return self.websocket_aggregator.get_all_ticks()

        # Fallback to REST API
        self.logger.warning("⚠️ WebSocket data stale, falling back to REST")
        return await self._fetch_via_rest_api()

    except Exception as e:
        self.logger.error(f"❌ Data fetch failed: {e}")
        # Return cached data if available
        return self._get_cached_data()
```

#### Data Source Prioritization
1. **WebSocket (Primary):** Real-time, low latency (< 500ms)
2. **REST API (Fallback):** Comprehensive, reliable (2-5 seconds)
3. **Cached Data (Last Resort):** Stale but available (< 30 seconds old)

## Internal Component Dependencies

### vFoundation Framework

#### FSM Core
**Purpose:** Event emission and system orchestration
**Integration:** Event-driven architecture for market data distribution

**Key Interfaces:**
```python
class MarketDataConnector:
    def __init__(self, fsm: FSM, config: MarketDataConfig):
        self.fsm = fsm
        self.config = config

    async def emit_event(self, event_type: str, payload: dict):
        """Emit market data events to downstream consumers"""
        await self.fsm.emit_event(event_type, payload)
```

**FSM Events:**
- **EVT:MARKET_TICK_RECEIVED:** Primary market data event
- **FSM Lifecycle Events:** Startup, shutdown, health checks

#### Configuration Management
**Purpose:** Centralized configuration loading and validation
**Integration:** Pydantic-based config with environment-specific overrides

**Configuration Schema:**
```python
class MarketDataConfig(BaseModel):
    poll_interval_sec: float = 2.0
    symbols: List[str] = ["SOLUSDT", "ETHUSDT"]
    websocket_streams: List[str] = ["bookTicker", "trade"]

    macro_sync: MacroSyncConfig = MacroSyncConfig()
    api_credentials: BinanceCredentials = BinanceCredentials()

class MacroSyncConfig(BaseModel):
    anchors: List[str] = ["BTCUSDT", "ETHUSDT"]
    update_interval_sec: float = 1.0

class BinanceCredentials(BaseModel):
    api_key: str
    api_secret: str
    testnet: bool = False
```

#### Logging Infrastructure
**Purpose:** Structured logging with correlation IDs and performance monitoring
**Integration:** JSON-formatted logs with configurable levels

**Log Categories:**
```python
# Market data events
self.logger.info(f"📊 {symbol} Tick: bid={bid_size}@{bid}, ask={ask_size}@{ask}, trades: BUY={buy_volume} SELL={sell_volume}")

# API interactions
self.logger.debug(f"🔗 REST API call: {endpoint} for {symbol}")

# Error conditions
self.logger.error(f"❌ WebSocket connection failed: {error}")

# Performance metrics
self.logger.info(f"⏱️ Data processing latency: {processing_time:.3f}s")
```

### BinanceAdapter Component

#### Purpose
**Role:** Abstracted Binance API client with retry logic and error handling
**Location:** `bridge/binance_adapter.py` or similar
**Integration:** HTTP client wrapper with rate limit management

**Key Methods:**
```python
class BinanceAdapter:
    async def get_book_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get best bid/ask for symbol"""
        pass

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for symbol"""
        pass

    async def get_klines(self, symbol: str, interval: str, limit: int) -> List[List[Any]]:
        """Get kline/candlestick data"""
        pass
```

#### Error Handling
```python
class BinanceAdapter:
    async def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make HTTP request with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = await self.session.get(f"{self.base_url}{endpoint}", params=params)
                response.raise_for_status()

                # Check rate limit headers
                if self._is_rate_limited(response):
                    await self._handle_rate_limit(response)
                    continue

                return await response.json()

            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### WebSocketAggregator Component

#### Purpose
**Role:** Real-time data aggregation and feature calculation engine
**Location:** `apps/reference/domains/market_data/websocket_aggregator.py`
**Integration:** WebSocket message processing and state management

**Key Features:**
- **Order Book Aggregation:** Bid/ask price and size tracking
- **Trade Windowing:** Time-based trade aggregation for TFI calculation
- **Feature Calculation:** OBI, TFI, price delta computation
- **Memory Management:** Automatic cleanup of old data

**Core Interface:**
```python
class WebSocketAggregator:
    def __init__(self, symbols: List[str], window_seconds: int = 60):
        self.symbols = symbols
        self.window_seconds = window_seconds
        self.book_state = {}  # symbol -> order book data
        self.trade_windows = {}  # symbol -> time windows of trades

    def on_book_ticker(self, symbol: str, bid: str, bid_size: str,
                      ask: str, ask_size: str, timestamp: int):
        """Process book ticker update"""
        pass

    def on_trade(self, symbol: str, price: str, quantity: str,
                 is_buyer_maker: bool, timestamp: int):
        """Process trade update"""
        pass

    def get_market_tick(self, symbol: str) -> Dict[str, Any]:
        """Get aggregated market data for symbol"""
        pass
```

## Data Processing Pipeline

### Data Flow Architecture

```
Binance API
    │
    ├── REST Polling ──┬─ BinanceAdapter ── MarketDataConnector
    │                  │
    └── WebSocket ─────┼─ WebSocketAggregator ── Feature Engineering
                       │
                       └─ Event Emission ── FSM ── Consumers
```

### Processing Stages

#### 1. Data Ingestion
```python
# WebSocket message processing
async def _on_message(self, message: str):
    """Process incoming WebSocket message"""
    data = json.loads(message)

    if data.get('stream', '').endswith('@bookTicker'):
        self._process_book_ticker(data['data'])
    elif data.get('stream', '').endswith('@trade'):
        self._process_trade(data['data'])
```

#### 2. Data Validation
```python
def _validate_market_data(self, data: dict) -> bool:
    """Validate incoming market data"""
    required_fields = ['symbol', 'price', 'bid', 'ask']
    for field in required_fields:
        if field not in data:
            return False

    # Check data freshness
    timestamp = data.get('timestamp', 0)
    if time.time() * 1000 - timestamp > 30000:  # 30 seconds
        return False

    return True
```

#### 3. Feature Calculation
```python
def _calculate_features(self, symbol: str) -> dict:
    """Calculate trading features from raw data"""
    book_data = self.book_state.get(symbol, {})
    trade_data = self._get_recent_trades(symbol)

    return {
        'obi': self._calculate_obi(book_data),
        'tfi': self._calculate_tfi(trade_data),
        'price_delta': self._calculate_price_delta(symbol),
        'buy_volume': trade_data.get('buy_volume', 0),
        'sell_volume': trade_data.get('sell_volume', 0)
    }
```

#### 4. Event Emission
```python
async def _emit_market_tick(self, symbol: str, tick_data: dict):
    """Emit processed market data event"""
    event_payload = self._format_event_payload(symbol, tick_data)
    await self.fsm.emit_event("EVT:MARKET_TICK_RECEIVED", event_payload)
```

## Operational Dependencies

### Infrastructure Requirements

#### Network Connectivity
- **Latency:** < 100ms to Binance data centers
- **Bandwidth:** < 1Mbps for WebSocket streams
- **DNS Resolution:** Reliable Binance domain resolution
- **Firewall:** Outbound connections to Binance IPs

#### System Resources
- **CPU:** < 5% for data processing (single core)
- **Memory:** < 50MB base + 2MB per symbol
- **Storage:** None required (in-memory processing)
- **Concurrency:** Single-threaded processing acceptable

### Monitoring Dependencies

#### Health Checks
```python
async def health_check(self) -> dict:
    """Comprehensive health check for market data"""
    return {
        'websocket_connected': self.websocket_aggregator.is_connected(),
        'api_reachable': await self._test_api_connectivity(),
        'data_freshness': self._check_data_freshness(),
        'event_emission': self._check_event_emission_rate(),
        'memory_usage': self._get_memory_usage()
    }
```

#### Metrics Collection
- **Prometheus Metrics:** Data freshness, API latency, event rates
- **Custom Metrics:** OBI/TFI distributions, error rates
- **Logging:** Structured JSON logs with correlation IDs

### Configuration Dependencies

#### Environment Variables
```bash
# Required
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
TRADING_MODE=live|testnet

# Optional
MARKET_DATA_POLL_INTERVAL=2.0
WEBSOCKET_RECONNECT_ATTEMPTS=5
LOG_LEVEL=INFO
```

#### Configuration Validation
```python
def validate_config(self, config: MarketDataConfig) -> List[str]:
    """Validate market data configuration"""
    errors = []

    if not config.api_credentials.api_key:
        errors.append("Binance API key is required")

    if config.poll_interval_sec < 0.5:
        errors.append("Poll interval must be >= 0.5 seconds")

    if len(config.symbols) == 0:
        errors.append("At least one symbol must be configured")

    return errors
```

## Failure Scenarios & Recovery

### API Failure Modes

#### Rate Limit Exceeded
**Detection:** HTTP 429 responses, rate limit headers
**Recovery:** Exponential backoff, reduce polling frequency
**Fallback:** Use cached data, reduce symbol count

#### Network Connectivity Issues
**Detection:** Connection timeouts, DNS failures
**Recovery:** Automatic retry with jitter, switch to REST-only mode
**Fallback:** Cached data emission with staleness warnings

#### API Service Degradation
**Detection:** Increased latency, error responses
**Recovery:** Circuit breaker pattern, gradual recovery
**Fallback:** Historical data replay if available

### Component Failure Modes

#### WebSocketAggregator Failure
**Detection:** Memory leaks, processing errors
**Recovery:** Component restart, state reset
**Fallback:** REST-only operation

#### FSM Integration Failure
**Detection:** Event emission failures, FSM unavailability
**Recovery:** Queue events for later emission, alert operators
**Fallback:** Local logging of market data

## Testing Dependencies

### Mock Infrastructure

#### API Mocks
```python
class MockBinanceAdapter:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_history = []

    async def get_book_ticker(self, symbol: str):
        self.call_history.append(('get_book_ticker', symbol))
        return self.responses.get(symbol, self._default_response())
```

#### WebSocket Mocks
```python
class MockWebSocketAggregator:
    def __init__(self):
        self.messages = []
        self.ticks = {}

    def on_book_ticker(self, *args):
        self.messages.append(('book_ticker', args))

    def get_market_tick(self, symbol):
        return self.ticks.get(symbol, {})
```

### Integration Testing

#### End-to-End Test Setup
```python
@pytest.fixture
async def market_data_stack(self):
    """Complete market data testing stack"""
    # Setup mocks
    binance_mock = MockBinanceAdapter()
    websocket_mock = MockWebSocketAggregator()
    fsm_mock = MockFSM()

    # Create connector
    config = MarketDataConfig(symbols=['SOLUSDT'])
    connector = MarketDataConnector(fsm_mock, config)

    # Inject mocks
    connector.binance_adapter = binance_mock
    connector.websocket_aggregator = websocket_mock

    return {
        'connector': connector,
        'binance_mock': binance_mock,
        'websocket_mock': websocket_mock,
        'fsm_mock': fsm_mock
    }
```

---

*API Dependencies Documentation Version: 1.0*
*Last Updated: January 15, 2024*
*Primary Provider: Binance API (REST + WebSocket)*
*Fallback Strategy: Automatic REST fallback*</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\market_data\API_DEPENDENCIES.md
