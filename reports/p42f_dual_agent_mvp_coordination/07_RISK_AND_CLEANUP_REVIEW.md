# 07 — Risk and Cleanup Review

This document audits security exposures, rate limits, and post-trade position cleanups.

---

## 1. Security Exposures & Mitigation

- **Mainnet Leakage**: The adapter and harness layers employ multiple redundant checks:
  - `verify_handoff_safety` immediately rejects production URLs or non-testnet environments.
  - `BinanceAdapter` checks environment properties and refuses to connect if production is specified without live-mode approval.
- **Key Exposure**: API keys are injected via environment variable substitution (`${BINANCE_TESTNET_API_KEY}`), keeping `.env` files out of Git.

---

## 2. Rate Limiting & Fallback

- **429 Prevention**: Burst requests are prevented by running independent staggered startups (`startup_stagger_sec`) and enforcing rate-limit tracking in the FSM watchdog.
- **Fail-Closed Fallback**: If credentials are missing, the system does not crash silently; rather, it intercepts requests and rejects them with `BLOCKED_CONFIG` or transitions to safe shadow/simulation mode.

---

## 3. Position Cleanup & Cleanup Status

- **Unresolved Exposure**: To guarantee zero lingering exposure, the FSM triggers a comprehensive cleanup sequence on exit:
  - All open/pending limit orders are canceled via `cancel_order`.
  - All active positions are closed out using market-reduce orders.
- **Verification**: In sandbox unit tests, the cleanup sequence successfully executes all cancels and positions queries without errors. In the live testnet runtime, cleanup remains pending because no real external positions could be opened or closed due to missing credentials.
