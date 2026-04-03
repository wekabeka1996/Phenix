# DATA_REPORT

Generated: 2026-04-01

## Scope

- FACT: This report audits three anomaly families only: MagicMock adapter-init bypass, Quadratic/pillar_sum scoring claims, and rapid UNCERTAIN / uncertain_cutoff claims.
- FACT: Authoritative cross-checks are [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md), [ORPHANED_TTL_FORENSIC_REPORT.md](ORPHANED_TTL_FORENSIC_REPORT.md), [aurora_math_passport.md](../config/docs/aurora_math_passport.md), [regime_passport.md](../config/docs/regime_passport.md), plus raw logs and code only where needed.
- FACT: Labels are strict: FACT, INFERENCE, ASSUMPTION, UNKNOWN.
- FACT: Static code risk is not runtime proof. One anomaly family is not used to explain another without explicit runtime linkage.

## Executive Verdict

- FACT: The previous DATA_REPORT is directionally correct on some kernel semantics, but it overstates causality and mixes at least four different anomaly families: test-like MagicMock execution failures, accepted Aurora SELL decisions under TREND_UP, detector-side regime churn, and lifecycle-side ORPHANED_TTL collapse.
- FACT: For the 7 accepted SHORT/TREND_UP RIDs, the strongest repeated proven seam remains decision-trace observability loss at EVT:DECISION_TRACE_EMITTED schema validation, as established in [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md).
- FACT: ORPHANED_TTL remains a logger fallback label rather than terminal execution truth, as established in [ORPHANED_TTL_FORENSIC_REPORT.md](ORPHANED_TTL_FORENSIC_REPORT.md).
- FACT: The MagicMock anomaly is a real code risk, but no target RID in the accepted_SHORT or ORPHANED_TTL incident set is runtime-linked to that path.
- FACT: The accepted SHORT sample does show negative pillar_sum at decision time. That supports a sample-specific scoring explanation. It does not support a population-wide "always SELL" claim.
- FACT: The uncertain_cutoff anomaly is mathematically real, but the previous report incorrectly conflated detector-side cutoff 0.22 with decision-side min_regime_confidence 0.42.
- INFERENCE: The previous DATA_REPORT should be treated as a mixed anomaly notebook, not as a root-cause report.

## Anomaly 1 - MagicMock / adapter-init guard bypass

Classification: PROVEN CODE RISK ONLY

### Proven facts

- FACT: Adapter initialization still uses a truthiness guard on credentials at [adapter_init.py#L91](../apps/reference/domains/execution_position/adapter_init.py#L91). The same method extracts env_config fields at [adapter_init.py#L83](../apps/reference/domains/execution_position/adapter_init.py#L83) and instantiates BinanceAdapter at [adapter_init.py#L104](../apps/reference/domains/execution_position/adapter_init.py#L104).
- FACT: A truthy MagicMock would bypass the incomplete-credential guard and can therefore reach adapter construction. This is a real static execution risk.
- FACT: Raw logs contain the exact MagicMock comparison failure outside the target RID set: [order_log_v1.jsonl#L144](../logs/order_log_v1.jsonl#L144), [order_log_v1.jsonl#L148](../logs/order_log_v1.jsonl#L148), [order_log_v1.jsonl#L222](../logs/order_log_v1.jsonl#L222), [order_log_v1.jsonl#L226](../logs/order_log_v1.jsonl#L226), and [order_log_v1.jsonl#L247](../logs/order_log_v1.jsonl#L247). The same synthetic-looking cluster contains MagicMock lifecycle IDs at [order_log_v1.jsonl#L135](../logs/order_log_v1.jsonl#L135), [order_log_v1.jsonl#L136](../logs/order_log_v1.jsonl#L136), [order_log_v1.jsonl#L140](../logs/order_log_v1.jsonl#L140), [order_log_v1.jsonl#L213](../logs/order_log_v1.jsonl#L213), [order_log_v1.jsonl#L214](../logs/order_log_v1.jsonl#L214), and [order_log_v1.jsonl#L218](../logs/order_log_v1.jsonl#L218).
- FACT: The target accepted_SHORT report and the ORPHANED_TTL report do not identify MagicMock as the first proven seam for their incident populations. The ORPHANED_TTL report instead classifies 14 fill-then-no-close cases, 7 watchdog silent-drop cases, and 1 explicit timeout/cancel case in [ORPHANED_TTL_FORENSIC_REPORT.md](ORPHANED_TTL_FORENSIC_REPORT.md).

### Best-supported interpretation

- INFERENCE: MagicMock contamination is a real ExecPosFSM failure mode, but it is a separate anomaly family from the accepted SHORT/TREND_UP sample and from the ORPHANED_TTL terminal-family audit.
- INFERENCE: Calling MagicMock the root cause of the studied incident set fails closed incorrectly, because stronger runtime evidence for that set already points to decision-trace observability loss and lifecycle/logger collapse instead.

### What remains unproven

- UNKNOWN: Whether any of the 7 accepted SHORT/TREND_UP RIDs ever passed through adapter initialization with MagicMock credentials.
- UNKNOWN: Whether any of the 22 ORPHANED_TTL RIDs ever traversed this path.
- UNKNOWN: Whether the MagicMock rows came from replay fixtures, mixed test contamination, or some isolated runtime path outside the incident set.

## Anomaly 2 - Quadratic kernel / pillar_sum / "always SELL"

| Sub-claim | Status |
|---|---|
| Quadratic kernel reads pillar_sum only | PROVEN |
| Legacy signal_weights are not consumed by the active kernel | PARTIALLY PROVEN |
| Aurora always outputs SHORT/SELL during micro-structural uptrend | CONTRADICTED |
| Macro H4/D1 dominance explains the 7 accepted SHORT RIDs | PARTIALLY PROVEN |

### Proven facts

- FACT: The active Quadratic kernel treats compatibility kwargs such as signal_weights as accepted-but-not-read surfaces at [quadratic_scoring_kernel.py#L182](../apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L182) and [quadratic_scoring_kernel.py#L183](../apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L183). The kernel uses features["pillar_sum"] when linear_score is absent at [quadratic_scoring_kernel.py#L216](../apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L216) and [quadratic_scoring_kernel.py#L220](../apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L220).
- FACT: The live threshold surface is decision.regime_threshold_multipliers, loaded into self.regime_thresholds at [aurora_config_loader.py#L156](../apps/reference/domains/decision_making/aurora_config_loader.py#L156) and [aurora_config_loader.py#L162](../apps/reference/domains/decision_making/aurora_config_loader.py#L162), with legacy/mock fallback at [aurora_config_loader.py#L176](../apps/reference/domains/decision_making/aurora_config_loader.py#L176) and [aurora_config_loader.py#L177](../apps/reference/domains/decision_making/aurora_config_loader.py#L177). The separate decision.regime_thresholds block is present in [aurora.yaml#L234](../config/aurora/strategies/aurora.yaml#L234), but the audited live loader path does not use it as the active threshold source.
- FACT: The 7 accepted target RIDs are real upstream SELL decisions under TREND_UP, as established in [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md).
- FACT: Feature snapshots around all 7 accepted decision windows inspected for this audit show negative pillar_sum: [aurora_core.log.28#L10443](../logs/aurora_core.log.28#L10443), [aurora_core.log.14#L23226](../logs/aurora_core.log.14#L23226), [aurora_core.log.13#L38959](../logs/aurora_core.log.13#L38959), [aurora_core.log.11#L4594](../logs/aurora_core.log.11#L4594), [aurora_core.log.11#L15395](../logs/aurora_core.log.11#L15395), and [aurora_core.log.10#L7620](../logs/aurora_core.log.10#L7620), and [aurora_core.log.5#L35089](../logs/aurora_core.log.5#L35089).
- FACT: Those same feature snapshots show the strategist term as the dominant negative contribution in the accepted sample. The operator term is near zero. The tactician term is positive in most of the accepted sample, but not all of it. Representative windows are [aurora_core.log.28#L10443](../logs/aurora_core.log.28#L10443), [aurora_core.log.14#L23226](../logs/aurora_core.log.14#L23226), [aurora_core.log.11#L4594](../logs/aurora_core.log.11#L4594), and [aurora_core.log.5#L35089](../logs/aurora_core.log.5#L35089).
- FACT: The runtime pillar contributions match the configured 0.45 / 0.25 / 0.30 weights in [domains.yaml#L359](../config/aurora/domains.yaml#L359), [domains.yaml#L360](../config/aurora/domains.yaml#L360), [domains.yaml#L361](../config/aurora/domains.yaml#L361), and [domains.yaml#L362](../config/aurora/domains.yaml#L362).
- FACT: The same incident window contains many rejected SELL intents via decision-side safety gates, including NRR-026 and NRR-027, so the population behavior is not "always SELL" and not "always accepted SELL". Examples include [order_log_v1.jsonl#L204](../logs/order_log_v1.jsonl#L204), [order_log_v1.jsonl#L205](../logs/order_log_v1.jsonl#L205), [order_log_v1.jsonl#L227](../logs/order_log_v1.jsonl#L227), [order_log_v1.jsonl#L235](../logs/order_log_v1.jsonl#L235), [order_log_v1.jsonl#L256](../logs/order_log_v1.jsonl#L256), and [order_log_v1.jsonl#L259](../logs/order_log_v1.jsonl#L259).

### Best-supported interpretation

- INFERENCE: The accepted SHORT/TREND_UP sample is best explained by negative pillar_sum feeding the active Quadratic kernel, with the D1 strategist contribution dominating the sign of the aggregate.
- INFERENCE: The evidence is much stronger for strategist dominance than for any broad "H4/D1 macro dominance" claim. In the accepted sample, the H4 operator contribution is typically negligible.
- INFERENCE: The exact allow path for why a TREND_UP short was permitted remains unproven because EVT:DECISION_TRACE_EMITTED fails when trend_run_length is emitted. That repeated observability seam is the stronger proven finding from [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md).

### What remains unproven

- UNKNOWN: Population-wide behavior across all TREND_UP decisions. The accepted sample does not justify the word "always".
- UNKNOWN: The per-RID why_short and trend_run_length values for the 7 accepted cases, because the decision trace payload is rejected before persistence.
- UNKNOWN: Whether legacy signal_weights are fully inert outside the active Quadratic kernel boundary. The active kernel ignores them directly, but compatibility surfaces still exist.

## Anomaly 3 - rapid UNCERTAIN / uncertain_cutoff / regime churn

Classification: PROVEN DETECTOR-SIDE BEHAVIOR, NOT PROVEN INCIDENT CAUSE FOR THE CURRENT SAMPLE

### Proven facts

- FACT: The detector-side uncertain_cutoff is wired from config at [regime_detector.py#L80](../apps/reference/domains/regime_detector/regime_detector.py#L80) and applied in the demotion block at [regime_detector.py#L664](../apps/reference/domains/regime_detector/regime_detector.py#L664), [regime_detector.py#L666](../apps/reference/domains/regime_detector/regime_detector.py#L666), and [regime_detector.py#L675](../apps/reference/domains/regime_detector/regime_detector.py#L675). The configured cutoff is 0.22 in [regime.yaml](../config/aurora/regime.yaml).
- FACT: Under sma_trend confidence_multiplier 80.0, the detector-side floor implied by uncertain_cutoff is 0.22 / 80.0 = 0.00275. That threshold math is correct as a detector-side statement.
- FACT: Logs show repeated uncertain_cutoff_gate demotions across symbols, for example [domain_regime_detector.log#L20](../logs/domain_regime_detector.log#L20), [domain_regime_detector.log#L40](../logs/domain_regime_detector.log#L40), [domain_regime_detector.log#L122](../logs/domain_regime_detector.log#L122), and [domain_regime_detector.log#L276](../logs/domain_regime_detector.log#L276).
- FACT: The widely cited 0.42 threshold is not uncertain_cutoff. It is the separate decision-side min_regime_confidence gate in [domains.yaml#L93](../config/aurora/domains.yaml#L93). Its runtime symptom is NRR-026 in order flow, for example [order_log_v1.jsonl#L204](../logs/order_log_v1.jsonl#L204) and [order_log_v1.jsonl#L259](../logs/order_log_v1.jsonl#L259).
- FACT: Several TREND_UP -> UNCERTAIN transitions are logged with model=sma_trend_v1 rather than uncertain_cutoff_gate, for example [aurora_core.log.28#L13986](../logs/aurora_core.log.28#L13986), [aurora_core.log.11#L15373](../logs/aurora_core.log.11#L15373), and [aurora_core.log.4#L2733](../logs/aurora_core.log.4#L2733). The previous report therefore overstates uncertain_cutoff as the sole or dominant explanation for all churn.
- FACT: Neither [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md) nor [ORPHANED_TTL_FORENSIC_REPORT.md](ORPHANED_TTL_FORENSIC_REPORT.md) identifies uncertain_cutoff or rapid UNCERTAIN churn as the first proven seam for the accepted_SHORT or ORPHANED_TTL sample.

### Best-supported interpretation

- INFERENCE: Detector churn is a real background behavior and may contribute to later rejection noise, but the previous report overfit it to the wrong symptom family.
- INFERENCE: The previous text conflated two different thresholds: detector demotion at 0.22 and decision-side NRR-026 blocking at 0.42.
- INFERENCE: Within this audit scope, anomaly 3 is a side observation unless separately linked to missed closes, stale-regime cancels, or another concrete downstream symptom.

### What remains unproven

- UNKNOWN: Whether any target RID in the accepted_SHORT or ORPHANED_TTL sample was directly caused by rapid UNCERTAIN churn.
- UNKNOWN: The relative contribution of uncertain_cutoff, hysteresis, and other raw-regime changes to the observed TREND_UP / UNCERTAIN flips without a separate churn study.

## Cross-report consistency

### Where the previous DATA_REPORT agrees with stronger evidence

- FACT: It is correct that the active Quadratic kernel is pillar_sum-based rather than legacy linear feature-weight scoring.
- FACT: It is correct that detector-side uncertain_cutoff exists and can demote low-confidence regimes to UNCERTAIN.
- FACT: It is correct that accepted SELL decisions under TREND_UP occurred in runtime.

### Where the previous DATA_REPORT outruns the evidence

- FACT: It calls MagicMock a root cause for the current incident set without RID-level runtime linkage.
- FACT: It uses the word "always" for behavior that the incident window itself contradicts.
- FACT: It treats the declared decision.regime_thresholds block as the active runtime threshold surface, while the audited live loader path uses regime_threshold_multipliers.
- FACT: It treats regime_confidence < 0.42 as evidence of uncertain_cutoff behavior, even though 0.42 belongs to a different gate.

### Where the previous DATA_REPORT conflicts with stronger evidence

- FACT: [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md) identifies decision-trace observability loss as the first repeated proven seam for the 7 accepted RIDs. The previous DATA_REPORT does not preserve that evidence hierarchy.
- FACT: [ORPHANED_TTL_FORENSIC_REPORT.md](ORPHANED_TTL_FORENSIC_REPORT.md) identifies logger/lifecycle collapse and one explicit timeout/cancel case as the proven ORPHANED_TTL family structure. The previous DATA_REPORT instead routes that family through the unrelated MagicMock anomaly.
- FACT: [aurora_math_passport.md](../config/docs/aurora_math_passport.md) and [aurora_config_loader.py#L156](../apps/reference/domains/decision_making/aurora_config_loader.py#L156) contradict the previous report's claim that the separate decision.regime_thresholds block is the active threshold source.

### Where the previous DATA_REPORT mixes unrelated anomaly families

- FACT: It mixes test-like ExecPosFSM MagicMock failures with accepted Aurora decision behavior.
- FACT: It mixes detector-side regime churn with decision-side NRR-026 gating.
- FACT: It mixes accepted_SHORT decision provenance with lifecycle-side ORPHANED_TTL terminalization.

## Closure evidence needed

- FACT: To elevate MagicMock from code risk to incident cause, the audit would need direct RID-linked evidence connecting a target RID to the adapter_init bypass path.
- FACT: To close the accepted_SHORT question, the audit would need a persisted EVT:DECISION_TRACE_EMITTED payload that survives schema validation and preserves trend_run_length, why_short, and other gate outcomes for the target RIDs.
- FACT: To justify any global scoring claim, the audit would need a population-wide export of TREND_UP decisions and rejections with pillar_sum, pillar_contribs, and final allow/deny reasons.
- FACT: To justify anomaly 3 as a current incident cause, the audit would need a dedicated churn study that aligns detector transitions to concrete downstream symptoms such as cancels, rejects, or missed closes.# DATA_REPORT.md — Anomaly Source Extraction
Generated: 2026-04-01

---

## ANOMALY 1 — MagicMock Injection into Live `ExecPosFSM` Adapter

### Root Cause: Truthiness Guard Bypass in `adapter_init.py`

**File:** `apps/reference/domains/execution_position/adapter_init.py`

The credential completeness guard at line 91 uses Python's implicit truthiness:

```python
# adapter_init.py  lines 82–102
try:
    api_key    = env_config.api_key
    api_secret = env_config.api_secret
    rest_url   = env_config.rest_url
except Exception:          # pragma: no cover - defensive
    api_key    = None
    api_secret = None
    rest_url   = None

if not all([api_key, api_secret, rest_url]):   # <-- LINE 91
    LOG.error(
        f"API configuration for execution in '{mode}' mode is incomplete. "
        "Execution will be simulated."
    )
    self.shadow_mode = True
    return
```

**The failure mode:**
`bool(MagicMock())` is **always `True`** in Python. If `env_config.api_key` (or `api_secret` / `rest_url`) returns a `MagicMock` object (e.g., from a partially-mocked config that escapes test isolation), the guard `not all([MagicMock(), MagicMock(), MagicMock()])` evaluates to `False`. The shadow-mode flip is **skipped**, and `BinanceAdapter` is constructed with three MagicMock credential values:

```python
# adapter_init.py  lines 104–119
self.adapter = BinanceAdapter(
    api_key    = api_key,      # ← MagicMock
    api_secret = api_secret,   # ← MagicMock
    rest_url   = rest_url,     # ← MagicMock
)
self.adapter._orphan_metrics_ref = self._orphan_metrics
self.adapter.exec_fsm  = self
self.adapter.fsm_core  = self.fsm
```

At the first integer comparison inside `BinanceAdapter` (e.g., HTTP status code check, TTL comparison in fill-watchdog), the runtime raises:

```
TypeError: '>' not supported between instances of 'MagicMock' and 'int'
```

caught and re-logged as: `Adapter execution failed: '>' not supported between instances of 'MagicMock' and 'int'` → triggers `ORPHANED_TTL`.

### Production Wiring (no DI container)

**File:** `apps/reference/bootstrap/domain_builder.py` line 113:
```python
execution_position = ExecPosFSM(config=config, fsm=fsm)
```

No adapter is injected externally. The single path into the live adapter is `_initialize_adapter()` called inside `__init__` when `shadow_mode=False` (the default). There is no `container.py`, no `adapters.yaml`.

### Fix Target
Replace the implicit-truthiness guard with an explicit type check:
```python
# CURRENT (vulnerable)
if not all([api_key, api_secret, rest_url]):

# REQUIRED (safe)
if not all(isinstance(v, str) and v for v in [api_key, api_secret, rest_url]):
```

---

## ANOMALY 2 — Aurora Always Outputs SHORT/SELL During Micro-Structural Uptrend

### Phase 9 Quadratic Scoring: Active Signal Path

**File:** `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`

#### Step 1 — Input Resolution (lines 206–230)
```python
if linear_score is not None:
    s_linear = linear_score
    source = "arg"
else:
    pillar_sum_raw = features.get("pillar_sum")
    if pillar_sum_raw is None:
        result.deferred = True
        result.defer_reason = "PILLAR_WARMUP"
        return result
    s_linear = float(pillar_sum_raw)
    source = "feature:pillar_sum"
```

The kernel reads **only `pillar_sum`** from the features dict. OBI, TFI, and absorption are **not read** by the Phase 9 kernel.

#### Step 2 — Scale and Clamp (lines 234–236)
```python
s_scaled_raw = s_linear * score_multiplier   # score_multiplier = 1.0 (aurora.yaml line 201)
s_clamped    = max(-1.0, min(1.0, s_scaled_raw))
```

#### Step 3 — Admission/Sizing Transform (lines 240–245)
```python
# From aurora.yaml: admission_mode=linear, sizing_mode=quadratic
admission_pre_shield = _transform_signed_score(s_clamped, mode="linear",    power=None)
sizing_pre_shield    = _transform_signed_score(s_clamped, mode="quadratic",  power=None)
```

The transform function (`lines 471–498`):
```python
def _transform_signed_score(value: float, *, mode: str, power: Optional[float]) -> float:
    sign      = 1.0 if value >= 0 else -1.0
    magnitude = abs(value)

    if mode == "quadratic":
        return sign * (magnitude ** 2)    # sign(x) * |x|²
    if mode == "linear":
        return value                       # unchanged
    if mode == "soft_power":
        return sign * (magnitude ** float(power))
    raise ValueError(f"unsupported transform mode: {mode}")
```

So: `admission_pre_shield = s_clamped` (linear, unchanged), `sizing_pre_shield = sign(s_clamped) * s_clamped²`.

#### Step 4 — Shield Cascade (lines 249–264)
```python
shield_mult, shield_reasons = _shield(symbol, features, s_linear, sizing_pre_shield)
shield_mult = max(0.0, min(1.0, shield_mult))

if shield_mult == 0.0:
    admission_shield_mult = 0.0
else:
    # admission_shield_floor=0.75 lifts soft attenuation but never overrides a hard veto
    admission_shield_mult = max(shield_mult, max(0.0, min(1.0, admission_shield_floor)))

decision_score_val = admission_pre_shield * admission_shield_mult
sizing_score_val   = sizing_pre_shield    * shield_mult
```

#### Step 5 — Regime Threshold + Side-Bias (lines 321–339)
```python
factor           = _resolve_regime_factor(regime_name, regime_thresholds)
signal_threshold = base_threshold * factor

buy_bias_mult, sell_bias_mult = _compute_side_bias_mult(side_bias_state)

thr_buy  = signal_threshold * buy_bias_mult
thr_sell = signal_threshold * sell_bias_mult
```

#### Step 6 — 3-Zone Hysteresis Side Selection (lines 433–468)
```python
def _determine_side(score, thr_buy, thr_sell, thr_neutral, current_side):
    if current_side == "":             # no position
        if score >= thr_buy:  return "buy",  f"enter:buy:..."
        elif score <= -thr_sell: return "sell", f"enter:sell:..."
        else:                    return "",    f"neutral:..."
    elif current_side == "buy":        # holding long
        if score <= -thr_sell: return "sell", f"flip:buy->sell:..."
        elif score >= thr_neutral: return "buy",  f"hold:buy:..."
        else:                     return "",   f"exit:buy->neutral:..."
    elif current_side == "sell":       # holding short
        if score >= thr_buy:  return "buy",  f"flip:sell->buy:..."
        elif score <= -thr_neutral: return "sell", f"hold:sell:..."
        else:                       return "",   f"exit:sell->neutral:..."
```

### Why Aurora Emits SELL During Micro-Structural Uptrend

**Root cause is in `pillar_sum` computation, not in OBI/TFI weights.**

`pillar_sum` is the weighted sum of three multi-timeframe pillars (`domains.yaml:359–362`):

```yaml
# config/aurora/domains.yaml  lines 359–362
weights:
  tactician:  0.45   # M15: ROC(14) normalized via tanh(x * 3.0)
  operator:   0.25   # H4:  LinReg slope * (ADX/50) normalized via tanh(x * 3.0)
  strategist: 0.30   # D1:  (close - SMA200) / SMA200 normalized via tanh(x * 3.0)
```

A micro-structural uptrend (tick-level / M15 impulse) contributes only through the **Tactician** pillar (weight 0.45). The **Strategist** (D1, weight 0.30) responds to the price relative to SMA200 — in a macro downtrend, this term is **negative** and persistent. If `(close - SMA200) / SMA200 < 0` on the daily frame and `LinReg slope < 0` on H4, both will produce negative normalized values, and together they outweigh the positive M15 ROC signal:

```
pillar_sum = 0.45 * (+) + 0.25 * (-) + 0.30 * (-) < 0
           → decision_score < 0
           → score <= -thr_sell  → side = "sell"
```

This explains the continuous stream of `SELL` intents rejected by:
- `NRR-027`: uptrend (regime_thresholds TREND_UP = 0.12 but score is negative)
- `NRR-029`: flash up
- `NRR-030`: bleed up

### YAML Configuration — Active Scoring Parameters

**File:** `config/aurora/strategies/aurora.yaml` (lines 196–241, 277–318)

```yaml
# Active scoring geometry (Phase 9)
signal_threshold: 0.162
score_multiplier: 1.0
decision_geometry:
  admission_mode: linear
  sizing_mode: quadratic
  admission_shield_floor: 0.75
neutral_threshold: 0.05
scoring_version: "quadratic"

# Regime threshold factors (multiplied against signal_threshold=0.162)
regime_thresholds:
  HIGH_VOLATILITY: 0.18
  LOW_VOLATILITY:  0.14
  MEAN_REVERSION:  0.075
  TREND_UP:        0.12
  TREND_DOWN:      0.12
  UNCERTAIN:       99.0     # effective block (0.162 * 99.0 = 16.0 >> any possible score)
  DEFAULT:         0.12

# Shield cascade
scoring_engine:
  shield_enabled: true

  danger_zone_shield:
    enabled: true
    vol_threshold:    0.95   # hard veto if volatility_state > 0.95
    spread_threshold: 50.0   # hard veto if spread > 50 bps
    motion_threshold: 3.0    # hard veto if pm_norm > 3.0

  context_shield:
    enabled: true
    regime_multipliers:
      TREND_UP:         1.0
      TREND_DOWN:       1.0
      MEAN_REVERSION:   0.75
      LOW_VOLATILITY:   0.85
      HIGH_VOLATILITY:  0.30
      UNCERTAIN:        0.55
    default_multiplier:    0.80
    no_regime_multiplier:  0.50

  memory_shield:
    enabled: true
    unknown_multiplier:    0.60   # < 10 visits
    exploring_multiplier:  0.80   # 10–50 visits
    known_multiplier:      1.00   # ≥ 50 visits
```

### DEPRECATED Fields — NOT Read by Phase 9 Kernel

```yaml
# config/aurora/strategies/aurora.yaml  lines 398–413
# DEPRECATED (Phase 9): signal_weights was used by v2 linear scoring.
# Not consumed by QuadraticScoringKernel. Retained for config schema backward-compatibility.
signal_weights:
  obi:              0.42
  tfi:              0.15
  delta_price:      0.15
  ema_bias:         0.15
  volume_spike:     0.10
  volatility_state: 0.10
  depth_imbalance: -0.15
  macro_resid:      0.10
  absorption:       0.0
```

**OBI, TFI, and absorption weights above are NOT read by `QuadraticScoringKernel.compute()`.** The kernel docstring explicitly states:
```python
# DEPRECATED: signal_weights, feature_neutrals, direction_strength_cfg
# are accepted for call-site compat but NOT read by Quadratic kernel.
# Quadratic reads pillar_sum only.
```

OBI/TFI appear only in:
- `aurora_decision.py ~line 991`: `entry_plan_calc.compute(obi=features.get("obi"), ...)` — entry *price offset*, not direction.
- `calculation_engine.py`: internal `update_absorption()` dedup guard.

---

## ANOMALY 3 — Rapid UNCERTAIN Transitions in `sma_trend_v1`

### Confidence Calculation Formula

**File:** `apps/reference/domains/regime_detector/regime_detector.py` (lines 247–284)

```python
def _calculate_confidence(self, sma_short: Decimal, sma_long: Decimal) -> Decimal:
    if sma_long == 0:
        return Decimal(str(self.model_config.confidence_min))

    confidence_multiplier = Decimal(str(self.model_config.confidence_multiplier))

    spread_ratio = (sma_short - sma_long) / sma_long   # Relative SMA separation
    confidence   = spread_ratio * confidence_multiplier

    conf_min = Decimal(str(self.model_config.confidence_min))
    conf_max = Decimal(str(self.model_config.confidence_max))

    # abs() makes the formula symmetric for TREND_UP and TREND_DOWN
    bounded_confidence = min(max(abs(confidence), conf_min), conf_max)
    return bounded_confidence
```

**Formula (active config):**
```
spread_ratio       = (SMA₄₈ – SMA₁₉₂) / SMA₁₉₂
raw_confidence     = spread_ratio × 80.0
bounded_confidence = clamp( |raw_confidence|, 0.15, 0.85 )
```

### `uncertain_cutoff_gate` Logic

**File:** `apps/reference/domains/regime_detector/regime_detector.py` (lines 664–675)

```python
# REG-FIX-01: uncertain_cutoff - demote low-confidence regimes to UNCERTAIN
if regime != "UNCERTAIN" and float(confidence) < self._uncertain_cutoff:
    data_notes.append(
        f"confidence_below_cutoff:{float(confidence):.3f}<{self._uncertain_cutoff}")
    self.logger.debug(
        f"[{symbol}] Regime {regime} demoted to UNCERTAIN: "
        f"confidence {float(confidence):.3f} < cutoff {self._uncertain_cutoff}"
    )
    regime       = "UNCERTAIN"
    confidence   = conf_min
    source_model = "uncertain_cutoff_gate"
```

This runs **after** all three priority layers (volatility priority 1, mean_reversion priority 2, sma_trend priority 3) and after the slope-gate lock.

### SMA Trend Trigger (lines 640–646)

```python
# Priority 3: SMA trend
if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready \
        and sma_short > sma_long and price > sma_short:
    regime     = "TREND_UP"
    confidence = self._calculate_confidence(sma_short, sma_long)
if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready \
        and sma_short < sma_long and price < sma_short:
    regime     = "TREND_DOWN"
    confidence = self._calculate_confidence(sma_short, sma_long)
```

### Active YAML Configuration

**File:** `config/aurora/regime.yaml`

```yaml
uncertain_cutoff: 0.22       # gate threshold — any regime with confidence < 0.22 → UNCERTAIN

models:
  sma_trend:
    sma_short_period: 48     # R2-WINNER-2026-03-01 (was 24)
    sma_long_period:  192    # R2-WINNER-2026-03-01 (was 96)
    confidence_multiplier: 80.0   # TUNED: Lowered from 120 to avoid saturation
    confidence_min: 0.15
    confidence_max: 0.85
```

### Why `regime_confidence < 0.42` Is Logged Continuously

The gate threshold `uncertain_cutoff = 0.22` means any SMA₄₈/SMA₁₉₂ spread ratio smaller than:

```
min_spread_ratio = uncertain_cutoff / confidence_multiplier
                 = 0.22 / 80.0
                 = 0.00275   (0.275%)
```

triggers a demotion to UNCERTAIN. In choppy or ranging markets, SMA₄₈ and SMA₁₉₂ will frequently be within 0.275% of each other. The log message `regime_confidence < 0.42` indicates the detector is computing valid SMA crossovers but the raw confidence is being bounced near the floor (0.15–0.22 range), then demoted back to UNCERTAIN.

Additionally, the slope gate (`vol_slope_gate_enabled: true`, `vol_slope_gate_eps: -0.005`, `vol_slope_gate_confirm_bars: 5`) fires `storm_rejected=True` during ATR expansion phases, which locks out TREND_UP/TREND_DOWN even when SMA conditions are met (lines 648–656):

```python
# HYSTERESIS-SLOPE-GATE-01
if storm_rejected and regime in ("TREND_UP", "TREND_DOWN", "MEAN_REVERSION"):
    data_notes.append(f"slope_gate_lock:blocked_{regime}")
    regime       = "UNCERTAIN"
    confidence   = conf_min
    source_model = "slope_gate_lock"
```

### Full Execution Order (all gates in sequence)

```
1. volatility priority (atr_period=14, atr_sma_length=288, threshold_multiplier=2.00)
2. mean_reversion priority (threshold=0.0050, confidence_multiplier=120.0)
3. sma_trend priority: SMA₄₈/SMA₁₉₂ crossover + price position check
4. slope_gate_lock: if vol spike blocked period → force UNCERTAIN
5. data_quality_gate: if any data drop → force UNCERTAIN
6. uncertain_cutoff_gate: if confidence < 0.22 → force UNCERTAIN
   → source_model = "uncertain_cutoff_gate"
   → emits UNCERTAIN with confidence = conf_min (0.15)
```

---

## Summary Matrix

| Anomaly | Root Cause File | Key Line(s) | Fix Target |
|---|---|---|---|
| MagicMock → ORPHANED_TTL | `adapter_init.py` | L91: `if not all([api_key, ...])` | Replace truthiness check with `isinstance(v, str) and v` |
| Aurora always SELL | `quadratic_scoring_kernel.py` + `domains.yaml` | L212 reads only `pillar_sum`; D1/H4 pillars (weight 0.55) are macro-bearish | Investigate D1/H4 pillar values; signal_weights block is DEPRECATED and has no effect |
| Rapid UNCERTAIN | `regime_detector.py` L247–284 + `regime.yaml` L2,38 | `uncertain_cutoff=0.22`, `multiplier=80.0` → gate floor is 0.275% SMA spread | Lower `uncertain_cutoff` or raise `confidence_multiplier`; also check `vol_slope_gate` firing rate |
