# Execution Position Domain - Troubleshooting Guide

## Overview

This guide provides systematic troubleshooting procedures for common issues in the execution_position domain. Follow the diagnostic flowcharts and use the provided tools for efficient problem resolution.

## Diagnostic Tools

### Health Check Script
```python
#!/usr/bin/env python3
# scripts/health_check.py

import requests
import time
from typing import Dict, List

def check_service_health() -> Dict[str, bool]:
    """Comprehensive health check"""
    results = {}

    # Service availability
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        results["service_up"] = response.status_code == 200
    except:
        results["service_up"] = False

    # API connectivity
    try:
        response = requests.get("http://localhost:8080/debug/api_status", timeout=5)
        results["api_connected"] = response.json().get("connected", False)
    except:
        results["api_connected"] = False

    # FSM health
    try:
        response = requests.get("http://localhost:8080/debug/fsm_status", timeout=5)
        fsm_data = response.json()
        results["fsm_healthy"] = all(
            fsm.get("state") == "active"
            for fsm in fsm_data.get("fsms", [])
        )
    except:
        results["fsm_healthy"] = False

    return results

if __name__ == "__main__":
    health = check_service_health()
    print("Health Status:")
    for check, status in health.items():
        print(f"  {check}: {'✓' if status else '✗'}")
```

### Log Analysis Script
```python
#!/usr/bin/env python3
# scripts/analyze_logs.py

import re
import sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta

def analyze_recent_logs(hours: int = 1) -> Dict[str, any]:
    """Analyze recent log entries for patterns"""

    # Read log file
    with open("logs/execution_position.log", "r") as f:
        lines = f.readlines()

    # Filter recent entries
    cutoff = datetime.now() - timedelta(hours=hours)
    recent_lines = []

    for line in lines:
        try:
            # Extract timestamp (assuming format: 2024-01-15 10:30:45)
            timestamp_str = line[:19]
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            if timestamp > cutoff:
                recent_lines.append(line)
        except:
            continue

    # Analyze patterns
    analysis = {
        "total_lines": len(recent_lines),
        "errors": [],
        "warnings": [],
        "timeouts": 0,
        "orders_processed": 0,
        "api_calls": 0
    }

    for line in recent_lines:
        if "ERROR" in line:
            analysis["errors"].append(line.strip())
        elif "WARNING" in line:
            analysis["warnings"].append(line.strip())
        elif "timeout" in line.lower():
            analysis["timeouts"] += 1
        elif "CMD:OPEN" in line or "CMD:CLOSE" in line:
            analysis["orders_processed"] += 1
        elif "api" in line.lower():
            analysis["api_calls"] += 1

    return analysis

if __name__ == "__main__":
    analysis = analyze_recent_logs()
    print(f"Log Analysis (last hour):")
    print(f"  Total lines: {analysis['total_lines']}")
    print(f"  Errors: {len(analysis['errors'])}")
    print(f"  Warnings: {len(analysis['warnings'])}")
    print(f"  Timeouts: {analysis['timeouts']}")
    print(f"  Orders processed: {analysis['orders_processed']}")
    print(f"  API calls: {analysis['api_calls']}")
```

## Issue Resolution Flowcharts

### Issue 1: Service Not Starting

```
START
  ↓
Check Python version (3.9+)
  ↓
Validate configuration file
  ↓
Check dependencies installed
  ↓
Review startup logs for errors
  ↓
Test individual components
  ↓
Check system resources
  ↓
END
```

**Diagnostic Steps**:

1. **Python Version Check**
   ```bash
   python --version
   # Should be 3.9 or higher
   ```

2. **Configuration Validation**
   ```bash
   python -c "
   from config import load_config
   try:
       config = load_config('config/master_config_v1.yaml')
       print('Configuration valid')
   except Exception as e:
       print(f'Configuration error: {e}')
   "
   ```

3. **Dependency Check**
   ```bash
   python -c "
   try:
       import apps.reference.domains.execution_position.fsm
       import vfoundation
       print('Dependencies OK')
   except ImportError as e:
       print(f'Missing dependency: {e}')
   "
   ```

4. **Resource Check**
   ```bash
   # Memory
   wmic OS get FreePhysicalMemory /Value

   # Disk space
   dir C:\
   ```

### Issue 2: Orders Not Executing

```
START
  ↓
Check API connectivity
  ↓
Validate API credentials
  ↓
Review exposure limits
  ↓
Check order parameters
  ↓
Monitor execution logs
  ↓
Test manual order placement
  ↓
END
```

**Diagnostic Steps**:

1. **API Connectivity Test**
   ```bash
   python -c "
   import asyncio
   from apps.reference.domains.execution_position.binance_execution_adapter import BinanceAdapter

   async def test():
       adapter = BinanceAdapter()
       status = await adapter.get_status()
       print(f'API Status: {status}')

   asyncio.run(test())
   "
   ```

2. **Credential Validation**
   ```bash
   # Test API key permissions
   curl -H 'X-MBX-APIKEY: YOUR_API_KEY' \
        'https://testnet.binance.vision/api/v3/account'
   ```

3. **Exposure Check**
   ```bash
   curl http://localhost:8080/debug/exposure_levels
   ```

4. **Order Parameter Validation**
   ```python
   # Test order validation
   from apps.reference.domains.execution_position.exposure_guard import ExposureGuard

   guard = ExposureGuard()
   result = guard.can_open('BTCUSDT', 'BUY', '0.001', '50000')
   print(f'Order allowed: {result}')
   ```

### Issue 3: High Latency

```
START
  ↓
Measure current latency
  ↓
Check network connectivity
  ↓
Profile code execution
  ↓
Review async operations
  ↓
Check resource utilization
  ↓
Optimize bottlenecks
  ↓
END
```

**Diagnostic Steps**:

1. **Latency Measurement**
   ```bash
   # Use curl timing
   curl -w "@curl-format.txt" -o /dev/null http://localhost:8080/health

   # curl-format.txt
   # %{time_total}\n
   ```

2. **Network Diagnostics**
   ```bash
   # Ping test
   ping testnet.binance.vision

   # Traceroute
   tracert testnet.binance.vision
   ```

3. **Code Profiling**
   ```python
   import cProfile
   import pstats

   def profile_execution():
       # Your code here
       pass

   cProfile.run('profile_execution()', 'profile.stats')
   p = pstats.Stats('profile.stats')
   p.sort_stats('cumulative').print_stats(10)
   ```

4. **Resource Monitoring**
   ```bash
   # CPU usage
   wmic cpu get loadpercentage

   # Memory usage
   wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value
   ```

## Common Error Patterns

### Pattern 1: Connection Refused
**Error**: `ConnectionError: [Errno 111] Connection refused`

**Causes**:
- Service not running
- Wrong port configuration
- Firewall blocking

**Resolution**:
```bash
# Check if service is running
netstat -ano | findstr :8080

# Check firewall
netsh advfirewall firewall show rule name=all | findstr 8080

# Test connectivity
telnet localhost 8080
```

### Pattern 2: API Rate Limits
**Error**: `HTTP 429 Too Many Requests`

**Causes**:
- High frequency trading
- Insufficient rate limit configuration
- API key restrictions

**Resolution**:
```python
# Implement exponential backoff
import asyncio
import random

async def api_call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if "429" in str(e):
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(wait_time)
            else:
                raise
    raise Exception("Max retries exceeded")
```

### Pattern 3: State Inconsistency
**Error**: `AssertionError: Position state mismatch`

**Causes**:
- Race conditions
- Event ordering issues
- State corruption

**Resolution**:
```python
# Add state validation
def validate_state_consistency():
    """Check FSM state against external sources"""
    # Compare internal state with exchange state
    # Reconcile discrepancies
    # Log inconsistencies for analysis
    pass

# Implement state snapshots
def create_state_snapshot():
    """Create point-in-time state backup"""
    # Serialize current state
    # Store with timestamp
    # Enable rollback capability
    pass
```

### Pattern 4: Memory Leaks
**Symptoms**: Gradually increasing memory usage, eventual OOM

**Causes**:
- Unclosed connections
- Accumulating event queues
- Large data structures not cleaned up

**Resolution**:
```python
# Memory profiling
import tracemalloc

tracemalloc.start()

# Your code here

current, peak = tracemalloc.get_traced_memory()
print(f"Current memory usage: {current / 1024 / 1024:.1f} MB")
print(f"Peak memory usage: {peak / 1024 / 1024:.1f} MB")

# Get top memory consumers
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

## Automated Diagnostics

### System Health Dashboard
```python
#!/usr/bin/env python3
# scripts/system_dashboard.py

import time
import psutil
import requests
from typing import Dict

class SystemDashboard:
    def __init__(self):
        self.metrics = {}

    def collect_system_metrics(self) -> Dict[str, float]:
        """Collect system-level metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "network_connections": len(psutil.net_connections())
        }

    def collect_service_metrics(self) -> Dict[str, any]:
        """Collect service-specific metrics"""
        try:
            response = requests.get("http://localhost:9090/metrics", timeout=5)
            # Parse Prometheus metrics
            return self.parse_prometheus_metrics(response.text)
        except:
            return {"service_metrics_error": True}

    def check_alerts(self) -> List[str]:
        """Check for alert conditions"""
        alerts = []

        system = self.collect_system_metrics()
        service = self.collect_service_metrics()

        # CPU alert
        if system.get("cpu_percent", 0) > 80:
            alerts.append("High CPU usage")

        # Memory alert
        if system.get("memory_percent", 0) > 85:
            alerts.append("High memory usage")

        # Service alerts
        if service.get("service_metrics_error"):
            alerts.append("Cannot collect service metrics")

        return alerts

    def run_continuous_monitoring(self):
        """Run continuous monitoring loop"""
        while True:
            alerts = self.check_alerts()
            if alerts:
                print(f"ALERTS: {alerts}")

            time.sleep(60)  # Check every minute

if __name__ == "__main__":
    dashboard = SystemDashboard()
    dashboard.run_continuous_monitoring()
```

## Recovery Procedures

### Emergency Stop
```bash
#!/bin/bash
# scripts/emergency_stop.sh

echo "Initiating emergency stop..."

# Cancel all pending orders
curl -X POST http://localhost:8080/admin/cancel_all_orders

# Close all positions
curl -X POST http://localhost:8080/admin/close_all_positions

# Shutdown service gracefully
curl -X POST http://localhost:8080/admin/shutdown

# Wait for cleanup
sleep 10

# Force kill if still running
pkill -f execution_position

echo "Emergency stop complete"
```

### State Recovery
```python
#!/usr/bin/env python3
# scripts/state_recovery.py

import json
import os
from datetime import datetime

def recover_from_backup(backup_file: str):
    """Recover state from backup file"""
    print(f"Recovering from backup: {backup_file}")

    # Load backup
    with open(backup_file, 'r') as f:
        backup_data = json.load(f)

    # Validate backup integrity
    if not validate_backup(backup_data):
        raise ValueError("Backup validation failed")

    # Restore state
    # Note: Implementation depends on state management system
    restore_state(backup_data)

    print("State recovery complete")

def create_backup():
    """Create current state backup"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backups/state_backup_{timestamp}.json"

    # Collect current state
    state_data = collect_current_state()

    # Write backup
    os.makedirs("backups", exist_ok=True)
    with open(backup_file, 'w') as f:
        json.dump(state_data, f, indent=2)

    print(f"Backup created: {backup_file}")
    return backup_file
```

## Prevention Measures

### Proactive Monitoring
```python
# Implement circuit breaker pattern
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"

    def call(self, func):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e

    def on_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
```

### Automated Testing
```bash
# Integration test script
#!/bin/bash
# scripts/integration_test.sh

echo "Running integration tests..."

# Health check
if ! curl -f http://localhost:8080/health; then
    echo "Service health check failed"
    exit 1
fi

# API connectivity
if ! python scripts/test_api_connectivity.py; then
    echo "API connectivity test failed"
    exit 1
fi

# Order placement test
if ! python scripts/test_order_placement.py; then
    echo "Order placement test failed"
    exit 1
fi

echo "All integration tests passed"
```

### Log Rotation and Retention
```bash
# Logrotate configuration
cat > /etc/logrotate.d/execution_position << EOF
/app/logs/execution_position.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 app app
    postrotate
        systemctl reload execution-position
    endscript
}
EOF
```

## Support Information

### Log Collection for Support
```bash
#!/bin/bash
# scripts/collect_support_logs.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SUPPORT_DIR="support_logs_$TIMESTAMP"

mkdir -p $SUPPORT_DIR

# System information
uname -a > $SUPPORT_DIR/system_info.txt
python --version > $SUPPORT_DIR/python_version.txt
pip list > $SUPPORT_DIR/pip_packages.txt

# Configuration (redact sensitive data)
cp config/master_config_v1.yaml $SUPPORT_DIR/
# TODO: Add redaction logic

# Recent logs
tail -1000 logs/execution_position.log > $SUPPORT_DIR/recent_logs.log

# Metrics snapshot
curl http://localhost:9090/metrics > $SUPPORT_DIR/metrics_snapshot.txt 2>/dev/null

# Create archive
tar -czf ${SUPPORT_DIR}.tar.gz $SUPPORT_DIR
rm -rf $SUPPORT_DIR

echo "Support logs collected: ${SUPPORT_DIR}.tar.gz"
```

### Escalation Matrix
- **Level 1**: Service restart, configuration check
- **Level 2**: Code review, dependency updates
- **Level 3**: Database recovery, infrastructure changes
- **Level 4**: Full system rebuild, vendor support

### Contact Information
- **Development Team**: dev@quantumtraderx.com
- **Operations**: ops@quantumtraderx.com
- **Security**: security@quantumtraderx.com</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\TROUBLESHOOTING.md
