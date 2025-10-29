# Aurora Core Testnet Runbook

## Overview

This runbook provides step-by-step instructions for running Aurora Core on Binance Futures Testnet. The system is designed for automated futures trading with enterprise-grade reliability features.

**RID:** `AURORA_TESTNET_RUN_V1`
**Version:** 1.0.0
**Last Updated:** 2025-01-XX

## Prerequisites

### System Requirements
- **Python:** 3.11+
- **OS:** Windows 10+, Linux, or macOS
- **RAM:** 4GB minimum, 8GB recommended
- **Network:** Stable internet connection

### Dependencies
```bash
# Install Python dependencies
pip install -r requirements.txt

# Verify Python version
python --version  # Should be 3.11+
```

### API Credentials
- ✅ Binance Futures Testnet account created
- ✅ API keys generated with Futures permissions
- ✅ Test USDT available in futures wallet
- ✅ `.env` file configured (see `docs/secrets.md`)

### Pre-launch Verification
Run the pre-launch checklist from `docs/TESTNET_LAUNCH_CHECKLIST.md` before proceeding.

## Starting the Daemon

### Step 1: Environment Setup
```bash
# Navigate to project root
cd /path/to/aurora_project

# Activate virtual environment
.venv\Scripts\Activate.ps1  # Windows
# or
source .venv/bin/activate   # Linux/macOS

# Verify environment
which python  # Should point to .venv/bin/python
```

### Step 2: Configuration Verification
```bash
# Test configuration loading
python -c "
from apps.reference.config_loader import ConfigLoader
loader = ConfigLoader()
config = loader.load_config()
print(f'✅ USE_TESTNET: {config.use_testnet}')
print(f'✅ API_KEY: {\"***\" + config.binance_api_key[-4:] if config.binance_api_key else \"NOT SET\"}')
print(f'✅ LOG_LEVEL: {config.log_level}')
"
```

Expected output:
```
✅ USE_TESTNET: True
✅ API_KEY: ***abcd
✅ LOG_LEVEL: INFO
```

### Step 3: Start Aurora Daemon
```bash
# Start the daemon
python apps/reference/main.py

# Alternative with explicit config (if needed)
# USE_TESTNET=true LOG_LEVEL=DEBUG python apps/reference/main.py
```

### Expected Startup Logs
```
2025-01-XX XX:XX:XX [INFO] Aurora Core starting...
2025-01-XX XX:XX:XX [INFO] [BinanceAdapter] Using TESTNET credentials
2025-01-XX XX:XX:XX [INFO] FSM Core initialized with 5 domains
2025-01-XX XX:XX:XX [INFO] Aurora Core startup complete
2025-01-XX XX:XX:XX [INFO] Ready for trading signals
```

## Monitoring

### Log Files
- **Main Log:** `logs/aurora_core.log`
- **Format:** JSON (configurable to text in `system.yaml`)
- **Rotation:** 10MB max, automatic rotation

### Key Log Messages to Monitor

#### Normal Operation
```
[INFO] EVT:TRADE_INTENT_PROPOSED - New trading opportunity detected
[INFO] DEC:OPEN - Executing market entry order
[INFO] EVT:ORDER_PLACED - Order successfully placed on Binance
[INFO] EVT:FILL_RECEIVED - Order fill confirmed
[INFO] DEC:CLOSE - Executing position closure
```

#### System Health
```
[INFO] [CircuitBreaker] CLOSED: Normal operation resumed
[INFO] Market data lag: 45ms (within limit)
[INFO] WAL integrity verified (hash: abc123...)
```

#### Warnings
```
[WARNING] [CircuitBreaker] OPEN: Blocking all requests for 30s
[WARNING] Market data lag: 1250ms (exceeds limit of 1000ms)
[WARNING] Retry attempt 2/3 for order placement
```

#### Errors (Require Attention)
```
[ERROR] DEC:OPEN failed - Insufficient balance
[ERROR] WebSocket connection lost, reconnecting...
[ERROR] FSM state transition failed
```

### Debug API (if available)
```bash
# Get system status
curl http://localhost:8000/debug/status

# Get logs for specific RID
curl http://localhost:8000/debug/{rid}

# Get metrics
curl http://localhost:8000/metrics
```

### Binance Testnet Dashboard
- **URL:** https://testnet.binancefuture.com/
- **Check:** Order history, position status, account balance
- **Monitor:** Ensure orders appear in Binance within seconds of Aurora logs

## Key Metrics to Track

### Activity Metrics
- **Orders Placed:** Number of entry/exit orders executed
- **Fill Rate:** Percentage of orders that get filled
- **Intent Generation:** Trading signals generated per hour

### Performance Metrics
- **Order Latency:** Time from DEC:OPEN to order placement confirmation
- **Fill Latency:** Time from order placement to fill confirmation
- **System CPU/Memory:** Resource usage during operation

### Reliability Metrics
- **API Error Rate:** Percentage of failed API calls
- **Circuit Breaker Events:** Number of times circuit opens
- **Reconnection Events:** WebSocket reconnection frequency
- **TTL Timeouts:** Orders timing out before execution

### Financial Metrics
- **PnL:** Realized/unrealized profit & loss
- **Win Rate:** Percentage of profitable trades
- **Max Drawdown:** Largest peak-to-valley decline

## Troubleshooting

### Startup Issues

#### "Config file not found"
```
Error: Config file not found: config/aurora/trading.yaml
```
**Solution:**
- Verify you're running from project root directory
- Check that `config/aurora/` directory exists
- Ensure YAML files are present: `trading.yaml`, `system.yaml`

#### "Required environment variable not set"
```
ValueError: Required environment variable 'BINANCE_TESTNET_API_KEY' is not set
```
**Solution:**
- Check `.env` file exists and is properly formatted
- Verify variable names match exactly (case-sensitive)
- Restart terminal after setting environment variables
- See `docs/secrets.md` for setup instructions

#### "API credentials not found, falling back to shadow mode"
```
[WARNING] API credentials not found, falling back to shadow mode
```
**Solution:**
- Same as above - check API key configuration
- Verify `USE_TESTNET=true` in environment

### Runtime Issues

#### Circuit Breaker Open
```
[CircuitBreaker] OPEN: Blocking all requests for 30s
```
**Cause:** Multiple API failures (rate limits, network issues, etc.)
**Solution:**
- Check network connectivity
- Verify API keys are valid
- Monitor Binance status page
- Wait for automatic recovery or restart if persistent

#### High Market Data Lag
```
[WARNING] Market data lag: 1250ms (exceeds limit of 1000ms)
```
**Cause:** Network latency, Binance API delays
**Solution:**
- Check internet connection stability
- Monitor Binance API status
- Consider adjusting `market_data.max_allowed_lag_ms` in config

#### Order Placement Failures
```
[ERROR] DEC:OPEN failed - Insufficient balance
```
**Cause:** Not enough test USDT in futures account
**Solution:**
- Transfer more test USDT from spot to futures wallet
- Reduce position sizes in `trading.yaml`
- Check current balance on Binance testnet

#### WebSocket Disconnections
```
[ERROR] WebSocket connection lost, reconnecting...
```
**Cause:** Network instability, Binance maintenance
**Solution:**
- Check internet connection
- Monitor Binance status page
- System will auto-reconnect with exponential backoff

### Emergency Procedures

#### Graceful Shutdown
```bash
# Press Ctrl+C in terminal running Aurora
# or send SIGTERM signal
```

#### Emergency Stop
```bash
# Find process ID
ps aux | grep "python apps/reference/main.py"

# Force kill if needed
kill -9 <PID>
```

#### Manual Position Closure
If Aurora fails but positions remain open:
1. Go to Binance Testnet dashboard
2. Navigate to Futures → Positions
3. Manually close any open positions
4. Cancel any pending orders

## Configuration Tuning

### For Development/Testing
```yaml
# system.yaml
logging:
  level: "DEBUG"

# trading.yaml
risk_budgets:
  trade_cvar95_max_bps: 100  # Conservative for testing
```

### For Production-like Testing
```yaml
# system.yaml
logging:
  level: "INFO"

# trading.yaml
risk_budgets:
  trade_cvar95_max_bps: 500  # More aggressive
```

## Post-Run Analysis

After stopping the daemon:

1. **Review Logs:**
   ```bash
   # Check for errors
   grep "ERROR" logs/aurora_core.log

   # Count successful orders
   grep "EVT:ORDER_PLACED" logs/aurora_core.log | wc -l
   ```

2. **Analyze Performance:**
   - Review PnL in Binance dashboard
   - Check order execution times
   - Identify any failure patterns

3. **Update Configuration:**
   - Adjust parameters based on observed behavior
   - Fine-tune risk limits if too conservative/aggressive

## Support

- **Logs Location:** `logs/aurora_core.log`
- **Config Files:** `config/aurora/*.yaml`
- **Environment:** `.env` file
- **Documentation:** This runbook, `docs/secrets.md`, `docs/TESTNET_LAUNCH_CHECKLIST.md`

For issues not covered here, check the logs and refer to the codebase documentation.</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\runbook\RUN_TESTNET.md