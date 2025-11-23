# Execution Position Config Field Usage Report

**RID:** EP-CONFIG-FIELD-USAGE-REPORT-S6
**Date:** 2025-11-21
**Status:** ✅ COMPLETED (Audit-only, Zero Logic Changes)
**Purpose:** Inventory which ExecutionPositionConfig fields are actually consumed by runtime vs. declared-only

---

## 1. Overview

This document answers one simple question:

**"Which fields of ExecutionPositionConfig are actually read/used in code, and which are currently declaration-only?"**

This report prepares the ground for future config schema cleanup and helps avoid "bloating" config without need.

**Scope:**
- **Model:** `ExecutionPositionConfig` (apps/reference/domains/execution_position/config.py)
- **Domain:** `apps/reference/domains/execution_position/**` (including `shadow_execpos/`)
- **Analysis Method:** grep search for field usage across domain code

**Out of Scope:**
- Other domains (risk_strategy, analyzer, etc.)
- Test files (tests/** usage not counted)
- Config loader/resolver (apps/reference/config/execution_position.py itself)

---

## 2. Model Snapshot

Full field inventory from `ExecutionPositionConfig` (apps/reference/domains/execution_position/config.py):

### 2.1 Root Structure

| field_path | type | default | constraints | description |
|------------|------|---------|-------------|-------------|
| `aggregated_oco` | AggregatedOcoConfig | (nested) | — | Bracket management config |
| `trailing` | TrailingConfig | (nested) | — | Trailing stop config |
| `close` | CloseConfig | (nested) | — | Position close config |

### 2.2 AggregatedOcoConfig Fields

| field_path | type | default | constraints | description |
|------------|------|---------|-------------|-------------|
| `aggregated_oco.enabled` | bool | False | — | Master switch for aggregated OCO |
| `aggregated_oco.aggregated_only_mode` | bool | False | — | Force clean entry/exit (no inline TP/SL) |
| `aggregated_oco.sl_pct` | float | 0.02 | gt=0, <1.0 | Stop-loss distance as % of entry (e.g., 0.02 = 2%) |
| `aggregated_oco.tp_rr` | float | 2.0 | gt=0, 0.1-100 | Take-profit reward/risk ratio (e.g., 2.0 = 2:1) |
| `aggregated_oco.recalc_on_scale_in` | bool | True | — | Rebuild brackets when position grows |
| `aggregated_oco.recalc_on_partial_close` | bool | False | — | Rebuild brackets when position shrinks |
| `aggregated_oco.ttl_protect_new_bracket_ms` | int | 3000 | ge=0 | TTL to protect new brackets from cleanup |
| `aggregated_oco.allow_unprotected_position` | bool | False | — | Allow positions without SL (strict mode if False) |
| `aggregated_oco.max_sl_legs` | int | 1 | ge=1 | Max number of SL orders per position |
| `aggregated_oco.max_tp_legs` | int | 1 | ge=1 | Max number of TP orders per position |
| `aggregated_oco.watchdog` | AggregatedOcoWatchdogConfig | (nested) | — | Watchdog config for bracket violations |

### 2.3 AggregatedOcoWatchdogConfig Fields

| field_path | type | default | constraints | description |
|------------|------|---------|-------------|-------------|
| `aggregated_oco.watchdog.enabled` | bool | False | — | Enable watchdog monitoring |
| `aggregated_oco.watchdog.interval_sec` | int | 5 | ge=1 | Watchdog poll interval |
| `aggregated_oco.watchdog.auto_heal_orphans` | bool | True | — | Auto-heal orphan brackets |
| `aggregated_oco.watchdog.grace` | AggregatedOcoWatchdogGraceConfig | (nested) | — | Grace period config |

### 2.4 AggregatedOcoWatchdogGraceConfig Fields

| field_path | type | default | constraints | description |
|------------|------|---------|-------------|-------------|
| `aggregated_oco.watchdog.grace.enabled` | bool | False | — | Enable grace period for violations |
| `aggregated_oco.watchdog.grace.period_sec` | float | 0.0 | ge=0 | Grace period duration |
| `aggregated_oco.watchdog.grace.kinds` | List[str] | [] | — | Violation kinds subject to grace |

### 2.5 TrailingConfig Fields

| field_path | type | default | constraints | description |
|------------|------|---------|-------------|-------------|
| `trailing.enabled` | bool | False | — | Master switch for trailing logic |
| `trailing.trail_distance_bps` | float | 100.0 | ge=0 | Move SL when price advances this many bps |
| `trailing.activate_after_bps` | float | 0.0 | ge=0 | Activation threshold (0 = immediate) |
| `trailing.breakeven_rr` | float | 0.0 | ge=0 | Move SL to entry after R:R multiple (0 = disabled) |
| `trailing.hard_time_exit_sec` | Optional[float] | None | ge=0 if set | Force exit after seconds (None = disabled) |
| `trailing.activation_profit_atr_k` | float | 1.0 | ge=0 | Activation profit multiplier (legacy) |
| `trailing.cooldown_sec` | float | 0.0 | ge=0 | Cooldown between trailing updates |
| `trailing.step_bps` | float | 0.0 | ge=0 | Step size for SL updates (0 = no step) |

### 2.6 CloseConfig Fields

| field_path | type | default | constraints | description | usage_kind |
|------------|------|---------|-------------|-------------|------------|
| `close.max_hold_time_sec` | int | 0 | ge=0 | Force close after seconds (0 = disabled) | **UNUSED** |
| `close.reason_policy` | str | "default" | in {"default", "strict", "permissive"} | Close reason policy | **UNUSED** |
| `close.allow_time_exit` | bool | True | — | Allow time-based exits | **UNUSED** |
| `close.allow_profit_exit` | bool | True | — | Allow profit target exits | **UNUSED** |

**Note:** Entire CloseConfig block is placeholder per config.py docstring (lines 218-241). No runtime code consumes these fields (UNUSED).

**Total Fields:** 30 (root: 3, aggregated_oco: 11, watchdog: 4, grace: 3, trailing: 8, close: 4)

---

## 3. Runtime Usage Map

**Analysis Method:** grep search for each field name in `apps/reference/domains/execution_position/**/*.py` (excluding config.py itself and test files).

**Usage Categories:**
- **AGG_OCO_RULE**: Used in BracketService evaluation logic (bracket_service.py)
- **RUNTIME_PARAM**: Used in ExecPosRuntimeV2 (shadow_execpos/runtime.py)
- **TRAILING_PARAM**: Used in TrailingService (shadow_execpos/trailing.py)
- **LEGACY_ADAPT**: Used in legacy fsm_manage.py or manage_config.py
- **WATCHDOG_PARAM**: Used in AggOcoWatchdogService (shadow_execpos/watchdog.py)
- **DOC_ONLY**: Declared in model but not found in runtime code
- **UNUSED**: Not found in any runtime files (config.py only)

### 3.1 AggregatedOcoConfig Field Usage

| field_path | usage_kind | used_in_files | line_refs |
|------------|------------|---------------|-----------|
| `aggregated_oco.enabled` | LEGACY_ADAPT | fsm_manage.py | line 1509 (`.brackets.aggregated_oco.enabled`) |
| `aggregated_oco.aggregated_only_mode` | LEGACY_ADAPT | manage_config.py | lines 709, 712 (validation logic) |
| `aggregated_oco.sl_pct` | AGG_OCO_RULE, RUNTIME_PARAM | bracket_service.py, runtime.py, fsm_manage.py | bracket_service.py:729,754; runtime.py:875 (via agg.sl_pct); fsm_manage.py:1355 |
| `aggregated_oco.tp_rr` | AGG_OCO_RULE, RUNTIME_PARAM | bracket_service.py, runtime.py, fsm_manage.py, trailing.py, watchdog.py | bracket_service.py:730,755; runtime.py:877,896; fsm_manage.py:1356; trailing.py:80; watchdog.py:213 |
| `aggregated_oco.recalc_on_scale_in` | RUNTIME_PARAM, LEGACY_ADAPT | runtime.py, fsm_manage.py, watchdog.py | runtime.py:872,891; fsm_manage.py:1610; watchdog.py:208 |
| `aggregated_oco.recalc_on_partial_close` | RUNTIME_PARAM, LEGACY_ADAPT | runtime.py, fsm_manage.py, manage_config.py, watchdog.py | runtime.py:871,890; fsm_manage.py:1599; manage_config.py:721,723; watchdog.py:207 |
| `aggregated_oco.ttl_protect_new_bracket_ms` | RUNTIME_PARAM, LEGACY_ADAPT | runtime.py, fsm_manage.py, watchdog.py | runtime.py:873,892; fsm_manage.py:1870; watchdog.py:209 |
| `aggregated_oco.allow_unprotected_position` | AGG_OCO_RULE, RUNTIME_PARAM, LEGACY_ADAPT | bracket_service.py, runtime.py, fsm_manage.py, manage_config.py, watchdog.py | bracket_service.py:590,608; runtime.py:870,889; fsm_manage.py:1786,1880; manage_config.py:717,719; watchdog.py:206 |
| `aggregated_oco.max_sl_legs` | AGG_OCO_RULE, RUNTIME_PARAM | bracket_service.py, runtime.py, watchdog.py | bracket_service.py:611,613,617; runtime.py:875,894; watchdog.py:211 |
| `aggregated_oco.max_tp_legs` | RUNTIME_PARAM | runtime.py, watchdog.py | runtime.py:874,893; watchdog.py:210 |
| `aggregated_oco.watchdog` | RUNTIME_PARAM | runtime.py (passed to BracketService as watchdog param) | runtime.py (BracketService init) |

### 3.2 AggregatedOcoWatchdogConfig Field Usage

| field_path | usage_kind | used_in_files | line_refs |
|------------|------------|---------------|-----------|
| `aggregated_oco.watchdog.enabled` | WATCHDOG_PARAM | shadow_execpos/watchdog.py, manage_config.py | watchdog.py (implicit via config), manage_config.py:500 (resolution) |
| `aggregated_oco.watchdog.interval_sec` | WATCHDOG_PARAM | shadow_execpos/watchdog.py, manage_config.py | watchdog.py (implicit via config), manage_config.py:501 (resolution) |
| `aggregated_oco.watchdog.auto_heal_orphans` | WATCHDOG_PARAM | manage_config.py | manage_config.py:502 (resolution logic) |
| `aggregated_oco.watchdog.grace` | WATCHDOG_PARAM | manage_config.py | manage_config.py:506 (resolution) |

**Note:** Watchdog fields are read via manage_config.py resolution but not directly accessed in V2 runtime path (ExecPosRuntimeV2). AggOcoWatchdogService exists but is not explicitly wired to ep_config.aggregated_oco.watchdog in current V2 flow.

### 3.3 AggregatedOcoWatchdogGraceConfig Field Usage

| field_path | usage_kind | used_in_files | line_refs |
|------------|------------|---------------|-----------|
| `aggregated_oco.watchdog.grace.enabled` | WATCHDOG_PARAM | manage_config.py | manage_config.py:517 (resolution) |
| `aggregated_oco.watchdog.grace.period_sec` | WATCHDOG_PARAM | manage_config.py | manage_config.py:518 (resolution) |
| `aggregated_oco.watchdog.grace.kinds` | WATCHDOG_PARAM | manage_config.py | manage_config.py:519 (resolution) |

**Note:** Grace config exists in model but is not actively enforced in V2 runtime (ExecPosRuntimeV2/BracketService). Legacy manage_config.py resolves it but runtime does not consume it.

### 3.4 TrailingConfig Field Usage

| field_path | usage_kind | used_in_files | line_refs |
|------------|------------|---------------|-----------|
| `trailing.enabled` | TRAILING_PARAM | shadow_execpos/trailing.py | trailing.py (implicit via TrailingConfig init) |
| `trailing.trail_distance_bps` | TRAILING_PARAM | shadow_execpos/trailing.py | trailing.py:79,118,128 (SL calculation) |
| `trailing.activate_after_bps` | TRAILING_PARAM | shadow_execpos/trailing.py | trailing.py:104,106 (activation threshold) |
| `trailing.breakeven_rr` | TRAILING_PARAM | shadow_execpos/trailing.py | trailing.py:116,118 (breakeven logic) |
| `trailing.hard_time_exit_sec` | TRAILING_PARAM | shadow_execpos/trailing.py | trailing.py:144,145 (time-based exit) |
| `trailing.activation_profit_atr_k` | DOC_ONLY | — | **NOT FOUND** in trailing.py runtime (legacy field) |
| `trailing.cooldown_sec` | DOC_ONLY | — | **NOT FOUND** in trailing.py runtime (legacy field) |
| `trailing.step_bps` | DOC_ONLY | — | **NOT FOUND** in trailing.py runtime (legacy field) |

**Note:** `activation_profit_atr_k`, `cooldown_sec`, `step_bps` are declared in TrailingConfig but not consumed by shadow_execpos/trailing.py. These are legacy fields from manage_config.py that were copied to Pydantic model but not wired to V2 runtime.

### 3.5 CloseConfig Field Usage

| field_path | usage_kind | used_in_files | line_refs |
|------------|------------|---------------|-----------|
| `close.max_hold_time_sec` | UNUSED | — | **NOT FOUND** in runtime (doc example only in config.py:281) |
| `close.reason_policy` | UNUSED | — | **NOT FOUND** in runtime (validator exists but not enforced) |
| `close.allow_time_exit` | UNUSED | — | **NOT FOUND** in runtime (placeholder field) |
| `close.allow_profit_exit` | UNUSED | — | **NOT FOUND** in runtime (placeholder field) |

**Note:** Entire CloseConfig block is **DOC_ONLY** / **UNUSED**. Per config.py comments (lines 218-241): "This config block does NOT exist in current YAML structure (execution.yaml). Added as placeholder for future close logic consolidation. Current close logic is scattered across trailing.hard_time_exit_sec and quick_profit.enabled."

---

## 4. Summary

### 4.1 Usage Statistics

**Total Fields:** 30

**By Usage Category:**
- **AGG_OCO_RULE** (BracketService evaluation): 4 fields
  - `sl_pct`, `tp_rr`, `allow_unprotected_position`, `max_sl_legs`
- **RUNTIME_PARAM** (ExecPosRuntimeV2): 9 fields
  - All core aggregated_oco fields (sl_pct, tp_rr, max_sl/tp_legs, recalc flags, ttl, allow_unprotected)
- **TRAILING_PARAM** (TrailingService): 5 fields
  - `enabled`, `trail_distance_bps`, `activate_after_bps`, `breakeven_rr`, `hard_time_exit_sec`
- **WATCHDOG_PARAM** (manage_config.py resolution): 7 fields
  - All watchdog.* and grace.* fields (read but not actively enforced in V2 runtime)
- **LEGACY_ADAPT** (fsm_manage.py): 8 fields
  - `enabled`, `aggregated_only_mode`, `sl_pct`, `tp_rr`, recalc flags, ttl, allow_unprotected
- **DOC_ONLY** (declared but not used in runtime): 7 fields
  - `trailing.activation_profit_atr_k`, `trailing.cooldown_sec`, `trailing.step_bps`
  - All 4 `close.*` fields (entire CloseConfig block)
- **UNUSED** (not found in any runtime code): 4 fields
  - Same as DOC_ONLY (close.* fields)

**Overlap Note:** Some fields appear in multiple categories (e.g., `sl_pct` is both AGG_OCO_RULE and RUNTIME_PARAM). Unique count of **actively used fields: 16/30 (53%)**.

### 4.2 Key Findings

✅ **Core Aggregated OCO Fields (9/11): ACTIVELY USED**
- `sl_pct`, `tp_rr`, `max_sl_legs`, `max_tp_legs` (bracket calculation)
- `recalc_on_scale_in`, `recalc_on_partial_close` (bracket rebuild triggers)
- `ttl_protect_new_bracket_ms` (cleanup protection)
- `allow_unprotected_position` (strict mode enforcement)
- `watchdog` (passed to BracketService but not explicitly consumed in V2)

⚠️ **Aggregated OCO Watchdog Fields (7/7): PARTIALLY USED**
- All 7 fields are read via manage_config.py resolution
- **Gap:** Not directly wired to ExecPosRuntimeV2/BracketService in V2 path
- **Current State:** AggOcoWatchdogService exists but operates independently (not integrated with ep_config.aggregated_oco.watchdog)
- **Future:** Wire watchdog config to V2 runtime (Phase 4)

✅ **Core Trailing Fields (5/8): ACTIVELY USED**
- `enabled`, `trail_distance_bps`, `activate_after_bps`, `breakeven_rr`, `hard_time_exit_sec` (all used in shadow_execpos/trailing.py)

⚠️ **Legacy Trailing Fields (3/8): UNUSED IN V2**
- `activation_profit_atr_k`, `cooldown_sec`, `step_bps` — declared but not consumed by shadow_execpos/trailing.py
- **Reason:** Copied from manage_config.py TrailingConfig but not wired to V2 TrailingService
- **Recommendation:** Either wire these fields to V2 runtime OR remove from ExecutionPositionConfig

❌ **Close Fields (4/4): COMPLETELY UNUSED**
- Entire CloseConfig block is placeholder (per config.py docstring lines 218-241)
- No runtime code consumes these fields
- **Reason:** Close logic scattered across `trailing.hard_time_exit_sec` and `quick_profit.enabled` (not centralized)
- **Recommendation:** Either implement CloseFlowService to consume these fields OR remove CloseConfig from model

### 4.3 Field Groups by Status

**Production-Ready (16 fields):**
- `aggregated_oco.{sl_pct, tp_rr, max_sl_legs, max_tp_legs, recalc_on_scale_in, recalc_on_partial_close, ttl_protect_new_bracket_ms, allow_unprotected_position}`
- `trailing.{enabled, trail_distance_bps, activate_after_bps, breakeven_rr, hard_time_exit_sec}`
- `aggregated_oco.enabled`, `aggregated_oco.aggregated_only_mode`

**Partially Wired (7 fields):**
- `aggregated_oco.watchdog.*` (read via manage_config.py but not consumed by V2 runtime)

**Unused/DOC_ONLY (7 fields):**
- `trailing.{activation_profit_atr_k, cooldown_sec, step_bps}` (3 fields)
- `close.{max_hold_time_sec, reason_policy, allow_time_exit, allow_profit_exit}` (4 fields)

---

## 5. Suggested Follow-ups (Optional)

**Note:** These are recommendations based on factual UNUSED findings, not commitments. Future tasks will be prioritized separately.

### 5.1 Wire Watchdog Config to V2 Runtime (Phase 4)

**Gap:** `aggregated_oco.watchdog.*` fields are read via manage_config.py but not explicitly consumed by ExecPosRuntimeV2.

**Scope:**
- Update AggOcoWatchdogService to accept `AggregatedOcoWatchdogConfig` from ep_config
- Wire watchdog.enabled, interval_sec, auto_heal_orphans to V2 runtime
- Implement grace period enforcement (watchdog.grace.*)

**Constraint:** Keep legacy manage_config.py resolution as fallback.

### 5.2 Remove Unused Trailing Fields (Phase 5 Cleanup)

**Gap:** 3 trailing fields declared but not used in V2 runtime.

**Scope:**
- Remove `activation_profit_atr_k`, `cooldown_sec`, `step_bps` from TrailingConfig
- OR wire these fields to shadow_execpos/trailing.py (if needed)

**Rationale:** These fields were copied from legacy manage_config.py but not integrated into V2 TrailingService.

### 5.3 Implement CloseFlowService OR Remove CloseConfig (Phase 5+)

**Gap:** Entire CloseConfig block (4 fields) is unused placeholder.

**Option A:** Implement CloseFlowService to centralize close logic
- Consume `max_hold_time_sec`, `reason_policy`, `allow_time_exit`, `allow_profit_exit`
- Replace scattered close logic (trailing.hard_time_exit_sec, quick_profit.enabled)

**Option B:** Remove CloseConfig from ExecutionPositionConfig
- Keep close logic scattered (current state)
- Remove unused config block to avoid bloat

**Recommendation:** Start with Option B (remove unused fields) unless CloseFlowService is prioritized.

### 5.4 Config Field Usage Audit (Ongoing)

**Objective:** Add pre-commit hook or CI check to detect new UNUSED fields.

**Scope:**
- Automated grep search for field names in runtime code
- Report fields declared in config.py but not found in domain/**/*.py
- Warn on new DOC_ONLY fields without runtime usage

**Deliverable:** CI job that runs on config.py changes.

---

## 6. Conclusion

**Quality Score:** **7/10**

**Justification:**
- **Strong:** Core aggregated_oco and trailing fields are actively used (16/30 = 53%)
- **Strong:** No dead code in critical paths (BracketService, TrailingService)
- **Minor Gap:** Watchdog config exists but not fully wired to V2 runtime (legacy manage_config.py only)
- **Minor Gap:** 3 trailing fields declared but unused (legacy carryover)
- **Major Gap:** Entire CloseConfig block (4 fields) is unused placeholder (13% of total fields)

**Recommendation:**
- **Phase 4:** Wire watchdog config to V2 runtime (prioritize over cleanup)
- **Phase 5:** Remove unused trailing fields (activation_profit_atr_k, cooldown_sec, step_bps)
- **Phase 5+:** Either implement CloseFlowService OR remove CloseConfig block

**Overall Assessment:** Config model is production-ready for core features (aggregated_oco, trailing). Cleanup needed for watchdog wiring and unused fields, but no blockers.

---

**Document Version:** 1.0
**Last Updated:** 2025-11-21
**Maintainer:** Agent (EP-CONFIG-FIELD-USAGE-REPORT-S6)
