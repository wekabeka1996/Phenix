
---

## 1. Executive Verdict

The system can remain non-tradable despite live market data and completed infrastructure startup due to **multiple simultaneous architectural defects (Classification E)** with two primary interacting root causes: **(A) startup seed propagation gap** — the warmup gate releases unconditionally in a `finally:` block regardless of whether handler-local `_bars_seen_since_restart` counters were actually seeded, and the `warmup_report` never tracks handler seed success (it only tracks FE/regime warmup), meaning a Binance fetch failure during basis hydration leaves all handlers cold at `_bars_seen=0` against a `_basis_required=301` gate that takes ~25 hours of live 5m bars to naturally satisfy; and **(B) duplicated readiness contract layering** — the cold-start gate (`_bars_seen < _basis_required`) lives exclusively inside each handler's `_process_decision()` while the warmup gate (`can_open_new_risk`) lives in `startup_warmup.py` and is enforced at `StrategyGateway`, creating two independent blocking layers where one can report "ready" while the other remains permanently blocked, with no cross-layer visibility or diagnostic surfacing. A tertiary cause is that mean_reversion is regime-gated at the `map_to_flat_regime()` layer and only DOGEUSDT is enabled, making it structurally alive but operationally dead whenever the market is not in MEAN_REVERSION or LOW_VOLATILITY regime.

---

## 2. Producer Map for `CMD:PROCESS_STRATEGY`

**Schema SSOT**: `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`
- `tf_sec`: required, integer, min 60, max 3600
- `bar_close_ts`: required, integer, min 1
- `warmup`: required, object with `full_ready` bool + `ticks_seen` int
- `additionalProperties: false`

| # | Producer Path | File / Function | Live Reachable? | Validates tf_sec? | Validates bar_close_ts? | Risk |
|---|---|---|---|---|---|---|
| **1** | Feature Engineering bar-close trigger | `feature_engineering.py:1819` / `_calculate_and_emit_features_for_tf()` | **YES** (primary live path) | **YES** (gate L1669: >= 60) | **YES** (gate L1713) | **LOW** — 5 imperative fail-closed gates; no JSON schema validation but functionally equivalent |
| **2** | Alpha Search replay self-trigger | `alpha_search/runtime/scenario_worker.py:150` / `process_snapshot()` | **NO** (LocalBus only, isolated backtest) | **PARTIAL** (Pydantic `ge=0`, allows 0) | **YES** (Pydantic required) | **NONE for live** — isolated LocalBus, never reaches live handlers |

**No JSON schema validation** is performed by any producer before emission. Producer 1 uses imperative Python gates that are functionally equivalent to the schema contract. There are zero unsafe live-reachable producer paths.

---

## 3. Aurora Readiness Contract Chain

The full chain from `CMD:PROCESS_STRATEGY` arrival to trade intent has **four independent blocking layers**, two in the handler and two in the gateway:

### Layer 1: Handler Pre-Decision Gates (`aurora_handler.py:579-693`)
```
Gate 0: _is_enabled == False           → STRATEGY_DISABLED (permanent)
Gate 1: tf_sec is None                 → MISSING_TF_SEC
Gate 2: tf_sec == 0                    → MISSING_TF_SEC
Gate 3: tf_sec != self.timeframe_sec   → silent skip (wrong timeframe)
Gate 4: bar_close_ts missing           → DATA_NOT_READY
→ _bars_seen_since_restart[symbol] += 1  (increment AFTER gates, BEFORE decision)
```

### Layer 2: Handler Decision Gates (`aurora_decision.py:165-1081`)
```
_basis_required = regime_detector_required_bars(config)
               = max(sma_long=192, atr_period+atr_sma_length-1=301) = 301

COLD-START GATE: _bars_seen < 301     → BARS_REQUIRED_COLD_START ★★★
Regime heartbeat: never received       → NRR-REGIME-NO-HEARTBEAT (permanent until detector emits)
Regime heartbeat: stale >15min         → NRR-REGIME-DETECTOR-DEAD
Contract unresolved: profile missing   → READINESS_CONTRACT_UNRESOLVED (permanent)
```

### Layer 3: Signal Payload Construction (`aurora_decision.py:1086-1542`)
```
readiness.warmup_ok = state.warmup_full_ready  (set from cmd.warmup.full_ready)
runtime_permissions.can_open_new_risk  (computed from gap policy + restore + startup overlay)
```

### Layer 4: StrategyGateway (`strategy_gateway.py:205-777`)
```
READINESS_WARMUP_NOT_OK: readiness.warmup_ok != True
READINESS_OPEN_NEW_RISK_NOT_ALLOWED: can_open_new_risk == False
NRR-RISK-SKEW-UNTIL-REFRESH: risk skew defer count exceeded → PERMANENT LATCH
+ risk gate, flip gate, sizing gate, TTL gate, etc.
```

### Duplicated Checks Identified

| Check | Handler Level | Gateway Level | Divergence Risk |
|-------|--------------|---------------|-----------------|
| Warmup readiness | Sets `warmup_full_ready` from CMD, embeds in payload | Enforces `warmup_ok is True` or rejects | **LOW** — intentional producer-consumer split |
| Cold-start bars | Hard gate: `_bars_seen < _basis_required` (L2) | **NOT PRESENT** | **HIGH** — gateway has no visibility into handler cold-start state |
| Strategy arbitration | Not checked in handler | Checked at gateway + IntentBuilder (double-check) | **LOW** — defense-in-depth |
| `can_open_new_risk` | Computed in handler emission | Enforced at gateway | **MEDIUM** — handler may compute True from stale gap_status |

### Permanent Latch Conditions
1. `_basis_required=301` with seed failure: takes ~25h of live 5m bars to recover
2. Regime detector never starts: permanent `NRR-REGIME-NO-HEARTBEAT`
3. Risk-skew defer count exceeded: permanent `until_refresh` latch
4. Config corruption: permanent `READINESS_CONTRACT_UNRESOLVED`

---

## 4. Mean Reversion Runtime Analysis

**Structural status: ALIVE but operationally blocked by regime.**

### Runtime path
```
CMD:PROCESS_STRATEGY (tf_sec=300)
  → MeanReversionHandler._on_process_strategy()
    GATE: tf_sec matches 300 (5m)
    GATE: bar_close_ts, bar data present
    GATE: symbol in _enabled_symbols
  → MeanReversion1mStrategy.on_bar()
    GATE: len(bars) >= min_bars (25)  ← only 25 bars, NOT 301
    GATE: map_to_flat_regime() → returns None for TREND_UP, TREND_DOWN, HIGH_VOLATILITY, UNCERTAIN
    GATE: flat_regime.name in allowed_regimes
  → _emit_signal() → EVT:STRATEGY_SIGNAL_PRODUCED
  → StrategyGateway (shared gate chain)
```

### Key finding: MR does NOT have Aurora's `_basis_required` contract
- MR only needs `min_bars=25` locally accumulated bars
- MR has `restart_local_basis_counter=False` in the compatibility matrix → **seed_startup_bars is never called for MR**
- MR accumulates bars solely from live `CMD:PROCESS_STRATEGY` commands

### Why MR is blocked
1. **DOGEUSDT is the only enabled asset** (all others `enabled: false` in mean_reversion.yaml)
2. **Regime gate**: `map_to_flat_regime()` in `regime_mapping.py:77` returns `None` for TREND_UP, TREND_DOWN, HIGH_VOLATILITY, UNCERTAIN — only MEAN_REVERSION and LOW_VOLATILITY pass
3. MR is not broken by any contract defect — it is correctly vetoed by market regime conditions

### Structural independence from Aurora
MR cannot be broken by Aurora's seed failure or cold-start block. MR only needs 25 bars (2 hours at 5m). Its only shared-failure mode with Aurora is at the `StrategyGateway` level (risk gate, readiness contract).

---

## 5. MD-AMR Runtime Analysis

**Structural status: ALIVE but blocked by cold-start bars gate, same root cause as Aurora.**

### Runtime path
```
CMD:PROCESS_STRATEGY (tf_sec=900, 15m bars)
  → MDAMRHandler._on_process_strategy()
    GATE: symbol in _enabled_symbols (XRPUSDT, BNBUSDT)
    GATE: tf_sec matches 900
    GATE: mandatory_live_warmup (2h after startup) ★
    GATE: warmup.full_ready is True
    GATE: _bars_seen < _basis_required (301) → BARS_REQUIRED_COLD_START ★★★
    GATE: strategy.on_bar() returns DEFER until internal buffers filled
  → _emit_signal() → EVT:STRATEGY_SIGNAL_PRODUCED
  → StrategyGateway (shared gate chain with md_amr-specific trace validation)
```

### Key finding: md_amr has the SAME cold-start defect as Aurora

From `strategy_compatibility_matrix.py:237-260`:
```python
basis_required_bars = max(
    channel_window_bars=12,
    atr_window=14,
    atr_stats_window=64,
    regime_detector_required_bars(config)=301  ← dominates
) = 301
```

Because `needs_regime=True`, the regime detector's 301-bar requirement dominates. MD-AMR needs 301 * 15min = **3.14 days** of live 15m bars to pass the cold-start gate if seeding fails.

### Additional blocker: mandatory_live_warmup
MD-AMR has a unique 2-hour mandatory live warmup period (`_MANDATORY_LIVE_WARMUP_SEC = 7200`) set during `_hydrate_state_from_rest()`. Every signal during this period is converted to `EVT:TRADE_INTENT_REJECTED` with `MANDATORY_LIVE_WARMUP`. This cannot be bypassed.

### Shared seed vulnerability
`restart_local_basis_counter=True` → `seed_startup_bars()` IS called for md_amr. If basis import fails, md_amr hits the same `_bars_seen=0 < _basis_required=301` gate as Aurora.

---

## 6. Startup Seed Materialization Analysis

### Execution flow in main.py
```
Phase D: market_data.start_async()        ← LIVE BARS START FLOWING
Phase E: HTF pillar backfill (D1/H4/M15)  → warmup_statuses["feature_engineering"]
Phase F: Regime backfill (321 × 5m bars)   → warmup_statuses["regime_detector"]
Phase G: execute_startup_basis_hydration() → _basis_summary (logged, not tracked)
Phase H: build_startup_warmup_report()     → checks FE + regime ONLY, not handler seed
         release_startup_warmup_gate()     → UNCONDITIONAL (finally: block)
```

### The critical gap

**`build_startup_warmup_report()` (`startup_warmup.py:356-436`) tracks three warmup owners:**
1. `feature_engineering_status` — from `warmup_statuses[symbol]["feature_engineering"]`
2. `regime_status` — from `warmup_statuses[symbol]["regime_detector"]`
3. `execution_restore` — from `analytics_restore_report`

**It does NOT track:**
- `_basis_summary` (handler seed success/failure)
- `_bars_seen_since_restart` on any handler
- Whether `seed_startup_bars()` was actually called or succeeded

### Failure sequence
```
1. Startup begins → handlers constructed with _bars_seen = 0
2. Market data starts → live bars begin incrementing _bars_seen (slowly, 1 per 5min)
3. Basis hydration fails (Binance -1007 timeout, adapter missing, etc.)
   → _seed_handler_counter() never called OR called with seeded_bars=0
   → _bars_seen_since_restart stays at 0 (or tiny live count)
4. Warmup report shows: FE=WARMED, regime=WARMED ← looks healthy
5. release_startup_warmup_gate() ← unconditional, in finally: block
6. Handlers receive live bars but:
   Aurora: _bars_seen=3 < _basis_required=301 → BARS_REQUIRED_COLD_START for ~25h
   md_amr: _bars_seen=0 < _basis_required=301 → BARS_REQUIRED_COLD_START for ~3.14 days
7. System appears "warmed and running" but ALL handlers are cold-blocked
```

### Conditions that skip seeding
1. `hydration_plan` is None (planner threw exception)
2. `bar_aggregator` is None (not configured)
3. `backfill_adapter` is None (execution_position missing)
4. Binance fetch returns 0 bars (timeout, rate limit, symbol not found)
5. `seeded_bars <= 0` in `_seed_handler_counter()` → early return None
6. Handler raw not found in `started_strategy_handlers` dict
7. Handler lacks `seed_startup_bars` attribute

---

## 7. Architectural Breakpoints

| # | File | Function/Line | Defect Class | Why It Breaks Runtime |
|---|---|---|---|---|
| **1** | `main.py:1277-1278` | `finally: release_startup_warmup_gate()` | **Seed propagation gap (C)** | Gate releases unconditionally; does not verify `_basis_summary` or handler `_bars_seen` state |
| **2** | `startup_warmup.py:356-436` | `build_startup_warmup_report()` | **Observability gap (C)** | Report checks FE + regime + restore but never checks handler seed success; operator sees "WARMED" while handlers are cold |
| **3** | `aurora_decision.py:250` | `if _basis_required and _bars_seen < _basis_required` | **Handler-exclusive gate (A)** | Cold-start gate exists only in handler, invisible to gateway and warmup report; no upstream recovery path |
| **4** | `md_amr_handler.py:1106-1163` | Cold-start bars gate | **Same as #3 for md_amr (A)** | Identical pattern: handler-local gate, invisible to gateway/warmup |
| **5** | `strategy_compatibility_matrix.py:247` | `_structural_regime_basis_required_bars(config)` in md_amr max() | **Over-constrained basis (D)** | md_amr's own data needs are 64 bars max, but `needs_regime=True` inflates to 301; 15m × 301 = 3.14 days |
| **6** | `md_amr_handler.py:~1072` | `_is_mandatory_live_warmup_active()` | **Compounding blocker (D)** | 2-hour hard warmup on top of seed failure means md_amr is blocked even longer |
| **7** | `regime_mapping.py:77-130` | `map_to_flat_regime()` | **Regime veto (D)** | MR blocked for any regime other than MEAN_REVERSION/LOW_VOLATILITY; single-asset (DOGE) amplifies |

---

## 8. Minimal Fix Plan

### Immediate Unblock Fixes (P0)

**Fix 1: Conditional warmup gate release based on seed verification**
- **File**: `main.py:1247-1278`
- **Change**: After `execute_startup_basis_hydration()`, inspect `_basis_summary` for seed records. If any handler/symbol pair has `seeded_bars >= required_bars`, mark that handler/symbol as seed-verified. Only release the warmup gate if at least one handler is seed-verified, OR emit a CRITICAL event if no handlers were seeded.
- **Impact**: Prevents false "warmed" state when handlers are actually cold.

**Fix 2: Feed `_basis_summary` into `warmup_report`**
- **File**: `startup_warmup.py:build_startup_warmup_report()`
- **Change**: Add a `handler_seed_statuses` parameter. For each strategy+symbol, if `restart_local_basis_counter=True` and seed status is FAILED/SKIPPED/0, add a blocker token `"handler_basis_seed_failed:{strategy_id}"`.
- **Impact**: Warmup report accurately reflects handler-level readiness.

**Fix 3: Retry basis hydration on failure before gate release**
- **File**: `main.py` Phase G
- **Change**: If `execute_startup_basis_hydration()` returns any symbol with 0 seeded bars and `required_bars > 0`, retry once (with exponential backoff) before proceeding to warmup report.
- **Impact**: Transient Binance failures don't cause 25-hour cold-start.

### Contract Hardening (P1)

**Fix 4: Surface handler cold-start state to gateway**
- **Files**: `aurora_handler.py`, `md_amr_handler.py`
- **Change**: Include `_bars_seen_since_restart` and `_basis_required` in the `EVT:STRATEGY_SIGNAL_PRODUCED` readiness payload (e.g., `readiness.basis_bars_seen`, `readiness.basis_bars_required`). This makes the cold-start gate visible at gateway level for diagnostics without adding a duplicate gate.
- **Impact**: Gateway can log/trace why signals never arrive from a handler.

**Fix 5: Separate md_amr basis requirement from regime detector**
- **File**: `strategy_compatibility_matrix.py:237-260`
- **Change**: If md_amr has `needs_regime=True`, apply the regime basis requirement to a separate `regime_warmup_required` field, not to the handler's `basis_required_bars`. Let the handler check its own data needs (64 bars) independently of the regime detector's warmup (tracked separately in `warmup_statuses`).
- **Impact**: md_amr cold-start drops from 3.14 days to ~16 hours (64 × 15min).

**Fix 6: Wire `get_readiness_diagnostics()` to periodic emitter**
- **Files**: `aurora_handler.py`, `md_amr_handler.py`, `decision_making.py`
- **Change**: Call `handler.get_readiness_diagnostics()` every 60s and emit as structured event.
- **Impact**: Operator can see real-time handler readiness including bars_seen vs basis_required.

### Regression Tests (P2)

**Fix 7: mean_reversion diagnostic parity**
- **File**: `mean_reversion_handler.py`
- **Change**: Add `get_readiness_diagnostics()` method matching aurora_handler's interface.
- **Impact**: Operational visibility for MR regime gates.

---

## 9. Required Tests

| # | Test | File to Create | What It Proves |
|---|---|---|---|
| 1 | `test_warmup_gate_not_released_on_seed_failure` | `tests/bootstrap/test_warmup_gate_seed_verification.py` | Gate does not release when `_basis_summary` shows 0 seeded bars |
| 2 | `test_warmup_report_includes_handler_seed_status` | `tests/bootstrap/test_warmup_report_seed_coverage.py` | `build_startup_warmup_report()` surfaces handler seed failures as blockers |
| 3 | `test_basis_hydration_retry_on_transient_failure` | `tests/bootstrap/test_basis_hydration_retry.py` | Single Binance failure triggers retry before gate release |
| 4 | `test_handler_cold_start_surfaced_in_signal_readiness` | `tests/domains/decision_making/test_handler_cold_start_readiness.py` | `EVT:STRATEGY_SIGNAL_PRODUCED` payload includes `basis_bars_seen` and `basis_bars_required` |
| 5 | `test_md_amr_basis_decoupled_from_regime_detector` | `tests/contracts/test_md_amr_basis_independence.py` | md_amr `basis_required_bars` reflects its own data needs (64), not regime detector's (301) |
| 6 | `test_concurrent_live_bars_during_warmup_preserved` | `tests/bootstrap/test_seed_max_preserves_live.py` | `seed_startup_bars()` with `max()` semantics does not overwrite live bar count |
| 7 | `test_mean_reversion_readiness_diagnostics_contract` | `tests/domains/decision_making/test_mr_readiness_diagnostics.py` | MR handler exposes `get_readiness_diagnostics()` with regime gate status |

---

## 10. Final Classification

**Multiple architectural defects (Classification E)** — two primary interacting root causes plus a tertiary operational blocker:

### Root Cause 1: Startup seed propagation gap (C)
**Proven from code**: `main.py:1277` releases the warmup gate in `finally:` unconditionally. `build_startup_warmup_report()` (startup_warmup.py:356-436) checks only `feature_engineering`, `regime_detector`, and `execution_restore` — never handler seed status. `_basis_summary` from `execute_startup_basis_hydration()` is `LOG.info()`'d and discarded. If Binance basis fetch fails (timeout, rate limit, adapter absent), handlers start with `_bars_seen_since_restart=0` while the system reports WARMED.

### Root Cause 2: Handler-exclusive cold-start gate invisible to system (A)
**Proven from code**: The `_bars_seen < _basis_required` gate at `aurora_decision.py:250` and `md_amr_handler.py:1106` is **only** checked inside each handler. The `StrategyGateway` never sees this state — it only receives signals that already passed the gate. If the gate blocks all signals, the gateway sees silence, not a diagnosed block. The warmup report has no visibility into this state. The `get_readiness_diagnostics()` method exists but is not wired to any periodic emitter.

### Root Cause 3 (tertiary): mean_reversion regime operational block (D)
**Proven from code**: `map_to_flat_regime()` in `regime_mapping.py:77-130` returns `None` for TREND_UP, TREND_DOWN, HIGH_VOLATILITY, and UNCERTAIN regimes. Only DOGEUSDT is enabled. This is not a code defect — it is correct behavior — but combined with roots 1+2 it means **zero strategies** can trade when Aurora/md_amr are cold-blocked and the market is trending.

**Interaction**: Root cause 1 causes root cause 2 to trigger. Without the seed propagation gap, the cold-start gate would pass immediately (seeded count >= 301). The system is designed so that warmup seeds the handlers, but the propagation path has no verification, no retry, and no diagnostic surfacing — making the cold-start gate a silent permanent block.

Completed: *Synthesize findings into final forensic report* (7/7)

Investigation complete. All findings derived exclusively from source code inspection — zero log-based or report-based reasoning. The three interacting architectural defects are fully traced with exact file paths, line numbers, and code-level proof.



---

## Corrections to Prior Report

### Correction 1: FSM Schema Validation — EXISTS in code but DEAD at runtime

The prior claim "No JSON schema validation is performed by any producer" was **wrong for the code** but **accidentally correct for live runtime** — for a different reason than stated.

**Code proof**:
- `fsm_core.py:83-107` contains a full Phase 14C JSON Schema validation pass using `Draft7Validator` against `cmd_process_strategy_v1.json`
- On `ValidationError`, it raises `InvalidMessagePayloadError` — a hard fail-fast (line 105)
- The schema SSOT `cmd_process_strategy_v1.json` enforces `tf_sec` (int, 60-3600), `bar_close_ts` (int, min 1), `warmup` (required), `bar` (required), `additionalProperties: false`

**But the validation is DEAD at runtime**:
- `init_global_registry()` is imported at `main.py:88` but **never called anywhere in the entire codebase**
- `_global_registry` stays `None` (schema_registry.py:125)
- `get_global_registry()` returns `None` (schema_registry.py:138-140)
- `fsm_core.py:89`: `if registry:` evaluates to `False` → validation block is skipped entirely
- All `CMD:PROCESS_STRATEGY` emissions pass through to listeners **unvalidated against JSON schema**

**This is a NEW root cause not in the prior report**: Phase 14C infrastructure exists but is never activated. The imperative Python gates in `feature_engineering.py:1665-1724` are the only live defense, and they are not schema-driven.

### Correction 2: `map_to_flat_regime` Location

**Wrong**: I cited `decision_making/regime_mapping.py:77`
**Correct**: `apps/reference/domains/feature_engineering/regime_mapping.py:77`

The function is defined in the **feature_engineering** domain, not decision_making. It is called from `feature_engineering/mean_reversion_strategy.py:379` via a relative import (`from .regime_mapping import map_to_flat_regime`). The mean_reversion_handler in decision_making delegates to the strategy object which lives in feature_engineering.

---

## Additional Blocking Paths Missed in Prior Report

The previous report missed at least **five significant permanent-latch or permanent-block paths**:

### Missed Blocker 1: `until_refresh` Permanent Latch
- **File**: `strategy_gateway.py:791-821` (set) / `event_handlers.py:141-152,294-304` (clear)
- **Defect**: Once `defer_count >= max_defer`, `until_refresh = True` blocks ALL signals for that symbol. Cleared only by next `EVT:FEATURES_CALCULATED` or `EVT:RISK_ASSESSMENT_COMPLETED`. If the upstream feature/risk pipeline stalls (same condition that caused the skew), the latch is **permanent** with no timeout or self-recovery.
- **Severity**: HIGH

### Missed Blocker 2: `latest_portfolio = None` Total Paralysis
- **File**: `decision_making.py:67` (init), `strategy_gateway.py:634-636` (gate), `readiness_gates.py:113-117` (gate)
- **Defect**: Initialized as `None`, only set by `EVT:PORTFOLIO_STATE_UPDATED`. If the exchange position tracker fails to emit this event at startup, **ALL strategies on ALL symbols are permanently blocked** at two gate points (gateway + warmup gate). No timeout, no fallback, no stale-data policy.
- **Severity**: CRITICAL

### Missed Blocker 3: Safety Gates — Regime Confidence & Price Motion
- **File**: `safety_gates.py:454-511`
- **Defect**: Gate 1 (regime_confidence) rejects if confidence is always `None` or below `min_regime_conf`. Gate 3 (price_motion) rejects if `pm_norm_10s is None`. In markets where features never emit price_motion data or regime confidence stays low, these gates reject every signal indefinitely.
- **Severity**: HIGH (market-condition dependent)

### Missed Blocker 4: MR Liquidity Gate RuntimeError
- **File**: `mean_reversion_handler.py:1329-1356`
- **Defect**: If `liquidity_kappa` is never emitted in features for a symbol, `self._liquidity_kappa_map.get(symbol)` returns `None`, causing `raise RuntimeError(...)`. Caught by outer `except Exception` — signal silently lost. Permanent if features never emit kappa.
- **Severity**: HIGH

### Missed Blocker 5: Dead Schema Registry = Silent Contract Erosion
- **File**: `main.py:88` (import), `schema_registry.py:125` (None), `fsm_core.py:89` (skipped)
- **Defect**: `init_global_registry()` is never called. The entire Phase 14C validation infrastructure exists but is inert. Any future producer introduced without imperative gates can emit structurally invalid `CMD:PROCESS_STRATEGY` payloads (missing `tf_sec`, missing `warmup`) without any fail-fast. Current defense relies entirely on FE's 5 Python gates — no defense-in-depth.
- **Severity**: MEDIUM (latent) — not an active blocker today but eliminates the schema safety net.

---

## Revised Architectural Breakpoints Table

| # | File | Function/Line | Defect Class | Impact |
|---|---|---|---|---|
| **1** | `main.py:1277` | `finally: release_startup_warmup_gate()` | Seed gap (C) | Gate releases without verifying handler seed state |
| **2** | `startup_warmup.py:356-436` | `build_startup_warmup_report()` | Observability gap (C) | Never checks handler `_bars_seen`, only FE/regime/restore |
| **3** | `aurora_decision.py:250` | `_bars_seen < _basis_required` | Handler-exclusive gate (A) | Cold-start invisible to gateway; 301 bars × 5min = 25h natural recovery |
| **4** | `md_amr_handler.py:1106-1163` | Cold-start bars gate | Same as #3 (A) | 301 bars × 15min = 3.14 days natural recovery |
| **5** | `strategy_compatibility_matrix.py:247` | md_amr max() includes `regime_detector_required_bars` | Over-constrained (D) | md_amr only needs 64 bars but contract inflates to 301 |
| **6** | `decision_making.py:67` | `latest_portfolio: None` | Data dependency (NEW) | Total paralysis if portfolio event never fires |
| **7** | `strategy_gateway.py:791-821` | `until_refresh = True` | Permanent latch (NEW) | No timeout; permanent if upstream pipeline dead |
| **8** | `main.py:88` | `init_global_registry` imported, never called | Dead infrastructure (NEW) | Phase 14C schema validation entirely inert |
| **9** | `safety_gates.py:454-511` | Regime confidence + price motion gates | Market-condition latch (NEW) | Permanent reject in flat/illiquid markets |
| **10** | `mean_reversion_handler.py:1329-1356` | Liquidity kappa RuntimeError | Silent crash (NEW) | MR permanently dead if kappa never emitted |

---

## Revised Fix Plan Additions

### P0 (Immediate) — Add to prior Fix 1-3:

**Fix 4: Call `init_global_registry()` at startup**
- **File**: `main.py`, early in startup sequence (before first `fsm.emit()`)
- **Change**: Add `init_global_registry(project_root=str(project_root))` call
- **Impact**: Activates Phase 14C schema validation for all emitted commands/events; any structurally invalid payload will fail-fast instead of silently passing through

**Fix 5: Portfolio presence timeout / startup guarantee**
- **File**: `main.py` startup sequence + `readiness_gates.py`
- **Change**: Either (a) ensure `EVT:PORTFOLIO_STATE_UPDATED` is emitted during startup before warmup gate release, or (b) add a grace period / stale portfolio fallback with explicit blocker token in warmup report
- **Impact**: Prevents total system paralysis from missing portfolio event

### P1 (Contract Hardening) — Add to prior Fix 4-7:

**Fix 6: `until_refresh` timeout**
- **File**: `strategy_gateway.py:482-495`
- **Change**: Add max-hold duration (e.g., `5 * window_sec`). If `until_refresh` has been True longer than the timeout, auto-clear and log CRITICAL.
- **Impact**: Prevents permanent latch when upstream pipeline is dead

**Fix 7: MR liquidity kappa default / graceful degradation**
- **File**: `mean_reversion_handler.py:1329-1356`
- **Change**: Replace `raise RuntimeError` with a fail-closed return that emits a diagnostic event, not an exception
- **Impact**: MR signals blocked cleanly with visibility, not silently crashed

---

## Revised Final Classification

**Multiple architectural defects (Classification E)** — increased from "two primary + one tertiary" to **five interacting defect classes**:

| # | Defect | Code Proof | Interaction |
|---|--------|-----------|-------------|
| **1** | Startup seed propagation gap | `main.py:1277` unconditional release; `startup_warmup.py:356-436` no handler seed check | Enables #2 |
| **2** | Handler-exclusive cold-start gate | `aurora_decision.py:250`, `md_amr_handler.py:1106` | Triggered by #1; invisible to gateway |
| **3** | Dead schema registry | `main.py:88` import-only; `schema_registry.py:125` `_global_registry=None` | Latent; removes safety net for future contract drift |
| **4** | Portfolio data dependency without startup guarantee | `decision_making.py:67` init None; no startup emission guarantee | Independent total-paralysis path |
| **5** | Multiple permanent-latch gates without timeout | `strategy_gateway.py:821` `until_refresh`; `safety_gates.py:454-511` | Compound blocking when market conditions deteriorate |

The system has **no single root cause** but rather a **defense-in-depth failure** where each layer assumes another layer handles the guarantee: startup assumed to seed handlers (but doesn't verify), warmup report assumed to track handler state (but doesn't), gateway assumed to have visibility into handler readiness (but doesn't), schema validation assumed to enforce contracts (but is never activated). Each gap is individually survivable but collectively they create a state where the system can boot "successfully", report "warmed", and remain permanently non-tradable with zero operator-visible diagnostics.

Completed: *Write corrected forensic report incorporating review feedback and new findings* (1/1)
