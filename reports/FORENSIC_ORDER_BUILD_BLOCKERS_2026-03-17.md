# Forensic Report: Why Orders Are Not Being Built

## Scope and method

- Evidence sources only: WAL, runtime logs, current SSOT/config, and code.
- No speculative owner or strategy mapping was used.
- Journals and task notes were checked and not modified.

Checked sources:

- `config/aurora/strategies.yaml`
- `logs/domain_mean_reversion.log`
- `logs/aurora_trades.log`
- `logs/aurora_core.log`
- `ops/wal/2026-03-17.jsonl`
- `apps/reference/domains/decision_making/event_handlers.py`
- `apps/reference/domains/decision_making/strategy_gateway.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/contracts/runtime_readiness.py`

## SSOT symbol to strategy mapping

Canonical activation comes from `config/aurora/strategies.yaml`.

- `DOGEUSDT -> mean_reversion`
- `XRPUSDT -> md_amr`
- `BTCUSDT -> aurora`
- `ETHUSDT -> aurora`
- `SOLUSDT -> aurora`
- `BNBUSDT -> md_amr`
- `1000PEPEUSDT -> llm_microstructure`

This is consistent with `apps/reference/config_loader.py`, which derives tracked symbols from `strategies_registry.assignments` and treats it as SSOT.

## Executive conclusion

The system is not failing at a single point. The evidence shows three distinct stop-points:

1. A large volume of tick-level `EVT:FEATURES_CALCULATED` messages reaches decision making with `tf_sec=0` and is intentionally rejected as bar-only noise. This creates many `NRR-046` rejects, but this is not the final cause for missing bar-driven orders.
2. `DOGEUSDT` on `mean_reversion` does generate valid bar-based signals, but those signals are blocked later in `strategy_signal_gateway` because runtime readiness is in `PROTECT_ONLY`, meaning existing risk may be managed but new risk may not be opened.
3. `aurora` symbols reach strategy evaluation on bar timeframes, but are then blocked by the strict regime allowlist with `REGIME_NOT_ALLOWLISTED` at strategy stage.

So the evidence does not support "the system does not build orders because bars are dead". Bars are alive. Strategy computation is alive. The missing orders come from policy gates after bar processing.

## Tail timeline

### Proven live pipeline

- WAL contains repeated `BAR_CLOSED` events for `DOGEUSDT` at `tf_sec=180` and `tf_sec=300` with `gap_state=CLEAR`.
- Runtime logs show `FeatureEngineering` emitting bar-features for `DOGEUSDT` and `XRPUSDT` at `tf_sec=300`.
- Runtime logs show `DecisionMaking.on_risk()` for `DOGEUSDT` and `XRPUSDT` with `is_trading_allowed: True`.

This proves that market data, bar aggregation, feature engineering, and risk callbacks are still running.

## Case A: DOGEUSDT / mean_reversion / bar-driven path

### Evidence chain

1. SSOT assignment routes `DOGEUSDT` to `mean_reversion`.
2. `logs/domain_mean_reversion.log` shows `MR_INIT` and `MR_REGISTER` for `DOGEUSDT` with `timeframe_sec=300`.
3. The same log shows repeated `MR_SIGNAL` events for `DOGEUSDT`:
   - `07:45:04` BUY
   - `09:15:04` SELL
   - `09:20:04` SELL
   - `09:25:04` SELL
   - `10:35:04` SELL
   - `10:45:05` SELL
   - `12:10:04` BUY
4. `logs/aurora_trades.log` shows matching timestamped guard rejects for the same DOGE intents with `strategy_signal_gateway:open_new_risk_not_allowed`.
5. WAL confirms the same stop-point with full reason payload. Example at `09:25:04`:
   - `reason_code: READINESS_OPEN_NEW_RISK_NOT_ALLOWED`
   - `strategy_id: mean_reversion`
   - `context: strategy_signal_gateway:open_new_risk_not_allowed`
   - `details.runtime_permissions.can_manage_existing_risk: true`
   - `details.runtime_permissions.can_open_new_risk: false`
   - `details.runtime_permissions.mode: PROTECT_ONLY`

### Exact stop-point

`strategy_signal_gateway` rejects new-entry MR signals because runtime readiness allows management of existing risk but forbids opening new risk.

### Code corroboration

- `apps/reference/domains/decision_making/strategy_gateway.py` explicitly rejects non-reduce paths when `runtime_permissions.can_open_new_risk is False` and emits `READINESS_OPEN_NEW_RISK_NOT_ALLOWED`.
- `apps/reference/contracts/runtime_readiness.py` defines this exact permission combination as `PROTECT_ONLY`.

### Conclusion for Case A

`DOGEUSDT` is not failing because MR is silent. MR is emitting signals. The signal-to-intent gateway is blocking them because runtime readiness is not allowing new risk.

## Case B: NRR-046 / tf_sec=0 flood

### Evidence chain

1. WAL repeatedly records `TRADE_INTENT_REJECTED` from `decision_making` with:
   - `reason_code: NRR-046`
   - `stage: DECISION`
   - `why: Ignoring tick-level EVT:FEATURES_CALCULATED (bar-only strategies)`
   - `tf_sec: 0`
2. These occur for multiple symbols, including `DOGEUSDT`, `XRPUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, and `1000PEPEUSDT`.
3. The code in `apps/reference/domains/decision_making/event_handlers.py` rejects feature events with `tf_sec <= 0` before normal bar-driven processing.

### Exact stop-point

This is a deliberate reject in `decision_making:on_features` for tick-level feature payloads reaching a bar-only path.

### Interpretation

This is real and noisy, but it is not sufficient to explain missing orders by itself, because bar-driven flows are also proven alive and are being stopped later by more specific gates.

## Case C: aurora symbol blocked at strategy stage

### Evidence chain

1. SSOT assigns `SOLUSDT`, `ETHUSDT`, and `BTCUSDT` to `aurora`.
2. `logs/aurora_core.log` shows aurora runtime activity on bar cadence:
   - `QUADRATIC_DECISION_TRACE`
   - `KERNEL_DIAG`
   - regime recorded as `LOW_VOLATILITY`
3. WAL repeatedly records `TRADE_INTENT_REJECTED` from `aurora_handler:_emit_strategy_blocked` with:
   - `reason_code: REGIME_NOT_ALLOWLISTED`
   - `stage: STRATEGY`
   - `why: aurora_handler:strict_regime_allowlist: REGIME`
   - `tf_sec: 300`

### Exact stop-point

The aurora handler blocks the strategy result at strategy stage due to strict regime allowlist failure.

### Code corroboration

`apps/reference/domains/decision_making/aurora_decision.py` calls `_emit_strategy_blocked` with `REGIME_NOT_ALLOWLISTED` when the current regime is not in the allowed set.

### Conclusion for Case C

For aurora symbols, the bar pipeline is not dead. The strategy reaches evaluation and then is explicitly blocked by regime policy.

## Root cause ranking

### Rank 1: Runtime readiness blocks new risk for mean_reversion entries

Why ranked first:

- It blocks real bar-driven `DOGEUSDT` strategy signals after they are generated.
- WAL carries the strongest payload: strategy id, side, why chain, and runtime mode `PROTECT_ONLY`.
- This directly prevents order construction for MR entry signals.

### Rank 2: aurora strict regime allowlist blocks aurora strategies at `tf_sec=300`

Why ranked second:

- It blocks real bar-driven aurora strategy evaluation on assigned symbols.
- It is repeated, explicit, and happens after feature/risk/decision activity is already live.

### Rank 3: Tick-level `NRR-046` flood obscures signal quality and produces high reject volume

Why ranked third:

- It is frequent and real.
- But it is a reject of the wrong path, not proof that the correct bar-driven path is dead.

## What is proven versus not proven

Proven:

- SSOT routing is active and DOGE is assigned to MR, not aurora.
- `DOGEUSDT` MR emits bar-based signals.
- Those DOGE MR signals are blocked by `READINESS_OPEN_NEW_RISK_NOT_ALLOWED` with `mode=PROTECT_ONLY`.
- `aurora` symbols reach bar-driven strategy evaluation and are blocked by `REGIME_NOT_ALLOWLISTED`.
- Tick-level `NRR-046` rejects are widespread and deliberate.

Not proven from current evidence:

- A final md_amr-specific order-blocking reason for `XRPUSDT` comparable in quality to the DOGE and aurora cases.

## Narrow fix targets

1. Inspect why runtime readiness is settling in `PROTECT_ONLY` during live MR operation.
   - The blocker is downstream of MR signal generation, not inside MR signal generation.
   - First inspection target: readiness and restore/hydration sources feeding `runtime_permissions` before `strategy_signal_gateway`.

2. Inspect aurora regime allowlist policy versus actual live regime stream.
   - The live regime repeatedly resolves to `LOW_VOLATILITY` while aurora rejects with `REGIME_NOT_ALLOWLISTED`.
   - First inspection target: effective `allowed_regimes` for aurora-assigned symbols and how they are derived at runtime.

3. Reduce `tf_sec=0` feature-path contamination if the intent is bar-only decisioning.
   - This is not the main stop-point, but it adds reject noise and can hide the real bar path during forensics.

## Final answer

Orders are not being built for two proven reasons on the current live path:

- `DOGEUSDT` / `mean_reversion`: real MR bar signals are blocked in `strategy_signal_gateway` because runtime readiness is `PROTECT_ONLY`, so new risk cannot be opened.
- `aurora` symbols: real aurora bar-driven strategy evaluation is blocked at strategy stage by `REGIME_NOT_ALLOWLISTED`.

The frequent `NRR-046` rejects are real but are not the root explanation for missing bar-driven orders; they are a parallel tick-level reject path.