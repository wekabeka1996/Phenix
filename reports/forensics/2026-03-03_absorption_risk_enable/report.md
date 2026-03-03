# PKG-ABSORPTION-RISK-FULL — Evidence Report

**Date:** 2026-03-04
**Package:** PKG-ABSORPTION-RISK-FULL
**Branch:** stable_11_11
**Commit candidate:** `PKG-ABSORPTION-RISK-FULL: enable full absorption + optional risk_score wiring`

---

## PHASE 0 — Context Probe Results

### File locations: exact line refs

| Artefact | File | Lines |
|---|---|---|
| `AbsorptionConfig` (FE mode schema) | `apps/reference/config_models.py` | 1824–1861 |
| `FeatureEngineeringDomainConfig` | `apps/reference/config_models.py` | 1890+ |
| `RiskScoreWeightsConfig` | `apps/reference/config_models.py` | 2006–2018 |
| `RiskManagementDomainConfig` | `apps/reference/config_models.py` | 2040–2090 |
| `RiskManagement._calculate_risk_parameters` | `apps/reference/domains/risk_management/risk_management.py` | 211–406 |
| Risk score formula (was) | `risk_management.py` | 325–331 |
| `DEC:STRATEGY_SIGNAL_GATEWAY` risk gate | `apps/reference/domains/decision_making/decision_making.py` | 700–723 |
| `domains.yaml` — `feature_engineering.absorption` | `config/aurora/domains.yaml` | 301–318 |
| `domains.yaml` — `risk_management` | `config/aurora/domains.yaml` | 320–342 |
| Existing proxy tests | `tests/domains/risk_management/test_absorption_toxicity_penalty.py` | all |

### Pre-existing absorption mode

```
feature_engineering.absorption.mode: proxy   # before this package
risk_management: no absorption_penalty_source field  # before this package
```

### `features["absorption"]` path

Emitted by `FeatureEngineeringDomain` → `EVT:FEATURES_CALCULATED.pld.features["absorption"]`
Consumed by `RiskManagement.on_features_calculated` → `_calculate_risk_parameters(features)`.

---

## PHASE 1 — Config Schema Changes

### `apps/reference/config_models.py`

**`RiskScoreWeightsConfig`** — added 1 field:

```python
absorption_feature: float = Field(
    default=0.0, ge=0.0,
    description="Weight for emitted absorption feature in risk score. Default 0.0 (no effect).",
)
```

**`RiskManagementDomainConfig`** — added 3 fields:

```python
absorption_penalty_source: Literal["proxy", "feature", "both"] = Field(
    default="proxy",
    description='Source for absorption penalty term: proxy (default), feature, or both.',
)
absorption_feature_clip_min: float = Field(
    default=0.0, ge=0.0, le=1.0,
    description="Clip min for emitted |absorption| before applying absorption_feature weight.",
)
absorption_feature_clip_max: float = Field(
    default=1.0, ge=0.0, le=1.0,
    description="Clip max for emitted |absorption| before applying absorption_feature weight.",
)
```

**Backward compatibility:** all fields have defaults matching the old behavior (`"proxy"`, `0.0`, `1.0`).
No existing fields were modified. `extra="forbid"` preserved — strict Pydantic.

---

## PHASE 2 — risk_management.py Formula Changes

### Old formula (`risk_management.py:325–331`, before this package)

```
risk_score = delta_price_pct * dw
           + |obi| * ow
           + |tfi| * tw
           + toxicity_term        # proxy only (or 0 if source was no-op)
```

### New formula (additive, source-routed)

```
# Source routing:
# "proxy"  → applied_toxicity=toxicity_term,  applied_feature=0     (UNCHANGED path)
# "feature"→ applied_toxicity=0,              applied_feature=feature_term
# "both"   → applied_toxicity=toxicity_term,  applied_feature=feature_term

feature_term = clamp(|absorption|, clip_min, clip_max) * absorption_feature_weight
             # 0 if use_absorption_penalty=false, weight=0, or absorption missing

risk_score = delta_price_pct * dw
           + |obi| * ow
           + |tfi| * tw
           + applied_toxicity
           + applied_feature
```

### Fail-closed contract

| Condition | Behaviour |
|---|---|
| `absorption` key absent from features | `feature_term=0`, `abs_source` tag gets `+abs_missing` suffix |
| `absorption` unparsable | `_to_dec()` returns `0` (existing helper) → `feature_term=0` |
| `use_absorption_penalty=false` | both `applied_toxicity=0` AND `applied_feature=0` |
| `absorption_feature_weight=0` (default) | `feature_term=0` always — default path identical to old code |
| `absorption_penalty_source="proxy"` (default) | `applied_feature=0` always — identical to old code |

### Explainability

`risk_terms` dict is added to the return value and logged:

```python
risk_terms = {
    "toxicity_term": float(applied_toxicity),
    "absorption_feature_term": float(applied_feature),
    "abs_source": "proxy|feature|both|disabled[+abs_missing]",
}
```

---

## PHASE 3 — Config Activation (testnet/hybrid)

**No overlay mechanism exists in this repo.** Changes apply to all runs (documented).

### `config/aurora/domains.yaml` diff summary

```yaml
# feature_engineering:
-   absorption.mode: proxy
+   absorption.mode: full     # enables real compute path in FeatureEngineering

# risk_management:
+  absorption_penalty_source: feature   # was default "proxy"
+  absorption_feature_clip_min: 0.0
+  absorption_feature_clip_max: 1.0
   risk_score_weights:
+    absorption_feature: 0.2            # conservative start (0.0 = no-op default)
```

Weight impact analysis at `absorption_feature: 0.2`:

```
feature_term_max = clip(1.0, 0, 1) * 0.2 = 0.20
risk_score headroom consumed at max absorption: 0.20 (out of 1.0)
existing proxy_term (source="feature"): now 0.0 (proxy is bypassed)
net absorption contribution ceiling: unchanged at ~0.3-level signal
```

---

## PHASE 4 — Test Results

### New tests (`tests/domains/risk_management/test_absorption_feature_risk.py`)

| Test | Expected | Result |
|---|---|---|
| `test_risk_score_default_proxy_unchanged` | absorption="0.9" does not affect score when source="proxy", absorption_feature_w=0 | PASSED |
| `test_risk_score_feature_only_uses_absorption` | feature_term=0.8×0.3=0.24, toxicity_term=0 | PASSED |
| `test_risk_score_both_adds_terms` | proxy + feature combined | PASSED |
| `test_absorption_missing_fail_closed` | no crash, feature_term=0, "abs_missing" in tag | PASSED |
| `test_config_new_fields_strict_validation` | Pydantic accepts new fields | PASSED |
| `test_config_invalid_source_rejected` | ValidationError on unknown source | PASSED |
| `test_config_loader_accepts_new_keys` | ConfigLoader loads config/aurora cleanly | PASSED |

### Regression: existing proxy tests (`test_absorption_toxicity_penalty.py`)

| Test | Result |
|---|---|
| `test_toxicity_penalty_disabled_is_zero` | PASSED |
| `test_toxicity_penalty_enabled_behavior` | PASSED (fixture pinned to `source="proxy"`) |
| `test_config_validation_requires_cap_when_penalty_enabled` | PASSED |

### Pre-existing failures (NOT introduced by this package)

Confirmed via `git stash` + re-run before changes:

| Test | Failure reason |
|---|---|
| `test_daily_gate_uses_equity_cross_usdt_and_blocks_at_8pct_drawdown` | `disable_daily_loss_limit=True` override active in config |
| `test_risk_management_blocks_trading_when_daily_drawdown_exceeded` | Same override, reaches price-check on empty dict `{}` |
| `test_task47_daily_loss_limit_blocks_by_default_when_no_equity_data` | Same override flag |

---

## PHASE 5 — Validation

### ConfigLoader check (PASSING)

```
$ PYTHONPATH=. python -c "from pathlib import Path; from apps.reference.config_loader import ConfigLoader; ..."
Config OK
absorption_penalty_source=feature
absorption_feature_clip_min=0.0
absorption_feature_clip_max=1.0
absorption_feature_weight=0.2
```

### Sample computed values (unit test assertions, source="feature")

```
features: price=100, delta_price=5.0, obi=0.1, tfi=0.5, absorption="0.8"
  dp_pct   = 0.050  →  0.005
  |obi|    = 0.100  →  0.030
  |tfi|    = 0.500  →  0.150
  toxicity = 0.0    (source="feature" → proxy bypassed)
  feature  = clip(0.8,0,1) × 0.3 = 0.240
  risk_score = 0.425
  risk_terms = {toxicity_term: 0.0, absorption_feature_term: 0.24, abs_source: "feature"}
```

---

## PHASE 6 — Follow-up items

- **Calibrate `max_risk_score` per symbol** via distribution of live risk_score at `absorption_feature=0.2`.
  Risk ceiling is now potentially lower compared to proxy path (proxy term was 0.15 max here; feature term can be up to 0.2).
  Run N≥500 events → percentile distribution → adjust per-symbol override if needed.

- Consider `absorption_penalty_source: both` once proxy and feature paths are calibrated independently.

- No overlay mechanism. If isolation per-environment is needed, add a `config/aurora/testnet.yaml` overlay before escalating this to prod.

---

## Files Changed

| File | Change type |
|---|---|
| `apps/reference/config_models.py` | +4 new fields (2 classes) — additive |
| `apps/reference/domains/risk_management/risk_management.py` | +60 lines — source routing + explainability |
| `config/aurora/domains.yaml` | +7 lines — mode=full, source=feature, clip, weight |
| `tests/domains/risk_management/test_absorption_feature_risk.py` | NEW — 7 tests |
| `tests/domains/risk_management/test_absorption_toxicity_penalty.py` | fixture: pin `source="proxy"` |
