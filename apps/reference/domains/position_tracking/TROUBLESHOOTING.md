# Position Tracking Domain - Troubleshooting Guide

## Overview

This guide provides diagnostic procedures and resolution steps for common issues in the position_tracking domain. The domain handles critical portfolio state management, so troubleshooting focuses on data consistency, performance, and reliability.

## Quick Reference

### Emergency Contacts
- **On-Call Engineer**: +1-555-0123 (24/7)
- **DevOps Team**: devops@quantumtraderx.com
- **Security Team**: security@quantumtraderx.com

### Critical Alerts
- WAL write failures
- Position data inconsistency
- High latency (>100ms p95)
- Service unavailability

## Diagnostic Tools

### Health Check Endpoints

#### Basic Health Check
```bash
curl -v http://localhost:9090/health
# Expected: HTTP 200 with {"status": "healthy"}
```

#### Readiness Check
```bash
curl -v http://localhost:9090/ready
# Expected: HTTP 200 with {"status": "ready", "checks": {...}}
```

#### Metrics Endpoint
```bash
curl http://localhost:9090/metrics | grep position_tracking
# Key metrics to monitor:
# - position_tracking_uptime_seconds
# - position_tracking_events_processed_total
# - position_tracking_wal_write_errors_total
```

### Log Analysis Tools

#### Real-time Log Monitoring
```bash
# Follow logs with correlation ID filtering
tail -f /var/log/quantumtraderx/position_tracking.log | jq 'select(.correlation_id == "evt_12345")'

# Error analysis
grep "ERROR\|CRITICAL" /var/log/quantumtraderx/position_tracking.log | tail -20

# Performance analysis
grep "processing_time_ms" /var/log/quantumtraderx/position_tracking.log | \
  awk '{print $NF}' | sort -n | tail -10
```

#### Log Pattern Analysis
```bash
# Event processing bottlenecks
grep "event_type.*TRADE_EXECUTED" /var/log/quantumtraderx/position_tracking.log | \
  jq -r '.processing_time_ms' | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count, "ms"}'

# WAL failure patterns
grep "WAL.*failed" /var/log/quantumtraderx/position_tracking.log | \
  jq -r '.error' | sort | uniq -c | sort -nr
```

### Database Inspection

#### Redis WAL Inspection
```bash
# Check WAL entries
redis-cli keys "wal:*" | head -10

# Inspect specific WAL entry
redis-cli get wal:evt_12345

# WAL queue length
redis-cli llen wal_queue

# Check Redis memory usage
redis-cli info memory | grep used_memory_human
```

#### Snapshot Validation
```bash
# Validate snapshot integrity
python -c "
import json
import hashlib

with open('/data/snapshots/latest.json', 'r') as f:
    snapshot = json.load(f)

data_hash = hashlib.sha256(json.dumps(snapshot['data'], sort_keys=True).encode()).hexdigest()
stored_hash = snapshot['metadata']['integrity_hash']

print(f'Data hash: {data_hash}')
print(f'Stored hash: {stored_hash}')
print(f'Valid: {data_hash == stored_hash}')
"
```

## Common Issues and Solutions

### Issue 1: High Event Processing Latency

#### Symptoms
- Event processing > 100ms p95
- Queue backlog growing
- Trading decisions delayed

#### Diagnosis
```bash
# Check system resources
top -p $(pgrep -f position_tracking) -b -n 1

# Monitor Redis performance
redis-cli --latency-history

# Check event queue depth
curl http://localhost:9090/metrics | grep queue_depth

# Analyze slow events
grep "processing_time_ms.*[0-9]\{3,\}" /var/log/quantumtraderx/position_tracking.log | tail -5
```

#### Root Causes
1. **Redis Connection Issues**: Network latency or Redis overload
2. **Memory Pressure**: Insufficient RAM causing swapping
3. **Lock Contention**: WAL write timeouts
4. **Large Position Sets**: >1000 active positions

#### Solutions

##### Immediate Mitigation
```bash
# Scale horizontally
kubectl scale deployment position-tracking --replicas=5

# Restart with increased resources
kubectl set resources deployment position-tracking \
  --limits=cpu=2000m,memory=2Gi
```

##### Long-term Fixes
```yaml
# Update deployment with better resource allocation
resources:
  requests:
    cpu: 1000m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 2Gi
```

### Issue 2: WAL Write Failures

#### Symptoms
- WAL write errors in logs
- Service processing halts
- Data consistency warnings

#### Diagnosis
```bash
# Check Redis connectivity
redis-cli ping

# Verify Redis disk space
redis-cli info | grep db

# Check WAL timeout settings
grep "wal_timeout" /etc/quantumtraderx/config/master_config_v1.yaml

# Inspect failed operations
grep "WAL.*ERROR" /var/log/quantumtraderx/position_tracking.log | tail -10
```

#### Root Causes
1. **Redis Unavailable**: Network partition or Redis failure
2. **Disk Full**: WAL storage exhausted
3. **Timeout Too Low**: Network latency exceeds timeout
4. **Memory Pressure**: Redis OOM killing writes

#### Solutions

##### Emergency Recovery
```bash
# Switch to degraded mode (no WAL)
POSITION_TRACKING_WAL_ENABLED=false \
POSITION_TRACKING_DEGRADED_MODE=true \
kubectl rollout restart deployment position-tracking

# Restore Redis
kubectl rollout restart deployment/redis
```

##### Permanent Fix
```yaml
# Increase WAL timeout
position_tracking:
  wal:
    timeout_ms: 10000  # Increased from 5000
    retry_attempts: 5   # Increased from 3
```

### Issue 3: Position Data Inconsistency

#### Symptoms
- Portfolio values don't match exchange
- P&L calculations incorrect
- Risk management alerts

#### Diagnosis
```bash
# Compare with exchange data
python -c "
from binance.client import Client
import os

client = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET'))
account = client.get_account()

print('Exchange positions:')
for balance in account['balances']:
    if float(balance['free']) > 0 or float(balance['locked']) > 0:
        print(f'  {balance[\"asset\"]}: {balance[\"free\"]} free, {balance[\"locked\"]} locked')
"

# Check internal state
curl http://localhost:9090/debug/positions

# Validate P&L calculations
curl http://localhost:9090/debug/pnl_calculation
```

#### Root Causes
1. **Event Processing Gaps**: Missed trade executions
2. **Account Update Failures**: Binance API issues
3. **State Corruption**: Memory corruption or serialization errors
4. **Manual Trading**: Positions modified outside the system

#### Solutions

##### State Reconciliation
```bash
# Force account synchronization
curl -X POST http://localhost:9090/admin/reconcile \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Create manual snapshot
curl -X POST http://localhost:9090/admin/snapshot \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

##### Recovery Procedure
```bash
# 1. Stop event processing
kubectl scale deployment position-tracking --replicas=0

# 2. Clear corrupted state
redis-cli flushdb

# 3. Restore from snapshot
POSITION_TRACKING_RECOVERY_MODE=snapshot \
POSITION_TRACKING_SNAPSHOT_PATH=/backup/snapshots/known_good.json \
kubectl scale deployment position-tracking --replicas=3

# 4. Validate reconciliation
curl http://localhost:9090/debug/state_validation
```

### Issue 4: Memory Leaks

#### Symptoms
- Gradual memory increase over time
- OOM kills
- Performance degradation

#### Diagnosis
```bash
# Monitor memory usage over time
kubectl top pods -l app=position-tracking --containers

# Check position count growth
curl http://localhost:9090/metrics | grep active_positions_total

# Analyze heap dumps (if available)
jmap -histo $(pgrep -f position_tracking) | head -20

# Check for circular references
python -c "
import gc
import psutil
process = psutil.Process()
print(f'Memory usage: {process.memory_info().rss / 1024 / 1024:.1f} MB')
print(f'GC objects: {len(gc.get_objects())}')
"
```

#### Root Causes
1. **Event Accumulation**: Events not properly cleaned up
2. **Position Object Leaks**: Position objects not garbage collected
3. **Log Buffer Growth**: Unbounded log buffers
4. **Cache Issues**: Internal caches not expiring

#### Solutions

##### Memory Optimization
```python
# Add position cleanup logic
def cleanup_old_positions(self):
    cutoff = datetime.now() - timedelta(days=30)
    to_remove = [
        symbol for symbol, pos in self._positions.items()
        if pos['last_update'] < cutoff and pos['quantity'] == 0
    ]
    for symbol in to_remove:
        del self._positions[symbol]
```

##### Resource Limits
```yaml
resources:
  limits:
    memory: 1Gi
  requests:
    memory: 512Mi
```

### Issue 5: Binance API Issues

#### Symptoms
- Account update failures
- API rate limit errors
- Authentication failures

#### Diagnosis
```bash
# Check API key validity
python -c "
from binance.client import Client
import os

try:
    client = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET'))
    status = client.get_account_status()
    print(f'API Status: {status}')
except Exception as e:
    print(f'API Error: {e}')
"

# Check rate limits
curl -H 'X-MBX-APIKEY: $BINANCE_API_KEY' \
  https://api.binance.com/api/v3/account | jq .rateLimits

# Monitor API error rates
grep "binance.*error" /var/log/quantumtraderx/position_tracking.log | tail -10
```

#### Root Causes
1. **Invalid Credentials**: API keys expired or revoked
2. **Rate Limiting**: Too many API calls
3. **Network Issues**: Connectivity problems to Binance
4. **IP Restrictions**: API key IP whitelist issues

#### Solutions

##### API Configuration
```yaml
# Update API settings
binance:
  api:
    timeout: 30
    retry_attempts: 3
    rate_limit_buffer: 0.8  # Use 80% of limit
```

##### Credential Rotation
```bash
# Update Kubernetes secrets
kubectl create secret generic binance-api \
  --from-literal=api-key=$NEW_API_KEY \
  --from-literal=api-secret=$NEW_API_SECRET \
  --dry-run=client -o yaml | kubectl apply -f -

# Rollout restart
kubectl rollout restart deployment position-tracking
```

## Performance Tuning

### Latency Optimization

#### Event Processing
```python
# Optimize event batching
async def process_events_batch(self, events):
    # Process multiple events together
    with self._wal_lock:
        for event in events:
            await self._process_single_event(event)
        await self._wal.flush_batch()
```

#### Database Tuning
```redis.conf
# Redis optimization for WAL
tcp-keepalive 60
timeout 300
maxclients 10000
maxmemory 2gb
maxmemory-policy volatile-lru
```

### Memory Optimization

#### Position Cleanup
```python
def _cleanup_positions(self):
    """Remove closed positions older than threshold"""
    cutoff = datetime.now() - timedelta(days=7)
    self._positions = {
        symbol: pos for symbol, pos in self._positions.items()
        if pos['quantity'] != 0 or pos['last_update'] > cutoff
    }
```

#### Cache Management
```python
# Implement LRU cache for frequently accessed data
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_symbol_config(self, symbol):
    return self._config.get(symbol, self._config['default'])
```

## Monitoring and Alerting

### Key Metrics to Monitor

#### Performance Metrics
```
position_tracking_event_processing_duration_seconds{p95}
position_tracking_wal_write_duration_seconds
position_tracking_portfolio_emit_duration_seconds
position_tracking_memory_usage_bytes
```

#### Health Metrics
```
position_tracking_redis_connection_status
position_tracking_binance_api_status
position_tracking_wal_health_status
position_tracking_position_count_total
```

#### Business Metrics
```
position_tracking_portfolio_value_usd
position_tracking_realized_pnl_usd
position_tracking_margin_used_percent
position_tracking_active_positions_total
```

### Alert Configuration

#### Critical Alerts
```yaml
alerts:
  - name: PositionTrackingDown
    condition: up{job="position_tracking"} == 0
    duration: 5m
    severity: critical

  - name: WALWriteFailures
    condition: rate(position_tracking_wal_write_errors_total[5m]) > 0
    duration: 1m
    severity: critical

  - name: DataInconsistency
    condition: position_tracking_data_consistency_status == 0
    duration: 5m
    severity: critical
```

#### Warning Alerts
```yaml
  - name: HighLatency
    condition: histogram_quantile(0.95, rate(position_tracking_event_processing_duration_seconds_bucket[5m])) > 0.1
    duration: 5m
    severity: warning

  - name: MemoryPressure
    condition: position_tracking_memory_usage_bytes / position_tracking_memory_limit_bytes > 0.8
    duration: 10m
    severity: warning
```

## Recovery Procedures

### Standard Recovery

#### Service Restart
```bash
# Graceful restart
kubectl rollout restart deployment position-tracking

# Force restart if needed
kubectl delete pods -l app=position-tracking

# Verify recovery
kubectl wait --for=condition=ready pod -l app=position-tracking --timeout=300s
```

#### Data Recovery
```bash
# 1. Identify last good snapshot
ls -la /data/snapshots/ | tail -5

# 2. Validate snapshot
python /scripts/validate_snapshot.py /data/snapshots/latest.json

# 3. Recover from snapshot
POSITION_TRACKING_RECOVERY_MODE=snapshot \
POSITION_TRACKING_SNAPSHOT_PATH=/data/snapshots/latest.json \
kubectl set env deployment/position-tracking RECOVERY_MODE=snapshot

# 4. Monitor recovery logs
kubectl logs -f deployment/position-tracking | grep "recovery"
```

### Emergency Recovery

#### Complete System Reset
```bash
# 1. Stop all trading
kubectl scale deployment trading-engine --replicas=0

# 2. Backup current state
cp -r /data /backup/emergency_$(date +%Y%m%d_%H%M%S)

# 3. Reset Redis
redis-cli flushall

# 4. Deploy clean instance
kubectl apply -f deployment_clean.yaml

# 5. Restore from known good state
kubectl exec -it position-tracking-0 -- \
  python -c "from position_tracking import PositionTracking; pt = PositionTracking(); pt.load_snapshot('/backup/known_good.json')"

# 6. Gradual traffic resumption
kubectl scale deployment trading-engine --replicas=1
```

## Prevention Measures

### Proactive Monitoring

#### Health Checks
```bash
# Comprehensive health check script
#!/bin/bash
# comprehensive_health_check.sh

ERRORS=0

# Service health
if ! curl -f http://localhost:9090/health >/dev/null; then
    echo "Service health check failed"
    ((ERRORS++))
fi

# Database connectivity
if ! redis-cli ping >/dev/null; then
    echo "Redis connectivity failed"
    ((ERRORS++))
fi

# API connectivity
if ! curl -f https://api.binance.com/api/v3/ping >/dev/null; then
    echo "Binance API connectivity failed"
    ((ERRORS++))
fi

# Data consistency
CONSISTENCY=$(curl -s http://localhost:9090/debug/consistency | jq .consistent)
if [ "$CONSISTENCY" != "true" ]; then
    echo "Data consistency check failed"
    ((ERRORS++))
fi

if [ $ERRORS -eq 0 ]; then
    echo "All health checks passed"
    exit 0
else
    echo "$ERRORS health checks failed"
    exit 1
fi
```

#### Automated Testing
```bash
# Daily regression tests
0 2 * * * /scripts/run_regression_tests.sh

# Performance benchmarks
0 3 * * * /scripts/run_performance_tests.sh

# Data integrity checks
*/30 * * * * /scripts/check_data_integrity.sh
```

### Capacity Planning

#### Resource Monitoring
```bash
# Monitor resource usage trends
kubectl top nodes --sort-by=memory
kubectl top pods --sort-by=cpu

# Capacity planning script
#!/bin/bash
# capacity_planning.sh

CURRENT_POSITIONS=$(curl -s http://localhost:9090/metrics | grep position_tracking_active_positions_total | awk '{print $2}')
MEMORY_USAGE=$(kubectl top pods -l app=position-tracking --no-headers | awk '{print $3}' | sed 's/Mi//')

echo "Current positions: $CURRENT_POSITIONS"
echo "Memory usage: ${MEMORY_USAGE}Mi"

# Alert if approaching limits
if [ "$CURRENT_POSITIONS" -gt 800 ]; then
    echo "WARNING: Approaching position limit"
fi

if [ "$MEMORY_USAGE" -gt 800 ]; then
    echo "WARNING: High memory usage"
fi
```

## Support and Escalation

### Support Levels

#### Level 1: Basic Troubleshooting
- Service restart
- Log analysis
- Basic configuration changes
- Response time: 15 minutes

#### Level 2: Advanced Troubleshooting
- Code debugging
- Performance optimization
- Configuration tuning
- Response time: 1 hour

#### Level 3: Critical Incident
- Data recovery
- System rebuild
- Cross-team coordination
- Response time: 30 minutes

### Escalation Matrix

| Issue Severity | Initial Response | Escalation Time | Escalation Path |
|----------------|------------------|-----------------|-----------------|
| Critical | 15 minutes | 30 minutes | On-call → DevOps Lead → CTO |
| High | 30 minutes | 2 hours | DevOps Team → Engineering Lead |
| Medium | 2 hours | 1 day | Engineering Team → Product Owner |
| Low | 1 day | 1 week | Development Team |

### Documentation Updates

#### Post-Incident Review
After resolving any incident:
1. Update this troubleshooting guide with new issues/solutions
2. Add monitoring/alerts for previously unseen issues
3. Review and update runbooks
4. Conduct knowledge sharing session

#### Continuous Improvement
- Monthly review of alert effectiveness
- Quarterly capacity planning updates
- Annual disaster recovery testing
- Bi-annual architecture reviews

---

*Troubleshooting Guide Version: 1.0*
*Last Updated: January 15, 2024*
*Review Required: Monthly*</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\position_tracking\TROUBLESHOOTING.md
