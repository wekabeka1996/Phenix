# MR Formula Verification Appendix

## Scope

This appendix reconstructs formulas and trigger inequalities directly from current code.

## 1. Exact formulas found in code

### 1.1 Vector 1: Microstructure Veto

#### TFI EMA

From `MeanReversionHandler._check_microstructure_veto()`:

```
alpha = 2.0 / (tfi_ema_span + 1)

if prev_ema is None:
    smoothed_tfi = tfi_val
else:
    smoothed_tfi = alpha * tfi_val + (1.0 - alpha) * prev_ema
```

#### Adverse flow tests

```
LONG adverse TFI  = smoothed_tfi < -tfi_adverse_threshold
SHORT adverse TFI = smoothed_tfi >  tfi_adverse_threshold
```

#### Optional OBI confirmation

```
LONG adverse OBI  = obi_val < -obi_adverse_threshold
SHORT adverse OBI = obi_val >  obi_adverse_threshold

if obi_confirm_enabled and not is_adverse_obi:
    allow
```

Important consequence:

OBI is confirm-only in code. It never vetoes by itself. It only acts as an additional precondition for blocking when enabled.

#### Wick ratio formulas

```
bar_range = bar_high - bar_low

LONG lower_wick = min(bar_open, bar_close) - bar_low
LONG wick_ratio = lower_wick / bar_range

SHORT upper_wick = bar_high - max(bar_open, bar_close)
SHORT wick_ratio = upper_wick / bar_range
```

#### Price-reaction key selection

```
ret_key = "ret_60s"
if lookback <= 15:
    ret_key = "ret_10s"
elif lookback >= 250:
    ret_key = "ret_300s"
```

#### Rebound and continuation logic

If `recent_ret` is available and numeric:

```
LONG favorable_rebound     = ret_val >= absorption_rebound_threshold
LONG adverse_continuation  = ret_val <= -price_continuation_threshold

SHORT favorable_rebound    = ret_val <= -absorption_rebound_threshold
SHORT adverse_continuation = ret_val >=  price_continuation_threshold
```

#### Final V1 decision topology

```
if has_absorption_wick or has_favorable_rebound:
    allow
elif has_adverse_continuation:
    block as TOXIC_FLOW_CONTINUATION
else:
    block as TOXIC_FLOW_AMBIGUOUS
```

### 1.2 Vector 2: Directional Bias

From `MeanReversionHandler._apply_directional_bias()`:

```
norm_funding = funding_rate / funding_normalization_scale
norm_funding = max(-1.0, min(1.0, norm_funding))

if abs(norm_funding) < funding_deadband:
    norm_funding = 0.0

eff_long = base_long_threshold - norm_funding * funding_shift_magnitude
eff_short = base_short_threshold + norm_funding * funding_shift_magnitude

eff_long = clamp(eff_long, threshold_clamp_min, threshold_clamp_max)
eff_short = clamp(eff_short, threshold_clamp_min, threshold_clamp_max)
```

Where clamp is:

```
clamp(x, lo, hi) = max(lo, min(hi, x))
```

### 1.3 Strategy trigger inequalities

From `MeanReversion1mStrategy._evaluate_signal()`:

```
long_threshold = entry_threshold_long if set else entry_threshold
short_threshold = entry_threshold_short if set else entry_threshold

LONG  triggers when pct_b < long_threshold
SHORT triggers when pct_b > (1 - short_threshold)
```

These inequalities are the decisive geometry. They matter more than the direction of threshold values alone.

## 2. Required numeric examples

Baseline requested by the audit prompt:

```
base_long = 0.10
base_short = 0.10
funding_shift_magnitude = 0.02
```

### 2.1 Positive funding example

Given:

```
norm_funding = +1
```

Then:

```
eff_long  = 0.10 - 1 * 0.02 = 0.08
eff_short = 0.10 + 1 * 0.02 = 0.12
```

Trigger boundaries become:

```
LONG  boundary:  pct_b < 0.08
SHORT boundary:  pct_b > (1 - 0.12) = 0.88
```

Interpretation:

- Baseline LONG boundary was `pct_b < 0.10`.
- New LONG boundary is `pct_b < 0.08`.
- LONG becomes harder because a more extreme oversold condition is required.

- Baseline SHORT boundary was `pct_b > 0.90`.
- New SHORT boundary is `pct_b > 0.88`.
- SHORT becomes easier because a less extreme overbought condition is required.

### 2.2 Negative funding example

Given:

```
norm_funding = -1
```

Then:

```
eff_long  = 0.10 - (-1) * 0.02 = 0.12
eff_short = 0.10 + (-1) * 0.02 = 0.08
```

Trigger boundaries become:

```
LONG  boundary: pct_b < 0.12
SHORT boundary: pct_b > (1 - 0.08) = 0.92
```

Interpretation:

- Baseline LONG boundary was `pct_b < 0.10`.
- New LONG boundary is `pct_b < 0.12`.
- LONG becomes easier.

- Baseline SHORT boundary was `pct_b > 0.90`.
- New SHORT boundary is `pct_b > 0.92`.
- SHORT becomes harder.

## 3. Proof of easier/harder semantics

### 3.1 LONG side

LONG uses:

```
pct_b < long_threshold
```

Therefore:

- lower long threshold = smaller admissible region = harder
- higher long threshold = larger admissible region = easier

### 3.2 SHORT side

SHORT uses:

```
pct_b > (1 - short_threshold)
```

Therefore the actual boundary is not `short_threshold`, but `1 - short_threshold`.

- higher short threshold -> lower boundary -> easier
- lower short threshold -> higher boundary -> harder

This is the source of the semantic confusion in several documents.

## 4. V1 contract fidelity check against expected bivariate logic

### Expected contract from the audit prompt

LONG toxic block should require:

- adverse sell-side flow
- adverse downside continuation or no bounce
- no absorption evidence

SHORT toxic block should require:

- adverse buy-side flow
- adverse upside continuation or no fade
- no absorption evidence

### What current code actually does

If nested `features.price_motion` is available, the code is close to the intended contract:

- adverse TFI establishes directional toxicity candidate
- wick or favorable rebound allows absorption
- adverse continuation blocks
- ambiguous cases block conservatively

### Runtime mismatch

Current FE -> MR command path does not prove nested `features.price_motion` availability.

In the currently inspected repository state:

- FE emits `price_motion` top-level in `EVT:FEATURES_CALCULATED`
- MR caches `cmd.features`
- MR then looks for `features["price_motion"]`

So actual runtime behavior tends to reduce to:

```
adverse TFI
and maybe OBI confirm
and wick absorption if present
else ambiguous block
```

This is still fail-closed, but it is not the full intended bivariate runtime topology.

## 5. Mismatch matrix: prose vs actual math

| Surface | Prose claim | Actual math verdict |
|---|---|---|
| `apps/reference/config_models.py` docstring | Positive funding -> SHORT stricter, LONG easier | Wrong |
| `REPORT_PACK_4_MR_V2_CONTRACTS_CONFIG.md` | Positive funding -> LONG easier, SHORT stricter | Wrong |
| `REPORT_PACK_6_MR_V2_TESTS_VALIDATION.md` | `eff_long=0.08` easier, `eff_short=0.12` stricter | Wrong |
| `config/docs/mean_reversion_state_machine_passport.md` | Positive funding -> LONG harder, SHORT easier | Correct |
| `tests/domains/decision_making/test_mr_directional_bias.py` current docstrings | Positive funding -> LONG harder, SHORT easier | Correct |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` current comment | Positive funding -> LONG harder, SHORT easier | Correct |

## 6. Formula verdict

### Vector 1

The implemented formulas and heuristics are internally coherent, but their runtime data contract is incomplete because price-reaction data is not wired to the handler in the shape the handler expects.

### Vector 2

The implemented formulas are mathematically correct and economically coherent for crowd-fade logic.

The main remaining problem is not formula sign, but stale prose and incomplete runtime evidence around actual dynamic `funding_rate` availability.
