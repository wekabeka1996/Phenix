# Execution Position Configuration Map

**RID:** EP-CONFIG-DOMAINS-REF-MAP-S4
**Date:** 2025-11-21
**Status:** ✅ ACTIVE
**Purpose:** Complete reference map of all configuration paths for execution_position domain

---

## 📋 Overview

This document serves as the **single source of truth** for understanding how configuration flows through the execution_position domain, from YAML files to runtime execution.

**Key Objectives:**
1. **Transparency** — Document every config source and transformation
2. **Traceability** — Map YAML paths → Pydantic models → runtime usage
3. **Migration Clarity** — Track Phase 1-5 evolution from dict → typed config
4. **Zero Ambiguity** — One canonical reference for all config questions

---

## 🗺️ Section 1: Configuration Sources

### 1.1 Primary YAML Config

**File:** `config/domains/execution.yaml`

**Structure:**
```yaml
exposure:
  max_equity_utilization_pct: 200.0
  leverage_defaults:
    enable: true
    oco_emulation: true
    aggregated_oco:
      enabled: true
      aggregated_only_mode: true
      recalc_on_scale_in: true
      ttl_protect_new_bracket_ms: 3000
      watchdog:
        enabled: true
        interval_sec: 5

brackets:  # Fallback/canonical block (mirrors manage.brackets)
  aggregated_oco:
    enabled: true
    aggregated_only_mode: true

trailing:
  enabled: true
  trail_distance_bps: 100.0

close:
  max_hold_time_sec: 86400
  reason_policy: "default"
```

**Paths:**
- Primary: `exposure.leverage_defaults.aggregated_oco.*`
- Fallback: `brackets.aggregated_oco.*`
- Trailing: `trailing.*` (at root level or under `manage`)
- Close: `close.*` (at root level)

**Migration Status:** Active (Phase 2-3)

---

### 1.2 Example YAML Configs

**Files:**
- `config/examples/execution_position_safe.yaml` — Conservative (SL 1.5%, TP 1.5x)
- `config/examples/execution_position_moderate.yaml` — Balanced (SL 2.0%, TP 2.0x)
- `config/examples/execution_position_aggressive.yaml` — High-risk (SL 1.0%, TP 3.0x)

**Purpose:**
- Production-ready templates
- Risk profile presets
- Documentation/testing

**Validation:** All profiles pass `ExecutionPositionConfig` Pydantic validation

**Usage:**
```bash
cp config/examples/execution_position_moderate.yaml config/domains/execution.yaml
```

---

### 1.3 Pydantic Models (SSOT)

**File:** `apps/reference/domains/execution_position/config.py`

**Models:**
```python
ExecutionPositionConfig
├── aggregated_oco: AggregatedOcoConfig
│   ├── enabled: bool = True
│   ├── sl_pct: float (gt=0, validator: < 1.0)
│   ├── tp_rr: float (gt=0, validator: 0.1-100)
│   ├── max_sl_legs: int (ge=1)
│   ├── max_tp_legs: int (ge=1)
│   ├── recalc_on_scale_in: bool = False
│   ├── recalc_on_partial_close: bool = False
│   ├── allow_unprotected_position: bool = False
│   ├── ttl_protect_new_bracket_ms: int (ge=0)
│   └── watchdog: AggregatedOcoWatchdogConfig
│       ├── enabled: bool = True
│       ├── interval_sec: int (ge=1)
│       ├── auto_heal_orphans: bool = True
│       └── grace: AggregatedOcoWatchdogGraceConfig
│           ├── enabled: bool = True
│           ├── period_sec: float (ge=0)
│           └── kinds: list[str] = []
├── trailing: TrailingConfig
│   ├── enabled: bool = True
│   ├── trail_distance_bps: float (ge=0)
│   ├── activate_after_bps: float (ge=0)
│   ├── breakeven_rr: Optional[float] (ge=0)
│   └── hard_time_exit_sec: Optional[float] (ge=0)
└── close: CloseConfig
    ├── max_hold_time_sec: int (ge=0)
    ├── reason_policy: str (validator: ["default", "strict", "permissive"])
    ├── allow_time_exit: bool = True
    └── allow_profit_exit: bool = True
```

**Key Features:**
- **Immutable:** All models frozen (`Config.frozen = True`)
- **Validated:** Range checks + custom validators
- **Type-safe:** Pydantic 2.x with Field constraints

**Created:** Phase 1 (EP-CONFIG-SSOT-S1)

---

### 1.4 Config Resolver

**File:** `apps/reference/config/execution_position.py`

**Function:** `resolve_execution_position_config(raw_cfg: Dict) -> ExecutionPositionConfig`

**Responsibilities:**
1. **Path Resolution** — Try primary paths, fallback to legacy
2. **Type Coercion** — Convert YAML strings to correct types
3. **Validation** — Raise `ValidationError` on invalid config
4. **Defaults** — Apply sensible defaults for missing fields

**Resolution Paths:**
```python
# Primary
manage.brackets.aggregated_oco.*

# Fallback (backward compat)
brackets.aggregated_oco.*

# Trailing (multiple locations)
manage.trailing.*
trailing.*  # root level

# Close (root level)
close.*
```

**Type Coercion Helpers:**
- `_coerce_bool(value, default)` — "true" → True
- `_coerce_int(value, default)` — "100" → 100
- `_coerce_float(value, default)` — "1.5" → 1.5

**Created:** Phase 1 (EP-CONFIG-SSOT-S1)

---

### 1.5 Hybrid Adapter (manage_config.py)

**File:** `apps/reference/domains/execution_position/manage_config.py`

**Purpose:** Temporary bridge between V2 Pydantic config (`ExecutionPositionConfig`) and legacy dict-based runtime code during migration (Phase 2-4).

**Hybrid Behavior:**

1. **V2 Path (Primary):**
   - Detector: `_get_v2_execution_manage_cfg(cfg)` → checks `cfg.config_v2.domains["execution"]["manage"]`
   - Builder: `_build_manage_from_v2(v2_cfg, cfg)` → uses specialized `_resolve_*_from_v2()` functions
   - Source: `source="config_v2"` in result
   - Validation: Strict Pydantic validation, raises exceptions on invalid data

2. **Legacy Path (Fallback):**
   - Triggered when: V2 config absent OR V2 parsing raises exception (except `ConfigError`)
   - Builder: `_build_manage_from_legacy(config)` → uses generic `_resolve_*()` + `_pluck()`
   - Source: `source="legacy"` in result
   - Validation: Manual type coercion (`_coerce_bool`, `_coerce_int`, etc.), lenient

3. **Priority Order:**
   - **Entry Point:** `resolve_execution_manage_config(config)`
   - **Execution:** Try V2 first → fallback to legacy on failure
   - **Rationale:** New V2 configs get strict validation; old configs keep working unchanged

**Key Functions:**
```python
resolve_execution_manage_config(cfg)  # Main entry (dual-path)
  ├─> _get_v2_execution_manage_cfg(cfg)  # V2 detector
  ├─> _build_manage_from_v2(v2_cfg, cfg)  # V2 builder (strict)
  │    └─> _resolve_*_from_v2(v2_cfg)  # 8 V2-specific resolvers
  └─> _build_manage_from_legacy(cfg)  # Legacy builder (lenient)
       └─> _resolve_*(node)  # 11 legacy resolvers
```

**Testing:** `tests/domains/execution_position/test_manage_config_hybrid.py` (11 tests)
- V2 path: 2 tests (V2 config detected, Pydantic model_dump)
- Legacy path: 4 tests (no V2, missing domains/execution/manage)
- Hybrid priority: 1 test (V2 wins over legacy when both present)
- Fallback: 2 tests (V2 exception → legacy, ConfigError bubbles up)
- Caching: 2 tests (same object cached, different object re-resolved)

**Migration Context:**
- **Phase 2-3:** Hybrid mode active (V2 SSOT + legacy support)
- **Phase 4:** Runtime adopts V2 → legacy path usage decreases
- **Phase 5:** Planned removal of legacy code paths (cleanup target)

**Related:** See [Phase 4 Runtime Adoption](#section-4-migration-timeline) for migration timeline.

**Documentation:** RID EP-CONFIG-MANAGE-HYBRID-S5 (2025-11-21)

---

### 1.6 Legacy Config (Deprecated)

**File:** `apps/reference/domains/execution_position/manage_config.py` (same as Hybrid Adapter, different role)

**Dataclasses:**
- `ExecutionManageConfig` — Top-level manage config
- `AggregatedOcoConfig` (dict-based)
- `WatchdogConfig` (dict-based)
- `OrphanMonitorConfig`
- `QuickProfitConfig`
- `TrailingConfig` (dict-based)

**Status:**
- ⚠️ **Active** in Phase 2-3 (runtime still uses dict)
- 🔄 **Hybrid Adapter** (1.5) wraps this for V2 compatibility
- 🗑️ **Phase 5 Cleanup Target** (replace with Pydantic models)

**Migration Path:**
```
Phase 1-3: Parallel systems (dict + Pydantic coexist via Hybrid Adapter)
Phase 4: Runtime adopts Pydantic (apps/reference/domains/execution_position/*)
Phase 5: Remove dict-based config + Hybrid Adapter (full Pydantic migration)
```

---

### 1.7 Global Config Dependencies

**Instruments Config:**
- **Path:** `config/instruments.yaml` → `trading.instruments`
- **Used By:** `fsm_open.py`, `fsm_manage.py`
- **Fields:**
  - `min_qty` — Minimum order quantity
  - `qty_step` — Quantity precision
  - `price_step` — Price precision
  - `min_notional` — Minimum notional value
  - `leverage` — Max leverage per symbol

**Example Usage:**
```python
# apps/reference/domains/execution_position/fsm_open.py
instruments = self.config.trading.instruments.get(symbol, {})
min_qty = instruments.get("min_qty", Decimal("0.001"))
```

**Modes Config:**
- **Path:** `config/modes.yaml` → `trading.mode`
- **Values:** `"testnet"`, `"live"`, `"hybrid_live_data_testnet_exec"`
- **Used By:** `fsm.py` (adapter initialization)

**Overrides:**
- **Path:** `config/overrides.yaml` (optional)
- **Purpose:** Environment-specific overrides
- **Precedence:** Overrides > Modes > Defaults

---

## 🔄 Section 2: Configuration Processing Pipeline

### 2.1 Load Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. YAML Load                                                │
│    config_loader.py → _load_config_v2()                     │
│    ├── config/domains/execution.yaml                        │
│    ├── config/instruments.yaml                              │
│    └── config/modes.yaml                                    │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Config Resolver                                          │
│    resolve_execution_position_config(raw_cfg)               │
│    ├── Path resolution (primary → fallback)                 │
│    ├── Type coercion (str → int/float/bool)                 │
│    ├── Defaults application                                 │
│    └── Pydantic validation                                  │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. AuroraConfig                                             │
│    config_loader.load_config()                              │
│    ├── execution_position_cfg: ExecutionPositionConfig      │
│    ├── trading: TradingConfig (instruments, modes)          │
│    └── binance_api: BinanceApiConfig                        │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Runtime Consumption (Phase 4 Target)                    │
│    apps/reference/domains/execution_position/               │
│    ├── fsm.py → ExecPosFSM(config)                          │
│    ├── fsm_manage.py → ManageFlowFSM(config)                │
│    └── shadow_execpos/ → ExecPosRuntimeV2                   │
│                                                              │
│    # Future (Phase 4):                                      │
│    ep_cfg = config.execution_position_cfg                   │
│    sl_pct = ep_cfg.aggregated_oco.sl_pct                    │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 Resolver Logic (Detailed)

**File:** `apps/reference/config/execution_position.py`

**Entry Point:**
```python
def resolve_execution_position_config(
    raw_cfg: Dict[str, Any],
    *,
    aggregated_oco_path: Tuple[str, ...] = ("manage", "brackets", "aggregated_oco"),
    trailing_path: Tuple[str, ...] = ("trailing",),
    close_path: Tuple[str, ...] = ("close",)
) -> ExecutionPositionConfig:
    """
    Transform raw YAML → ExecutionPositionConfig (Pydantic).

    Handles:
    - Dual-path resolution (primary → fallback)
    - Type coercion (YAML strings → Python types)
    - Validation (Pydantic validators)
    - Defaults (if fields missing)
    """
```

**Path Resolution Strategy:**
1. **Primary Path:** `manage.brackets.aggregated_oco.*`
   - Modern structure (config_v2 domains)
2. **Fallback Path:** `brackets.aggregated_oco.*`
   - Backward compatibility (legacy structure)
3. **Trailing Multiple Locations:**
   - `manage.trailing.*` (preferred)
   - `trailing.*` (root-level fallback)

**Type Coercion Examples:**
```python
# Input (YAML)
enabled: "true"
sl_pct: "0.015"
max_sl_legs: "2"

# After Coercion
enabled: True       # bool
sl_pct: 0.015       # float
max_sl_legs: 2      # int
```

**Validation Triggers:**
```python
# Invalid: sl_pct <= 0
ValidationError: sl_pct must be > 0

# Invalid: sl_pct >= 1.0
ValidationError: sl_pct must be < 1.0 (100%)

# Invalid: tp_rr not in [0.1, 100]
ValidationError: tp_rr must be between 0.1 and 100

# Invalid: reason_policy not in ["default", "strict", "permissive"]
ValidationError: Invalid reason_policy
```

---

### 2.3 Runtime Consumption (Current State)

**Phase 2-3 (Dict-based):**
```python
# apps/reference/domains/execution_position/manage_config.py
def resolve_execution_manage_config(cfg: Any) -> ExecutionManageConfig:
    """Returns dict-based config (legacy)."""

    manage_cfg = _get_v2_execution_manage_cfg(cfg)
    # Returns ExecutionManageConfig dataclass
```

**Phase 4 Target (Pydantic-based):**
```python
# Future usage in runtime
def _apply_bracket_plan(self, ...):
    ep_cfg = self.config.execution_position_cfg  # ExecutionPositionConfig

    if ep_cfg.aggregated_oco.recalc_on_scale_in:
        # Recalculate brackets on position growth
        ...

    sl_pct = ep_cfg.aggregated_oco.sl_pct
    tp_rr = ep_cfg.aggregated_oco.tp_rr
```

---

## 📖 Section 3: Field Reference Table

### 3.1 Aggregated OCO Fields

| Parameter | Type | Default | Constraint | Runtime Usage | YAML Path |
|-----------|------|---------|------------|---------------|-----------|
| `enabled` | bool | `True` | — | Enable/disable bracket management | `manage.brackets.aggregated_oco.enabled` |
| `sl_pct` | float | `0.02` | `(0, 1.0)` | Stop-loss % from entry (e.g., 0.02 = 2%) | `manage.brackets.aggregated_oco.sl_pct` |
| `tp_rr` | float | `2.0` | `[0.1, 100]` | Take-profit risk-reward ratio | `manage.brackets.aggregated_oco.tp_rr` |
| `max_sl_legs` | int | `1` | `>= 1` | Max SL ladder legs (pyramiding) | `manage.brackets.aggregated_oco.max_sl_legs` |
| `max_tp_legs` | int | `1` | `>= 1` | Max TP ladder legs (scaling out) | `manage.brackets.aggregated_oco.max_tp_legs` |
| `recalc_on_scale_in` | bool | `False` | — | Rebuild brackets when position grows | `manage.brackets.aggregated_oco.recalc_on_scale_in` |
| `recalc_on_partial_close` | bool | `False` | — | Rebuild brackets when position shrinks | `manage.brackets.aggregated_oco.recalc_on_partial_close` |
| `allow_unprotected_position` | bool | `False` | — | Allow positions without brackets (unsafe) | `manage.brackets.aggregated_oco.allow_unprotected_position` |
| `ttl_protect_new_bracket_ms` | int | `5000` | `>= 0` | TTL for new bracket order placement | `manage.brackets.aggregated_oco.ttl_protect_new_bracket_ms` |

**Runtime Files Using These:**
- `apps/reference/domains/execution_position/fsm_manage.py` (ManageFlowFSM)
- `apps/reference/domains/execution_position/shadow_execpos/bracket_service.py` (BracketService)
- `apps/reference/domains/execution_position/shadow_execpos/runtime_v2.py` (ExecPosRuntimeV2)

---

### 3.2 Watchdog Fields

| Parameter | Type | Default | Constraint | Runtime Usage | YAML Path |
|-----------|------|---------|------------|---------------|-----------|
| `enabled` | bool | `True` | — | Enable bracket watchdog monitoring | `manage.brackets.aggregated_oco.watchdog.enabled` |
| `interval_sec` | int | `10` | `>= 1` | Check interval (seconds) | `manage.brackets.aggregated_oco.watchdog.interval_sec` |
| `auto_heal_orphans` | bool | `True` | — | Auto-cancel orphaned brackets | `manage.brackets.aggregated_oco.watchdog.auto_heal_orphans` |
| `grace.enabled` | bool | `True` | — | Enable grace period before escalation | `manage.brackets.aggregated_oco.watchdog.grace.enabled` |
| `grace.period_sec` | float | `3.0` | `>= 0` | Grace period (seconds) | `manage.brackets.aggregated_oco.watchdog.grace.period_sec` |
| `grace.kinds` | list[str] | `[]` | — | Allowed violation kinds during grace | `manage.brackets.aggregated_oco.watchdog.grace.kinds` |

**Watchdog Violation Kinds:**
- `NO_SL_FOR_OPEN_POSITION` — Position without SL
- `ORPHAN_SL_FOR_ZERO_POSITION` — SL without position
- `TOO_MANY_SL` — Excessive SL orders
- `STALE_LEVELS` — Outdated bracket levels

**Runtime Files:**
- `apps/reference/domains/execution_position/watchdog.py` (BracketWatchdog)
- `apps/reference/domains/execution_position/shadow_execpos/watchdog_v2.py`

---

### 3.3 Trailing Stop Fields

| Parameter | Type | Default | Constraint | Runtime Usage | YAML Path |
|-----------|------|---------|------------|---------------|-----------|
| `enabled` | bool | `True` | — | Enable trailing stop | `trailing.enabled` |
| `trail_distance_bps` | float | `100.0` | `>= 0` | Trailing distance (basis points, 1 bp = 0.01%) | `trailing.trail_distance_bps` |
| `activate_after_bps` | float | `0.0` | `>= 0` | Profit threshold to activate (bps) | `trailing.activate_after_bps` |
| `breakeven_rr` | float | `None` | `>= 0` (optional) | Risk-reward to move to breakeven | `trailing.breakeven_rr` |
| `hard_time_exit_sec` | float | `None` | `>= 0` (optional) | Max time before forced exit (seconds) | `trailing.hard_time_exit_sec` |

**Profile Examples:**
- **Safe:** `trail_distance_bps: 80.0` (tight trailing)
- **Moderate:** `trail_distance_bps: 100.0` (balanced)
- **Aggressive:** `trail_distance_bps: 150.0` (wide, let winners run)

**Runtime Files:**
- `apps/reference/domains/execution_position/fsm_manage.py` (trailing logic)
- `apps/reference/domains/execution_position/shadow_execpos/runtime_v2.py`

---

### 3.4 Close Policy Fields

| Parameter | Type | Default | Constraint | Runtime Usage | YAML Path |
|-----------|------|---------|------------|---------------|-----------|
| `max_hold_time_sec` | int | `86400` | `>= 0` | Max position hold time (seconds, default 24h) | `close.max_hold_time_sec` |
| `reason_policy` | str | `"default"` | `["default", "strict", "permissive"]` | Close reason validation policy | `close.reason_policy` |
| `allow_time_exit` | bool | `True` | — | Allow time-based exits | `close.allow_time_exit` |
| `allow_profit_exit` | bool | `True` | — | Allow profit-based exits | `close.allow_profit_exit` |

**Reason Policy:**
- **`default`** — Standard close reasons (manual, profit, loss, time)
- **`strict`** — Requires explicit close reason (no discretionary exits)
- **`permissive`** — Allows any close reason (max flexibility)

**Runtime Files:**
- `apps/reference/domains/execution_position/fsm_close.py` (CloseFlowFSM)
- `apps/reference/domains/execution_position/shadow_execpos/runtime_v2.py`

---

## 🗓️ Section 4: Migration Timeline

### Phase 1: SSOT (✅ COMPLETED)
**RID:** EP-CONFIG-SSOT-S1
**Date:** 2025-11-25
**Status:** ✅ DONE

**Deliverables:**
- ✅ Pydantic models (`apps/reference/domains/execution_position/config.py`)
- ✅ Resolver (`apps/reference/config/execution_position.py`)
- ✅ Unit tests (27/27 passing)

**Impact:**
- Typed config layer ready
- No runtime changes (zero risk)

---

### Phase 2: Config Loader Integration (✅ COMPLETED)
**RID:** EP-CONFIG-INJECTION-S2
**Date:** 2025-11-25
**Status:** ✅ DONE

**Deliverables:**
- ✅ `config_loader.py` builds `execution_position_cfg`
- ✅ `AuroraConfig.execution_position_cfg` field added
- ✅ Integration tests (6/6 passing)
- ✅ Graceful degradation (ValidationError logged, not fatal)

**Impact:**
- Typed config available at startup
- Dict-based config still active (parallel systems)

---

### Phase 3: Example Profiles (✅ COMPLETED)
**RID:** EP-CONFIG-SAMPLES-S3
**Date:** 2025-11-25
**Status:** ✅ DONE

**Deliverables:**
- ✅ 3 YAML examples (`config/examples/execution_position_{safe,moderate,aggressive}.yaml`)
- ✅ Roundtrip tests (16/16 passing)
- ✅ Documentation (`CONFIG_REFERENCE.md`)

**Impact:**
- Users have production-ready templates
- All profiles validated

---

### Phase 4: Runtime Adoption (🚧 PLANNED)
**RID:** EP-CONFIG-RUNTIME-ADOPT-S4
**Status:** 🚧 TODO

**Scope:**
- Update `apps/reference/domains/execution_position/*` to consume `config.execution_position_cfg`
- Replace dict navigation with Pydantic model access
- Deprecate `manage_config.py` dict-based config

**Files to Update:**
- `fsm_manage.py` — Use `ep_cfg.aggregated_oco.*`
- `shadow_execpos/bracket_service.py` — Use Pydantic config
- `shadow_execpos/runtime_v2.py` — Use Pydantic config
- `watchdog.py` — Use `ep_cfg.aggregated_oco.watchdog.*`

**Example Migration:**
```python
# Before (Phase 2-3)
sl_pct = self.config.get("trading", {}).get("execution", {}).get("manage", {}).get("brackets", {}).get("aggregated_oco", {}).get("sl_pct", 0.02)

# After (Phase 4)
sl_pct = self.config.execution_position_cfg.aggregated_oco.sl_pct
```

**Constraint:**
- No breaking changes to external APIs
- Shadow mode (`shadow_execpos/`) updated first
- Legacy FSMs updated after shadow validation

---

### Phase 5: Cleanup (🔮 FUTURE)
**RID:** EP-CONFIG-CLEANUP-S5
**Status:** 🔮 BACKLOG

**Scope:**
- Delete `apps/reference/domains/execution_position/manage_config.py`
- Remove dict-based fallback paths from resolver
- Freeze `ExecutionPositionConfig` schema (versioned)

**Prerequisites:**
- Phase 4 complete (runtime fully migrated)
- All tests passing (no dict access in domain code)
- Metrics show zero dict-based config reads

---

## 📊 Config Path Summary

### Primary Paths (Recommended)

| Config Section | YAML Path | Pydantic Model |
|----------------|-----------|----------------|
| **Aggregated OCO** | `manage.brackets.aggregated_oco.*` | `AggregatedOcoConfig` |
| **Watchdog** | `manage.brackets.aggregated_oco.watchdog.*` | `AggregatedOcoWatchdogConfig` |
| **Trailing** | `trailing.*` (root) | `TrailingConfig` |
| **Close** | `close.*` (root) | `CloseConfig` |

### Fallback Paths (Backward Compat)

| Config Section | Fallback YAML Path | Status |
|----------------|-------------------|--------|
| **Aggregated OCO** | `brackets.aggregated_oco.*` | ⚠️ Deprecated (Phase 5 removal) |
| **Trailing** | `manage.trailing.*` | ✅ Active (secondary path) |

---

## 🔍 Quick Reference

### Get Config Value (Phase 2-3)
```python
# Option 1: Typed config (if available)
ep_cfg = config.execution_position_cfg
sl_pct = ep_cfg.aggregated_oco.sl_pct if ep_cfg else 0.02

# Option 2: Dict fallback (legacy)
sl_pct = config.execution.manage.brackets.aggregated_oco.sl_pct
```

### Load Example Profile
```bash
# Copy safe profile
cp config/examples/execution_position_safe.yaml config/domains/execution.yaml

# Validate
pytest tests/config/test_execution_position_examples.py::test_safe_profile_loads_successfully
```

### Check Validation
```python
from apps.reference.config.execution_position import resolve_execution_position_config
import yaml

with open("config/domains/execution.yaml") as f:
    raw = yaml.safe_load(f)

try:
    ep_cfg = resolve_execution_position_config(raw)
    print("✅ Config valid")
except ValidationError as e:
    print(f"❌ Config invalid: {e}")
```

---

## 📚 Related Documentation

- **Technical Spec:** [`docs/EP_CONFIG_SSOT_REPORT.md`](./EP_CONFIG_SSOT_REPORT.md)
- **User Guide:** [`CONFIG_REFERENCE.md`](../CONFIG_REFERENCE.md)
- **Pydantic Models:** [`apps/reference/domains/execution_position/config.py`](../apps/reference/domains/execution_position/config.py)
- **Resolver:** [`apps/reference/config/execution_position.py`](../apps/reference/config/execution_position.py)
- **Examples:** [`config/examples/`](../config/examples/)
- **Tests:** [`tests/config/test_execution_position_*.py`](../tests/config/)

---

## 🆘 Troubleshooting

### Common Issues

**Q: ValidationError: sl_pct must be > 0**
**A:** Set `sl_pct: 0.015` (minimum 0.001, i.e., 0.1%)

**Q: ValidationError: tp_rr must be in [0.1, 100]**
**A:** Use `tp_rr: 2.0` (typical range: 1.0-5.0)

**Q: Config not loading after editing YAML**
**A:** Restart app or re-run config_loader.load_config()

**Q: Which profile should I use?**
**A:**
- Safe = learning/low volatility
- Moderate = standard production (recommended)
- Aggressive = high conviction/trending markets

---

**Document Version:** 1.0
**Last Updated:** 2025-11-21
**Maintainer:** Agent-2 (EP-CONFIG-DOMAINS-REF-MAP-S4)
