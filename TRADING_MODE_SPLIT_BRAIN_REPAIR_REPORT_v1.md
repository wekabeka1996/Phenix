# TRADING_MODE_SPLIT_BRAIN_REPAIR_REPORT_v1

**Date:** 2026-05-09
**Track:** config / SSOT / split-brain repair
**Scope:** OS-004 (trading_mode split-brain)
**Verdict:** `FIXED_AND_VALIDATED`

---

## Section 1: Problem Framing

OS-004 identified that the same business concept (active trading mode) was declared at two structural YAML paths:

- `config/aurora/system.yaml` root: `trading_mode: hybrid_live_data_testnet_exec`
- `config/aurora/trading.yaml` nested: `trading.mode: hybrid_live_data_testnet_exec`

This is a structural split-brain because:
1. Both paths survive `deep_merge` under different namespaces (`trading_mode` at root vs `mode` inside the `trading:` block)
2. `_fail_on_duplicate_paths()` in config_loader.py cannot detect semantic duplicates at structurally different paths
3. An operator who updated one path but not the other would not get an immediate error unless the values diverged to a non-backtest mismatch — and even then, the historical code had a backtest safety override that silently forced `backtest` everywhere instead of failing

A historical mismatch in these two values caused past bootstrap failures (noted in OS-004 risk annotation).

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `system.yaml:trading_mode` is declared at YAML root | `config/aurora/system.yaml` line 2 |
| F-02 | `trading.yaml:trading.mode` is declared inside `trading:` block | `config/aurora/trading.yaml` line 11 (pre-repair) |
| F-03 | `_fail_on_duplicate_paths()` compares leaf paths, not semantic equivalents | `config_loader.py` — the duplicate detector only catches `a.b.c` appearing in two files, not `a.b.c` vs `x.y.z` expressing the same concept |
| F-04 | Pre-repair loader comment says: "system.yaml → root `trading_mode`" as primary, "trading.yaml → `trading.mode`" as secondary | `config_loader.py` lines 1025-1029 (pre-repair) |
| F-05 | Pre-repair loader had bidirectional sync: if only `trading.mode` was set, it propagated to root | `config_loader.py` `elif trade_norm and not root_norm: merged_config["trading_mode"] = trading_mode` |
| F-06 | Pre-repair loader had a backtest override: if either source said `backtest`, force both to `backtest` | `config_loader.py` lines 1041-1051 (pre-repair) |
| F-07 | `AuroraConfig.trading_mode: str = Field(...)` reads from root — required | `config_models.py` line 1146 |
| F-08 | `TradingConfig.mode: str = Field(...)` reads from `trading:` block — required | `config_models.py` line 991 |
| F-09 | `validate_trading_mode_consistency` synced `trading.mode ← trading_mode` silently if they differed | `config_models.py` lines 1268-1278 (pre-repair) |
| F-10 | All direct runtime consumers read `config.trading_mode` (root) | `main.py:442`, `fsm.py:424,2178`, `daily_gate.py:95`, `facade.py:805`, `domain_config.py:284` |
| F-11 | `compute_effective_trading_modes()` reads `trading.mode` first, falls back to `trading_mode` | `trading_modes.py` lines 139-141 |
| F-12 | After Pydantic validation, `cfg.trading_mode == cfg.trading.mode` always held (due to validator) | Pre-repair guarantee via `validate_trading_mode_consistency` |
| F-13 | `MODE_SSOT_RESOLVED` log named "source=system.yaml" when system.yaml had `trading_mode` | `config_loader.py` line 1073 (pre-repair) |

---

## Section 3: INFERENCES

| # | Inference | Basis |
|---|-----------|-------|
| I-01 | Root `system.yaml:trading_mode` is the intended canonical source | F-04, F-13, F-10 — all evidence points to root as primary |
| I-02 | `trading.mode` in trading.yaml was a historical holdover, not an intentional secondary source | F-12 — they were always equal at runtime; the secondary path never diverged in practice |
| I-03 | The bidirectional sync was a defensive band-aid for the split-brain, not a feature | F-05 — if you remove the split-brain, the band-aid is no longer needed |
| I-04 | `compute_effective_trading_modes` reads `trading.mode` first for compatibility with test fixtures using SimpleNamespace | F-11 — test fixtures use `SimpleNamespace(trading=SimpleNamespace(mode=...))` without a root `trading_mode` |
| I-05 | After loader injection, `cfg.trading.mode` will be populated from `trading_mode`, so `compute_effective_trading_modes` still works | I-04 + the loader now always injects `trading.mode = root_mode` before Pydantic |

---

## Section 4: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No runtime code reads `trading.mode` from the raw YAML dict before loader injection (i.e., all reads go through the Pydantic-validated config object) |
| A-02 | Test fixtures using `SimpleNamespace(trading=SimpleNamespace(mode=...))` bypass ConfigLoader and are unaffected by the guard |
| A-03 | No external tooling reads `trading.mode` from trading.yaml directly (e.g., operator scripts, monitoring agents) |

---

## Section 5: UNKNOWNS

| # | Unknown | Risk |
|---|---------|------|
| U-01 | Whether any deployment/ops tooling reads `trading.mode` from trading.yaml for configuration parsing outside the Python process | LOW — confirmed unused by grep across `apps/` |
| U-02 | Whether any future test creates a tmp config with `trading.mode` and expects it to work | LOW — all discovered tests have been updated; guard provides clear error on regression |

---

## Section 6: Canonical Owner Decision

**Canonical: `system.yaml:trading_mode` (root)**

Rationale:
1. All direct runtime consumers read `config.trading_mode` (the root path)
2. The pre-repair loader comment declared system.yaml as the primary source
3. `AuroraConfig.trading_mode: str = Field(...)` is the required root field that Pydantic validates first
4. Consistent with how ops.* was fixed: trading config lives in system.yaml for global controls

**Non-canonical (removed): `trading.yaml:trading.mode`**

---

## Section 7: Files Changed

| File | Change |
|------|--------|
| `config/aurora/trading.yaml` | Removed `mode: hybrid_live_data_testnet_exec` from `trading:` block; replaced with SSOT tombstone comment |
| `apps/reference/config_loader.py` | Replaced MODE-SSOT block: added guard rejecting `trading.mode` in trading.yaml, simplified to one-way injection (root → trading block), removed bidirectional sync and backtest override |
| `apps/reference/config_models.py` | Changed `validate_trading_mode_consistency` from silent sync to fail-closed ValueError |
| `tests/config/test_task28_hybrid_mode_config_contract.py` | Removed line that set `trading["trading"]["mode"]` in test tmp config |
| `tests/config/test_btcusdt_aurora_runtime_fields.py` | Removed lines that set `trading_data["trading"]["mode"]` in test fixture |
| `tests/config/test_task47_config_dedup_and_debug_flags.py` | Removed lines that set `trading["trading"]["mode"]` in two test setups |
| `tests/config/test_trading_mode_ssot.py` | **NEW** — 12 focused tests (see Section 9) |

---

## Section 8: Exact Behavior Changed

### config_loader.py (MODE-SSOT block)

**Before:** Bidirectional sync. Both paths could set the effective mode. Mismatch on non-backtest = HARD FAIL. Mismatch with backtest = silent backtest override. If only trading.yaml had `trading.mode`, it propagated to root.

**After:** Guard-first, one-way injection.
1. If `trading.mode` is present in the merged trading block → `ConfigContractError` immediately (split-brain guard)
2. If `trading_mode` is set at root → inject `trading_block["mode"] = root_mode` so `TradingConfig.mode` can validate
3. If `trading_mode` is absent → no injection; Pydantic fails with "trading_mode required" (fail-closed)
4. Log always says `source=system.yaml`

### config_models.py (`validate_trading_mode_consistency`)

**Before:** If `trading.mode != trading_mode`, silently overwrite `v.mode = info.data['trading_mode']`.

**After:** If `trading.mode != trading_mode`, raise `ValueError(...)`. This cannot trigger in normal operation (loader ensures equality) but catches any direct-construction bypass.

---

## Section 9: Validation Performed

### Focused tests (12 — all pass)

`tests/config/test_trading_mode_ssot.py`:

| Test | Proves |
|------|--------|
| `test_system_yaml_has_root_trading_mode` | Structural: system.yaml has the canonical field |
| `test_trading_yaml_has_no_mode_field` | Structural: trading.yaml has no `mode:` under `trading:` |
| `test_config_loads_with_single_canonical_trading_mode` | Config loads cleanly from single source |
| `test_cfg_trading_mode_injected_into_trading_block` | `cfg.trading.mode == cfg.trading_mode` after load |
| `test_trading_mode_split_brain_rejected_if_trading_yaml_has_mode` | Guard fires on regression (mode added back to trading.yaml) |
| `test_trading_mode_split_brain_rejected_even_when_values_match` | Guard fires even when both values are identical |
| `test_trading_mode_missing_from_system_yaml_fails_closed` | Startup fails if canonical source absent |
| `test_trading_mode_invalid_value_fails_closed` | Pydantic rejects invalid trading_mode strings |
| `test_consistency_validator_fails_on_mismatch_in_direct_construction` | Validator is now fail-closed (not silent sync) |
| `test_valid_trading_modes_load_correctly[testnet]` | All valid mode strings accepted |
| `test_valid_trading_modes_load_correctly[hybrid_live_data_testnet_exec]` | All valid mode strings accepted |
| `test_valid_trading_modes_load_correctly[backtest]` | All valid mode strings accepted |

### Broader suite

```
tests/config/, tests/domains/, tests/bootstrap/, tests/integration/, tests/units/:
5 failed, 1684 passed, 10 skipped
```

The 5 failures are **pre-existing** (confirmed by running identical tests on baseline before any changes):
- `test_decision_making_contracts.py::test_current_aurora_config_loads_decision_making_contract` — config value drift
- `test_execution_position_contracts.py::test_execution_position_extraction_preserves_model_contract` — model field drift
- `test_fail_closed_config_loading.py::TestFailClosedEventDedup` ×2 — pre-existing
- `test_decision_making_composition.py::test_decision_making_uses_constructor_domain_resolver_seam_for_config_spec` — SimpleNamespace attr error

Zero new regressions.

---

## Section 10: Residual Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Tooling that reads `trading.mode` directly from trading.yaml YAML (not via Python config) | LOW | Grep found no such tooling in apps/; tombstone comment in trading.yaml provides clear guidance |
| Future test author adds `trading.mode` to tmp config thinking it's needed | LOW | Guard fires `ConfigContractError` with clear `T-TMODE-SSOT-2026-05-09` message |
| `compute_effective_trading_modes` with a SimpleNamespace that has no `trading_mode` at root and no `trading.mode` | LOW | Falls back to `None` → `_canonicalize_profile(None)` → raises ValueError. Existing behavior unchanged. |
| Backtest safety override removed | LOW | The override was a workaround for the split-brain. With the guard, split-brain is impossible at startup. Backtest mode is set via `system.yaml:trading_mode: backtest` only. |

---

## Section 11: Final Verdict

```
FIXED_AND_VALIDATED
```

OS-004 (HIGH) is resolved. The single canonical source is `system.yaml:trading_mode`. The mirror in `trading.yaml:trading.mode` is removed. A fail-closed guard in the loader prevents silent regression. The Pydantic validator is now fail-closed. 12 dedicated tests confirm correct behavior. 3 additional tests updated to remove stale `trading.mode` injection. Zero pre-existing tests regressed.

**Remaining split-brain surfaces from CONFIG_SURFACE_LEDGER_SEED_v1.md:** OS-005 through OS-014 remain open and out of scope for this package.
