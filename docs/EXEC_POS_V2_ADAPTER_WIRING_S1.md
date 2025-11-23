# ExecPos V2 Adapter Wiring (S1)

**RID:** EP-EXEC-V2-ADAPTER-WIRING-AUDIT-S15  
**Scope:** Document adapter selection for execution_position runtimes (legacy vs V2) and hybrid wiring.

## Adapter Matrix

| runtime_mode | trading_mode            | execution_adapter                |
|--------------|-------------------------|----------------------------------|
| legacy       | testnet / live          | BinanceExecutionAdapter          |
| v2           | testnet / live          | BinanceExecutionAdapter          |
| v2           | sim / shadow            | Shadow/Paper adapter (sim-only)  |

- V2 runtime (`ExecPosRuntimeV2` via `runtime_factory.build_execution_runtime`) uses the same Binance adapter for real trading (testnet/live). Sim/shadow modes rely on a paper adapter outside production paths.
- Legacy runtime mode is blocked in code (`runtime_factory` raises on `runtime_mode=legacy`), but inventory remains for tests/archives.

## Hybrid live-metrics + testnet-exec

- **Market data / metrics source:** live feeds (market_data, feature_engineering, decision_making domains).  
- **Order destination:** testnet execution (execution_position domain), using BinanceExecutionAdapter with testnet credentials.  
- **Config:** `trading_mode: testnet` with hybrid profile (e.g., `shadow_live`), runtime_mode fixed to `v2`.  
- **Goal:** observe real market metrics while executing safely on testnet.

## Wiring Notes

- `apps/reference/main.py` and `runtime_factory.py` select V2 by default and log `runtime_mode='v2' -> using V2RuntimeFacade`. No shadow/paper adapter is auto-injected in production paths.
- Shadow/Paper adapters are test/sim utilities only; production V2 wiring passes a real adapter instance (BinanceExecutionAdapter) when provided by invoking code.

## Validation Targets (S15)

- Static check: no production module imports or references shadow/paper adapters for V2 runtime.
- Smoke wiring: V2 runtime initializes under testnet hybrid config without wiring errors or shadow adapter leakage.
