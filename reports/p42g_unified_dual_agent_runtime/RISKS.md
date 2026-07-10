# OPERATIONAL RISKS & SECURITY MITIGATIONS

This document lists the operational risk checkpoints and implemented security controls.

---

## 1. Security Safeguard Checkpoints

- **Mainnet Hard Block**: Both `AgentOrderLifecycleHarness` and `BinanceAdapter` perform redundant checks to reject any command containing production URLs or execution environments other than `testnet` or `sandbox`.
- **Symbol Lease Guard**: The YAML configuration defines disjoint symbol maps. Any attempt by an agent to trade a symbol not assigned to its lease is rejected by the preflight check, returning `BLOCKED_POLICY`.
- **Agent 1 Restricted Interface**: `api_agent_01` is strictly blocked from placing orders, protecting `ETHUSDT` and `SOLUSDT` from unauthorized or automated trades.
- **Idempotency checks**: Commands contain a unique `command_id` which is tracked in `order_lifecycle_traces.jsonl`. Duplicates are detected and rejected.

---

## 2. API Credentials Protection

- **No Key Storage**: No API keys, secrets, or passwords are hardcoded in the codebase, `system.yaml`, or `p42_dual_agent_mvp.yaml`.
- **Environment Ingress**: Credentials must be supplied via local system environment variables (`BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`). If missing, orders transition to safe shadow/simulation mode and return `BLOCKED_CONFIG`.

---

## 3. Rate-Limiting Controls

- **Staggered Startups**: The runner introduces a staggered delay (`startup_stagger_sec: 5`) on startup, preventing simultaneous REST calls from both agents and avoiding rate limit blocks (HTTP 429).
- **Execution Limits**: The YAML configuration specifies `max_orders` and `max_notional` limits per agent, protecting the testnet account balance from rogue loops.
- **FSM Watchdog**: Direct raw client calls (such as ccxt or direct HTTP) are strictly forbidden; all order lifecycles route exclusively through FSM handlers, enforcing centralized rate-limit supervision.
