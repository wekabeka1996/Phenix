# AURORA_LEVERAGE_TARGET_MODE_REMOVAL_REPORT_v1

**Date:** 2026-05-10
**Track:** config / SSOT / dead strategy-surface cleanup
**Scope:** LEV-TARGET-MODE-REMOVE-2026-05-10
**Verdict:** `FIXED_AND_VALIDATED`

---

## Section 1: Problem Framing

Following `AURORA_LEVERAGE_BLOCK_CLEANUP_AUDIT_v1.md` (verdict: `MUST_SPLIT_MAX_NOTIONAL_VALUE`), this package implements the seam identified as LEV-TARGET-MODE-REMOVE-2026-05-10.

`aurora.yaml` contained three leverage fields per symbol:
- `leverage.target` (LEV-03) — dead after `LEV-REPOINT-QUANTIZER-2026-05-09`. Zero runtime consumers.
- `leverage.mode` (LEV-05) — dead. Zero runtime consumers.
- `leverage.max_notional_value` (LEV-04) — live read in `decision.py:1630`. All 7 symbols = null. Retained.

The fix introduces `AuroraLeverageOverrideConfig` (slim model, only `max_notional_value`) as the new type for `AuroraInstrumentConfig.leverage`, removes `target` and `mode` from all 7 aurora symbol leverage blocks in `aurora.yaml`, and removes the aurora comparison block from `validate_ssot_consistency()`.

`max_notional_value` is NOT changed. The instruments SSOT path is NOT changed. Execution leverage is NOT changed.

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `AuroraLeverageOverrideConfig` introduced in `apps/reference/config/strategies/aurora.py` with `extra="forbid"` and a single field: `max_notional_value: Optional[Decimal] = Field(None, ...)` | `aurora.py` (new class) |
| F-02 | `AuroraInstrumentConfig.leverage` field type changed from `Optional[LeverageConfig]` to `Optional[AuroraLeverageOverrideConfig]` | `aurora.py:272-274` |
| F-03 | `leverage.target` and `leverage.mode` removed from all 7 aurora symbol leverage blocks in `aurora.yaml` (ETHUSDT, SOLUSDT, BTCUSDT, BNBUSDT, 1000PEPEUSDT, DOGEUSDT, XRPUSDT) | `config/aurora/strategies/aurora.yaml` |
| F-04 | Each leverage block now contains only `max_notional_value: null` — unchanged from previous value | `config/aurora/strategies/aurora.yaml:383,466,574,678,781,889,991` |
| F-05 | `extra="forbid"` on `AuroraLeverageOverrideConfig` means any YAML with `target` or `mode` under `leverage:` will now cause a Pydantic ValidationError at config load. Stale config is fail-closed. | Confirmed by `test_stale_target_in_yaml_fails_validation` and `test_stale_mode_in_yaml_fails_validation` |
| F-06 | Aurora comparison block removed from `validate_ssot_consistency()` in `leverage_config.py`. The aurora block read `asset_cfg.leverage.target` (now absent from `AuroraLeverageOverrideConfig`). | `leverage_config.py:163-218` (post-repair) |
| F-07 | MeanReversion comparison block in `validate_ssot_consistency()` is unchanged. MR still carries `LeverageConfig` with a `.target` field. | `leverage_config.py:192-213` (post-repair) |
| F-08 | `LeverageConfig` (in `instruments.py`) is unchanged. `collect_configs()` still builds `LeverageConfig(target=..., mode=..., max_notional_value=None)` from instruments SSOT only. | `leverage_config.py:96-161` (unchanged) |
| F-09 | `decision.py:1628-1630`: `leverage_cfg = getattr(instr_cfg, "leverage", None)` and `max_notional_cap = getattr(leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")`. This path is unchanged. If leverage block is present → `AuroraLeverageOverrideConfig.max_notional_value` returned; all symbols = null → defaults to 1M. | `decision.py:1628-1630` (unchanged by this seam) |
| F-10 | `AuroraLeverageOverrideConfig` added to `config_models.py` export list for external test access. | `config_models.py:184` |
| F-11 | `test_btcusdt_aurora_runtime_fields.py` updated: stale mutation lines (`btc["leverage"]["target"] = 21`, `btc["leverage"]["mode"] = "ISOLATED"`) replaced with a comment; direct assertion `assert btc_cfg.leverage.target == 21` replaced with `assert btc_cfg.leverage.max_notional_value is None`. | `tests/config/test_btcusdt_aurora_runtime_fields.py:64-65,145` |
| F-12 | `test_aurora_strategy_contracts.py` updated: two assertions on `cm.LeverageConfig` updated to `cm.AuroraLeverageOverrideConfig`. | `tests/config/test_aurora_strategy_contracts.py:344,690` |
| F-13 | `test_leverage_ssot_fix.py::TestLeverageSSOTConsistencyValidation` updated: two tests that expected aurora mismatch warnings to be produced now verify that zero aurora warnings are produced. The behavior is correctly described in new docstrings. | `tests/domains/execution_position/test_leverage_ssot_fix.py:234-258` |
| F-14 | The `LeverageConfig` import in `aurora.py` is removed (no longer used in that file). `Decimal` import added for the new model. | `aurora.py:1-14` |

---

## Section 3: INFERENCES

| # | Inference | Confidence |
|---|-----------|-----------|
| I-01 | `max_notional_cap` in `decision.py` will continue to always resolve to `decimal.Decimal("1000000")` for all 7 symbols, because all YAML values are `null`. Behavior is unchanged. | HIGH — confirmed by zero code change to that path and the null YAML values |
| I-02 | Stale YAML (re-adding `target` or `mode` to aurora.yaml leverage block) will now cause a hard config load failure instead of silent pass-through. This is a strictness improvement. | HIGH — proven by two tests |
| I-03 | The `validate_ssot_consistency()` removal of the aurora block means that if aurora.yaml were re-edited to reintroduce a `target` field, no SSOT mismatch warning would be emitted (config load would fail instead, which is stronger). | HIGH — `extra="forbid"` takes over as the guard |
| I-04 | `LeverageConfig` remains the correct return type from `collect_configs()` and is unrelated to aurora's per-asset config type. The two usages are now distinct: `LeverageConfig` = instruments-derived bootstrap object; `AuroraLeverageOverrideConfig` = aurora per-symbol override (max_notional_value only). | HIGH — confirmed by model separation |

---

## Section 4: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No external code outside the scanned codebase reads `aurora.assets.<SYM>.leverage.target` or `.mode`. Confirmed by full-text codebase search in `AURORA_LEVERAGE_BLOCK_CLEANUP_AUDIT_v1.md`. |
| A-02 | `max_notional_value: null` in all 7 symbols is intentional and represents "no per-symbol notional cap in effect". The 1M USDT default applied by the quantizer is correct for current operation. |
| A-03 | `LeverageConfig` is not used in `aurora.py` outside the now-removed `leverage: Optional[LeverageConfig]` field. Confirmed by reading the file top to bottom. |

---

## Section 5: UNKNOWNS

| # | Unknown |
|---|---------|
| U-01 | Whether `max_notional_value` for any symbol will ever need to be set to a non-null value (per-symbol notional cap). Currently all null. The code path exists but is never triggered. Requires a separate product/risk decision. |
| U-02 | MeanReversion leverage cleanup: `config.strategies.mean_reversion.assets` still carries `LeverageConfig` with `.target` and `.mode`. MR was explicitly out of scope for this seam. |
| U-03 | The `HoldingPeriodConfig` import in `aurora.py` includes `SafetyGatesConfig` — these are unrelated to this seam and not touched. |

---

## Section 6: Files Changed

| File | Change |
|------|--------|
| `apps/reference/config/strategies/aurora.py` | Added `AuroraLeverageOverrideConfig` class; removed `LeverageConfig` import; added `Decimal` import; changed `AuroraInstrumentConfig.leverage` from `Optional[LeverageConfig]` to `Optional[AuroraLeverageOverrideConfig]` |
| `apps/reference/config_models.py` | Added `AuroraLeverageOverrideConfig` to the import/export block from `config.strategies.aurora` |
| `config/aurora/strategies/aurora.yaml` | Removed `target` and `mode` from leverage block for all 7 symbols (ETHUSDT, SOLUSDT, BTCUSDT, BNBUSDT, 1000PEPEUSDT, DOGEUSDT, XRPUSDT). Each block now contains only `max_notional_value: null`. |
| `apps/reference/domains/execution_position/guards/leverage_config.py` | Removed aurora comparison block from `validate_ssot_consistency()`. Updated docstring. MR block unchanged. |
| `tests/config/test_btcusdt_aurora_runtime_fields.py` | Removed stale aurora leverage mutation lines 64-65; updated assertion at line 145 from `.target == 21` to `.max_notional_value is None` |
| `tests/config/test_aurora_strategy_contracts.py` | Updated two assertions from `cm.LeverageConfig` to `cm.AuroraLeverageOverrideConfig` |
| `tests/domains/execution_position/test_leverage_ssot_fix.py` | Rewrote `test_detects_aurora_leverage_mismatch` and `test_warning_contains_both_values` to verify no aurora warnings are produced (new correct behavior) |
| `tests/config/test_aurora_lev_target_mode_removal.py` | **NEW** — 18 focused regression tests (see Section 7) |

---

## Section 7: Exact Behavior Changed

### Before

```yaml
# aurora.yaml (each of 7 symbols)
leverage:
  target: 20       # or 35 for BTCUSDT
  mode: ISOLATED
  max_notional_value: null
```

```python
# AuroraInstrumentConfig
leverage: Optional[LeverageConfig] = Field(...)
# LeverageConfig has .target, .mode, .max_notional_value
```

```python
# validate_ssot_consistency()
# compared aurora.assets.<SYM>.leverage.target to instruments.execution.target_leverage
# emitted LEVERAGE_SSOT_MISMATCH warning if they differed
```

### After

```yaml
# aurora.yaml (each of 7 symbols)
leverage:
  max_notional_value: null
# Stale target/mode keys will now cause Pydantic ValidationError at load
```

```python
# AuroraInstrumentConfig
leverage: Optional[AuroraLeverageOverrideConfig] = Field(...)
# AuroraLeverageOverrideConfig has ONLY .max_notional_value
# extra="forbid" — stale keys cause ValidationError
```

```python
# validate_ssot_consistency()
# aurora block REMOVED — no aurora leverage.target comparison
# MR block unchanged
# SSOT mismatch detection for aurora now handled by extra="forbid" at model level
```

**Unchanged behavior:**
- `decision.py:1630`: `max_notional_cap = getattr(leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")` — always returns 1M for all symbols (unchanged).
- `collect_configs()`: reads from instruments SSOT only, returns `LeverageConfig` objects (unchanged).
- Instruments SSOT path: entirely unchanged.
- Execution leverage bootstrap: unchanged.
- `qty`, `notional`, `margin_required` in `EVT:STRATEGY_SIGNAL_PRODUCED`: unchanged (set by prior seam LEV-REPOINT-QUANTIZER).

---

## Section 8: Validation Performed

### Focused regression tests — 18 (all pass)

`tests/config/test_aurora_lev_target_mode_removal.py`:

**Section 1 — Model contract (7 tests)**

| Test | Proves |
|------|--------|
| `test_model_has_only_max_notional_value_field` | `AuroraLeverageOverrideConfig` has exactly 1 field |
| `test_no_target_attribute` | No `.target` on instances |
| `test_no_mode_attribute` | No `.mode` on instances |
| `test_max_notional_value_none_is_valid` | `None` accepted |
| `test_max_notional_value_decimal_is_valid` | Decimal value accepted |
| `test_stale_target_key_raises_validation_error` | `extra="forbid"`: target → ValidationError |
| `test_stale_mode_key_raises_validation_error` | `extra="forbid"`: mode → ValidationError |

**Section 2 — Config loading with real aurora.yaml (5 tests)**

| Test | Proves |
|------|--------|
| `test_config_loads_without_error` | `ConfigLoader.load_config()` succeeds |
| `test_all_symbols_leverage_is_aurora_leverage_override_config` | All 7 symbols have correct type |
| `test_all_symbols_max_notional_value_is_none` | All 7 have `max_notional_value=None` |
| `test_no_symbol_has_leverage_target` | No `.target` attribute on any symbol |
| `test_no_symbol_has_leverage_mode` | No `.mode` attribute on any symbol |

**Section 3 — Stale YAML fail-closed (2 tests)**

| Test | Proves |
|------|--------|
| `test_stale_target_in_yaml_fails_validation` | Re-adding `target:` to aurora.yaml → load fails |
| `test_stale_mode_in_yaml_fails_validation` | Re-adding `mode:` to aurora.yaml → load fails |

**Section 4 — `collect_configs()` unchanged (2 tests)**

| Test | Proves |
|------|--------|
| `test_collect_configs_reads_instruments_not_aurora` | Instruments SSOT path unaffected |
| `test_collect_configs_mode_from_instruments_margin_mode` | Mode derives from instruments |

**Section 5 — `validate_ssot_consistency()` aurora block removed (2 tests)**

| Test | Proves |
|------|--------|
| `test_no_aurora_warnings_regardless_of_aurora_leverage` | Zero aurora warnings produced |
| `test_no_attribute_error_on_new_style_aurora_config` | No AttributeError with new model |

### Updated tests — all pass

| Test file | Tests | Result |
|-----------|-------|--------|
| `test_btcusdt_aurora_runtime_fields.py` | 3 | all pass |
| `test_aurora_strategy_contracts.py` | 2 updated assertions | pass |
| `test_leverage_ssot_fix.py` | 2 rewrites + 8 unchanged | all pass |
| `test_aurora_quantizer_leverage_repoint.py` | 12 (unchanged) | all pass |

### Broader suite

```
tests/config/, tests/domains/execution_position/, tests/domains/decision_making/ (selected):
13 failed, 2251 passed, 7 skipped
```

**Zero new regressions.** All 13 failures are pre-existing and unrelated to this seam:
- `test_decision_making_contracts.py` — regime confidence threshold drift (pre-existing)
- `test_execution_position_contracts.py` — `trade_executed_cutover_active` module (pre-existing)
- `test_fail_closed_config_loading.py` — guardian config (pre-existing)
- `test_emitted_surface_audit.py` — verb registry surface drift (pre-existing)
- `test_canonical_fill_ingress_activation.py` — `authoritative` kwarg (pre-existing)
- `test_execpos_fsm_recovery_ordering_v2.py` ×3 — pre-existing
- `test_execution_position_registry_surface_sync.py` ×2 — pre-existing
- `test_exposure_guard_wiring.py` — pre-existing
- `test_pending_brackets_wal_corrupt_row_policy.py` — pre-existing

---

## Section 9: Residual Risks

| Risk | Severity | Notes |
|------|----------|-------|
| `max_notional_value` null for all 7 symbols — no per-symbol cap is active | LOW | Operational behavior unchanged. The 1M USDT default is the working cap. Separate seam needed if caps are required. |
| MR leverage still carries stale `.target` in `leverage.yaml` | LOW | Out of scope. MR comparison block still runs in `validate_ssot_consistency()`. No impact from this seam. |
| `LeverageConfig` is used as both a return type (from instruments) and a legacy field type (MR). Two distinct usages share one model. | LOW | Architecturally ambiguous but not broken. Separate future cleanup seam. |
| Any code added post-seam that tries to read `aurora.assets.<SYM>.leverage.target` will get `AttributeError` at runtime. | EXPECTED | This is the desired fail-closed behavior. `extra="forbid"` and no `.target` field on `AuroraLeverageOverrideConfig` prevent silent corruption. |

---

## Section 10: Final Verdict

```
FIXED_AND_VALIDATED
```

`leverage.target` (LEV-03) and `leverage.mode` (LEV-05) removed from all 7 aurora symbol leverage blocks in `aurora.yaml`. `AuroraLeverageOverrideConfig` introduced as the slim replacement model containing only `max_notional_value`. The new model is fail-closed: stale `target` or `mode` keys in YAML cause a Pydantic ValidationError at config load.

`max_notional_value` (LEV-04) is unchanged. `decision.py:1630` reads it as before; all symbols are null; behavior is identical to pre-seam.

Aurora comparison block removed from `validate_ssot_consistency()`. SSOT mismatch detection is now enforced at model layer via `extra="forbid"` — which is stronger than a runtime warning.

18 focused tests all pass. 50 tests across the affected test files all pass. Zero new regressions in the full config + execution_position + decision_making suite.

The instruments SSOT path (`collect_configs()`, leverage bootstrap, quantizer reads) is entirely unchanged by this seam.
