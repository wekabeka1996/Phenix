# Forensic Audit: Absorption & Risk Gate
**Date:** 2026-03-03
**Scope:** Aurora/Phenix feature engineering, risk management, and decision making pipelines.

## Executive Summary
This report investigates the end-to-end flow of the `absorption` feature, specifically evaluating its computation, presence in runtime, and impact on signal and risk scoring. 

**Key Findings:**
- The actual `absorption` feature is currently **disabled globally** in the Feature Engineering config and emits a placeholder `0.0`.
- Risk Management computes an "absorption penalty" for its `risk_score`, but it **does not use the emitted absorption feature**. Instead, it computes an internal toxicity proxy based on `tfi` and `delta_price_pct`.
- Both Signal Scoring and Risk Scoring have the capability to be overridden per-symbol, but default to global configurations or zero weights.

---

## A) Is absorption computed? Where? Under what conditions?
**Status: DISABLED (Returns 0.0 placeholder)**

The computation logic resides in `apps/reference/domains/feature_engineering/feature_engineering.py` (lines 1045-1061):
```python
# R2 (P2): ABSORPTION — Experimental (Default OFF)
absorption_mode = self.cfg.absorption_mode
if absorption_mode != "disabled":
    # ... computation using self._engine.update_absorption ...
    absorption_val, _, _ = self._engine.compute_absorption(hot)
    features["absorption"] = str(absorption_val)
else:
    features["absorption"] = str(self.cfg.zero_value)
    hot.absorption_ready = False
    hot.absorption_not_ready_reason = "mode_disabled"
```

**Conditions:**
It is controlled by the config `domains.feature_engineering.absorption.mode`. 
According to `config/aurora/domains.yaml` (line 302):
```yaml
  # R2 (P2): ABSORPTION — Experimental (Default OFF, no live impact)
  absorption:
    mode: disabled              # disabled | proxy | full
```
Because the mode is `disabled`, the engine skips actual computation and assigns the neutral/zero value (`0.0`).

---

## B) Is absorption present in FEATURES payload at runtime? Example payload keys.
**Status: CONFIRMED (As a placeholder)**

Yes, `absorption` is always present in the runtime `EVT:FEATURES_CALCULATED` event payload because it is mandated by the schema.
- **Evidence:** `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json` mandates `"required": ["obi", "tfi", "delta_price", "absorption"]`.
- **Example Payload Key:** `"absorption": "0.0"` (always zero due to disabled mode).

---

## C) Is absorption used in SIGNAL scoring? Is it per-symbol or global there?
**Status: CONFIGURED PER-SYMBOL (Effectively 0.0 for most)**

Signal scoring dynamically consumes features based on weights defined in config. 
- **Evidence (Code):** `apps/reference/domains/decision_making/signal_score_v2.py` iterates over `weights.items()` and applies them. If the weight is `0.0`, the feature is ignored.
- **Evidence (Config):** `config/aurora/strategies/aurora.yaml` defines `absorption` under the `weights` block for assets.
  - It is configured **PER-SYMBOL** (e.g., `assets.<SYM>.weights.absorption`).
  - For most assets, it is set to `0.0` (e.g., `absorption: 0.0`).
  - A few calibrated outliers exist (e.g., `absorption: 0.0562502`), but because the feature engine outputs `0.0`, the net contribution to the signal score is currently `0.0`.

---

## D) Is absorption used in RISK scoring? Exact formula and config knobs.
**Status: NO (It uses an internal proxy instead)**

The true `absorption` feature emitted by Feature Engineering is completely ignored in the risk score formula, despite being parsed.
- **Evidence:** `apps/reference/domains/risk_management/risk_management.py` (lines 273-315) extracts `_absorption = _to_dec(features.get("absorption"))` but uses a locally computed `toxicity_term` instead for the penalty:
```python
        # D5/P1: Absorption penalty (toxicity proxy, directionless)
        toxicity_term = decimal.Decimal("0")
        if self._use_absorption_penalty and absorption_inverse_weight != 0:
            dp_cap = _to_dec(getattr(self.domain_config, "absorption_dp_cap_pct", None))
            impact_norm = delta_price_pct / dp_cap
            if impact_norm > 1:
                impact_norm = decimal.Decimal("1")
            toxicity = abs(tfi) * impact_norm
            toxicity_term = toxicity * absorption_inverse_weight
```

**Exact Formula:**
```
risk_score = (delta_price_pct * w_delta) + (|obi| * w_obi) + (|tfi| * w_tfi) + toxicity_term
# where toxicity_term = |tfi| * min(delta_price_pct / dp_cap, 1) * w_abs_inv
```

**Config Knobs** (from `config/aurora/domains.yaml`):
- `domains.risk_management.use_absorption_penalty`: `true`
- `domains.risk_management.absorption_dp_cap_pct`: `0.02`
- `domains.risk_management.risk_score_weights.absorption_inverse`: `0.3`

---

## E) Is risk_score gate per-symbol or global? Where configured?
**Status: GLOBAL (with optional per-symbol overrides)**

The risk gate blocks trading if `risk_score > max_risk_score`.
- **Evidence (Code):** `apps/reference/domains/decision_making/decision_making.py` (lines 701-720).
- **Global Config:** It pulls the baseline threshold from `domains.yaml` -> `domains.risk_management.trading_allowed_thresholds.max_risk_score` (currently `0.96`).
- **Per-Symbol Override:** The code explicitly checks `instr_cfg.max_risk_score` from `strategies/aurora.yaml`. If an asset has `max_risk_score: { enabled: true, value: X }`, the gate applies the symbol-specific threshold instead.

---

## F) If absorption currently disabled/missing/zero: why, and minimal safe plan to enable.
**Why it's disabled:**
It is explicitly labeled as an "Experimental (Default OFF, no live impact)" feature (R2/P2) in `domains.yaml`. To avoid blocking readiness with unstable experimental data, `mode: disabled` forces it to 0.0 and `absorption_ready = False`.

**Minimal Safe Plan to Enable (Conceptual):**
1. **Enable Compute:** In `config/aurora/domains.yaml`, change `domains.feature_engineering.absorption.mode` from `disabled` to `proxy` or `full`.
2. **Readiness Alignment:** Ensure `absorption.dp_cap_pct` and `neutral` values are properly set in `domains.yaml` so that the feature passes validation and reaches `absorption_ready = True` in the warmup pipeline.
3. **Reconcile Risk Score:** Modify `apps/reference/domains/risk_management/risk_management.py` to either:
   - Actually incorporate the real `_absorption` variable into the `risk_score` formula.
   - Or, rename the existing internal variables (`toxicity_term` instead of `absorption_inverse_weight`) to decouple the naming overlap, acknowledging Risk Management handles toxicity differently.
4. **Signal Scoring Rollout:** Progressively update `assets.<SYM>.weights.absorption` from `0.0` to calibrated values in `config/aurora/strategies/aurora.yaml`.