# Position Tracking Domain - Deployment Guide

## Overview

This guide covers the deployment procedures for the position_tracking domain in the QuantumTraderX system. The domain serves as the central portfolio state management component with critical requirements for data durability and consistency.

## Prerequisites

### System Requirements

#### Hardware Requirements
- **CPU**: 2+ cores (minimum), 4+ cores (recommended)
- **Memory**: 512MB minimum, 1GB recommended
- **Storage**: 10GB minimum (for WAL logs and snapshots)
- **Network**: 100Mbps minimum, 1Gbps recommended

#### Software Dependencies
- **Python**: 3.9+ with decimal module
- **vFoundation**: Latest stable version
- **Redis**: 6.0+ (for WAL persistence)
- **Binance API**: Valid API credentials with trading permissions

### Network Configuration

#### Required Ports
- **Redis**: 6379 (WAL storage)
- **Internal Events**: FSM message bus (configured via vFoundation)
- **Monitoring**: 9090 (Prometheus metrics, optional)

#### Firewall Rules
```
Inbound:
- Redis port (6379) from application servers
- Monitoring port (9090) from monitoring systems

Outbound:
- Binance API endpoints (api.binance.com, testnet.binance.vision)
- NTP servers (for time synchronization)
```

## Configuration

### Environment Variables

#### Required Configuration
```bash
# vFoundation Configuration
VFOUNDATION_WORKER_ID=position_tracking_01
VFOUNDATION_ENVIRONMENT=production
VFOUNDATION_CONFIG_PATH=/etc/quantumtraderx/config

# Redis Configuration
REDIS_HOST=redis-cluster.internal
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_DB=1

# Binance API Configuration
BINANCE_API_KEY=${BINANCE_API_KEY}
BINANCE_API_SECRET=${BINANCE_API_SECRET}
BINANCE_TESTNET=false

# Domain-Specific Configuration
POSITION_TRACKING_LEVERAGE_DEFAULT=5.0
POSITION_TRACKING_WAL_TIMEOUT_MS=5000
POSITION_TRACKING_SNAPSHOT_INTERVAL_MINUTES=60
```

#### Optional Configuration
```bash
# Monitoring Configuration
METRICS_ENABLED=true
METRICS_PORT=9090
HEALTH_CHECK_ENABLED=true

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/quantumtraderx/position_tracking.log

# Performance Tuning
MAX_CONCURRENT_EVENTS=100
EVENT_PROCESSING_TIMEOUT_MS=10000
```

### Configuration Files

#### Master Configuration (YAML)
```yaml
# /etc/quantumtraderx/config/master_config_v1.yaml
position_tracking:
  leverage_defaults:
    BTCUSDT: 5.0
    ETHUSDT: 4.0
    default: 3.0

  wal:
    timeout_ms: 5000
    retry_attempts: 3
    lock_timeout_ms: 30000

  snapshots:
    interval_minutes: 60
    retention_days: 30
    compression: true

  monitoring:
    metrics_enabled: true
    health_checks_enabled: true
    alert_thresholds:
      latency_p95_ms: 100
      error_rate_percent: 1.0
      wal_failure_count: 5
```

## Installation

### Package Installation

#### Using pip (Recommended)
```bash
# Install from requirements.txt
pip install -r requirements.txt

# Or install specific version
pip install quantumtraderx-position-tracking==1.0.0
```

#### Using Docker
```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app
WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 9090
CMD ["python", "-m", "apps.reference.domains.position_tracking"]
```

### Directory Structure

#### Production Layout
```
/opt/quantumtraderx/
├── apps/
│   └── reference/
│       └── domains/
│           └── position_tracking/
│               ├── position_tracking.py
│               └── __init__.py
├── config/
│   ├── master_config_v1.yaml
│   └── schemas/
├── logs/
│   └── position_tracking.log
├── data/
│   ├── wal/
│   └── snapshots/
└── scripts/
    ├── deploy.sh
    └── health_check.sh
```

## Deployment Strategies

### Blue-Green Deployment

#### Preparation
```bash
# Create blue environment
kubectl create namespace position-tracking-blue

# Deploy blue version
helm upgrade --install position-tracking-blue ./charts/position-tracking \
  --namespace position-tracking-blue \
  --set image.tag=v1.0.0 \
  --set environment=blue

# Wait for readiness
kubectl wait --for=condition=ready pod \
  -l app=position-tracking \
  --namespace position-tracking-blue \
  --timeout=300s
```

#### Traffic Switching
```bash
# Switch service to blue
kubectl patch service position-tracking \
  --namespace production \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/selector/environment", "value": "blue"}]'

# Verify traffic switch
kubectl logs -f deployment/position-tracking \
  --namespace production \
  -l environment=blue
```

### Rolling Deployment

#### Kubernetes Manifest
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: position-tracking
  namespace: production
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  selector:
    matchLabels:
      app: position-tracking
  template:
    metadata:
      labels:
        app: position-tracking
        version: v1.0.0
    spec:
      containers:
      - name: position-tracking
        image: quantumtraderx/position-tracking:v1.0.0
        ports:
        - containerPort: 9090
          name: metrics
        envFrom:
        - configMapRef:
            name: position-tracking-config
        - secretRef:
            name: position-tracking-secrets
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 9090
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 9090
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Canary Deployment

#### Istio Configuration
```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: position-tracking
spec:
  http:
  - route:
    - destination:
        host: position-tracking
        subset: v1
      weight: 90
    - destination:
        host: position-tracking
        subset: v2
      weight: 10
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: position-tracking
spec:
  host: position-tracking
  subsets:
  - name: v1
    labels:
      version: v1.0.0
  - name: v2
    labels:
      version: v1.1.0
```

## Startup and Initialization

### Cold Start Procedure

#### 1. Pre-Startup Checks
```bash
# Verify configuration
python -c "import yaml; yaml.safe_load(open('config/master_config_v1.yaml'))"

# Test Redis connectivity
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping

# Validate Binance API credentials
python -c "
import os
from binance.client import Client
client = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET'))
print('API Key valid:', client.get_account_status())
"
```

#### 2. Initial Startup
```bash
# Start with verbose logging
POSITION_TRACKING_LOG_LEVEL=DEBUG python -m apps.reference.domains.position_tracking

# Expected startup sequence:
# 1. Configuration loaded
# 2. Redis connection established
# 3. WAL initialized
# 4. FSM event listeners registered
# 5. Ready for event processing
```

#### 3. Health Verification
```bash
# Check health endpoint
curl http://localhost:9090/health

# Verify event processing
curl http://localhost:9090/metrics | grep position_tracking_events_processed_total

# Check WAL status
curl http://localhost:9090/metrics | grep wal_operations_total
```

### Recovery Startup

#### From WAL Recovery
```bash
# Automatic recovery (default behavior)
# System will replay WAL events on startup
POSITION_TRACKING_RECOVERY_MODE=wal python -m apps.reference.domains.position_tracking

# Monitor recovery progress
tail -f /var/log/quantumtraderx/position_tracking.log | grep "recovery"
```

#### From Snapshot Recovery
```bash
# Force snapshot recovery
POSITION_TRACKING_RECOVERY_MODE=snapshot \
POSITION_TRACKING_SNAPSHOT_PATH=/data/snapshots/latest.json \
python -m apps.reference.domains.position_tracking
```

## Monitoring and Observability

### Key Metrics

#### Performance Metrics
```
position_tracking_event_processing_duration_seconds
position_tracking_events_processed_total
position_tracking_wal_write_duration_seconds
position_tracking_portfolio_emit_duration_seconds
```

#### Health Metrics
```
position_tracking_redis_connection_status
position_tracking_wal_health_status
position_tracking_binance_api_status
position_tracking_uptime_seconds
```

#### Business Metrics
```
position_tracking_active_positions_total
position_tracking_portfolio_value_usd
position_tracking_realized_pnl_usd
position_tracking_margin_used_percent
```

### Alert Configuration

#### Critical Alerts
```yaml
# Prometheus Alert Rules
groups:
- name: position_tracking_critical
  rules:
  - alert: PositionTrackingDown
    expr: up{job="position_tracking"} == 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Position tracking service is down"

  - alert: WALWriteFailures
    expr: rate(position_tracking_wal_write_errors_total[5m]) > 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "WAL write failures detected"
```

#### Warning Alerts
```yaml
- alert: HighLatency
  expr: histogram_quantile(0.95, rate(position_tracking_event_processing_duration_seconds_bucket[5m])) > 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Position tracking latency above threshold"

- alert: RedisConnectionIssues
  expr: position_tracking_redis_connection_status == 0
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "Redis connection lost"
```

### Logging Configuration

#### Structured Logging
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "service": "position_tracking",
  "worker_id": "position_tracking_01",
  "correlation_id": "evt_123456789",
  "event_type": "TRADE_EXECUTED",
  "symbol": "BTCUSDT",
  "quantity": "0.001",
  "price": "45000.00",
  "pnl_realized": "2.50",
  "processing_time_ms": 8.5
}
```

#### Log Aggregation
```yaml
# Fluentd Configuration
<source>
  @type tail
  path /var/log/quantumtraderx/position_tracking.log
  pos_file /var/log/fluentd/position_tracking.pos
  tag position_tracking
  <parse>
    @type json
  </parse>
</source>

<match position_tracking>
  @type elasticsearch
  host elasticsearch.internal
  port 9200
  index_name quantumtraderx-position-tracking
  logstash_format true
</match>
```

## Backup and Recovery

### WAL Backup Strategy

#### Continuous Backup
```bash
# WAL files backup (every 15 minutes)
*/15 * * * * rsync -av /data/wal/ /backup/wal/

# Retention policy (keep 7 days)
0 2 * * * find /backup/wal/ -type f -mtime +7 -delete
```

#### Snapshot Backup
```bash
# Daily snapshots
0 1 * * * python -c "
from apps.reference.domains.position_tracking import PositionTracking
pt = PositionTracking()
pt.create_snapshot('/backup/snapshots/daily_$(date +\%Y\%m\%d).json')
"

# Weekly full backup
0 3 * * 0 rsync -av /data/ /backup/full/
```

### Disaster Recovery

#### Recovery Time Objectives
- **RTO**: 15 minutes (snapshot loading + reconciliation)
- **RPO**: 0 seconds (WAL guarantees no data loss)

#### Recovery Procedure
```bash
# 1. Stop affected instance
kubectl scale deployment position-tracking --replicas=0

# 2. Restore from latest snapshot
cp /backup/snapshots/latest.json /data/snapshot_recovery.json

# 3. Start with recovery mode
POSITION_TRACKING_RECOVERY_MODE=snapshot \
POSITION_TRACKING_SNAPSHOT_PATH=/data/snapshot_recovery.json \
kubectl scale deployment position-tracking --replicas=3

# 4. Verify recovery
kubectl logs -f deployment/position-tracking | grep "recovery.*completed"
```

## Scaling and Performance

### Horizontal Scaling

#### Kubernetes HPA Configuration
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: position-tracking-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: position-tracking
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Custom
    custom:
      metric:
        name: position_tracking_event_processing_duration_seconds
      target:
        type: Value
        value: 50m
```

### Performance Tuning

#### JVM Tuning (if applicable)
```bash
# Python GIL considerations
export PYTHONOPTIMIZE=1
export PYTHONPATH=/opt/quantumtraderx

# Memory tuning
export MALLOC_ARENA_MAX=2
```

#### Database Tuning
```redis.conf
# Redis configuration for WAL
maxmemory 1gb
maxmemory-policy allkeys-lru
tcp-keepalive 300
timeout 300
```

## Troubleshooting

### Common Issues

#### High Latency
**Symptoms**: Event processing > 100ms p95
**Diagnosis**:
```bash
# Check Redis performance
redis-cli --latency

# Monitor WAL writes
curl http://localhost:9090/metrics | grep wal_write_duration

# Check system resources
top -p $(pgrep -f position_tracking)
```

**Resolution**:
```bash
# Scale horizontally
kubectl scale deployment position-tracking --replicas=5

# Optimize Redis
redis-cli config set maxmemory-policy volatile-lru
```

#### WAL Write Failures
**Symptoms**: WAL write errors in logs
**Diagnosis**:
```bash
# Check Redis connectivity
redis-cli ping

# Verify disk space
df -h /data

# Check Redis memory
redis-cli info memory
```

**Resolution**:
```bash
# Restart Redis if needed
kubectl rollout restart deployment/redis

# Clear WAL backlog
redis-cli flushdb

# Scale storage if needed
kubectl patch pvc wal-storage -p '{"spec":{"resources":{"requests":{"storage":"50Gi"}}}}'
```

#### Memory Issues
**Symptoms**: OOM kills, high memory usage
**Diagnosis**:
```bash
# Check memory usage
kubectl top pods -l app=position-tracking

# Monitor position count
curl http://localhost:9090/metrics | grep active_positions
```

**Resolution**:
```bash
# Increase memory limits
kubectl patch deployment position-tracking \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"position-tracking","resources":{"limits":{"memory":"2Gi"}}}]}}}}'

# Implement position cleanup
# (Check code for position cleanup logic)
```

### Debug Commands

#### Health Check Script
```bash
#!/bin/bash
# health_check.sh

ENDPOINT="http://localhost:9090"

# Health check
if ! curl -f "${ENDPOINT}/health" > /dev/null 2>&1; then
    echo "Health check failed"
    exit 1
fi

# Metrics check
if ! curl -f "${ENDPOINT}/metrics" > /dev/null 2>&1; then
    echo "Metrics check failed"
    exit 1
fi

# Event processing check
EVENTS=$(curl -s "${ENDPOINT}/metrics" | grep position_tracking_events_processed_total | awk '{print $2}')
if [ "$EVENTS" -lt 1 ]; then
    echo "No events processed"
    exit 1
fi

echo "All checks passed"
```

#### Log Analysis
```bash
# Error analysis
grep "ERROR" /var/log/quantumtraderx/position_tracking.log | tail -10

# Performance analysis
grep "processing_time_ms" /var/log/quantumtraderx/position_tracking.log | \
  awk '{sum+=$NF; count++} END {print "Average:", sum/count, "ms"}'

# Event type distribution
grep "event_type" /var/log/quantumtraderx/position_tracking.log | \
  sed 's/.*event_type":"\([^"]*\)".*/\1/' | sort | uniq -c | sort -nr
```

## Security Considerations

### API Key Management
```bash
# Use Kubernetes secrets
kubectl create secret generic binance-api \
  --from-literal=api-key=$BINANCE_API_KEY \
  --from-literal=api-secret=$BINANCE_API_SECRET

# Mount as environment variables
env:
- name: BINANCE_API_KEY
  valueFrom:
    secretKeyRef:
      name: binance-api
      key: api-key
- name: BINANCE_API_SECRET
  valueFrom:
    secretKeyRef:
      name: binance-api
      key: api-secret
```

### Network Security
```yaml
# Network Policy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: position-tracking-netpol
spec:
  podSelector:
    matchLabels:
      app: position-tracking
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: quantumtraderx
    ports:
    - protocol: TCP
      port: 9090
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
  - to: []
    ports:
    - protocol: TCP
      port: 443  # HTTPS for Binance API
```

## Maintenance Procedures

### Regular Maintenance

#### Daily Checks
```bash
# Log rotation
logrotate /etc/logrotate.d/position_tracking

# WAL cleanup (remove old entries)
redis-cli --scan --pattern "wal:*" | xargs redis-cli del

# Snapshot cleanup
find /data/snapshots/ -name "*.json" -mtime +30 -delete
```

#### Weekly Maintenance
```bash
# Full backup verification
python -c "
import json
with open('/backup/snapshots/latest.json') as f:
    snapshot = json.load(f)
    print(f'Positions: {len(snapshot[\"positions\"])}')
    print(f'Valid: {snapshot[\"metadata\"][\"integrity_hash\"] is not None}')
"

# Performance benchmark
ab -n 1000 -c 10 http://localhost:9090/health
```

#### Monthly Maintenance
```bash
# Security updates
pip install --upgrade quantumtraderx-position-tracking

# Configuration review
diff config/master_config_v1.yaml config/master_config_v1.yaml.backup

# Capacity planning
kubectl top nodes
kubectl describe pvc wal-storage
```

### Emergency Procedures

#### Service Outage
1. **Assess Impact**: Check affected trading operations
2. **Failover**: Switch to backup instance if available
3. **Recovery**: Follow disaster recovery procedure
4. **Post-Mortem**: Analyze root cause and update procedures

#### Data Corruption
1. **Isolate**: Stop all position tracking instances
2. **Assess**: Verify WAL and snapshot integrity
3. **Recover**: Use latest valid snapshot + WAL replay
4. **Validate**: Cross-check with exchange account data

---

*Deployment Guide Version: 1.0*
*Last Updated: January 15, 2024*
*Review Required: Quarterly*</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\position_tracking\DEPLOYMENT.md
