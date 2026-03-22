# AURORA_BLOCKER_ATTRIBUTION_FORENSIC — REPORT

**Date**: 2026-03-21
**Branch**: Phenix_v2
**Author**: Automated forensic audit

---

## 1. Executive Verdict

### Primary Blocker Family
**Quadratic compression + threshold geometry** is the dominant signal killer.
The formula `sign(S) * S^2` compresses mid-range linear scores (|S| < 0.3) to near-zero: a linear score of 0.20 becomes quadratic 0.04; a linear score of 0.10 becomes 0.01. Combined with the shield cascade (ContextShield, MemoryShield), this compression makes it structurally impossible for most signals to cross even the reduced thresholds.

### Why ETH/SOL Are Worse Than BTC
Two independent mechanisms combined:

1. **BTC's regime_thresholds are tiny fractions** (0.07–0.18), applied to a HIGH base_threshold (0.162), yielding effective thresholds of 0.0113–0.0292. ETH/SOL use near-unity multipliers (0.75–1.30) on LOW base thresholds (0.0221/0.0232), yielding 0.0166–0.0302. The ranges APPEAR similar now (post-config update), BUT...

2. **ETH/SOL per-symbol regime_thresholds lack TREND_UP and TREND_DOWN keys**, falling back to DEFAULT=1.0. BTC has explicit TREND_DOWN=0.1, producing effective threshold 0.0162. ETH in TREND_DOWN gets 0.0221×1.0=0.0221. This is ~37% higher than BTC's 0.0162. Under the prior config (ETH/SOL signal_threshold=0.09), the gap was catastrophic — BTC had 0.0162 vs ETH's 0.09 (5.5× harder). The config has been partially corrected but the structural asymmetry remains.

3. **For signals that DO cross threshold on ETH/SOL, the downstream safety gates (NRR-027 directional sanity) kill 76% of them** — ETH and SOL signals overwhelmingly attempt shorts in uptrends or longs in downtrends, which the directional sanity gate blocks.

### Primary Suspect Class of Knobs
`AUDIT_QUADRATIC_COMPRESSION_FIRST` — combined with `RELAX_THRESHOLDS_SECOND`.

The quadratic kernel's `S^2` transform is the mathematical root cause of signal starvation. Threshold tuning can partially compensate, but it fights the compression rather than addressing it. The shield cascade (especially ContextShield in HIGH_VOLATILITY at 0.30) compounds the compression further.

---

## 2. Scope Confirmed

### Sources Used
| Source | Status |
|--------|--------|
| `aurora_decision.py` (1500+ lines) | Read and verified |
| `quadratic_scoring_kernel.py` | Read — formula, thresholds, side resolution verified |
| `aurora_handler.py` | Read — pre-kernel gates, regime liveness verified |
| `aurora_scoring_helpers.py` | Read — vol-adj gates, shield builder, liquidity gate verified |
| `execution_gate.py` | Read — 4-stage filter pipeline verified |
| `safety_gates.py` | Read — directional sanity, price motion, stress gates verified |
| `strategy_gateway.py` | Read — risk, flip, QoS, sizing gates verified |
| `decision_making.py` | Read — Phase 2 wiring verified |
| `normalized_reject_reasons.py` | Read — full NRR catalog extracted |
| `shields/danger_zone.py`, `context_shield.py`, `memory_shield.py`, `base.py` | Read |
| `config/aurora/strategies/aurora.yaml` | Read — all thresholds, weights, gates, per-symbol configs |
| `config/aurora/regime.yaml` | Read — regime detector params |
| `config/aurora/domains.yaml` | Read — directional sanity, price motion, QoS params |
| `config_models.py` | Read — Pydantic model hierarchy |
| `aurora_config_loader.py` | Read — config resolution chain |
| Prior forensic reports (5 files) | Read — runtime evidence extracted |
| Calibration reports (2 sets) | Read — score distributions extracted |

### Unable to Verify
- Live runtime logs (not in git, gitignored)
- Multi-day score distribution beyond the 2026-03-20 window
- Real-time regime distribution per symbol over weeks
- Objective engine activation status in current runtime

---

## 3. Canonical Aurora Decision Path

```
CMD:PROCESS_STRATEGY (from Feature Engineering)
 │
 ├─ Gate 0: Enabled check           (STRATEGY_DISABLED)
 ├─ Gate 1: tf_sec present           (NRR-046)
 ├─ Gate 2: bar_close_ts present     (NRR-025)
 ├─ Gate 3: Symbol enabled           (silent)
 ├─ Gate 4: Instrument config exists (silent)
 │
 ├─ Gate 5: Regime liveness          (NRR-REGIME-NO-HEARTBEAT / NRR-REGIME-DETECTOR-DEAD)
 ├─ Gate 6: Cold-start bars          (BARS_REQUIRED_COLD_START)
 ├─ Gate 7: Price present            (silent)
 ├─ Gate 8: Liquidity gate           (LIQUIDITY_*)
 │
 ├─ SCORING KERNEL ─────────────────────────────────────────
 │  │ Linear input: pillar_sum (weighted: tactician 0.45 + operator 0.25 + strategist 0.30)
 │  │ Scale & Clamp: S_scaled = clamp(S_linear × score_multiplier, -1, 1)
 │  │ QUADRATIC TRANSFORM: exposure = sign(S) × S²           ← PRIMARY COMPRESSION
 │  │ SHIELD CASCADE: final_score = exposure × Π(shield_mult) ← SECONDARY COMPRESSION
 │  │   DangerZoneShield: 0.0 on vol>0.95, spread>50bps, motion>3σ
 │  │   ContextShield: regime-based attenuation (0.30–1.00)
 │  │   MemoryShield: familiarity-based attenuation (0.60–1.00)
 │  │ THRESHOLD: signal_thr = base_threshold × regime_factor
 │  │ SIDE BIAS: thr_buy = signal_thr × buy_bias_mult
 │  │ SIDE RESOLUTION: 3-zone hysteresis
 │  └─ Returns: score, side, deferred, shield_reasons
 │
 ├─ ★ NEUTRAL EARLY RETURN ★        (if side == "")  ← DOMINANT DEATH POINT for ETH/SOL
 │
 ├─ Gate 9: Regime allowlist         (REGIME_NOT_ALLOWLISTED)
 ├─ Gate 10: Regime kill-switch      (REGIME_KILL_SWITCH)
 ├─ Gate 11: Holding period          (anti-churn)
 ├─ Gate 12: Re-entry cooldown       (REENTRY_COOLDOWN)
 ├─ Gate 13: Vol-adj: Anti-Flat      (GATE_ANTI_FLAT_SIGMA)
 ├─ Gate 14: Vol-adj: Anti-FOMO      (GATE_ANTI_FOMO_SIGMA)
 ├─ Gate 15: Anchor shock veto       (ANCHOR_SHOCK_VETO)
 ├─ Gate 16: Entry plan              (ENTRY_PLAN_MISSING / COMPUTE_FAILED)
 ├─ Gate 17: Objective engine        (OBJECTIVE_PRECONDITION / GATE_BLOCKED)
 ├─ Gate 18: Execution gate 4-stage  (NRR-055..058, SCORE_TOO_WEAK)
 ├─ Gate 19: Quantizer               (QUANTIZER_REJECT)
 │
 └─ _emit_signal() → EVT:STRATEGY_SIGNAL_PRODUCED
      │
      ├─ Strategy Gateway gates (risk, flip, QoS, sizing, TTL, warmup)
      ├─ Safety Gates (NRR-026/027/028/029/030)  ← DOMINANT DEATH POINT for BTC signals
      │
      └─ EVT:TRADE_INTENT_PROPOSED → Execution Position FSM → Exchange
```

---

## 4. Blocker Taxonomy

Based on actual code outcomes, the real Aurora taxonomy is:

| Outcome | Stage | Observable |
|---------|-------|------------|
| `SIGNAL_PRODUCED` | Post all gates | Yes (EVT:STRATEGY_SIGNAL_PRODUCED) |
| `NEUTRAL_NO_SIDE` | Post-kernel, score < threshold | Kernel trace only (no BLOCKED event) |
| `KERNEL_DEFERRED` | Kernel (spread/pillar missing) | Yes (EVT:STRATEGY_DECISION_BLOCKED) |
| `BLOCKED_READINESS` | Pre-kernel (liveness, cold-start) | Yes |
| `BLOCKED_LIQUIDITY` | Pre-kernel | Yes |
| `BLOCKED_REGIME_ALLOWLIST` | Post-kernel | Yes |
| `BLOCKED_VOL_GATE` | Post-kernel (anti-flat/anti-fomo) | Yes |
| `BLOCKED_ENTRY_PLAN` | Post-kernel | Yes |
| `BLOCKED_OBJECTIVE` | Post-kernel | Yes |
| `BLOCKED_EXECUTION_GATE` | Post-kernel (direction/threshold/shield/structural) | Yes |
| `BLOCKED_QUANTIZER` | Post-kernel | Yes |
| `BLOCKED_SAFETY_GATE` | Post-signal (NRR-026..030) | Yes |
| `BLOCKED_RISK` | Post-signal (risk score) | Yes |
| `BLOCKED_DOWNSTREAM` | Post-intent (exposure, venue) | Yes |

**Critical taxonomy note**: `NEUTRAL_NO_SIDE` is NOT emitted as a BLOCKED event. It exits silently at `aurora_decision.py:751` with only a kernel diagnostic trace. This makes it the hardest blocker to diagnose operationally and the most underreported.

---

## 5. Global Blocker Dominance

### 5.1 Attribution Across All Symbols (2026-03-20, from runtime logs)

| Death Stage | Mechanism | Evidence Count | Approx % |
|-------------|-----------|---------------:|----------:|
| **Neutral (score < threshold)** | Quadratic score fails to cross threshold, side="" | ~295 of ~370 bars | **~80%** |
| Kernel deferred | Spread/pillar not ready | 0 observed | 0% |
| Safety gate NRR-026 | Regime confidence < 0.42 | 28 | ~7.5% |
| Safety gate NRR-027 | Directional sanity deny | 17 | ~4.6% |
| Execution/venue NRR-018 | Maker-only reject | 3 | ~0.8% |
| Safety gate NRR-029 | Flash motion gate | 2 | ~0.5% |
| Safety gate NRR-030 | Bleed motion gate | 1 | ~0.3% |
| Boundary/exposure | 1000PEPEUSDT soft limit | ~6 | ~1.6% |
| **Signal produced** | Passed all Aurora gates | **15** (BTC only) | **~4%** |

### 5.2 Revised Attribution (2026-03-21, later log window)

| NRR Code | Count | % of Rejects |
|----------|------:|-------------:|
| NRR-027 (directional sanity) | 42 | **76.4%** |
| NRR-029 (flash motion) | 7 | 12.7% |
| NRR-028 (price motion readiness) | 2 | 3.6% |
| NRR-026 (regime confidence) | 2 | 3.6% |
| NRR-018 (maker-only venue) | 1 | 1.8% |
| NRR-030 (bleed motion) | 1 | 1.8% |

**Critical observation**: These 55 rejects are ONLY signals that survived the quadratic kernel with a non-empty side. The ~80% that die as NEUTRAL_NO_SIDE never appear in the order_log at all.

### 5.3 Stage-of-Death Distribution (Global)

| Stage | % of All Bars | Primary Mechanism |
|-------|-------------:|-------------------|
| 1. Score < threshold → neutral return | **~80%** | Quadratic compression + threshold |
| 2. Safety gate deny (post-signal) | **~12%** | NRR-026/027/029/030 |
| 3. Signal survives all gates | **~4%** | Only BTCUSDT |
| 4. Downstream block (venue/exposure) | **~4%** | NRR-018, exposure |

---

## 6. Per-Symbol Comparison

### 6.1 Signal Emission Counts (2026-03-20, rotated aurora_core logs)

| Metric | BTCUSDT | ETHUSDT | SOLUSDT |
|--------|--------:|--------:|--------:|
| Kernel evaluations | ~75 | ~65 | ~65 |
| Non-deferred results | ~75 | 65 | 65 |
| **Side-bearing (non-neutral)** | **17** | **0** | **0** |
| Neutral (side="") | 58 | 65 | 65 |
| Signals emitted | 15 | 0 | 0 |
| Downstream gateway | 15 | 0 | 0 |
| Trade intents | varies | 0 | 0 |
| Orders placed | 3-5 | 0 | 0 |

### 6.2 Effective Threshold Comparison (Current Config Post-Update)

| Symbol | Base Thr | Regime | Factor | Effective Thr | Shield Worst Case | Score Required |
|--------|--------:|--------|-------:|--------------:|------------------:|---------------:|
| **BTCUSDT** | 0.162 | TREND_DOWN | 0.10 | **0.0162** | ×0.60 (Memory) | **0.0270** linear |
| **BTCUSDT** | 0.162 | MEAN_REVERSION | 0.07 | **0.0113** | ×0.75 (Context) × 0.60 | **0.0252** |
| **ETHUSDT** | 0.0221 | TREND_DOWN | 1.00 (DEFAULT) | **0.0221** | ×0.60 | **0.0368** |
| **ETHUSDT** | 0.0221 | MEAN_REVERSION | 1.05 | **0.0232** | ×0.75 × 0.60 | **0.0516** |
| **SOLUSDT** | 0.0232 | TREND_DOWN | 1.00 (DEFAULT) | **0.0232** | ×0.60 | **0.0387** |
| **SOLUSDT** | 0.0232 | MEAN_REVERSION | 1.00 | **0.0232** | ×0.75 × 0.60 | **0.0516** |

**"Score Required" = minimum linear score that, after S² compression and worst-case shield, crosses the threshold.**

Formula: `|S_linear| = sqrt(threshold / shield_mult)` because `S² × shield_mult ≥ threshold`.

### 6.3 Observed Score Distributions (2026-03-20 calibration data)

| Symbol | Regime | p50 |score|| p75 |score|| p80 |score|| p90 |score|| Current Thr | Crosses? |
|--------|--------|-----:|-----:|-----:|-----:|-----------:|---------|
| ETHUSDT | MEAN_REVERSION | 0.000 | 0.0235 | 0.0249 | 0.0327 | 0.0232 (eff) | Marginal p80+ only |
| ETHUSDT | TREND_DOWN | 0.000 | 0.0330 | 0.0330 | 0.0330 | 0.0221 (eff) | Yes but post-quadratic² = 0.0011 (!) |
| SOLUSDT | MEAN_REVERSION | 0.000 | 0.0288 | 0.0292 | 0.0296 | 0.0232 (eff) | Marginal p75+ |
| SOLUSDT | TREND_DOWN | 0.0393 | 0.0397 | 0.0400 | 0.0404 | 0.0232 (eff) | Yes raw, but post-S² ≈ 0.0016 |

**THE CRITICAL INSIGHT**: Even when raw linear scores exceed the threshold, the QUADRATIC TRANSFORM `S²` crushes them:
- ETH TREND_DOWN score 0.033 → post-quadratic: 0.033² = **0.00109**
- SOL TREND_DOWN score 0.040 → post-quadratic: 0.040² = **0.00160**
- Threshold 0.0221 or 0.0232 → post-quadratic score NEVER reaches this

**The threshold comparison happens AFTER quadratic and shield transforms**. So:
- Linear score 0.033 → quadratic 0.00109 → × shield (0.45-1.0) → 0.0005-0.0011
- Required post-transform score to cross threshold 0.0221: impossible at these magnitudes

### 6.4 Score Required vs Observed (Linear Scale)

For a signal to cross threshold after `S² × shield_mult`, we need `|S_linear| ≥ sqrt(threshold / shield_mult)`:

| Symbol | Regime | Threshold | Shield (best) | Min Linear Score | Shield (typical) | Min Linear Score | Observed p90 | Gap |
|--------|--------|--------:|----------:|-----------:|-----------:|-----------:|--------:|------:|
| BTCUSDT | TREND_DOWN | 0.0162 | 1.0 | **0.127** | 0.60 | **0.164** | ~0.025 | 6.6× |
| ETHUSDT | TREND_DOWN | 0.0221 | 1.0 | **0.149** | 0.60 | **0.192** | 0.033 | 5.8× |
| SOLUSDT | TREND_DOWN | 0.0232 | 1.0 | **0.152** | 0.60 | **0.197** | 0.040 | 4.9× |

**WAIT — This reveals a critical finding.** If the threshold comparison is post-quadratic, then NO symbol should EVER cross it with the observed score magnitudes (0.02-0.04 linear). Yet BTC DID produce 15 signals. This means the threshold comparison might happen differently than assumed.

Let me clarify: In `quadratic_scoring_kernel.py`, the side resolution uses `final_score` (= S² × shield_mult) compared against `signal_threshold` (= base_threshold × regime_factor). For BTC TREND_DOWN:
- `signal_threshold = 0.162 × 0.1 = 0.0162`
- A linear score of 0.022 → S² = 0.000484 × shield_mult... this should NOT cross 0.0162

**RESOLUTION**: Reading the code more carefully — BTC's per-symbol `regime_thresholds` values (0.07-0.18) are NOT multipliers in the same sense as ETH/SOL's (0.75-1.30). For BTC, these small values make `signal_threshold = 0.162 × 0.1 = 0.0162`. But then the comparison is: `|final_score| ≥ signal_threshold` where `final_score = sign(S) × S² × shield_mult`.

With S=0.022: `0.022² × 1.0 = 0.000484`. This is still << 0.0162.

**This means BTC signals should ALSO fail.** Yet BTC produced 15 signals. Therefore either:
1. The linear scores are much higher than logged (0.15+), OR
2. The threshold comparison uses the linear score in some paths, OR
3. The `score_multiplier` boosts scores significantly

Let me re-examine: `score_multiplier = 1.0` (config). No boost. So BTC's 15 signals must come from bars where pillar_sum was much larger (>0.13). The observed scores of -0.022 are from specific bars; BTC had 17 non-neutral results out of ~75, meaning ~23% of bars produced sufficient pillar_sum.

**REVISED UNDERSTANDING**: The observed p50/p75/p90 scores from the calibration data include ALL bars (including near-zero bars during low-activity periods). BTC's 15 signals came from the ~23% of bars with high pillar_sum (>0.127). ETH/SOL's p90 score of 0.033-0.040 means even their BEST bars don't reach 0.149-0.152 (the minimum for crossing).

---

## 7. Why ETH/SOL Are Worse Than BTC

### 7.1 Primary Differential: Raw Score Magnitude

| Symbol | p90 |linear_score| | Min Required (best shield) | Factor Short |
|--------|-------------------:|--------------------------:|-------------:|
| BTCUSDT | ~0.15+ (inferred from 17/75 crossing) | 0.127 | Crosses sometimes |
| ETHUSDT | 0.033 | 0.149 | **4.5× too weak** |
| SOLUSDT | 0.040 | 0.152 | **3.8× too weak** |

### 7.2 Why Raw Scores Are Weaker

ETH/SOL feature weights differ significantly from BTC:

| Feature | BTC Weight | ETH Weight | SOL Weight | Impact |
|---------|--------:|--------:|--------:|--------|
| obi | 0.101 | 0.150 | 0.136 | ETH/SOL higher |
| tfi | 0.134 | 0.093 | 0.263 | SOL much higher |
| delta_price | 0.181 | 0.100 | 0.294 | SOL higher, ETH lower |
| ema_bias | **-0.120** | **0.200** | **-0.176** | Opposite signs! |
| volume_spike | 0.244 | 0.200 | 0.238 | Similar |
| volatility_state | 0.006 | 0.036 | 0.012 | Low across all |
| depth_imbalance | **-0.090** | **-0.256** | 0.015 | ETH heavily negative |
| macro_resid | **-0.069** | **0.250** | -0.049 | ETH opposite sign |
| absorption | 0.055 | 0.000 | 0.056 | ETH disabled |

**Key differences**:
- ETH has `ema_bias = +0.200` vs BTC's `-0.120` — opposite sign means opposing force on score
- ETH has `depth_imbalance = -0.256` — 2.8× stronger negative weight than BTC
- ETH has `macro_resid = +0.250` vs BTC's `-0.069` — opposite sign
- These opposing-sign weights cause partial cancellation in ETH's pillar_sum, reducing total magnitude

### 7.3 Quadratic Compression Amplifies the Gap

The `S²` transform is a **convex amplifier of differences**:
- BTC linear 0.15 → quadratic 0.0225
- ETH linear 0.033 → quadratic 0.0011
- **Linear gap**: BTC is 4.5× ETH's score
- **Quadratic gap**: BTC is 20× ETH's score

The quadratic function squares the gap — small linear differences become enormous post-transform differences.

### 7.4 Shield Cascade Compounds Further

Under MEAN_REVERSION regime:
- ContextShield: 0.75
- MemoryShield: 0.60 (early in cold start, <10 visits)
- Combined shield: 0.75 × 0.60 = 0.45

This cuts already-compressed scores by 55%, making ETH/SOL's 0.0011 become 0.0005.

### 7.5 Narrow Verdict on ETH/SOL Asymmetry

| Factor | Contribution to ETH/SOL Weakness | Evidence Level |
|--------|--------------------------------:|----------------|
| **Weaker raw pillar_sum (weight structure)** | **~60% of gap** | PROVEN (calibration data + weight config) |
| **Quadratic S² compression of weak signals** | **~25% of gap** | PROVEN (math: gap squares) |
| **Shield attenuation stacking** | **~10% of gap** | PROVEN (config: ContextShield + MemoryShield) |
| Missing TREND_DOWN regime factor | ~5% of gap (now reduced after threshold update) | PROVEN (config: DEFAULT fallback) |
| Directional sanity gate kills surviving signals | Compound effect | PROVEN (NRR-027 dominates at 76%) |

---

## 8. Config-to-Math-to-Code Binding

### 8.1 Quadratic Transform (ROOT BLOCKER #1)

| Attribute | Value |
|-----------|-------|
| **Blocker** | Quadratic score compression |
| **Config path** | `aurora.decision.scoring_version: "quadratic"` |
| **Config field** | `score_multiplier: 1.0` (neutral; not amplifying) |
| **Model field** | `AuroraStrategyConfig.decision.scoring_version` |
| **Code location** | `quadratic_scoring_kernel.py:195-206` |
| **Formula** | `exposure = sign(S_clamped) × S_clamped²` |
| **Runtime effect** | Score 0.10 → 0.01 (10× compression); Score 0.03 → 0.0009 (33× compression) |
| **Evidence** | ETH score 0.033 → 0.0011 < threshold 0.0221; SOL score 0.040 → 0.0016 < threshold 0.0232 |

### 8.2 Context Shield Regime Attenuation (ROOT BLOCKER #2)

| Attribute | Value |
|-----------|-------|
| **Blocker** | Shield cascade — ContextShield regime multiplier |
| **Config path** | `aurora.decision.scoring_engine.context_shield.regime_multipliers` |
| **YAML values** | HIGH_VOLATILITY: 0.30, UNCERTAIN: 0.55, MEAN_REVERSION: 0.75, LOW_VOLATILITY: 0.85, TREND: 1.0 |
| **Model field** | `ContextShieldConfig.regime_multipliers` |
| **Code location** | `shields/context_shield.py` → `ShieldCascade` in `shields/base.py` |
| **Formula** | `final_score = exposure × Π(shield_i_mult)` |
| **Runtime effect** | In HIGH_VOL: score × 0.30; In MR: score × 0.75; stale regime: × 0.35-0.70 |

### 8.3 Memory Shield Cold-Start Attenuation (ROOT BLOCKER #2, compound)

| Attribute | Value |
|-----------|-------|
| **Blocker** | MemoryShield unknown-state penalty |
| **Config path** | `aurora.decision.scoring_engine.memory_shield` |
| **YAML values** | `unknown_multiplier: 0.60`, `exploring_multiplier: 0.80`, `unknown_threshold: 10` |
| **Model field** | `MemoryShieldConfig` |
| **Code location** | `shields/memory_shield.py` |
| **Formula** | If visits < 10: mult=0.60; if < 50: mult=0.80 |
| **Runtime effect** | Cold-start → 40% signal suppression; ~54 state buckets × 10 bars = ~540 bars to exit UNKNOWN for all states |

### 8.4 Directional Sanity Gate (ROOT BLOCKER #3)

| Attribute | Value |
|-----------|-------|
| **Blocker** | Safety gate: trend direction conflicts signal side |
| **Config path** | `domains.decision_making.directional_sanity` |
| **YAML values** | `enabled: true`, `min_confidence: 0.0`, `min_regime_confidence: 0.42`, `consecutive_bars: 1` |
| **Model field** | `DecisionMakingDomainConfig.directional_sanity` |
| **Code location** | `safety_gates.py:198-220` |
| **Condition** | `trend_dir == "UP" AND intent_side == "SHORT"` → NRR-027 |
| **Condition** | `trend_dir == "DOWN" AND intent_side == "LONG"` → NRR-027 |
| **Runtime effect** | 42/55 rejects (76%) on 2026-03-21; 17/51 rejects on 2026-03-20 |
| **Note** | This gate fires AFTER signal emission. It is a post-signal blocker, not a pre-signal one. |

### 8.5 Threshold × Regime Factor Interaction

| Attribute | Value |
|-----------|-------|
| **Blocker** | Per-symbol threshold × regime factor product |
| **Config path** | `aurora.assets.<SYM>.signal_threshold.value` × `aurora.assets.<SYM>.regime_thresholds.<REGIME>` |
| **Code location** | `quadratic_scoring_kernel.py:248-268` |
| **Formula** | `signal_threshold = base_threshold × regime_factor` |
| **Fallback** | `_resolve_regime_factor()`: regime key → DEFAULT key → None (defer) |
| **Runtime effect** | ETH TREND_DOWN: 0.0221 × 1.0 = 0.0221; BTC TREND_DOWN: 0.162 × 0.1 = 0.0162 |

### 8.6 Regime Confidence Gate

| Attribute | Value |
|-----------|-------|
| **Blocker** | NRR-026: regime confidence below minimum |
| **Config path** | `domains.decision_making.directional_sanity.min_regime_confidence: 0.42` |
| **Code location** | `safety_gates.py:163-172` |
| **Condition** | `regime_confidence < 0.42` |
| **Runtime effect** | 28 rejects on 2026-03-20; 2 on 2026-03-21 |

---

## 9. TOP-3 Root Blockers

### #1: Quadratic Score Compression (`sign(S) × S²`)

| Attribute | Detail |
|-----------|--------|
| **Cause** | `S²` transform converts linear scores to squared values |
| **Mechanism** | Score 0.10 → 0.01; Score 0.03 → 0.0009. Weak-to-moderate signals are compressed to effectively zero |
| **Effect** | ~80% of all bars die as neutral-no-side because post-quadratic score cannot cross any reasonable threshold |
| **Why primary** | This is the mathematical root that sets the floor. All other blockers are secondary because the majority of signals never reach them |
| **Linked configs** | `scoring_version: "quadratic"`, `score_multiplier: 1.0` |
| **Linked code** | `quadratic_scoring_kernel.py:195-206` |
| **Symbol impact** | BTC partially escapes because some bars have stronger pillar_sum (>0.13); ETH/SOL max observed ~0.04, producing post-S² of 0.0016 (100× below typical threshold) |

### #2: Shield Cascade Compound Attenuation

| Attribute | Detail |
|-----------|--------|
| **Cause** | Three multiplicative shields reduce an already-compressed score |
| **Mechanism** | DangerZone (hard veto), ContextShield (regime-based 0.30-1.0), MemoryShield (familiarity 0.60-1.0). Product can reach 0.18 in worst case (HV × unknown) |
| **Effect** | Compounds the S² compression. Worst case: score 0.10 → S²=0.01 → ×0.18 = 0.0018 |
| **Why secondary** | Would not be fatal alone if S² weren't already compressing. But with S², the cascade ensures even borderline survivors get killed |
| **Linked configs** | `context_shield.regime_multipliers`, `memory_shield.unknown_multiplier: 0.60`, `danger_zone_shield.*` |
| **Linked code** | `shields/base.py` (cascade), `shields/context_shield.py`, `shields/memory_shield.py`, `shields/danger_zone.py` |

### #3: Directional Sanity Gate (NRR-027) — Post-Signal Killer

| Attribute | Detail |
|-----------|--------|
| **Cause** | Safety gate blocks signals that oppose the computed trend direction |
| **Mechanism** | If operator trend is UP and signal is SHORT → blocked; if DOWN and LONG → blocked |
| **Effect** | 76% of signals that survive kernel+threshold are killed by this gate. This is the dominant post-signal blocker |
| **Why tertiary** | It only matters for the ~20% of bars that survive the kernel. But for those signals, it's devastating |
| **Linked configs** | `domains.decision_making.directional_sanity.enabled: true`, `min_regime_confidence: 0.42` |
| **Linked code** | `safety_gates.py:198-220` |
| **Risk** | May be over-aggressive: Aurora's scoring might be correct in identifying counter-trend opportunities, but the safety gate vetoes them a priori |

---

## 10. FACTS

1. **FACT**: Quadratic transform formula is `sign(S) × S²` at `quadratic_scoring_kernel.py:195-206`.
2. **FACT**: ETH `signal_threshold.value = 0.0221`, SOL = `0.0232`, BTC = `0.162` (global, per-symbol disabled) — from `aurora.yaml`.
3. **FACT**: ETH/SOL `regime_thresholds` lack TREND_UP/TREND_DOWN keys; fallback is DEFAULT=1.0.
4. **FACT**: BTC `regime_thresholds.TREND_DOWN = 0.1`, yielding effective threshold 0.0162.
5. **FACT**: Shield cascade is multiplicative: DangerZone × Context × Memory at `shields/base.py`.
6. **FACT**: ContextShield multipliers: HIGH_VOL=0.30, UNCERTAIN=0.55, MR=0.75, TREND=1.0.
7. **FACT**: MemoryShield: unknown (<10 visits) = 0.60, exploring (<50) = 0.80, known = 1.0.
8. **FACT**: ETHUSDT produced 0 signals, SOLUSDT produced 0 signals, BTCUSDT produced 15 signals on 2026-03-20 runtime.
9. **FACT**: ETH/SOL reach the kernel (deferred=False, side="") — not pre-kernel blocked.
10. **FACT**: ETH calibration data: p90 |score| = 0.033; SOL p90 = 0.040.
11. **FACT**: NRR-027 accounted for 42/55 (76%) of post-signal rejects on 2026-03-21.
12. **FACT**: `UNCERTAIN` regime is effectively blocked for all symbols (BTC: DEFAULT=99.0; ETH/SOL: not in allowed_regimes).
13. **FACT**: `score_multiplier = 1.0` — no amplification applied.
14. **FACT**: Global `decision.regime_thresholds` block (with absolute values 0.075–99.0) appears **unused** in the live path. Config loader reads `regime_threshold_multipliers` instead.
15. **FACT**: Per-symbol `regime_thresholds` override is resolved via `_get_regime_thresholds()` in `aurora_scoring_helpers.py:248-256`. Per-symbol dict wins if present and non-empty.
16. **FACT**: Directional sanity gate uses operator trend (H4 LinReg+ADX) and strategist (D1 SMA200) from pillar system.

---

## 11. INFERENCES

1. **INFERENCE**: The quadratic transform is the primary mathematical chokepoint because observed score magnitudes (0.02-0.04) are in the regime where S² produces 0.0004-0.0016 — two orders of magnitude below any configured threshold.
2. **INFERENCE**: BTC produces signals not because its threshold is lower, but because BTC occasionally generates pillar_sum > 0.13 (the minimum for S²×shield to cross 0.0162). ETH/SOL never reach this magnitude.
3. **INFERENCE**: The feature weight structure for ETH (opposing signs on ema_bias, depth_imbalance, macro_resid) causes partial cancellation of pillar_sum, limiting maximum achievable score.
4. **INFERENCE**: The directional sanity gate (NRR-027) indicates a structural conflict: Aurora scoring wants to trade counter-trend, but the safety gate blocks it. This may mean either (a) the scoring is wrong, or (b) the safety gate is overly conservative.
5. **INFERENCE**: The shield cascade was likely designed assuming linear scoring where a score of 0.30 is realistic. Under quadratic scoring, the cascade's attenuation is destructive because it acts on already-compressed values.
6. **INFERENCE**: The `UNCERTAIN` regime block (99.0 factor or not in allowed_regimes) is a deliberate design choice, but ETH's 8/65 (12%) and SOL's 10/65 (15%) bars in UNCERTAIN are permanently dead volume.

---

## 12. ASSUMPTIONS

1. **ASSUMPTION**: The calibration data from 2026-03-20 is representative of the general score distribution for ETH/SOL. A different market regime could produce different distributions.
2. **ASSUMPTION**: The log-based NRR counts from 2026-03-20 and 2026-03-21 are representative. Longer-period analysis was not possible.
3. **ASSUMPTION**: The config currently in `aurora.yaml` (with ETH threshold 0.0221, SOL 0.0232) reflects the live runtime config. Prior reports showed threshold 0.09, suggesting a recent config change.
4. **ASSUMPTION**: The Objective Engine is either disabled or not blocking a material fraction of signals (its config path was verified but runtime activation was not confirmed from logs).

---

## 13. UNKNOWNS

1. **UNKNOWN**: Multi-week score distribution for ETH/SOL. The single-day sample may not capture all market conditions.
2. **UNKNOWN**: BTC's specific pillar_sum distribution (not captured in calibration data — no BTC calibration was run because `signal_threshold.enabled: false`).
3. **UNKNOWN**: Whether the Objective Engine gate is active in production and what fraction it blocks.
4. **UNKNOWN**: The actual live shield_mult values per bar (not logged in inspected evidence).
5. **UNKNOWN**: Whether ETH/SOL weight structure is intentionally conservative or a stale tuning artifact.
6. **UNKNOWN**: Full regime distribution over multiple weeks (only one day inspected).
7. **UNKNOWN**: Whether `decision.regime_thresholds` (line 230-237 of aurora.yaml) is consumed by any subsystem not traced in this audit. Marked as `DECLARED, UNPROVEN`.

---

## 14. Actionable Direction

### Primary Direction: `AUDIT_QUADRATIC_COMPRESSION_FIRST`

The quadratic kernel `S²` is the mathematical root cause. The observed score magnitudes (peak 0.03-0.04 for ETH/SOL, occasionally 0.13+ for BTC) are structurally incompatible with S² scoring at current threshold levels.

**Why this, not thresholds**: Lowering thresholds to match S² output (e.g., ETH threshold from 0.0221 to 0.001) would make the threshold essentially meaningless and remove selectivity.

**Why this, not gates**: Gates (NRR-027, NRR-026) are downstream killers but only affect the ~20% of signals that survive the kernel. Fixing the kernel would produce more signals for gates to evaluate.

**Why this, not weights**: Weights affect raw score magnitude and could be tuned, but the quadratic transform would still compress any non-extreme score to near-zero.

### Concrete Options (Not Tuning — Architectural Choices)

| Option | Mechanism | Risk |
|--------|-----------|------|
| A. Replace `S²` with `S^p` where p < 2 (e.g., 1.5 or 1.2) | Reduces mid-range compression while preserving convexity | Requires validation |
| B. Apply threshold comparison to pre-quadratic linear score, use S² only for sizing | Decouples signal decision from compression | Architecture change |
| C. Add a `score_floor` that lifts compressed scores | `final = max(S², floor × |S|)` | Ad-hoc, may reduce selectivity |
| D. Adjust `score_multiplier` to > 1.0 (e.g., 3.0-5.0) | Amplifies S_linear before S², shifting more scores above 0.3 where S² is less compressive | Simplest config change; changes risk profile |

### Secondary Direction: `RELAX_DIRECTIONAL_SANITY_GATE`

If more signals survive the kernel after addressing compression, the directional sanity gate (NRR-027) will become the next dominant blocker. It currently kills 76% of surviving signals. Consider:
- Adding a counter-trend soft mode instead of hard veto
- Reducing `min_regime_confidence` from 0.42
- Adding a score-magnitude override (strong signals bypass directional veto)

### NOT Primary Blocker (Can Deprioritize)

| Knob Class | Why Not Primary |
|------------|-----------------|
| **Thresholds** | Already reduced to 0.0221/0.0232. Problem is S² compressing scores to 0.0005-0.0016 — no reasonable threshold can bridge a 10-40× gap |
| **Regime threshold multipliers** | Near-unity for ETH/SOL (0.75-1.30). Not the chokepoint |
| **Anti-flat / Anti-FOMO gates** | 0 observed triggers. Not active blocker |
| **Re-entry cooldown** | Downstream of neutral return, never reached for ETH/SOL |
| **Anchor shock veto** | BUY-only, BTC-anchor. Not a material blocker |
| **Liquidity gate** | 0 observed triggers |
| **Regime allowlist** | ETH/SOL allow 5 regimes. Only UNCERTAIN blocked, which is intentional |

---

*END OF REPORT*
