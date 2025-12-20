# TASK28 — RegimeDetector End-to-End + Hybrid Mode Readiness Report

## 1) New integration test added (no fallbacks, warmup-gated)

### Test
- `tests/integration/test_regime_detector_event_flow.py`:
  - `test_decision_making_does_not_defer_for_regime_after_warmup_ready`
  - plus coverage for subscription + warmup deferral behavior

### What it proves
- RegimeDetector is subscribed and emits `EVT:REGIME_DETECTED`.
- DecisionMaking **does not** emit warmup/regime-missing deferrals once RegimeDetector reaches `warmup.full_ready=true`.
- Forbidden defers checked: `NRR-ARMING-NOT-READY`, `NRR-ARMING-WARMUP-MISSING`, `NRR-REGIME-MISSING`.

### Result
- Ran: `.venv/bin/pytest -q tests/integration/test_regime_detector_event_flow.py`
- Result: **3 passed**

## 1.1) New hybrid config contract test (credentials + mode mapping)

### Test
- `tests/config/test_task28_hybrid_mode_config_contract.py`:
  - `test_hybrid_mode_config_contract_mapping_and_credentials_present`

### What it proves
- `trading_mode == hybrid_live_data_testnet_exec` and the `trading.domain_configuration` mapping matches the intended hybrid wiring.
- `decision_making.arming.require_regime_warmup == true` (fail-closed until RegimeDetector is ready).
- Testnet execution API credentials are present and env placeholders are resolved (no `${VAR}` strings survive).

### Result
- Ran: `.venv/bin/pytest -q tests/integration/test_regime_detector_event_flow.py tests/config/test_task28_hybrid_mode_config_contract.py`
- Result: **4 passed**

## 2) Config scan (hybrid live-features + testnet-execution)

### Effective modes (from config mapping)
- `config/aurora/system.yaml:4` sets `trading_mode: hybrid_live_data_testnet_exec`.
- `config/aurora/trading.yaml:244` defines `domain_configuration`:
  - `market_data: live` (`config/aurora/trading.yaml:245`)
  - `feature_engineering: live` (`config/aurora/trading.yaml:247`)
  - `decision_making: live` (`config/aurora/trading.yaml:249`)
  - `risk_management: testnet` (`config/aurora/trading.yaml:251`)
  - `execution_position: testnet` (`config/aurora/trading.yaml:253`)
- `config/aurora/trading.yaml:257` defines risk mgmt sources:
  - `portfolio_state: testnet` (`config/aurora/trading.yaml:258`)
  - `market_data: live` (`config/aurora/trading.yaml:259`)

### Warmup policy is now strict (fail-closed until RegimeDetector ready)
- `config/aurora/domains.yaml:43` sets `decision_making.arming.require_regime_warmup: true`.

### TTL / staleness
- `config/aurora/system.yaml:19` sets `system.market_data.tick_ttl_ms: 2000`.
  - RegimeDetector will mark stale features as `UNCERTAIN` (data-quality gate) and DecisionMaking will block by `allowed_regimes` when present.

### Basic config-tool validation (structure-only)
- Ran: `.venv/bin/python tools/validate_configs.py`
- Result: **exit 0** (trading/system/regime YAML structure OK; required env vars present)

## 3) Readiness verdict for hybrid mode

### ✅ Ready (conceptually + wiring)
- Domain mode mapping matches “live features + testnet execution” (`config/aurora/trading.yaml:244`).
- RegimeDetector now participates in the runtime event bus and DecisionMaking can be configured to wait for warmup (no trade intents before ready).

### ⚠️ Not fully ready to run “fail-closed” without operational checks
1) **Environment resolution depends on `python-dotenv` / exported env vars**
   - Verified in venv via `tests/config/test_task28_hybrid_mode_config_contract.py` (no `${VAR}` placeholders survive in required testnet creds).
   - If you run outside the venv / without dotenv, `${VAR}` placeholders may remain unresolved and still look “truthy”.
2) **ExecutionPosition has a “shadow_mode” fallback**
   - `apps/reference/domains/execution_position/fsm.py:897`–`apps/reference/domains/execution_position/fsm.py:905` sets `self.shadow_mode = True` on missing API creds instead of failing hard.
   - This violates “no fallbacks” and can mask misconfiguration.
3) **Kill-switch is configured but not enforced**
   - `ops.panic_killswitch: true` is set in config (`config/aurora/system.yaml:23`, `config/aurora/trading.yaml:164`), but repo grep shows no enforcement in runtime domains.

### Minimal “go / no-go” checklist for hybrid run
- Run using venv: `.venv/bin/python -c "from apps.reference.config_loader import get_config; c=get_config(); print(c.binance_api.live.api_key[:4], c.binance_api.testnet.api_key[:4])"`.
- Verify market_data uses live and execution_position uses testnet (effective mapping).
- Ensure ExecPos is **not** in `shadow_mode` (API keys present, URL is testnet).
- Decide whether kill-switch should be implemented or explicitly disabled (right now it’s configured but not active).
