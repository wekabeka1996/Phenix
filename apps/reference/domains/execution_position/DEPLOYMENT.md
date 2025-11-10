# Execution Position Domain - Deployment Guide

## Overview

This guide covers deployment, configuration, and operational procedures for the execution_position domain in production environments.

## Prerequisites

### System Requirements
- **Python**: 3.9+
- **Memory**: 2GB minimum, 4GB recommended
- **CPU**: 2 cores minimum
- **Network**: Low-latency connection to Binance API
- **Storage**: 100MB for logs and state

### Dependencies
```bash
pip install -r requirements.txt
```

### Environment Setup
```bash
# Create virtual environment
python -m venv .venv
.venv/Scripts/Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Validate installation
python -c "import apps.reference.domains.execution_position.fsm; print('OK')"
```

## Configuration

### Environment Variables
```bash
# Trading mode
export TRADING_MODE=testnet  # or live

# API credentials (secure storage recommended)
export BINANCE_API_KEY=your_api_key
export BINANCE_API_SECRET=your_api_secret

# Risk parameters
export MAX_EXPOSURE_PER_SYMBOL=100000
export MAX_TOTAL_EXPOSURE=500000

# Monitoring
export METRICS_PORT=9090
export HEALTH_CHECK_PORT=8080
```

### Configuration File Structure
```yaml
# config/master_config_v1.yaml
trading:
  mode: "${TRADING_MODE}"
  execution:
    cooldown_ms: 1000
    guard_enabled: true
    watchdog:
      ack_ttl_ms: 8000
      fill_ttl_ms: 30000
    manage:
      auto_manage: true
      brackets:
        enable: true
        sl:
          fixed_bps: 50
        tp:
          fixed_bps: 100
        offset_bps: 5
        oco_emulation: true
    orphan_monitor:
      enabled: true
      run_on_startup: true
      periodic_interval_sec: 300
      min_order_age_sec: 0
      batch_cancel_limit: 50
      rate_limit_per_min: 120
  orders:
    default_ttl_seconds: 30
  instruments:
    BTCUSDT:
      tick_size: "0.01"
      min_qty: "0.000001"
```

## Deployment Options

### 1. Standalone Process
```bash
# Start execution position service
python -m apps.reference.domains.execution_position.fsm \
  --config config/master_config_v1.yaml \
  --log-level INFO
```

### 2. Docker Container
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8080 9090

CMD ["python", "-m", "apps.reference.domains.execution_position.fsm"]
```

```bash
# Build and run
docker build -t execution-position .
docker run -p 8080:8080 -p 9090:9090 execution-position
```

### 3. Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: execution-position
spec:
  replicas: 1
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
        ports:
        - containerPort: 8080
        - containerPort: 9090
        env:
        - name: TRADING_MODE
          value: "testnet"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Operational Procedures

### Startup Sequence
1. **Validate Configuration**
   ```bash
   python -c "from config import validate_config; validate_config()"
   ```

2. **Pre-flight Checks**
   ```bash
   # Test API connectivity
   python scripts/test_binance_connectivity.py

   # Validate risk parameters
   python scripts/validate_risk_limits.py
   ```

3. **Start Service**
   ```bash
   python -m apps.reference.domains.execution_position.fsm
   ```

4. **Verify Health**
   ```bash
   curl http://localhost:8080/health
   curl http://localhost:9090/metrics
   ```

### Monitoring

#### Health Endpoints
- **Health Check**: `GET /health` - Service availability
- **Readiness Check**: `GET /ready` - Can accept traffic
- **Metrics**: `GET /metrics` - Prometheus format metrics

#### Key Metrics to Monitor
```prometheus
# Performance
execution_position_request_duration_seconds{quantile="0.95"} < 0.1
execution_position_orders_per_second > 0

# Errors
execution_position_errors_total{type="timeout"} < 0.01
execution_position_errors_total{type="api_error"} < 0.001

# Business
execution_position_active_positions > 0
execution_position_exposure_utilization_ratio < 0.8
```

#### Log Monitoring
```bash
# Follow logs
tail -f logs/execution_position.log

# Search for errors
grep "ERROR" logs/execution_position.log | tail -10

# Monitor order flow
grep "CMD:OPEN\|EVT:FILL" logs/execution_position.log
```

### Maintenance Tasks

#### Daily
```bash
# Check orphan orders
curl http://localhost:8080/debug/orphan_check

# Review exposure levels
curl http://localhost:8080/debug/exposure_report

# Validate position reconciliation
python scripts/reconcile_positions.py
```

#### Weekly
```bash
# Review logs for anomalies
python scripts/analyze_logs.py --days 7

# Test failover scenarios
python scripts/test_failover.py

# Update risk parameters if needed
python scripts/calibrate_risk_limits.py
```

#### Monthly
```bash
# Full system reconciliation
python scripts/monthly_reconciliation.py

# Performance review
python scripts/performance_analysis.py --period 30d

# Configuration audit
python scripts/config_audit.py
```

## Troubleshooting

### Common Issues

#### 1. API Connection Failures
**Symptoms**: `ConnectionError` in logs, orders not executing

**Diagnosis**:
```bash
# Test connectivity
curl -X POST https://testnet.binance.vision/api/v3/order/test \
  -H "X-MBX-APIKEY: $BINANCE_API_KEY"

# Check network
ping testnet.binance.vision
```

**Resolution**:
- Verify API credentials
- Check network connectivity
- Review rate limits
- Switch to backup API endpoints

#### 2. Order Timeouts
**Symptoms**: `TimeoutError`, orders stuck in pending state

**Diagnosis**:
```bash
# Check watchdog status
curl http://localhost:8080/debug/watchdog_status

# Review order states
curl http://localhost:8080/debug/pending_orders
```

**Resolution**:
- Adjust timeout parameters
- Check exchange status
- Review network latency
- Enable retry logic

#### 3. Exposure Limit Breaches
**Symptoms**: `EXPOSURE_LIMIT_EXCEEDED` errors

**Diagnosis**:
```bash
# Check current exposure
curl http://localhost:8080/debug/exposure_levels

# Review position sizes
curl http://localhost:8080/debug/positions
```

**Resolution**:
- Adjust risk limits
- Close positions manually
- Review sizing logic
- Update configuration

#### 4. Orphan Orders
**Symptoms**: Orders not tracked by system

**Diagnosis**:
```bash
# Run orphan detection
curl http://localhost:8080/debug/orphan_scan

# Check reconciliation
python scripts/reconcile_orphans.py
```

**Resolution**:
- Run cleanup procedure
- Review order tracking logic
- Update reconciliation rules
- Manual intervention if needed

### Emergency Procedures

#### Service Restart
```bash
# Graceful shutdown
curl -X POST http://localhost:8080/shutdown

# Wait for cleanup
sleep 30

# Restart service
python -m apps.reference.domains.execution_position.fsm
```

#### Emergency Stop
```bash
# Cancel all orders
python scripts/emergency_cancel_all.py

# Close all positions
python scripts/emergency_close_positions.py

# Shutdown service
kill -TERM $(pgrep -f execution_position)
```

#### Data Recovery
```bash
# Restore from backup
python scripts/restore_state.py --backup latest

# Reconcile with exchange
python scripts/full_reconciliation.py

# Validate state
python scripts/validate_state.py
```

## Performance Tuning

### Memory Optimization
```python
# Adjust FSM pool size based on symbols
fsm_pool_size = min(100, len(active_symbols) * 2)

# Configure garbage collection
gc.set_threshold(700, 10, 10)
```

### Network Optimization
```python
# Connection pooling
aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100))

# Timeout configuration
timeout = aiohttp.ClientTimeout(total=10, connect=5)
```

### CPU Optimization
```python
# Async processing
async def process_orders():
    tasks = [process_symbol(symbol) for symbol in symbols]
    await asyncio.gather(*tasks)

# Thread pool for CPU-bound operations
executor = ThreadPoolExecutor(max_workers=4)
```

## Security Considerations

### API Key Management
- Store keys in secure vault (AWS KMS, HashiCorp Vault)
- Rotate keys regularly
- Use read-only keys where possible
- Monitor key usage

### Network Security
- Use HTTPS for all API calls
- Implement rate limiting
- Validate all inputs
- Log security events

### Access Control
- Restrict service ports
- Use authentication for admin endpoints
- Implement RBAC for operations
- Audit all configuration changes

## Backup and Recovery

### State Backup
```bash
# Automated backup script
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
tar -czf backup_$TIMESTAMP.tar.gz \
  /app/state/ \
  /app/logs/ \
  /app/config/
```

### Recovery Procedure
```bash
# Stop service
systemctl stop execution-position

# Restore backup
tar -xzf backup_latest.tar.gz -C /

# Validate state
python scripts/validate_backup.py

# Start service
systemctl start execution-position
```

### Disaster Recovery
- Multi-region deployment
- Automated failover
- Data replication
- Regular DR testing

## Scaling Considerations

### Horizontal Scaling
- Deploy multiple instances
- Use load balancer
- Shared state management
- Event-driven coordination

### Vertical Scaling
- Increase CPU/memory
- Optimize algorithms
- Cache frequently used data
- Monitor resource usage

### Auto-scaling
- CPU utilization > 70%
- Memory usage > 80%
- Queue depth > 100
- Response time > 100ms</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\DEPLOYMENT.md
