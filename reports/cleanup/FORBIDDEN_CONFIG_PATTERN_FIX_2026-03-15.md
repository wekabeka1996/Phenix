# Forbidden Config Access Pattern Fix

**Date:** 2026-03-15
**Package:** FORBIDDEN-CONFIG-PATTERN-FIX
**Status:** COMPLETE

---

## 1. Executive Verdict

Eliminated all 4 `.get()` silent-fallback patterns in `mean_reversion_strategy.py` by introducing two typed dataclasses (`SqueezeExpansionVetoConfig`, `MomentumSeparationVetoConfig`) and converting all call sites from raw `Dict[str, Any]` to typed attribute access. The pre-existing failing test `test_no_forbidden_config_get_patterns` now passes.

**Before:** 4 `.get("key", [])` patterns — silent fallback on missing keys, bypasses fail-loud policy.
**After:** 0 `.get()` patterns. All veto config access is typed attribute access. Missing fields crash at construction time.

---

## 2. Root Cause

`MRStrategyConfig` declared veto fields as:
```python
squeeze_expansion_veto: Optional[Dict[str, Any]] = None
momentum_separation_veto: Optional[Dict[str, Any]] = None
```

Strategy methods accessed these dicts via `.get("regimes", [])` and `.get("sides", [])` — 4 violations total. The project's static scan test (`test_task53_no_silent_fallbacks_scan.py::test_no_forbidden_config_get_patterns`) correctly flagged these as forbidden.

---

## 3. Violations Found (4)

| # | File | Line | Pattern | Method |
|---|------|------|---------|--------|
| 1 | mean_reversion_strategy.py | ~652 | `veto_cfg.get("regimes", [])` | `_squeeze_expansion_veto_reason` |
| 2 | mean_reversion_strategy.py | ~656 | `veto_cfg.get("sides", [])` | `_squeeze_expansion_veto_reason` |
| 3 | mean_reversion_strategy.py | ~710 | `veto_cfg.get("regimes", [])` | `_momentum_separation_veto_reason` |
| 4 | mean_reversion_strategy.py | ~714 | `veto_cfg.get("sides", [])` | `_momentum_separation_veto_reason` |

---

## 4. Changes Applied

| File | Change |
|------|--------|
| `mean_reversion_strategy.py` | Added `SqueezeExpansionVetoConfig` and `MomentumSeparationVetoConfig` dataclasses; changed `MRStrategyConfig` fields from `Optional[Dict[str, Any]]` to typed Optional; rewrote both veto methods to use typed attribute access |
| `strategy_bridge.py` | Added re-exports for `SqueezeExpansionVetoConfig`, `MomentumSeparationVetoConfig` |
| `mean_reversion_handler.py` | Updated `_runtime_squeeze_expansion_veto()` and `_runtime_momentum_separation_veto()` to return typed instances instead of dicts |
| `test_mean_reversion_squeeze_expansion_veto.py` | Changed `_squeeze_veto_config()` from dict to `SqueezeExpansionVetoConfig`; updated type annotations |
| `test_mean_reversion_momentum_slope_separation.py` | Changed `_squeeze_veto_config()` and `_momentum_veto_config()` from dicts to typed instances; updated type annotations |
| `test_mean_reversion_handler_config_wiring.py` | Changed dict-style `["key"]` assertions to typed `.key` attribute access |

---

## 5. Test Results

| Suite | Pass | Fail | Skip | Notes |
|-------|------|------|------|-------|
| Forbidden config scan (6) | 6 | 0 | 0 | **Previously 5 pass, 1 fail** — now clean |
| Squeeze expansion veto tests (6) | 6 | 0 | 0 | All typed, no regressions |
| Momentum separation tests (7) | 7 | 0 | 0 | All typed, no regressions |
| Handler config wiring (2) | 2 | 0 | 0 | Attribute access verified |
| Domain guardrails (89) | 89 | 0 | 3 | Pre-existing env skips |
| Full FE + DM domains (386) | 386 | 0 | 19 | Zero regressions |

---

## 6. Architectural Notes

- The typed dataclasses (`SqueezeExpansionVetoConfig`, `MomentumSeparationVetoConfig`) mirror the existing Pydantic models in `config_models.py` (`MRSqueezeExpansionVetoConfig`, `MRMomentumSeparationVetoConfig`). The Pydantic models handle config validation at load time; the dataclasses serve as the runtime type used by strategy code.
- The `mean_reversion_handler.py` converter functions bridge Pydantic → dataclass with explicit `Decimal()` wrapping for numeric fields.
- No backward-compatibility shims were added — the typed contracts replace the dicts outright.
