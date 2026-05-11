# OPS_SPLIT_BRAIN_REPAIR_REPORT_v1

**Date:** 2026-05-09
**Track:** config / SSOT / split-brain repair
**Scope:** OS-001, OS-002, OS-003 (ops.panic_killswitch, ops.metrics_url, ops.reports_dir)
**Verdict:** `FIXED_AND_VALIDATED`

---

## Section 1: Problem Statement

Three config surfaces declared the same business concept (`ops.*`) at two different YAML paths:

| Surface ID | File | Path | Role |
|------------|------|------|------|
| OS-001 | `config/aurora/system.yaml` | `ops.panic_killswitch` | NON-CANONICAL MIRROR |
| OS-002 | `config/aurora/system.yaml` | `ops.metrics_url` | NON-CANONICAL MIRROR |
| OS-003 | `config/aurora/system.yaml` | `ops.reports_dir` | NON-CANONICAL MIRROR |
| — | `config/aurora/trading.yaml` | `trading.ops.panic_killswitch` | CANONICAL |
| — | `config/aurora/trading.yaml` | `trading.ops.metrics_url` | CANONICAL |
| — | `config/aurora/trading.yaml` | `trading.ops.reports_dir` | CANONICAL |

**Risk classification of OS-001:** HIGH. The runtime entry gate (`CMD:OPEN`) reads exclusively from `config.trading.ops.panic_killswitch`. A value set in `system.yaml:ops.panic_killswitch` had **zero runtime effect** on the safety gate — a silently inert emergency control. An operator setting the killswitch in the wrong file would believe trading was halted while it continued.

---

## Section 2: Runtime Binding Proof

### 2.1 Canonical consumer (fsm_open.py)

`apps/reference/domains/execution_position/flows/open/fsm_open.py`, line 463:

```python
ops = config.trading.ops
panic = getattr(ops, "panic_killswitch", False)
```

The gate reads from `config.trading.ops`, not `config.ops`. This was also documented in `config/docs/system_passport.md`:

> "Panic killswitch wiring: gate для CMD:OPEN читає config.trading.ops.panic_killswitch, а не config.ops.panic_killswitch"
> "Для гарантованого ефекту на CMD:OPEN встановлювати в trading.yaml → trading.ops.panic_killswitch"

### 2.2 Path divergence mechanism

`ConfigLoader` loads files in order:
1. `system.yaml` → deep_merged to merged config root (`ops:` at root)
2. `trading.yaml` → deep_merged over it (`trading.ops:` nested under `trading:`)

Because the two paths are structurally different (root `ops` vs nested `trading.ops`), `_fail_on_duplicate_paths()` in config_loader.py **cannot detect this split-brain** — it only catches identical leaf paths from two files.

### 2.3 Pydantic model binding (pre-repair)

| Model field | YAML source | Runtime consumer? |
|-------------|-------------|-------------------|
| `AuroraConfig.ops` (required `OpsConfig`) | `system.yaml:ops.*` | NO — only tooling |
| `AuroraConfig.trading.ops` (`Optional[OpsConfig]`) | `trading.yaml:trading.ops.*` | YES — fsm_open.py |

The inert `AuroraConfig.ops` was required by the model, forcing `system.yaml` to always declare the ops block — which locked in the split-brain structurally.

---

## Section 3: Canonical Owner Determination

**Canonical: `trading.yaml → trading.ops.*`**

Evidence:
1. `fsm_open.py:463` reads `config.trading.ops.panic_killswitch`
2. `config/docs/system_passport.md` lines 19 and 183-187 explicitly document this
3. `TradingConfig.ops: Optional[OpsConfig]` was the runtime-connected field
4. The pattern is consistent with the `execution.*` migration where `system.yaml` execution was deprecated in favour of `trading.execution.*`

**Non-canonical (removed): `system.yaml → ops.*`**

---

## Section 4: Changes Made

### 4.1 `config/aurora/system.yaml`

Removed the root `ops:` block (was lines 20-23):

```yaml
# BEFORE (removed):
ops:
  panic_killswitch: false
  metrics_url: http://127.0.0.1:8000/metrics
  reports_dir: reports
```

Replaced with a tombstone comment:

```yaml
# T-OPS-SSOT-2026-05-09: ops block removed. Canonical source: trading.yaml -> trading.ops.*
```

### 4.2 `apps/reference/config_models.py`

**`AuroraConfig.ops` field** — changed from required to Optional with no default:

```python
# BEFORE:
ops: OpsConfig = Field(...)

# AFTER:
# T-OPS-SSOT-2026-05-09: Root ops is now an alias populated by _alias_ops_from_trading_ops.
# Canonical source: trading.yaml -> trading.ops.*  Do NOT add ops to system.yaml.
ops: Optional[OpsConfig] = Field(default=None)
```

**`_alias_ops_from_trading_ops` validator** — added (after `_backcompat_root_execution_alias`):

```python
@model_validator(mode='after')
def _alias_ops_from_trading_ops(self) -> "AuroraConfig":
    """T-OPS-SSOT-2026-05-09: trading.ops is the single canonical ops source.

    Root ops (system.yaml) was removed. If it reappears, fail-closed to prevent
    silent split-brain regression. Canonical source: trading.yaml -> trading.ops.*
    """
    trading_ops = getattr(self.trading, "ops", None)
    if self.ops is not None:
        raise ValueError(
            "ops split-brain detected: ops.* found at config root — "
            "this block was removed from system.yaml (T-OPS-SSOT-2026-05-09). "
            "Canonical source is trading.yaml -> trading.ops.*"
        )
    if trading_ops is None:
        raise ValueError(
            "trading.ops is required: ops config (panic_killswitch, metrics_url, reports_dir) "
            "must be declared in trading.yaml -> trading.ops.*"
        )
    self.ops = trading_ops
    return self
```

**Behavioral guarantees of the validator:**
- If `system.yaml` has root `ops:` (split-brain regression) → `ValueError` at startup
- If `trading.yaml` has no `trading.ops:` (missing canonical source) → `ValueError` at startup
- Normal operation: `cfg.ops is cfg.trading.ops` (exact same object, aliased)

### 4.3 `tests/config/test_ops_contracts.py`

Complete rewrite. 14 tests total (was 9).

**Tests preserved (updated):**
- `test_ops_facade_reexport_is_exact_identity`
- `test_ops_canonical_definition_lives_only_in_extracted_module`
- `test_ops_extraction_preserves_field_contract`
- `test_ops_extraction_preserves_assembly_annotations` — updated: annotation check now uses `_annotation_includes` + `_is_optional_union` for `Optional[OpsConfig]`
- `test_current_aurora_config_loads_ops_contract` — passes unchanged (values still correct via alias)
- `test_ops_runtime_import_smoke`
- `test_panic_killswitch_runtime_gate_still_blocks_new_open_when_enabled`

**Tests removed (stale — tested the non-canonical root path):**
- `test_ops_yaml_contract_fails_closed_on_forbidden_root_extra_field`
- `test_ops_yaml_contract_fails_closed_on_invalid_root_panic_killswitch_type`

**Tests added (new):**
- `test_system_yaml_has_no_root_ops_block` — structural guard: system.yaml must not have `ops:`
- `test_trading_yaml_has_ops_block` — structural guard: trading.yaml must have `trading.ops.*`
- `test_ops_alias_is_same_object_as_trading_ops` — `cfg.ops is cfg.trading.ops`
- `test_ops_split_brain_rejected_when_root_ops_present_in_system_yaml` — validator rejects regression
- `test_ops_missing_trading_ops_fails_closed` — validator rejects missing canonical source
- `test_ops_yaml_contract_fails_closed_on_forbidden_trading_ops_extra_field` — OpsConfig `extra='forbid'` on canonical path
- `test_ops_yaml_contract_fails_closed_on_invalid_trading_ops_panic_killswitch_type` — type validation on canonical path

---

## Section 5: Test Results

```
tests/config/test_ops_contracts.py  14 passed in 6.17s
```

Broader suite (tests/config/, tests/domains/, tests/bootstrap/, tests/contracts/):

```
5 failed, 1672 passed, 10 skipped
```

The 5 failures are **pre-existing** (confirmed by running identical subset on baseline before any changes):
- `test_decision_making_contracts.py::test_current_aurora_config_loads_decision_making_contract` — config value drift, pre-existing
- `test_execution_position_contracts.py::test_execution_position_extraction_preserves_model_contract` — model field drift, pre-existing
- `test_fail_closed_config_loading.py::TestFailClosedEventDedup` (×2) — pre-existing
- `test_decision_making_composition.py::test_decision_making_uses_constructor_domain_resolver_seam_for_config_spec` — SimpleNamespace attr error, pre-existing

Zero regressions introduced.

---

## Section 6: Invariants Preserved

| Invariant | Status |
|-----------|--------|
| `fsm_open.py` reads `config.trading.ops.panic_killswitch` | PRESERVED — no change to runtime consumer |
| `OpsConfig` schema (3 fields: panic_killswitch, metrics_url, reports_dir) | PRESERVED |
| `OpsConfig.extra='forbid'` on canonical path | PRESERVED |
| `AuroraConfig.extra='forbid'` | PRESERVED — root ops now parsed before validator fires |
| Config load fails on malformed ops | PRESERVED — now enforced on canonical path |
| `cfg.ops.panic_killswitch` accessible post-load | PRESERVED — via alias |

---

## Section 7: Regression Guard

The `_alias_ops_from_trading_ops` model validator provides permanent structural protection:

1. **Against adding ops back to system.yaml**: raises `ValueError("ops split-brain detected")` at startup
2. **Against removing ops from trading.yaml**: raises `ValueError("trading.ops is required")` at startup
3. **Against silent drift**: `cfg.ops is cfg.trading.ops` is enforced by the validator; both always identical

---

## Section 8: Ledger Updates

The following surfaces in `CONFIG_SURFACE_LEDGER_SEED_v1.md` are now resolved:

| Surface ID | Previous Classification | New Status |
|------------|------------------------|------------|
| OS-001 | `owner_split` (HIGH) | RESOLVED — canonical: trading.ops; mirror removed; split-brain guard added |
| OS-002 | `owner_split` (LOW) | RESOLVED — same fix |
| OS-003 | `owner_split` (LOW) | RESOLVED — same fix |

---

## Section 9: What Was NOT Touched

Per scope restriction:
- OS-004 (`trading_mode` split) — untouched
- OS-005 (`execution.*` migration) — untouched
- OS-006 through OS-014 — untouched
- `execution.*` in system.yaml — untouched
- `macro_sync` contradiction (OS-010) — untouched
- DOGEUSDT enabled flag (RR-004) — untouched
- Any null stub cleanup — untouched
- Physical sharding — not attempted

---

## Verdict

```
FIXED_AND_VALIDATED
```

OS-001 (HIGH), OS-002 (LOW), OS-003 (LOW) are resolved. The single canonical source is `trading.yaml → trading.ops.*`. The non-canonical mirror in `system.yaml` is removed. A fail-closed model validator prevents silent regression. 14 dedicated tests confirm correct behavior. Zero pre-existing tests regressed.
