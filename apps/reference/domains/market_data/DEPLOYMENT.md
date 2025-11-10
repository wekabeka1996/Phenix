# Market Data Deployment

## Overview

The `market_data` domain is designed for **24/7 operation** in live trading environments with high availability and low latency requirements. This document covers deployment procedures, scaling considerations, and operational monitoring.

**Deployment Model:** Containerized microservice
**Availability Target:** 99.9% uptime
**Latency Target:** < 2 seconds data freshness
**Scaling:** Horizontal scaling with data partitioning

## Deployment Architecture

### Container Configuration

#### Dockerfile
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps/ ./apps/
COPY vfoundation/ ./vfoundation/

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command
CMD ["python", "-m", "apps.reference.domains.market_data.market_data_connector"]
```

#### Docker Compose Configuration
```yaml
version: '3.8'
services:
  market-data:
    build: .
    environment:
      - TRADING_MODE=live
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
      - MARKET_DATA_POLL_INTERVAL=2.0
      - LOG_LEVEL=INFO
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - trading-network

networks:
  trading-network:
    driver: bridge
```

### Kubernetes Deployment

#### Deployment Manifest
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: market-data-connector
  labels:
    app: market-data
    domain: market-data
spec:
  replicas: 2
  selector:
    matchLabels:
      app: market-data
  template:
    metadata:
      labels:
        app: market-data
        domain: market-data
    spec:
      containers:
      - name: market-data
        image: quantumtrader/market-data:latest
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: TRADING_MODE
          value: "live"
        - name: BINANCE_API_KEY
          valueFrom:
            secretKeyRef:
              name: binance-credentials
              key: api-key
        - name: BINANCE_API_SECRET
          valueFrom:
            secretKeyRef:
              name: binance-credentials
              key: api-secret
        - name: MARKET_DATA_POLL_INTERVAL
          value: "2.0"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
```

#### Service Manifest
```yaml
apiVersion: v1
kind: Service
metadata:
  name: market-data-service
  labels:
    app: market-data
spec:
  selector:
    app: market-data
  ports:
  - name: http
    port: 8000
    targetPort: 8000
  type: ClusterIP
```

#### ConfigMap for Configuration
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: market-data-config
data:
  config.yaml: |
    trading:
      market_data:
        poll_interval_sec: 2.0
        symbols:
          - SOLUSDT
          - ETHUSDT
          - BTCUSDT
        websocket_streams:
          - bookTicker
          - trade
        macro_sync:
          anchors:
            - BTCUSDT
            - ETHUSDT
      logging:
        level: INFO
        format: json
```

## Environment Configuration

### Environment Variables

#### Required Variables
```bash
# Binance API Credentials
BINANCE_API_KEY=your_production_api_key
BINANCE_API_SECRET=your_production_api_secret

# Trading Environment
TRADING_MODE=live  # or testnet

# Application Configuration
MARKET_DATA_POLL_INTERVAL=2.0
LOG_LEVEL=INFO
DEBUG_MODE=false
```

#### Optional Variables
```bash
# Performance Tuning
WEBSOCKET_RECONNECT_ATTEMPTS=5
WEBSOCKET_RECONNECT_DELAY=1.0
API_REQUEST_TIMEOUT=5.0
MAX_CONCURRENT_REQUESTS=10

# Monitoring
METRICS_PORT=8000
HEALTH_CHECK_INTERVAL=30
MEMORY_WARNING_THRESHOLD=80

# Feature Flags
ENABLE_MACRO_SYNC=true
ENABLE_DEBUG_LOGGING=false
ENABLE_PERFORMANCE_METRICS=true
```

### Configuration Files

#### Production Configuration
```yaml
# config/production.yaml
trading:
  mode: live
  market_data:
    poll_interval_sec: 2.0
    symbols:
      - SOLUSDT
      - ETHUSDT
      - ADAUSDT
      - DOTUSDT
    websocket_streams:
      - bookTicker
      - trade
    macro_sync:
      anchors:
        - BTCUSDT
        - ETHUSDT
      update_interval_sec: 1.0

logging:
  level: INFO
  format: json
  handlers:
    - console
    - file

monitoring:
  metrics:
    enabled: true
    port: 8000
  health_checks:
    enabled: true
    interval_sec: 30
```

#### Testnet Configuration
```yaml
# config/testnet.yaml
trading:
  mode: testnet
  market_data:
    poll_interval_sec: 2.0
    symbols:
      - SOLUSDT
      - ETHUSDT
    websocket_streams:
      - bookTicker
      - trade

logging:
  level: DEBUG
  format: json

monitoring:
  metrics:
    enabled: true
    port: 8000
```

## Scaling Strategy

### Horizontal Scaling

#### Data Partitioning
```python
class MarketDataPartitioner:
    """Partition symbols across multiple instances"""

    def __init__(self, instance_id: int, total_instances: int):
        self.instance_id = instance_id
        self.total_instances = total_instances

    def get_assigned_symbols(self, all_symbols: List[str]) -> List[str]:
        """Get symbols assigned to this instance"""
        assigned = []
        for i, symbol in enumerate(sorted(all_symbols)):
            if i % self.total_instances == self.instance_id:
                assigned.append(symbol)
        return assigned
```

#### Deployment with Partitioning
```yaml
# Kubernetes deployment with partitioning
apiVersion: apps/v1
kind: Deployment
metadata:
  name: market-data-connector-0
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: market-data
        env:
        - name: INSTANCE_ID
          value: "0"
        - name: TOTAL_INSTANCES
          value: "3"
        # ... other env vars
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: market-data-connector-1
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: market-data
        env:
        - name: INSTANCE_ID
          value: "1"
        - name: TOTAL_INSTANCES
          value: "3"
```

### Vertical Scaling

#### Resource Allocation Guidelines
```yaml
# resources.yaml
resources:
  # Base resources per instance
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "500m"

  # Additional resources per symbol
  per_symbol:
    memory: "2Mi"
    cpu: "5m"

  # Examples for different scales
  small:    # 5 symbols
    memory: "138Mi"
    cpu: "125m"
  medium:   # 20 symbols
    memory: "168Mi"
    cpu: "200m"
  large:    # 50 symbols
    memory: "228Mi"
    cpu: "350m"
```

## Operational Procedures

### Startup Sequence

#### Normal Startup
1. **Configuration Validation**
   ```bash
   # Validate configuration before startup
   python -c "from apps.reference.domains.market_data.config import validate_config; validate_config()"
   ```

2. **Dependency Checks**
   ```bash
   # Test API connectivity
   curl -f https://api.binance.com/api/v3/ping

   # Test WebSocket connectivity
   timeout 5 websocat wss://stream.binance.com:9443/ws/solusdt@bookTicker
   ```

3. **Service Startup**
   ```bash
   # Start the service
   docker-compose up -d market-data

   # Verify startup logs
   docker-compose logs -f market-data
   ```

4. **Health Verification**
   ```bash
   # Wait for health check to pass
   curl -f http://localhost:8000/health

   # Check metrics endpoint
   curl http://localhost:8000/metrics
   ```

#### Recovery Startup
1. **State Assessment**
   ```bash
   # Check for crash dumps or error logs
   docker-compose logs --tail=100 market-data

   # Verify configuration hasn't changed
   git status
   ```

2. **Clean Restart**
   ```bash
   # Stop and remove old containers
   docker-compose down

   # Start fresh
   docker-compose up -d --force-recreate market-data
   ```

### Monitoring Setup

#### Key Metrics to Monitor

##### Data Quality Metrics
```
market_data_data_freshness_seconds{symbol="SOLUSDT"} < 5
market_data_api_request_duration_seconds < 2.0
market_data_websocket_connection_status 1
market_data_events_emitted_total > 0
```

##### Performance Metrics
```
market_data_event_emission_duration_seconds < 0.05
market_data_memory_usage_bytes < 250000000
market_data_cpu_usage_percent < 50
market_data_api_error_rate < 0.05
```

##### Business Metrics
```
market_data_symbols_tracked 20
market_data_events_per_second > 5
market_data_data_completeness_ratio > 0.95
```

#### Alert Configuration

##### Critical Alerts
```yaml
# Prometheus alerting rules
groups:
  - name: market_data_critical
    rules:
      - alert: MarketDataDown
        expr: up{job="market-data"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Market data connector is down"

      - alert: MarketDataStale
        expr: market_data_data_freshness_seconds > 30
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Market data is stale"

      - alert: MarketDataHighErrorRate
        expr: rate(market_data_api_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High market data error rate"
```

##### Warning Alerts
```yaml
  - name: market_data_warning
    rules:
      - alert: MarketDataHighLatency
        expr: market_data_api_request_duration_seconds > 5.0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Market data API latency is high"

      - alert: MarketDataMemoryUsage
        expr: market_data_memory_usage_bytes / market_data_memory_limit_bytes > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Market data memory usage is high"
```

### Log Analysis

#### Log Levels and Patterns

##### Info Level Logs
```
INFO 📊 SOLUSDT Tick: bid=150.5@123.40, ask=200.3@123.50, trades: BUY=45 SELL=32
INFO ✅ Event EVT:MARKET_TICK_RECEIVED emitted for SOLUSDT
INFO 🔗 REST API call completed for SOLUSDT in 0.234s
```

##### Warning Level Logs
```
WARN ⚠️ WebSocket connection lost, falling back to REST polling
WARN ⚠️ API rate limit approaching: 80% used
WARN ⚠️ Data freshness degraded: 8.5 seconds
```

##### Error Level Logs
```
ERROR ❌ Failed to fetch data for SOLUSDT: Connection timeout
ERROR ❌ WebSocket reconnection failed after 5 attempts
ERROR ❌ Event emission failed: FSM unavailable
```

#### Log Analysis Commands
```bash
# Monitor real-time event emission
docker-compose logs -f market-data | grep "📊.*Tick:"

# Check error rates
docker-compose logs market-data | grep "❌" | wc -l

# Monitor API latency
docker-compose logs market-data | grep "🔗 REST API" | awk '{print $NF}' | sort -n

# Check data freshness trends
docker-compose logs market-data | grep "freshness" | tail -20
```

## Backup and Recovery

### Configuration Backup
```bash
# Backup configuration
cp config/production.yaml config/production.yaml.backup

# Version control configurations
git add config/
git commit -m "feat: update market data configuration"
```

### Data Recovery

#### Cache Recovery
```python
class MarketDataRecovery:
    """Handle data recovery scenarios"""

    async def recover_from_outage(self):
        """Recover market data after service interruption"""
        # Load last known state
        last_state = await self.load_cached_state()

        # Validate state freshness
        if self.is_state_fresh(last_state):
            # Emit cached data with staleness warning
            await self.emit_stale_data(last_state)
        else:
            # Start fresh data collection
            await self.start_fresh_collection()
```

#### State Persistence
```python
def save_state(self):
    """Persist current market data state"""
    state = {
        'timestamp': int(time.time() * 1000),
        'symbols': {},
        'last_update': self.last_update_time
    }

    for symbol in self.symbols:
        tick = self.websocket_aggregator.get_market_tick(symbol)
        state['symbols'][symbol] = tick

    # Save to Redis or local file
    await self.state_store.save('market_data_state', state)
```

## Security Considerations

### API Key Management

#### Secret Storage
```yaml
# Kubernetes secrets
apiVersion: v1
kind: Secret
metadata:
  name: binance-credentials
type: Opaque
data:
  api-key: <base64-encoded-api-key>
  api-secret: <base64-encoded-api-secret>
```

#### Key Rotation
```bash
# Rotate API keys
kubectl create secret generic binance-credentials-new \
  --from-literal=api-key=$NEW_API_KEY \
  --from-literal=api-secret=$NEW_API_SECRET

# Update deployment to use new secret
kubectl set env deployment/market-data-connector BINANCE_API_KEY_SECRET=binance-credentials-new

# Verify and cleanup
kubectl rollout status deployment/market-data-connector
kubectl delete secret binance-credentials
```

### Network Security

#### Firewall Rules
```bash
# Allow outbound to Binance
iptables -A OUTPUT -d api.binance.com -j ACCEPT
iptables -A OUTPUT -d stream.binance.com -j ACCEPT

# Block all other outbound except essential
iptables -P OUTPUT DROP
```

#### TLS Configuration
```python
# Force TLS 1.3 for API calls
connector = aiohttp.TCPConnector(
    ssl=aiohttp.ssl.create_default_context(),
    limit=10,
    ttl_dns_cache=30
)
```

## Troubleshooting

### Common Deployment Issues

#### Container Won't Start
**Symptoms:** Container exits immediately, health check fails
**Causes:** Configuration errors, missing dependencies, port conflicts
**Solutions:**
```bash
# Check container logs
docker-compose logs market-data

# Validate configuration
python -c "import yaml; yaml.safe_load(open('config/production.yaml'))"

# Test dependencies
python -c "import aiohttp, asyncio; print('Dependencies OK')"
```

#### High Memory Usage
**Symptoms:** Container OOM killed, memory alerts
**Causes:** Too many symbols, memory leaks, large trade windows
**Solutions:**
```bash
# Reduce symbol count
export MARKET_DATA_SYMBOLS="SOLUSDT,ETHUSDT,BTCUSDT"

# Decrease trade window size
export TRADE_WINDOW_SECONDS=30

# Monitor memory usage
docker stats market-data
```

#### WebSocket Connection Issues
**Symptoms:** Frequent disconnections, fallback to REST polling
**Causes:** Network issues, firewall blocking, Binance maintenance
**Solutions:**
```bash
# Test WebSocket connectivity
websocat wss://stream.binance.com:9443/ws/solusdt@bookTicker

# Check firewall rules
iptables -L | grep binance

# Monitor connection stability
docker-compose logs market-data | grep "WebSocket"
```

#### Event Emission Problems
**Symptoms:** No events received by consumers, event queue growing
**Causes:** FSM issues, consumer failures, event serialization errors
**Solutions:**
```bash
# Check FSM connectivity
curl http://fsm-service:8000/health

# Verify event serialization
python -c "import json; json.dumps(sample_event_payload)"

# Monitor event emission logs
docker-compose logs market-data | grep "✅ Event"
```

### Performance Tuning

#### Optimization Settings
```yaml
# config/performance.yaml
market_data:
  # Reduce polling frequency for lower load
  poll_interval_sec: 5.0

  # Limit concurrent requests
  max_concurrent_requests: 5

  # Reduce trade window for lower memory
  trade_window_seconds: 30

  # Batch event emissions
  event_batch_size: 10
  event_batch_timeout_sec: 1.0
```

#### Profiling Commands
```bash
# Profile memory usage
python -m memory_profiler market_data_connector.py

# Profile CPU usage
python -m cProfile -s time market_data_connector.py

# Monitor system resources
docker run --rm --pid=host --net=host nicolargo/glances
```

---

*Deployment Documentation Version: 1.0*
*Last Updated: January 15, 2024*
*Availability Target: 99.9% uptime*
*Latency Target: <2s data freshness*</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\market_data\DEPLOYMENT.md
