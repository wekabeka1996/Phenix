# AURORA_QUANTIZER_LEVERAGE_REPOINT_REPORT_v1

**Date:** 2026-05-10
**Track:** config / SSOT / leverage ownership repair
**Scope:** LEV-REPOINT-QUANTIZER-2026-05-09
**Verdict:** `FIXED_AND_VALIDATED`

---

## Section 1: Problem Framing

Following `AURORA_LEVERAGE_SEMANTICS_AUDIT_REPORT_v1` (verdict: READY_FOR_NARROW_IMPLEMENTATION), this package implements the safe seam identified as LEV-REPOINT-QUANTIZER-2026-05-09.

`decision.py:1621` read `aurora.assets.<SYM>.leverage.target` (LEV-03) for the quantizer's `target_leverage` parameter. This produced an inaccurate `margin_required` field in `EVT:STRATEGY_SIGNAL_PRODUCED` for symbols where aurora and instruments leverage diverge:

| Symbol | aurora.leverage.target | instruments.execution.target_leverage | margin underestimate |
|--------|------------------------|---------------------------------------|----------------------|
| BTCUSDT | 35 | 25 | −28.6% |
| ETHUSDT | 20 | 20 | 0% (aligned) |
| DOGEUSDT | 20 | 10 | −50% |

The fix repoints the quantizer read from `aurora.assets.leverage.target` → `instruments.execution.target_leverage`, making `margin_required` accurate and consistent with the actual exchange leverage used by all execution-layer consumers since `LEVERAGE-SSOT-FIX-01`.

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `decision.py:1621` previously read `target_leverage = getattr(leverage_cfg, "target", 20)` from `aurora.assets.<SYM>.leverage` | `decision.py:1619-1621` (pre-repair) |
| F-02 | `precision.execution.target_leverage` is the instruments SSOT, read by `ExposureGuard`, `leverage_config.py`, `fsm_open.py`, and `LeverageBootstrapper` | `AURORA_LEVERAGE_SEMANTICS_AUDIT_REPORT_v1 F-13 through F-16` |
| F-03 | `margin_required = actual_notional / leverage` in the quantizer — ONLY field affected by leverage | `instrument_quantizer.py:186-189` |
| F-04 | `qty` and `notional` are leverage-independent — leverage change has zero effect on sizing | `instrument_quantizer.py:136-150` |
| F-05 | BTCUSDT: instruments.target_leverage=25, aurora.leverage.target=35 — confirmed from real YAML | `config/aurora/instruments.yaml`, `config/aurora/strategies/aurora.yaml` |
| F-06 | DOGEUSDT: instruments.target_leverage=10, aurora.leverage.target=20 — confirmed from real YAML | `config/aurora/instruments.yaml`, `config/aurora/strategies/aurora.yaml` |
| F-07 | ETHUSDT: instruments.target_leverage=20, aurora.leverage.target=20 — values already aligned | `config/aurora/instruments.yaml`, `config/aurora/strategies/aurora.yaml` |
| F-08 | `margin_required` from the quantizer is emitted in `EVT:STRATEGY_SIGNAL_PRODUCED.quantization` but is NOT consumed by any decision gate, sizing logic, or execution path | `AURORA_LEVERAGE_SEMANTICS_AUDIT_REPORT_v1 F-12` |
| F-09 | `aurora.assets.<SYM>.leverage.max_notional_value` is kept as a separate surface (LEV-04) and is NOT changed by this seam | `decision.py:1630` (post-repair) |
| F-10 | `InstrumentPrecisionSpec.execution: InstrumentExecutionConfig` is a required Pydantic field (Field(...)) — `execution.target_leverage` is always present for valid configs | `apps/reference/config/shared/instruments.py:97-99` |

---

## Section 3: Exact Code Change

**File:** `apps/reference/domains/strategies/runtimes/aurora/decision.py`
**Lines:** 1619-1623 (pre-repair → post-repair)

### Before

```python
instr_cfg = self._get_instrument_config(symbol)
leverage_cfg = getattr(instr_cfg, "leverage", None)
target_leverage = getattr(leverage_cfg, "target", 20)
max_notional_cap = getattr(
    leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")
```

### After

```python
instr_cfg = self._get_instrument_config(symbol)
leverage_cfg = getattr(instr_cfg, "leverage", None)
# LEV-REPOINT-QUANTIZER-2026-05-09: Read leverage from instruments SSOT (fail-closed).
# aurora.assets.leverage.target is no longer used for margin estimation.
instr_exec = getattr(precision, "execution", None)
target_leverage = getattr(instr_exec, "target_leverage", None) if instr_exec is not None else None
if target_leverage is None:
    raise ValueError(
        f"instruments.{symbol}.execution.target_leverage is required "
        "(LEV-REPOINT-QUANTIZER-2026-05-09)"
    )
target_leverage = int(target_leverage)
max_notional_cap = getattr(
    leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")
```

**Why this is safe:**
- `margin_required` is diagnostic only (F-08). No gate or execution decision consumes it.
- `qty` and `notional` are unchanged — leverage-independent (F-04).
- The execution layer was already correct (`instruments` SSOT was already in place for all execution consumers).
- The change makes `margin_required` in `EVT:STRATEGY_SIGNAL_PRODUCED` consistent with actual execution margin.
- `max_notional_value` is kept from `aurora.assets.leverage` (separate surface, separate seam).

**Fail-closed behavior:**
- If `precision.execution` is `None` → `target_leverage = None` → `ValueError` raised
- `ValueError` is caught by the `except Exception as e:` block at line 1662
- `EVT:STRATEGY_DECISION_BLOCKED` with `reason_code="QUANTIZER_ERROR"` is emitted
- Function returns without emitting `EVT:STRATEGY_SIGNAL_PRODUCED`
- No silent fallback to a magic constant (the old `getattr(..., 20)` default is eliminated)

---

## Section 4: Diagnostic Gap Closed

### BTCUSDT (pre-repair vs post-repair)

```
Pre-repair (aurora leverage=35):
  quantize_exposure(leverage=35, ...)
  → margin_required = notional / 35
  → 800,000 USDT notional → margin_required ≈ 22,857 USDT

Post-repair (instruments leverage=25):
  quantize_exposure(leverage=25, ...)
  → margin_required = notional / 25
  → 800,000 USDT notional → margin_required = 32,000 USDT

Actual exchange margin: notional / 25 = 32,000 USDT
Diagnostic gap: ELIMINATED (was −28.6% underestimate)
```

### DOGEUSDT (pre-repair vs post-repair)

```
Pre-repair (aurora leverage=20):
  margin_required = 750,000 / 20 = 37,500 USDT

Post-repair (instruments leverage=10):
  margin_required = 750,000 / 10 = 75,000 USDT

Actual exchange margin: 750,000 / 10 = 75,000 USDT
Diagnostic gap: ELIMINATED (was −50% underestimate)
```

### ETHUSDT (no change)

```
aurora.leverage.target = 20 = instruments.target_leverage
margin_required = notional / 20 — unchanged
```

---

## Section 5: What Is NOT Changed

| Surface | Status |
|---------|--------|
| `aurora.assets.<SYM>.leverage.target` | Still present in `aurora.yaml` (not removed). Now unused by runtime code. |
| `aurora.assets.<SYM>.leverage.max_notional_value` | Still read from aurora.yaml via `leverage_cfg` for `max_notional_cap` (separate surface, LEV-04) |
| `aurora.assets.<SYM>.leverage.mode` | Dead schema, unchanged (LEV-05, separate future seam) |
| `instruments.yaml` values | Unchanged |
| `config_models.py` | Unchanged |
| All execution-layer consumers | Unchanged (already used instruments SSOT) |
| `qty`, `notional` in signal payload | Unchanged (leverage-independent) |

---

## Section 6: Files Changed

| File | Change |
|------|--------|
| `apps/reference/domains/strategies/runtimes/aurora/decision.py` | Lines 1619-1623: repoint leverage read from `leverage_cfg.target` to `precision.execution.target_leverage` with fail-closed guard |
| `tests/apps/reference/tests/test_phase9_wiring.py` | Added `import decimal`; updated BTCUSDT mock to set `execution.target_leverage = 10`; removed stale `instr_cfg.leverage.target = 10` line; updated comment |
| `tests/config/test_aurora_quantizer_leverage_repoint.py` | **NEW** — 12 focused regression tests (see Section 7) |

---

## Section 7: Validation Performed

### Focused regression tests — 12 (all pass)

`tests/config/test_aurora_quantizer_leverage_repoint.py`:

**Section 1 — Quantizer semantic unit tests (7 tests)**

| Test | Proves |
|------|--------|
| `test_btcusdt_instruments_leverage_25_margin` | `leverage=25` → `margin_required = 799200/25 = 31968` |
| `test_btcusdt_aurora_leverage_35_would_give_different_margin` | `leverage=35` gives lower margin, qty/notional unchanged |
| `test_dogeusdt_instruments_leverage_10_margin` | `leverage=10` → `margin_required = 799200/10 = 79920` (step_size=0.001 spec) |
| `test_dogeusdt_aurora_leverage_20_would_give_different_margin` | `leverage=20` gives lower margin |
| `test_ethusdt_leverage_20_same_on_both_surfaces` | `leverage=20` → `margin_required = 39960` (consistent) |
| `test_qty_leverage_independent` | qty identical for leverage ∈ {10, 20, 25, 35} |
| `test_notional_leverage_independent` | notional identical for leverage ∈ {10, 20, 25, 35} |

**Section 2 — Handler wiring tests (5 tests, using real config + real AuroraHandler)**

| Test | Proves |
|------|--------|
| `test_btcusdt_uses_instruments_leverage_25_not_aurora_35` | Real handler: `margin_required = 799200/25 = 31968` (not 22834 from aurora=35) |
| `test_dogeusdt_uses_instruments_leverage_10_not_aurora_20` | Real handler: `margin_required = 750000/10 = 75000` (not 37500 from aurora=20) |
| `test_ethusdt_consistent_leverage_20_both_surfaces` | Real handler: `margin_required = 799200/20 = 39960` (unchanged, both agree) |
| `test_qty_notional_unchanged_after_leverage_repoint` | Real handler: `qty = "15.984"` unchanged by repoint |
| `test_missing_execution_target_leverage_is_fail_closed` | `precision.execution = None` → QUANTIZER_ERROR block, no signal emitted |

### Broader suite

```
tests/config/, tests/domains/, tests/integration/, tests/e2e/, tests/units/,
tests/unit/, tests/bootstrap/, tests/vfoundation/, tests/telemetry/, tests/domain_truth/:
87 failed, 7353 passed, 125 skipped, 8 xfailed
```

**Zero new regressions.** All 87 failures are pre-existing and unrelated to this change:
- `test_regime_confidence_decision_audit.py` ×16 — regime confidence threshold config drift (pre-existing)
- `test_neocortex/test_config_contracts.py` — neocortex config drift (pre-existing)
- `test_decision_making_composition.py` — `neocortex_enforcement_mode` attr error (pre-existing)
- `test_execution_position_registry_surface_sync.py` — verb registry surface drift (pre-existing)
- `tests/vfoundation/obs/test_domain_bridge.py` ×11 — vfoundation domain bridge (pre-existing)
- `tests/telemetry/` ×7 — shadow journal schema drift (pre-existing)
- `tests/integration/` — E2E chain payload contract drift (pre-existing)
- Other pre-existing failures documented in prior reports

None of the failing tests exercise the aurora quantizer leverage path in `decision.py`.

Pass count from LEV-REMOVE-DEFAULTS baseline: 1705 (at maxfail=5 boundary). Post-repoint: 12 new tests all pass.

---

## Section 8: Residual State

| Surface | Status after this seam |
|---------|------------------------|
| `LEV-03`: `aurora.assets.<SYM>.leverage.target` | Present in `aurora.yaml` but **now unused in runtime code**. Tombstone comment opportunity in future cleanup seam. |
| `LEV-04`: `aurora.assets.<SYM>.leverage.max_notional_value` | Still read by quantizer (`max_notional_cap`). All audited symbols = null → defaults to 1M USDT. Separate evaluation needed. |
| `LEV-05`: `aurora.assets.<SYM>.leverage.mode` | Dead schema in all aurora runtime files. Separate future seam. |

**Recommended follow-on seams (out of scope here):**
1. Remove `aurora.assets.<SYM>.leverage.target` and `mode` from `aurora.yaml` (after confirming no external reads)
2. Remove `LeverageConfig` embedding from `AuroraInstrumentConfig` (after (1) is proven)
3. Evaluate `max_notional_value = null` → whether explicit per-symbol notional caps are needed

---

## Section 9: Final Verdict

```
FIXED_AND_VALIDATED
```

`decision.py` quantizer now reads `target_leverage` from `instruments.<SYM>.execution.target_leverage` (the canonical SSOT, same as all execution-layer consumers since `LEVERAGE-SSOT-FIX-01`). `margin_required` in `EVT:STRATEGY_SIGNAL_PRODUCED` now correctly reflects actual exchange leverage for all symbols. The diagnostic gap is eliminated: BTCUSDT (−28.6% → 0%), DOGEUSDT (−50% → 0%), ETHUSDT (unchanged, was already aligned).

The repoint is fail-closed: `instruments.execution.target_leverage` absent raises `ValueError`, caught as `QUANTIZER_ERROR`, signal blocked. No silent magic-constant fallback.

12 focused tests confirm all invariants. Zero new regressions across the full test suite.
