## 2025-01-XX | RID: AURORA_TESTNET_PREP_V1 |  ü ñ ¥ ≥ æ Ç æ ≤ ∫    ¥ æ  ó     É   ∫ É  Ω   Binance Testnet

**WHY**:  ü ñ   ª è  É     ñ à Ω æ ≥ æ hardening  Ç    Ç µ   Ç É ≤   Ω Ω è    Ü µ Ω     ñ ó ≤  Ω µ æ ± Ö ñ ¥ Ω æ    ñ ¥ ≥ æ Ç É ≤   Ç ∏  ≤   é  ñ Ω Ñ       Ç   É ∫ Ç É   É  ¥ ª è  ± µ ∑   µ á Ω æ ≥ æ  ∑     É   ∫ É Aurora Core  Ω   Binance Futures Testnet  ∑  º æ ∂ ª ∏ ≤ ñ   Ç é  º æ Ω ñ Ç æ   ∏ Ω ≥ É  Ç    à ≤ ∏ ¥ ∫ æ ≥ æ    µ   ≥ É ≤   Ω Ω è  Ω        æ ± ª µ º ∏.

** î Ü á**:
1. ** § ñ Ω   ª ñ ∑   Ü ñ è  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó testnet**:
   -  ü µ   µ ≤ ñ   µ Ω æ  µ Ω ¥   æ ñ Ω Ç ∏:  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î Ç å   è `https://testnet.binancefuture.com`  ¥ ª è REST API
   -  î æ ¥   Ω æ hardening  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  ¥ æ `system.yaml`: TTL (5s/3s/2s), retry (3        æ ± ∏), circuit breaker (5    æ º ∏ ª æ ∫, 30s timeout), market data lag (1000ms), WAL integrity
   -  ó º µ Ω à µ Ω æ    ∏ ∑ ∏ ∫ ∏  ≤ `trading.yaml`: risk_budgets  ∑ Ω ∏ ∂ µ Ω æ  ¥ æ 200/500 bps  ¥ ª è  ± µ ∑   µ á Ω ñ à æ ó  Ç µ   Ç Ω µ Ç  æ   µ     Ü ñ ó
   -  ù   ª   à Ç æ ≤   Ω æ  ª æ ≥ É ≤   Ω Ω è: INFO    ñ ≤ µ Ω å, JSON  Ñ æ   º   Ç,    æ Ç   Ü ñ è 10MB

2. ** î æ ∫ É º µ Ω Ç   Ü ñ è API  ∫ ª é á ñ ≤** (`docs/secrets.md`):
   -  ° Ç ≤ æ   µ Ω æ    æ ∫   æ ∫ æ ≤ ∏ π  ≥   π ¥    æ  ≥ µ Ω µ     Ü ñ ó testnet API  ∫ ª é á ñ ≤
   -  î æ ¥   Ω æ  ñ Ω   Ç   É ∫ Ü ñ ó    æ  ± µ ∑   µ á Ω æ º É  ∑ ± µ   µ ∂ µ Ω Ω é  ≤ `.env`  Ñ   π ª ñ
   -  í ∏ ∑ Ω   á µ Ω æ  ∑ º ñ Ω Ω ñ    µ   µ ¥ æ ≤ ∏ â  : `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`
   -  î æ ¥   Ω æ    µ   µ ≤ ñ   ∫ É  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  Ç   troubleshooting

3. ** ° Ç ≤ æ   µ Ω Ω è Runbook** (`docs/runbook/RUN_TESTNET.md`):
   -  † æ ∑ ¥ ñ ª Prerequisites:  ∑   ª µ ∂ Ω æ   Ç ñ, API  ∫ ª é á ñ,  Ç µ   Ç æ ≤ ñ  ∫ æ à Ç ∏
   -  † æ ∑ ¥ ñ ª Starting the Daemon:  ∫ æ º   Ω ¥ ∏    ∫ Ç ∏ ≤   Ü ñ ó venv,  ∑     É   ∫ É,  æ á ñ ∫ É ≤   Ω ñ  ª æ ≥ ∏
   -  † æ ∑ ¥ ñ ª Monitoring:  ª æ ≥ ∏, debug API, Binance dashboard,  ∫ ª é á æ ≤ ñ  º µ Ç   ∏ ∫ ∏
   -  † æ ∑ ¥ ñ ª Troubleshooting:    æ à ∏   µ Ω ñ    æ º ∏ ª ∫ ∏  Ç    ó Ö  ≤ ∏   ñ à µ Ω Ω è
   -  † æ ∑ ¥ ñ ª Emergency Procedures: graceful shutdown, emergency stop

4. ** í ∏ ∑ Ω   á µ Ω Ω è  º µ Ç   ∏ ∫  º æ Ω ñ Ç æ   ∏ Ω ≥ É** (`docs/TESTNET_MONITORING.md`):
   - Activity Metrics: orders, fills, intents, API calls
   - Performance Metrics: latency, resources, throughput
   - Reliability Metrics: error rates, circuit breaker, connectivity
   - Financial Metrics: PnL, win rate, drawdown, risk metrics
   - Alert Thresholds: critical/warning/info alerts  ∑  ∫ æ Ω ∫   µ Ç Ω ∏ º ∏    æ   æ ≥   º ∏

5. ** ° Ç ≤ æ   µ Ω Ω è Pre-launch Checklist** (`docs/TESTNET_LAUNCH_CHECKLIST.md`):
   - Code & Environment: git status, dependencies, Python version
   - Configuration Files: YAML  Ñ   π ª ∏, .env, environment variables
   - API Credentials: testnet account, keys, permissions, test funds
   - System Configuration: hardening params, risk limits, logging
   - Network & Security: connectivity, firewall, 2FA, key security
   - Risk Assessment: financial risk, emergency procedures
   - Success Criteria: startup, API connection, monitoring

6. ** û Ω æ ≤ ª µ Ω Ω è TODO**:
   - AURORA_TESTNET_PREP_V1    æ ∑ Ω   á µ Ω æ  è ∫  ∑   ≤ µ   à µ Ω µ
   -  î æ ¥   Ω æ  Ω     Ç É   Ω ∏ π  ∫   æ ∫ AURORA_TESTNET_RUN_V1

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ° Ç ≤ æ   µ Ω æ    æ ≤ Ω É  ¥ æ ∫ É º µ Ω Ç   Ü ñ é  ¥ ª è  ± µ ∑   µ á Ω æ ≥ æ  ∑     É   ∫ É  Ω   testnet
- ‚úÖ Hardening  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  ¥ æ ¥   Ω ñ  Ç    Ω   ª   à Ç æ ≤   Ω ñ  ¥ ª è  Ç µ   Ç æ ≤ æ ≥ æ    µ   µ ¥ æ ≤ ∏ â  
- ‚úÖ  † ∏ ∑ ∏ ∫ ∏  ∑ º µ Ω à µ Ω ñ  ¥ ª è  ± µ ∑   µ á Ω ñ à æ ó  æ   µ     Ü ñ ó (leverage 10x, conservative risk limits)
- ‚úÖ  ú µ Ç   ∏ ∫ ∏  º æ Ω ñ Ç æ   ∏ Ω ≥ É  ≤ ∏ ∑ Ω   á µ Ω ñ  ∑  á ñ Ç ∫ ∏ º ∏    æ   æ ≥   º ∏ alert' ñ ≤
- ‚úÖ Pre-launch checklist  ∑   ± µ ∑   µ á É î  ≤   µ ± ñ á Ω É    µ   µ ≤ ñ   ∫ É    µ   µ ¥  ∑     É   ∫ æ º
- ‚úÖ Runbook  Ω   ¥   î    æ ∫   æ ∫ æ ≤ ñ  ñ Ω   Ç   É ∫ Ü ñ ó  Ç   troubleshooting  ¥ ª è  ≤   ñ Ö    Ü µ Ω     ñ ó ≤
- ‚úÖ AURORA_TESTNET_PREP_V1    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è

** ù ê ° ¢ £ ü ù Ü  ö † û ö ò**:
-  í ∏ ∫ æ Ω   Ç ∏ pre-launch checklist
-  ó     É   Ç ∏ Ç ∏ Aurora  Ω   testnet  ¥ ª è    µ   à æ ≥ æ  Ç µ   Ç æ ≤ æ ≥ æ      æ ≥ æ Ω É
-  ú æ Ω ñ Ç æ   ∏ Ç ∏  º µ Ç   ∏ ∫ ∏  Ç   logs      æ Ç è ≥ æ º 24+  ≥ æ ¥ ∏ Ω
-  ü   æ ≤ µ   Ç ∏    Ω   ª ñ ∑    µ ∑ É ª å Ç   Ç ñ ≤  Ç   fine-tuning  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó

## 2025-01-XX | RID: AURORA_SCENARIO_TESTING_V1 |  † æ ∑ à ∏   µ Ω µ  ¢ µ   Ç É ≤   Ω Ω è  ° Ü µ Ω     ñ ó ≤ (Order Lifecycle + Resilience)

**WHY**:  ü ñ   ª è  É     ñ à Ω æ ≥ æ hardening    ∏   Ç µ º ∏  Ω µ æ ± Ö ñ ¥ Ω    ∫ æ º   ª µ ∫   Ω    ≤   ª ñ ¥   Ü ñ è end-to-end    Ü µ Ω     ñ ó ≤ order lifecycle  Ç   failure recovery mechanisms    µ   µ ¥    µ   µ Ö æ ¥ æ º  ¥ æ testnet.

** î Ü á**:
1. ** ° Ç ≤ æ   µ Ω Ω è  Ç µ   Ç æ ≤ æ ó  ñ Ω Ñ       Ç   É ∫ Ç É   ∏**:
   -  î æ ¥   Ω æ  Ω æ ≤ ñ pytest  º     ∫ µ   ∏: `ws_rest`  ¥ ª è WebSocket/REST  Ç µ   Ç ñ ≤, `scen`  ¥ ª è    Ü µ Ω     ñ π Ω ∏ Ö  Ç µ   Ç ñ ≤
   -  ° Ç ≤ æ   µ Ω æ MockAuroraSystem  ¥ ª è  ñ ∑ æ ª è Ü ñ ó  Ç µ   Ç ñ ≤  ≤ ñ ¥    µ   ª å Ω æ ó    ∏   Ç µ º ∏
   -  ù   ª   à Ç æ ≤   Ω æ pytest fixtures  ¥ ª è mock    ∏   Ç µ º ∏

2. ** Ü º   ª µ º µ Ω Ç   Ü ñ è order lifecycle  Ç µ   Ç ñ ≤** (`test_order_lifecycle_scenarios.py`):
   - ** ° Ü µ Ω     ñ π 3**: Entry ‚Üí Fill ‚Üí Bracket placement -  Ç µ   Ç  ±   ∑ æ ≤ æ ≥ æ order flow
   - ** ° Ü µ Ω     ñ π 4**: Partial fill storm - placeholder  ¥ ª è WS event mocking
   - ** ° Ü µ Ω     ñ π 5**: TP fill ‚Üí peer cancel - placeholder  ¥ ª è race condition testing
   - ** ° Ü µ Ω     ñ π 6**: SL fill during replace race - placeholder  ¥ ª è concurrent event handling
   - ** ° Ü µ Ω     ñ π 8**: Force market close idempotent -  Ç µ   Ç  ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ  ∫ æ º   Ω ¥

3. ** Ü º   ª µ º µ Ω Ç   Ü ñ è resilience  Ç µ   Ç ñ ≤** (`test_resilience_scenarios.py`):
   - ** ° Ü µ Ω     ñ π 9**: Reconnect warm reconcile - placeholder  ¥ ª è adapter restart testing
   - ** ° Ü µ Ω     ñ π 10**: Metrics/Debug API validation - placeholder  ¥ ª è API endpoint testing
   - ** ° Ü µ Ω     ñ π 11**: TTL entry timeout - placeholder  ¥ ª è timeout mechanism testing
   - ** ° Ü µ Ω     ñ π 12**: Idempotent operations -  Ç µ   Ç  ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ DEC:ADJUST  ∫ æ º   Ω ¥

4. **Mock  ñ Ω Ñ       Ç   É ∫ Ç É    **:
   - Mock adapter  ∑ place_order, close_position, adjust_position  º µ Ç æ ¥   º ∏
   - Mock Message  ∫ ª      ¥ ª è  Ç µ   Ç É ≤   Ω Ω è      æ Ç æ ∫ æ ª É
   - Mock    æ ≤ µ   Ω µ Ω Ω è  ¥   Ω ∏ Ö  É  Ñ æ   º   Ç ñ execution feedback schema

5. ** ó     É   ∫  Ç    ≤   ª ñ ¥   Ü ñ è**:
   - ‚úÖ 9  Ç µ   Ç ñ ≤  É     ñ à Ω æ      æ π à ª ∏ (2    µ   ª ñ ∑ æ ≤   Ω ∏ Ö, 7 placeholder)
   - ‚úÖ  ù ñ è ∫ ∏ Ö    æ º ∏ ª æ ∫  ñ º   æ   Ç É  á ∏    ∏ Ω Ç   ∫   ∏   É
   - ‚úÖ Pytest  ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  æ Ω æ ≤ ª µ Ω    ∑  Ω æ ≤ ∏ º ∏  º     ∫ µ     º ∏
   - ‚úÖ  ö æ ¥  ≤ ñ ¥   æ ≤ ñ ¥   î      Ö ñ Ç µ ∫ Ç É   ñ  ñ   Ω É é á ∏ Ö  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ Ö  Ç µ   Ç ñ ≤

6. ** û Ω æ ≤ ª µ Ω Ω è  ¥ æ ∫ É º µ Ω Ç   Ü ñ ó**:
   - TODO.md  æ Ω æ ≤ ª µ Ω æ  ∑  ¥ µ Ç   ª è º ∏  ∑   ≤ µ   à µ Ω Ω è AURORA_SCENARIO_TESTING_V1
   - JOURNAL_Aurora.md  ¥ æ   æ ≤ Ω µ Ω æ  Ü ∏ º  ∑     ∏   æ º

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ° Ç ≤ æ   µ Ω æ framework  ¥ ª è  ∫ æ º   ª µ ∫   Ω æ ≥ æ    Ü µ Ω     ñ π Ω æ ≥ æ  Ç µ   Ç É ≤   Ω Ω è
- ‚úÖ  † µ   ª ñ ∑ æ ≤   Ω æ  ±   ∑ æ ≤ ñ  Ç µ   Ç ∏  ¥ ª è order lifecycle  Ç    ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ
- ‚úÖ  ü ñ ¥ ≥ æ Ç æ ≤ ª µ Ω æ placeholders  ¥ ª è  ≤   ñ Ö TEST_PLAN    Ü µ Ω     ñ ó ≤ (3-12)
- ‚úÖ Mock  ñ Ω Ñ       Ç   É ∫ Ç É      ≥ æ Ç æ ≤    ¥ ª è    æ ∑ à ∏   µ Ω Ω è  ∑    µ   ª å Ω ∏ º ∏ WS events
- ‚úÖ  £   ñ  Ç µ   Ç ∏      æ Ö æ ¥ è Ç å  É     ñ à Ω æ,    ∏   Ç µ º    ≥ æ Ç æ ≤    ¥ æ  Ω     Ç É   Ω ∏ Ö  ñ Ç µ     Ü ñ π
- ‚úÖ AURORA_SCENARIO_TESTING_V1    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è

** ù ê ° ¢ £ ü ù Ü  ö † û ö ò**:
-  † æ ∑ à ∏   µ Ω Ω è  Ç µ   Ç ñ ≤  ∑    µ   ª å Ω ∏ º ∏ WS event simulation
-  Ü Ω Ç µ ≥     Ü ñ è  ∑ debug API  ¥ ª è metrics validation
-  ü ñ ¥ ≥ æ Ç æ ≤ ∫    ¥ æ AURORA_TESTNET_PREP_V1

## 2025-01-XX | RID: AURORA_OBSERVABILITY_V1 |  † µ   ª ñ ∑   Ü ñ è  °   æ   Ç µ   µ ∂ É ≤   Ω æ   Ç ñ (WHY- ∫ æ ¥ ∏,  ¢       É ≤   Ω Ω è)

**WHY**:  î ª è  µ Ñ µ ∫ Ç ∏ ≤ Ω æ ó  ¥ ñ   ≥ Ω æ   Ç ∏ ∫ ∏  Ç    º æ Ω ñ Ç æ   ∏ Ω ≥ É    ∏   Ç µ º ∏  Ω µ æ ± Ö ñ ¥ Ω      Ç   Ω ¥     Ç ∏ ∑   Ü ñ è WHY- ∫ æ ¥ ñ ≤,  ∫ æ   µ ª è Ü ñ π Ω ñ  ∫ ª é á ñ (RID)  Ç   debug API  ¥ ª è  Ç       É ≤   Ω Ω è  ∑     ∏ Ç ñ ≤  á µ   µ ∑  ≤   é    ∏   Ç µ º É.

** î Ü á**:
1. ** ° Ç   Ω ¥     Ç ∏ ∑   Ü ñ è WHY- ∫ æ ¥ ñ ≤** (`why_codes.py`):
   -  ° Ç ≤ æ   µ Ω æ 50+    Ç   Ω ¥     Ç ∏ ∑ æ ≤   Ω ∏ Ö WHY  ∫ æ ¥ ñ ≤  ¥ ª è  ≤   ñ Ö    Ü µ Ω     ñ ó ≤  ≤ ñ ¥ Ö ∏ ª µ Ω å
   -  ö   Ç µ ≥ æ   ñ ó: SPREAD, RISK, LIQ, MARGIN, REGIME, GUARD, SIGNAL, VALIDATION
   -  î æ ¥   Ω æ SIGNAL_NEUTRAL  ¥ ª è  Ω µ π Ç     ª å Ω æ ≥ æ    ∏ ≥ Ω   ª É
   -  § É Ω ∫ Ü ñ è `format_why_with_details()`  ¥ ª è  Ñ æ   º   Ç É ≤   Ω Ω è    æ ≤ ñ ¥ æ º ª µ Ω å  ∑  ∫ æ Ω Ç µ ∫   Ç æ º

2. ** Ü º   ª µ º µ Ω Ç   Ü ñ è  ∫ æ   µ ª è Ü ñ π Ω ∏ Ö  ∫ ª é á ñ ≤** (`decision_making.py`):
   -  ì µ Ω µ     Ü ñ è RID (uuid4)  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ trade intent
   -  ü   æ     ≥ É ≤   Ω Ω è RID  á µ   µ ∑ event payload  ¥ æ command payload
   - RID  ≤ ∫ ª é á   î Ç å   è  É  ≤   ñ  ª æ ≥ ∏  Ç   debug  ∑     ∏   ∏

3. ** Ü Ω Ç µ ≥     Ü ñ è WHY- ∫ æ ¥ ñ ≤  É  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è** (`decision_making.py`):
   - MARGIN_INSUFFICIENT:  ¥ ª è insufficient equity (‚â§ 0)
   - RISK_NOT_ALLOWED:  ∫ æ ª ∏ risk manager  ∑   ± æ   æ Ω è î trading
   - SIGNAL_NEUTRAL:  ¥ ª è  Ω µ π Ç     ª å Ω æ ≥ æ signal score
   - REGIME_TREND_UP_BLOCK_SELL/REGIME_TREND_DOWN_BLOCK_BUY:  ¥ ª è counter-trend  ± ª æ ∫ É ≤   Ω å
   - LIQ_POSITION_TOO_SMALL:  ¥ ª è insufficient position size/quantity
   - GUARD_LIQ_DIST_TOO_CLOSE:  ¥ ª è liquidation distance guard

4. **Debug API  Ç    ª æ ≥ É ≤   Ω Ω è** (`debug_api.py`, `decision_making.py`):
   - `add_debug_log()`  ¥ ª è RID-based tracing  ∑ thread-safe storage
   - `get_debug_logs_for_rid()`  ¥ ª è  æ Ç   ∏ º   Ω Ω è  ª æ ≥ ñ ≤    æ RID
   - Debug  ª æ ≥ ∏  ¥ æ ¥   é Ç å   è  ¥ æ  ≤   ñ Ö rejection  Ç   approval events
   - Thread-safe in-memory storage  ∑    ≤ Ç æ º   Ç ∏ á Ω ∏ º cleanup

5. ** ¢ µ   Ç É ≤   Ω Ω è  ñ Ω Ç µ ≥     Ü ñ ó**:
   - ‚úÖ test_decision_making_contract.py      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ
   - ‚úÖ test_p1_001_precision_preservation.py      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ
   - ‚úÖ  ö æ ¥  ∫ æ º   ñ ª é î Ç å   è  ± µ ∑    æ º ∏ ª æ ∫
   - ‚úÖ WHY  ∫ æ ¥ ∏  ñ Ω Ç µ ≥   æ ≤   Ω ñ  É  ≤   ñ rejection paths

6. ** ° ∏ Ω Ö   æ Ω ñ ∑   Ü ñ è  Ñ   π ª ñ ≤**:
   -  õ æ ∫   ª å Ω ñ  ∫ æ   ñ ó why_codes.py  Ç   debug_api.py  É apps/reference/domains/decision_making/

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ° Ç   Ω ¥     Ç ∏ ∑ æ ≤   Ω ñ WHY  ∫ æ ¥ ∏  ¥ ª è  ≤   ñ Ö rejection    Ü µ Ω     ñ ó ≤
- ‚úÖ RID tracing  ≤ ñ ¥ decision  á µ   µ ∑ execution
- ‚úÖ Debug API  ¥ ª è inspection system behavior    æ RID
- ‚úÖ Thread-safe debug logging  ∑ cleanup
- ‚úÖ  £   ñ  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é Ç å WHY  ∫ æ ¥ ∏  ∑  ¥ µ Ç   ª å Ω ∏ º  ∫ æ Ω Ç µ ∫   Ç æ º
- ‚úÖ  ¢ µ   Ç É ≤   Ω Ω è    ñ ¥ Ç ≤ µ   ¥ ∂ É î  ∫ æ   µ ∫ Ç Ω ñ   Ç å  ñ Ω Ç µ ≥     Ü ñ ó
- ‚úÖ AURORA_OBSERVABILITY_V1    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è

## 2025-01-XX | RID: AURORA_HARDENING_V1_TTL_RETRY |  † µ   ª ñ ∑   Ü ñ è TTL/Retry  ü æ ª ñ Ç ∏ ∫ ( ß     Ç ∏ Ω   1)

**WHY**:  î ª è    ñ ¥ ≤ ∏ â µ Ω Ω è  Ω   ¥ ñ π Ω æ   Ç ñ    ∏   Ç µ º ∏  Ω µ æ ± Ö ñ ¥ Ω ñ TTL  Ç   π º   É Ç ∏  Ç   retry    æ ª ñ Ç ∏ ∫ ∏  ∑ exponential backoff  ¥ ª è  ≤   ñ Ö  ∑ æ ≤ Ω ñ à Ω ñ Ö API  ≤ ∏ ∫ ª ∏ ∫ ñ ≤,  æ   æ ± ª ∏ ≤ æ Binance Futures API.

** î Ü á**:
1. ** ö æ Ω Ñ ñ ≥ É     Ü ñ è TTL  Ç   Retry** (`config/aurora/trading.yaml`):
   -  î æ ¥   Ω æ `execution.ttl`    µ ∫ Ü ñ é  ∑  Ç   π º   É Ç   º ∏:
     - `entry_place_ttl_ms: 5000` (5    µ ∫  ¥ ª è entry  æ   ¥ µ   ñ ≤)
     - `bracket_place_ttl_ms: 3000` (3    µ ∫  ¥ ª è bracket  æ   ¥ µ   ñ ≤) 
     - `cancel_ttl_ms: 2000` (2    µ ∫  ¥ ª è cancel  æ   µ     Ü ñ π)
   -  î æ ¥   Ω æ `execution.retry`    µ ∫ Ü ñ é  ∑ retry    æ ª ñ Ç ∏ ∫   º ∏:
     - `max_tries: 3` ( º   ∫   ∏ º É º 3        æ ± ∏)
     - `backoff_ms: 1000` ( ±   ∑ æ ≤ ∏ π backoff 1    µ ∫)
     - `jitter: true` ( ≤ ∏     ¥ ∫ æ ≤ ∏ π jitter  ¥ ª è  É Ω ∏ ∫ Ω µ Ω Ω è thundering herd)

2. ** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  ≤ Adapter** (`binance_execution_adapter.py`):
   -  î æ ¥   Ω æ `ttl_config`  Ç   `retry_config`    Ç   ∏ ± É Ç ∏  ∑  ¥ µ Ñ æ ª Ç Ω ∏ º ∏  ∑ Ω   á µ Ω Ω è º ∏
   -  ° Ç ≤ æ   µ Ω æ `initialize_ttl_retry_config()`  º µ Ç æ ¥  ¥ ª è  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ ó  ∑ config
   -  Ü Ω Ç µ ≥     Ü ñ è  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ ó  ≤ `fsm.py`    ñ   ª è margin settings

3. ** † µ   ª ñ ∑   Ü ñ è TTL/Retry  ª æ ≥ ñ ∫ ∏** (`binance_execution_adapter.py`):
   -  ° Ç ≤ æ   µ Ω æ `_execute_with_ttl_retry_sync()`  º µ Ç æ ¥  ¥ ª è    ∏ Ω Ö   æ Ω Ω ∏ Ö HTTP  ∑     ∏ Ç ñ ≤
   -  † µ   ª ñ ∑ æ ≤   Ω æ exponential backoff  ∑ jitter: `backoff_ms * (2 ** attempt) + random_jitter`
   - Threading-based TTL    µ   ª ñ ∑   Ü ñ è  ¥ ª è    ∏ Ω Ö   æ Ω Ω æ ≥ æ  ∫ æ Ω Ç µ ∫   Ç É
   -  ü ñ ¥ Ç   ∏ º ∫      ñ ∑ Ω ∏ Ö TTL  ¥ ª è    ñ ∑ Ω ∏ Ö  Ç ∏   ñ ≤  æ   µ     Ü ñ π (entry/bracket/cancel)

4. ** Ü Ω Ç µ ≥     Ü ñ è  ≤ HTTP  ∑     ∏ Ç ∏** (`binance_execution_adapter.py`):
   - `_place_binance_order()`:  ¥ æ ¥   Ω æ TTL  ≤ ∏ ± ñ    ∑   ª µ ∂ Ω æ  ≤ ñ ¥ order type
   - `_cancel_binance_order()`:  ¥ æ ¥   Ω æ TTL  ¥ ª è cancel  æ   µ     Ü ñ π
   -  í ∏ ¥   ª µ Ω æ    É á Ω É retry  ª æ ≥ ñ ∫ É  ¥ ª è timestamp    æ º ∏ ª æ ∫ (-1021) -  Ç µ   µ    á µ   µ ∑ TTL/retry
   -  ó   ª ∏ à µ Ω æ      µ Ü ∏ Ñ ñ á Ω É  æ ±   æ ± ∫ É  ¥ ª è insufficient balance (-2010)  Ç   rate limits (-429)

5. ** õ æ ≥ É ≤   Ω Ω è  Ç    º æ Ω ñ Ç æ   ∏ Ω ≥**:
   -  î æ ¥   Ω æ  ª æ ≥ ∏  ¥ ª è TTL  ∑ Ω   á µ Ω å  Ç   retry attempts
   - Thread-safe    µ   ª ñ ∑   Ü ñ è  ∑ proper exception handling
   -  î µ Ç   ª å Ω ñ  ª æ ≥ ∏  ¥ ª è timeout  Ç   retry    Ü µ Ω     ñ ó ≤

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ö æ Ω Ñ ñ ≥ É     Ü ñ è TTL/retry  ¥ æ ¥   Ω    ¥ æ trading.yaml
- ‚úÖ Adapter  ñ Ω ñ Ü ñ   ª ñ ∑ É î TTL/retry  ∑ config
- ‚úÖ  ° ∏ Ω Ö   æ Ω Ω   TTL/retry  ª æ ≥ ñ ∫      µ   ª ñ ∑ æ ≤   Ω    ∑ exponential backoff + jitter
- ‚úÖ  Ü Ω Ç µ ≥   æ ≤   Ω æ  ≤ place_order  Ç   cancel_order  º µ Ç æ ¥ ∏
- ‚úÖ Thread-safe    µ   ª ñ ∑   Ü ñ è  ∑ proper error handling
- ‚úÖ  î µ Ç   ª å Ω µ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è debugging timeout/retry    Ü µ Ω     ñ ó ≤
- ‚úÖ AURORA_HARDENING_V1_TTL_RETRY ( á     Ç ∏ Ω   1)    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π

## 2025-01-XX | RID: AURORA_HARDENING_V1_MARKETDATA_WAL |  ö æ Ω Ç   æ ª å  Ø ∫ æ   Ç ñ MarketData  Ç   WAL Integrity ( ß     Ç ∏ Ω   2)

**WHY**:  î ª è  ∑   ± µ ∑   µ á µ Ω Ω è  Ω   ¥ ñ π Ω æ   Ç ñ    ∏   Ç µ º ∏  Ω µ æ ± Ö ñ ¥ Ω ∏ π  ∫ æ Ω Ç   æ ª å  è ∫ æ   Ç ñ  ≤ Ö ñ ¥ Ω ∏ Ö    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö  Ç    Ü ñ ª ñ   Ω æ   Ç ñ WAL  ¥ ª è  ∑     æ ± ñ ≥   Ω Ω è    æ à ∫ æ ¥ ∂ µ Ω Ω é  ¥   Ω ∏ Ö  Ç    ∑   ± µ ∑   µ á µ Ω Ω è data integrity.

** î Ü á**:
1. **MarketData Quality Control** (`market_data_connector.py`):
   - **Lag Control**:    µ   µ ≤ ñ   ∫    ∑   Ç   ∏ º ∫ ∏  º ñ ∂ event timestamp  Ç    ª æ ∫   ª å Ω ∏ º  á     æ º
     - `max_allowed_lag_ms: 45`  ≤ trading.yaml
     -  í ñ ¥ ∫ ∏ ¥   Ω Ω è    æ ≤ ñ ¥ æ º ª µ Ω å  ∑ lag > 45ms  ∑ WARNING  ª æ ≥   º ∏
     -  ü µ   µ ≤ ñ   ∫    ¥ ª è  ≤   ñ Ö  Ç ∏   ñ ≤  ¥   Ω ∏ Ö: bookTicker, trade, depthUpdate
   - **Sequence Control  ¥ ª è Order Book**:  ≤ ñ ¥   Ç µ ∂ µ Ω Ω è sequence numbers  ≤ depthUpdate
     -  ó ± µ   µ ∂ µ Ω Ω è `last_final_update_id`  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ    ∏ º ≤ æ ª É
     -  ü µ   µ ≤ ñ   ∫   continuity: `event['U'] <= last_final_update_id + 1`
     -  î µ Ç µ ∫ Ü ñ è gap' ñ ≤  Ç    ñ Ω ñ Ü ñ é ≤   Ω Ω è `CMD:RESYNC_ORDERBOOK`  ¥ ª è    µ   ∏ Ω Ö   æ Ω ñ ∑   Ü ñ ó
     -  Ü ≥ Ω æ   É ≤   Ω Ω è stale    æ ≤ ñ ¥ æ º ª µ Ω å (final_update_id <= last_final_update_id)

2. **WAL Hash-Chain Integrity** (`wal.py`, `replay.py`):
   - **Enhanced Append**: SHA256 hash-chain  ∑ `_prev`  Ç   `_hash`    æ ª è º ∏
     - `_calculate_record_hash()`  Ñ É Ω ∫ Ü ñ è  ¥ ª è  ∫ æ Ω   ∏   Ç µ Ω Ç Ω æ ≥ æ hashing
     -  ö æ ∂ µ Ω  ∑     ∏    º ñ   Ç ∏ Ç å hash    æ   µ   µ ¥ Ω å æ ≥ æ  ∑     ∏   É
     - Atomic writes  ∑ file locking  ¥ ª è integrity
   - **Integrity Verification      ∏ Replay**:    µ   µ ≤ ñ   ∫   hash-chain    ñ ¥  á      á ∏ Ç   Ω Ω è
     - `_verify_wal_hash_chain_integrity()`  ¥ ª è chronological    µ   µ ≤ ñ   ∫ ∏
     -  ü µ   µ ≤ ñ   ∫   `record['_prev'] == expected_previous_hash`
     -  ü µ   µ ≤ ñ   ∫   `record['_hash'] == calculated_hash(record_content)`
     - CRITICAL  ª æ ≥ ∏      ∏  ≤ ∏ è ≤ ª µ Ω Ω ñ corruption
   - **Merkle Root**:  ¥ ª è  ¥ æ ¥   Ç ∫ æ ≤ æ ó integrity    µ   µ ≤ ñ   ∫ ∏

3. ** ¢ µ   Ç É ≤   Ω Ω è**:
   - **MarketData Tests** (`test_market_data.py`):
     - `test_lag_control_discards_stale_data`:    µ   µ ≤ ñ   ∫    ≤ ñ ¥ ∫ ∏ ¥   Ω Ω è stale  ¥   Ω ∏ Ö
     - `test_sequence_control_depth_update`: gap detection  Ç   resync triggering
     - `test_depth_update_stale_sequence_ignored`:  ñ ≥ Ω æ   É ≤   Ω Ω è stale sequences
   - **WAL Tests** (`test_wal_replay.py`):
     - `test_wal_hash_chain_integrity_append`:    µ   µ ≤ ñ   ∫   hash-chain structure
     - `test_wal_hash_chain_integrity_verification`:  É     ñ à Ω    ≤ µ   ∏ Ñ ñ ∫   Ü ñ è valid chain
     - `test_wal_hash_chain_corruption_detection`:  ¥ µ Ç µ ∫ Ü ñ è _prev hash corruption
     - `test_wal_record_hash_mismatch_detection`:  ¥ µ Ç µ ∫ Ü ñ è content corruption

4. ** ö æ Ω Ñ ñ ≥ É     Ü ñ è** (`trading.yaml`):
   -  î æ ¥   Ω æ `market_data.max_allowed_lag_ms: 45`
   -  î æ ¥   Ω æ `market_data.websocket_streams: ['bookTicker', 'trade']`
   -  î æ ¥   Ω æ `market_data.keep_alive_interval: 1.0`

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ Lag control  ≤ ñ ¥ ∫ ∏ ¥   î  ∑     Ç     ñ ª ñ    ∏ Ω ∫ æ ≤ ñ  ¥   Ω ñ (>45ms)  ∑  ¥ µ Ç   ª å Ω ∏ º ∏  ª æ ≥   º ∏
- ‚úÖ Sequence control  ¥ µ Ç µ ∫ Ç É î gaps  ≤ order book updates  Ç    ñ Ω ñ Ü ñ é î    µ   ∏ Ω Ö   æ Ω ñ ∑   Ü ñ é
- ‚úÖ WAL hash-chain  ∑   ± µ ∑   µ á É î tamper-evident storage  ∑ SHA256 integrity
- ‚úÖ Replay  ≤ µ   ∏ Ñ ñ ∫ É î hash-chain integrity  ∑ CRITICAL  ª æ ≥   º ∏      ∏ corruption
- ‚úÖ  ü æ ≤ Ω ∏ π  Ω   ± ñ   unit  Ç µ   Ç ñ ≤    æ ∫   ∏ ≤   î  ≤   ñ edge cases
- ‚úÖ  ö æ Ω Ñ ñ ≥ É     Ü ñ è  ñ Ω Ç µ ≥   æ ≤   Ω    ≤ trading.yaml  ∑    æ ∑ É º Ω ∏ º ∏ defaults
- ‚úÖ AURORA_HARDENING_V1_MARKETDATA_WAL ( á     Ç ∏ Ω   2)    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π

## 2025-01-XX | RID: AURORA_HARDENING_V1_CIRCUIT_BREAKER |  † µ   ª ñ ∑   Ü ñ è Circuit Breaker  ¥ ª è Failure Isolation ( ß     Ç ∏ Ω   3)

**WHY**:  î ª è  ∑     æ ± ñ ≥   Ω Ω è  ∫     ∫   ¥ Ω ∏ Ö  ∑ ± æ ó ≤  Ç      µ   µ ≤   Ω Ç   ∂ µ Ω Ω è  ∑ æ ≤ Ω ñ à Ω å æ ≥ æ API Binance      ∏  Ç   ∏ ≤   ª ∏ Ö      æ ± ª µ º   Ö  Ω µ æ ± Ö ñ ¥ Ω ∏ π circuit breaker      Ç µ   Ω  ¥ ª è    ≤ Ç æ º   Ç ∏ á Ω æ ó  ñ ∑ æ ª è Ü ñ ó  ≤ ñ ¥  ∑ ± æ ó ≤.

** î Ü á**:

1. ** í ∏ ± ñ    Ç    ñ Ω Ç µ ≥     Ü ñ è  ± ñ ± ª ñ æ Ç µ ∫ ∏ Circuit Breaker**:
   -  í ∏ ±     Ω æ `pybreaker`  è ∫  ≥ æ Ç æ ≤ É  ± ñ ± ª ñ æ Ç µ ∫ É  ∑    ñ ¥ Ç   ∏ º ∫ æ é asyncio  Ç   advanced features
   -  í   Ç   Ω æ ≤ ª µ Ω æ pybreaker==1.4.1  á µ   µ ∑ pip
   -  Ü Ω Ç µ ≥   æ ≤   Ω æ  ≤ BinanceExecutionAdapter  è ∫ circuit_breaker    Ç   ∏ ± É Ç

2. ** ö æ Ω Ñ ñ ≥ É     Ü ñ è Circuit Breaker** (`trading.yaml`):
   ```yaml
   execution:
     circuit_breaker:
       fail_max: 5                    #  ö ñ ª å ∫ ñ   Ç å    æ º ∏ ª æ ∫  ¥ ª è  ≤ ñ ¥ ∫   ∏ Ç Ç è
       reset_timeout_sec: 30          #  ß      É OPEN    Ç   Ω ñ    µ   µ ¥ HALF_OPEN
       exclude:                       #  í ∏ ∫ ª é á µ Ω Ω è,  è ∫ ñ  ù ï      Ö É é Ç å   è    æ º ∏ ª ∫   º ∏
         - 'binance.error.ClientError:.*-2010'  # Insufficient balance
         - 'binance.error.ClientError:.*-1021'  # Timestamp out of window
       open_threshold_pct: 20         #  í ñ ¥ ∫   ∏ Ç ∏      ∏ >20%    æ º ∏ ª æ ∫  É  ≤ ñ ∫ Ω ñ
       error_rate_window_sec: 60      #  í ñ ∫ Ω æ  ¥ ª è    æ ∑     Ö É Ω ∫ É error rate
       half_open_attempts: 3          #  ¢ µ   Ç æ ≤ ñ  ≤ ∏ ∫ ª ∏ ∫ ∏  É HALF_OPEN    Ç   Ω ñ
   ```
   -  û Ω æ ≤ ª µ Ω æ `aurora_trading.schema.json`  ∑  ≤   ª ñ ¥   Ü ñ î é  ≤   ñ Ö          º µ Ç   ñ ≤

3. ** û ± ≥ æ   Ç   Ω Ω è  ∫   ∏ Ç ∏ á Ω ∏ Ö API  ≤ ∏ ∫ ª ∏ ∫ ñ ≤**:
   - `place_order` ‚Üí `_place_binance_order()`  æ ± ≥ æ   Ω É Ç æ  ≤ `circuit_breaker.call()`
   - `cancel_order` ‚Üí `_cancel_binance_order()`  æ ± ≥ æ   Ω É Ç æ    Ω   ª æ ≥ ñ á Ω æ
   - API calls  Ç µ   µ    ∫ ∏ ¥   é Ç å RuntimeError      ∏    æ º ∏ ª ∫   Ö  ¥ ª è circuit breaker counting
   - CircuitBreakerError  ª æ ≤ ∏ Ç å   è  Ç      µ   µ Ç ≤ æ   é î Ç å   è  Ω    ∑   æ ∑ É º ñ ª ñ    æ ≤ ñ ¥ æ º ª µ Ω Ω è

4. ** ° ª É Ö   á ñ    Ç   Ω É  ¥ ª è  º æ Ω ñ Ç æ   ∏ Ω ≥ É**:
   -  ° Ç ≤ æ   µ Ω æ `CircuitBreakerListener`  ∫ ª      ∑  º µ Ç æ ¥   º ∏ `state_change()`
   -  õ æ ≥ É î WARNING      ∏    µ   µ Ö æ ¥ ñ  ≤ OPEN    Ç   Ω
   -  õ æ ≥ É î INFO      ∏    µ   µ Ö æ ¥ ñ  ≤ HALF_OPEN  Ç   CLOSED    Ç   Ω ∏
   -  ê ≤ Ç æ º   Ç ∏ á Ω æ  ¥ æ ¥   î Ç å   è      ∏  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ ó circuit breaker

5. ** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è  ∑  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó**:
   - `initialize_circuit_breaker_config()`  º µ Ç æ ¥  ¥ ª è runtime config updates
   -  Ü Ω Ç µ ≥   æ ≤   Ω æ  ≤ `fsm.py`    ñ   ª è TTL/retry  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ ó
   - Graceful fallback  Ω   defaults      ∏  ≤ ñ ¥   É Ç Ω æ   Ç ñ  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó

6. **Unit  Ç µ   Ç É ≤   Ω Ω è**:
   - ‚úÖ `test_circuit_breaker_initialization`:    µ   µ ≤ ñ   ∫   default config
   - ‚úÖ `test_initialize_circuit_breaker_config`: config update functionality
   - ‚úÖ `test_circuit_breaker_blocks_after_failures`: OPEN    Ç   Ω    ñ   ª è 5    æ º ∏ ª æ ∫
   - ‚úÖ `test_circuit_breaker_cancel_blocks_after_failures`:  ± ª æ ∫ É ≤   Ω Ω è cancel  É OPEN
   - ‚úÖ `test_circuit_breaker_excludes_insufficient_balance`:  ≤ ∏ ∫ ª é á µ Ω Ω è -2010    æ º ∏ ª æ ∫
   - ‚úÖ `test_circuit_breaker_half_open_recovery`:  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    ñ   ª è  É     ñ à Ω æ ≥ æ  Ç µ   Ç É
   - ‚úÖ `test_circuit_breaker_state_logging`:  º æ Ω ñ Ç æ   ∏ Ω ≥  ∑ º ñ Ω    Ç   Ω É

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ Circuit breaker  ñ ∑ æ ª é î  ≤ ñ ¥  ∑ ± æ ó ≤ Binance API    ñ   ª è 5    æ     ñ ª å    æ º ∏ ª æ ∫
- ‚úÖ  ê ≤ Ç æ º   Ç ∏ á Ω µ  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è  á µ   µ ∑ 30    µ ∫ É Ω ¥  ∑  Ç µ   Ç æ ≤ ∏ º ∏  ≤ ∏ ∫ ª ∏ ∫   º ∏
- ‚úÖ  í ∏ ∫ ª é á µ Ω Ω è  Ω µ ∫   ∏ Ç ∏ á Ω ∏ Ö    æ º ∏ ª æ ∫ (-2010 insufficient balance)  ∑ counting
- ‚úÖ  ü æ ≤ Ω µ unit  Ç µ   Ç É ≤   Ω Ω è  ∑ 7  Ç µ   Ç   º ∏,  ≤   ñ      æ Ö æ ¥ è Ç å
- ‚úÖ  ö æ Ω Ñ ñ ≥ É     Ü ñ è  ñ Ω Ç µ ≥   æ ≤   Ω    ≤ trading.yaml  ∑ JSON schema  ≤   ª ñ ¥   Ü ñ î é
- ‚úÖ  ú æ Ω ñ Ç æ   ∏ Ω ≥    Ç   Ω É  ∑  ¥ µ Ç   ª å Ω ∏ º ∏  ª æ ≥   º ∏
- ‚úÖ AURORA_HARDENING_V1_CIRCUIT_BREAKER ( á     Ç ∏ Ω   3)    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π
- ‚úÖ **AURORA_HARDENING_V1  ó ê í ï † ® ï ù û  ü û í ù Ü ° ¢ Æ!** üõ°Ô∏è‚ö°üîß

** ù ê ° ¢ £ ü ù Ü  ö † û ö ò**:
- AURORA_SCENARIO_TESTING_V1:    æ ∑ à ∏   µ Ω µ  Ç µ   Ç É ≤   Ω Ω è    Ü µ Ω     ñ ó ≤
- AURORA_TESTNET_PREP_V1:    ñ ¥ ≥ æ Ç æ ≤ ∫    ¥ æ  ∑     É   ∫ É  Ω   testnet
- Performance benchmarking  ¥ ª è  ≤   ñ Ö hardening features

** ù ê ° ¢ £ ü ù Ü  ö † û ö ò**:
- MarketData quality control (lag detection, sequence validation)
- WAL integrity verification (SHA256 hash-chain)
- Circuit breaker implementation
- Unit/integration  Ç µ   Ç ∏  ¥ ª è TTL/retry  ª æ ≥ ñ ∫ ∏

## 2025-01-XX | RID: AURORA_MANAGE_FEATURES_V1 |  † µ   ª ñ ∑   Ü ñ è  £       ≤ ª ñ Ω Ω è  ü æ ∑ ∏ Ü ñ î é  ∑  ë   µ ∫ µ Ç   º ∏  Ç   Trailing Stop

**WHY**:  î ª è  Ω   ¥ ñ π Ω æ ≥ æ  É       ≤ ª ñ Ω Ω è  ≤ ñ ¥ ∫   ∏ Ç ∏ º ∏    æ ∑ ∏ Ü ñ è º ∏  Ω µ æ ± Ö ñ ¥ Ω      ≤ Ç æ º   Ç ∏ ∑   Ü ñ è SL/TP  ±   µ ∫ µ Ç ñ ≤  ∑ OCO- µ º É ª è Ü ñ î é  Ç   trailing stop  Ñ É Ω ∫ Ü ñ æ Ω   ª æ º,  â æ  ≤ ∏       ≤ ª è î  ¥ µ Ñ µ ∫ Ç ∏ D5 ( ≤ ñ ¥   É Ç Ω ñ   Ç å bracket management)  Ç   D6 (no trailing stops).

** î Ü á**:
1. ** † æ ∑ à ∏   µ Ω æ  ∫ æ Ω Ñ ñ ≥ É     Ü ñ é** (`trading.yaml`, `aurora_trading.schema.json`):
   -  î æ ¥   Ω æ    µ ∫ Ü ñ ó `brackets` (enable, reduce_only, oco_emulation, sl/tp modes, ATR/bps calculation)
   -  î æ ¥   Ω æ    µ ∫ Ü ñ ó `trailing` (enable, activation_profit_atr_k, step_bps, cooldown_sec)
   -  í   ª ñ ¥ æ ≤   Ω æ    Ö µ º ∏ JSON  ¥ ª è  ≤   ñ Ö  Ω æ ≤ ∏ Ö          º µ Ç   ñ ≤

2. ** † µ   ª ñ ∑ æ ≤   Ω æ Bracket Management  ≤ ManageFlowFSM** (`fsm_manage.py`):
   -  î æ ¥   Ω æ    Ç   Ω ∏: BRACKETS_PENDING ‚Üí BRACKETS_PLACED
   -  † æ ∑     Ö É Ω æ ∫ SL/TP  Ü ñ Ω  Ω    æ   Ω æ ≤ ñ entry_price + ATR/bps  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó
   - Immediate placement    ñ   ª è FILL: DEC:PLACE_ORDER  ¥ ª è STOP_MARKET (SL)  Ç   LIMIT (TP)
   - OCO- µ º É ª è Ü ñ è: SL fill ‚Üí DEC:CANCEL_ORDER  ¥ ª è TP, TP fill ‚Üí cancel SL
   -  û ±   æ ± ∫   partial fills  ∑ quantity adjustment (cancel + replace)

3. ** † µ   ª ñ ∑ æ ≤   Ω æ Trailing Stop** (`fsm_manage.py`):
   -  ê ∫ Ç ∏ ≤   Ü ñ è      ∏  ¥ æ   è ≥ Ω µ Ω Ω ñ profit threshold (activation_profit_atr_k * ATR)
   -  î ∏ Ω   º ñ á Ω µ    µ   µ º ñ â µ Ω Ω è SL: cancel    Ç     æ ≥ æ + place  Ω æ ≤ æ ≥ æ  ∑ step_bps
   - Cooldown mechanism  ¥ ª è  ∑     æ ± ñ ≥   Ω Ω è  Ω   ¥ ª ∏ à ∫ æ ≤ ∏ Ö adjust
   - ATR-based    ± æ fixed BPS trailing modes

4. ** † æ ∑ à ∏   µ Ω æ BinanceExecutionAdapter** (`binance_execution_adapter.py`):
   -  î æ ¥   Ω æ `cancel_order()`  º µ Ç æ ¥  ∑ DELETE /fapi/v1/order API
   -  † æ ∑ à ∏   µ Ω æ `place_order()`  ¥ ª è LIMIT/STOP_MARKET  æ   ¥ µ   ñ ≤
   -  ü ñ ¥ Ç   ∏ º ∫   reduceOnly, stopPrice, newClientOrderId          º µ Ç   ñ ≤
   - Error handling  ¥ ª è cancel operations

5. ** î æ ¥   Ω æ  ∫ æ º   ª µ ∫   Ω µ  Ç µ   Ç É ≤   Ω Ω è** (`test_fsm_manage.py`):
   -  ¢ µ   Ç ∏ bracket placement    ñ   ª è fill
   -  ¢ µ   Ç ∏ OCO emulation (SL fill cancels TP)
   -  ¢ µ   Ç ∏ trailing stop activation  Ç   adjustment
   -  ¢ µ   Ç ∏ cooldown  Ç   edge cases
   - ‚úÖ 13/13  Ç µ   Ç ñ ≤      æ Ö æ ¥ è Ç å  É     ñ à Ω æ (100% success rate)

6. ** ° ∏ Ω Ö   æ Ω ñ ∑ æ ≤   Ω æ  Ñ   π ª ∏**:
   -  ö æ   ñ é ≤   Ω Ω è  ≤   ñ Ö  ∑ º ñ Ω  ∑ `apps/`  ¥ æ `vfoundation/`

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ Bracket orders    æ ∑ º ñ â É é Ç å   è    ≤ Ç æ º   Ç ∏ á Ω æ    ñ   ª è  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó
- ‚úÖ OCO- µ º É ª è Ü ñ è        Ü é î:  æ ¥ ∏ Ω  ±   µ ∫ µ Ç fill ‚Üí  ñ Ω à ∏ π    ∫     æ ≤ É î Ç å   è
- ‚úÖ Trailing stop    ∫ Ç ∏ ≤ É î Ç å   è      ∏ profit threshold  Ç      µ   µ º ñ â É î Ç å   è  ¥ ∏ Ω   º ñ á Ω æ
- ‚úÖ Partial fill handling  ∑ quantity adjustment
- ‚úÖ Cancel order API  ñ Ω Ç µ ≥   æ ≤   Ω æ  ≤ BinanceExecutionAdapter
- ‚úÖ 13/13  Ç µ   Ç ñ ≤      æ Ö æ ¥ è Ç å  É     ñ à Ω æ (100% success rate)
- ‚úÖ AURORA_MANAGE_FEATURES_V1    æ ≤ Ω ñ   Ç é      æ Ç µ   Ç æ ≤   Ω æ  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  ñ Ω Ç µ ≥     Ü ñ ó

** ê † ¢ ï § ê ö ¢ ò**:
- FSM: `apps/reference/domains/execution_position/fsm_manage.py`
- Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py`
- Config: `config/aurora/trading.yaml`, `config/_schemas/aurora_trading.schema.json`
- Tests: `tests/test_fsm_manage.py`

---

## 2025-01-XX | RID: AURORA_SYMBOL_SPECS_FIX_V1 |  í ∏       ≤ ª µ Ω Ω è DecisionMaking    ñ   ª è  Ü Ω Ç µ ≥     Ü ñ ó  °   µ Ü ∏ Ñ ñ ∫   Ü ñ π  ° ∏ º ≤ æ ª ñ ≤

**WHY**:  ü ñ   ª è  ñ Ω Ç µ ≥     Ü ñ ó AURORA_SYMBOL_SPECS_V1  ∑   ª ∏ à ∏ ª ∏   å    æ   ∏ ª   Ω Ω è  Ω    ∑     Ç     ñ ª É  ∑ º ñ Ω Ω É `lot_step`  ∑   º ñ   Ç å `step_size`  É DecisionMaking,  â æ        ∏ á ∏ Ω è ª æ NameError  Ç        ¥ ñ Ω Ω è  Ç µ   Ç ñ ≤  ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ.

** î Ü á**:
1. ** í ∏       ≤ ª µ Ω æ  ∑ º ñ Ω Ω ñ  É DecisionMaking** (`decision_making.py`):
   -  † è ¥ æ ∫ 377: `lot_step` ‚Üí `step_size`  É  ¥ ñ   ≥ Ω æ   Ç ∏ á Ω æ º É  ª æ ≥ É ≤   Ω Ω ñ
   -  † è ¥ æ ∫ 452: `lot_step` ‚Üí `step_size`  É qty  æ ∫   É ≥ ª µ Ω Ω ñ  ¥ ª è volatility sizing
   -  † è ¥ æ ∫ 478: `lot_step` ‚Üí `step_size`  É qty  æ ∫   É ≥ ª µ Ω Ω ñ  ¥ ª è mean reversion sizing
   -  û Ω æ ≤ ª µ Ω æ  ∫ æ º µ Ω Ç     ñ: "Floor to lot step" ‚Üí "Floor to step size"

2. ** ° ∏ Ω Ö   æ Ω ñ ∑ æ ≤   Ω æ  Ñ   π ª ∏**:
   -  ö æ   ñ é ≤   Ω Ω è  ≤ ∏       ≤ ª µ Ω å  ∑ `apps/`  ¥ æ `vfoundation/`

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  í   ñ 23  Ç µ   Ç ∏  ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ      æ Ö æ ¥ è Ç å  É     ñ à Ω æ
- ‚úÖ  í   ñ 36  Ç µ   Ç ñ ≤ ( ñ ¥ µ º   æ Ç µ Ω Ç Ω ñ   Ç å +      µ Ü ∏ Ñ ñ ∫   Ü ñ ó    ∏ º ≤ æ ª ñ ≤)      æ Ö æ ¥ è Ç å  É     ñ à Ω æ
- ‚úÖ  ü ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω æ  ∫ æ   µ ∫ Ç Ω ñ   Ç å  ¥ ∏ Ω   º ñ á Ω æ ≥ æ  æ Ç   ∏ º   Ω Ω è      µ Ü ∏ Ñ ñ ∫   Ü ñ π  ñ Ω   Ç   É º µ Ω Ç ñ ≤
- ‚úÖ AURORA_SYMBOL_SPECS_V1    æ ≤ Ω ñ   Ç é      æ Ç µ   Ç æ ≤   Ω æ  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  Ω     Ç É   Ω ∏ Ö  µ Ç     ñ ≤

** ê † ¢ ï § ê ö ¢ ò**:
- Decision: `apps/reference/domains/decision_making/decision_making.py`
- Tests: `tests/test_idempotency_*.py`, `tests/test_fsm_open.py`

---

## 2025-01-XX | RID: AURORA_FSM_TEST_FIX_V1 |  í ∏       ≤ ª µ Ω Ω è  ¢ µ   Ç ñ ≤ FSM Lifecycle

**WHY**: 4      ¥   é á ∏ Ö pytest  Ç µ   Ç      æ   É à É ≤   ª ∏ TDD      ∏ Ω Ü ∏   ∏,  Ω µ  ¥ æ ∑ ≤ æ ª è é á ∏    ñ ¥ Ç ≤ µ   ¥ ∏ Ç ∏  ∫ æ   µ ∫ Ç Ω ñ   Ç å    µ   ª ñ ∑   Ü ñ ó AURORA_FSM_LIFECYCLE_V1.

** î Ü á**:
1. ** í ∏       ≤ ª µ Ω æ  ñ º   æ   Ç      ñ æ   ∏ Ç µ Ç** (`conftest.py`):
   -  ü µ   µ   Ç   ≤ ª µ Ω æ sys.path: apps/ ‚Üí vfoundation/  ¥ ª è  ∑   ≤   Ω Ç   ∂ µ Ω Ω è  æ Ω æ ≤ ª µ Ω ∏ Ö FSM
   -  ° ∏ Ω Ö   æ Ω ñ ∑ æ ≤   Ω æ  Ñ   π ª ∏  º ñ ∂ apps/  Ç   vfoundation/

2. ** í ∏       ≤ ª µ Ω æ  Ç µ   Ç É ≤   Ω Ω è ExecPosFSM** (`test_fsm_close.py`, `test_fsm_manage.py`):
   -  ° Ç ≤ æ   µ Ω æ MockConfig  ∫ ª      ∑ trading    Ç   ∏ ± É Ç æ º  Ç   get()  º µ Ç æ ¥ æ º
   -  î æ ¥   Ω æ required src/dst    æ ª è  ¥ æ Message  æ ±' î ∫ Ç ñ ≤  ¥ ª è recovery  Ç µ   Ç ñ ≤

3. ** í ∏       ≤ ª µ Ω æ payload  Ç µ   Ç ñ ≤** (`test_fsm_close.py`):
   -  î æ ¥   Ω æ `filled_qty > 0`  ¥ æ  ≤   ñ Ö FILL/PARTIAL_FILL    æ ≤ ñ ¥ æ º ª µ Ω å
   -  í ∏       ≤ ª µ Ω æ test_manage_flow_on_fill_opens_position: OPENED ‚Üí TRACKING

4. ** ü µ   µ ≤ ñ   µ Ω æ FSM  ª æ ≥ ñ ∫ É**:
   - CloseFlowFSM: FLAT ‚Üí OPENED      ∏ filled_qty > 0
   - ManageFlowFSM: FLAT ‚Üí TRACKING      ∏ FILL/PARTIAL_FILL (immediate activation)
   - Portfolio state recovery:    ∏ º É ª è Ü ñ è fill events  ¥ ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  í   ñ 20  Ç µ   Ç ñ ≤ FSM      æ Ö æ ¥ è Ç å  É     ñ à Ω æ
- ‚úÖ  ü ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω æ  ∫ æ   µ ∫ Ç Ω ñ   Ç å PARTIAL_FILL  æ ±   æ ± ∫ ∏  Ç   immediate activation
- ‚úÖ  í   ª ñ ¥ æ ≤   Ω æ portfolio state recovery  º µ Ö   Ω ñ ∑ º
- ‚úÖ AURORA_FSM_LIFECYCLE_V1    æ ≤ Ω ñ   Ç é      æ Ç µ   Ç æ ≤   Ω æ  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  Ω     Ç É   Ω ∏ Ö  µ Ç     ñ ≤

** ê † ¢ ï § ê ö ¢ ò**:
- Tests: `tests/test_fsm_close.py`, `tests/test_fsm_manage.py`
- Config: `conftest.py`
- FSM: `vfoundation/apps/reference/domains/execution_position/fsm_*.py`

---

## 2025-10-23 | RID: AURORA_ACCOUNT_BALANCE_TEST_V1 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  ¢ µ   Ç AccountConnector

**WHY**:  ó   ± µ ∑   µ á ∏ Ç ∏  Ω   ¥ ñ π Ω ñ   Ç å  ≤ ∏       ≤ ª µ Ω Ω è  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó AccountConnector  á µ   µ ∑    ≤ Ç æ º   Ç ∏ ∑ æ ≤   Ω ∏ π  Ç µ   Ç,  â æ    µ   µ ≤ ñ   è î polling,    æ ¥ ñ ó  Ç    æ ±   æ ± ∫ É    æ º ∏ ª æ ∫.

** î Ü á**:
1. ** ° Ç ≤ æ   µ Ω æ  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç** (`tests/integration/test_account_connector.py`):
   - `test_account_connector_initialization`:    µ   µ ≤ ñ   è î  ∫ æ   µ ∫ Ç Ω É  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ é  ∑ config
   - `test_account_connector_polling_and_event_emission`:    µ   µ ≤ ñ   è î polling API  Ç    ≥ µ Ω µ     Ü ñ é EVT:ACCOUNT_UPDATE_RECEIVED
   - `test_account_connector_error_handling`:    µ   µ ≤ ñ   è î graceful handling    æ º ∏ ª æ ∫ API
   - `test_account_connector_graceful_shutdown`:    µ   µ ≤ ñ   è î  ∑ É   ∏ Ω ∫ É polling thread
   - `test_account_connector_config_defaults`:    µ   µ ≤ ñ   è î  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è defaults

2. ** ¢ µ   Ç æ ≤      Ç   É ∫ Ç É    **:
   -  í ∏ ∫ æ   ∏   Ç   Ω æ pytest fixtures  ¥ ª è mock config  Ç   Binance client
   - Mock FSMCore  ¥ ª è  ≤ ñ ¥   Ç µ ∂ µ Ω Ω è    æ ¥ ñ π
   -  ® ≤ ∏ ¥ ∫ ∏ π poll_interval (1    µ ∫)  ¥ ª è  Ç µ   Ç ñ ≤
   -  ü µ   µ ≤ ñ   ∫   fail-closed    æ ≤ µ ¥ ñ Ω ∫ ∏      ∏    æ º ∏ ª ∫   Ö

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ¢ µ   Ç    æ ∫   ∏ ≤   î  ∫ ª é á æ ≤ ñ    Ü µ Ω     ñ ó: init, polling, events, errors, shutdown
-  ó   ± µ ∑   µ á É î    µ ≥   µ   ñ π Ω ∏ π  ∑   Ö ∏   Ç  ¥ ª è account_balance domain
-  ü ñ ¥ Ç ≤ µ   ¥ ∂ É î,  â æ AccountConnector        Ü é î  ∑  Ω æ ≤ æ é  ∫ æ Ω Ñ ñ ≥ É     Ü ñ î é

** ê † ¢ ï § ê ö ¢ ò**:
- Test: `tests/integration/test_account_connector.py`

---

## 2025-10-23 | RID: AURORA_ACCOUNT_BALANCE_FIX_V1 |  í ∏       ≤ ª µ Ω Ω è  ö æ Ω Ñ ñ ≥ É     Ü ñ ó Account Balance

**WHY**:  í ñ ¥   É Ç Ω ñ   Ç å  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó account_balance      ∏ ∑ ≤ æ ¥ ∏ Ç å  ¥ æ  Ω µ ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ ó AccountConnector,  â æ        ∏ á ∏ Ω è î  Ω µ ∫ æ Ω Ç   æ ª å æ ≤   Ω µ  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π  á µ   µ ∑  ∑     Ç     ñ ª ñ  ¥   Ω ñ  º     ∂ ñ.

** î Ü á**:
1. **AuroraConfig** (`config_loader.py`):
   -  î æ ¥   Ω æ    æ ª µ `account_balance: Dict[str, Any]`
   -  û Ω æ ≤ ª µ Ω æ `to_dict()`  ¥ ª è  ≤ ∫ ª é á µ Ω Ω è account_balance
   -  î æ ¥   Ω æ  ∑   ≤   Ω Ç   ∂ µ Ω Ω è `account_balance_config = trading_config.get('account_balance', {})`

2. **Trading Config** (`trading.yaml`):
   -  î æ ¥   Ω æ    µ ∫ Ü ñ é `account_balance`:
     ```yaml
     account_balance:
       poll_interval_seconds: 15
       symbols: ["BTCUSDT", "ETHUSDT"]
     ```

3. **AccountConnector** (`account_connector.py`):
   -  î æ ¥   Ω æ `self.account_balance_config = config.account_balance`
   -  ó º ñ Ω µ Ω æ `self.update_interval = self.account_balance_config.get('poll_interval_seconds', 30)`

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- AccountConnector  Ç µ   µ    ñ Ω ñ Ü ñ   ª ñ ∑ É î Ç å   è  ∑ poll_interval=15    µ ∫
- Portfolio  æ Ω æ ≤ ª é î Ç å   è    µ ≥ É ª è   Ω æ,  ∑     æ ± ñ ≥   é á ∏    æ ≤ Ç æ   Ω ∏ º intents  á µ   µ ∑  ∑     Ç     ñ ª É  º     ∂ É
- POSITION_GATE  æ Ç   ∏ º É î    ∫ Ç É   ª å Ω ñ  ¥   Ω ñ      æ    æ ∑ ∏ Ü ñ ó

** ê † ¢ ï § ê ö ¢ ò**:
- Config: `apps/reference/config_loader.py`, `config/aurora/trading.yaml`
- Logic: `apps/reference/domains/account_balance/account_connector.py`

---

## 2025-10-23 | RID: AURORA_IDEMPOTENCY_V1 |  Ü ¥ µ º   æ Ç µ Ω Ç Ω ñ   Ç å  û   ¥ µ   ñ ≤

**WHY**:  ó     æ ± ñ ≥ Ç ∏  ¥ É ± ª ñ ∫   Ç   º  æ   ¥ µ   ñ ≤  á µ   µ ∑  ≥ µ Ω µ     Ü ñ é  É Ω ñ ∫   ª å Ω æ ≥ æ `idempotent_key`  Ç    ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  π æ ≥ æ  è ∫ `newClientOrderId`  É Binance API.

** î Ü á**:
1. ** ö æ Ω Ñ ñ ≥ É     Ü ñ è**:  î æ ¥   Ω æ    µ ∫ Ü ñ é `idempotency`  É `trading.yaml`:
   ```yaml
   idempotency:
     enabled: true
     key_template: "{symbol}:{side}:{ts_bucket_ms}"
     ts_bucket_ms: 1000  # 1-second buckets
     ttl_sec: 120  # 2-minute TTL
   ```

2. ** ì µ Ω µ     Ü ñ è  ö ª é á  ** (`decision_making.py`):
   -  î æ ¥   Ω æ  ñ º   æ   Ç ∏: `hashlib`, `time`
   -  ì µ Ω µ     Ü ñ è `idempotent_key`  Ω    æ   Ω æ ≤ ñ  à   ± ª æ Ω É: `{symbol}:{side}:{ts_bucket}`
   -  • µ à É ≤   Ω Ω è SHA256 ‚Üí    µ   à ñ 32 hex    ∏ º ≤ æ ª ∏ ( ≤ ñ ¥   æ ≤ ñ ¥   î Binance  æ ± º µ ∂ µ Ω Ω é 36 chars)
   -  î æ ¥   Ω æ    æ ª µ `idempotent_key`  ¥ æ payload `EVT:TRADE_INTENT_PROPOSED`
   - Fallback:  è ∫ â æ `enabled=False`,  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î Ç å   è `{symbol}_{timestamp_ms}`

3. ** ü µ   µ ¥   á    ß µ   µ ∑ Bridge** (`main.py`):
   -  û Ω æ ≤ ª µ Ω æ `on_trade_intent_proposed()`:  ∫ æ   ñ é ≤   Ω Ω è `idempotent_key`  ∑ event payload  É `CMD:OPEN`
   -  î æ ¥   Ω æ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è  Ç   µ π   ñ Ω ≥ É  ∫ ª é á  

4. ** í ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤  ê ¥     Ç µ   ñ** (`binance_execution_adapter.py`):
   -  û Ω æ ≤ ª µ Ω æ `place_order()`:  ≤ ∏ Ç è ≥ `idempotent_key`  ∑ payload
   -  û Ω æ ≤ ª µ Ω æ `_place_binance_order()`:          º µ Ç   `idempotent_key: Optional[str]`
   -  Ø ∫ â æ  ∫ ª é á      ∏   É Ç Ω ñ π ‚Üí  ¥ æ ¥   î Ç å   è  è ∫ `newClientOrderId`  ¥ æ Binance API request
   -  õ æ ≥ É ≤   Ω Ω è: `"Using idempotent newClientOrderId: {key}"`

5. ** ¢ µ   Ç ∏** (`test_idempotency_key_generation.py`):
   - ‚úÖ `test_idempotent_key_generated_when_enabled`:    µ   µ ≤ ñ   è î  ≥ µ Ω µ     Ü ñ é SHA256 hash (32 chars)
   - ‚úÖ `test_idempotent_key_fallback_when_disabled`:    µ   µ ≤ ñ   è î fallback  Ñ æ   º   Ç `{symbol}_{ts}`
   - ‚úÖ `test_idempotent_key_uniqueness_across_symbols`:    ñ ∑ Ω ñ  ∫ ª é á ñ  ¥ ª è BTCUSDT/ETHUSDT
   - ** † µ ∑ É ª å Ç   Ç**: 3/3 passed

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ** Ü ¥ µ º   æ Ç µ Ω Ç Ω ñ   Ç å  Ω      ñ ≤ Ω ñ Binance**:    æ ≤ Ç æ   Ω ñ POST  ∑  æ ¥ Ω   ∫ æ ≤ ∏ º `newClientOrderId`  Ω µ    Ç ≤ æ   é é Ç å  ¥ É ± ª ñ ∫   Ç ñ ≤
- ** £ Ω ñ ∫   ª å Ω ñ   Ç å  ∫ ª é á  **: SHA256 hash  ∑   ± µ ∑   µ á É î collision-free  ∫ ª é á ñ (birthday paradox: ~2^128  ± µ ∑   µ á Ω ñ   Ç å)
- **Time bucketing**: 1-second buckets  ∑     æ ± ñ ≥   é Ç å  ¥ É ± ª ñ ∫   Ç   º  É  º µ ∂   Ö  æ ¥ Ω ñ î ó    µ ∫ É Ω ¥ ∏
- **Backward compatibility**:      ∏ `enabled=false`  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î Ç å   è fallback  ± µ ∑  ≤   ª ∏ ≤ É  Ω      æ ± æ Ç É

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ Ω Ñ ñ ≥: `config/aurora/trading.yaml` (+   µ ∫ Ü ñ è idempotency)
-  õ æ ≥ ñ ∫    ≥ µ Ω µ     Ü ñ ó: `apps/reference/domains/decision_making/decision_making.py` (lines 503-536)
- Bridge: `apps/reference/main.py` (line 107)
- Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py` (lines 226, 260, 349-382)
-  ¢ µ   Ç ∏: `tests/test_idempotency_key_generation.py` (3 tests, all passed)

** ù ê ° ¢ £ ü ù Ü  ö † û ö ò**:
-  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç:    µ   µ ≤ ñ   ∫    ¥ É ± ª ñ ∫   Ç ñ ≤  á µ   µ ∑    ∏ º É ª è Ü ñ é    æ ≤ Ç æ   Ω ∏ Ö `CMD:OPEN`
-  ú æ Ω ñ Ç æ   ∏ Ω ≥:  º µ Ç   ∏ ∫   `duplicate_order_attempts_count` ( è ∫ â æ Binance  ≤ ñ ¥ Ö ∏ ª è î  ∑ `newClientOrderId` collision)

---

## 2025-10-15 | RID: FSMP-P2-T01 |  ö æ Ω Ç     ∫ Ç  ¥ ª è  ¥ æ º µ Ω É feature_engineering

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  Ñ æ   º   ª å Ω ∏ π  ∫ æ Ω Ç     ∫ Ç  ¥ ª è  ¥ æ º µ Ω É feature_engineering  Ω    æ   Ω æ ≤ ñ    Ω   ª ñ ∑ É  ∫ æ ¥ É- ¥ æ Ω æ     aurora/features.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/features/builder.py:    ñ ¥ Ç   ∏ º É î  Ñ ñ á ñ obi, tfi, delta_price, absorption
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/features/sol_crosslink.py:  æ ± á ∏   ª é î  ∫   æ  - ª ñ Ω ∫  ∑ SOL returns
-  ° Ç ≤ æ   µ Ω æ domain_dict.json  ∑  ñ º   æ   Ç æ º EVT:MARKET_TICK_RECEIVED  Ç    µ ∫     æ   Ç æ º EVT:FEATURES_CALCULATED
-  ° Ç ≤ æ   µ Ω æ JSON    Ö µ º É features_calculated_v1.json  ∑    æ ª è º ∏ ts, symbol, features (obi, tfi, delta_price, absorption)

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ö æ Ω Ç     ∫ Ç    Ç ≤ æ   µ Ω æ: apps/reference/domains/feature_engineering/domain_dict.json
-  ° Ö µ º      Ç ≤ æ   µ Ω  : apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json
-  ° Ö µ º    ≤   ª ñ ¥ Ω    Ç    ≤ ñ ¥ æ ±     ∂   î  ª æ ≥ ñ ∫ É  ∑ aurora/features/builder.py

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ Ω Ç     ∫ Ç: apps/reference/domains/feature_engineering/domain_dict.json
-  ° Ö µ º  : apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json

---

## 2025-10-15 | RID: FSMP-P2-T02 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è feature_engineering

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç,  â æ    µ   µ ≤ ñ   è î    ñ ¥   ∏   ∫ É  Ω   EVT:MARKET_TICK_RECEIVED  Ç    ≥ µ Ω µ     Ü ñ é EVT:FEATURES_CALCULATED.

** î Ü á**:
-  ° Ç ≤ æ   ∏ Ç ∏ tests/domains/test_feature_engineering.py  ∑  Ç µ   Ç æ º test_feature_engineering_consumes_tick_and_emits_features
-  † µ   ª ñ ∑ É ≤   Ç ∏  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ é FSMCore, mock listener,    ñ ¥   ∏   ∫ É  Ω   EVT:FEATURES_CALCULATED
-  î æ ¥   Ç ∏  ∫ æ ¥  ¥ ª è  ñ º   æ   Ç É FeatureEngineering ( ± É ¥ µ      ¥   Ç ∏,  ± æ  â µ  Ω µ  ñ   Ω É î)
-  ° Ç ≤ æ   ∏ Ç ∏ fake_market_tick_payload  ∑ ≥ ñ ¥ Ω æ market_tick_v1.json
-  ï º ñ Ç ∏ Ç ∏ EVT:MARKET_TICK_RECEIVED  Ç      µ   µ ≤ ñ   ∏ Ç ∏  ≤ ∏ ∫ ª ∏ ∫ mock listener

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç    Ç ≤ æ   µ Ω æ,      ∏  ∑     É   ∫ É pytest      ¥   î  ∑ ModuleNotFoundError  ¥ ª è FeatureEngineering

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç: tests/domains/test_feature_engineering.py

---

## 2025-10-15 | RID: FSMP-P2-T03 |  † µ   ª ñ ∑   Ü ñ è  ∫ æ º   æ Ω µ Ω Ç   FeatureEngineering

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ∫ ª     FeatureEngineering,  â æ    µ   ª ñ ∑ É î  ª æ ≥ ñ ∫ É    æ ∑     Ö É Ω ∫ É  Ñ ñ á  ∑ aurora/features/  ¥ ª è    æ ± æ Ç ∏  ∑ vFoundation.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/features/builder.py:  ª æ ≥ ñ ∫      æ ∑     Ö É Ω ∫ É obi, tfi, delta_price, absorption
-  ° Ç ≤ æ   µ Ω æ apps/reference/domains/feature_engineering/feature_engineering.py  ∑  ∫ ª     æ º FeatureEngineering
-  † µ   ª ñ ∑ æ ≤   Ω æ __init__  ∑    ñ ¥   ∏   ∫ æ é  Ω   EVT:MARKET_TICK_RECEIVED
-  ú ñ ≥     Ü ñ è  ª æ ≥ ñ ∫ ∏    æ ∑     Ö É Ω ∫ É  Ñ ñ á: obi=(bid-ask)/(bid+ask), tfi=(buy-sell)/(buy+sell), absorption=(buy+sell)/(bid+ask), delta_price=price-prev_price
-  î æ ¥   Ω æ  º µ Ç æ ¥ on_market_tick  ¥ ª è  æ ±   æ ± ∫ ∏    æ ¥ ñ π  Ç      É ± ª ñ ∫   Ü ñ ó EVT:FEATURES_CALCULATED
-  ê ¥     Ç æ ≤   Ω æ  ¥ ª è    æ ± æ Ç ∏  ∑ payload    æ ¥ ñ ó  ∑   º ñ   Ç å RawFeed    Ç   É ∫ Ç É   ∏

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç tests/domains/test_feature_engineering.py      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ
-  ö æ ¥      æ Ö æ ¥ ∏ Ç å ruff  Ç   mypy    µ   µ ≤ ñ   ∫ ∏
-  ü æ ∫   ∏ Ç Ç è  ∫ æ ¥ É feature_engineering.py ‚â•89%

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ¢ µ   Ç      æ Ö æ ¥ ∏ Ç å (3 passed)
- ‚úÖ ruff check: All checks passed
- ‚úÖ mypy --strict: Success: no issues found
- ‚ö†Ô∏è  ü æ ∫   ∏ Ç Ç è: 82% ( Ω µ   æ ∫   ∏ Ç ñ    è ¥ ∫ ∏ -  Ç µ   Ç æ ≤ ∏ π  ∫ ª     FSMCore,  Ñ   ∫ Ç ∏ á Ω µ    æ ∫   ∏ Ç Ç è  ª æ ≥ ñ ∫ ∏ 100%)
-  ö æ ¥  ≥ æ Ç æ ≤ ∏ π  ¥ ª è  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤ vFoundation      Ö ñ Ç µ ∫ Ç É   ñ.

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ ¥: apps/reference/domains/feature_engineering/feature_engineering.py
-  ¢ µ   Ç ∏: tests/domains/test_feature_engineering.py (3  Ç µ   Ç ∏)

---

## 2025-10-15 | RID: FSMP-P1-T03 |  † µ   ª ñ ∑   Ü ñ è MarketDataConnector

**WHY**:  † µ   ª ñ ∑ É ≤   Ç ∏ MarketDataConnector  ∫ ª      ¥ ª è    ñ ¥ ∫ ª é á µ Ω Ω è  ¥ æ Binance WebSocket  Ç    Ç     Ω   Ñ æ   º   Ü ñ ó  ¥   Ω ∏ Ö  ≤ FSM    æ ¥ ñ ó.

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ  ∫ ª     `MarketDataConnector`  ≤ `apps/reference/domains/market_data/market_data_connector.py`  ∑  º µ Ç æ ¥   º ∏ `__init__`, `start()`, `stop()`, `_ws_loop()`, `_process_message()`.
-  Ü Ω Ç µ ≥   æ ≤   Ω æ WebSocket    ñ ¥ ∫ ª é á µ Ω Ω è  á µ   µ ∑ `unicorn_binance_websocket_api`  ∑ fallback  æ ±   æ ± ∫ æ é.
-  † µ   ª ñ ∑ æ ≤   Ω æ  Ç     Ω   Ñ æ   º   Ü ñ é Binance bookTicker    æ ≤ ñ ¥ æ º ª µ Ω å  ≤ FSM    æ ¥ ñ ó `EVT:MARKET_TICK_RECEIVED`  ∑ payload  ∑ ≥ ñ ¥ Ω æ    Ö µ º ∏ `market_tick_v1.json`.
-  î æ ¥   Ω æ    æ Ç æ ∫ æ ≤ É  æ ±   æ ± ∫ É  ¥ ª è  Ω µ ± ª æ ∫ É é á æ ó    æ ± æ Ç ∏.
-  ° Ç ≤ æ   µ Ω æ    æ ∑ à ∏   µ Ω ñ unit  Ç µ   Ç ∏  ¥ ª è  ¥ æ   è ≥ Ω µ Ω Ω è  ≤ ∏   æ ∫ æ ≥ æ    æ ∫   ∏ Ç Ç è  ∫ æ ¥ É.

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ¢ µ   Ç      æ Ö æ ¥ ∏ Ç å (13 passed)
- ‚úÖ ruff check: All checks passed
- ‚úÖ mypy --strict: Success: no issues found
- ‚ö†Ô∏è  ü æ ∫   ∏ Ç Ç è: 87% ( Ü ñ ª å 89%,  Ω µ    æ ∫   ∏ Ç æ 12    è ¥ ∫ ñ ≤  ≤  æ ±   æ ± Ü ñ    æ º ∏ ª æ ∫)
-  ö æ ¥  ≥ æ Ç æ ≤ ∏ π  ¥ æ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤ vFoundation      Ö ñ Ç µ ∫ Ç É   ñ.

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ ¥: `apps/reference/domains/market_data/market_data_connector.py`
-  ¢ µ   Ç ∏: `tests/domains/test_market_data.py` (13  Ç µ   Ç ñ ≤)

---

## 2025-10-15 | RID: FSMP-P1-T02 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è  ¥ æ º µ Ω É market_data

**WHY**:  ù     ∏     Ç ∏  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è MarketDataConnector  ¥ æ    µ   ª ñ ∑   Ü ñ ó  ∫ æ º   æ Ω µ Ω Ç  .

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ  Ñ   π ª `tests/domains/test_market_data.py`  ∑  ∫ ª     æ º `TestMarketDataConnector`.
-  † µ   ª ñ ∑ æ ≤   Ω æ  Ç µ   Ç `test_connector_emits_market_tick_event`  ∑  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ î é FSMCore, mock listener, mocking BinanceWebSocketApiManager,        æ ± æ é  ñ º   æ   Ç É MarketDataConnector  Ç   assertions  ¥ ª è    µ   µ ≤ ñ   ∫ ∏    æ ¥ ñ ó.

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ¢ µ   Ç    Ç ≤ æ   µ Ω æ  Ç        ¥   î  ∑  æ á ñ ∫ É ≤   Ω æ é    æ º ∏ ª ∫ æ é  ñ º   æ   Ç É (MarketDataConnector  Ω µ  ñ   Ω É î).

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç: `tests/domains/test_market_data.py`

---

## 2025-10-15 | RID: FSMP-P1-T02 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è  ¥ æ º µ Ω É market_data

**WHY**:  ù     ∏     Ç ∏  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è MarketDataConnector  ¥ æ    µ   ª ñ ∑   Ü ñ ó  ∫ æ º   æ Ω µ Ω Ç  .

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ  Ñ   π ª `tests/domains/test_market_data.py`  ∑  ∫ ª     æ º `TestMarketDataConnector`.
-  † µ   ª ñ ∑ æ ≤   Ω æ  Ç µ   Ç `test_connector_emits_market_tick_event`  ∑  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ î é FSMCore, mock listener, mocking BinanceWebSocketApiManager,        æ ± æ é  ñ º   æ   Ç É MarketDataConnector  Ç   assertions  ¥ ª è    µ   µ ≤ ñ   ∫ ∏    æ ¥ ñ ó.

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ¢ µ   Ç    Ç ≤ æ   µ Ω æ  Ç        ¥   î  ∑  æ á ñ ∫ É ≤   Ω æ é    æ º ∏ ª ∫ æ é  ñ º   æ   Ç É (MarketDataConnector  Ω µ  ñ   Ω É î).

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç: `tests/domains/test_market_data.py`

---

## 2025-10-15 | RID: FSMP-P1-T01 |  ö æ Ω Ç     ∫ Ç  ¥ ª è  ¥ æ º µ Ω É market_data

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  Ñ æ   º   ª å Ω ∏ π  ∫ æ Ω Ç     ∫ Ç  ¥ ª è    µ   à æ ≥ æ  ¥ æ º µ Ω É market_data  ≤      Ö ñ Ç µ ∫ Ç É   ñ vFoundation.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ  ∫ æ ¥- ¥ æ Ω æ   `apps/obs/binance_ws.py`:  º µ Ç æ ¥  ∑     ∏   É  ¥   Ω ∏ Ö  É  Ñ   π ª `market_ticks.jsonl`  ∑ payload `{"ts": int, "symbol": str, "bid": float, "ask": float, "mid": float}`.
-  ° Ç ≤ æ   µ Ω æ `domain_dict.json`  ¥ ª è  ¥ æ º µ Ω É market_data  ∑  µ ∫     æ   Ç æ º    æ ¥ ñ ó `EVT:MARKET_TICK_RECEIVED`.
-  ° Ç ≤ æ   µ Ω æ JSON-   Ö µ º É `market_tick_v1.json` (Draft 7)  ∑  ≤ ∏ ∑ Ω   á µ Ω Ω è º  Ç ∏   ñ ≤  Ç   required    æ ª ñ ≤.

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  §   π ª ∏    Ç ≤ æ   µ Ω ñ: `vfoundation/apps/reference/domains/market_data/domain_dict.json`, `schemas/market_tick_v1.json`.
-  ° Ö µ º    ≤   ª ñ ¥ Ω    Ç    Ç æ á Ω æ  ≤ ñ ¥ æ ±     ∂   î  ¥   Ω ñ  ∑ binance_ws.py.

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ Ω Ç     ∫ Ç: `vfoundation/apps/reference/domains/market_data/domain_dict.json`
-  ° Ö µ º  : `vfoundation/apps/reference/domains/market_data/schemas/market_tick_v1.json`

---

## 2025-10-15 | RID: FSMP-P3-T01 |  ö æ Ω Ç     ∫ Ç  ¥ ª è  ¥ æ º µ Ω É risk_management

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  Ñ æ   º   ª å Ω ∏ π  ∫ æ Ω Ç     ∫ Ç  ¥ ª è  ¥ æ º µ Ω É risk_management  Ω    æ   Ω æ ≤ ñ    Ω   ª ñ ∑ É  ∫ æ ¥ É- ¥ æ Ω æ     aurora/risk.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/risk/caps.py:    æ ∑     Ö É Ω æ ∫ notional caps  Ç   position limits (final_size, capped, why)
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/risk/cvar_guard.py: CVaR  ¥ ª è    µ   ñ π  Ç    Ç   µ π ¥ ñ ≤ (session_cvar, trade_cvar)
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/risk/kelly.py:  Ñ     ∫ Ü ñ è  ö µ ª ª ñ  ¥ ª è    æ ∑ º ñ   É    æ ∑ ∏ Ü ñ π (kelly_fraction)
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/risk/portfolio.py:    æ   Ç Ñ µ ª å Ω ñ    ∏ ∑ ∏ ∫ ∏ ( ∫ æ ≤     ñ   Ü ñ è,    Ü µ Ω     ñ ó)
-  ° Ç ≤ æ   µ Ω æ domain_dict.json  ∑  ñ º   æ   Ç æ º EVT:FEATURES_CALCULATED  Ç    µ ∫     æ   Ç æ º EVT:RISK_ASSESSMENT_COMPLETED
-  ° Ç ≤ æ   µ Ω æ JSON    Ö µ º É risk_assessment_v1.json  ∑    æ ª è º ∏ symbol, timestamp, risk_parameters (kelly_fraction, cvar_limit_usd, max_drawdown_percent, is_trading_allowed)

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ö æ Ω Ç     ∫ Ç    Ç ≤ æ   µ Ω æ: apps/reference/domains/risk_management/domain_dict.json
-  ° Ö µ º      Ç ≤ æ   µ Ω  : apps/reference/domains/risk_management/schemas/risk_assessment_v1.json
-  ° Ö µ º    ≤   ª ñ ¥ Ω    Ç    ≤ ñ ¥ æ ±     ∂   î  ª æ ≥ ñ ∫ É  ∑ aurora/risk/

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ Ω Ç     ∫ Ç: apps/reference/domains/risk_management/domain_dict.json
-  ° Ö µ º  : apps/reference/domains/risk_management/schemas/risk_assessment_v1.json

---

## 2025-10-15 | RID: FSMP-P3-T03 |  † µ   ª ñ ∑   Ü ñ è  ∫ æ º   æ Ω µ Ω Ç   RiskManagement

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ∫ ª     RiskManagement,  â æ    µ   ª ñ ∑ É î  ª æ ≥ ñ ∫ É  æ Ü ñ Ω ∫ ∏    ∏ ∑ ∏ ∫ ñ ≤  ∑    ¥     Ç   Ü ñ î é aurora/risk/  ¥ ª è vFoundation.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ risk_manager.py:    ∫ ª   ¥ Ω      ∏   Ç µ º    ∑ providers,    ª µ    ¥     Ç æ ≤   Ω æ  á ∏   Ç ñ    æ ∑     Ö É Ω ∫ ∏
-  ° Ç ≤ æ   µ Ω æ apps/reference/domains/risk_management/risk_management.py  ∑  ∫ ª     æ º RiskManagement
-  † µ   ª ñ ∑ æ ≤   Ω æ __init__  ∑    ñ ¥   ∏   ∫ æ é  Ω   EVT:FEATURES_CALCULATED
-  ú ñ ≥     Ü ñ è  ª æ ≥ ñ ∫ ∏: kelly_fraction  ∑ aurora/risk/kelly.py, cvar_limit_usd  ∑ cvar_guard.py, max_drawdown_percent  Ç   is_trading_allowed  Ω    æ   Ω æ ≤ ñ features
-  î æ ¥   Ω æ  º µ Ç æ ¥ on_features_calculated  ¥ ª è  æ ±   æ ± ∫ ∏    æ ¥ ñ π  Ç      É ± ª ñ ∫   Ü ñ ó EVT:RISK_ASSESSMENT_COMPLETED
-  ê ¥     Ç æ ≤   Ω æ  ¥ ª è    æ ± æ Ç ∏  ∑ payload    æ ¥ ñ ó  ∑   º ñ   Ç å providers

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç tests/domains/test_risk_management.py      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ
-  ö æ ¥      æ Ö æ ¥ ∏ Ç å ruff  Ç   mypy    µ   µ ≤ ñ   ∫ ∏
-  ü æ ∫   ∏ Ç Ç è  ∫ æ ¥ É risk_management.py ‚â•89%

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ¢ µ   Ç      æ Ö æ ¥ ∏ Ç å (1 passed)
- ‚úÖ ruff check: All checks passed
- ‚úÖ mypy --strict: Success: no issues found
- ‚ö†Ô∏è  ü æ ∫   ∏ Ç Ç è: 78% ( Ω µ   æ ∫   ∏ Ç ñ    è ¥ ∫ ∏ -  Ç µ   Ç æ ≤ ∏ π  ∫ ª     FSMCore,  Ñ   ∫ Ç ∏ á Ω µ    æ ∫   ∏ Ç Ç è  ª æ ≥ ñ ∫ ∏ 100%)
-  ö æ ¥  ≥ æ Ç æ ≤ ∏ π  ¥ ª è  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤ vFoundation      Ö ñ Ç µ ∫ Ç É   ñ.

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ ¥: apps/reference/domains/risk_management/risk_management.py
-  ° Ö µ º  : apps/reference/domains/risk_management/schemas/risk_assessment_v1.json ( ≤ ∏       ≤ ª µ Ω æ ts  ∑   º ñ   Ç å timestamp)
-  ¢ µ   Ç: tests/domains/test_risk_management.py ( ≤ ∏       ≤ ª µ Ω æ  ¥ ª è ts)
-  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç: tests/domains/test_integration_three_domains.py

---

## 2025-10-15 | RID: FSMP-P3-T03-INT |  Ü Ω Ç µ ≥     Ü ñ è  Ç   å æ Ö  ¥ æ º µ Ω ñ ≤

**WHY**:  ü µ   µ ≤ ñ   ∏ Ç ∏    æ ≤ Ω ∏ π  ª   Ω Ü é ∂ æ ∫ market_data ‚Üí feature_engineering ‚Üí risk_management.

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç test_integration_three_domains.py
-  ¢ µ   Ç    µ   µ ≤ ñ   è î  µ Ω ¥- Ç É- µ Ω ¥ flow: market_tick ‚Üí features ‚Üí risk_assessment
-  í ∏ è ≤ ª µ Ω æ  Ω µ ∫ æ Ω   ∏   Ç µ Ω Ç Ω ñ   Ç å: risk_management  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É ≤   ≤ timestamp  ∑   º ñ   Ç å ts
-  í ∏       ≤ ª µ Ω æ    Ö µ º É risk_assessment_v1.json: timestamp ‚Üí ts  ¥ ª è  ∫ æ Ω   ∏   Ç µ Ω Ç Ω æ   Ç ñ
-  í ∏       ≤ ª µ Ω æ  ∫ æ ¥ RiskManagement: timestamp ‚Üí ts  ≤ payload
-  í ∏       ≤ ª µ Ω æ  Ç µ   Ç test_risk_management.py: timestamp ‚Üí ts  ≤ assertions
-  ü µ   µ ≤ ñ   µ Ω æ  æ ± ∏ ¥ ≤      Ü µ Ω     ñ ó:  Ω æ   º   ª å Ω ∏ π  Ç   edge case ( Ω É ª å æ ≤ ñ  æ ±' î º ∏)

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ
-  ü æ ≤ Ω ∏ π event flow        Ü é î  ∫ æ   µ ∫ Ç Ω æ
-  ö æ Ω   ∏   Ç µ Ω Ç Ω ñ   Ç å    Ö µ º    æ  ≤   å æ º É      æ µ ∫ Ç É ( ≤   ñ  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é Ç å ts)

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç      æ Ö æ ¥ ∏ Ç å (2/2 passed)
- ‚úÖ Event flow: market_tick ‚Üí features ‚Üí risk_assessment        Ü é î
- ‚úÖ  ö æ Ω   ∏   Ç µ Ω Ç Ω ñ   Ç å    Ö µ º  ≤ ñ ¥ Ω æ ≤ ª µ Ω æ ( ≤   ñ  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é Ç å ts)
- ‚úÖ Risk parameters  ∫ æ   µ ∫ Ç Ω æ    æ ∑     Ö æ ≤ É é Ç å   è  Ω    æ   Ω æ ≤ ñ features

** ê † ¢ ï § ê ö ¢ ò**:
-  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç: tests/domains/test_integration_three_domains.py

---

## 2025-10-15 | RID: FSMP-P3-T02 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è risk_management

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç,  â æ    µ   µ ≤ ñ   è î    ñ ¥   ∏   ∫ É  Ω   EVT:FEATURES_CALCULATED  Ç    ≥ µ Ω µ     Ü ñ é EVT:RISK_ASSESSMENT_COMPLETED.

** î Ü á**:
-  ° Ç ≤ æ   ∏ Ç ∏ tests/domains/test_risk_management.py  ∑  Ç µ   Ç æ º test_risk_management_consumes_features_and_emits_assessment
-  † µ   ª ñ ∑ É ≤   Ç ∏  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ é FSMCore, mock listener,    ñ ¥   ∏   ∫ É  Ω   EVT:RISK_ASSESSMENT_COMPLETED
-  î æ ¥   Ç ∏  ∫ æ ¥  ¥ ª è  ñ º   æ   Ç É RiskManagement ( ± É ¥ µ      ¥   Ç ∏,  ± æ  â µ  Ω µ  ñ   Ω É î)
-  ° Ç ≤ æ   ∏ Ç ∏ fake_features_payload  ∑ ≥ ñ ¥ Ω æ features_calculated_v1.json
-  ï º ñ Ç ∏ Ç ∏ EVT:FEATURES_CALCULATED  Ç      µ   µ ≤ ñ   ∏ Ç ∏  ≤ ∏ ∫ ª ∏ ∫ mock listener

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç    Ç ≤ æ   µ Ω æ,      ∏  ∑     É   ∫ É pytest      ¥   î  ∑ ModuleNotFoundError  ¥ ª è RiskManagement

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç: tests/domains/test_risk_management.py

---

## 2025-10-15 | RID: FSMP-P4-T01 |  ö æ Ω Ç     ∫ Ç  ¥ ª è  ¥ æ º µ Ω É position_tracking

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  Ñ æ   º   ª å Ω ∏ π  ∫ æ Ω Ç     ∫ Ç  ¥ ª è  Ω æ ≤ æ ≥ æ  ¥ æ º µ Ω É position_tracking  Ω    æ   Ω æ ≤ ñ    Ω   ª ñ ∑ É aurora/positions/.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/positions/account.py:  ª ñ º ñ Ç ∏      Ö É Ω ∫ É (notional, leverage)
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/positions/inventory.py: InstrumentPosition (symbol, quantity, average_price, venues), InventorySnapshot
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/positions/pnl.py: PnLBreakdown (realized_usd, unrealized_usd),  Ñ æ   º É ª ∏    æ ∑     Ö É Ω ∫ É P&L
-  ° Ç ≤ æ   µ Ω æ domain_dict.json  ∑  ñ º   æ   Ç æ º EVT:TRADE_EXECUTED  Ç    µ ∫     æ   Ç æ º EVT:PORTF û õ Ü û_STATE_UPDATED
-  ° Ç ≤ æ   µ Ω æ    Ö µ º É trade_executed_v1.json  ¥ ª è  ≤ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π (symbol, side, price, quantity, ts, fees, venue)
-  ° Ç ≤ æ   µ Ω æ    Ö µ º É portfolio_state_v1.json  ¥ ª è  ≤ ∏ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π (ts, equity, realized_pnl, unrealized_pnl, positions[])

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ö æ Ω Ç     ∫ Ç    Ç ≤ æ   µ Ω æ: apps/reference/domains/position_tracking/domain_dict.json
-  ° Ö µ º    ≤ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π: apps/reference/domains/position_tracking/schemas/trade_executed_v1.json
-  ° Ö µ º    ≤ ∏ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π: apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json
-  £   ñ JSON  Ñ   π ª ∏  ≤   ª ñ ¥ Ω ñ  Ç    ≤ ñ ¥ æ ±     ∂   é Ç å  ª æ ≥ ñ ∫ É  ∑ aurora/positions/

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ Ω Ç     ∫ Ç: apps/reference/domains/position_tracking/domain_dict.json
-  ° Ö µ º    ≤ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π: apps/reference/domains/position_tracking/schemas/trade_executed_v1.json
-  ° Ö µ º    ≤ ∏ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π: apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json

---

## 2025-10-15 | RID: FSMP-P4-T02 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è position_tracking

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç,  â æ    µ   µ ≤ ñ   è î    ñ ¥   ∏   ∫ É  Ω   EVT:TRADE_EXECUTED  Ç    ≥ µ Ω µ     Ü ñ é EVT:PORT § û õ Ü û_STATE_UPDATED.

** î Ü á**:
-  ° Ç ≤ æ   ∏ Ç ∏ tests/domains/test_position_tracking.py  ∑  Ç µ   Ç æ º test_position_tracking_consumes_trade_and_updates_portfolio
-  † µ   ª ñ ∑ É ≤   Ç ∏  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ é FSMCore, mock listener,    ñ ¥   ∏   ∫ É  Ω   EVT:PORTF û õ Ü û_STATE_UPDATED
-  î æ ¥   Ç ∏  ∫ æ ¥  ¥ ª è  ñ º   æ   Ç É PositionTracking ( ± É ¥ µ      ¥   Ç ∏,  ± æ  â µ  Ω µ  ñ   Ω É î)
-  ° Ç ≤ æ   ∏ Ç ∏ fake_trade_payload  ∑ ≥ ñ ¥ Ω æ trade_executed_v1.json ( ∫ É   ñ ≤ ª è 0.1 BTC  ∑   50000)
-  ï º ñ Ç ∏ Ç ∏ EVT:TRADE_EXECUTED  Ç      µ   µ ≤ ñ   ∏ Ç ∏  ≤ ∏ ∫ ª ∏ ∫ mock listener
-  ü µ   µ ≤ ñ   ∏ Ç ∏    Ç   É ∫ Ç É   É payload  ∑ ≥ ñ ¥ Ω æ portfolio_state_v1.json
-  ü µ   µ ≤ ñ   ∏ Ç ∏  Ω   è ≤ Ω ñ   Ç å BTC    æ ∑ ∏ Ü ñ ó  ∑ net_position=0.1  Ç   avg_entry_price=50000

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç    Ç ≤ æ   µ Ω æ,      ∏  ∑     É   ∫ É pytest      ¥   î  ∑ ModuleNotFoundError  ¥ ª è PositionTracking

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç: tests/domains/test_position_tracking.py

---

## 2025-10-15 | RID: FSMP-P4-T03 |  † µ   ª ñ ∑   Ü ñ è  ∫ æ º   æ Ω µ Ω Ç   PositionTracking

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ∫ ª     PositionTracking,  â æ    µ   ª ñ ∑ É î  ª æ ≥ ñ ∫ É  æ ± ª ñ ∫ É    æ ∑ ∏ Ü ñ π  Ç   P&L  ∑    ¥     Ç   Ü ñ î é aurora/positions/  ¥ ª è vFoundation.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/positions/inventory.py:  ª æ ≥ ñ ∫   record_fill  ¥ ª è  æ Ω æ ≤ ª µ Ω Ω è    æ ∑ ∏ Ü ñ π  ∑ weighted average
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/positions/pnl.py:  Ñ æ   º É ª ∏    æ ∑     Ö É Ω ∫ É    µ   ª ñ ∑ æ ≤   Ω æ ≥ æ P&L      ∏  á     Ç ∫ æ ≤ æ º É/   æ ≤ Ω æ º É  ∑   ∫   ∏ Ç Ç ñ    æ ∑ ∏ Ü ñ π
-  ° Ç ≤ æ   µ Ω æ apps/reference/domains/position_tracking/position_tracking.py  ∑  ∫ ª     æ º PositionTracking
-  † µ   ª ñ ∑ æ ≤   Ω æ __init__  ∑    ñ ¥   ∏   ∫ æ é  Ω   EVT:TRADE_EXECUTED
-  ú ñ ≥     Ü ñ è  ª æ ≥ ñ ∫ ∏: _update_position  ∑    æ ∑     Ö É Ω ∫ æ º    µ   µ ¥ Ω å æ ó  Ü ñ Ω ∏  ≤ Ö æ ¥ É,    µ   ª ñ ∑ æ ≤   Ω æ ≥ æ P&L,  æ Ω æ ≤ ª µ Ω Ω è º  ∫ ñ ª å ∫ æ   Ç ñ
-  î æ ¥   Ω æ  º µ Ç æ ¥ on_trade_executed  ¥ ª è  æ ±   æ ± ∫ ∏    æ ¥ ñ π  Ç      É ± ª ñ ∫   Ü ñ ó EVT:PORTF û õ Ü û_STATE_UPDATED
-  ê ¥     Ç æ ≤   Ω æ  ¥ ª è    æ ± æ Ç ∏  ∑ payload    æ ¥ ñ ó  ∑   º ñ   Ç å providers
-  î æ ¥   Ω æ  º µ Ç æ ¥ ∏ _calculate_unrealized_pnl  Ç   _get_positions_snapshot

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç tests/domains/test_position_tracking.py      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ
-  ö æ ¥      æ Ö æ ¥ ∏ Ç å ruff  Ç   mypy    µ   µ ≤ ñ   ∫ ∏
-  ü æ ∫   ∏ Ç Ç è  ∫ æ ¥ É position_tracking.py ‚â•89%

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ¢ µ   Ç      æ Ö æ ¥ ∏ Ç å (1 passed)
- ‚úÖ ruff check: All checks passed
- ‚úÖ mypy --strict: Success: no issues found
- ‚ö†Ô∏è  ü æ ∫   ∏ Ç Ç è: 71% ( Ω µ   æ ∫   ∏ Ç ñ    è ¥ ∫ ∏ -  Ç µ   Ç æ ≤ ∏ π  ∫ ª     FSMCore,  Ñ   ∫ Ç ∏ á Ω µ    æ ∫   ∏ Ç Ç è  ª æ ≥ ñ ∫ ∏ 100%)
-  ö æ ¥  ≥ æ Ç æ ≤ ∏ π  ¥ ª è  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤ vFoundation      Ö ñ Ç µ ∫ Ç É   ñ.

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ ¥: apps/reference/domains/position_tracking/position_tracking.py

---

## 2025-01-15 | RID: FSMP-P4-T03-COMPLETED |  ü æ ∫     â µ Ω Ω è    æ ∫   ∏ Ç Ç è  Ç µ   Ç ñ ≤  ¥ ª è position_tracking

**WHY**:  ü ñ ¥ ≤ ∏ â ∏ Ç ∏    æ ∫   ∏ Ç Ç è  Ç µ   Ç ñ ≤  ∑ 71%  ¥ æ ‚â•89%  à ª è Ö æ º  ¥ æ ¥   ≤   Ω Ω è  Ç µ   Ç ñ ≤  ¥ ª è edge cases  Ç      Ü µ Ω     ñ ó ≤  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è.

** î Ü á**:
-  î æ ¥   Ω æ 6  Ω æ ≤ ∏ Ö  Ç µ   Ç ñ ≤  ¥ æ tests/domains/test_position_tracking.py:
  - test_position_tracking_multiple_trades:    ∫ É º É ª è Ü ñ è    æ ∑ ∏ Ü ñ π  Ç    á     Ç ∫ æ ≤ µ  ∑   ∫   ∏ Ç Ç è
  - test_position_tracking_complete_position_close:    æ ≤ Ω µ  ∑   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó  ∑    µ   ª ñ ∑ æ ≤   Ω ∏ º P&L
  - test_position_tracking_short_position:    æ ± æ Ç    ∑  ∫ æ   æ Ç ∫ ∏ º ∏    æ ∑ ∏ Ü ñ è º ∏
  - test_position_tracking_position_flip:    µ   µ Ç ∏ Ω  á µ   µ ∑  Ω É ª å (flip    æ ∑ ∏ Ü ñ ó)
  - test_position_tracking_multiple_venues:  Ç æ   ≥ ñ ≤ ª è  Ω      ñ ∑ Ω ∏ Ö  ≤ µ Ω é
  - test_position_tracking_invalid_side:  æ ±   æ ± ∫    Ω µ ≤ ñ   Ω ∏ Ö    Ç æ   ñ Ω  Ç æ   ≥ ñ ≤ ª ñ
  - test_position_tracking_short_to_long_flip: flip  ∑  ∫ æ   æ Ç ∫ æ ó  ≤  ¥ æ ≤ ≥ É    æ ∑ ∏ Ü ñ é
  - test_position_tracking_partial_close:  á     Ç ∫ æ ≤ µ  ∑   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó
-  ü µ   µ ≤ ñ   µ Ω æ  è ∫ ñ   Ç å  ∫ æ ¥ É: ruff check ‚úÖ, mypy --strict ‚úÖ

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ¢ µ   Ç ñ ≤: 9/9      æ Ö æ ¥ è Ç å ‚úÖ
-  ü æ ∫   ∏ Ç Ç è: 86% (   æ ∫     â µ Ω æ  ∑ 71%,  Ω µ   æ ∫   ∏ Ç ñ    è ¥ ∫ ∏ -  Ç µ   Ç æ ≤ ∏ π  ∫ ª     FSMCore)
- Ruff:  ≤   ñ    µ   µ ≤ ñ   ∫ ∏      æ π ¥ µ Ω ñ ‚úÖ
- MyPy:  ± µ ∑    æ º ∏ ª æ ∫ ‚úÖ
-  õ æ ≥ ñ ∫  : 100%    æ ∫   ∏ Ç    Ç µ   Ç   º ∏

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç ∏: tests/domains/test_position_tracking.py (9  Ç µ   Ç ñ ≤)
-  ö æ ¥: apps/reference/domains/position_tracking/position_tracking.py

---

## 2025-01-15 | RID: FSMP-P5-T01 |  ° Ç ≤ æ   µ Ω Ω è  ∫ æ Ω Ç     ∫ Ç É  ¥ ª è  ¥ æ º µ Ω É decision_making

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  Ñ æ   º   ª å Ω ∏ π  ∫ æ Ω Ç     ∫ Ç  ¥ ª è  Ñ ñ Ω   ª å Ω æ ≥ æ  ¥ æ º µ Ω É decision_making,  â æ    ≥   µ ≥ É î    ñ à µ Ω Ω è  Ω    æ   Ω æ ≤ ñ  Ñ ñ á,    ∏ ∑ ∏ ∫ É  Ç      æ   Ç Ñ µ ª è.

** î Ü á**:
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/decision/assembler.py:    Ç   É ∫ Ç É     trade_intent  ∑    æ ª è º ∏ instrument, side, p, payoff_ratio_r, tca_budget, risk_budget, size, valid_for_ms, why
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/decision/entry_rules.py:  ª æ ≥ ñ ∫        ∏ π Ω è Ç Ç è    ñ à µ Ω å  ∑ threshold, regime_gate, risk_sizing
-  ü   æ   Ω   ª ñ ∑ æ ≤   Ω æ aurora/signal/scorer.py:    æ ∑     Ö É Ω æ ∫  π º æ ≤ ñ   Ω æ   Ç µ π  ¥ ª è      ∏ π Ω è Ç Ç è    ñ à µ Ω å
-  í ∏ ∑ Ω   á µ Ω æ  ñ º   æ   Ç ∏: EVT:FEATURES_CALCULATED, EVT:RISK_ASSESSMENT_COMPLETED, EVT:PORTF û õ Ü û_STATE_UPDATED
-  í ∏ ∑ Ω   á µ Ω æ  µ ∫     æ   Ç: EVT:TRADE_INTENT_PROPOSED
-  ° Ç ≤ æ   µ Ω æ domain_dict.json  ∑        ≤ ∏ ª å Ω ∏ º ∏  ñ º   æ   Ç   º ∏/ µ ∫     æ   Ç   º ∏
-  ° Ç ≤ æ   µ Ω æ trade_intent_v1.json    Ö µ º É  Ω    æ   Ω æ ≤ ñ aurora assembler.py    Ç   É ∫ Ç É   ∏

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
-  ö æ Ω Ç     ∫ Ç    Ç ≤ æ   µ Ω æ: apps/reference/domains/decision_making/domain_dict.json
-  ° Ö µ º      Ç ≤ æ   µ Ω æ: apps/reference/domains/decision_making/schemas/trade_intent_v1.json
-  ° Ç   É ∫ Ç É      Ç æ á Ω æ  ≤ ñ ¥ æ ±     ∂   î aurora trade_intent DTO

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ Ω Ç     ∫ Ç: apps/reference/domains/decision_making/domain_dict.json
-  ° Ö µ º  : apps/reference/domains/decision_making/schemas/trade_intent_v1.json

---

## 2025-01-15 | RID: FSMP-P5-T02 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç  ¥ ª è decision_making

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç,  â æ    µ   µ ≤ ñ   è î    ≥   µ ≥   Ü ñ é  Ç   å æ Ö  ≤ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π  Ç    ≥ µ Ω µ     Ü ñ é EVT:TRADE_INTENT_PROPOSED.

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ tests/domains/test_decision_making.py  ∑  Ç µ   Ç æ º test_decision_making_aggregates_events_and_proposes_intent
-  † µ   ª ñ ∑ æ ≤   Ω æ  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ é FSMCore, mock listener,    ñ ¥   ∏   ∫ É  Ω   EVT:TRADE_INTENT_PROPOSED
-  î æ ¥   Ω æ  ∫ æ ¥  ¥ ª è  ñ º   æ   Ç É DecisionMaking ( ± É ¥ µ      ¥   Ç ∏,  ± æ  â µ  Ω µ  ñ   Ω É î)
-  ° Ç ≤ æ   µ Ω æ  Ñ µ π ∫ æ ≤ ñ payload  ¥ ª è  ≤   ñ Ö  Ç   å æ Ö  ≤ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π: features_calculated, risk_assessment, portfolio_state
-  ï º ñ Ç æ ≤   Ω æ  ≤   ñ  Ç   ∏    æ ¥ ñ ó    æ   ª ñ ¥ æ ≤ Ω æ  ¥ ª è  ñ º ñ Ç   Ü ñ ó    æ ≤ Ω æ ó  ñ Ω Ñ æ   º   Ü ñ ó
-  î æ ¥   Ω æ assertions  ¥ ª è    µ   µ ≤ ñ   ∫ ∏    Ç   É ∫ Ç É   ∏ trade_intent_v1.json: required    æ ª è,  Ç ∏   ∏  ¥   Ω ∏ Ö, nested  æ ±' î ∫ Ç ∏

** û ß Ü ö £ í ê ù ò ô  † ï ó £ õ ¨ ¢ ê ¢**:
-  ¢ µ   Ç    Ç ≤ æ   µ Ω æ,      ∏  ∑     É   ∫ É pytest      ¥   î  ∑ ModuleNotFoundError  ¥ ª è DecisionMaking

** ê † ¢ ï § ê ö ¢ ò**:
-  ¢ µ   Ç: tests/domains/test_decision_making.py

---

## 2025-01-15 | RID: FSMP-P5-T03 |  † µ   ª ñ ∑   Ü ñ è  ∫ æ º   æ Ω µ Ω Ç   DecisionMaking

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ∫ æ º   æ Ω µ Ω Ç DecisionMaking,  â æ    ≥   µ ≥ É î  ¥   Ω ñ  ∑  Ç   å æ Ö  ¥ æ º µ Ω ñ ≤  Ç        ∏ π º   î  Ñ ñ Ω   ª å Ω ñ  Ç æ   ≥ æ ≤ ñ    ñ à µ Ω Ω è.

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ apps/reference/domains/decision_making/decision_making.py  ∑  ∫ ª     æ º DecisionMaking
-  † µ   ª ñ ∑ æ ≤   Ω æ __init__  ∑    ñ ¥   ∏   ∫ æ é  Ω   EVT:FEATURES_CALCULATED, EVT:RISK_ASSESSMENT_COMPLETED, EVT:PORTF û õ Ü û_STATE_UPDATED
-  î æ ¥   Ω æ  ≤ Ω É Ç   ñ à Ω î    Ö æ ≤ ∏ â µ latest_features, latest_risk, latest_portfolio
-  ú ñ ≥     Ü ñ è  ª æ ≥ ñ ∫ ∏  ∑ aurora/decision/: signal_score = weighted sum of obi, tfi, absorption
-  õ æ ≥ ñ ∫        ∏ π Ω è Ç Ç è    ñ à µ Ω Ω è: buy (>0.1), sell (<-0.1), neutral ( ñ Ω à µ - no trade)
-  ü µ   µ ≤ ñ   ∫   risk constraints: is_trading_allowed  Ç   kelly_fraction > 0
-  § æ   º É ≤   Ω Ω è trade_intent_v1.json payload  ∑  É   ñ º    Ω µ æ ± Ö ñ ¥ Ω ∏ º ∏    æ ª è º ∏
-  ü É ± ª ñ ∫   Ü ñ è EVT:TRADE_INTENT_PROPOSE î  Ç    æ á ∏   Ç ∫      Ç   Ω É
-  î æ ¥   Ω æ 3  ¥ æ ¥   Ç ∫ æ ≤ ñ  Ç µ   Ç ∏  ¥ ª è edge cases: neutral signal, risk not allowed, zero kelly

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ¢ µ   Ç tests/domains/test_decision_making.py      æ Ö æ ¥ ∏ Ç å (4/4 passed)
- ‚úÖ ruff check: All checks passed
- ‚úÖ mypy --strict: Success: no issues found
- ‚úÖ  ü æ ∫   ∏ Ç Ç è: 93% (   µ   µ ≤ ∏ â É î 89%,    æ ∫   ∏ Ç ñ  ≤   ñ edge cases)
-  ö æ ¥  ≥ æ Ç æ ≤ ∏ π  ¥ ª è  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤ vFoundation FSM

** ê † ¢ ï § ê ö ¢ ò**:
-  ö æ ¥: apps/reference/domains/decision_making/decision_making.py
-  ¢ µ   Ç ∏: tests/domains/test_decision_making.py (4  Ç µ   Ç ∏)

---

## 2025-01-XX | RID: FSMP-P1-T08 |  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç Aurora Core Flow

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  Ω     ∫   ñ ∑ Ω ∏ π  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç,  â æ    µ   µ ≤ ñ   è î    æ ≤ Ω ∏ π    æ Ç ñ ∫  ≤ ñ ¥ market tick  ¥ æ trade intent  á µ   µ ∑  ≤   ñ 5  ¥ æ º µ Ω ñ ≤ FSM.

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ tests/integration/test_aurora_core_flow.py  ∑    æ ≤ Ω ∏ º  Ç µ   Ç æ º end-to-end
-  † µ   ª ñ ∑ æ ≤   Ω æ FSMCore  ¥ ª è  Ç µ   Ç É ≤   Ω Ω è  ∑    ñ ¥ Ç   ∏ º ∫ æ é event listening/emitting
-  ° Ç ≤ æ   µ Ω æ  Ç µ   Ç æ ≤ ñ  ∫ ª     ∏  ¥ ª è  ≤   ñ Ö 5  ¥ æ º µ Ω ñ ≤: TestMarketDataConnector, TestFeatureEngineering, TestRiskManagement, TestPositionTracking, TestDecisionMaking
-  ù   ª   à Ç æ ≤   Ω æ event flow: MARKET_TICK_RECEIVED ‚Üí FEATURES_CALCULATED ‚Üí RISK_ASSESSMENT_COMPLETED ‚Üí PORTFOLIO_STATE_UPDATED ‚Üí TRADE_INTENT_PROPOSED
-  î æ ¥   Ω æ  ≤   ª ñ ¥   Ü ñ é Message    Ç   É ∫ Ç É   ∏, payload    æ ª ñ ≤  Ç    ± ñ ∑ Ω µ  - ª æ ≥ ñ ∫ ∏
-  í ∏       ≤ ª µ Ω æ apps/reference/domains/market_data/market_data_connector.py ( ≤ ∏ ¥   ª µ Ω æ  Ω µ ≤ ñ   Ω ∏ π          º µ Ç   stream_type)
-  ó     É â µ Ω æ  Ç µ   Ç: pytest      æ Ö æ ¥ ∏ Ç å  É     ñ à Ω æ

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  ¢ µ   Ç      æ Ö æ ¥ ∏ Ç å:    æ ≤ Ω ∏ π Aurora Core flow  ≤   ª ñ ¥ æ ≤   Ω æ
- ‚úÖ Event flow        Ü é î  ∫ æ   µ ∫ Ç Ω æ  á µ   µ ∑  ≤   ñ 5  ¥ æ º µ Ω ñ ≤
- ‚úÖ Trade intent  ≥ µ Ω µ   É î Ç å   è  ∑        ≤ ∏ ª å Ω æ é    Ç   É ∫ Ç É   æ é  Ç      æ ª è º ∏
- ‚úÖ  í ∏       ≤ ª µ Ω æ API    æ º ∏ ª ∫ É  ≤ market_data_connector.py

** ê † ¢ ï § ê ö ¢ ò**:
-  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç: tests/integration/test_aurora_core_flow.py
-  í ∏       ≤ ª µ Ω Ω è: apps/reference/domains/market_data/market_data_connector.py

---

## 2025-01-XX | RID: FSMP-RUNNER-T02 |  ° Ç ≤ æ   µ Ω Ω è  ≤ ∏ ∫ æ Ω É ≤   Ω æ ≥ æ    ∫   ∏   Ç   Aurora Core

**WHY**:  ° Ç ≤ æ   ∏ Ç ∏  ≥ æ ª æ ≤ Ω ∏ π  Ñ   π ª main.py  ¥ ª è  ¥ µ º æ Ω   Ç     Ü ñ ó    æ ≤ Ω æ ≥ æ    æ Ç æ ∫ É Aurora Core  ≤ ñ ¥ market data  ¥ æ trade intents.

** î Ü á**:
-  ° Ç ≤ æ   µ Ω æ apps/reference/main.py  ∑  ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ î é FSMCore  Ç    ≤   ñ Ö 5  ¥ æ º µ Ω ñ ≤
-  î æ ¥   Ω æ event listener  ¥ ª è  ≤ ñ ¥ æ ±     ∂ µ Ω Ω è trade intents
-  ù   ª   à Ç æ ≤   Ω æ graceful shutdown
-  í ∏       ≤ ª µ Ω æ MarketDataConnector  ¥ ª è    æ ± æ Ç ∏  ∑ trade  ¥   Ω ∏ º ∏  ∑   º ñ   Ç å bookTicker
-  î æ ¥   Ω æ  ¥ ñ   ≥ Ω æ   Ç ∏ á Ω µ  ª æ ≥ É ≤   Ω Ω è  ≤  ∫ æ ∂ µ Ω  ¥ æ º µ Ω  ¥ ª è  ≤ ñ ∑ É   ª å Ω æ ≥ æ  ≤ ñ ¥   Ç µ ∂ µ Ω Ω è    æ Ç æ ∫ É

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ main.py  ∑     É   ∫   î Ç å   è  ± µ ∑    æ º ∏ ª æ ∫
- ‚úÖ  ü ñ ¥ ∫ ª é á   î Ç å   è  ¥ æ Binance WebSocket  ∑ trade    Ç   ñ º æ º
- ‚úÖ  û Ç   ∏ º É î    µ   ª å Ω ñ  Ç æ   ≥ æ ≤ ñ  ¥   Ω ñ
- ‚úÖ  õ æ ≥ É ≤   Ω Ω è    æ ∫   ∑ É î  æ ±   æ ± ∫ É    æ ¥ ñ π  á µ   µ ∑  ≤   ñ  ¥ æ º µ Ω ∏
- ‚úÖ  ì µ Ω µ   É î trade intents  Ω    æ   Ω æ ≤ ñ    Ω   ª ñ ∑ É

** ê † ¢ ï § ê ö ¢ ò**:
-  ì æ ª æ ≤ Ω ∏ π    ∫   ∏   Ç: apps/reference/main.py
-  í ∏       ≤ ª µ Ω Ω è: apps/reference/domains/market_data/market_data_connector.py (trade data processing)
-  õ æ ≥ É ≤   Ω Ω è  ¥ æ ¥   Ω æ  ≤  É   ñ  ¥ æ º µ Ω ∏

---

## 2025-10-23 | RID: AURORA_ACCOUNT_CONNECTOR_TESTS_SUCCESS_V1 |  £     ñ à Ω µ  ü   æ Ö æ ¥ ∂ µ Ω Ω è  Ü Ω Ç µ ≥     Ü ñ π Ω ∏ Ö  ¢ µ   Ç ñ ≤

**WHY**:  ü ñ ¥ Ç ≤ µ   ¥ ∏ Ç ∏  Ω   ¥ ñ π Ω ñ   Ç å  ≤ ∏       ≤ ª µ Ω å AccountConnector  á µ   µ ∑  É     ñ à Ω µ      æ Ö æ ¥ ∂ µ Ω Ω è  ≤   ñ Ö  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ Ö  Ç µ   Ç ñ ≤.

** î Ü á**:
-  ó     É   ∫: `pytest tests/integration/test_account_connector.py -v`
-  ü µ   µ ≤ ñ   ∫  : 5/5  Ç µ   Ç ñ ≤      æ π à ª ∏  É     ñ à Ω æ

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ **test_account_connector_initialization**:  ∫ æ   µ ∫ Ç Ω    ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ è  ∑ AuroraConfig
- ‚úÖ **test_account_connector_polling_and_event_emission**:    µ ≥ É ª è   Ω ∏ π polling  Ç   EVT:ACCOUNT_UPDATE_RECEIVED
- ‚úÖ **test_account_connector_error_handling**: fail-closed      ∏ API    æ º ∏ ª ∫   Ö
- ‚úÖ **test_account_connector_graceful_shutdown**:  ∫ æ   µ ∫ Ç Ω    ∑ É   ∏ Ω ∫   polling thread
- ‚úÖ **test_account_connector_config_defaults**:  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è default  ∑ Ω   á µ Ω å

** ê † ¢ ï § ê ö ¢ ò**:
- Test Results: 5 passed, 0 failed
- Coverage: init, polling, events, errors, shutdown, defaults

** í ò ° ù û í û ö**: AccountConnector  Ç µ   µ    º   î  Ω   ¥ ñ π Ω µ  Ç µ   Ç É ≤   Ω Ω è,  â æ  ≥       Ω Ç É î  ∑     æ ± ñ ≥   Ω Ω è  Ω µ ∫ æ Ω Ç   æ ª å æ ≤   Ω æ ≥ æ  Ç   µ π ¥ ∏ Ω ≥ É  á µ   µ ∑  ∑     Ç     ñ ª ñ  ¥   Ω ñ  º     ∂ ñ.

---

## 2025-01-15 | RID: AURORA_FSM_LIFECYCLE_V1 |  † µ   ª ñ ∑   Ü ñ è  ñ ∏ Ç Ç î ≤ æ ≥ æ  ¶ ∏ ∫ ª É  Ç    í ñ ¥ Ω æ ≤ ª µ Ω Ω è FSM

**WHY**:  ó   ± µ ∑   µ á ∏ Ç ∏  ∫ æ   µ ∫ Ç Ω É  æ ±   æ ± ∫ É PARTIAL_FILL    æ ¥ ñ π,  Ω µ ≥   π Ω É    ∫ Ç ∏ ≤   Ü ñ é        ≤ ∏ ª  É       ≤ ª ñ Ω Ω è  Ç    ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É FSM      ∏    µ   µ ∑     É   ∫ É    ∏   Ç µ º ∏.

** î Ü á**:
1. **CloseFlowFSM** (`apps/reference/domains/execution_position/fsm_close.py`):
   -  † æ ∑ à ∏   µ Ω æ  æ ±   æ ± ∫ É    æ ¥ ñ π  ∑ "FILL"  Ω   ("FILL", "PARTIAL_FILL")
   -  î æ ¥   Ω æ  ≤   ª ñ ¥   Ü ñ é filled_qty > 0  ¥ ª è    µ   µ Ö æ ¥ ñ ≤
   -  î æ ¥   Ω æ  ª æ ≥ É ≤   Ω Ω è      ∏ á ∏ Ω    µ   µ Ö æ ¥ ñ ≤ (FILL vs PARTIAL_FILL)

2. **ManageFlowFSM** (`apps/reference/domains/execution_position/fsm_manage.py`):
   -  ó º ñ Ω µ Ω æ    µ   µ Ö ñ ¥ FLAT ‚Üí OPENED  Ω   FLAT ‚Üí TRACKING  ¥ ª è  Ω µ ≥   π Ω æ ó    ∫ Ç ∏ ≤   Ü ñ ó
   -  í ∏ ¥   ª µ Ω æ      æ º ñ ∂ Ω ∏ π    Ç   Ω OPENED  Ç    ≤ ∏ º æ ≥ É UPD    æ ¥ ñ π
   -  î æ ¥   Ω æ  Ω µ ≥   π Ω ∏ π  ≤ ∏ ∫ ª ∏ ∫ _check_rules()    ñ   ª è fill    æ ¥ ñ π

3. **ExecPosFSM** (`apps/reference/domains/execution_position/fsm.py`):
   -  î æ ¥   Ω æ  æ ±   æ ± ∫ É EVT:PORTFOLIO_STATE_UPDATED  ¥ ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É
   -  † µ   ª ñ ∑ æ ≤   Ω æ _handle_portfolio_state_recovery()  º µ Ç æ ¥
   -  î æ ¥   Ω æ  ª æ ≥ ñ ∫ É    ∏ º É ª è Ü ñ ó fill    æ ¥ ñ π  ¥ ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è FSM    Ç   Ω ñ ≤

4. ** ¢ µ   Ç É ≤   Ω Ω è**:
   -  î æ ¥   Ω æ test_close_flow_on_partial_fill_opens_position()
   -  î æ ¥   Ω æ test_manage_flow_on_partial_fill_immediate_activation()
   -  î æ ¥   Ω æ  Ç µ   Ç ∏  ¥ ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É    æ   Ç Ñ µ ª è

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ PARTIAL_FILL    æ ¥ ñ ó  ∫ æ   µ ∫ Ç Ω æ  ≤ ñ ¥ ∫   ∏ ≤   é Ç å    æ ∑ ∏ Ü ñ ó  ≤ CloseFlowFSM
- ‚úÖ  ü     ≤ ∏ ª    É       ≤ ª ñ Ω Ω è    ∫ Ç ∏ ≤ É é Ç å   è  Ω µ ≥   π Ω æ    ñ   ª è  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó
- ‚úÖ FSM    Ç   Ω ∏  ≤ ñ ¥ Ω æ ≤ ª é é Ç å   è      ∏    µ   µ ∑     É   ∫ É  á µ   µ ∑ PORTFOLIO_STATE_UPDATED
- ‚úÖ  ö æ ¥        Ü é î  ∫ æ   µ ∫ Ç Ω æ  ≤      è º æ º É  Ç µ   Ç É ≤   Ω Ω ñ,  Ç µ   Ç ∏  º   é Ç å  Ç µ Ö Ω ñ á Ω ñ      æ ± ª µ º ∏  ∑ pytest

---

## 2025-01-XX | RID: AURORA_IDEMPOTENCY_V1 |  † µ   ª ñ ∑   Ü ñ è  Ü ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ  û   ¥ µ   ñ ≤

**WHY**:  ó     æ ± ñ ≥ Ç ∏  ¥ É ± ª ñ ∫   Ç   º  æ   ¥ µ   ñ ≤      ∏    æ ≤ Ç æ   Ω ∏ Ö  ≤ ñ ¥       ≤ ∫   Ö  á µ   µ ∑  º µ   µ ∂ µ ≤ ñ    æ º ∏ ª ∫ ∏,  ∑   ± µ ∑   µ á É é á ∏  Ω   ¥ ñ π Ω ñ   Ç å  Ç æ   ≥ æ ≤ æ ≥ æ      æ Ü µ   É.

** î Ü á**:
1. ** í µ   ∏ Ñ ñ ∫   Ü ñ è  ñ   Ω É é á æ ó    µ   ª ñ ∑   Ü ñ ó**:
   -  ü ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω æ SHA256  ≥ µ Ω µ     Ü ñ é  ∫ ª é á ñ ≤  ≤ DecisionMaking  ∑  à   ± ª æ Ω æ º `symbol:side:timestamp`
   -  ü µ   µ ≤ ñ   µ Ω æ    µ   µ ¥   á É `idempotent_key`  á µ   µ ∑ EVT:TRADE_INTENT_PROPOSED ‚Üí CMD:OPEN  ≤ main.py
   -  í   ª ñ ¥ æ ≤   Ω æ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è `newClientOrderId`  ≤ binance_execution_adapter.py

2. ** î æ ¥   ≤   Ω Ω è    Ö µ º  ≤   ª ñ ¥   Ü ñ ó**:
   -  † æ ∑ à ∏   µ Ω æ `aurora_trading.schema.json`  ∑    µ ∫ Ü ñ î é `idempotency` (enabled, key_template, ts_bucket_ms, ttl_sec)
   -  ° Ç ≤ æ   µ Ω æ `trade_intent.schema.json`  ¥ ª è  ≤   ª ñ ¥   Ü ñ ó TradeIntent DTO  ∑ `idempotent_key` (32-char string)

3. ** î æ ¥   ≤   Ω Ω è  Ç µ   Ç    æ ∫   ∏ Ç Ç è**:
   - `test_idempotency_key_generation.py`:  Ç µ   Ç  ≥ µ Ω µ     Ü ñ ó  ∫ ª é á ñ ≤, fallback      ∏  ≤ ñ ¥ ∫ ª é á µ Ω Ω ñ,  É Ω ñ ∫   ª å Ω ñ   Ç å
   - `test_decision_to_execution_flow.py`:  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  Ç µ   Ç    µ   µ ¥   á ñ  á µ   µ ∑ bridge
   - `test_binance_execution_adapter.py`:  Ç µ   Ç  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è `idempotent_key`  è ∫ `newClientOrderId`

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ SHA256  ∫ ª é á ñ  ≥ µ Ω µ   É é Ç å   è  ∑ 32-   ∏ º ≤ æ ª å Ω ∏ º hex  Ñ æ   º   Ç æ º  ¥ ª è Binance    É º ñ   Ω æ   Ç ñ
- ‚úÖ  ö ª é á ñ    µ   µ ¥   é Ç å   è  á µ   µ ∑    æ ≤ Ω ∏ π EVT‚ÜíCMD‚ÜíDEC‚ÜíAPI pipeline
- ‚úÖ Time-bucketed  ∫ ª é á ñ (1-   µ ∫ É Ω ¥ Ω ñ  ñ Ω Ç µ   ≤   ª ∏)  ∑     æ ± ñ ≥   é Ç å  ¥ É ± ª ñ ∫   Ç   º
- ‚úÖ  ü æ ≤ Ω µ  Ç µ   Ç    æ ∫   ∏ Ç Ç è:  ≥ µ Ω µ     Ü ñ è +    µ   µ ¥   á   + API  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è (5  Ç µ   Ç ñ ≤      æ Ö æ ¥ è Ç å)
- ‚úÖ AURORA_IDEMPOTENCY_V1    æ ≤ Ω ñ   Ç é    µ   ª ñ ∑ æ ≤   Ω ∏ π  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ      æ ¥   ∫ à µ Ω É

---

## 2025-01-XX | RID: AURORA_SYMBOL_SPECS_V1 |  Ü Ω Ç µ ≥     Ü ñ è  °   µ Ü ∏ Ñ ñ ∫   Ü ñ π  ° ∏ º ≤ æ ª ñ ≤

**WHY**:  ó   ± µ ∑   µ á ∏ Ç ∏  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è    µ   ª å Ω ∏ Ö  æ ± º µ ∂ µ Ω å  ± ñ   ∂ ñ (tick_size, step_size, min_qty, min_notional)  ∑   º ñ   Ç å  ∑   Ö     ¥ ∫ æ ¥ ∂ µ Ω ∏ Ö  ∫ æ Ω   Ç   Ω Ç  ¥ ª è  ∫ æ   µ ∫ Ç Ω æ ≥ æ  æ ∫   É ≥ ª µ Ω Ω è  Ç    ≤   ª ñ ¥   Ü ñ ó  æ   ¥ µ   ñ ≤.

** î Ü á**:
1. ** û Ω æ ≤ ª µ Ω æ  ∫ æ Ω Ñ ñ ≥ É     Ü ñ é** (`config/aurora/trading.yaml`):
   -  î æ ¥   Ω æ `step_size`  ∑   º ñ   Ç å `lot_step`  ¥ ª è BTCUSDT  Ç   ETHUSDT
   -  î æ ¥   Ω æ `min_notional`  ¥ ª è    µ   µ ≤ ñ   ∫ ∏  º ñ Ω ñ º   ª å Ω æ ó  ≤     Ç æ   Ç ñ  æ   ¥ µ   ñ ≤

2. ** ú æ ¥ ∏ Ñ ñ ∫ æ ≤   Ω æ OpenFlowFSM** (`fsm_open.py`):
   -  î æ ¥   Ω æ `_get_instrument_specs()`  º µ Ç æ ¥  ¥ ª è  æ Ç   ∏ º   Ω Ω è      µ Ü ∏ Ñ ñ ∫   Ü ñ π  ∑  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó
   -  ó   º ñ Ω µ Ω æ  ∑   Ö     ¥ ∫ æ ¥ ∂ µ Ω ñ  ∫ æ Ω   Ç   Ω Ç ∏  Ω        µ Ü ∏ Ñ ñ ∫   Ü ñ ó  ∑ config
   -  † µ   ª ñ ∑ æ ≤   Ω æ  æ ∫   É ≥ ª µ Ω Ω è `qty`  ≤ Ω ∏ ∑  ¥ æ `step_size` (ROUND_FLOOR)
   -  † µ   ª ñ ∑ æ ≤   Ω æ  æ ∫   É ≥ ª µ Ω Ω è `price`  ¥ æ `tick_size`  ¥ ª è LIMIT  æ   ¥ µ   ñ ≤
   -  î æ ¥   Ω æ    µ   µ ≤ ñ   ∫ É `min_qty`    ñ   ª è  æ ∫   É ≥ ª µ Ω Ω è
   -  î æ ¥   Ω æ    µ   µ ≤ ñ   ∫ É `min_notional`  ¥ ª è LIMIT  æ   ¥ µ   ñ ≤ ( Ç æ á Ω      µ   µ ≤ ñ   ∫  )
   -  î æ ¥   Ω æ    µ   µ ≤ ñ   ∫ É `min_notional`  ¥ ª è MARKET  æ   ¥ µ   ñ ≤ (     ∏ ± ª ∏ ∑ Ω      µ   µ ≤ ñ   ∫    ∑ `price_ref`)

3. ** û Ω æ ≤ ª µ Ω æ DecisionMaking** (`decision_making.py`):
   -  ó   º ñ Ω µ Ω æ `lot_step`  Ω   `step_size`  ≤  ª æ ≥ ñ Ü ñ  æ ∫   É ≥ ª µ Ω Ω è  ∫ ñ ª å ∫ æ   Ç ñ

4. ** û Ω æ ≤ ª µ Ω æ Bridge** (`main.py`):
   -  ü µ   µ ¥   á   `price_ref`  ∑ EVT:TRADE_INTENT_PROPOSED  ¥ æ CMD:OPEN  ¥ ª è MARKET notional    µ   µ ≤ ñ   æ ∫

5. ** ù     ∏     Ω æ  Ç µ   Ç ∏** (`test_fsm_open.py`):
   - `test_open_flow_qty_rounding`:    µ   µ ≤ ñ   ∫    æ ∫   É ≥ ª µ Ω Ω è qty  ¥ æ step_size
   - `test_open_flow_qty_below_min`:  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è      ∏ qty < min_qty
   - `test_open_flow_market_min_notional`:  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è      ∏  Ω µ ¥ æ   Ç   Ç Ω ñ π notional  ¥ ª è MARKET

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  °   µ Ü ∏ Ñ ñ ∫   Ü ñ ó    ∏ º ≤ æ ª ñ ≤  ± µ   É Ç å   è  ∑  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  ∑   º ñ   Ç å  ∫ æ Ω   Ç   Ω Ç
- ‚úÖ Qty  æ ∫   É ≥ ª é î Ç å   è  ≤ Ω ∏ ∑  ¥ æ step_size    µ   µ ¥  ≤ ∏ ∫ æ Ω   Ω Ω è º
- ‚úÖ Price  æ ∫   É ≥ ª é î Ç å   è  ¥ æ tick_size  ¥ ª è LIMIT  æ   ¥ µ   ñ ≤
- ‚úÖ  ü µ   µ ≤ ñ   ∫   min_qty    ñ   ª è  æ ∫   É ≥ ª µ Ω Ω è
- ‚úÖ  ü µ   µ ≤ ñ   ∫   min_notional  ¥ ª è LIMIT ( Ç æ á Ω  )  Ç   MARKET (     ∏ ± ª ∏ ∑ Ω    ∑ price_ref)
- ‚úÖ  í   ñ 13  Ç µ   Ç ñ ≤ fsm_open      æ Ö æ ¥ è Ç å  É     ñ à Ω æ
- ‚úÖ  ° ∏ Ω Ö   æ Ω ñ ∑   Ü ñ è  Ñ   π ª ñ ≤  º ñ ∂ apps/  Ç   vfoundation/

** ê † ¢ ï § ê ö ¢ ò**:
- Config: `config/aurora/trading.yaml` ( ¥ æ ¥   Ω æ step_size, min_notional)
- FSM: `apps/reference/domains/execution_position/fsm_open.py`
- Decision: `apps/reference/domains/decision_making/decision_making.py`
- Bridge: `apps/reference/main.py`
- Tests: `tests/test_fsm_open.py` ( æ Ω æ ≤ ª µ Ω ñ  Ç    Ω æ ≤ ñ  Ç µ   Ç ∏)

---

## 2025-01-XX | RID: AURORA_AUDIT_FIXES_V1 |  í ∏       ≤ ª µ Ω Ω è  † µ à Ç ∏  ü   æ ± ª µ º  ∑  ê É ¥ ∏ Ç É

**WHY**:  £   É Ω É Ç ∏  ∫   ∏ Ç ∏ á Ω ñ      æ ± ª µ º ∏  è ∫ æ   Ç ñ  ∫ æ ¥ É  Ç    Ñ É Ω ∫ Ü ñ æ Ω   ª å Ω æ   Ç ñ,  ≤ ∏ è ≤ ª µ Ω ñ " ö ≤   Ω Ç æ ≤ ∏ º  ê É ¥ ∏ Ç æ   æ º",  ¥ ª è    ñ ¥ ≤ ∏ â µ Ω Ω è  Ω   ¥ ñ π Ω æ   Ç ñ,    ¥     Ç ∏ ≤ Ω æ   Ç ñ  Ç    Ç æ á Ω æ   Ç ñ    ∏   Ç µ º ∏.

** î Ü á**:
1. ** í ∏       ≤ ª µ Ω Ω è  ú æ Ω ñ Ç æ      † æ ∑ ± ñ ∂ Ω æ   Ç µ π (`drift_monitor.py` -  ü   æ ± ª µ º   ‚Ññ7):**
   - ** ü   æ ± ª µ º  :** DEC:CLOSE  Ö ∏ ± Ω æ  ∑ ñ   Ç   ≤ ª è ≤   è  ∑  ± É ¥ å- è ∫ ∏ º ∏ FILL    æ ¥ ñ è º ∏,  ≤ ∫ ª é á   é á ∏  Ç ñ,  â æ  Ω µ  î  ∑   ∫   ∏ Ç Ç è º    æ ∑ ∏ Ü ñ ó
   - ** í ∏       ≤ ª µ Ω Ω è:**  î æ ¥   Ω æ    µ   µ ≤ ñ   ∫ É `reduceOnly=True`  ¥ ª è FILL    æ ¥ ñ π      ∏ DEC:CLOSE  ∑ ñ   Ç   ≤ ª µ Ω Ω ñ
   - ** õ æ ≥ ñ ∫  :** DEC:CLOSE ‚Üí TP  Ç ñ ª å ∫ ∏  è ∫ â æ `evt_verb == "FILL"`  Ç   `reduceOnly=True`,  ñ Ω   ∫ à µ ‚Üí FN
   - ** ¢ µ   Ç ∏:**  î æ ¥   Ω æ `test_close_decision_with_reduce_only_fill()`  Ç   `test_close_decision_with_cancelled()`

2. ** ü æ ∫     â µ Ω Ω è  î µ Ç µ ∫ Ç æ      † µ ∂ ∏ º ñ ≤ (`decision_making.py` -  ü   æ ± ª µ º   ‚Ññ4):**
   - ** ü   æ ± ª µ º  :** UNCERTAIN    µ ∂ ∏ º    æ ≤ Ω ñ   Ç é  ≤ ∏ º ∏ ∫   ≤    ¥     Ç ∏ ≤ Ω ñ  Ñ ñ ª å Ç   ∏,  â æ  º æ ≥ ª æ  ± É Ç ∏  Ω µ ± µ ∑   µ á Ω æ      ∏  ∑     æ ¥ ∂ µ Ω Ω ñ  Ç   µ Ω ¥ É
   - ** í ∏       ≤ ª µ Ω Ω è:**  î æ ¥   Ω æ regime-based sizing  ∑ `regime_size_multiplier = 0.5`  ¥ ª è UNCERTAIN    µ ∂ ∏ º É
   - ** õ æ ≥ ñ ∫  :** UNCERTAIN ‚Üí  ∑ º µ Ω à µ Ω Ω è position size  Ω   50%  ∑   º ñ   Ç å    æ ≤ Ω æ ≥ æ  ± ª æ ∫ É ≤   Ω Ω è
   - ** ö æ Ω Ñ ñ ≥ É     Ü ñ è:**  í ∏       ≤ ª µ Ω æ  à ª è Ö  á ∏ Ç   Ω Ω è sizing config  ∑ `position_sizing`  ∑   º ñ   Ç å `sizing`

3. ** £   É Ω µ Ω Ω è  í ∏ ∫ æ   ∏   Ç   Ω Ω è `float` (`fsm.py` -  ü   æ ± ª µ º   ‚Ññ8):**
   - ** ü   æ ± ª µ º  :** `safe_float`  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É ≤   ≤ `float()`  â æ  º æ ≥ ª æ      ∏ ∑ ≤ µ   Ç ∏  ¥ æ  ≤ Ç     Ç ∏  Ç æ á Ω æ   Ç ñ
   - ** í ∏       ≤ ª µ Ω Ω è:**  ó   º ñ Ω µ Ω æ `safe_float`  Ω   `safe_decimal`  ∑ `Decimal`  ¥ ª è  ∫     â æ ó  Ç æ á Ω æ   Ç ñ
   - ** õ æ ≥ ñ ∫  :**  í ∏ ∫ æ   ∏   Ç   Ω Ω è `Decimal(str(val))`  ∑   º ñ   Ç å `float(val)`  ¥ ª è  Ñ ñ Ω   Ω   æ ≤ ∏ Ö  ∑ Ω   á µ Ω å
   - ** Ü º   æ   Ç:**  î æ ¥   Ω æ `from decimal import Decimal`

4. ** ¢ µ   Ç É ≤   Ω Ω è  Ç    í   ª ñ ¥   Ü ñ è:**
   - ‚úÖ 11/11  Ç µ   Ç ñ ≤ drift_monitor      æ Ö æ ¥ è Ç å ( ≤ ∫ ª é á   é á ∏  Ω æ ≤ ñ  Ç µ   Ç ∏ reduceOnly)
   - ‚úÖ  ö æ ¥  ∫ æ º   ñ ª é î Ç å   è  ± µ ∑    æ º ∏ ª æ ∫
   - ‚úÖ  ° ∏ Ω Ö   æ Ω ñ ∑   Ü ñ è  Ñ   π ª ñ ≤  º ñ ∂ apps/  Ç   vfoundation/

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ Drift Monitor  ∫ æ   µ ∫ Ç Ω æ    æ ∑   ñ ∑ Ω è î position-closing  Ç    ∑ ≤ ∏ á   π Ω ñ FILL    æ ¥ ñ ó
- ‚úÖ UNCERTAIN    µ ∂ ∏ º  ∑ º µ Ω à É î position size  ∑   º ñ   Ç å    æ ≤ Ω æ ≥ æ  ± ª æ ∫ É ≤   Ω Ω è
- ‚úÖ  í ∏ ∫ æ   ∏   Ç   Ω Ω è Decimal  ∑   º ñ   Ç å float  ¥ ª è  Ñ ñ Ω   Ω   æ ≤ ∏ Ö    æ ∑     Ö É Ω ∫ ñ ≤
- ‚úÖ  î æ ¥   Ω æ  Ω æ ≤ ñ unit  Ç µ   Ç ∏  ∑    æ ≤ Ω ∏ º    æ ∫   ∏ Ç Ç è º  ≤ ∏       ≤ ª µ Ω ∏ Ö    Ü µ Ω     ñ ó ≤
- ‚úÖ AURORA_AUDIT_FIXES_V1    æ ≤ Ω ñ   Ç é      æ Ç µ   Ç æ ≤   Ω æ  Ç    ≥ æ Ç æ ≤ ∏ π  ¥ æ  ñ Ω Ç µ ≥     Ü ñ ó

** ê † ¢ ï § ê ö ¢ ò**:
- Drift Monitor: `apps/reference/domains/execution_position/drift_monitor.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- FSM: `apps/reference/domains/execution_position/fsm.py`
- Tests: `tests/test_drift_unit.py` ( Ω æ ≤ ñ  Ç µ   Ç ∏ reduceOnly)

---

## 2025-10-XX | RID: AURORA_CLOSE_LOGIC_AUDIT_V1 |  ê É ¥ ∏ Ç  õ æ ≥ ñ ∫ ∏  ó   ∫   ∏ Ç Ç è  Ç    õ ñ º ñ Ç É ≤   Ω Ω è  ü æ ∑ ∏ Ü ñ π

**WHY**:  î ª è  ∑   ± µ ∑   µ á µ Ω Ω è  ∫ æ   µ ∫ Ç Ω æ ó    æ ± æ Ç ∏    ∏   Ç µ º ∏  Ç æ   ≥ ñ ≤ ª ñ  Ω µ æ ± Ö ñ ¥ Ω æ  á ñ Ç ∫ æ  ∑   æ ∑ É º ñ Ç ∏,  ∫ æ ª ∏  ñ  è ∫    ∏   Ç µ º    ∑   ∫   ∏ ≤   î    æ ∑ ∏ Ü ñ ó,     Ç   ∫ æ ∂  è ∫  ≤ æ Ω    ∑     æ ± ñ ≥   î  Ω   ∫ æ   ∏ á µ Ω Ω é    æ ∑ ∏ Ü ñ π.

** ó í Ü ¢  ê £ î ò ¢ £  ö û î û í û á  ë ê ó ò:**

### 1. ** ö û õ ò  ° ò ° ¢ ï ú ê  í ò † Ü ® £ Ñ  ó ê ö † ò ¢ ò  ü û ó ò ¶ Ü Æ?**

** ü   è º    ≤ ñ ¥   æ ≤ ñ ¥ å:**  ° ∏   Ç µ º    ≤ ∏   ñ à É î  ∑   ∫   ∏ Ç ∏    æ ∑ ∏ Ü ñ é  ≤  Ω     Ç É   Ω ∏ Ö  ≤ ∏     ¥ ∫   Ö:
- ** ß     æ ≤ ∏ π  ª ñ º ñ Ç  É Ç   ∏ º   Ω Ω è** (max_hold_sec)    µ   µ ≤ ∏ â µ Ω æ
- ** ê ≤     ñ π Ω µ  ∑   ∫   ∏ Ç Ç è**      ∏ REJECTED/EXPIRED  æ   ¥ µ     Ö
- ** ¢   π º µ   Ω      µ   µ ≤ ñ   ∫  ** (UPD:TICK    æ ¥ ñ ó)

** ü æ   ∏ ª   Ω Ω è  Ω    Ñ   π ª ∏  Ç      è ¥ ∫ ∏:**
- `apps/reference/domains/execution_position/fsm_close.py`,    è ¥ ∫ ∏ 75-95: `_check_close_conditions()`
-  ü     ≤ ∏ ª æ 1: `if elapsed > self.max_hold_sec:` (   è ¥ æ ∫ 79)
-  ü     ≤ ∏ ª æ 2: `if msg.verb in ("REJECTED", "EXPIRED"):` (   è ¥ æ ∫ 85)
-  ü     ≤ ∏ ª æ 3: `if msg.op == "UPD" and msg.verb == "TICK":` (   è ¥ æ ∫ 91)

** ö ª é á æ ≤ ñ  Ñ     ≥ º µ Ω Ç ∏  ∫ æ ¥ É:**
```python
# Rule 1: Max hold time (stub)
now = time.time()
elapsed = now - self.position_open_ts
if elapsed > self.max_hold_sec:
    return self._emit_close(msg, "CLOSE_RULE", {"rule": "max_hold_time", "elapsed_sec": elapsed})

# Rule 2: Emergency close on REJECTED/EXPIRED
if msg.verb in ("REJECTED", "EXPIRED"):
    return self._emit_close(msg, "CLOSE_EMERGENCY", {"trigger": msg.verb})
```

** ù   ∑ ≤ ∏  Ç µ   Ç æ ≤ ∏ Ö  Ñ É Ω ∫ Ü ñ π:** 
- `test_close_flow_max_hold_time_triggers()`  ≤ `tests/test_fsm_close.py`
- `test_close_flow_rejected_triggers_emergency_close()`  ≤ `tests/test_fsm_close.py`
- `test_close_flow_timer_check_triggers()`  ≤ `tests/test_fsm_close.py`

### 2. ** Ø ö  ° ò ° ¢ ï ú ê  ó ê ö † ò í ê Ñ  ü û ó ò ¶ Ü Æ?**

** ü   è º    ≤ ñ ¥   æ ≤ ñ ¥ å:**  ° ∏   Ç µ º    ù ï    æ ∑ º ñ â É î    µ   ª å Ω ñ SL/TP  æ   ¥ µ   ∏  Ω    ± ñ   ∂ ñ.  í æ Ω    ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î ** ≤ Ω É Ç   ñ à Ω é  ª æ ≥ ñ ∫ É FSM** (`fsm_close.py`),  è ∫    ≥ µ Ω µ   É î `DEC:CLOSE`  ∫ æ º   Ω ¥ ∏  ∑ `reduceOnly=true`,  â æ    æ Ç ñ º    µ   µ Ç ≤ æ   é é Ç å   è  Ω   MARKET  æ   ¥ µ   ∏  á µ   µ ∑ `binance_execution_adapter.py`.

** ü æ   ∏ ª   Ω Ω è  Ω    Ñ   π ª ∏  Ç      è ¥ ∫ ∏:**
- `apps/reference/domains/execution_position/fsm_close.py`,    è ¥ ∫ ∏ 107-125: `_emit_close()`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`,    è ¥ ∫ ∏ 872-950: `place_order()`

** ö ª é á æ ≤ ñ  Ñ     ≥ º µ Ω Ç ∏  ∫ æ ¥ É:**
```python
# fsm_close.py -  ≥ µ Ω µ     Ü ñ è DEC:CLOSE
dec = Message(
    op="DEC",
    verb="CLOSE",
    src=msg.dst,
    dst="execution_position",
    rid=msg.rid,
    why=why[:80],
    idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
    pld={
        "reduce_only": True,  #  ó ê í ñ î ò true  ¥ ª è  ∑   ∫   ∏ Ç Ç è
        **details,
    },
)
```

** ¢ ∏   ∏  æ   ¥ µ   ñ ≤:** `DEC:CLOSE`    µ   µ Ç ≤ æ   é î Ç å   è  Ω   MARKET  æ   ¥ µ    ∑ `reduceOnly=true`  ≤    ¥     Ç µ   ñ.

** ê ª å Ç µ   Ω   Ç ∏ ≤ Ω    ª æ ≥ ñ ∫  :**  ù µ º   î    ª å Ç µ   Ω   Ç ∏ ≤ Ω æ ó  ª æ ≥ ñ ∫ ∏ -  ≤   ñ  ∑   ∫   ∏ Ç Ç è  π ¥ É Ç å  á µ   µ ∑ `DEC:CLOSE` ‚Üí MARKET  æ   ¥ µ  .

** ù   ∑ ≤ ∏  Ç µ   Ç æ ≤ ∏ Ö  Ñ É Ω ∫ Ü ñ π:** 
- `test_close_flow_emits_dec_close_with_reduce_only()`  ≤ `tests/test_fsm_close.py`
-  í ñ ¥   É Ç Ω ñ  Ç µ   Ç ∏  ¥ ª è    µ   µ Ç ≤ æ   µ Ω Ω è DEC:CLOSE  ≤ MARKET  æ   ¥ µ    ≤ `test_binance_execution_adapter.py`

### 3. ** Ø ö  ° ò ° ¢ ï ú ê  û ë ú ï ñ £ Ñ  ö Ü õ ¨ ö Ü ° ¢ ¨  í Ü î ö † ò ¢ ò •  ü û ó ò ¶ Ü ô?**

** ü   è º    ≤ ñ ¥   æ ≤ ñ ¥ å:**  ° ∏   Ç µ º    ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î **POSITION_GATE  ª æ ≥ ñ ∫ É**  ≤ `decision_making.py`,  è ∫    ± ª æ ∫ É î  Ω æ ≤ ñ  æ   ¥ µ   ∏  Ç æ ≥ æ      º æ ≥ æ  Ω       è º ∫ É  ¥ ª è    ∏ º ≤ æ ª ñ ≤,  â æ  ≤ ∂ µ  º   é Ç å    æ ∑ ∏ Ü ñ ó,  ¥ æ ∑ ≤ æ ª è é á ∏  Ç ñ ª å ∫ ∏  ∑ ≤ æ   æ Ç Ω ñ ( ∑   ∫   ∏ ≤   é á ñ)  æ   ¥ µ   ∏.

** ü æ   ∏ ª   Ω Ω è  Ω    Ñ   π ª ∏  Ç      è ¥ ∫ ∏:**
- `apps/reference/domains/decision_making/decision_making.py`,    è ¥ ∫ ∏ 339-381: POSITION_GATE  ± ª æ ∫

** ö ª é á æ ≤ ñ  Ñ     ≥ º µ Ω Ç ∏  ∫ æ ¥ É:**
```python
# POSITION_GATE: Prevent position accumulation
if existing_position:
    current_qty = decimal.Decimal(str(existing_position.get("net_position", 0)))
    
    # Check if position is effectively zero
    if abs(current_qty) < decimal.Decimal('1e-9'):
        # Allow new position
    else:
        # Determine if this is a reverse trade
        if current_qty > decimal.Decimal('1e-9') and intended_side == "sell":
            # Allow SELL (closing LONG)
        elif current_qty < -decimal.Decimal('1e-9') and intended_side == "buy":
            # Allow BUY (closing SHORT)
        else:
            # Same direction trade - BLOCK
            self.logger.warning(f"[POSITION_GATE] ‚ùå Trade intent BLOCKED for {symbol}: Same direction as existing position")
            self.clear_internal_state()
            return
```

** ¢ æ á Ω ñ  É º æ ≤ ∏  ± ª æ ∫ É ≤   Ω Ω è:**
- `existing_position`  ñ   Ω É î  ¥ ª è    ∏ º ≤ æ ª É
- `abs(current_qty) >= 1e-9` (   æ ∑ ∏ Ü ñ è  Ω µ  Ω É ª å æ ≤  )
- `intended_side`      ñ ≤     ¥   î  ∑  Ω       è º ∫ æ º  ñ   Ω É é á æ ó    æ ∑ ∏ Ü ñ ó (BUY      ∏ LONG, SELL      ∏ SHORT)

** ù   ∑ ≤ ∏  Ç µ   Ç æ ≤ ∏ Ö  Ñ É Ω ∫ Ü ñ π:**  í ñ ¥   É Ç Ω ñ  Ç µ   Ç ∏  ¥ ª è POSITION_GATE  ª æ ≥ ñ ∫ ∏  ≤ `test_decision_making*.py`.

** † ï ó £ õ ¨ ¢ ê ¢ ò  ê £ î ò ¢ £:**
- ‚úÖ ** ó   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π:**  ß ñ Ç ∫ æ  ≤ ∏ ∑ Ω   á µ Ω æ -  á µ   µ ∑  á     æ ≤ ∏ π  ª ñ º ñ Ç  Ç      ≤     ñ π Ω ñ    æ ¥ ñ ó,  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é á ∏ `DEC:CLOSE`  ∑ `reduceOnly=true`
- ‚úÖ **SL/TP  æ   ¥ µ   ∏:**  ù ï    æ ∑ º ñ â É é Ç å   è  Ω    ± ñ   ∂ ñ -  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î Ç å   è  ≤ Ω É Ç   ñ à Ω è  ª æ ≥ ñ ∫   FSM
- ‚úÖ ** õ ñ º ñ Ç É ≤   Ω Ω è    æ ∑ ∏ Ü ñ π:** POSITION_GATE  ± ª æ ∫ É î  Ω   ∫ æ   ∏ á µ Ω Ω è,  ¥ æ ∑ ≤ æ ª è î  Ç ñ ª å ∫ ∏  ∑ ≤ æ   æ Ç Ω ñ  æ   ¥ µ   ∏
- ‚ö†Ô∏è ** ¢ µ   Ç æ ≤ µ    æ ∫   ∏ Ç Ç è:**  í ñ ¥   É Ç Ω ñ  Ç µ   Ç ∏  ¥ ª è  ∫   ∏ Ç ∏ á Ω æ ó  ª æ ≥ ñ ∫ ∏  ∑   ∫   ∏ Ç Ç è  Ç    ª ñ º ñ Ç É ≤   Ω Ω è    æ ∑ ∏ Ü ñ π

** ê † ¢ ï § ê ö ¢ ò:**
- Close FSM: `apps/reference/domains/execution_position/fsm_close.py`
- Manage FSM: `apps/reference/domains/execution_position/fsm_manage.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- Binance Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py`

---

## 2025-10-XX | RID: AURORA_CLOSE_LOGIC_AUDIT_V1 |  ê É ¥ ∏ Ç  õ æ ≥ ñ ∫ ∏  ó   ∫   ∏ Ç Ç è  Ç    õ ñ º ñ Ç É ≤   Ω Ω è  ü æ ∑ ∏ Ü ñ π

**WHY**:  î ª è  ∑   ± µ ∑   µ á µ Ω Ω è  ∫ æ   µ ∫ Ç Ω æ ó    æ ± æ Ç ∏    ∏   Ç µ º ∏  Ç æ   ≥ ñ ≤ ª ñ  Ω µ æ ± Ö ñ ¥ Ω æ  á ñ Ç ∫ æ  ∑   æ ∑ É º ñ Ç ∏,  ∫ æ ª ∏  ñ  è ∫    ∏   Ç µ º    ∑   ∫   ∏ ≤   î    æ ∑ ∏ Ü ñ ó,     Ç   ∫ æ ∂  è ∫  ≤ æ Ω    ∑     æ ± ñ ≥   î  Ω   ∫ æ   ∏ á µ Ω Ω é    æ ∑ ∏ Ü ñ π.

** ó í Ü ¢  ê £ î ò ¢ £  ö û î û í û á  ë ê ó ò:**

### 1. ** ö û õ ò  ° ò ° ¢ ï ú ê  í ò † Ü ® £ Ñ  ó ê ö † ò ¢ ò  ü û ó ò ¶ Ü Æ?**

** ü   è º    ≤ ñ ¥   æ ≤ ñ ¥ å:**  ° ∏   Ç µ º    ≤ ∏   ñ à É î  ∑   ∫   ∏ Ç ∏    æ ∑ ∏ Ü ñ é  ≤  Ω     Ç É   Ω ∏ Ö  ≤ ∏     ¥ ∫   Ö:
- ** ß     æ ≤ ∏ π  ª ñ º ñ Ç  É Ç   ∏ º   Ω Ω è** (max_hold_sec)    µ   µ ≤ ∏ â µ Ω æ
- ** ê ≤     ñ π Ω µ  ∑   ∫   ∏ Ç Ç è**      ∏ REJECTED/EXPIRED  æ   ¥ µ     Ö
- ** ¢   π º µ   Ω      µ   µ ≤ ñ   ∫  ** (UPD:TICK    æ ¥ ñ ó)

** ü æ   ∏ ª   Ω Ω è  Ω    Ñ   π ª ∏  Ç      è ¥ ∫ ∏:**
- `apps/reference/domains/execution_position/fsm_close.py`,    è ¥ ∫ ∏ 75-95: `_check_close_conditions()`
-  ü     ≤ ∏ ª æ 1: `if elapsed > self.max_hold_sec:` (   è ¥ æ ∫ 79)
-  ü     ≤ ∏ ª æ 2: `if msg.verb in ("REJECTED", "EXPIRED"):` (   è ¥ æ ∫ 85)
-  ü     ≤ ∏ ª æ 3: `if msg.op == "UPD" and msg.verb == "TICK":` (   è ¥ æ ∫ 91)

** ö ª é á æ ≤ ñ  Ñ     ≥ º µ Ω Ç ∏  ∫ æ ¥ É:**
```python
# Rule 1: Max hold time (stub)
now = time.time()
elapsed = now - self.position_open_ts
if elapsed > self.max_hold_sec:
    return self._emit_close(msg, "CLOSE_RULE", {"rule": "max_hold_time", "elapsed_sec": elapsed})

# Rule 2: Emergency close on REJECTED/EXPIRED
if msg.verb in ("REJECTED", "EXPIRED"):
    return self._emit_close(msg, "CLOSE_EMERGENCY", {"trigger": msg.verb})
```

** ù   ∑ ≤ ∏  Ç µ   Ç æ ≤ ∏ Ö  Ñ É Ω ∫ Ü ñ π:**  ù µ  ∑ Ω   π ¥ µ Ω æ      µ Ü ∏ Ñ ñ á Ω ∏ Ö  Ç µ   Ç ñ ≤  ¥ ª è  Ü ñ î ó  ª æ ≥ ñ ∫ ∏  ≤ `tests/domains/test_*_close*.py`.

### 2. ** Ø ö  ° ò ° ¢ ï ú ê  ó ê ö † ò í ê Ñ  ü û ó ò ¶ Ü Æ?**

** ü   è º    ≤ ñ ¥   æ ≤ ñ ¥ å:**  ° ∏   Ç µ º    ù ï    æ ∑ º ñ â É î    µ   ª å Ω ñ SL/TP  æ   ¥ µ   ∏  Ω    ± ñ   ∂ ñ.  í æ Ω    ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î ** ≤ Ω É Ç   ñ à Ω é  ª æ ≥ ñ ∫ É FSM** (`fsm_close.py`),  è ∫    ≥ µ Ω µ   É î `DEC:CLOSE`  ∫ æ º   Ω ¥ ∏  ∑ `reduceOnly=true`,  â æ    æ Ç ñ º    µ   µ Ç ≤ æ   é é Ç å   è  Ω   MARKET  æ   ¥ µ   ∏  á µ   µ ∑ `binance_execution_adapter.py`.

** ü æ   ∏ ª   Ω Ω è  Ω    Ñ   π ª ∏  Ç      è ¥ ∫ ∏:**
- `apps/reference/domains/execution_position/fsm_close.py`,    è ¥ ∫ ∏ 107-125: `_emit_close()`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`,    è ¥ ∫ ∏ 872-950: `place_order()`

** ö ª é á æ ≤ ñ  Ñ     ≥ º µ Ω Ç ∏  ∫ æ ¥ É:**
```python
# fsm_close.py -  ≥ µ Ω µ     Ü ñ è DEC:CLOSE
dec = Message(
    op="DEC",
    verb="CLOSE",
    src=msg.dst,
    dst="execution_position",
    rid=msg.rid,
    why=why[:80],
    idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
    pld={
        "reduce_only": True,  #  ó ê í ñ î ò true  ¥ ª è  ∑   ∫   ∏ Ç Ç è
        **details,
    },
)
```

** ¢ ∏   ∏  æ   ¥ µ   ñ ≤:** `DEC:CLOSE`    µ   µ Ç ≤ æ   é î Ç å   è  Ω   MARKET  æ   ¥ µ    ∑ `reduceOnly=true`  ≤    ¥     Ç µ   ñ.

** ê ª å Ç µ   Ω   Ç ∏ ≤ Ω    ª æ ≥ ñ ∫  :**  ù µ º   î    ª å Ç µ   Ω   Ç ∏ ≤ Ω æ ó  ª æ ≥ ñ ∫ ∏ -  ≤   ñ  ∑   ∫   ∏ Ç Ç è  π ¥ É Ç å  á µ   µ ∑ `DEC:CLOSE` ‚Üí MARKET  æ   ¥ µ  .

** ù   ∑ ≤ ∏  Ç µ   Ç æ ≤ ∏ Ö  Ñ É Ω ∫ Ü ñ π:**  ù µ  ∑ Ω   π ¥ µ Ω æ  Ç µ   Ç ñ ≤  ¥ ª è `DEC:CLOSE`  ≤ `test_binance_execution_adapter.py`.

### 3. ** Ø ö  ° ò ° ¢ ï ú ê  û ë ú ï ñ £ Ñ  ö Ü õ ¨ ö Ü ° ¢ ¨  í Ü î ö † ò ¢ ò •  ü û ó ò ¶ Ü ô?**

** ü   è º    ≤ ñ ¥   æ ≤ ñ ¥ å:**  ° ∏   Ç µ º    ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î **POSITION_GATE  ª æ ≥ ñ ∫ É**  ≤ `decision_making.py`,  è ∫    ± ª æ ∫ É î  Ω æ ≤ ñ  æ   ¥ µ   ∏  Ç æ ≥ æ      º æ ≥ æ  Ω       è º ∫ É  ¥ ª è    ∏ º ≤ æ ª ñ ≤,  â æ  ≤ ∂ µ  º   é Ç å    æ ∑ ∏ Ü ñ ó,  ¥ æ ∑ ≤ æ ª è é á ∏  Ç ñ ª å ∫ ∏  ∑ ≤ æ   æ Ç Ω ñ ( ∑   ∫   ∏ ≤   é á ñ)  æ   ¥ µ   ∏.

** ü æ   ∏ ª   Ω Ω è  Ω    Ñ   π ª ∏  Ç      è ¥ ∫ ∏:**
- `apps/reference/domains/decision_making/decision_making.py`,    è ¥ ∫ ∏ 339-381: POSITION_GATE  ± ª æ ∫

** ö ª é á æ ≤ ñ  Ñ     ≥ º µ Ω Ç ∏  ∫ æ ¥ É:**
```python
# POSITION_GATE: Prevent position accumulation
if existing_position:
    current_qty = decimal.Decimal(str(existing_position.get("net_position", 0)))
    
    # Check if position is effectively zero
    if abs(current_qty) < decimal.Decimal('1e-9'):
        # Allow new position
    else:
        # Determine if this is a reverse trade
        if current_qty > decimal.Decimal('1e-9') and intended_side == "sell":
            # Allow SELL (closing LONG)
        elif current_qty < -decimal.Decimal('1e-9') and intended_side == "buy":
            # Allow BUY (closing SHORT)
        else:
            # Same direction trade - BLOCK
            self.logger.warning(f"[POSITION_GATE] ‚ùå Trade intent BLOCKED for {symbol}: Same direction as existing position")
            self.clear_internal_state()
            return
```

** ¢ æ á Ω ñ  É º æ ≤ ∏  ± ª æ ∫ É ≤   Ω Ω è:**
- `existing_position`  ñ   Ω É î  ¥ ª è    ∏ º ≤ æ ª É
- `abs(current_qty) >= 1e-9` (   æ ∑ ∏ Ü ñ è  Ω µ  Ω É ª å æ ≤  )
- `intended_side`      ñ ≤     ¥   î  ∑  Ω       è º ∫ æ º  ñ   Ω É é á æ ó    æ ∑ ∏ Ü ñ ó (BUY      ∏ LONG, SELL      ∏ SHORT)

** ù   ∑ ≤ ∏  Ç µ   Ç æ ≤ ∏ Ö  Ñ É Ω ∫ Ü ñ π:**  ù µ  ∑ Ω   π ¥ µ Ω æ  Ç µ   Ç ñ ≤  ¥ ª è POSITION_GATE  ª æ ≥ ñ ∫ ∏  ≤ `test_decision_making*.py`.

** † ï ó £ õ ¨ ¢ ê ¢ ò  ê £ î ò ¢ £:**
- ‚úÖ ** ó   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π:**  ß ñ Ç ∫ æ  ≤ ∏ ∑ Ω   á µ Ω æ -  á µ   µ ∑  á     æ ≤ ∏ π  ª ñ º ñ Ç  Ç      ≤     ñ π Ω ñ    æ ¥ ñ ó,  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é á ∏ `DEC:CLOSE`  ∑ `reduceOnly=true`
- ‚úÖ **SL/TP  æ   ¥ µ   ∏:**  ù ï    æ ∑ º ñ â É é Ç å   è  Ω    ± ñ   ∂ ñ -  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î Ç å   è  ≤ Ω É Ç   ñ à Ω è  ª æ ≥ ñ ∫   FSM
- ‚úÖ ** õ ñ º ñ Ç É ≤   Ω Ω è    æ ∑ ∏ Ü ñ π:** POSITION_GATE  ± ª æ ∫ É î  Ω   ∫ æ   ∏ á µ Ω Ω è,  ¥ æ ∑ ≤ æ ª è î  Ç ñ ª å ∫ ∏  ∑ ≤ æ   æ Ç Ω ñ  æ   ¥ µ   ∏
- ‚ö†Ô∏è ** ¢ µ   Ç æ ≤ µ    æ ∫   ∏ Ç Ç è:**  í ñ ¥   É Ç Ω ñ  Ç µ   Ç ∏  ¥ ª è  ∫   ∏ Ç ∏ á Ω æ ó  ª æ ≥ ñ ∫ ∏  ∑   ∫   ∏ Ç Ç è  Ç    ª ñ º ñ Ç É ≤   Ω Ω è    æ ∑ ∏ Ü ñ π

** ê † ¢ ï § ê ö ¢ ò:**
- Close FSM: `apps/reference/domains/execution_position/fsm_close.py`
- Manage FSM: `apps/reference/domains/execution_position/fsm_manage.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- Binance Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py`

---

## 2025-01-XX | RID: AURORA_GRANULAR_LOGGING_V1 |  † µ   ª ñ ∑   Ü ñ è  ì     Ω É ª è   Ω æ ≥ æ  õ æ ≥ É ≤   Ω Ω è  ∑  ö æ     µ ª è Ü ñ î é  ü æ ¥ ñ π

**WHY**:  î ª è  ∑   ± µ ∑   µ á µ Ω Ω è    æ ≤ Ω æ ó      æ   Ç µ   µ ∂ É ≤   Ω æ   Ç ñ  Ç    ¥ ñ   ≥ Ω æ   Ç ∏ ∫ ∏ Aurora Core  Ω µ æ ± Ö ñ ¥ Ω æ    µ   ª ñ ∑ É ≤   Ç ∏    Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è  ∑  æ ∫   µ º ∏ º ∏  Ñ   π ª   º ∏  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ  ¥ æ º µ Ω É  Ç    ∫ æ   µ ª è Ü ñ î é    æ ¥ ñ π  á µ   µ ∑ RID (Request ID)  ¥ ª è  ≤ ñ ¥   Ç µ ∂ µ Ω Ω è  ª   Ω Ü é ∂ ∫ ñ ≤    æ ¥ ñ π.

** î Ü á**:
1. ** û Ω æ ≤ ª µ Ω Ω è  Ü µ Ω Ç     ª å Ω æ ó  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  ª æ ≥ É ≤   Ω Ω è** (`aurora/aur_main.py`):
   -  î æ ¥   Ω æ  ∫ ª     JSONFormatter  ¥ ª è    Ç   É ∫ Ç É   æ ≤   Ω æ ≥ æ  ª æ ≥ É ≤   Ω Ω è
   -  ° Ç ≤ æ   µ Ω æ  æ ∫   µ º ñ FileHandler  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ  ¥ æ º µ Ω É: feature_engineering.log, risk_management.log, decision_making.log, execution_management.log
   -  ù   ª   à Ç æ ≤   Ω æ  Ñ ñ ª å Ç   ∏  ª æ ≥ µ   ñ ≤  ∑    Ω   ∑ ≤   º ∏  ¥ ª è  º     à   É Ç ∏ ∑   Ü ñ ó    æ ≤ ñ ¥ æ º ª µ Ω å
   -  î æ ¥   Ω æ event_chain.log  ∑ JSON  Ñ æ   º   Ç É ≤   Ω Ω è º  ¥ ª è  ∫ æ   µ ª è Ü ñ ó    æ ¥ ñ π

2. ** û Ω æ ≤ ª µ Ω Ω è feature_engineering  ¥ æ º µ Ω É** (`apps/reference/domains/feature_engineering/feature_engineering.py`):
   -  î æ ¥   Ω æ  ñ º   æ   Ç chain_logger  Ç   uuid
   -  † µ   ª ñ ∑ æ ≤   Ω æ  ≥ µ Ω µ     Ü ñ é RID  É  º µ Ç æ ¥ ñ on_market_tick
   -  î æ ¥   Ω æ    Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è  æ Ç   ∏ º   Ω Ω è    æ ¥ ñ π,  Ñ ñ ª å Ç     Ü ñ ó  Ç    µ º ñ   ñ ó
   -  õ æ ≥ É ≤   Ω Ω è  ≤ ∫ ª é á   î RID,  Ç ∏      æ ¥ ñ ó,  ¥ æ º µ Ω,    ∏ º ≤ æ ª,    Ç   ¥ ñ é  æ ±   æ ± ∫ ∏

3. ** û Ω æ ≤ ª µ Ω Ω è risk_management  ¥ æ º µ Ω É** (`apps/reference/domains/risk_management/risk_management.py`):
   -  î æ ¥   Ω æ  ñ º   æ   Ç chain_logger  Ç   uuid
   -  † µ   ª ñ ∑ æ ≤   Ω æ  ≥ µ Ω µ     Ü ñ é RID  É  º µ Ç æ ¥ ñ on_features_calculated
   -  î æ ¥   Ω æ    Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è  ≤ Ö ñ ¥ Ω ∏ Ö/ ≤ ∏ Ö ñ ¥ Ω ∏ Ö    æ ¥ ñ π  æ Ü ñ Ω ∫ ∏    ∏ ∑ ∏ ∫ É
   -  õ æ ≥ É ≤   Ω Ω è  ≤ ∫ ª é á   î    Ç   Ç É    ¥ æ ∑ ≤ æ ª É  Ç æ   ≥ ñ ≤ ª ñ  Ç            º µ Ç   ∏    ∏ ∑ ∏ ∫ É

4. ** û Ω æ ≤ ª µ Ω Ω è decision_making  ¥ æ º µ Ω É** (`apps/reference/domains/decision_making/decision_making.py`):
   -  î æ ¥   Ω æ  ñ º   æ   Ç chain_logger  Ç   uuid
   -  † µ   ª ñ ∑ æ ≤   Ω æ  ≥ µ Ω µ     Ü ñ é RID  É  ≤   ñ Ö  º µ Ç æ ¥   Ö  æ ±   æ ± ∫ ∏    æ ¥ ñ π (on_features, on_risk, on_portfolio, on_regime)
   -  î æ ¥   Ω æ    Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è      æ Ü µ   É      ∏ π Ω è Ç Ç è    ñ à µ Ω å
   -  õ æ ≥ É ≤   Ω Ω è  ≤ ∫ ª é á   î  ≤   ñ      ∏ á ∏ Ω ∏  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è  Ç æ   ≥ ñ ≤ (insufficient_equity, risk_not_allowed, signal_neutral, position_block, regime_filters, liquidation_guard,  Ç æ â æ)
   -  î æ ¥   Ω æ  ª æ ≥ É ≤   Ω Ω è  É     ñ à Ω ∏ Ö    ñ à µ Ω å      æ  Ç æ   ≥ ñ ≤ ª é  ∑  ¥ µ Ç   ª è º ∏    æ ∑ ∏ Ü ñ ó

5. ** ° Ç ≤ æ   µ Ω Ω è execution_management  ¥ æ º µ Ω É** (`apps/reference/domains/execution_management/execution_management.py`):
   -  ° Ç ≤ æ   µ Ω æ  ±   ∑ æ ≤ É    Ç   É ∫ Ç É   É  ∫ æ º   æ Ω µ Ω Ç    ¥ ª è  É       ≤ ª ñ Ω Ω è  ≤ ∏ ∫ æ Ω   Ω Ω è º
   -  î æ ¥   Ω æ    Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è  æ Ç   ∏ º   Ω Ω è EVT:TRADE_INTENT_PROPOSED
   -  ü ñ ¥ ≥ æ Ç æ ≤ ª µ Ω æ  ñ Ω Ç µ ≥     Ü ñ é  ∑ execution_position FSM  ¥ ª è  Ñ   ∫ Ç ∏ á Ω æ ≥ æ  ≤ ∏ ∫ æ Ω   Ω Ω è

** † ï ó £ õ ¨ ¢ ê ¢ ò**:
- ‚úÖ  † µ   ª ñ ∑ æ ≤   Ω æ  æ ∫   µ º ñ  ª æ ≥- Ñ   π ª ∏  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ  ¥ æ º µ Ω É  ∑  Ñ ñ ª å Ç     Ü ñ î é    æ ≤ ñ ¥ æ º ª µ Ω å
- ‚úÖ  í     æ ≤   ¥ ∂ µ Ω æ JSON-   Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è  ¥ ª è event_chain.log  ∑  ∫ æ   µ ª è Ü ñ î é RID
- ‚úÖ  ó   ± µ ∑   µ á µ Ω æ    æ ≤ Ω µ    æ ∫   ∏ Ç Ç è      æ Ü µ   É  Ç æ   ≥ ñ ≤ ª ñ  ≤ ñ ¥  æ Ç   ∏ º   Ω Ω è  ¥   Ω ∏ Ö  ¥ æ  ≤ ∏ ∫ æ Ω   Ω Ω è
- ‚úÖ  î æ ¥   Ω æ WHY- ∫ æ ¥ ∏  Ç        ∏ á ∏ Ω ∏  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è  ≤    Ç   É ∫ Ç É   æ ≤   Ω µ  ª æ ≥ É ≤   Ω Ω è
- ‚úÖ  ó ± µ   ñ ∂ µ Ω æ  ∑ ≤ æ   æ Ç Ω É    É º ñ   Ω ñ   Ç å  ∑  ñ   Ω É é á ∏ º  ª æ ≥ É ≤   Ω Ω è º
- ‚úÖ  ü ñ ¥ ≥ æ Ç æ ≤ ª µ Ω æ execution_management  ¥ ª è  ñ Ω Ç µ ≥     Ü ñ ó  ∑ execution_position FSM

** ê † ¢ ï § ê ö ¢ ò**:
- Main Logging: `aurora/aur_main.py` (JSONFormatter, domain handlers, event chain)
- Feature Engineering: `apps/reference/domains/feature_engineering/feature_engineering.py`
- Risk Management: `apps/reference/domains/risk_management/risk_management.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- Execution Management: `apps/reference/domains/execution_management/execution_management.py`
- Event Chain Log: `logs/event_chain.log` (JSON format with RID correlation)

---