# BOOTSTRAP READINESS HARDENING — 2026-03-15

## 1. Executive Verdict

**YES** — this package materially improves trade readiness observability and mode correctness.

Before: aurora and md_amr silently accumulated bars for 24h+ after restart with zero operator evidence of whether bootstrap ran, what it imported, or why strategies remained cold. Mode conflict between system.yaml (backtest) and trading.yaml (hybrid) was silently resolved to backtest. Quadratic decision trace was buried at DEBUG level.

After: bootstrap lifecycle is fully observable via structured JSON events at INFO level. Readiness state is machine-queryable per (strategy, symbol, tf). Mode conflict is a hard-fail. Quadratic trace is emitted as FSM event + INFO log.

## 2. Root Cause Confirmed

### RC-1: Mode config conflict — silent backtest override
- `config/aurora/system.yaml` had `trading_mode: "backtest"` at root level
- `config/aurora/trading.yaml` had `trading.mode: hybrid_live_data_testnet_exec`
- Config loader (`config_loader.py:993-1011`) silently forced `trading.mode` to match root `trading_mode` → everything became backtest
- **Runtime effectively landed in BACKTEST path** while operator expected hybrid testnet execution
- **Impact:** Execution adapter path did not submit orders; system appeared "non-trading" but was actually in the wrong mode

### RC-2: Bootstrap hydration invisible
- `execute_startup_basis_hydration()` in `startup_basis_hydrator.py` functionally existed and was wired
- But it emitted zero structured lifecycle events — only scattered LOG.info lines with no JSON structure
- On missing hydration plan (common cold-start scenario), it returned silently with `{"skipped": ["hydration_plan_missing"]}`
- **Operator had no way to distinguish** "bootstrap ran and imported 0 bars" from "bootstrap never ran"
- Result: strategies started with `bars_seen=0` and had to accumulate 301+ bars purely from live data (~24h at 300s timeframe)

### RC-3: Cold-start gate logged at DEBUG
- `aurora_decision.py:266` — `self.logger.debug(...)` for BARS_REQUIRED gate
- `md_amr_handler.py:1099` — `self.mlog.debug(...)` for BARS_REQUIRED gate
- Production log level is typically INFO → these messages were **invisible** to operator
- Cold-start blocks were only visible via WAL reject entries (post-mortem), not in live log stream

### RC-4: Quadratic trace buried
- `aurora_decision.py:508` — `self.logger.debug("[%s] QUADRATIC_DECISION_TRACE %s", ...)` — DEBUG level
- No FSM event emission for successful quadratic compute path
- Only crash/deferred paths had event emission (`EVT:QUADRATIC_KERNEL_CRASH`, `EVT:STRATEGY_DECISION_BLOCKED`)
- **Operator could not see:** score, side, regime, shield_multiplier, deferred status — when path succeeded

## 3. Files Changed

| File | Change |
|------|--------|
| `apps/reference/bootstrap/startup_basis_hydrator.py` | Added `_emit_bootstrap_lifecycle()` helper + structured events: EXECUTOR_START, IMPORTED, SEEDED, READINESS_STATE, EXECUTOR_DONE |
| `apps/reference/domains/decision_making/aurora_handler.py` | Added `get_readiness_diagnostics()` method |
| `apps/reference/domains/decision_making/aurora_decision.py` | Cold-start gate DEBUG→INFO with "quadratic path NOT reached"; added `EVT:QUADRATIC_DECISION_TRACE` emission + INFO log after quadratic compute |
| `apps/reference/domains/decision_making/md_amr_handler.py` | Added `get_readiness_diagnostics()` method; cold-start gate DEBUG→INFO with "quadratic/signal path NOT reached" |
| `apps/reference/config_loader.py` | Replaced silent mode override with MODE-SSOT: hard-fail `ConfigContractError` on non-backtest mismatch; backtest safety preserved; emits `MODE_SSOT_RESOLVED` at startup |
| `config/aurora/system.yaml` | Fixed `trading_mode: "backtest"` → `"hybrid_live_data_testnet_exec"` |
| `tests/test_bootstrap_readiness_hardening.py` | **NEW** — 15 tests across 7 required coverage areas |
| `tests/domains/decision_making/test_aurora_runtime_readiness_contract.py` | Updated 1 assertion to accommodate new `EVT:QUADRATIC_DECISION_TRACE` event |
| `JOURNAL.md` | Updated |
| `JOURNAL_мій.md` | Updated |
| `TODO.md` | Updated with residual debt |

## 4. Bootstrap Readiness Contract

### Lifecycle events (emitted at INFO as structured JSON)

```
BOOTSTRAP_LIFECYCLE STARTUP_BASIS_EXECUTOR_START {
  "event": "STARTUP_BASIS_EXECUTOR_START",
  "ts_ms": 1710518400000,
  "hydration_plan_present": true,
  "bar_aggregator_present": true,
  "backfill_adapter_present": true,
  "guardian_runtime_present": true,
  "handlers_available": ["aurora", "md_amr"]
}

BOOTSTRAP_LIFECYCLE STARTUP_BASIS_IMPORTED {
  "event": "STARTUP_BASIS_IMPORTED",
  "ts_ms": ...,
  "symbol": "BTCUSDT",
  "tf_sec": 300,
  "bars_required": 301,
  "bars_imported": 301,
  "success": true
}

BOOTSTRAP_LIFECYCLE STARTUP_BASIS_SEEDED {
  "event": "STARTUP_BASIS_SEEDED",
  "ts_ms": ...,
  "strategy": "aurora",
  "symbol": "BTCUSDT",
  "tf_sec": 300,
  "bars_required": 301,
  "bars_seeded": 301,
  "source": "startup_replay_import"
}

BOOTSTRAP_LIFECYCLE STRATEGY_READINESS_STATE {
  "event": "STRATEGY_READINESS_STATE",
  "ts_ms": ...,
  "strategy": "aurora",
  "symbol": "BTCUSDT",
  "tf_sec": 300,
  "bars_required": 301,
  "bars_seeded": 301,
  "bars_imported": 301,
  "ready": true
}

BOOTSTRAP_LIFECYCLE STARTUP_BASIS_EXECUTOR_DONE {
  "event": "STARTUP_BASIS_EXECUTOR_DONE",
  "ts_ms": ...,
  "outcome": "completed",
  "imports_count": 3,
  "seeded_count": 6,
  "skipped_count": 0
}
```

### Runtime readiness diagnostics (queryable at any time)

```python
handler.get_readiness_diagnostics()
# Returns per enabled symbol:
[{
  "strategy": "aurora",
  "symbol": "BTCUSDT",
  "tf_sec": 300,
  "bars_seen": 301,
  "bars_required": 301,
  "ready": True,
  "block_reason": None
}]
```

## 5. Mode Conflict Resolution

### Before
- `system.yaml`: `trading_mode: "backtest"`
- `trading.yaml`: `trading.mode: "hybrid_live_data_testnet_exec"`
- Config loader: silently overwrote `trading.mode` → `"backtest"` (line 1008-1009)
- Runtime: **backtest mode** — no orders

### After
- `system.yaml`: `trading_mode: "hybrid_live_data_testnet_exec"` (fixed)
- Config loader: **hard-fail** `ConfigContractError` on non-backtest mismatch
- Backtest safety preserved: if either source says "backtest", both become "backtest" (with WARNING)
- At startup: `MODE_SSOT_RESOLVED: effective_trading_mode=hybrid_live_data_testnet_exec source=system.yaml`
- Operator can verify exact effective mode in startup log

### Behavior matrix

| system.yaml | trading.yaml | Result |
|-------------|-------------|--------|
| hybrid | hybrid | OK, consistent |
| backtest | hybrid | Both → backtest + WARNING |
| hybrid | backtest | Both → backtest + WARNING |
| live | hybrid | **ConfigContractError** — must fix |
| hybrid | live | **ConfigContractError** — must fix |

## 6. Quadratic Visibility Outcome

### Before
- Quadratic trace built but `logger.debug(...)` — invisible at production log level
- No FSM event for successful compute path
- Only kernel crash and deferred paths emitted events
- Operator could not distinguish: "path not reached" vs "computed but not logged"

### After
- **INFO log**: `[BTCUSDT] QUADRATIC_DECISION_TRACE score=0.123456 side=BUY deferred=False regime=LOW_VOLATILITY`
- **FSM event**: `EVT:QUADRATIC_DECISION_TRACE` with full payload:
  ```json
  {
    "schema_version": 1,
    "strategy_id": "aurora",
    "symbol": "BTCUSDT",
    "tf_sec": 300,
    "score": 0.123456,
    "side": "BUY",
    "deferred": false,
    "regime": "LOW_VOLATILITY",
    "shield_multiplier": 1.0,
    "quadratic_path_reached": true,
    "compact_trace": {...},
    "ts_ms": 1710518400000
  }
  ```
- **Cold-start gate**: INFO with explicit `"quadratic path NOT reached"` message
- **Operator can now distinguish:**
  1. Quadratic path not reached → `BARS_REQUIRED gate ... quadratic path NOT reached` (INFO)
  2. Quadratic path reached, deferred → `EVT:STRATEGY_DECISION_BLOCKED` with `AURORA_KERNEL_DEFERRED`
  3. Quadratic path reached, blocked → `EVT:STRATEGY_DECISION_BLOCKED` with specific reason
  4. Quadratic path reached, candidate produced → `EVT:QUADRATIC_DECISION_TRACE` + `EVT:STRATEGY_SIGNAL_PRODUCED`

## 7. Tests Added/Updated

### New: `tests/test_bootstrap_readiness_hardening.py` — 15 tests

| # | Test | Covers |
|---|------|--------|
| 1 | `test_emit_bootstrap_lifecycle_logs_at_info` | Lifecycle events land at INFO |
| 2 | `test_emit_bootstrap_lifecycle_json_parseable` | Lifecycle payload is valid JSON with correct fields |
| 3 | `test_execute_hydration_emits_start_and_done_on_missing_plan` | Missing plan still emits START + DONE |
| 4 | `test_aurora_readiness_blocked_when_insufficient` | Aurora 71/301 → blocked with explicit reason |
| 5 | `test_md_amr_readiness_blocked_when_insufficient` | md_amr 23/96 → blocked with explicit reason |
| 6 | `test_aurora_ready_after_full_seed` | Aurora 301/301 → ready=True |
| 7 | `test_md_amr_ready_after_full_seed` | md_amr 96/96 → ready=True |
| 8 | `test_mode_ssot_conflict_raises_on_non_backtest_mismatch` | Non-backtest mode mismatch → ConfigContractError |
| 9 | `test_mode_ssot_backtest_forces_everywhere` | Backtest from either source → both backtest |
| 10 | `test_consistent_modes_pass_silently` | Matching modes → no error |
| 11 | `test_cold_start_gate_logs_at_info_not_debug` | Cold-start gate visible at INFO |
| 12 | `test_diagnostics_structure` | md_amr diagnostics return complete structured data |
| 13 | `test_aurora_cold_has_explicit_block_reason` | Every cold aurora symbol has non-None block_reason |
| 14 | `test_md_amr_cold_has_explicit_block_reason` | Every cold md_amr symbol has non-None block_reason |
| 15 | `test_readiness_state_emitted_for_each_requirement` | STRATEGY_READINESS_STATE event parseable |

### Updated: `tests/domains/decision_making/test_aurora_runtime_readiness_contract.py`
- `test_aurora_objective_missing_exposure_summary_blocks_explicitly`: Changed `assert not emitted` → `assert not any(name == "EVT:STRATEGY_SIGNAL_PRODUCED" for name, _ in emitted)` to accommodate new `EVT:QUADRATIC_DECISION_TRACE` event

### Results
```
15 new tests:     15/15 PASSED
Domain suite:   1231/1231 PASSED, 35 skipped, 0 failed
```

## 8. Residual Debt

### P1: Hydration data-path not yet verified end-to-end
- `PillarBackfillService.fetch_candles()` must actually return sufficient bars for all enabled symbols in production
- `started_strategy_handlers` dict timing dependency — must be populated before hydration runs
- Need integration test for full bootstrap → hydration → seed → readiness path

### P1: EVT:QUADRATIC_DECISION_TRACE sink routing
- Event is emitted on FSM bus but not yet confirmed to land in the operator's actual decision trace sink/file
- Consider adding JSONL file sink for quadratic traces

### P2: Readiness periodic health check
- `get_readiness_diagnostics()` is currently pull-only (must be called explicitly)
- Should wire to periodic emitter (e.g. every 60s post-startup) for continuous visibility

### P2: Per-domain mode override visibility
- `trading.yaml` has `domain_configuration.market_data.trading_mode: live` etc.
- These per-domain overrides are not yet covered by the MODE-SSOT hard-fail check
- Currently only root `trading_mode` vs `trading.mode` conflict is caught

---

## Audit Questions Answered

### 1. Why exactly were aurora and md_amr staying cold?
**Answer:** Three compounding causes:
- Mode was silently backtest → execution adapter path inactive
- Bootstrap hydration ran but fetch results may have been insufficient (only 71/301 bars for aurora)
- Cold-start gate blocked all signals, but logged at DEBUG → operator couldn't see why no trades were happening

### 2. Did bootstrap executor actually run before the fix?
**Answer:** Yes, `execute_startup_basis_hydration()` was called. The code path existed. But without structured lifecycle events, there was zero operator evidence of:
- Whether it started
- How many bars it imported per symbol
- Whether seeding succeeded
- Which strategies became ready vs remained blocked

### 3. What exact wiring/data-path prevented seed from becoming visible to handlers?
**Answer:** The seed path (`_seed_handler_counter → handler.seed_startup_bars()`) worked mechanically when data was available. The visibility problem was twofold:
- Import may have returned insufficient bars (only 71 out of required 301)
- Even when seed counted correctly, the state was only visible in `_bars_seen_since_restart` internal dict — no external diagnostic or event exposed it

### 4. After the fix, where can the operator see bootstrap and readiness?
| Question | Where |
|----------|-------|
| Bootstrap start/done | `BOOTSTRAP_LIFECYCLE STARTUP_BASIS_EXECUTOR_START` / `_DONE` in startup logs |
| Import counts | `BOOTSTRAP_LIFECYCLE STARTUP_BASIS_IMPORTED` per (symbol, tf) |
| Seed counts | `BOOTSTRAP_LIFECYCLE STARTUP_BASIS_SEEDED` per (strategy, symbol, tf) |
| Readiness state | `BOOTSTRAP_LIFECYCLE STRATEGY_READINESS_STATE` per (strategy, symbol, tf) |
| Runtime readiness | `handler.get_readiness_diagnostics()` — list of dicts |
| Quadratic trace | `EVT:QUADRATIC_DECISION_TRACE` FSM event + INFO log |
| Mode truth | `MODE_SSOT_RESOLVED: effective_trading_mode=...` in startup logs |

### 5. Is mode conflict truly resolved, or only made louder?
**Answer:** Both. The actual config file is fixed (`system.yaml` now says `hybrid_live_data_testnet_exec`). Additionally, the config loader now hard-fails on non-backtest mismatches, preventing future silent overrides. The conflict is **resolved** for this instance and **prevented** for future instances.

### 6. What remains as residual debt?
See Section 8 above. Key items: end-to-end hydration data-path verification, quadratic trace sink routing confirmation, periodic readiness health emitter.
