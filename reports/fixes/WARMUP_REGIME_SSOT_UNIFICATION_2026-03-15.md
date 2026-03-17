# WARMUP / REGIME SSOT UNIFICATION — Final (2026-03-16)

## Status: PACKAGE COMPLETE

All fail-open paths closed. Single canonical truth source for regime warmup bars. 24 new tests prove
SSOT alignment and fail-closed behavior across both exception and `None` resolution paths.

---

## 1. Executive Verdict

**YES** — this package unifies required-bars and regime warmup truth into a single canonical source
and closes all handler fail-open paths in both trading and diagnostics paths.

**Before**: Three independent truth layers existed for regime warmup requirements:
1. YAML + Pydantic (correct SSOT)
2. `strategy_compatibility_matrix.py` with silent `getattr(..., 192/14/288)` fallbacks
3. Hardcoded literal `320` in two separate startup files, derived from incorrect math and not connected to any config

**Critical live bug**: Handler fail-open on profile resolution failure. Two independent failure modes:
- `get_active_strategy_profile` raises an exception → `_basis_required = 0` (silent fail-open)
- `get_active_strategy_profile` returns `None` (unknown strategy) → `_basis_required = int(...) if _profile else 0` → silent fail-open via ternary

Both paths were present in all 3 handlers across 4 sites. Gate `if _basis_required and bars_seen < _basis_required` never fires when `_basis_required = 0`.

**After**: One canonical public function `regime_detector_required_bars(config)` in `strategy_compatibility_matrix.py`.
Startup warmup and main.py legacy path both derive from it. All 4 handler fail-open sites replaced with
explicit `READINESS_CONTRACT_UNRESOLVED` block. Matrix config-path failures raise loudly. 24 new tests.

---

## 2. Root Cause Summary

### RC-1: Handler fail-open in trading path (CRITICAL)

**`aurora_decision.py`** (trading path `_process_decision`):
```python
# BEFORE — exception fail-open
except Exception:
    _basis_required = 0   # silent fail-open
# BEFORE — None fail-open (same outcome via ternary)
_basis_required = int(_profile.basis_required_bars) if _profile else 0
```

**`md_amr_handler.py`** (trading path `_on_process_strategy`):
```python
# BEFORE
except Exception:
    pass   # _basis_required stays 0 from line init
_basis_required = int(_profile.basis_required_bars) if _profile else 0
```

Same fail-open in `get_readiness_diagnostics` of both handlers: `ready = True if not _basis_required else ...`

**Impact**: Any transient ImportError, ConfigContractError, ValueError, or `None` return during profile
resolution silently disabled the cold-start gate — strategy traded without readiness enforcement.

### RC-2: Hardcoded 320 (two independent copies)

**`startup_warmup.py`**: `regime_basis_candles=320` — bare literal, incorrect math in comment
("288 + 32" ignores `atr_period`).

**`main.py`**: `_rd_bars_count = 320  # 288 atr_sma_length + 32 buffer` — second independent literal
in legacy backfill path.

Canonical formula: `max(sma_long=192, atr_period=14 + atr_sma_length=288 - 1) = 301`. Both literals
were manually maintained and would silently diverge if `atr_sma_length` changed in YAML.

### RC-3: Silent config-path failure swallowing in matrix

**`strategy_compatibility_matrix.py`**:
```python
sma_long = int(getattr(sma_cfg, "sma_long_period", 192) or 192)
atr_period = int(getattr(vol_cfg, "atr_period", 14) or 14)
atr_sma_length = int(getattr(vol_cfg, "atr_sma_length", 288) or 288)
```
`sma_cfg` and `vol_cfg` could be `None` if config path traversal failed, producing silently wrong bars
requirements using the hardcoded fallback values.

---

## 3. Canonical Contract Design

**Single public function**: `regime_detector_required_bars(config: Any) -> int`

Location: `apps/reference/contracts/strategy_compatibility_matrix.py`

```
formula: max(sma_long_period, atr_period + atr_sma_length - 1)
source:  regime.yaml → models.sma_trend / models.volatility (Pydantic mandatory fields)
guard:   raises ValueError if sma_cfg or vol_cfg is None (fail-closed)
current: max(192, 14+288-1) = 301
```

**Startup import**: `regime_detector_required_bars(config) + config.basis_import_buffer`

`basis_import_buffer` field added to `regime.yaml` (value: 20) and `AuroraConfig` Pydantic model
(`Field(default=20)`). Current startup import: `301 + 20 = 321`.

**Internal alias** `_structural_regime_basis_required_bars = regime_detector_required_bars` preserved
for zero breaking-change rollout.

---

## 4. Files Changed

| File | Change |
|---|---|
| `apps/reference/contracts/strategy_compatibility_matrix.py` | Added `regime_detector_required_bars()` (public); None guard with `ValueError`; `_structural_regime_basis_required_bars` alias; removed dead `96` and `_aurora_basis_required_bars` wrapper |
| `config/aurora/regime.yaml` | Added `basis_import_buffer: 20` |
| `apps/reference/config_models.py` | Added `basis_import_buffer: int = Field(default=20)` to `AuroraConfig` |
| `apps/reference/bootstrap/startup_warmup.py` | Replaced `320` with `regime_detector_required_bars(config) + getattr(config, "basis_import_buffer", 20)` |
| `apps/reference/main.py` | Replaced `_rd_bars_count = 320` with same formula in legacy backfill path |
| `apps/reference/domains/decision_making/aurora_decision.py` | Replaced exception fail-open and `None` ternary with `_readiness_contract_error` + `_emit_strategy_blocked(READINESS_CONTRACT_UNRESOLVED) + return` |
| `apps/reference/domains/decision_making/aurora_handler.py` | Replaced exception fail-open and `None` ternary with fail-closed early return: `ready=False` for all symbols |
| `apps/reference/domains/decision_making/md_amr_handler.py` | Replaced exception fail-open and `None` ternary (trading path + diagnostics) with identical fail-closed pattern |
| `tests/bootstrap/test_warmup_ssot_alignment.py` | 10 new tests |
| `tests/domains/decision_making/test_handler_fail_closed.py` | 14 new tests |

---

## 5. Removed Fallback Layers

| Removed | Location | Risk class |
|---|---|---|
| `except Exception: _basis_required = 0` | `aurora_decision.py` (trading path) | **CRITICAL** |
| `int(_profile.basis_required_bars) if _profile else 0` | `aurora_decision.py` (trading path) | **CRITICAL** |
| `except Exception: pass` + `if _profile else 0` | `md_amr_handler.py` (trading path) | **CRITICAL** |
| `if _basis_required else True` / `None` fail-open | `aurora_handler.py` (diagnostics) | HIGH |
| `if _basis_required else True` / `None` fail-open | `md_amr_handler.py` (diagnostics) | HIGH |
| `regime_basis_candles=320` literal | `startup_warmup.py` | HIGH |
| `_rd_bars_count = 320` literal | `main.py` | HIGH |
| `getattr(sma_cfg, "sma_long_period", 192) or 192` | `strategy_compatibility_matrix.py` | MEDIUM |
| `getattr(vol_cfg, "atr_period", 14) or 14` | `strategy_compatibility_matrix.py` | MEDIUM |
| `getattr(vol_cfg, "atr_sma_length", 288) or 288` | `strategy_compatibility_matrix.py` | MEDIUM |
| Dead `max(96, ...)` floor | `strategy_compatibility_matrix.py` | LOW |
| `_aurora_basis_required_bars` no-op wrapper | `strategy_compatibility_matrix.py` | LOW |

---

## 6. Fail-Closed Hardening

**All 4 handler sites — both failure modes now blocked:**

| Trigger | Before | After |
|---|---|---|
| exception during `get_active_strategy_profile` | `_basis_required = 0`, gate bypassed, signal emitted | `READINESS_CONTRACT_UNRESOLVED:{ExcType}` → block + return |
| `get_active_strategy_profile` returns `None` | `_basis_required = 0` via ternary, gate bypassed | `READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND` → block + return |

**Diagnostics path (aurora_handler + md_amr_handler)**: On exception or `None`:
- Before: `ready = True` for all symbols (fail-open)
- After: immediate return, all symbols `ready=False, bars_required=None, block_reason="READINESS_CONTRACT_UNRESOLVED:..."`

**Matrix config-path**: `regime_detector_required_bars()` raises `ValueError` on `None` sma_cfg or vol_cfg:
- Before: silently used hardcoded numbers (192, 14, 288)
- After: `ValueError("regime.models.sma_trend / regime.models.volatility not found in config ...")`

---

## 7. Tests Added

### `tests/bootstrap/test_warmup_ssot_alignment.py` (10 tests)
- `test_startup_warmup_plan_ge_regime_required` — plan >= canonical minimum
- `test_startup_warmup_plan_equals_canonical_plus_buffer` — exact equality check
- `test_startup_warmup_plan_uses_config_buffer` — buffer=42 reflected in plan
- `test_startup_warmup_plan_adapts_when_sma_long_changes` — large SMA dominates
- `test_regime_detector_required_bars_formula` — 301 = max(192, 301) verified
- `test_regime_detector_required_bars_sma_dominant` — sma=500 > atr formula
- `test_regime_detector_required_bars_raises_if_models_missing` — fail-closed on ValueError
- `test_regime_detector_required_bars_raises_if_volatility_missing` — fail-closed on ValueError
- `test_no_hardcoded_320_in_startup_warmup` — AST drift prevention
- `test_no_hardcoded_320_in_main` — AST drift prevention

### `tests/domains/decision_making/test_handler_fail_closed.py` (14 tests)
- `test_aurora_diagnostics_returns_contract_error_on_resolution_failure`
- `test_aurora_diagnostics_contract_error_includes_exception_type`
- `test_aurora_diagnostics_normal_path_no_false_positive_ready`
- `test_aurora_diagnostics_ready_when_bars_met`
- `test_md_amr_diagnostics_returns_contract_error_on_resolution_failure`
- `test_md_amr_diagnostics_no_false_positive_ready`
- `test_md_amr_trading_gate_blocks_on_contract_resolution_failure`
- `test_aurora_diagnostics_blocks_when_profile_is_none`
- `test_md_amr_diagnostics_blocks_when_profile_is_none`
- `test_no_profile_is_none_fail_open_in_aurora_decision`
- `test_no_profile_is_none_fail_open_in_aurora_handler`
- `test_no_profile_is_none_fail_open_in_md_amr_handler`
- `test_no_fail_open_gate_pattern_in_aurora_handler`
- `test_no_fail_open_gate_pattern_in_md_amr_handler`

**Test results**: 24/24 new package tests passing. Full regression suite: 1552 passed, 0 new failures.

---

## 8. Residual Debt

| Item | Reason deferred |
|---|---|
| `_aurora_required_htf` HTF fallbacks (50/100/200) | Pillar backfill, not regime warmup critical path. `backfill_cfg is None` should raise, but leaving for next hardening pass. |
| md_amr local getattr fallbacks (`channel_window_bars=12`, `atr_window=14`, `atr_stats_window=64`) | md_amr-local strategy config, not regime warmup. These fields may not be in Pydantic types. |
| `test_task28_hybrid_mode_config_contract.py` pre-existing failure | Test sets `system.yaml: hybrid_live_data_testnet_exec` and `trading.yaml.mode: testnet` — now these must match due to MODE_SSOT hard-fail. Test needs update to use matching mode values. Pre-dates this package. |
