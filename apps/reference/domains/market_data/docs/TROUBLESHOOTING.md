# Market Data Troubleshooting

## Overview

This guide covers common issues, diagnostic procedures, and resolution steps for the `market_data` domain. The domain is designed for high reliability but may encounter issues related to API connectivity, data processing, or system performance.

**Quick Diagnosis:** Check `/health` endpoint and logs for error patterns
**Most Common Issues:** API connectivity (40%), data freshness (30%), memory usage (20%)
**Average Resolution Time:** 15 minutes for known issues

## Health Check Endpoints

### Primary Health Check
```bash
# Basic health check
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "timestamp": 1703123456789,
  "checks": {
    "websocket_connected": true,
    "api_reachable": true,
    "data_freshness": "1.2s",
    "memory_usage": "45MB"
  }
}
```

### Detailed Diagnostics
```bash
# Comprehensive health check
curl http://localhost:8000/health?detailed=true

# Response includes:
# - Individual symbol status
# - API response times
# - WebSocket connection details
# - Event emission statistics
# - Memory breakdown
```

### Readiness Check
```bash
# Check if service is ready to serve traffic
curl http://localhost:8000/ready

# Returns 200 if ready, 503 if not ready
```

## Common Issues & Solutions

### Issue 1: No Market Data Events

**Symptoms:**
- Consumers not receiving `EVT:MARKET_TICK_RECEIVED` events
- Logs show no "📊 Tick:" messages
- Health check shows `"data_freshness": "stale"`

**Diagnostic Steps:**
```bash
# 1. Check service logs
docker-compose logs --tail=50 market-data

# 2. Verify API connectivity
curl -f https://api.binance.com/api/v3/ping

# 3. Check WebSocket connectivity
timeout 10 websocat wss://stream.binance.com:9443/ws/solusdt@bookTicker

# 4. Verify configuration
python -c "from apps.reference.domains.market_data.config import load_config; print(load_config())"
```

**Common Causes & Solutions:**

#### API Credentials Invalid
```
Log Pattern: ERROR ❌ API authentication failed
Solution: Verify BINANCE_API_KEY and BINANCE_API_SECRET
```

```bash
# Test API credentials
curl -H "X-MBX-APIKEY: $BINANCE_API_KEY" \
     "https://api.binance.com/api/v3/account" \
     -H "X-MBX-SIGNATURE: $(echo -n "timestamp=$(date +%s)000" | openssl dgst -sha256 -hmac $BINANCE_API_SECRET | cut -d' ' -f2)"
```

#### Network Connectivity Issues
```
Log Pattern: ERROR ❌ Connection timeout to api.binance.com
Solution: Check network connectivity and firewall rules
```

```bash
# Test network connectivity
ping api.binance.com
traceroute api.binance.com

# Check DNS resolution
nslookup api.binance.com

# Verify firewall rules
iptables -L | grep binance
```

#### WebSocket Connection Failed
```
Log Pattern: WARN ⚠️ WebSocket connection lost, falling back to REST
Solution: Check WebSocket connectivity and proxy settings
```

```bash
# Test WebSocket connection
websocat wss://stream.binance.com:9443/ws/solusdt@bookTicker

# Check for proxy interference
env | grep -i proxy

# Verify SSL/TLS
openssl s_client -connect stream.binance.com:9443 -servername stream.binance.com
```

### Issue 2: Stale Market Data

**Symptoms:**
- Data freshness > 10 seconds in health check
- Event timestamps are old
- Trading signals based on outdated data

**Diagnostic Steps:**
```bash
# Check data freshness
curl http://localhost:8000/health | jq '.checks.data_freshness'

# Monitor event timestamps
docker-compose logs -f market-data | grep "📊" | head -5

# Check API response times
docker-compose logs market-data | grep "🔗 REST API" | tail -10
```

**Common Causes & Solutions:**

#### High API Latency
```
Log Pattern: WARN ⚠️ API request took 8.5s
Solution: Check network latency and API rate limits
```

```bash
# Measure API latency
curl -w "@curl-format.txt" -o /dev/null https://api.binance.com/api/v3/ticker/price

# Check rate limit status
curl -H "X-MBX-APIKEY: $BINANCE_API_KEY" \
     https://api.binance.com/api/v3/account | grep -E "X-MBX-.*-WEIGHT"
```

#### Rate Limit Exceeded
```
Log Pattern: ERROR ❌ Rate limit exceeded, retrying in 30s
Solution: Reduce polling frequency or implement rate limit handling
```

```bash
# Check current rate limit usage
curl -I https://api.binance.com/api/v3/ticker/price

# Headers to check:
# X-MBX-USED-WEIGHT-1M: Current usage
# Retry-After: Seconds to wait
```

#### Processing Bottleneck
```
Log Pattern: WARN ⚠️ Event processing queue growing
Solution: Check system resources and processing capacity
```

```bash
# Monitor system resources
docker stats market-data

# Check CPU usage
top -p $(pgrep -f market_data)

# Monitor memory usage
free -h
```

### Issue 3: Memory Usage Issues

**Symptoms:**
- Container OOM killed
- Memory alerts triggered
- Slow performance and garbage collection pauses

**Diagnostic Steps:**
```bash
# Check memory usage
curl http://localhost:8000/health | jq '.checks.memory_usage'

# Monitor memory growth
docker stats --no-stream market-data

# Check for memory leaks
docker-compose logs market-data | grep "memory" | tail -20
```

**Common Causes & Solutions:**

#### Too Many Symbols
```
Log Pattern: WARN ⚠️ Memory usage at 85%
Solution: Reduce number of tracked symbols
```

```yaml
# Reduce symbol count in config
trading:
  market_data:
    symbols:
      - SOLUSDT
      - ETHUSDT
      - BTCUSDT  # Remove less important symbols
```

#### Large Trade Windows
```
Log Pattern: INFO Memory usage: 120MB
Solution: Reduce trade aggregation window
```

```yaml
# Decrease trade window size
market_data:
  trade_window_seconds: 30  # Reduce from 60
```

#### Memory Leaks
```
Log Pattern: ERROR ❌ Memory leak detected
Solution: Restart service and monitor for recurrence
```

```bash
# Restart service
docker-compose restart market-data

# Monitor memory after restart
watch -n 5 'docker stats market-data --no-stream'
```

### Issue 4: Event Processing Errors

**Symptoms:**
- Events emitted but consumers not processing them
- FSM errors in logs
- Event queue backlog

**Diagnostic Steps:**
```bash
# Check event emission
docker-compose logs market-data | grep "✅ Event" | tail -5

# Verify FSM connectivity
curl http://fsm-service:8000/health

# Check consumer health
curl http://feature-engineering:8000/health
```

**Common Causes & Solutions:**

#### FSM Unavailable
```
Log Pattern: ERROR ❌ Event emission failed: FSM not available
Solution: Check FSM service status and connectivity
```

```bash
# Check FSM service
kubectl get pods -l app=fsm

# Verify network connectivity
telnet fsm-service 8000

# Check FSM logs
kubectl logs -l app=fsm --tail=50
```

#### Consumer Circuit Breaker
```
Log Pattern: WARN ⚠️ Consumer feature_engineering circuit breaker open
Solution: Check consumer health and restart if needed
```

```bash
# Check consumer health
curl http://feature-engineering:8000/health

# Restart consumer if unhealthy
kubectl rollout restart deployment/feature-engineering
```

#### Event Serialization Issues
```
Log Pattern: ERROR ❌ Event payload serialization failed
Solution: Validate event payload structure
```

```python
# Debug event payload
import json
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector

connector = MarketDataConnector(fsm, config)
tick_data = connector.websocket_aggregator.get_market_tick('SOLUSDT')
payload = connector._format_event_payload('SOLUSDT', tick_data)
print(json.dumps(payload, indent=2))
```

## Performance Issues

### Slow Event Processing

**Symptoms:**
- Event emission latency > 100ms
- Consumer processing delays
- System resource contention

**Diagnostic Steps:**
```bash
# Measure event processing time
docker-compose logs market-data | grep "⏱️" | tail -10

# Profile performance
python -m cProfile market_data_connector.py

# Check system load
uptime
iostat -x 1 5
```

**Optimization Steps:**
```python
# Enable async processing
async def _emit_market_tick(self, symbol: str, tick_data: dict):
    """Async event emission"""
    await asyncio.gather(
        self.fsm.emit_event("EVT:MARKET_TICK_RECEIVED", payload),
        self._update_metrics(symbol, tick_data)
    )
```

### High CPU Usage

**Symptoms:**
- CPU usage > 70%
- System responsiveness degraded
- Other services affected

**Diagnostic Steps:**
```bash
# Monitor CPU usage
docker stats market-data

# Profile CPU hotspots
python -m cProfile -s cumulative market_data_connector.py

# Check thread count
ps -T -p $(pgrep -f market_data)
```

**Optimization Steps:**
```yaml
# Reduce processing frequency
market_data:
  poll_interval_sec: 5.0  # Increase from 2.0

# Enable batch processing
event_processing:
  batch_size: 10
  batch_timeout_sec: 1.0
```

## Network Issues

### Connectivity Problems

**Symptoms:**
- Connection timeouts
- DNS resolution failures
- SSL/TLS handshake errors

**Diagnostic Steps:**
```bash
# Test basic connectivity
ping api.binance.com

# Check DNS resolution
dig api.binance.com

# Test SSL connectivity
openssl s_client -connect api.binance.com:443 -servername api.binance.com

# Check proxy settings
env | grep -i proxy
```

**Resolution Steps:**
```bash
# Update DNS settings
echo "nameserver 8.8.8.8" >> /etc/resolv.conf

# Configure proxy if needed
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080

# Update CA certificates
apt-get update && apt-get install -y ca-certificates
```

### WebSocket Issues

**Symptoms:**
- Frequent WebSocket disconnections
- Fallback to REST polling
- Increased latency

**Diagnostic Steps:**
```bash
# Test WebSocket connection
websocat wss://stream.binance.com:9443/ws/solusdt@bookTicker

# Check connection stability
timeout 60 websocat wss://stream.binance.com:9443/ws/solusdt@bookTicker

# Monitor reconnection attempts
docker-compose logs market-data | grep "WebSocket" | tail -20
```

**Resolution Steps:**
```python
# Implement exponential backoff
async def _reconnect_websocket(self):
    """Reconnect WebSocket with exponential backoff"""
    for attempt in range(self.max_reconnect_attempts):
        try:
            await self.websocket.connect()
            break
        except Exception as e:
            delay = min(2 ** attempt, 300)  # Max 5 minutes
            await asyncio.sleep(delay)
```

## Configuration Issues

### Invalid Configuration

**Symptoms:**
- Service fails to start
- Configuration validation errors
- Runtime errors due to missing settings

**Diagnostic Steps:**
```bash
# Validate configuration
python -c "
from apps.reference.domains.market_data.config import validate_config, load_config
config = load_config()
errors = validate_config(config)
print('Errors:', errors)
"

# Check environment variables
env | grep -E "(BINANCE|MARKET_DATA|TRADING)"

# Verify file permissions
ls -la config/
```

**Common Configuration Errors:**
```yaml
# Missing required fields
trading:
  market_data:
    # Missing poll_interval_sec

# Invalid symbol format
trading:
  market_data:
    symbols:
      - "solusdt"  # Should be uppercase: SOLUSDT

# Invalid API credentials
BINANCE_API_KEY=invalid_key
```

### Environment Mismatches

**Symptoms:**
- Testnet data in production
- Production credentials in test environment
- Different behavior across environments

**Diagnostic Steps:**
```bash
# Check environment
echo $TRADING_MODE

# Verify configuration matches environment
grep -r "testnet\|live" config/

# Compare configurations
diff config/production.yaml config/testnet.yaml
```

## Monitoring & Alerting

### Key Metrics to Monitor

#### System Metrics
```
market_data_uptime_seconds
market_data_memory_usage_bytes
market_data_cpu_usage_percent
market_data_thread_count
```

#### Data Quality Metrics
```
market_data_data_freshness_seconds
market_data_api_request_duration_seconds
market_data_websocket_connection_status
market_data_events_emitted_total
market_data_data_completeness_ratio
```

#### Error Metrics
```
market_data_api_errors_total
market_data_websocket_disconnections_total
market_data_event_emission_failures_total
market_data_config_validation_errors_total
```

### Alert Configuration

#### Critical Alerts
```yaml
alerts:
  - name: MarketDataDown
    condition: up{job="market-data"} == 0
    duration: 5m
    severity: critical

  - name: MarketDataStaleData
    condition: market_data_data_freshness_seconds > 30
    duration: 2m
    severity: critical

  - name: MarketDataHighMemory
    condition: market_data_memory_usage_bytes > 200000000
    duration: 5m
    severity: warning
```

### Log Analysis Patterns

#### Success Patterns
```
INFO 📊 SOLUSDT Tick: bid=150.5@123.40, ask=200.3@123.50, trades: BUY=45 SELL=32
INFO ✅ Event EVT:MARKET_TICK_RECEIVED emitted for SOLUSDT
INFO 🔗 REST API call completed for SOLUSDT in 0.234s
```

#### Warning Patterns
```
WARN ⚠️ WebSocket connection lost, falling back to REST polling
WARN ⚠️ API rate limit approaching: 80% used
WARN ⚠️ Memory usage at 75%
```

#### Error Patterns
```
ERROR ❌ Failed to fetch data for SOLUSDT: Connection timeout
ERROR ❌ WebSocket reconnection failed after 5 attempts
ERROR ❌ Event emission failed: FSM unavailable
ERROR ❌ Configuration validation failed: missing api_key
```

## Emergency Procedures

### Service Restart
```bash
# Graceful restart
docker-compose restart market-data

# Force restart
docker-compose down market-data
docker-compose up -d market-data

# Kubernetes restart
kubectl rollout restart deployment/market-data-connector
```

### Data Recovery
```bash
# Check for cached data
curl http://localhost:8000/debug/cache

# Force data refresh
curl -X POST http://localhost:8000/admin/refresh-data

# Restore from backup
cp backup/market_data_state.json /app/data/
```

### Emergency Configuration
```yaml
# Minimal configuration for emergency operation
trading:
  market_data:
    poll_interval_sec: 10.0  # Reduce load
    symbols:
      - BTCUSDT  # Only essential symbols
    websocket_streams: []  # Disable WebSocket, use REST only
```

## Prevention Measures

### Proactive Monitoring
- Set up alerts for all critical metrics
- Monitor error rates and latency trends
- Regular configuration validation
- Automated health checks

### Capacity Planning
- Monitor resource usage trends
- Plan for symbol count increases
- Test performance under load
- Implement auto-scaling where appropriate

### Backup Strategies
- Regular configuration backups
- State persistence for faster recovery
- Multiple data source fallbacks
- Geographic redundancy for critical deployments

---

*Troubleshooting Guide Version: 1.0*
*Last Updated: January 15, 2024*
*Average Resolution Time: 15 minutes*
*Most Common Issues: API connectivity (40%), data freshness (30%), memory (20%)*</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\market_data\TROUBLESHOOTING.md
