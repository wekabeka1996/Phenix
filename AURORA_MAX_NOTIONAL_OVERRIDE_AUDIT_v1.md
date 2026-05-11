# AURORA_MAX_NOTIONAL_OVERRIDE_AUDIT_v1

**Date:** 2026-05-10
**Track:** config / SSOT / aurora override cleanup
**Scope:** LEV-MAX-NOTIONAL-AUDIT-2026-05-10
**Mode:** READ-ONLY. No code changes. No YAML changes.
**Verdict:** `BLOCKED_BY_PRODUCT_DECISION`

---

## Section 1: Problem Statement

Following `AURORA_LEVERAGE_TARGET_MODE_REMOVAL_REPORT_v1.md` (verdict: `FIXED_AND_VALIDATED`),
`aurora.assets.<SYM>.leverage.max_notional_value` is the **sole surviving field** in the aurora
leverage block. This audit determines whether it is a justified live override surface or a
dormant/dead surface that should be removed in a later seam.

Accepted facts from the prior truth-base:
- `leverage.target` removed. `leverage.mode` removed.
- `AuroraLeverageOverrideConfig` introduced with `extra="forbid"` and a single field.
- All 7 aurora symbols have `max_notional_value: null`.
- `decision.py` still reads the field (reported as `:1630`, actual current line `:1847`).
- Runtime always resolves to the hardcoded default `decimal.Decimal("1000000")`.

---

## Section 2: Complete Reference Inventory

### 2A — Runtime reads (behavioral)

| Site | File | Line (approx) | Nature |
|------|------|----------------|--------|
| Read site 1 | `apps/reference/domains/strategies/runtimes/aurora/decision.py` | 1847–1858 | Primary: derives `max_notional_cap`, passes to `quantize_exposure()` |

Exact code at read site 1:
```python
leverage_cfg = getattr(instr_cfg, "leverage", None)           # line 1835
# ...
max_notional_cap = getattr(
    leverage_cfg, "max_notional_value", None                   # line 1847
) or decimal.Decimal("1000000")                                # line 1848

q_pos = quantize_exposure(
    exposure=float(getattr(result, "sizing_score", result.score)),
    price=entry_price,
    max_notional=max_notional_cap,                             # line 1854
    leverage=target_leverage,
    spec=spec,
    min_notional_policy="floor",
)
```

The `getattr(leverage_cfg, "max_notional_value", None)` pattern means:
- If `leverage` block is absent entirely → `leverage_cfg = None` → `getattr(None, ...) = None` → fallback to 1M.
- If `leverage_cfg.max_notional_value is None` (all 7 YAML symbols) → falsy → `or` fallback to 1M.
- Only a **non-null, non-zero Decimal** value would short-circuit the default.

### 2B — Model / config definition

| Site | File | Nature |
|------|------|--------|
| Model class | `apps/reference/config/strategies/aurora.py:222–240` | `AuroraLeverageOverrideConfig`, `extra="forbid"`, single field `max_notional_value: Optional[Decimal] = Field(None, ...)` |
| Field on `AuroraInstrumentConfig` | `apps/reference/config/strategies/aurora.py:293–296` | `leverage: Optional[AuroraLeverageOverrideConfig]` |
| `LeverageConfig` (instruments model) | `apps/reference/config/shared/instruments.py:45–47` | Also declares `max_notional_value: Optional[Decimal]` — **different model, different consumer** |
| `leverage_config.py:165` | `apps/reference/domains/execution_position/guards/leverage_config.py` | `max_notional_value=None` hardcoded when building `LeverageConfig` from instruments SSOT — no read from aurora YAML |

**Critical distinction:** `instruments.py:LeverageConfig.max_notional_value` and
`aurora.py:AuroraLeverageOverrideConfig.max_notional_value` are **two separate fields on two
separate models**. The leverage_config.py reference is to the instruments model (always `None`
from `collect_configs()`), not the aurora per-symbol override.

### 2C — YAML values

| Config file | Occurrences | Values |
|-------------|-------------|--------|
| `config/aurora/strategies/aurora.yaml` | 7 (all aurora symbols) | All `null` |
| `config/aurora/strategies/mean_reversion.yaml` | 3 (MR symbols) | All `null` — but MR uses `LeverageConfig`, not `AuroraLeverageOverrideConfig` |

### 2D — Tests

| Test file | Reference type | Nature |
|-----------|---------------|--------|
| `tests/config/test_aurora_lev_target_mode_removal.py` | 7 model contract tests + 5 YAML load tests | Proves field exists, accepts `None`, accepts non-null `Decimal("500000")`, stale keys raise `ValidationError` |
| `tests/config/test_btcusdt_aurora_runtime_fields.py` | `assert btc_cfg.leverage.max_notional_value is None` | Confirms null for BTCUSDT |
| `tests/config/test_aurora_quantizer_leverage_repoint.py` | `instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL` (mock at `Decimal("1000000")`) | Tests that quantizer uses the value from aurora leverage config; explicitly sets it to 1M to verify wiring |
| `tests/apps/reference/tests/test_phase9_wiring.py` | `instr_cfg.leverage.max_notional_value = decimal.Decimal("1000000")` | Phase-9 wiring test mocks the field explicitly at 1M |

### 2E — Reports (non-behavioral, documentation only)

`AURORA_LEVERAGE_SEMANTICS_AUDIT_REPORT_v1.md`, `AURORA_LEVERAGE_BLOCK_CLEANUP_AUDIT_v1.md`,
`AURORA_QUANTIZER_LEVERAGE_REPOINT_REPORT_v1.md`, `AURORA_LEVERAGE_TARGET_MODE_REMOVAL_REPORT_v1.md`.

---

## Section 3: Exact Quantizer Behavior Proof

### 3A — Call chain

```
decision.py:1835   leverage_cfg = getattr(instr_cfg, "leverage", None)
decision.py:1847   max_notional_cap = getattr(leverage_cfg, "max_notional_value", None)
                                      or decimal.Decimal("1000000")          ← always 1M today
decision.py:1850   quantize_exposure(
                       exposure=sizing_score,        ← quadratic kernel output ∈ [-1, +1]
                       price=entry_price,
                       max_notional=max_notional_cap, ← THE FULL-CONVICTION CEILING
                       leverage=target_leverage,
                       spec=spec,
                       min_notional_policy="floor",
                   )

instrument_quantizer.py:133  exposure_abs = min(abs(exposure), exposure_cap)
instrument_quantizer.py:136  notional = _d(exposure_abs) * max_notional
instrument_quantizer.py:139  notional = notional * (Decimal("1") - fee_buffer)
instrument_quantizer.py:149  raw_qty = notional / price
instrument_quantizer.py:150  qty = floor_to_step(raw_qty, spec.step_size)
```

**Role of `max_notional`**: It is the **full-conviction notional ceiling**. At `exposure=1.0`, the
target notional equals `max_notional × (1 - fee_buffer)` ≈ `1_000_000 × 0.999 = 999,000 USDT`.
At `exposure=0.3`, target notional ≈ `299,700 USDT`. The value scales linearly with exposure.

`max_notional` is **not equity-derived**. The quantizer does not validate the result against
account balance. Over-sized orders (if equity is insufficient) are rejected by the exchange, not
by the quantizer. The quantizer's size constraint from this parameter is one-sided: it can only
cap downward (if set below equity × leverage) or be irrelevant (if set above, which is always
the case with the 1M default on small accounts).

Also note: at `min_notional_policy="floor"` (the active call), the quantizer checks:
```python
if max_notional > 0 and floored_notional > max_notional:
    return QuantizedPosition(..., reject_reason=f"MIN_NOTIONAL_FLOOR_EXCEEDS_CAP:...")
```
This means a non-null `max_notional_value` set BELOW the exchange's minimum notional would
cause a `QUANTIZER_REJECT` event for that symbol. This is an active guard path.

### 3B — Current behavior (all symbols null → 1M default)

For all 7 aurora symbols the effective cap is `1,000,000 USDT`. This value is:
1. High enough that it never binds on any realistic testnet account.
2. Hardcoded in `decision.py:1848` — not surfaced to YAML/config.
3. The ONLY mechanism by which an operator can currently set a per-symbol notional ceiling
   below 1M is to set a non-null value in `aurora.yaml`.

---

## Section 4: Quantification — Can Real Notionals Reach the 1M Cap?

### 4A — Formula

```
notional_attempted = exposure_abs × 1_000_000 × 0.999
```

| exposure_abs | notional_attempted |
|---|---|
| 0.10 | ~99,900 USDT |
| 0.25 | ~249,750 USDT |
| 0.50 | ~499,500 USDT |
| 0.75 | ~749,250 USDT |
| 1.00 | ~999,000 USDT |

### 4B — What limits actual size?

The quantizer does **not** perform an equity check. Size is limited by:
1. The `max_notional` cap (always 1M today → never binds).
2. The exchange's own margin/balance rejection if the order exceeds available margin.

So for small accounts (testnet, < 10K USDT equity):
- At 20x leverage: max deployable notional = 200K USDT.
- A quadratic score of 0.3 → notional target ≈ 300K → order is generated by quantizer but
  rejected by the exchange (insufficient balance). The cap never binds.

For large production accounts (100K+ USDT equity):
- At 20x leverage: max deployable notional = 2M USDT.
- The 1M cap WOULD bind for any `exposure_abs > 0.5`, effectively halving max position size.

### 4C — Conclusion

**The 1M cap cannot be reached by the quantizer on current testnet-scale accounts.**
It would only bind on production accounts with equity × leverage > 1M USDT (i.e., equity > ~50K
at 20x). The cap is architecturally real (not dead code) but currently dormant due to account
scale.

---

## Section 5: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `max_notional_value` has exactly one live runtime read site: `decision.py:1847-1848`. | Codebase search: 14 files matched; only one is a behavioral runtime read. |
| F-02 | The read uses `getattr(..., None) or decimal.Decimal("1000000")`. This is robust: absent field, `None` field, and zero all fall back to 1M. | `decision.py:1847-1848` |
| F-03 | All 7 aurora YAML symbols have `max_notional_value: null`. The 1M default is always applied today. | `config/aurora/strategies/aurora.yaml:383,466,574,678,781,889,991` |
| F-04 | `quantize_exposure()` uses `max_notional` as the full-conviction notional ceiling, not as a risk-budget or equity-fraction. | `instrument_quantizer.py:136` |
| F-05 | The quantizer does not perform an equity check. Exchange-level margin rejection is the only downside guard for oversized notionals. | `instrument_quantizer.py` — no equity parameter |
| F-06 | The `MIN_NOTIONAL_FLOOR_EXCEEDS_CAP` reject path in the quantizer references `max_notional`. Setting a per-symbol cap below exchange minimum would generate a `QUANTIZER_REJECT` event. This path is alive but never triggered (cap = 1M >> any exchange minimum). | `instrument_quantizer.py:173-179` |
| F-07 | `AuroraLeverageOverrideConfig.max_notional_value` and `LeverageConfig.max_notional_value` (instruments) are distinct fields on distinct models. The instruments model's field is always populated as `None` by `collect_configs()`. | `leverage_config.py:165`, `instruments.py:45-47` |
| F-08 | `mean_reversion.yaml` declares `max_notional_value: null` under MR leverage blocks, but MR uses `LeverageConfig` not `AuroraLeverageOverrideConfig`. MR runtime reads are out of scope. | `mean_reversion.yaml:120,149,181` |
| F-09 | The 1M USDT default is hardcoded in `decision.py:1848`. It is not configurable via YAML or any current config model field. | `decision.py:1848` |
| F-10 | `AuroraLeverageOverrideConfig` has `extra="forbid"`. The leverage block can only contain `max_notional_value`. Any other key causes `ValidationError` at config load. | `aurora.py:231` |
| F-11 | Test `test_max_notional_value_decimal_is_valid` proves a non-null `Decimal("500000")` is accepted by the model. The mechanism works correctly for non-null values. | `test_aurora_lev_target_mode_removal.py:83-87` |
| F-12 | Tests in `test_aurora_quantizer_leverage_repoint.py` explicitly set `instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL` (`Decimal("1000000")`) to verify the field is read by decision.py and passed to the quantizer. The wiring is tested. | `test_aurora_quantizer_leverage_repoint.py:231,269,310,339,376` |

---

## Section 6: INFERENCES

| # | Inference | Confidence |
|---|-----------|-----------|
| I-01 | The field is **not dead code**: it is the only operator-accessible mechanism to set a per-symbol notional cap below 1M USDT without a code change. If any aurora symbol needed a 50K USDT cap (e.g. DOGEUSDT on a risk-limited testnet), the operator would set `max_notional_value: 50000` in aurora.yaml. | HIGH |
| I-02 | At current testnet account scales, the cap is functionally inert (never binds). The 1M default exceeds any realistic position the account can deploy. | HIGH |
| I-03 | The hardcoded 1M default in `decision.py:1848` should ideally live in config, not code. Currently, no YAML field surfaces this default for operator visibility. | HIGH |
| I-04 | If the system scales to production accounts where equity × leverage > 1M USDT, the 1M default will silently cap full-conviction trades. This is a hidden configuration risk for large accounts. | MEDIUM |
| I-05 | Removing the leverage block from aurora.yaml would not break the quantizer — the `getattr` chain in decision.py already handles `leverage_cfg = None`. The field itself is the guard for robustness. | HIGH (proven by F-02 and F-08 of prior audit) |
| I-06 | The field cannot be classified as `active_override_surface` (all null, no active cap) nor as `metadata_only` (it has a real behavioral effect when non-null). The correct classification is `dormant_but_valid_override`. | HIGH |

---

## Section 7: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | No external system (operator UI, deployment script) reads or modifies `aurora.assets.<SYM>.leverage.max_notional_value` outside the scanned codebase. Supported by the reference inventory (Section 2) finding only test/report references beyond the model and read site. |
| A-02 | The 7 aurora YAML `null` values are intentional — not a data migration gap. The prior audit (F-07 of cleanup audit) explicitly states: "null represents 'no per-symbol notional cap in effect'". |
| A-03 | The absence of an equity check in the quantizer is intentional: the exchange is the backstop for oversized orders. The `max_notional_value` field is a strategy-level cap, not an account-protection mechanism. |

---

## Section 8: UNKNOWNS

| # | Unknown |
|---|---------|
| U-01 | **Product intent**: Is `max_notional_value` a planned risk control that will eventually be populated with per-symbol limits, or was it added as a "just in case" placeholder with no concrete usage plan? This is the central blocking question. |
| U-02 | **Account scale trajectory**: At what account equity level is the system expected to operate? The 1M default is benign for < 50K equity accounts but silently constraining for larger accounts at the same leverage. |
| U-03 | **Default placement**: Should the 1M default live in `decision.py` (code) or in a config field (e.g. `aurora.decision.max_notional_default`)? Currently it is a hardcoded constant invisible to operators. |
| U-04 | **`LeverageConfig.max_notional_value`** (instruments model) is always `None` from `collect_configs()`. If the instruments SSOT ever carries a `leverageBracket` API-derived cap, this model field is the intended landing zone. Whether that path will be wired is unknown. |

---

## Section 9: Field Classification

```
CLASSIFICATION: dormant_but_valid_override
```

**Justification:**

| Criterion | Result |
|-----------|--------|
| Live runtime read site? | YES — `decision.py:1847-1848` passes it to quantizer as the full-conviction ceiling |
| Active behavioral effect today? | NO — all 7 symbols null → always falls back to 1M default → cap never binds |
| Would a non-null value change behavior? | YES — proven by quantizer logic: `notional = exposure_abs × max_notional_value` |
| Is the mechanism architecturally sound? | YES — model is clean (`extra="forbid"`, single field), read path is robust, wiring is tested |
| Can operators use it without code change? | YES — set any `Decimal` value in `aurora.yaml` per symbol |
| Is there a product/risk intention behind it? | UNKNOWN (U-01) |

The field is not `active_override_surface` (nothing configured), not `metadata_only` (has real
quantizer effect when non-null), not `remove_or_repoint` (the mechanism is correct and correctly
placed). It is `dormant_but_valid_override`.

---

## Section 10: Next Seam Recommendation

**Verdict: `BLOCKED_BY_PRODUCT_DECISION`**

The field cannot be removed, moved, or promoted to active status without an explicit
product/risk decision on the following:

> **Decision required**: Should individual aurora symbols have per-symbol notional caps? If yes,
> what are the appropriate values? If no, should the field be removed and the 1M default either
> promoted to a global config field or hardened into a shared risk constant?

### Three viable next seams (ordered by risk, smallest first):

#### Option A — Keep as-is (no seam needed)
- `dormant_but_valid_override` is a stable state.
- Cost: the 1M hardcoded default in `decision.py:1848` remains invisible to operators.
- When to choose: if no production accounts will exceed equity × leverage > 1M USDT in
  the near term, and no per-symbol risk caps are planned.

#### Option B — Promote the 1M default to config (future single-seam)
- Add `aurora.decision.max_notional_default: 1000000` to `aurora.yaml` (or `aurora.yaml` global block).
- Change `decision.py:1848` to read this field instead of the hardcoded constant.
- Keep `max_notional_value: null` in all per-symbol blocks as the "use global default" signal.
- Cost: config surface expands by one field; seam is small and safe.
- When to choose: when account scale grows toward the 1M boundary, to give operators visibility
  into the default before it starts binding.

#### Option C — Remove the leverage block entirely (future seam, requires product sign-off)
- The `getattr` chain is already robust to `leverage_cfg = None` (F-02, F-08 of prior audit).
- The quantizer would receive `max_notional_cap = decimal.Decimal("1000000")` with no config
  read at all.
- Requires: (1) product confirmation that per-symbol notional caps will never be needed via
  this surface; (2) moving the 1M constant to a named config field.
- Cost: loses the per-symbol override mechanism for future operators.
- When to choose: if risk management confirms the global 1M default is permanent policy and no
  per-symbol variation is intended.

### Recommended immediate action

**Do nothing in this seam.** The field is structurally clean after
`LEV-TARGET-MODE-REMOVE-2026-05-10`. The only deficiency is the invisible hardcoded 1M default
in `decision.py:1848`. Open a separate tracking item for Option B and defer it until:
- Account scale approaches equity × leverage > 500K USDT, OR
- A risk manager requests per-symbol notional caps.

---

## Section 11: Summary Table

| Question | Answer |
|----------|--------|
| Is it a live runtime read? | YES |
| Does it affect behavior today? | NO (all null → 1M default always) |
| Can realistic notionals hit the 1M default? | NO at current testnet scale; YES at equity > ~50K production |
| Is removing it safe? | YES (code is already robust to `None`/absence), but eliminates future override surface |
| Is moving it justified? | Not without product input |
| Classification | `dormant_but_valid_override` |
| Verdict | `BLOCKED_BY_PRODUCT_DECISION` |
| Recommended next seam | Keep as-is; open tracking item for config-promoting the 1M default (Option B) |
