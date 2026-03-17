

- **Phase 2** is the core fix: `build_startup_warmup_report()` gets a new `basis_seed_statuses` param (default `None` for backward compat) that feeds handler seed outcomes into the blocker system. This means `can_open_new_risk=False` when seed fails — the warmup gate still releases but *permissions* correctly block.
- **Phase 6** decouples md_amr's `basis_required_bars` from regime (drops 301 → 64), because regime is independently tracked via `needs_regime=True` in the warmup report.
- All new config fields have Pydantic defaults → no existing YAML breakage.
- New event `EVT:STARTUP_SEED_STATUS` gets full verb_registry + schema + domain_dict registration.

Вот план Claude:

# DEAD-STATE FIX PLAN: Phenix Aurora Trading System

## Context

**Problem**: The system boots "successfully", reports "WARMED", but remains permanently non-tradable. Seven interacting code defects create a defense-in-depth failure where each layer assumes another handles the guarantee.

**Root causes proven from code** (forensic audit 2026-03-16):
1. Startup seed propagation gap — warmup gate releases unconditionally; warmup report never tracks handler seed status
2. Handler-exclusive cold-start gate invisible to system — `_bars_seen < 301` checked only inside handlers
3. Dead schema registry — `init_global_registry()` imported but never called; Phase 14C inert
4. `latest_portfolio = None` total paralysis — no startup guarantee for portfolio event
5. `until_refresh` permanent latch — no timeout; permanent if upstream pipeline stalls
6. MR liquidity gate RuntimeError — `raise RuntimeError` when kappa missing; signal silently lost
7. md_amr basis over-constraint — regime's 301-bar requirement inflates md_amr from 64 to 301 bars

**Intended outcome**: All seven defects fixed with regression tests. System can recover from transient startup failures and provides operator-visible diagnostics when blocked.

---

## Phase 1: Schema Registry Activation (DEFECT 3)

**Why first**: Zero cascades, enables contract safety net for all subsequent phases.

### Step 1.1: Activate `init_global_registry()` at startup

**File**: `apps/reference/main.py`
**Change**: Add call to `init_global_registry()` early in startup (before first `fsm.emit()`), after config is loaded but before any domain `.start()`.
**Exact code**: After the `FSMCore()` instantiation and config load, before `feature_engineering.start()`:
```python
from vfoundation.core.schema_registry import init_global_registry
# ... already imported at line 88 ...
init_global_registry(project_root=str(project_root))
LOG.info("SCHEMA_REGISTRY initialized (Phase 14C active)")
```

**CASCADE**:
- `fsm_core.py:emit()` will now validate payloads against JSON schemas from `verb_registry_v1.yaml`
- If any existing emit path has an invalid payload, it will raise `InvalidMessagePayloadError`
- Risk: existing code may emit payloads that miss optional fields the schema requires → mitigated by the fact that the live producer (`feature_engineering.py:1819`) already passes 5 imperative gates that align with the schema
- `alpha_search/scenario_worker.py:150` emits on a `LocalBus` (not `FSMCore`), so no impact

**Test**: `tests/bootstrap/test_schema_registry_activation.py`
```
- test_init_global_registry_loads_validators: Verifies registry loads and has validators > 0
- test_fsm_emit_validates_cmd_process_strategy: Emit valid payload → no error; emit with tf_sec=0 → InvalidMessagePayloadError
- test_fsm_emit_graceful_without_registry: If registry not initialized, emit still works (backward compat)
```

---

## Phase 2: Startup Seed Propagation Fix (DEFECTS 1 + 2)

**Why second**: This is the primary root cause. Fixes the gap between basis hydration and warmup report.

### Step 2.1: Add `"handler_basis_seed"` as a warmup owner in `build_startup_warmup_report()`

**File**: `apps/reference/bootstrap/startup_warmup.py`
**Change**: Add new parameter `basis_seed_statuses` to `build_startup_warmup_report()`. This carries per-strategy+symbol seed outcomes from `_basis_summary.readiness`.

**Signature change**:
```python
def build_startup_warmup_report(
    *,
    config: Any,
    analytics_restore_report: StartupAnalyticsRestoreReport,
    warmup_statuses: Mapping[str, Mapping[str, StartupWarmupStatus]] | None,
    basis_seed_statuses: Mapping[str, StartupWarmupStatus] | None = None,  # NEW
    updated_at: int | None,
    source: str = "startup:warmup_report",
    gate_active: bool | None = None,
) -> StartupWarmupReport:
```

**Inside the function**, after the regime/FE blocker checks, add:
```python
# Check handler basis seed status (if strategy profile requires it)
if profile.restart_local_basis_counter:
    seed_key = f"{strategy_id}:{symbol_key}"
    seed_status = (basis_seed_statuses or {}).get(seed_key)
    if seed_status is None or seed_status.state != StartupWarmupState.WARMED:
        blockers.append(_warmup_blocker("handler_basis_seed", seed_status))
```

Also include the seed status in `owner_statuses`:
```python
if seed_status is not None:
    owner_statuses["handler_basis_seed"] = seed_status
```

**CASCADE**:
- `build_startup_warmup_report()` callers: **only** `main.py:1264` → must pass `basis_seed_statuses`
- `StrategyStartupWarmupSnapshot.warmup` dict gains new key `"handler_basis_seed"` → downstream consumers that iterate over `warmup` keys will naturally pick it up
- `effective_blockers` may now include `"handler_basis_seed_warmup_missing"` or `"handler_basis_seed_warmup_failed"` → these are string tokens, no schema change needed
- `warmup_report.to_payload()` output shape unchanged (just more entries in `warmup` and `effective_blockers` dicts)
- Default `basis_seed_statuses=None` maintains backward compat for tests that call this function without the new param

### Step 2.2: Build `basis_seed_statuses` dict from `_basis_summary` in `main.py`

**File**: `apps/reference/main.py` (between `execute_startup_basis_hydration()` call and `build_startup_warmup_report()` call)
**Change**: Convert `_basis_summary["readiness"]` list into `Mapping[str, StartupWarmupStatus]` keyed by `"{strategy_id}:{SYMBOL}"`:

```python
# Convert basis seed results to warmup status format
basis_seed_statuses: dict[str, StartupWarmupStatus] = {}
for readiness_entry in (_basis_summary or {}).get("readiness", []):
    key = f"{readiness_entry['strategy_id']}:{readiness_entry['symbol']}"
    if readiness_entry.get("ready"):
        basis_seed_statuses[key] = warmed_warmup_status(
            why=("basis_seed_complete",),
            updated_at=int(time.time() * 1000),
            source="main:basis_seed",
            details={
                "seeded_bars": readiness_entry.get("seeded_bars", 0),
                "required_bars": readiness_entry.get("required_bars", 0),
                "seed_source": readiness_entry.get("seed_source"),
            },
        )
    else:
        basis_seed_statuses[key] = failed_warmup_status(
            why=(readiness_entry.get("block_reason", "seed_failed"),),
            updated_at=int(time.time() * 1000),
            source="main:basis_seed",
            details={
                "seeded_bars": readiness_entry.get("seeded_bars", 0),
                "required_bars": readiness_entry.get("required_bars", 0),
            },
        )
```

Then pass to `build_startup_warmup_report()`:
```python
warmup_report = build_startup_warmup_report(
    config=config,
    analytics_restore_report=restore_report,
    warmup_statuses=warmup_statuses,
    basis_seed_statuses=basis_seed_statuses,  # NEW
    updated_at=int(time.time() * 1000),
    source="main:startup_warmup_report",
    gate_active=True,
)
```

**CASCADE**:
- No signature break: `basis_seed_statuses` has a default of `None`
- `warmup_report.to_payload()` will now show seed failures as blockers → operator sees "handler_basis_seed_warmup_failed" instead of green status
- `can_open_new_risk` will be `False` for strategies whose seed failed → **this is the core fix** — prevents the system from reporting WARMED when handlers are cold
- The warmup gate itself still releases in `finally:`, but the *permissions* now correctly block new risk → strategies cannot open new positions until seed is verified
- `apply_startup_warmup_permission_overlay()` already handles `can_open_new_risk=False` correctly

### Step 2.3: Emit `EVT:STARTUP_SEED_STATUS` structured event

**File**: `apps/reference/main.py` (after basis_seed_statuses is built)
**Change**: Emit a structured event for each seed status so operators can monitor:
```python
for key, status in basis_seed_statuses.items():
    strategy_id, symbol = key.split(":", 1)
    fsm.emit("EVT:STARTUP_SEED_STATUS", payload={
        "strategy_id": strategy_id,
        "symbol": symbol,
        "state": status.state.value,
        "why": list(status.why),
        "details": dict(status.details),
    }, why="startup_basis_seed_status")
```

**CASCADE**: New event → needs verb_registry + schema + domain_dict entries.

### Step 2.4: Register `EVT:STARTUP_SEED_STATUS` in verb_registry and domain_dict

**File**: `apps/reference/dictionaries/verb_registry_v1.yaml`
**Change**: Add entry:
```yaml
- op: EVT
  verb: STARTUP_SEED_STATUS
  owner: bootstrap
  status: active
  schema: apps/reference/bootstrap/schemas/startup_seed_status_v1.json
  since: '2026-03-16'
```

**File**: `apps/reference/domains/decision_making/domain_dict.json`
**Change**: Add to `imports`:
```json
{"event_name": "EVT:STARTUP_SEED_STATUS", "source_domain": "bootstrap"}
```

**File**: `apps/reference/bootstrap/schemas/startup_seed_status_v1.json` (NEW)
**Change**: Create JSON schema:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EVT:STARTUP_SEED_STATUS",
  "type": "object",
  "required": ["strategy_id", "symbol", "state"],
  "properties": {
    "strategy_id": {"type": "string"},
    "symbol": {"type": "string"},
    "state": {"type": "string", "enum": ["WARMED", "PARTIAL", "SKIPPED", "FAILED"]},
    "why": {"type": "array", "items": {"type": "string"}},
    "details": {"type": "object"}
  },
  "additionalProperties": false
}
```

**Test**: `tests/bootstrap/test_warmup_seed_propagation.py`
```
- test_warmup_report_includes_seed_status_warmed: Seed success → no blocker, can_open_new_risk=True
- test_warmup_report_includes_seed_status_failed: Seed failure → blocker "handler_basis_seed_warmup_failed", can_open_new_risk=False
- test_warmup_report_backward_compat_no_seed: basis_seed_statuses=None → existing behavior preserved
- test_warmup_report_skip_seed_for_non_restart_strategy: MR (restart_local_basis_counter=False) → no seed check
- test_basis_summary_to_seed_statuses_conversion: Verify main.py conversion logic
```

---

## Phase 3: `until_refresh` Latch Timeout (DEFECT 5)

### Step 3.1: Add `until_refresh_max_hold_sec` to `RiskSkewConfig`

**File**: `apps/reference/config_models.py`
**Change**: Add field to `RiskSkewConfig`:
```python
until_refresh_max_hold_sec: int = Field(
    default=300, ge=30, le=3600,
    description='Max seconds until_refresh latch can be held. After this, auto-clear and log CRITICAL.'
)
```

**File**: `config/aurora/decision_making.yaml` (or wherever RiskSkewConfig is sourced)
**Change**: Add `until_refresh_max_hold_sec: 300` to the `risk_skew` section.

**CASCADE**:
- Pydantic `extra='forbid'` on `RiskSkewConfig` → YAML must include the field OR the default must be used
- Default `300` means backward compat: if YAML doesn't have it, Pydantic fills default → no existing test breakage
- All consumers of `RiskSkewConfig` get the new field automatically via `self._rscfg()`

### Step 3.2: Add `until_refresh_latched_at_ms` to the risk_skew_guard state and implement auto-clear

**File**: `apps/reference/domains/decision_making/strategy_gateway.py`

**Change 1**: When setting the latch (in `_handle_risk_skew`, ~line 808), record timestamp:
```python
if dc >= max_defer:
    state["until_refresh"] = True
    state["until_refresh_latched_at_ms"] = now_ms  # NEW: record latch time
```

**Change 2**: In the `until_refresh` check (~line 483), add timeout auto-clear:
```python
guard = dm.symbol_states[symbol].get("risk_skew_guard") or {}
if guard.get("until_refresh"):
    latched_at = guard.get("until_refresh_latched_at_ms", 0)
    max_hold_ms = int(self._rscfg("until_refresh_max_hold_sec") * 1000)
    if now_ms - latched_at > max_hold_ms:
        # Auto-clear stale latch
        dm.symbol_states[symbol]["risk_skew_guard"] = {
            "defer_count": 0,
            "window_start_ms": now_ms,
            "until_refresh": False,
        }
        self.logger.critical(
            "[%s] RISK_SKEW_GUARD: until_refresh AUTO-CLEARED after %dms (max_hold=%dms)",
            symbol, now_ms - latched_at, max_hold_ms,
        )
    else:
        # Existing defer logic
        ...
        return
```

**CASCADE**:
- `event_handlers.py` clear paths (lines 141-152, 294-306) remain unchanged — they still clear on fresh data
- The new timeout is a **fallback** — if fresh data arrives first, it clears normally
- `symbol_states[symbol]["risk_skew_guard"]` dict gains new key `until_refresh_latched_at_ms` → serialization-safe (int), no consumers read this dict besides the gateway and event_handlers clear paths
- `_rscfg("until_refresh_max_hold_sec")` reads from `RiskSkewConfig` via the existing resolver pattern

**Test**: `tests/domains/decision_making/test_until_refresh_timeout.py`
```
- test_until_refresh_latch_sets_timestamp: Verify latched_at_ms recorded
- test_until_refresh_auto_clears_after_max_hold: Advance clock past max_hold → guard cleared, signal passes
- test_until_refresh_not_cleared_before_max_hold: Clock within max_hold → signal still deferred
- test_until_refresh_cleared_by_features_before_timeout: Fresh features → cleared even before timeout
- test_until_refresh_cleared_by_risk_before_timeout: Fresh risk → cleared even before timeout
```

---

## Phase 4: Portfolio Startup Guarantee (DEFECT 4)

### Step 4.1: Add `portfolio_warmup_timeout_sec` to config and emit initial portfolio at startup

**File**: `apps/reference/config_models.py`
**Change**: Add to `DecisionMakingDomainConfig`:
```python
portfolio_warmup_timeout_sec: int = Field(
    default=30, ge=5, le=120,
    description='Max seconds to wait for initial EVT:PORTFOLIO_STATE_UPDATED at startup before emitting empty fallback.'
)
```

**File**: `apps/reference/main.py` (in startup, after `position_tracking.start()` but before warmup gate release)
**Change**: Wait for portfolio event with bounded timeout. If none arrives, emit a synthetic portfolio event with zero positions (fail-safe):

```python
# Ensure portfolio state is populated before warmup completes
_portfolio_timeout = config.domains.decision_making.portfolio_warmup_timeout_sec
_portfolio_received = _wait_for_portfolio_event(
    decision_making=decision_making,
    timeout_sec=_portfolio_timeout,
)
if not _portfolio_received:
    LOG.critical(
        "STARTUP_PORTFOLIO_TIMEOUT: No EVT:PORTFOLIO_STATE_UPDATED received within %ds. "
        "Emitting empty fallback to prevent total paralysis.",
        _portfolio_timeout,
    )
    fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload={
        "positions": {},
        "balances": {},
        "updated_at": int(time.time() * 1000),
        "source": "startup:portfolio_fallback",
    }, why="startup_portfolio_timeout_fallback")
```

**Helper function** `_wait_for_portfolio_event()`:
```python
def _wait_for_portfolio_event(*, decision_making, timeout_sec: int) -> bool:
    """Poll decision_making.latest_portfolio with 1s interval."""
    import time
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if decision_making.latest_portfolio is not None:
            return True
        time.sleep(1.0)
    return False
```

**CASCADE**:
- If position_tracking starts successfully, portfolio event fires within seconds → no change to behavior
- Fallback only triggers on timeout → empty portfolio means gateway won't block on `LATEST_PORTFOLIO_MISSING`
- Empty portfolio means sizing will compute `qty=0` for most instruments → signals rejected at `SIZING_QTY_NONE`, which is correct (no phantom trades)
- Readiness gate `portfolio_missing` cleared → warmup gate no longer permanently blocks
- Pydantic default `30` → backward compat

**Test**: `tests/bootstrap/test_portfolio_startup_guarantee.py`
```
- test_portfolio_received_before_timeout: Portfolio arrives in 2s → no fallback emitted
- test_portfolio_fallback_on_timeout: No portfolio → fallback emitted after timeout
- test_portfolio_fallback_unblocks_gateway: After fallback, gateway does not reject with LATEST_PORTFOLIO_MISSING
```

---

## Phase 5: MR Liquidity Gate Fix (DEFECT 6)

### Step 5.1: Replace RuntimeError with fail-closed return + diagnostic event

**File**: `apps/reference/domains/decision_making/mean_reversion_handler.py`
**Change** at line 1345-1350:

**Before**:
```python
kappa = self._liquidity_kappa_map.get(symbol)
if kappa is None:
    raise RuntimeError(
        f"[{symbol}] Liquidity gate enabled but liquidity_kappa not found in cache. ..."
    )
```

**After**:
```python
kappa = self._liquidity_kappa_map.get(symbol)
if kappa is None:
    self.logger.warning(
        "[%s] LIQUIDITY_GATE_FAIL_CLOSED: kappa not in cache. "
        "FE must emit liquidity_kappa before MR decision. gate_cfg: enabled=%s, kappa_min=%s",
        symbol, gate_cfg.enabled, gate_cfg.kappa_min,
    )
    return False  # Fail-closed: block signal, don't crash
```

**CASCADE**:
- Outer `try/except Exception` in `_on_process_strategy` no longer catches this path → signal is explicitly blocked rather than silently lost
- Existing signal emission logic handles `_check_liquidity_gate() == False` correctly (skips with log)
- No signature change, no config change, no event contract change

**Test**: `tests/domains/decision_making/test_mr_liquidity_gate_failclosed.py`
```
- test_kappa_none_returns_false_not_raises: Missing kappa → returns False, no exception
- test_kappa_below_min_returns_false: kappa < kappa_min → returns False normally
- test_kappa_above_min_returns_true: kappa >= kappa_min → returns True
- test_gate_disabled_always_passes: gate_cfg.enabled=False → returns True regardless of kappa
```

---

## Phase 6: md_amr Basis Decoupling (DEFECT 7)

### Step 6.1: Separate md_amr data basis from regime basis requirement

**File**: `apps/reference/contracts/strategy_compatibility_matrix.py`
**Change**: In the md_amr profile (line 244-249), remove `_structural_regime_basis_required_bars(config)` from the `max()` call:

**Before**:
```python
basis_required_bars=max(
    int(getattr(md_cfg, "channel_window_bars", 12) or 12),
    int(getattr(md_cfg, "atr_window", 14) or 14),
    int(getattr(md_cfg, "atr_stats_window", 64) or 64),
    _structural_regime_basis_required_bars(config)
),
```

**After**:
```python
basis_required_bars=max(
    int(getattr(md_cfg, "channel_window_bars", 12) or 12),
    int(getattr(md_cfg, "atr_window", 14) or 14),
    int(getattr(md_cfg, "atr_stats_window", 64) or 64),
),
```

**Result**: md_amr `basis_required_bars` drops from `301` to `64`. The regime warmup requirement is already tracked separately via `needs_regime=True` + `warmup_statuses["regime_detector"]` in the warmup report.

**CASCADE**:
- `execute_startup_basis_hydration()` plans seed requirements from `basis_required_bars` → md_amr now needs only 64 bars seeded instead of 301
- `hydrate_basis_bars()` requests from Binance: `n_bars` drops to 64 for md_amr → faster backfill, less data
- Handler cold-start gate: `_bars_seen < 64` instead of `_bars_seen < 301` → passes after 64*15min = 16h live instead of 3.14 days
- Warmup report still blocks on `regime_detector` separately (`needs_regime=True` check at line 408-413) → regime gate unaffected
- Aurora profile **unchanged** (it uses `regime_detector_required_bars` independently)
- MR profile **unchanged** (`restart_local_basis_counter=False`, no seed)
- **Warning**: Verify `md_amr_handler.py` uses the profile's `basis_required_bars` (via `get_active_strategy_profile()`) for its cold-start gate, not a separate hardcoded value. If it does, the fix propagates automatically.

**Test**: `tests/contracts/test_md_amr_basis_decoupled.py`
```
- test_md_amr_basis_equals_own_data_needs: basis_required_bars == max(12, 14, 64) == 64
- test_md_amr_regime_tracked_separately: needs_regime == True; regime is tracked via warmup_statuses, not basis_required_bars
- test_aurora_basis_unchanged: aurora still uses regime_detector_required_bars (301)
- test_mr_basis_unchanged: MR restart_local_basis_counter still False
```

---

## Phase 7: Handler Cold-Start Visibility (DEFECT 2 complement)

### Step 7.1: Surface `_bars_seen` / `_basis_required` in diagnostics event

**File**: `apps/reference/domains/decision_making/aurora_handler.py`
**Change**: In `get_readiness_diagnostics()`, ensure `bars_seen` and `basis_required` are included (verify already present; if not, add them).

**File**: `apps/reference/domains/decision_making/md_amr_handler.py`
**Change**: Same as aurora — verify `get_readiness_diagnostics()` includes `bars_seen` and `basis_required`.

### Step 7.2: Register `EVT:HANDLER_READINESS_DIAGNOSTICS` for periodic emission

**File**: `apps/reference/dictionaries/verb_registry_v1.yaml`
**Change**: Add, if not already present:
```yaml
- op: EVT
  verb: HANDLER_READINESS_DIAGNOSTICS
  owner: decision_making
  status: active
  schema: null
  since: '2026-03-16'
```

**File**: `apps/reference/domains/decision_making/domain_dict.json`
**Change**: Add to exports:
```json
{"event_name": "EVT:HANDLER_READINESS_DIAGNOSTICS", "target_domains": ["monitoring"]}
```

**Note**: Wiring the periodic 60s emitter that calls `get_readiness_diagnostics()` is P2 (not in scope of immediate unblock). The infrastructure is prepared here so it can be wired later.

**Test**: `tests/domains/decision_making/test_handler_readiness_diagnostics.py`
```
- test_aurora_diagnostics_includes_bars_seen: Verify bars_seen and basis_required in diagnostics
- test_md_amr_diagnostics_includes_bars_seen: Same for md_amr
- test_diagnostics_after_seed: After seed_startup_bars(301), bars_seen >= 301 in diagnostics
```

---

## Execution Order Summary

```
Phase 1: Schema Registry Activation      [0 cascades, standalone]
  └─ Step 1.1: Call init_global_registry() in main.py

Phase 2: Seed Propagation Fix             [core fix, touches warmup.py + main.py]
  ├─ Step 2.1: Add basis_seed_statuses to build_startup_warmup_report()
  ├─ Step 2.2: Build basis_seed_statuses from _basis_summary in main.py
  ├─ Step 2.3: Emit EVT:STARTUP_SEED_STATUS
  └─ Step 2.4: verb_registry + domain_dict + JSON schema for new event

Phase 3: until_refresh Timeout            [config + gateway change]
  ├─ Step 3.1: Add until_refresh_max_hold_sec to RiskSkewConfig
  └─ Step 3.2: Implement timeout auto-clear in strategy_gateway.py

Phase 4: Portfolio Startup Guarantee      [config + main.py]
  └─ Step 4.1: Bounded wait + fallback emit for initial portfolio

Phase 5: MR Liquidity Gate Fix            [single file, no cascades]
  └─ Step 5.1: Replace RuntimeError with fail-closed return

Phase 6: md_amr Basis Decoupling          [compatibility matrix]
  └─ Step 6.1: Remove regime requirement from md_amr max()

Phase 7: Handler Diagnostics Visibility   [verb_registry + handlers]
  ├─ Step 7.1: Verify/add bars_seen to get_readiness_diagnostics()
  └─ Step 7.2: Register EVT:HANDLER_READINESS_DIAGNOSTICS
```

---

## Files Modified (Complete List)

| File | Phase | Change Type |
|------|-------|-------------|
| `apps/reference/main.py` | 1,2,4 | Add registry init, seed status conversion, portfolio wait |
| `apps/reference/bootstrap/startup_warmup.py` | 2 | Add `basis_seed_statuses` param + handler seed blocker logic |
| `apps/reference/config_models.py` | 3,4 | Add fields to RiskSkewConfig, DecisionMakingDomainConfig |
| `apps/reference/domains/decision_making/strategy_gateway.py` | 3 | Add timeout auto-clear for until_refresh latch |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | 5 | Replace RuntimeError with fail-closed return |
| `apps/reference/contracts/strategy_compatibility_matrix.py` | 6 | Remove regime from md_amr basis_required_bars max() |
| `apps/reference/domains/decision_making/aurora_handler.py` | 7 | Verify diagnostics completeness |
| `apps/reference/domains/decision_making/md_amr_handler.py` | 7 | Verify diagnostics completeness |
| `apps/reference/dictionaries/verb_registry_v1.yaml` | 2,7 | Register new events |
| `apps/reference/domains/decision_making/domain_dict.json` | 2,7 | Add imports/exports |
| `config/aurora/decision_making.yaml` | 3,4 | Add new config values |

## New Files

| File | Phase | Type |
|------|-------|------|
| `apps/reference/bootstrap/schemas/startup_seed_status_v1.json` | 2 | JSON schema |
| `tests/bootstrap/test_schema_registry_activation.py` | 1 | Test |
| `tests/bootstrap/test_warmup_seed_propagation.py` | 2 | Test |
| `tests/domains/decision_making/test_until_refresh_timeout.py` | 3 | Test |
| `tests/bootstrap/test_portfolio_startup_guarantee.py` | 4 | Test |
| `tests/domains/decision_making/test_mr_liquidity_gate_failclosed.py` | 5 | Test |
| `tests/contracts/test_md_amr_basis_decoupled.py` | 6 | Test |
| `tests/domains/decision_making/test_handler_readiness_diagnostics.py` | 7 | Test |

---

## Verification Plan

After all phases:
1. Run full domain test suite: `python -m pytest tests/ -x -q`
2. Verify existing 1511 tests still pass (no regression)
3. Verify all new tests pass (~25 new tests across 7 files)
4. Verify `test_warmup_ssot_alignment.py` still passes (Phase 2 touches warmup)
5. Verify `test_handler_fail_closed.py` still passes (Phase 2 changes warmup logic)
6. Verify `test_safety_gates_config_v1.py` still passes (Phase 5 changes MR handler)
7. Grep for any hardcoded `301` in md_amr paths to ensure Phase 6 didn't miss a reference



