# EXECUTION_ROOT_REMOVAL_REPORT_v1

**Date:** 2026-05-09
**Track:** config / SSOT / split-brain repair
**Scope:** OS-005 — EX-REMOVE-ROOT seam
**Verdict:** `FIXED_AND_VALIDATED`

---

## Section 1: Problem Framing

OS-005 identified that the `execution:` config block was declared at two structural YAML paths:

- `config/aurora/system.yaml` root: `execution.*` — the non-canonical mirror
- `config/aurora/trading.yaml` nested: `trading.execution.*` — the canonical source

This is a structural split-brain because:
1. Both paths survived `deep_merge` under different namespaces (`execution` at root vs nested under `trading:`)
2. All 15+ active runtime consumers already read `config.trading.execution.*` — the root path was dead at runtime
3. The `_backcompat_root_execution_alias` model validator was silently assigning `self.execution = self.trading.execution` only when root was None — but root was never None (system.yaml always provided it), so the alias was dead code
4. A future operator who changed only one path (e.g., updated `trading.execution.cooldown_after_close_ms`) would not get an immediate error — the root mirror would silently retain the old value

The audit (`EXECUTION_CONFIG_SPLIT_AUDIT_REPORT_v1.md`) concluded: `MUST_SPLIT_INTO_SMALLER_SEAMS`. The first safe seam is `EX-REMOVE-ROOT`.

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `system.yaml:execution.*` block was present at YAML root (lines 21-84 pre-repair) | `config/aurora/system.yaml` (pre-repair) |
| F-02 | `trading.yaml:trading.execution.*` is declared inside the `trading:` block | `config/aurora/trading.yaml` lines 89-154 |
| F-03 | All 15+ runtime consumers hardcode `config.trading.execution.*` | Audit EX-01..EX-15 classification |
| F-04 | `_backcompat_root_execution_alias` was dead code: root execution was never None so the `if self.execution is None` branch never fired | `config_models.py` line 1292 (pre-repair) |
| F-05 | One consumer used root alias: `event_handlers.py:1147` read `config.execution.allow_trade_with_guardian_tidy_only` | `event_handlers.py` line 1148 (pre-repair) |
| F-06 | `config_resolver.py:_resolve_fsm_periodic_cleanup_enabled` used dual-path: root execution first, then trading.execution fallback | `config_resolver.py` lines 67-109 (pre-repair) |
| F-07 | Guardian migration block created root execution from trading.execution when root.guardian was present | `config_loader.py` lines 1088-1097 (pre-repair) |
| F-08 | `AuroraConfig.execution` was declared `Field(...)` (required), not `Field(default=None)` | `config_models.py` line 1188 (pre-repair) |
| F-09 | Pre-repair `_validate_order_guardian_surface_conflicts` compared root and trading execution order_guardian; now a no-op since root is gone | `config_loader.py` lines 707-738 |

---

## Section 3: INFERENCES

| # | Inference | Basis |
|---|-----------|-------|
| I-01 | `trading.yaml:trading.execution.*` is the intended canonical source | F-03 — all runtime consumers already read the trading path |
| I-02 | `system.yaml:execution.*` was a holdover mirror, not a live config surface | F-04 — alias was dead code; mirror was never divergent in practice |
| I-03 | The `_backcompat_root_execution_alias` needed to be converted from silent assign to fail-closed guard + explicit alias | F-04, F-08 — pattern matches what was done for ops (OS-001) |
| I-04 | The guardian migration block creating root execution was a side effect of the old dual-path design; it must be removed | F-07 — creating root execution from trading.execution was only needed so Pydantic could validate a required root field |
| I-05 | After EX-REMOVE-ROOT, `_validate_order_guardian_surface_conflicts` becomes a no-op (root execution is always None in the raw dict) | F-09 — method returns early when root_guardian is None |

---

## Section 4: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No runtime code reads `execution.*` from the raw YAML dict before Pydantic (all reads go through the validated config object) |
| A-02 | Test fixtures using `SimpleNamespace(execution=...)` bypass ConfigLoader and are unaffected by the loader guard |
| A-03 | No operator tooling reads `system.yaml:execution.*` directly outside the Python process |
| A-04 | The `_validate_order_guardian_surface_conflicts` method being a no-op post-repair is acceptable — the conflict it was guarding against is now structurally impossible |

---

## Section 5: UNKNOWNS

| # | Unknown | Risk |
|---|---------|------|
| U-01 | Whether any deployment/ops tooling reads `execution.*` from system.yaml directly | LOW — grep across `apps/` found no such access |
| U-02 | Whether future tests will construct SimpleNamespace configs with `execution=...` and expect the root alias path | LOW — guard fires on direct construction too; test authors will see clear error |
| U-03 | Whether `_validate_order_guardian_surface_conflicts` being dead code will cause confusion for future maintainers | LOW — method handles None root gracefully (returns early); it can be cleaned up in a later seam |

---

## Section 6: Canonical Owner Decision

**Canonical: `trading.yaml:trading.execution.*`**

Rationale:
1. All 15+ runtime consumers already read `config.trading.execution.*` — the trading path was already the runtime truth
2. The ops SSOT (OS-001) used the same pattern: canonical in trading.yaml, alias at root
3. `_backcompat_root_execution_alias` is now active: `cfg.execution is cfg.trading.execution` (same object)

**Non-canonical (removed): `system.yaml:execution.*`**

---

## Section 7: Files Changed

| File | Change |
|------|--------|
| `config/aurora/system.yaml` | Removed entire `execution:` block (lines 21-84); replaced with EX-REMOVE-ROOT SSOT tombstone comment |
| `apps/reference/config_loader.py` | Added loader guard (fail-closed if root execution dict appears after merge); rewrote guardian migration block to target only trading.execution (not root) |
| `apps/reference/config_models.py` | Changed `execution: Optional[ExecutionConfig] = Field(...)` → `Field(default=None)`; renamed and converted `_backcompat_root_execution_alias` to `_activate_root_execution_alias` (fail-closed split-brain guard + explicit alias) |
| `apps/reference/domains/execution_position/adapters/config_resolver.py` | Removed dual-path logic from `_resolve_fsm_periodic_cleanup_enabled`; reads only `trading.execution.fsm_periodic_cleanup_enabled` |
| `apps/reference/domains/execution_position/orchestration/event_handlers.py` | `entry_tidy_gate_allow`: switched `config.execution` access → `config.trading.execution` (explicit canonical path) |
| `tests/config/test_execution_root_removal.py` | **NEW** — 13 focused tests (see Section 9) |
| `tests/config/test_config_models_cross_validators_inventory.py` | Updated `_backcompat_root_execution_alias` → `_activate_root_execution_alias` in REQUIRED_CROSS_VALIDATORS and docstring |
| `tests/config/test_task28_schema_no_optional_required_trap.py` | Updated 3 tests: `test_guardian_migration_only_allowed_root_mutation` (removed dead system_exec manipulation), `test_order_guardian_surfaces_load_when_non_conflicting` (rewritten for single-source reality), `test_order_guardian_surfaces_fail_when_divergent_at_config_load` (repurposed to test EX-REMOVE-ROOT guard) |

---

## Section 8: Exact Behavior Changed

### config/aurora/system.yaml

**Before:** `execution:` block at root (lines 21-84) with manage, exposure, fallback, order_params, preflight_backoff_ms, allow_trade_with_guardian_tidy_only, order_guardian, fsm_periodic_cleanup_enabled, etc.

**After:** SSOT tombstone comment only: `# EX-REMOVE-ROOT-2026-05-09: execution block removed. Canonical source: trading.yaml -> trading.execution.*`

### config_loader.py (EX-REMOVE-ROOT guard)

**Before:** No guard. System.yaml execution block merged to root, then Pydantic model required it.

**After:** Guard fires immediately after T-TMODE-SSOT block:
1. If `isinstance(merged_config.get("execution"), dict)` → `ConfigContractError("execution.* must not be declared in system.yaml ... EX-REMOVE-ROOT-2026-05-09")`
2. Guard passes → log `EXEC_SSOT_RESOLVED: source=trading.yaml:trading.execution`

### config_loader.py (guardian migration block)

**Before:** If root.guardian present AND root.execution absent → clone trading.execution → `merged_config["execution"] = exec_block` → put guardian in both root execution and trading execution.

**After:** If root.guardian present → only migrate into `trading.execution.order_guardian`; never create root execution; conflict check targets trading.execution.order_guardian only.

### config_models.py (_activate_root_execution_alias)

**Before (`_backcompat_root_execution_alias`):** If `self.execution is None and trading.execution is not None: self.execution = trading.execution` (silent assign, no failure paths). Alias was dead code because root execution was always non-None.

**After (`_activate_root_execution_alias`):**
1. If `self.execution is not None` → `ValueError("execution split-brain detected ... EX-REMOVE-ROOT-2026-05-09")` — fail-closed against regression
2. If `trading.execution is None` → `ValueError("trading.execution is required ...")` — fail-closed against missing canonical
3. Else: `self.execution = trading.execution` — explicit alias

### config_resolver.py (_resolve_fsm_periodic_cleanup_enabled)

**Before:** Dual-path: checked root execution first, fell back to trading.execution. Root path raised `ValueError("execution.fsm_periodic_cleanup_enabled is required when config.execution is present")`.

**After:** Single path: reads only `config.trading.execution.fsm_periodic_cleanup_enabled`. Root path removed entirely.

### event_handlers.py (entry_tidy_gate_allow)

**Before:** `aget(self._fsm.config.execution, "allow_trade_with_guardian_tidy_only", False)` — read from root alias.

**After:** `trading_exec = getattr(self._fsm.config.trading, "execution", None); aget(trading_exec, "allow_trade_with_guardian_tidy_only", False)` — reads from canonical path directly.

**Justification:** The alias makes `config.execution is config.trading.execution`, so both paths are equivalent at runtime. Switching to `config.trading.execution` removes dependence on alias mechanics and makes the canonical access path explicit. This is the narrower safe option.

---

## Section 9: Validation Performed

### Focused tests (13 — all pass)

`tests/config/test_execution_root_removal.py`:

| Test | Proves |
|------|--------|
| `test_system_yaml_has_no_root_execution_block` | Structural: system.yaml has no root execution |
| `test_trading_yaml_has_execution_block` | Structural: trading.yaml has canonical execution block |
| `test_config_loads_from_trading_execution_as_sole_source` | Config loads cleanly from single source |
| `test_cfg_execution_is_same_object_as_trading_execution` | `cfg.execution is cfg.trading.execution` — alias, not copy |
| `test_cfg_execution_fsm_cleanup_flag_matches_trading_execution` | Cleanup flag propagates correctly |
| `test_loader_guard_rejects_root_execution_in_system_yaml` | Guard fires on regression |
| `test_loader_guard_fires_even_when_root_execution_matches_trading_execution` | Guard fires even with identical values |
| `test_trading_execution_missing_fails_closed` | Startup fails if canonical source absent |
| `test_model_validator_rejects_root_execution_in_direct_construction` | Validator is fail-closed (no silent bypass) |
| `test_fsm_periodic_cleanup_enabled_resolves_from_trading_execution` | Resolver reads only trading.execution |
| `test_fsm_cleanup_resolver_uses_only_trading_execution_not_root` | Resolver returns correct value from canonical path |
| `test_entry_tidy_gate_reads_allow_trade_flag_from_trading_execution` | flag=False → gate disabled → entries allowed |
| `test_entry_tidy_gate_allow_trade_flag_enabled_blocks_without_tidy` | flag=True, no tidy event → entry blocked |

### Updated tests (all pass)

`tests/config/test_task28_schema_no_optional_required_trap.py`:
- `test_guardian_migration_only_allowed_root_mutation` — updated: guardian migrates into `trading.execution.order_guardian`, not root; accessed via alias
- `test_order_guardian_surfaces_load_when_non_conflicting` [2 parametrize cases] — rewritten: only trading guardian; `cfg.execution is cfg.trading.execution`
- `test_order_guardian_surfaces_fail_when_divergent_at_config_load` — repurposed: tests EX-REMOVE-ROOT guard fires on root execution regression

`tests/config/test_config_models_cross_validators_inventory.py`:
- Updated `REQUIRED_CROSS_VALIDATORS` to reference `_activate_root_execution_alias`

### Broader suite

```
tests/config/, tests/domains/, tests/bootstrap/, tests/integration/, tests/units/:
5 failed, 1696 passed, 10 skipped
```

The 5 failures are **pre-existing** (confirmed by git stash baseline before any changes):
- `test_decision_making_contracts.py::test_current_aurora_config_loads_decision_making_contract` — config value drift
- `test_execution_position_contracts.py::test_execution_position_extraction_preserves_model_contract` — model field drift
- `test_fail_closed_config_loading.py::TestFailClosedEventDedup` ×2 — pre-existing
- `test_decision_making_composition.py::test_decision_making_uses_constructor_domain_resolver_seam_for_config_spec` — SimpleNamespace attr error

Zero new regressions.

---

## Section 10: Residual Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `_validate_order_guardian_surface_conflicts` is now a no-op (root execution absent → root_guardian is None → early return) | LOW | No behavior change; method returns without error; it can be removed in a later seam if desired |
| `test_order_guardian_surfaces_fail_when_divergent_at_config_load` previously tested root-vs-trading divergence detection — that code path is now dead | LOW | Test repurposed to test EX-REMOVE-ROOT guard; divergence detection dead code is documented in U-03 |
| Operator tooling that reads `system.yaml:execution.*` directly (outside Python process) | LOW | Grep found no such tooling in `apps/`; tombstone comment in system.yaml provides clear guidance |
| Future test author adds root execution to system.yaml thinking it's needed | LOW | Loader guard fires `ConfigContractError` with clear `EX-REMOVE-ROOT-2026-05-09` message |
| `_activate_root_execution_alias` validator ordering relative to `_alias_ops_from_trading_ops` | LOW | Both are `mode='after'` validators; Pydantic runs them in definition order; ops alias runs after execution alias — both are independent and do not interact |

---

## Section 11: What Remains Unproven

The following invariants were **not** exercised by the new tests (noted for completeness, not blocking):

1. **`_validate_order_guardian_surface_conflicts` dead-code path**: No test exercises the case where both root execution and trading execution have different order_guardian values after EX-REMOVE-ROOT — this code path is structurally unreachable (root execution is rejected at loader guard before reaching this validator). The method is dead but harmless.

2. **`allow_trade_with_guardian_tidy_only = True` with a fresh tidy event**: The `test_entry_tidy_gate_allow_trade_flag_enabled_blocks_without_tidy` test proves the blocking case. The allowing case (tidy event within TTL) was not added to minimize test scope — it is orthogonal to the EX-REMOVE-ROOT seam.

3. **Config reload**: The alias pattern (`self.execution = self.trading.execution`) is proven to work at startup. Reload scenarios (if any) are not covered by this seam.

---

## Section 12: Final Verdict

```
FIXED_AND_VALIDATED
```

OS-005 EX-REMOVE-ROOT seam is resolved. The single canonical source is `trading.yaml:trading.execution.*`. The mirror at `system.yaml:execution.*` is removed. A fail-closed loader guard prevents silent regression. The Pydantic alias validator is now active and fail-closed. `config_resolver.py` reads exclusively from `trading.execution`. `event_handlers.py` accesses `config.trading.execution` directly. 13 dedicated tests confirm correct behavior. All relevant existing tests updated with no pre-existing tests regressed.

**Remaining OS-005 sub-seams from EXECUTION_CONFIG_SPLIT_AUDIT_REPORT_v1.md:** EX-02 through EX-07 (individual surface migrations: exposure overlap OS-008, leverage_defaults OS-012/013, order_params OS-009, cooldown/anti_race EX-06, preflight_backoff_ms EX-07) remain open and out of scope for this package.
