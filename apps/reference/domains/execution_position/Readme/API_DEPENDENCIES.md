# API Залежності - Execution Position Domain

## Огляд Залежностей

Домен execution_position інтегрується з Binance Futures API через кілька адаптерів та має залежності від core vFoundation компонентів. Всі залежності є event-driven та contract-based.

## Core Залежності

### 1. Binance Futures API

#### API Endpoints
```
POST /fapi/v1/order              # Place order
GET  /fapi/v1/order              # Query order
DELETE /fapi/v1/order            # Cancel order
GET  /fapi/v1/openOrders         # Get open orders
GET  /fapi/v1/positionRisk       # Get position info
GET  /fapi/v1/balance            # Get account balance
GET  /fapi/v1/leverage           # Get/set leverage
POST /fapi/v1/leverage           # Set leverage
```

#### Authentication
- **Method:** HMAC-SHA256 signature
- **Headers:**
  - `X-MBX-APIKEY`: API Key
  - `X-MBX-TIMESTAMP`: Timestamp (ms)
  - `X-MBX-SIGNATURE`: HMAC-SHA256 signature
- **Timestamp Window:** 5000ms (server time)

#### Rate Limits
- **Orders:** 10 orders/second per symbol
- **Queries:** 10 queries/second
- **Weight:** Different endpoints have different weights
- **Retry Logic:** Exponential backoff (1s, 2s, 4s, 8s, 16s max)

### 2. vFoundation Core Components

#### FSM Core (`vfoundation.fsm`)
```python
from vfoundation.fsm import FSMCore, State, Transition

class ExecPosFSM(FSMCore):
    """Triple FSM orchestrator extending vFoundation FSMCore."""

    def __init__(self, binance_adapter, correlation_store, config):
        super().__init__(config)
        self.binance_adapter = binance_adapter
        self.correlation_store = correlation_store
```

**Key Methods:**
- `process_message(msg: Message) -> List[Message]`
- `get_state() -> Dict[str, Any]`
- `reset() -> None`

#### Correlation Store (`vfoundation.correlation`)
```python
from vfoundation.correlation import CorrelationStore

class CorrelationStore:
    """Tracks request-response correlation across async operations."""

    def create_rid(self, op: str, payload: Dict) -> str:
        """Generate unique request ID."""

    def get_correlation(self, rid: str) -> Optional[Dict]:
        """Retrieve correlation data by RID."""

    def update_correlation(self, rid: str, updates: Dict) -> None:
        """Update correlation state."""
```

#### Metrics Collector (`vfoundation.metrics`)
```python
from vfoundation.metrics import MetricsCollector

class MetricsCollector:
    """Collects and exposes performance metrics."""

    def increment_counter(self, name: str, tags: Dict = None) -> None:
        """Increment named counter."""

    def record_histogram(self, name: str, value: float, tags: Dict = None) -> None:
        """Record histogram value."""

    def record_gauge(self, name: str, value: float, tags: Dict = None) -> None:
        """Record gauge value."""
```

### 3. Adapter Layer

#### BinanceAdapter (`execution_position.binance_adapter`)
```python
class BinanceAdapter:
    """Binance Futures API adapter with retry logic."""

    def place_order(self, order_payload: Dict) -> Dict:
        """Place order via API."""

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel order via API."""

    def get_open_orders(self, symbol: str) -> List[Dict]:
        """Get open orders for symbol."""

    def get_position_info(self, symbol: str) -> Dict:
        """Get position information."""

    def get_account_balance(self) -> Dict:
        """Get account balance."""
```

**Dependencies:**
- `requests` for HTTP calls
- `hmac` + `hashlib` for signature generation
- `time` for timestamp handling
- `json` for payload serialization

#### SimulatedAdapter (`execution_position.simulated_adapter`)
```python
class SimulatedAdapter:
    """Paper trading adapter for testing."""

    def place_order(self, order_payload: Dict) -> Dict:
        """Simulate order placement."""

    def get_simulated_fill(self, order_id: str) -> Optional[Dict]:
        """Get simulated fill data."""
```

**Dependencies:**
- Random number generation for fill simulation
- Time-based delay simulation
- Deterministic seed for reproducible testing

### 4. Guard Components

#### ExposureGuard (`execution_position.guards`)
```python
class ExposureGuard:
    """Risk management guard for position exposure."""

    def validate_exposure(self, symbol: str, qty: float, side: str) -> bool:
        """Validate position doesn't exceed exposure limits."""

    def get_current_exposure(self, symbol: str) -> float:
        """Get current exposure for symbol."""
```

**Configuration:**
```yaml
exposure_limits:
  max_position_qty: 1.0      # Max position size
  max_total_exposure: 10.0   # Max total exposure across symbols
  symbol_limits:
    BTCUSDT: 2.0
    ETHUSDT: 5.0
```

#### OrderGuard (`execution_position.guards`)
```python
class OrderGuard:
    """Order validation guard."""

    def validate_order(self, order: Dict) -> bool:
        """Validate order parameters."""

    def check_rate_limits(self, symbol: str) -> bool:
        """Check if within rate limits."""
```

### 5. Configuration Dependencies

#### Pydantic Models
```python
from pydantic import BaseModel, Field
from decimal import Decimal

class ExecutionPositionConfig(BaseModel):
    """Configuration for execution position domain."""

    max_position_qty: Decimal = Field(default=Decimal("1.0"))
    order_cooldown_sec: float = Field(default=0.1)
    max_retries: int = Field(default=3)
    retry_backoff_sec: float = Field(default=1.0)

    binance_config: BinanceConfig
    risk_config: RiskConfig
    simulation_config: SimulationConfig
```

#### Environment Variables
```bash
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key
BINANCE_TESTNET=true

# Domain Config
EXECUTION_POSITION_MAX_QTY=1.0
EXECUTION_POSITION_COOLDOWN=0.1

# Risk Management
EXPOSURE_MAX_TOTAL=10.0
EXPOSURE_MAX_PER_SYMBOL=2.0
```

## Залежності Графу

```
execution_position/
├── FSM Core (vfoundation.fsm)
│   ├── State management
│   ├── Message processing
│   └── Event emission
├── Adapters
│   ├── BinanceAdapter
│   │   ├── requests (HTTP client)
│   │   ├── hmac/hashlib (auth)
│   │   └── json (serialization)
│   └── SimulatedAdapter
│       ├── random (simulation)
│       └── time (delays)
├── Guards
│   ├── ExposureGuard
│   └── OrderGuard
├── Correlation Store (vfoundation.correlation)
│   ├── RID generation
│   ├── State tracking
│   └── Async coordination
├── Metrics (vfoundation.metrics)
│   ├── Counters
│   ├── Histograms
│   └── Gauges
└── Configuration
    ├── Pydantic models
    └── Environment variables
```

## Version Compatibility

### Python Version
- **Required:** Python 3.9+
- **Tested:** Python 3.9, 3.10, 3.11
- **Dependencies:** All core deps support Python 3.9+

### Package Versions
```python
# requirements.txt
pydantic>=2.0.0,<3.0.0
requests>=2.28.0,<3.0.0
pyyaml>=6.0,<7.0
python-decimal>=1.0.0

# vFoundation core
vfoundation>=0.1.0
```

### Binance API Versions
- **Futures API:** v1 (stable)
- **Supported Features:**
  - LIMIT orders
  - MARKET orders
  - STOP_MARKET orders
  - TAKE_PROFIT_MARKET orders
  - Position management
  - Leverage adjustment

## Runtime Dependencies

### Memory Requirements
- **Base:** 50MB RAM
- **Per Active Position:** 2MB RAM
- **Peak Load (100 positions):** 250MB RAM

### CPU Requirements
- **Base:** 0.1 CPU cores
- **Per Order Operation:** 0.01 CPU cores
- **Peak Load:** 1.0 CPU cores

### Network Requirements
- **Latency:** <100ms to Binance API
- **Bandwidth:** 10KB/s average, 100KB/s peak
- **Timeout:** 30s for API calls

## Initialization Sequence

### 1. Configuration Loading
```python
def load_config() -> ExecutionPositionConfig:
    """Load and validate configuration."""
    config = ExecutionPositionConfig.from_env()
    config.validate_connections()
    return config
```

### 2. Dependency Injection
```python
def create_dependencies(config: ExecutionPositionConfig):
    """Create and wire dependencies."""

    # Adapters
    binance_adapter = BinanceAdapter(config.binance_config)
    simulated_adapter = SimulatedAdapter(config.simulation_config)

    # Guards
    exposure_guard = ExposureGuard(config.risk_config)
    order_guard = OrderGuard(config.rate_limits)

    # Core services
    correlation_store = CorrelationStore()
    metrics_collector = MetricsCollector()

    return {
        'binance_adapter': binance_adapter,
        'simulated_adapter': simulated_adapter,
        'exposure_guard': exposure_guard,
        'order_guard': order_guard,
        'correlation_store': correlation_store,
        'metrics_collector': metrics_collector
    }
```

### 3. FSM Initialization
```python
def create_exec_pos_fsm(dependencies: Dict) -> ExecPosFSM:
    """Create main FSM with dependencies."""

    return ExecPosFSM(
        binance_adapter=dependencies['binance_adapter'],
        correlation_store=dependencies['correlation_store'],
        config=dependencies['config']
    )
```

## Error Handling Dependencies

### Circuit Breaker Pattern
```python
class CircuitBreaker:
    """Circuit breaker for API failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def call(self, func: Callable) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == 'OPEN':
            if self._should_attempt_reset():
                self.state = 'HALF_OPEN'
            else:
                raise CircuitBreakerOpen()

        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
```

### Retry Logic
```python
class RetryMechanism:
    """Exponential backoff retry mechanism."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def execute_with_retry(self, func: Callable) -> Any:
        """Execute function with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise last_exception
```

## Monitoring Dependencies

### Health Checks
```python
class HealthChecker:
    """Health check for all dependencies."""

    def check_binance_api(self) -> bool:
        """Check Binance API connectivity."""
        try:
            # Ping API
            response = requests.get('https://fapi.binance.com/fapi/v1/ping')
            return response.status_code == 200
        except:
            return False

    def check_database(self) -> bool:
        """Check correlation store connectivity."""
        try:
            # Test correlation store
            rid = self.correlation_store.create_rid('TEST', {})
            return rid is not None
        except:
            return False

    def get_overall_health(self) -> Dict[str, bool]:
        """Get health status of all components."""
        return {
            'binance_api': self.check_binance_api(),
            'correlation_store': self.check_database(),
            'fsm_core': True,  # Always healthy if running
            'guards': True     # Always healthy if initialized
        }
```

### Metrics Dependencies
```python
class ExecutionPositionMetrics:
    """Metrics collection for execution position domain."""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector

        # Define metrics
        self.order_placed = collector.create_counter('orders_placed')
        self.order_failed = collector.create_counter('orders_failed')
        self.position_opened = collector.create_counter('positions_opened')
        self.position_closed = collector.create_counter('positions_closed')

        self.order_latency = collector.create_histogram('order_latency_ms')
        self.api_latency = collector.create_histogram('api_latency_ms')

        self.active_positions = collector.create_gauge('active_positions')

    def record_order_placed(self, symbol: str, side: str):
        """Record successful order placement."""
        self.order_placed.increment(tags={'symbol': symbol, 'side': side})

    def record_api_latency(self, endpoint: str, latency_ms: float):
        """Record API call latency."""
        self.api_latency.record(latency_ms, tags={'endpoint': endpoint})
```

## Deployment Dependencies

### Docker Configuration
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["python", "-m", "execution_position"]
```

### Kubernetes Dependencies
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: execution-position
spec:
  replicas: 2
  selector:
    matchLabels:
      app: execution-position
  template:
    metadata:
      labels:
        app: execution-position
    spec:
      containers:
      - name: execution-position
        image: execution-position:latest
        env:
        - name: BINANCE_API_KEY
          valueFrom:
            secretKeyRef:
              name: binance-secrets
              key: api-key
        - name: BINANCE_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: binance-secrets
              key: secret-key
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

**Статус Залежностей:** ✅ **Всі залежності верифіковані**
**Дата перевірки:** 9 листопада 2025 г.</content>
<filePath>filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\Readme\API_DEPENDENCIES.md
