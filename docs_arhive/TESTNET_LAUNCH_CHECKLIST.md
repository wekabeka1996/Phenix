# Testnet Launch Checklist

**RID:** `AURORA_TESTNET_PREP_V1`
**Version:** 1.0.0
**Purpose:** Pre-launch verification checklist to ensure safe and successful testnet deployment

## Pre-Launch Verification

### □ Code & Environment
- [ ] **Git Status:** Code is on stable branch/tag (`git status` shows clean)
- [ ] **Dependencies:** All packages installed (`pip install -r requirements.txt`)
- [ ] **Python Version:** 3.11+ verified (`python --version`)
- [ ] **Virtual Environment:** Activated and pointing to correct Python (`which python`)
- [ ] **Unit Tests:** All tests pass (`pytest tests/unit/ -v`)
- [ ] **Integration Tests:** Scenario tests pass (`pytest tests/integration/ -v`)

### □ Configuration Files
- [ ] **trading.yaml:** Exists in `config/aurora/` and properly formatted
- [ ] **system.yaml:** Exists in `config/aurora/` and properly formatted
- [ ] **Environment File:** `.env` exists and configured (not committed to git)
- [ ] **USE_TESTNET:** Set to `true` in environment
- [ ] **LOG_LEVEL:** Set appropriately (INFO for production testing, DEBUG for development)
- [ ] **TRADING_ENV:** Set to `testnet` for identification

### □ API Credentials
- [ ] **Testnet Account:** Binance Futures Testnet account created and verified
- [ ] **API Keys Generated:** Keys created with Futures permissions enabled
- [ ] **API Keys Configured:** `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET` set
- [ ] **Read-only Keys:** `BINANCE_RO_API_KEY`/`SECRET` configured (optional)
- [ ] **Key Permissions:** Futures trading enabled, withdrawals disabled
- [ ] **Test USDT Available:** Sufficient test funds in futures wallet (minimum 100 USDT recommended)

### □ System Configuration
- [ ] **Hardening Parameters:** TTL/retry/circuit breaker settings reasonable for testnet
- [ ] **Risk Limits:** Conservative position sizes and leverage (leverage ≤ 10x recommended)
- [ ] **Market Data:** Lag detection enabled with appropriate thresholds
- [ ] **Logging:** File rotation configured, log directory writable
- [ ] **Trading Pairs:** Only BTCUSDT/ETHUSDT enabled initially

### □ Network & Security
- [ ] **Internet Connection:** Stable connection verified
- [ ] **Firewall:** No blocking of Binance API endpoints
- [ ] **VPN/Proxy:** None active (can interfere with API calls)
- [ ] **2FA:** Enabled on Binance account
- [ ] **API Key Security:** Keys not exposed in logs or shared

## Configuration Verification Commands

Run these commands to verify setup:

```bash
# 1. Environment check
echo "USE_TESTNET: $USE_TESTNET"
echo "LOG_LEVEL: $LOG_LEVEL"
echo "TRADING_ENV: $TRADING_ENV"

# 2. Configuration loading test
python -c "
from apps.reference.config_loader import ConfigLoader
c = ConfigLoader()
config = c.load_config()
print('✅ Config loaded successfully')
print(f'USE_TESTNET: {config.use_testnet}')
print(f'API_KEY configured: {bool(config.binance_api_key)}')
print(f'LOG_LEVEL: {config.log_level}')
"

# 3. API connectivity test (optional, requires keys)
python -c "
import os
import requests
import time
import hashlib
import hmac

# Test basic connectivity to Binance Testnet
BASE_URL = 'https://testnet.binancefuture.com'
response = requests.get(f'{BASE_URL}/fapi/v1/time')
if response.status_code == 200:
    print('✅ Binance Testnet API reachable')
    server_time = response.json()['serverTime']
    local_time = int(time.time() * 1000)
    offset = server_time - local_time
    print(f'�  Time offset: {offset}ms')
else:
    print('❌ Binance Testnet API unreachable')
"
```

## Launch Readiness Assessment

### Risk Assessment
- [ ] **Financial Risk:** Only testnet funds at risk (no real money)
- [ ] **Position Sizing:** Conservative limits prevent excessive losses
- [ ] **Emergency Stop:** Shutdown procedures known and tested
- [ ] **Monitoring:** Log monitoring plan in place

### Operational Readiness
- [ ] **Runbook Read:** `docs/runbook/RUN_TESTNET.md` reviewed
- [ ] **Secrets Guide:** `docs/secrets.md` reviewed
- [ ] **Troubleshooting:** Common issues and solutions known
- [ ] **Support Access:** Team contact information available

### Success Criteria
- [ ] **Startup:** System starts without critical errors
- [ ] **API Connection:** Successfully connects to Binance Testnet
- [ ] **Order Placement:** Can place test orders (manual verification)
- [ ] **Monitoring:** Logs are generated and accessible
- [ ] **Shutdown:** Graceful shutdown works correctly

## Launch Approval

**Launch Authorized By:** ________________________
**Date:** ________________________
**Time:** ________________________

**Pre-launch Checklist Completed:** □ Yes □ No
**All Critical Items Verified:** □ Yes □ No
**Ready for Launch:** □ Yes □ No

## Post-Launch Notes

**Launch Time:** ________________________
**Initial Status:** ________________________
**Issues Encountered:** ________________________
**Follow-up Actions:** ________________________

---

## Emergency Contacts

- **Technical Lead:** [Name/Contact]
- **DevOps:** [Name/Contact]
- **Binance Support:** https://testnet.binancefuture.com/ (for API issues)

## Quick Reference

**Start Command:**
```bash
.venv\Scripts\Activate.ps1
python apps/reference/main.py
```

**Stop Commands:**
- Graceful: `Ctrl+C`
- Emergency: `taskkill /PID <pid> /F` (Windows) or `kill -9 <pid>` (Linux)

**Log Location:** `logs/aurora_core.log`

**Binance Testnet:** https://testnet.binancefuture.com/</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\TESTNET_LAUNCH_CHECKLIST.md