# LEVERAGE_DEFAULTS_REMOVAL_REPORT_v1

**Date:** 2026-05-09
**Track:** config / SSOT / leverage ownership cleanup
**Scope:** LEV-REMOVE-DEFAULTS-2026-05-09
**Verdict:** `FIXED_AND_VALIDATED`

---

## Section 1: Problem Framing

`ExposureConfig.leverage_defaults` (bound to `trading.execution.exposure.leverage_defaults` in `trading.yaml`) was a required Pydantic field (`Field(...)`) with zero runtime consumers. The prior `LEVERAGE-SSOT-FIX-01` migration had already established `instruments.<SYM>.execution.target_leverage` as the sole runtime SSOT for execution-layer leverage. The `leverage_defaults` field remained as a dead schema: Pydantic required it in YAML but no code ever read it, creating false documentation and two OS-registered value conflicts (BTCUSDT: 20 vs 25; DOGEUSDT: 20 vs 10).

This package removes the dead field atomically from both the Pydantic model and the YAML source, with fail-closed evidence (extra='forbid') that the field cannot silently re-appear.

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `ExposureConfig.leverage_defaults: Dict[str, int] = Field(...)` existed as a required field with no default | `config_models.py` line 417 (pre-repair) |
| F-02 | `trading.yaml:trading.execution.exposure.leverage_defaults` declared 6 keys: BTCUSDT=20, ETHUSDT=20, SOLUSDT=20, XRPUSDT=20, DOGEUSDT=20, `__default__`=20 | `config/aurora/trading.yaml` lines 122-128 (pre-repair) |
| F-03 | Zero runtime reads of `leverage_defaults` in `apps/reference/domains/` — grep returned only the model definition site | `grep -r "leverage_defaults" apps/` → 1 hit in `config_models.py` only |
| F-04 | `ExposureGuard.resolve_symbol_leverage()` reads exclusively `instruments.<SYM>.execution.target_leverage` with fail-closed `ConfigContractError` if absent | `exposure_guard.py:resolve_symbol_leverage()` — explicit SSOT annotation |
| F-05 | BTCUSDT instruments value = 25 (vs leverage_defaults = 20); DOGEUSDT instruments value = 10 (vs leverage_defaults = 20) — OS-012, OS-013 | `instruments.yaml` per-symbol execution blocks |
| F-06 | `AuroraExposureConfig = ExposureConfig` — alias; both names appear in public surface manifest | `config_models.py:1758` |
| F-07 | `tests/config/_artifacts/config_models_public_surface.json` pinned `leverage_defaults` in both `AuroraExposureConfig.fields` and `ExposureConfig.fields` | `config_models_public_surface.json` lines 131, 841 (pre-repair) |
| F-08 | `test_toplevel_forbid_enforcement.py` constructed `ExposureConfig(**_valid_exposure_kwargs())` with `leverage_defaults` and asserted `hasattr(config, 'leverage_defaults')` | `test_toplevel_forbid_enforcement.py` lines 87, 236 (pre-repair) |
| F-09 | All other `leverage_defaults` references in tests are MagicMock attribute assignments — they do not construct real `ExposureConfig` and are not structurally broken by field removal | grep of tests/: MagicMock pattern confirmed for ~15 files |
| F-10 | `ExposureConfig` inherits `model_config = ConfigDict(extra='forbid')` — after removal, passing `leverage_defaults` to the constructor raises `ValidationError` (proven by test) | `test_leverage_defaults_removal.py::test_exposure_config_rejects_leverage_defaults_as_unknown_field` |

---

## Section 3: INFERENCES

| # | Inference | Basis |
|---|-----------|-------|
| I-01 | Removing `leverage_defaults` from both model and YAML in the same commit is the only safe atomic operation — removing from model while keeping in YAML triggers `extra='forbid'` startup failure; removing from YAML while keeping model field triggers required-field validation failure | F-01, Pydantic V2 semantics |
| I-02 | The MagicMock-based tests that set `cfg.trading.execution.exposure.leverage_defaults = {...}` are inert dead code — MagicMock auto-creates attributes regardless of the model's field list, so they neither validate the field's existence nor break on its absence | F-09 — confirmed by test suite: 1705 passed after removal, no MagicMock-based test regressed |
| I-03 | The value conflicts (BTCUSDT, DOGEUSDT) are now eliminated as documentation defects: `leverage_defaults` no longer exists; OS-012 and OS-013 entries are resolved by deletion, not value alignment | F-05, F-03 |
| I-04 | `resolve_symbol_leverage` behavior is identical before and after this change because it never accessed `leverage_defaults` | F-04 — confirmed by 3 direct runtime-path regression tests |

---

## Section 4: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No external tooling reads `leverage_defaults` from the config object outside `apps/` or `tests/` |
| A-02 | MagicMock-based tests that still assign `cfg.trading.execution.exposure.leverage_defaults` are acceptable residual dead code — they are benign (tests pass) and cleanup is deferred per no-opportunistic-cleanup constraint |
| A-03 | The `__default__` key in `leverage_defaults` had no fallback dispatch logic anywhere in `apps/` |

---

## Section 5: UNKNOWNS

| # | Unknown | Risk |
|---|---------|------|
| U-01 | Whether ~15 MagicMock-based test files that still assign `leverage_defaults` are ever read by a future code path that switches from MagicMock to real config | LOW — those tests are isolated; any future switch to real config would trigger `extra='forbid'` on construction and surface the dead assignment clearly |
| U-02 | Whether LEV-03 (aurora.yaml per-asset `leverage_cfg.target`) will eventually be unified with `instruments.target_leverage` | OUT OF SCOPE — separate surface, separate seam |

---

## Section 6: Files Changed

| File | Change |
|------|--------|
| `apps/reference/config_models.py` | Removed `leverage_defaults: Dict[str, int] = Field(...)` from `ExposureConfig`; added tombstone comment `LEV-REMOVE-DEFAULTS-2026-05-09` |
| `config/aurora/trading.yaml` | Removed `leverage_defaults:` block (6 keys, lines 122-128 pre-repair) from `trading.execution.exposure`; added tombstone comment at removal site |
| `tests/config/test_toplevel_forbid_enforcement.py` | Removed `"leverage_defaults": {"long": 1, "short": 1}` from `_valid_exposure_kwargs()`; removed `assert hasattr(config, 'leverage_defaults')` from `test_exposure_config_has_all_known_fields`; added tombstone comments |
| `tests/config/_artifacts/config_models_public_surface.json` | Removed `"leverage_defaults"` from `AuroraExposureConfig.fields` and `ExposureConfig.fields` |
| `tests/config/test_leverage_defaults_removal.py` | **NEW** — 9 focused regression tests (see Section 8) |

---

## Section 7: Exact Behavior Changed

### `apps/reference/config_models.py` — `ExposureConfig`

**Before:**
```python
# TASK-ZOMBIE-FIX: Removed positions_stale_ttl_sec (...)
leverage_defaults: Dict[str, int] = Field(...)
count_pending_orders: bool = Field(...)
```

**After:**
```python
# TASK-ZOMBIE-FIX: Removed positions_stale_ttl_sec (...)
# LEV-REMOVE-DEFAULTS-2026-05-09: leverage_defaults removed. SSOT: instruments.yaml -> instruments.<SYM>.execution.target_leverage
count_pending_orders: bool = Field(...)
```

**Runtime effect:** `ExposureConfig` no longer requires or exposes `leverage_defaults`. Passing `leverage_defaults` as a constructor kwarg now raises `ValidationError` (extra='forbid').

### `config/aurora/trading.yaml` — `trading.execution.exposure`

**Before:**
```yaml
      leverage_defaults:
        BTCUSDT: 20
        ETHUSDT: 20
        SOLUSDT: 20
        XRPUSDT: 20
        DOGEUSDT: 20
        __default__: 20
```

**After:**
```yaml
      # LEV-REMOVE-DEFAULTS-2026-05-09: leverage_defaults removed. SSOT: instruments.yaml -> instruments.<SYM>.execution.target_leverage
```

**Runtime effect:** Config loads without `leverage_defaults` in the `exposure` block. Pydantic no longer validates or stores these values.

### `config_models_public_surface.json` — `AuroraExposureConfig` and `ExposureConfig`

**Before:** Both entries listed `"leverage_defaults"` in their `"fields"` arrays.

**After:** `"leverage_defaults"` removed from both. The frozen-surface test (`test_no_pydantic_field_was_removed`) now passes because the artifact and model agree.

### `test_toplevel_forbid_enforcement.py` — `_valid_exposure_kwargs` and assertions

**Before:** `_valid_exposure_kwargs()` included `"leverage_defaults": {"long": 1, "short": 1}`; `test_exposure_config_has_all_known_fields` asserted `hasattr(config, 'leverage_defaults')`.

**After:** Both removed. `ExposureConfig(**_valid_exposure_kwargs())` constructs without `leverage_defaults`. The `hasattr` assertion is replaced with a tombstone comment.

### Runtime leverage resolution — no change

`ExposureGuard.resolve_symbol_leverage()` continues to read exclusively from `instruments.<SYM>.execution.target_leverage`. No code path touched. BTCUSDT=25, DOGEUSDT=10, ETHUSDT/SOLUSDT/XRPUSDT=20.

---

## Section 8: Validation Performed

### Focused regression tests — 9 (all pass)

`tests/config/test_leverage_defaults_removal.py`:

| Test | Proves |
|------|--------|
| `test_exposure_config_has_no_leverage_defaults_field` | `ExposureConfig.model_fields` does not contain `leverage_defaults` |
| `test_aurora_exposure_config_alias_has_no_leverage_defaults_field` | `AuroraExposureConfig` alias also clean |
| `test_exposure_config_rejects_leverage_defaults_as_unknown_field` | extra='forbid' raises ValidationError when leverage_defaults passed to constructor |
| `test_exposure_config_valid_without_leverage_defaults` | ExposureConfig constructs cleanly without the field |
| `test_config_loads_without_leverage_defaults` | Full YAML round-trip loads without error |
| `test_exposure_config_loaded_has_no_leverage_defaults` | Loaded config.trading.execution.exposure has no leverage_defaults in model_fields |
| `test_resolve_symbol_leverage_btcusdt_reads_from_instruments` | BTCUSDT resolves to 25 from instruments.yaml |
| `test_resolve_symbol_leverage_dogeusdt_reads_from_instruments` | DOGEUSDT resolves to 10 from instruments.yaml |
| `test_resolve_symbol_leverage_does_not_use_leverage_defaults` | BTCUSDT != 20 (old defaults value); proves instruments path is sole source |

### Updated tests — all pass

`tests/config/test_toplevel_forbid_enforcement.py`:
- `test_exposure_config_forbid_rejects_unknown_keys_strict` — `_valid_exposure_kwargs()` no longer contains `leverage_defaults`; extra='forbid' test still fires correctly on a genuinely unknown field
- `test_exposure_config_has_all_known_fields` — `leverage_defaults` assertion removed

`tests/config/_artifacts/config_models_public_surface.json` + `test_config_models_public_surface.py`:
- `test_no_pydantic_field_was_removed` — passes: frozen artifact and model agree that `leverage_defaults` does not exist

### Broader suite

```
tests/config/, tests/domains/, tests/integration/, tests/e2e/, tests/units/,
tests/unit/, tests/bootstrap/, tests/vfoundation/, tests/telemetry/, tests/domain_truth/:
5 failed, 1705 passed, 10 skipped
```

The 5 failures are identical to the **pre-existing** failures documented in `EXECUTION_ROOT_REMOVAL_REPORT_v1.md` (Section 9, confirmed by git-stash baseline):
- `test_decision_making_contracts.py::test_current_aurora_config_loads_decision_making_contract` — config value drift (pre-existing)
- `test_execution_position_contracts.py::test_execution_position_extraction_preserves_model_contract` — model field drift (pre-existing)
- `test_fail_closed_config_loading.py::TestFailClosedEventDedup` ×2 — guardian emit_tidy config drift (pre-existing)
- `test_decision_making_composition.py::test_decision_making_uses_constructor_domain_resolver_seam_for_config_spec` — SimpleNamespace attr error (pre-existing)

**Zero new regressions.** Pass count increased from 1696 (EX-REMOVE-ROOT baseline) to 1705 (+9 new tests).

---

## Section 9: Residual Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| ~15 MagicMock-based test files still assign `cfg.trading.execution.exposure.leverage_defaults = {...}` — dead code, not cleaned up | LOW | Benign: MagicMock accepts any attribute; tests pass. Cleanup deferred to avoid scope creep. Future switch to real config will surface the dead assignment via `extra='forbid'` |
| OS-012 (BTCUSDT leverage split) and OS-013 (DOGEUSDT leverage split) ledger entries now refer to a field that no longer exists | INFORMATIONAL | Ledger entries can be marked RESOLVED; the split is eliminated by deletion |
| LEV-03 (aurora.yaml per-asset `leverage_cfg.target`) remains a separate, unaudit-ed leverage surface | OUT OF SCOPE | No consumers cross between LEV-02 and LEV-03 at runtime; separate seam required |

---

## Section 10: Final Verdict

```
FIXED_AND_VALIDATED
```

`leverage_defaults` is removed from `ExposureConfig` (model) and `trading.yaml` (YAML) atomically. The field no longer exists in the Pydantic schema, the YAML source, or the frozen public-surface manifest. `extra='forbid'` ensures that reintroduction via YAML immediately fails startup.

Runtime leverage resolution is unaffected: `ExposureGuard.resolve_symbol_leverage()` continues to read exclusively from `instruments.<SYM>.execution.target_leverage` (proven by 3 direct regression tests). BTCUSDT resolves to 25, DOGEUSDT resolves to 10 — the instruments values, not the now-deleted defaults.

9 focused tests confirm all invariants. Zero new regressions across the 1705-test relevant suite.

**OS-012 (BTCUSDT leverage split) and OS-013 (DOGEUSDT leverage split) are resolved by deletion** — the conflicting surface no longer exists.
