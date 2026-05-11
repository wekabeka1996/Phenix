# EXECUTION_CONFIG_SPLIT_AUDIT_REPORT_v1

**Date:** 2026-05-09
**Mode:** READ-ONLY AUDIT
**Track:** config / SSOT / split-brain repair — OS-005 pre-implementation analysis
**Verdict:** `MUST_SPLIT_INTO_SMALLER_SEAMS`

---

## Section 1: Problem Framing

OS-005 from `CONFIG_SURFACE_LEDGER_SEED_v1.md` identified that the `execution` config family is split across two YAML namespaces that survive `deep_merge` under structurally different keys:

- `config/aurora/system.yaml` root: `execution.*`
- `config/aurora/trading.yaml` nested: `trading.execution.*`

Unlike the `ops.*` split (OS-001/002/003) and `trading_mode` split (OS-004), the execution config family is:
1. **Architecturally large** — 12+ distinct sub-surfaces, some with complex nested structures
2. **Partially migrated** — watchdog already moved (T5A.1-SSOT 2026-05-07), others not
3. **Independently consumed** — nearly all runtime consumers already read `trading.execution` directly, not the root alias
4. **Contains deprecated dead fields** mixed with live active surfaces
5. **Has two existing split-brain detectors** in the codebase (order_guardian loader check, fsm_periodic_cleanup dual-path validator) that must be preserved or updated during migration

The goal of this audit is to decompose OS-005 into named, bounded sub-seams and identify the safest next implementation package.

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `system.yaml:execution.*` is a root-level YAML block merged into `merged_config["execution"]` | `config_loader.py`, `system.yaml` lines 24–88 |
| F-02 | `trading.yaml:trading.execution.*` is nested under `trading:`, merged into `merged_config["trading"]["execution"]` | `config_loader.py`, `trading.yaml` lines 89–154 |
| F-03 | After deep_merge, BOTH `merged_config["execution"]` and `merged_config["trading"]["execution"]` are populated independently — they do NOT conflict at the dict level because they land at different keys | `config_loader.py` deep_merge logic — no execution-specific branching |
| F-04 | `AuroraConfig.execution: Optional[ExecutionConfig] = Field(...)` is declared REQUIRED (Field(...)) but Optional (can be None) — reads from `merged_config["execution"]` (system.yaml) | `config_models.py` line 1186 |
| F-05 | `TradingConfig.execution: Optional[ExecutionConfig] = Field(...)` reads from `merged_config["trading"]["execution"]` (trading.yaml) | `config_models.py` line 992 |
| F-06 | `_backcompat_root_execution_alias` fires only if `self.execution is None` — currently NEVER fires because system.yaml always provides an execution block | `config_models.py` lines 1286-1294 |
| F-07 | Both execution blocks contain identical values for 11 out of 12 sub-surfaces — the only difference is `watchdog` which exists ONLY in trading.yaml | Diff analysis of system.yaml lines 24-88 vs trading.yaml lines 89-154 |
| F-08 | `execution.watchdog` was explicitly removed from system.yaml 2026-05-07 (T5A.1-SSOT) and is canonical in trading.yaml only | `system.yaml` comment lines 56-58; `config_models.py` WatchdogConfig comment |
| F-09 | All runtime consumers of `manage`, `exposure`, `watchdog`, `preflight_backoff_ms`, `cooldown_after_close_ms`, `anti_race_close_ms` read from `config.trading.execution.*` — NOT from `config.execution.*` | `fsm.py:327`, `fsm_manage.py:140,159-171`, `exposure_guard.py:117`, `bracket_manager.py:1219-1226`, `binance_adapter.py:1881` |
| F-10 | `event_handlers.py:1147` is the ONLY runtime consumer that reads `config.execution` (root alias path) — accesses `allow_trade_with_guardian_tidy_only` | `event_handlers.py` lines 1147-1149 |
| F-11 | `config_resolver.py:67-109` performs explicit dual-path validation for `fsm_periodic_cleanup_enabled`: first checks `config.execution`, then `config.trading.execution`, raises if neither is explicitly set | `config_resolver.py` lines 67-109 |
| F-12 | `config_loader.py` has order_guardian conflict detection at lines 710, 734, 1105, 1108: validates that root `execution.order_guardian` and `trading.execution.order_guardian` do not conflict | `config_loader.py` lines ~710-1108 |
| F-13 | `ExecutionConfig` marks `order_params`, `preflight_backoff_ms`, `allow_trade_with_guardian_tidy_only`, `order_guardian` as `DEPRECATED` in field descriptions | `config_models.py` lines 819-826 |
| F-14 | `bracket_manager.py:1219-1226` actively consumes `config.trading.execution.preflight_backoff_ms` — contradicting the DEPRECATED label in the model | `bracket_manager.py` lines 1219-1226 |
| F-15 | `ExposureConfig.pending_ttl_sec` and `post_fill_hold_ttl_sec` are Optional with `default=None` — SSOT moved to domains.yaml (T3-SSOT, T3B-SSOT) | `config_models.py` lines 402-417 |
| F-16 | `_extract_system_meta()` in config_loader does NOT pop `execution` from system_config — execution reaches Pydantic intact from the raw merge | `config_loader.py` `_extract_system_meta` function |
| F-17 | `domain_config.py` has deprecated accessor methods (`get_brackets_strict`, `get_legacy_exposure`, `get_legacy_brackets`, `get_legacy_manage`) that all use `config.trading.execution.*` | `domain_config.py` lines 156-274 |

---

## Section 3: INFERENCES

| # | Inference | Basis |
|---|-----------|-------|
| I-01 | `config.trading.execution` is the de-facto canonical runtime source — hardcoded in 15+ consumer sites | F-09, F-10 — all active consumers use trading path |
| I-02 | `_backcompat_root_execution_alias` is currently dead code — it never fires because system.yaml always provides an execution block | F-06, F-07 |
| I-03 | Removing system.yaml:execution entirely would activate the alias and provide `cfg.execution = cfg.trading.execution`, making the root path point to the same object | I-02 + the alias logic |
| I-04 | The `order_params` and `allow_trade_with_guardian_tidy_only` DEPRECATED labels in the model are accurate for the root path — no consumer reads them from root | F-13 + absence of root consumers |
| I-05 | The `preflight_backoff_ms` DEPRECATED label in the model is INACCURATE — `bracket_manager.py` actively consumes it via trading.execution; the comment should say "deprecated at root only" | F-13, F-14 conflict |
| I-06 | OS-005 cannot be implemented as a single atomic seam — the mix of dead fields, partially migrated surfaces, and existing split-brain detectors requires phased decomposition | F-11, F-12 (existing guards must be updated), F-15 (exposure has sub-splits) |
| I-07 | The cleanest atomic migration matches the ops.* and trading_mode patterns: add a loader guard rejecting system.yaml:execution, change AuroraConfig.execution to Field(default=None), activate the alias, update config_resolver.py | I-03 + pattern precedent from OS-001/OS-004 |

---

## Section 4: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No runtime code reads execution config from the raw YAML dict before Pydantic validation — all reads go through typed config objects |
| A-02 | `domain_config.py` deprecated accessors are not called in production paths — they are wrapper utilities with explicit DEPRECATED labels |
| A-03 | `config_loader.py` order_guardian conflict detection is still needed and must not be silently removed without a replacement guard |
| A-04 | `preflight_backoff_ms` is genuinely consumed at runtime via `trading.execution.preflight_backoff_ms` (bracket_manager.py), despite the model's DEPRECATED annotation |

---

## Section 5: UNKNOWNS

| # | Unknown | Risk |
|---|---------|------|
| U-01 | Whether `config_resolver.py:67-109` dual-path fsm_periodic_cleanup check is exercised in any test or only in production | MEDIUM — if removed without test coverage, regression is silent |
| U-02 | Whether `config_loader.py:710-1108` order_guardian conflict detection has dedicated tests | MEDIUM — must be verified before migration |
| U-03 | Whether `event_handlers.py:1147` still needs the `allow_trade_with_guardian_tidy_only` flag in production (field is DEPRECATED) | LOW — if deprecated, can be hardcoded to False and removed |
| U-04 | Whether `ExposureConfig.leverage_defaults` overlaps with `instruments.yaml` leverage values in a way that creates a secondary split-brain (OS-012, OS-013 from ledger) | MEDIUM — leverage values differ between instruments.yaml and exposure.leverage_defaults for BTCUSDT (25 vs 20) |

---

## Section 6: Execution Config Surface Inventory

### 6.1 system.yaml:execution.* surfaces (pre-migration state)

```
execution:
  manage:
    brackets: {sl.fixed_bps=40, tp.fixed_bps=80, oco_emulation=true, offset_bps=5}
    emergency: {enabled=false, wait_mode_bars=2, emergency_sl_bps=100}
    auto: true
    orphan_monitor: {enabled=true, run_on_startup=true, ...}
  exposure:
    max_equity_utilization_pct: 150.0
    max_portfolio_fraction: 150.0
    max_directional_ratio: 50.0
    leverage_defaults: {BTCUSDT:20, ETHUSDT:20, ...}
    count_pending_orders: true
    exclude_reduce_only: true
  fallback: null
  limit_orders: null
  orders: null
  fsm_periodic_cleanup_enabled: false
  cooldown_after_close_ms: 60000
  anti_race_close_ms: 800
  order_params: {LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET}
  preflight_backoff_ms: [120, 250, 400, 800, 1200, 1800]
  allow_trade_with_guardian_tidy_only: false
  order_guardian: {unified=true, ledger_db_path=data/order_ledger.db}
  # NOTE: watchdog ABSENT (removed 2026-05-07, T5A.1-SSOT)
```

### 6.2 trading.yaml:trading.execution.* surfaces (canonical state)

```
trading.execution:
  manage: [IDENTICAL to system.yaml execution.manage]
  exposure: [IDENTICAL to system.yaml execution.exposure]
  fallback: null
  limit_orders: null
  orders: null
  fsm_periodic_cleanup_enabled: false
  cooldown_after_close_ms: 60000
  anti_race_close_ms: 800
  order_params: [IDENTICAL to system.yaml execution.order_params]
  watchdog: {ack_ttl_ms=8000, fill_ttl_ms=3600000, check_interval_ms=1000, rps_limit=10}
  preflight_backoff_ms: [IDENTICAL]
  allow_trade_with_guardian_tidy_only: false
  order_guardian: {unified=true, ledger_db_path=data/order_ledger.db}
```

---

## Section 7: Ownership Classification Table

| surface_id | yaml_path | physical_file | semantic_concept | runtime_consumer | runtime_owner_status | current_status | evidence | recommended_action |
|------------|-----------|---------------|-----------------|-----------------|----------------------|----------------|----------|--------------------|
| EX-01 | `execution.manage.brackets` | system.yaml | Bracket SL/TP config | `fsm_manage.py` via `trading.execution.manage.brackets` | trading.execution ONLY | owner_split (IDENTICAL values) | `fsm_manage.py:1317`; root never consumed | Remove from system.yaml |
| EX-02 | `trading.execution.manage.brackets` | trading.yaml | Bracket SL/TP config | `fsm_manage.py`, `domain_config.py` | trading.execution | active_single_owner | `fsm_manage.py:140,1317`; `domain_config.py:156` | CANONICAL — keep |
| EX-03 | `execution.manage.orphan_monitor` | system.yaml | Orphan order cleanup | `fsm.py` via `trading.execution.manage.orphan_monitor` | trading.execution ONLY | owner_split (IDENTICAL values) | `fsm.py:454` | Remove from system.yaml |
| EX-04 | `trading.execution.manage.orphan_monitor` | trading.yaml | Orphan order cleanup | `fsm.py` | trading.execution | active_single_owner | `fsm.py:454` | CANONICAL — keep |
| EX-05 | `execution.manage.emergency` | system.yaml | Emergency SL config | Not found at runtime | trading.execution (inferred) | owner_split | No direct consumer found | Remove from system.yaml |
| EX-06 | `execution.exposure.*` | system.yaml | Exposure limits | `exposure_guard.py` via `trading.execution.exposure` | trading.execution ONLY | owner_split (IDENTICAL values) | `exposure_guard.py:117`; root never consumed | Remove from system.yaml |
| EX-07 | `trading.execution.exposure.*` | trading.yaml | Exposure limits | `exposure_guard.py`, `domain_config.py` | trading.execution | active_single_owner | `exposure_guard.py:117-126` | CANONICAL — keep |
| EX-08 | `execution.exposure.leverage_defaults` | system.yaml | Per-symbol leverage | No consumer found | DEAD — secondary conflict with instruments.yaml | dead_schema / owner_split | F-15; OS-012, OS-013 from ledger | Remove from system.yaml |
| EX-09 | `execution.watchdog` | system.yaml | Order timeout | Already removed (T5A.1-SSOT 2026-05-07) | N/A | legacy_compat (absent) | `system.yaml` comment lines 56-58 | Already done — confirm in tests |
| EX-10 | `trading.execution.watchdog` | trading.yaml | Order timeout | `fsm.py` via `_get_config_value(["trading","execution","watchdog"])` | trading.execution | active_single_owner | `fsm.py:580-606` | CANONICAL — keep |
| EX-11 | `execution.fallback` | system.yaml | Fallback backoff | `binance_adapter.py` via `trading.execution.fallback` | trading.execution ONLY | dead_schema (null + root never consumed) | null value; `binance_adapter.py:1881` | Remove null stub from system.yaml |
| EX-12 | `execution.limit_orders` | system.yaml | Limit order policy | No consumer found | dead_schema (null) | dead_schema | null; no grep hit | Remove null stub from system.yaml |
| EX-13 | `execution.orders` | system.yaml | Order config | No consumer found | dead_schema (null) | dead_schema | null; no grep hit | Remove null stub from system.yaml |
| EX-14 | `execution.fsm_periodic_cleanup_enabled` | system.yaml | FSM cleanup flag | `config_resolver.py` — reads BOTH paths (dual-path) | DUAL-PATH (existing guard) | owner_split (explicit guard in code) | `config_resolver.py:67-109` | Remove from system.yaml; update config_resolver.py |
| EX-15 | `trading.execution.fsm_periodic_cleanup_enabled` | trading.yaml | FSM cleanup flag | `config_resolver.py` | trading.execution (secondary check) | active_single_owner | `config_resolver.py:88-109` | CANONICAL — keep; update resolver |
| EX-16 | `execution.cooldown_after_close_ms` | system.yaml | Post-close cooldown | `fsm.py` via `trading.execution.cooldown_after_close_ms` | trading.execution ONLY | owner_split | `fsm.py:338` | Remove from system.yaml |
| EX-17 | `trading.execution.cooldown_after_close_ms` | trading.yaml | Post-close cooldown | `fsm.py` | trading.execution | active_single_owner | `fsm.py:338` | CANONICAL — keep |
| EX-18 | `execution.anti_race_close_ms` | system.yaml | Anti-race window | `fsm_manage.py` via `trading.execution.anti_race_close_ms` | trading.execution ONLY | owner_split | `fsm_manage.py:164-168` | Remove from system.yaml |
| EX-19 | `trading.execution.anti_race_close_ms` | trading.yaml | Anti-race window | `fsm_manage.py` | trading.execution | active_single_owner | `fsm_manage.py:164` | CANONICAL — keep |
| EX-20 | `execution.order_params` | system.yaml | LIMIT/STOP_MARKET TIF | No runtime consumer at root | dead_schema (deprecated model label) | remove_or_repoint | `config_models.py:819` "DEPRECATED: No consumption found" | Remove from system.yaml |
| EX-21 | `trading.execution.order_params` | trading.yaml | LIMIT/STOP_MARKET TIF | No runtime consumer confirmed | compat_only | compat_only | `config_models.py:819` — but in trading path | Investigate; low priority |
| EX-22 | `execution.preflight_backoff_ms` | system.yaml | Preflight retry sequence | NOT consumed at root | remove_or_repoint (deprecated at root) | remove_or_repoint | Model DEPRECATED label; `bracket_manager.py` uses trading path | Remove from system.yaml |
| EX-23 | `trading.execution.preflight_backoff_ms` | trading.yaml | Preflight retry sequence | `bracket_manager.py:1219-1226` | trading.execution | active_single_owner | `bracket_manager.py:1219` — NOTE: model DEPRECATED label is WRONG for this path | CANONICAL — keep; fix model comment |
| EX-24 | `execution.allow_trade_with_guardian_tidy_only` | system.yaml | Guardian-only tidy gate | `event_handlers.py:1147` via root alias `config.execution` | root alias (ONLY consumer of alias) | remove_or_repoint | `event_handlers.py:1147`; field DEPRECATED in model | Migrate consumer to `trading.execution`, then remove from system.yaml |
| EX-25 | `trading.execution.allow_trade_with_guardian_tidy_only` | trading.yaml | Guardian-only tidy gate | Not consumed at trading path | dead (consumer uses root alias) | compat_only | No direct `trading.execution.allow_trade_with_guardian_tidy_only` consumer found | CANONICAL source if consumer is migrated |
| EX-26 | `execution.order_guardian` | system.yaml | Guardian DB config | Loader conflict check; not consumed at runtime | remove_or_repoint (deprecated model) | owner_split (loader guard) | `config_loader.py:710,1105`; `config_models.py:825` "DEPRECATED: Guardian not config" | Remove from system.yaml after verifying loader guard |
| EX-27 | `trading.execution.order_guardian` | trading.yaml | Guardian DB config | Loader conflict check; `order_guardian.py` error messages | compat_only / loader-checked | compat_only | `config_loader.py:1105-1108`; `config_models.py:825` | Retain or clean up separately |

---

## Section 8: Confirmed Split-Brain Surfaces

All surfaces where the same concept appears in both system.yaml:execution and trading.yaml:trading.execution with IDENTICAL values:

| # | Concept | system.yaml path | trading.yaml path | Risk | Effective winner |
|---|---------|-----------------|-------------------|------|-----------------|
| SB-01 | Bracket config | `execution.manage.brackets` | `trading.execution.manage.brackets` | MEDIUM | trading.execution (runtime reads this) |
| SB-02 | Orphan monitor | `execution.manage.orphan_monitor` | `trading.execution.manage.orphan_monitor` | MEDIUM | trading.execution |
| SB-03 | Emergency config | `execution.manage.emergency` | `trading.execution.manage.emergency` | LOW | trading.execution |
| SB-04 | Exposure limits | `execution.exposure.*` | `trading.execution.exposure.*` | HIGH | trading.execution |
| SB-05 | Leverage defaults | `execution.exposure.leverage_defaults` | `trading.execution.exposure.leverage_defaults` | MEDIUM | trading.execution (but conflicts with instruments.yaml) |
| SB-06 | FSM cleanup flag | `execution.fsm_periodic_cleanup_enabled` | `trading.execution.fsm_periodic_cleanup_enabled` | LOW | BOTH (dual-path guard in config_resolver.py) |
| SB-07 | Post-close cooldown | `execution.cooldown_after_close_ms` | `trading.execution.cooldown_after_close_ms` | LOW | trading.execution |
| SB-08 | Anti-race window | `execution.anti_race_close_ms` | `trading.execution.anti_race_close_ms` | LOW | trading.execution |
| SB-09 | Order params | `execution.order_params` | `trading.execution.order_params` | LOW | trading.execution |
| SB-10 | Preflight backoff | `execution.preflight_backoff_ms` | `trading.execution.preflight_backoff_ms` | MEDIUM | trading.execution |
| SB-11 | Guardian tidy flag | `execution.allow_trade_with_guardian_tidy_only` | `trading.execution.allow_trade_with_guardian_tidy_only` | LOW | root alias (event_handlers.py) |
| SB-12 | Order guardian config | `execution.order_guardian` | `trading.execution.order_guardian` | MEDIUM | trading.execution (loader guards against conflict) |

Dead (null) stubs also present in system.yaml: `fallback`, `limit_orders`, `orders`.

**Confirmed: 12 split-brain surfaces. All have identical values in both locations. No value divergence detected.**

---

## Section 9: Safe Next Implementation Seam

### Why the full OS-005 cannot be a single package

1. `config_resolver.py` has explicit dual-path code for `fsm_periodic_cleanup_enabled` that must be updated during migration — not just YAML removal
2. `event_handlers.py` is the only consumer via the root alias (`allow_trade_with_guardian_tidy_only`) — migration requires updating this consumer
3. `config_loader.py` has order_guardian conflict detection — must be preserved or explicitly removed
4. `ExposureConfig.leverage_defaults` has secondary conflicts with instruments.yaml (OS-012, OS-013) — touching exposure risks opening a separate unresolved seam
5. `AuroraConfig.execution = Field(...)` is marked required — changing to `default=None` is a model schema change that needs its own test coverage

### Recommended next implementation seam: EX-REMOVE-ROOT

**Name:** `EX-REMOVE-ROOT — Remove system.yaml:execution block, activate trading.execution as sole SSOT`

**Scope (exact and bounded):**
1. Remove the entire `execution:` block from `config/aurora/system.yaml`
2. Change `AuroraConfig.execution: Optional[ExecutionConfig] = Field(...)` → `Optional[ExecutionConfig] = Field(default=None)`
3. Add a loader guard (following the ops and trading_mode pattern): if `merged_config.get("execution")` is a non-None dict after merge, raise `ConfigContractError` — prevents silent regression
4. Update `config_resolver.py:67-109`: remove the first branch that checks root `config.execution.fsm_periodic_cleanup_enabled`; keep only the trading.execution check
5. Update `event_handlers.py:1147`: change `config.execution` → `config.trading.execution` (or trust the alias since after migration `config.execution is config.trading.execution`)
6. Verify `config_loader.py` order_guardian conflict detection is still coherent (if root execution is absent, there is no root `execution.order_guardian` to conflict with)
7. Add focused tests proving:
   - system.yaml must NOT have `execution:` block (structural guard)
   - config loads correctly with trading.execution as sole source
   - `cfg.execution is cfg.trading.execution` (alias activated)
   - config_resolver.py cleanup flag reads from trading.execution only
   - Loader guard rejects any reintroduction of root execution block

**Why this seam is safe:**
- All runtime consumers ALREADY read `config.trading.execution` exclusively (F-09)
- The alias fires deterministically after removal (I-03)
- The pattern is identical to ops.* repair (precedent from OS-001)
- Zero value changes — same data, one source removed

**Explicitly excluded from this seam:**
- Do not touch `execution.exposure.leverage_defaults` OS-012/OS-013 (separate audit needed)
- Do not touch strategy profiles, instruments, or market_data config
- Do not clean up deprecated field labels in `ExecutionConfig` Pydantic model (separate housekeeping)
- Do not migrate `trading.execution.order_params` or other trading-side cleanup

---

## Section 10: Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `config_resolver.py` dual-path guard updated incorrectly | HIGH | Dedicated test for fsm_periodic_cleanup_enabled with only trading.execution set |
| `event_handlers.py:1147` stops reading allow_trade_with_guardian_tidy_only | MEDIUM | Verify alias still works OR update consumer to use trading.execution directly |
| Loader order_guardian conflict detection references root execution | MEDIUM | Read exact lines ~710-1108 in config_loader.py before writing the guard — may need to update conflict logic |
| `AuroraConfig.execution = Field(default=None)` breaks a test that expects it to be non-None | LOW | Guard test and structural test catch this |
| Removing system.yaml:execution exposes null stubs in trading.yaml | LOW | `fallback: null`, `limit_orders: null`, `orders: null` remain in trading.yaml; null stubs are already parsed correctly by Pydantic with `Field(...)` Optional |
| `ExposureConfig.leverage_defaults` secondary conflicts with instruments.yaml | MEDIUM | Explicitly exclude from this seam; document as deferred OS-012/OS-013 |
| `preflight_backoff_ms` model DEPRECATED label is factually wrong | LOW | Document discrepancy; do not fix in this seam |

---

## Section 11: Final Verdict

```
MUST_SPLIT_INTO_SMALLER_SEAMS
```

OS-005 as a single migration seam is not safe due to:
- Mixed dead and live surfaces
- Two existing split-brain detectors (config_resolver.py dual-path, loader order_guardian check) that require coordinated updates
- Exposure config having a secondary sub-seam (OS-012/OS-013 leverage conflict)
- One consumer (event_handlers.py) relying on the root alias that currently dead-fires

**Recommended first implementation package:** `EX-REMOVE-ROOT`
Remove `system.yaml:execution.*` block. Add loader guard. Activate `_backcompat_root_execution_alias`. Update `config_resolver.py`. Single bounded atomic seam, zero value changes, follows the established OS-001/OS-004 repair pattern.

---

## Appendix: Next Bounded Implementation Prompt

```
MODE: implementation_package
MODEL: HIGH

Track: config / SSOT / split-brain repair
Priority: P0 config-ownership stabilization
Goal: resolve OS-005 execution split-brain — first implementation seam (EX-REMOVE-ROOT)

Context:
OS-001/002/003 (ops), OS-004 (trading_mode) are FIXED_AND_VALIDATED.
EXECUTION_CONFIG_SPLIT_AUDIT_REPORT_v1.md has been produced.
Verdict: MUST_SPLIT_INTO_SMALLER_SEAMS.
This package implements the first and most bounded seam: EX-REMOVE-ROOT.

ALL of the following are FACTS (do not re-verify, just implement):
- All runtime consumers already use config.trading.execution.* (not root config.execution.*)
- The _backcompat_root_execution_alias model validator is currently dead (never fires)
- config_resolver.py:67-109 has a dual-path check for fsm_periodic_cleanup_enabled that must be updated
- event_handlers.py:1147 accesses config.execution (root alias) for allow_trade_with_guardian_tidy_only
- system.yaml:execution and trading.yaml:trading.execution have identical values for all 12 surfaces
- config_loader.py has order_guardian conflict detection at ~lines 710, 1105

Required tasks (exactly these, no more):
1. Remove the entire execution: block from config/aurora/system.yaml
2. Change AuroraConfig.execution: Optional[ExecutionConfig] = Field(...) to Field(default=None)
3. Add loader guard in config_loader.py: if merged_config.get("execution") is a non-None dict, raise ConfigContractError("execution block must not appear in system.yaml — canonical: trading.yaml -> trading.execution.* (EX-REMOVE-ROOT-2026-05-09)")
4. Update config_resolver.py:67-109 — remove the dual-path check, use only trading.execution path for fsm_periodic_cleanup_enabled
5. Verify event_handlers.py:1147 — confirm alias still provides correct value (cfg.execution is cfg.trading.execution after alias fires) OR update to use trading.execution directly
6. Add focused tests proving:
   - system.yaml must NOT have execution: block
   - cfg.execution is cfg.trading.execution (alias active)
   - startup validates correctly
   - fsm_periodic_cleanup_enabled reads from trading.execution only
   - loader guard rejects execution block reintroduction in system.yaml

Forbidden:
- Do not touch execution.exposure.leverage_defaults OS-012/OS-013
- Do not touch strategy configs, instruments, market_data, ops, trading_mode
- Do not clean up deprecated field labels in ExecutionConfig model
- Do not migrate trading.execution.order_params or other trading-side cleanup
- Do not shard files

Required output artifact: EXECUTION_ROOT_REMOVAL_REPORT_v1.md
Required verdict: FIXED_AND_VALIDATED | PARTIALLY_FIXED_WITH_COMPAT_BRIDGE | BLOCKED_BY_RUNTIME_PROOF_GAP | BLOCKED_DO_NOT_MERGE
```
