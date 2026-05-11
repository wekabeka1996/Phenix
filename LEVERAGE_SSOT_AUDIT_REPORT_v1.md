# LEVERAGE_SSOT_AUDIT_REPORT_v1

**Date:** 2026-05-09
**Track:** config / SSOT / execution ownership repair
**Scope:** `trading.execution.exposure.leverage_defaults` vs `instruments.<SYM>.execution.target_leverage`
**Verdict:** `READY_FOR_NARROW_IMPLEMENTATION`

---

## Section 1: Problem Framing

Two YAML paths declare leverage for the same trading symbols:

- `config/aurora/trading.yaml` → `trading.execution.exposure.leverage_defaults: {BTCUSDT: 20, ...}` — bound to `ExposureConfig.leverage_defaults` (required Pydantic field)
- `config/aurora/instruments.yaml` → `instruments.<SYM>.execution.target_leverage: <N>` — bound to `InstrumentExecutionConfig.target_leverage`

Values diverge for at least two symbols (BTCUSDT: 25 vs 20; DOGEUSDT: 10 vs 20), per OS-012 and OS-013 in `CONFIG_SURFACE_LEDGER_SEED_v1.md`. The audit determines which surface is the runtime owner, whether the other is dead, and what the safest bounded seam is.

---

## Section 2: Surface Inventory

| surface_id | yaml_path | physical_file | semantic_concept | runtime_consumer | runtime_owner_status | current_status | evidence | recommended_action |
|---|---|---|---|---|---|---|---|---|
| LEV-01 | `trading.execution.exposure.leverage_defaults` | `config/aurora/trading.yaml` lines 122-128 | Per-symbol default leverage fallback | None found in `apps/reference/domains/` | dead_schema | Required Pydantic field (`Field(...)`) with zero runtime reads | grep `leverage_defaults` returns only `config_models.py` definition site; no consumer call sites | Remove from `ExposureConfig` model and from `trading.yaml` atomically |
| LEV-02 | `instruments.<SYM>.execution.target_leverage` | `config/aurora/instruments.yaml` | Per-symbol canonical execution leverage | `leverage_config.py`, `exposure_guard.py`, `position_queries.py`, `position_tracking.py`, `fsm_open.py` | active_single_owner | 5 confirmed runtime consumers; annotated LEVERAGE-SSOT-FIX-01 | Source code reads and grep confirm 5 consumer sites | Preserve as-is; document as sole leverage SSOT |
| LEV-03 | `strategies.aurora.assets.<SYM>.leverage.target` | `config/aurora/aurora.yaml` | Aurora strategy leverage (strategy-local) | `aurora/decision.py` via `_get_instrument_config()` | active_strategy_local | Separate surface; not part of this OS seam | `aurora/handler.py:_get_instrument_config()` returns `config.strategies.aurora.assets[symbol]` | Out of scope; do not touch in this seam |

---

## Section 3: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `leverage_defaults` is declared `Dict[str, int] = Field(...)` (required, no default) in `ExposureConfig` | `config_models.py` — `ExposureConfig` class definition |
| F-02 | `leverage_defaults` values in `trading.yaml`: BTCUSDT=20, ETHUSDT=20, SOLUSDT=20, XRPUSDT=20, DOGEUSDT=20, `__default__`=20 | `config/aurora/trading.yaml` lines 122-128 |
| F-03 | `instruments.target_leverage` values: BTCUSDT=25, ETHUSDT=20, SOLUSDT=20, XRPUSDT=20, DOGEUSDT=10 | `config/aurora/instruments.yaml` per-symbol execution blocks |
| F-04 | Zero runtime consumers of `leverage_defaults` in `apps/reference/domains/` | grep `leverage_defaults` across `apps/` returns only the `config_models.py` definition site |
| F-05 | `leverage_config.py:collect_configs()` annotated `LEVERAGE-SSOT-FIX-01` — prior migration that established `instruments.target_leverage` as SSOT | `apps/reference/domains/execution_position/guards/leverage_config.py` |
| F-06 | `exposure_guard.py:resolve_symbol_leverage()` reads `instruments.<SYM>.execution.target_leverage`; SSOT declared explicitly in method docstring | `apps/reference/domains/execution_position/guards/exposure_guard.py` |
| F-07 | `position_queries.py` line 218: `leverage = int(_field(execution, "target_leverage"))` — reads from per-instrument execution config | `apps/reference/domains/decision_making/primitives/position_queries.py:218` |
| F-08 | `position_tracking.py:_resolve_leverage_for_symbol()` reads from instruments with explicit SSOT comment | `apps/reference/domains/position_tracking/position_tracking.py` |
| F-09 | `fsm_open.py` line 801: `expected_leverage = execution_config.target_leverage` — reads from instrument execution config | `apps/reference/domains/execution_position/flows/open/fsm_open.py:801` |
| F-10 | `aurora/decision.py` reads `leverage_cfg.target` from `_get_instrument_config()` which returns `config.strategies.aurora.assets[symbol]` (aurora.yaml) — a third independent surface | `apps/reference/domains/strategies/runtimes/aurora/decision.py:1619-1621`, `handler.py:_get_instrument_config()` |
| F-11 | BTCUSDT leverage is split: `leverage_defaults`=20 vs `target_leverage`=25 (OS-012) | F-02, F-03 |
| F-12 | DOGEUSDT leverage is split: `leverage_defaults`=20 vs `target_leverage`=10 (OS-013) | F-02, F-03 |
| F-13 | `ExposureConfig` is declared with `extra='forbid'` (inherits from base config model). Removing a required field from the Pydantic model while it remains in YAML causes startup failure. Removing it from YAML while the model field remains required also causes startup failure. Both changes must be made atomically. | Pydantic V2 validation semantics + `config_models.py` base class |

---

## Section 4: INFERENCES

| # | Inference | Basis |
|---|-----------|-------|
| I-01 | `leverage_defaults` is a dead schema: declared as required but never read at runtime | F-04 — zero consumer sites; F-05/F-06 confirm the prior migration already moved ownership to instruments |
| I-02 | `instruments.target_leverage` is the de facto and de jure leverage SSOT for all execution domains | F-05 through F-09 — 5 active consumers, LEVERAGE-SSOT-FIX-01 annotation |
| I-03 | The value divergence (BTCUSDT: 25 vs 20; DOGEUSDT: 10 vs 20) is not a runtime risk today because `leverage_defaults` has zero consumers. The divergence is purely a config hygiene risk (false documentation) | F-04, F-11, F-12 |
| I-04 | The aurora.yaml `leverage_cfg.target` surface (LEV-03) is a separate, strategy-local config surface that coexists with instruments SSOT without conflict — it governs aurora strategy decision-making, not execution layer enforcement | F-10 — different code path, different semantic concept |
| I-05 | The safe implementation seam is atomic: remove `leverage_defaults` field from `ExposureConfig` (model) and remove `leverage_defaults:` block from `trading.yaml` in the same commit. No migration logic needed. No consumer updates needed. | F-13, I-01 — removing dead schema requires only deletion, no rewiring |
| I-06 | `__default__` key in `leverage_defaults` has no consumer either. It was likely intended as a fallback key for unknown symbols. Since no consumer reads `leverage_defaults`, the `__default__` mechanism is also dead. | F-04 |

---

## Section 5: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No external tooling (ops scripts, dashboards, Jupyter notebooks outside `apps/`) reads `leverage_defaults` directly from the config object |
| A-02 | No test fixtures construct `ExposureConfig` or `AuroraConfig` with `leverage_defaults` populated via `model_validate` or `SimpleNamespace` that would break on removal |
| A-03 | `extra='forbid'` enforcement at the `ExposureConfig` level means that if `leverage_defaults` is removed from both model and YAML simultaneously, no other YAML key in the `exposure:` block will accidentally become the new source of a name collision |
| A-04 | The prior `LEVERAGE-SSOT-FIX-01` migration was complete — no legacy `strategies.*.assets.<SYM>.leverage` path still active in the execution domain code |

---

## Section 6: UNKNOWNS

| # | Unknown | Risk |
|---|---------|------|
| U-01 | Whether any test in `tests/` constructs `ExposureConfig` with `leverage_defaults` and asserts on it | LOW — a grep-before-remove step in implementation will surface any such tests |
| U-02 | Whether `aurora/decision.py` `leverage_cfg.target` (LEV-03) will eventually need to be unified with `instruments.target_leverage` (LEV-02) | OUT OF SCOPE — different semantic layer; flag as future OS seam |
| U-03 | Whether `__default__` in `leverage_defaults` was consumed by any now-deleted code that was cleaned up by `LEVERAGE-SSOT-FIX-01` | LOW — the migration comment implies a clean cut; risk is only historical |

---

## Section 7: Concrete Runtime Binding Proof

### BTCUSDT execution leverage — live resolution path

```
AuroraConfig.instruments["BTCUSDT"]
  → InstrumentConfig.execution          (instruments.yaml: instruments.BTCUSDT.execution)
    → InstrumentExecutionConfig.target_leverage = 25

Consumed by:
  leverage_config.py:collect_configs()
    → LeverageConfig(symbol="BTCUSDT", target_leverage=25, ...)
  exposure_guard.py:resolve_symbol_leverage("BTCUSDT")
    → returns 25
  position_queries.py:218
    → leverage = int(_field(execution, "target_leverage"))  → 25
  fsm_open.py:801
    → expected_leverage = execution_config.target_leverage  → 25
  position_tracking.py:_resolve_leverage_for_symbol("BTCUSDT")
    → returns 25

leverage_defaults["BTCUSDT"] = 20
  → NEVER read by any of the above paths
  → OS-012: value mismatch (25 vs 20) is documented but inconsequential to runtime
```

### ETHUSDT execution leverage — live resolution path

```
instruments.ETHUSDT.execution.target_leverage = 20
leverage_defaults["ETHUSDT"] = 20
→ Values happen to agree; no OS entry needed
→ Same 5-consumer path as BTCUSDT; leverage_defaults still dead
```

### SOLUSDT execution leverage — live resolution path

```
instruments.SOLUSDT.execution.target_leverage = 20
leverage_defaults["SOLUSDT"] = 20
→ Values happen to agree
→ Same consumer path; leverage_defaults dead
```

### DOGEUSDT execution leverage — live resolution path

```
instruments.DOGEUSDT.execution.target_leverage = 10
leverage_defaults["DOGEUSDT"] = 20
→ OS-013: value mismatch (10 vs 20)
→ Runtime uses 10 (from instruments); leverage_defaults value of 20 is never applied
```

---

## Section 8: Safe Seam Definition

**Seam ID:** LEV-REMOVE-DEFAULTS-2026-05-09

**Scope (narrow):**
1. Remove `leverage_defaults: Dict[str, int] = Field(...)` from `ExposureConfig` in `config_models.py`
2. Remove `leverage_defaults:` block (6 keys) from `trading.execution.exposure` in `trading.yaml`
3. Grep `tests/` for any reference to `leverage_defaults` — update or remove affected tests
4. Add a tombstone comment at the removal site in `trading.yaml`: `# LEV-REMOVE-DEFAULTS-2026-05-09: leverage_defaults removed. SSOT: instruments.yaml -> instruments.<SYM>.execution.target_leverage`

**Why this is the narrowest safe seam:**
- No consumer rewiring needed (leverage_defaults has zero consumers)
- No migration logic needed (instruments already the sole runtime source)
- Atomic YAML + model removal avoids the Pydantic required-field trap (F-13)
- Does not touch LEV-03 (aurora.yaml per-asset leverage) — separate surface, separate seam

**Out of scope for this seam:**
- LEV-03 (aurora.yaml `leverage_cfg.target`) unification with instruments
- Value reconciliation in instruments.yaml (OS-012, OS-013 values are already the runtime truth; no change needed)
- `__default__` key replacement logic (never consumed; removal is sufficient)

---

## Section 9: Pre-Implementation Checklist

Before implementing LEV-REMOVE-DEFAULTS-2026-05-09:

- [ ] `grep -r "leverage_defaults" tests/` — enumerate test references
- [ ] `grep -r "leverage_defaults" apps/` — confirm zero consumer sites (verify F-04 holds)
- [ ] Confirm `ExposureConfig` field list after removal still satisfies all `extra='forbid'` constraints in `trading.yaml:trading.execution.exposure`
- [ ] Confirm `__default__` key has no special dispatch logic anywhere in `apps/`
- [ ] Run `tests/config/` suite before and after to establish baseline and confirm zero new regressions

---

## Section 10: Residual Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| External tooling reads `leverage_defaults` from config object | LOW | Grep found zero reads in `apps/`; tombstone comment in YAML provides guidance |
| Test constructs `ExposureConfig(leverage_defaults={...})` directly | LOW | Pre-implementation grep will catch; removal is straightforward |
| `__default__` removal breaks a fallback path in deleted/untested code | LOW | No consumer exists; risk is historical only |
| LEV-03 (aurora.yaml leverage) diverges from LEV-02 (instruments) for a symbol | OUT OF SCOPE | Separate surface; flag as future audit item |
| OS-012/OS-013 value conflicts draw attention without resolution | INFORMATIONAL | Conflicts are already documented in ledger; runtime already uses the correct (instruments) value |

---

## Section 11: Final Verdict

```
READY_FOR_NARROW_IMPLEMENTATION
```

**Rationale:**

`trading.execution.exposure.leverage_defaults` is a **dead schema**: required by Pydantic, present in YAML, but consumed by zero runtime code paths. The prior `LEVERAGE-SSOT-FIX-01` migration already established `instruments.<SYM>.execution.target_leverage` as the sole runtime owner, with 5 confirmed active consumers across 5 execution-domain files.

The implementation seam (`LEV-REMOVE-DEFAULTS-2026-05-09`) is narrow and safe:
- **Delete** `ExposureConfig.leverage_defaults` from `config_models.py`
- **Delete** `leverage_defaults:` block from `trading.yaml`
- **Atomic** — both changes in same commit (required-field Pydantic trap, F-13)
- **No consumer rewiring** required
- **No migration logic** required

Value conflicts for BTCUSDT (instruments=25, defaults=20) and DOGEUSDT (instruments=10, defaults=20) are OS-012 and OS-013 documentation items, not runtime risks — the runtime already uses the correct instruments values. Removing `leverage_defaults` eliminates the false documentation without changing any runtime behavior.

**Remaining open OS seams after this package:**
- LEV-03 unification (aurora.yaml per-asset leverage vs instruments) — future audit item
- OS-012, OS-013 ledger entries resolved by this removal (no separate fix needed)
- EX-02 through EX-07 (other OS-005 sub-seams) remain out of scope
