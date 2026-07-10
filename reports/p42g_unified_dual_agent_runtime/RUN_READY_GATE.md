# RUN READY GATE

This document defines the operational gate status and allowed execution permissions for the unified dual-agent trading runtime.

---

## 1. Gate Specification

- **Integration SHA**: `c55489003d891bf8e0b223fa4e12391452f6eda1`
- **Integration Branch**: `p42-dual-agent-runtime-integrated-primary-20260710`
- **Allowed Agents**:
  - `api_agent_01` (Agent 1): Excluded from placing external testnet orders.
  - `cli_agent_01` (Agent 2): Allowed to place testnet orders.
- **Allowed Symbols**:
  - `api_agent_01`: `ETHUSDT`, `SOLUSDT`
  - `cli_agent_01`: `XRPUSDT`, `BNBUSDT`
- **Configuration Paths**: `config/p42_dual_agent_mvp.yaml`
- **Credential Presence Metadata**:
  - `BINANCE_TESTNET_API_KEY`: False (missing in local testing environment)
  - `BINANCE_TESTNET_API_SECRET`: False (missing in local testing environment)
- **External Adapter Path**: `apps/reference/adapters/binance_adapter.py`
- **Current Execution Mode**: `agent_arena`
- **One Tiny Testnet Proof Allowed**: Yes (Only for Agent 2, `cli_agent_01`, on `XRPUSDT`, pending credential configuration).

---

## 2. Gate Verdict

**VERDICT**: `P42G_GATE_ONE_TESTNET_PROOF_ALLOWED`

### Rationale:
Validation of the unified codebase is fully complete and all tests are passing. Once the operator provides active credentials in the local environment, exactly one tiny testnet order submission and cancel loop is permitted for Agent 2 (`cli_agent_01`) on `XRPUSDT` to prove live end-to-end integration. All other actions remain strictly blocked.
