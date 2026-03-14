# FINAL QUADRATIC CONVERSION AUDIT
**Aurora / Phenix — Quadratic Scoring Runtime Transition**
**Audit Date:** 2026-03-13
**Auditor Role:** Principal Quant Runtime Auditor / Scoring Migration Architect
**Method:** Code-first. Docs as secondary hints only. No implementations in this pass.

---

## 1. Executive Summary

**Current runtime truth:** Quadratic scoring is **NOT live**. `scoring_version: "v2"` is set in [config/aurora/strategies/aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) (line 274). The system runs the [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#74-326) (linear v2) as the active production kernel.

**Quadratic status:** All infrastructure for Quadratic exists — kernel, rollout contract, shadow evaluation, pillar indicators, pillar backfill service, PillarState in FE types. However, the core feed path from pillar computation → [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) → QuadraticScoringKernel is **NOT wired end-to-end in production config**. The pillar system exists in [pillar_indicators.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py) and is configured in [domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml), but the [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) feature key is not emitted into the live `EVT:FEATURES_CALCULATED` payload in a way that the quadratic kernel can consume from real bars.

**Pre-conditions before flip:** Four structural gaps must be closed. See Section 12.

---

## 2. Current Active Scoring Truth

### Source of truth (code-verified, CONFIRMED)

| Item | Value | Source |
|---|---|---|
| Active scoring_version | `"v2"` | [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) line 274 |
| Active kernel class | [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#74-326) | [aurora_config_loader.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_config_loader.py) line 199 (condition: `effective_live_scoring_version == "quadratic"` → NOT met) |
| Rollout mode resolved | `V2_LIVE` | [quadratic_rollout.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py) QuadraticRolloutMode enum |
| Shadow mode active? | `false` (no [quadratic_rollout](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#285-326) block in aurora.yaml) | [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) grep: no [quadratic_rollout](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#285-326) key found |
| `scoring_engine` config | None | [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml): no `scoring_engine` block → `shadow_scoring_engine_cfg=None` |

**How the kernel is selected (code path):**
1. `aurora_config_loader.py:_load_config()` calls [resolve_requested_quadratic_rollout(decision)](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#188-231) (line 182)
2. [resolve_requested_quadratic_rollout()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#188-231) reads `decision.scoring_version` → `"v2"`
3. Since `requested_scoring_version != "quadratic"`, `effective_live_scoring_version = "v2"`
4. `if requested_rollout.effective_live_scoring_version == "quadratic":` → **FALSE**
5. Handler gets [AuroraScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#74-326) (default, not set explicitly; the `scoring_kernel_cls` is only set to [QuadraticScoringKernel](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py#65-234) in the `if` branch)

> **CONFIRMED: v2 is the live runtime. Quadratic is NOT active.**

> **CRITICAL**: [aurora_config_loader.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_config_loader.py) has no explicit `else: self.scoring_kernel_cls = AuroraScoringKernel`. If `effective_live_scoring_version != "quadratic"`, `scoring_kernel_cls` must be set elsewhere (likely in [__init__](file:///c:/Users/user/Music/Phenix/apps/reference/domains/regime_detector/regime_detector.py#54-158) of `AuroraHandler`). This is an initialization order risk — **LIKELY** that it defaults correctly, but **NOT VERIFIED** without reading [aurora_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py) init.

---

## 3. Quadratic Specification Map

| Source type | File | What it specifies | Trusted? | Notes |
|---|---|---|---|---|
| **code** | [quadratic_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py) | Formula: `Exposure = sign(Σ) × Σ²`; shield cascade; defer semantics | YES | 327 lines, fully readable |
| **code** | [quadratic_rollout.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py) | Rollout modes (V2_LIVE, SHADOW, LIVE, ROLLBACK); state machine; shadow evaluation | YES | 360 lines |
| **code** | [aurora_config_loader.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_config_loader.py) | How kernel class is selected; rollout resolution path | YES | Lines 181–213 |
| **code** | [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) | Local v2 fallback when quadratic crashes (lines 396–407); shadow evaluation at every bar (line 383) | YES | CRITICAL path |
| **code** | [pillar_indicators.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py) | Tactician (M15 ROC), Operator (H4 LinReg×ADX), Strategist (D1 SMA200); [aggregate_pillars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py#356-392) | YES | 392 lines, pure math |
| **code** | [pillar_backfill.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py) | D1/H4/M15 historical candle fetch; [warmup_pillars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#206-244) | YES | 273 lines |
| **code** | [feature_engineering.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py) | PillarState references, `_pillar_states`, HTF import handler, pillar timeframe label map | YES | Pillar types initialized; compute wiring NOT confirmed |
| **config** | [domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml) lines 324–365 | Pillar config: enabled=true, tactician/operator/strategist, weights, backfill | YES (config exists) | Consumed by FE? NOT VERIFIED end-to-end |
| **config** | [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) line 274 | `scoring_version: "v2"` — THE GATE KEEPER | YES | No [quadratic_rollout](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#285-326) block present |
| **test** | [test_quadratic_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py) | 3 classes, 6 tests: sign transform, defer, psi_vector | YES (exists) | Only covers kernel math in isolation, NOT pipeline |
| **doc** | [docs/SCORING.md](file:///c:/Users/user/Music/Phenix/docs/SCORING.md) | Scoring concepts | NOT VERIFIED | Not read in this audit |
| **doc** | [config/docs/scoring_passport.md](file:///c:/Users/user/Music/Phenix/config/docs/scoring_passport.md) | Passport | NOT VERIFIED | Not read in this audit |
| **doc** | [docs/audits/current_warmup_quadratic_scoring_decision_lifecycle_audit_2026-03-10.md](file:///c:/Users/user/Music/Phenix/docs/audits/current_warmup_quadratic_scoring_decision_lifecycle_audit_2026-03-10.md) | Previous audit | NOT VERIFIED | May contain stale info |

---

## 4. V2 vs Quadratic: Conceptual and Runtime Differences

| Aspect | V2 Implementation | Quadratic Implementation | Same/Different | Runtime Impact | Migration Consequence |
|---|---|---|---|---|---|
| **Feature inputs** | `obi`, `tfi`, `delta_price`, [ema_bias](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#422-426), [depth_imbalance](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#466-469), `macro_resid`, `absorption`, [volume_spike](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#427-431), [volatility_state](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#442-446) (5m tick features) | [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) = weighted aggregate of M15/H4/D1 pillar indicators | **DIFFERENT** | Quadratic ignores per-tick features; v2 uses them directly | Must ensure [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) is in features dict before flip |
| **Multi-timeframe structure** | Single timeframe: 5m basis only | Three timeframes: M15 (Tactician), H4 (Operator), D1 (Strategist) | **DIFFERENT** | Quadratic requires HTF data; v2 does not | HTF backfill and pillar readiness become hard prerequisites |
| **Score formula** | `dir × (1 + α × strength)` — linear with strength modifier | [sign(Σ) × Σ²](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py#966-1422) — quadratic, squaring conviction | **DIFFERENT** | V2 is linear/continuous; Quadratic penalizes weak signals aggressively (near-zero zone) | Score magnitudes change; thresholds must be re-calibrated |
| **Confidence** | Implicit: `abs(score)/threshold_factor` computed in [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) line 726 | Shield multiplier ∈ [0,1] cascaded as explicit confidence | **DIFFERENT** | V2 confidence is post-hoc; Quadratic has explicit shield cascade | Shield cascade must be configured (currently NullShield when scoring_engine absent) |
| **Threshold logic** | `base_threshold × regime_factor × side_bias_mult` | Same threshold math reused (lines 207–224 in quadratic kernel) | **SAME** | No change | No threshold re-wiring needed |
| **Regime usage** | Regime factor multiplies threshold; regime gating via allowlist | Same regime factor; same allowlist | **SAME** | No structural change | No regime-threshold migration needed |
| **Readiness requirements** | FE warmup: `full_ready` for 5m features | FE warmup PLUS pillar readiness: all 3 pillars must return non-None | **DIFFERENT** | Quadratic has higher readiness bar; will defer if any pillar not ready | Pillar warmup gate must be tested |
| **Startup hydration** | 5m feature EMA/volume warmup (fast, ~minutes) | D1 SMA200 needs 200 daily bars (via [PillarBackfillService](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#62-273), async [warmup_pillars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#206-244)) | **DIFFERENT** | Quadratic has slower startup; `backfill.enabled=true` in config | Backfill wiring must be verified for live mode |
| **Execution influence** | Score → side determination → intent routing → order lifecycle | Same path; shield_multiplier additionally exposed in `shield_breakdown` | **SAME structure, different score values** | Score magnitude changes affect threshold-crossing frequency | Entry rate will change post-flip |
| **Rollback/fallback** | None (the stable path) | LOCAL: v2 fallback if Quadratic kernel throws exception ([aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) lines 396–407); GLOBAL: `rollback_armed=true` in rollout config | **DIFFERENT** | v2 fallback exists silently on crash | See Section 11 |
| **Observability** | [psi_vector](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#80-91) has `dir_score`, [strength_score](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py#97-239), `final_score` | [psi_vector](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#80-91) has `scoring_engine="quadratic_v1"`, `s_linear`, `s_clamped`, `final_exposure`, `shield_multiplier`, `shield_reasons` | **DIFFERENT** | Quadratic has richer explainability | Dashboards/alerts need quadratic field awareness |

---

## 5. Multi-Timeframe Architecture Audit

### User Hypothesis: 4 temporal layers
- Global strategic trend ≈ 200 days
- Smaller/intermediate trend ≈ monthly / H4 scale
- Tactical trend ≈ M15
- Operational trend ≈ 5m

### What the code actually implements

**D1 / ~200 days — CONFIRMED IN CODE, NOT IN RUNTIME**
- [compute_strategist()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py#316-350) in [pillar_indicators.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py): `Price vs SMA(200)` on D1 closes
- SMA period = 200 (configurable in [domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml): `sma_period: 200`)
- Requires 200 D1 bars (backfill)
- **BUT**: Not confirmed to feed into [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) in live FE output

**H4 — CONFIRMED IN CODE, NOT IN RUNTIME**
- [compute_operator()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py#256-294): `LinReg slope × ADX_weight` on H4 bars
- LinReg period=20 H4 bars, ADX period=14 H4 bars
- Requires backfill of ≥50 H4 bars

**M15 — CONFIRMED IN CODE, NOT IN RUNTIME**
- [compute_tactician()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_indicators.py#82-102): `ROC(14)` on M15 closes
- Requires ≥20 M15 bars

**5m (operational) — NOT PRESENT IN QUADRATIC**
- V2 uses 5m features as its ONLY source
- Quadratic as implemented uses [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) from M15+H4+D1 → no explicit 5m pillar
- The 5m basis still drives: liquidity gate, vol gates, shields, regime detection
- There is **NO "Operator 5m" pillar** in the current implementation

### The gap: 4 layers vs 3
The design idea mentions 4 layers. The code implements 3 (M15, H4, D1). The 5m level is NOT a pillar — it's the basis timeframe for gates and regime, but not contributing to [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78).

### Verdict by sub-question

| Claim | Verdict |
|---|---|
| Global strategic trend ≈ 200 days (D1 SMA200) | **PARTIALLY IMPLEMENTED** — code exists, runtime wiring not verified |
| Intermediate trend ≈ H4 (Operator) | **PARTIALLY IMPLEMENTED** — code exists, runtime wiring not verified |
| Tactical trend ≈ M15 (Tactician) | **PARTIALLY IMPLEMENTED** — code exists, runtime wiring not verified |
| Operational trend ≈ 5m | **ONLY IN DOCS / NOT IN CODE AS PILLAR** — 5m is basis, not a pillar |
| Confidence assembled from 4 layers | **NOT IMPLEMENTED** — confidence comes from shield cascade (currently NullShield), not from pillar layer convergence |
| Dynamic confidence correction | **PARTIALLY IMPLEMENTED** — shield cascade architecture exists; shields (DangerZone, Context, Memory) can attenuate; but `shield_enabled=false` without `scoring_engine` config |
| Better noise filtering than v2 | **NOT VERIFIED** — requires live shadow comparison |

---

## 6. Confidence Construction Audit

### V2 confidence (code-verified)
- Computed in [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) line 726: `confidence = min(1.0, abs(score) / factor) if factor > 0 else 0.5`
- This is a DERIVED, POST-HOC value used only for `entry_plan_calculator.compute(pillar_confidence=confidence)`
- It does NOT feed back into the scoring itself

### Quadratic confidence (code-verified)
- `shield_multiplier ∈ [0, 1]` from shield cascade
- `final_score = raw_exposure × shield_multiplier`
- Shields available: `DangerZoneShield`, `ContextShield`, `MemoryShield`
- **Current state**: [_build_shield_cascade()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#173-232) returns `NullShield()` when `cfg.shield_enabled=False` (line 180 in [aurora_scoring_helpers.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py))
- No `scoring_engine` block in [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml) → `shadow_scoring_engine_cfg=None` → shield cascade = NullShield

**Conclusion:** Quadratic's confidence/shield system EXISTS in code but is INOPERATIVE because there is no `scoring_engine` config and `shield_enabled` defaults to False. `final_score = sign(Σ)×Σ²×1.0` — the shield multiplier is always 1.0.

> **CONFIRMED: Confidence/shield system is not configured. Quadratic currently runs with NullShield.**

---

## 7. Readiness / Warmup / Hydration Requirements

### V2 readiness (code-verified, CONFIRMED)
- `state.warmup_full_ready` must be True (from FE `warmup.full_ready`)
- Essential features: `obi`, `delta_price`, `macro_resid` must be in `warmup_readiness`
- Enforcement: `fail_fast` (blocks scoring if not ready)
- Cold-start gate: `basis_required_bars` from strategy compatibility profile

### Quadratic readiness (code-verified, status: NOT CONFIRMED END-TO-END)
- Kernel defers with `reason="PILLAR_WARMUP"` if `features["pillar_sum"]` is None/missing
- PillarBackfillService fetches D1(200 bars), H4(100 bars), M15(50 bars) at startup
- [_on_htf_bars_imported](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#783-870) in FE handles `EVT:HTF_BARS_IMPORTED` to seed pillar buffers
- **CRITICAL GAPS:**
  1. Is the pillar computation actually called on each bar close event? NOT VERIFIED in FE's [on_bar_closed()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#650-782) (FE code read to line 800, pillar calculation path not traced to completion)
  2. Is [pillar_sum](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py#72-78) emitted into `EVT:FEATURES_CALCULATED` payload? NOT VERIFIED
  3. Is `PillarBackfillService.warmup_pillars()` called during live startup? NOT VERIFIED in handler init

### Hydration summary

| Requirement | V2 | Quadratic |
|---|---|---|
| Fastest warmup | Minutes (5m EMA/vol) | Minutes (5m features) + Hours (H4 ≥50 bars) + 200 days (D1 SMA) |
| Live startup fetch needed | No | Yes (D1/H4/M15 backfill via exchange API) |
| Fail-closed on missing | Yes (fail_fast) | Yes (pillar_sum missing → PILLAR_WARMUP defer) |
| Backfill validated | N/A | Configured in domains.yaml, implementation unverified end-to-end |

---

## 8. Execution and Order Lifecycle Impact

### Quadratic influence path (code-verified)
`QuadraticScoringKernel.compute()` → `ScoringResult.score` → `result.side` → [_emit_signal()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py#966-1422) → `EVT:STRATEGY_SIGNAL_PRODUCED` → strategy_gateway → execution

The score magnitude change (quadratic compression at low Σ, amplification at high Σ) will affect:
- **Entry frequency**: Weak signals → score²  much lower → fewer threshold crossings
- **Exit frequency**: Same. Score must exceed threshold; for small noise signals, quadratic makes it harder to cross → better noise filtering
- **shield_multiplier** (when shields are enabled): additional attenuator on execution size path via [confidence](file:///c:/Users/user/Music/Phenix/apps/reference/domains/regime_detector/regime_detector.py#170-208) calculation

### Strategy gateway (code search result)
- [strategy_gateway.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py) EXISTS in `apps/reference/domains/decision_making/`
- Grep for quadratic/scoring returned NO results in this file → **NOT VERIFIED** if it passes any scoring metadata downstream
- Likely operates on `side` and `signal_threshold` only, not on raw score values

### V2 assumptions still alive in execution downstream
- `entry_plan_calculator.compute(pillar_confidence=confidence)` uses the DERIVED v2-style confidence regardless of kernel
- This confidence computation (line 726 in `aurora_decision.py`) is used with BOTH v2 and quadratic kernels unchanged
- For quadratic, `score_for_conf = float(result.score)` where `result.score = sign(Σ)×Σ²` — the confidence formula still divides by `threshold_factor`, which is correct structurally but was designed for linear scores

---

## 9. MR / md_amr Compatibility Impact

### Direct Quadratic impact: NO
- `mean_reversion` and `md_amr` strategies have their own handlers
- They do not use `AuroraHandler` or `AuroraScoringKernel`/`QuadraticScoringKernel`
- `strategy_gateway.py` routes intents by strategy_id

### Indirect impact: POTENTIAL

| Shared component | Risk |
|---|---|
| `feature_engineering.py` | SHARED. FE serves all strategies. Pillar computation adds CPU overhead per bar; M15/H4/D1 bars are calculated for aurora but FE `on_bar_closed` fires for all symbols/timeframes. MR/md_amr get bar-closed events too. |
| QoS | `apply_to_strategies: ["aurora", "md_amr"]` in domains.yaml. QoS is shared; intent spam from Aurora quadratic scoring differences won't directly affect MR, but shared intent counter could. |
| Regime detection | SHARED. `regime_detector.py` serves all strategies. No Quadratic impact here — regime stays SMA+ATR on 5m. |
| Startup warmup timing | Quadratic needs D1 backfill at startup. If backfill fails, Aurora blocks but MR/md_amr should proceed independently. |
| FE `_pillar_states` | Per-symbol, per-timeframe. New HTF bars being processed adds compute but MR does not consume pillar data. |

**Verdict:** Full Aurora Quadratic conversion should NOT break MR or md_amr if FE pillar compute is correctly isolated per-symbol and HTF failures fail-closed only for Aurora.

---

## 10. Legacy V2 Surfaces Still Alive

| Surface | File | Status | Live-critical? | Migration action |
|---|---|---|---|---|
| `AuroraScoringKernel` | `aurora_scoring_kernel.py` | ACTIVE (current production kernel) | YES | Becomes fallback-only after flip; do NOT delete |
| `scoring_direction_strength_v1.py` | `scoring_direction_strength_v1.py` | Called by `AuroraScoringKernel`; references `SignalScoreV2` | YES (transitive) | Becomes fallback-only |
| `signal_score_v2.py` | `signal_score_v2.py` (inferred from imports) | Called by `compute_direction_strength_score()` | YES (transitive) | Becomes fallback-only |
| `scoring_version: "v2"` | `aurora.yaml` line 274 | THE GATE KEEPER | YES | Must change to `"quadratic"` to activate |
| `signal_weights` (per-symbol config) | `aurora.yaml` assets.{sym}.weights | Used by v2 only (directional features weighted) | YES for v2 | Quadratic does NOT use signal_weights; these become dead config |
| `feature_neutrals` | `aurora.yaml` decision.feature_neutrals | Used by v2 only | YES for v2 | Quadratic does NOT use feature_neutrals; becomes dead config |
| `direction_strength_cfg` | `aurora.yaml` decision.direction_strength_scoring | Used by v2 only | YES for v2 | Quadratic does NOT use direction_strength; becomes dead config |
| `essential_features` | `aurora.yaml` decision.essential_features | Used by v2 kernel to check readiness | YES for v2 | Quadratic ignores this; readiness check is `pillar_sum` presence |
| Local v2 fallback | `aurora_decision.py` lines 396–407 | SILENT FALLBACK on QuadraticKernel exception | YES (as silent risk) | MUST be removed or made explicit/alerting before final flip |

---

## 11. Silent Fallback / Drift / Ambiguity Findings

### Finding 1: CRITICAL — Local v2 fallback in quadratic crash path
**Location:** `aurora_decision.py` lines 396–407
```python
except Exception as _kernel_exc:
    if self.scoring_kernel_cls is QuadraticScoringKernel:
        self.logger.error(
            "[%s] QUADRATIC_FALLBACK: %s — falling back to AuroraScoringKernel (local only)",
            symbol, _kernel_exc,
        )
        try:
            result = AuroraScoringKernel.compute(**_compute_kwargs)
        except Exception as _fallback_exc:
            ...
            raise _fallback_exc from _kernel_exc
```
**Risk:** If Quadratic kernel throws for ANY reason (pillar_sum type error, shield exception, config issue), the system silently falls back to v2 **without any circuit breaker**. Trading continues on v2 behavior while logs say "QUADRATIC" mode is active. This is a dual-identity runtime risk.

### Finding 2: HIGH — `scoring_kernel_cls` init path unverified
**Location:** `aurora_config_loader.py` — the `else:` branch (when `effective_live_scoring_version != "quadratic"`) does NOT explicitly set `self.scoring_kernel_cls = AuroraScoringKernel`. If `AuroraHandler.__init__` does not set a default before calling `_load_config()`, and if `scoring_kernel_cls` attribute is only set in the `if` branch, then v2 path leaves `scoring_kernel_cls` unset. **LIKELY** defaulted in handler init — **NOT VERIFIED**.

### Finding 3: HIGH — `pillar_sum` emission into FE output not confirmed
**Location:** `feature_engineering.py` `_calculate_and_emit_features_for_tf()` (function not read in audit — file is 1850 lines, read to line 800)
The `_pillar_states` dict exists. The HTF import handler exists. But whether `pillar_sum` key is actually emitted into the `EVT:FEATURES_CALCULATED` payload's `features` dict is **NOT VERIFIED**.

### Finding 4: MEDIUM — Shield cascade inoperative by default
**Location:** `aurora_scoring_helpers.py` `_build_shield_cascade()` line 180
`if not cfg or not getattr(cfg, "shield_enabled", False): return NullShield()`
No `scoring_engine` block in `aurora.yaml` → `cfg=None` → always NullShield.
This means Quadratic will run without any signal attenuation even if `scoring_version: "quadratic"` is set today.

### Finding 5: MEDIUM — Shadow evaluation computed but likely NOT persisted/emitted
**Location:** `aurora_decision.py` lines 383–390
`quadratic_shadow_evaluation = evaluate_quadratic_shadow(...)` is called on every bar, but:
- `quadratic_shadow_evaluation` result stored in a local variable
- NOT emitted to any `EVT:` nor stored on state
- Since `shadow_requested=False` (no `quadratic_rollout` block), `evaluate_quadratic_shadow()` returns `NOT_REQUESTED` immediately
- Effectively: shadow evaluation call exists in code but is fully dormant

### Finding 6: LOW — `scoring_version` comment says `"v1" (Legacy), "v2" (Linear), "quadratic" (Phase 9)` but `_VALID_SCORING_VERSIONS = {"v2", "quadratic"}` rejects `"v1"` with CRITICAL log
**Location:** `aurora.yaml` lines 272–274, `quadratic_rollout.py` lines 17–18
Comment implies "v1" is still conceptually supported but code rejects it. Clean the comment.

---

## 12. Critical Blockers Before Full Quadratic Conversion

### B1 [CRITICAL] — `pillar_sum` emission path NOT verified
**Required:** Confirm `feature_engineering.py`'s bar-close handler computes pillars and emits `pillar_sum` into the `features` dict of `EVT:FEATURES_CALCULATED`. Without this, every bar will result in `defer_reason="PILLAR_WARMUP"` — zero signals.
**Files:** `feature_engineering.py` (lines 800–1850 not audited), `types.py` (PillarState)
**Action:** Trace `_calculate_and_emit_features_for_tf()` → confirm `pillar_sum` in emitted payload.

### B2 [CRITICAL] — Remove or harden the silent local v2 fallback
**Required:** The `except QuadraticKernel: → AuroraScoringKernel.compute()` fallback at `aurora_decision.py:396-407` is invisible to ops. Two options:
- (A) Keep it but emit `EVT:QUADRATIC_FALLBACK_ACTIVATED` and increment a metric, then halt signal for the bar (don't silently trade on old kernel)
- (B) Remove it entirely (strict mode) — if quadratic crashes, the bar is skipped

**Action:** Decision required. Cannot proceed without this.

### B3 [CRITICAL] — `scoring_kernel_cls` default initialization not confirmed
**Required:** Confirm `AuroraHandler.__init__` sets `self.scoring_kernel_cls = AuroraScoringKernel` before `_load_config()` is called. If not, `scoring_kernel_cls` will be undefined when `effective_live_scoring_version == "v2"` and handler will crash on first bar.
**Action:** Read `aurora_handler.py` lines that were cut off in this audit.

### B4 [CRITICAL] — PillarBackfillService startup call not confirmed
**Required:** Confirm that `PillarBackfillService.warmup_pillars()` is called during Aurora live startup and its result seeds FE pillar buffers via `EVT:HTF_BARS_IMPORTED`. Without this, D1 SMA(200) will never be ready in live mode (would need 200 days of live 5m bars to organically fill).
**Action:** Trace startup orchestration code (startup_warmup? app init?).

---

## 13. High-Priority Cleanup Before Conversion

### H1 [HIGH] — Configure `scoring_engine` block in `aurora.yaml`
Without it, `shield_cascade = NullShield` and Quadratic provides NO signal attenuation beyond the quadratic transform. At minimum, add `scoring_engine` with `shield_enabled: false` (explicit), or configure at least `DangerZoneShield` for safety.

### H2 [HIGH] — Add `quadratic_rollout` block to `aurora.yaml` for shadow mode
Before flipping live, run shadow mode: `shadow_enabled: true`, `rollback_armed: false`.
This enables `evaluate_quadratic_shadow()` to run and log quadratic scores alongside v2 without affecting trades. Required for validation dataset.

### H3 [HIGH] — Calibrate `pillar_weights` for live conditions
`domains.yaml`: `weights: {tactician: 0.30, operator: 0.40, strategist: 0.30}`. These are defaults from design, NOT empirically calibrated. `pillar_sum` range affects how often `sign(Σ)×Σ²` crosses threshold.

### H4 [HIGH] — `signal_weights`, `feature_neutrals`, `direction_strength_scoring` sunset plan
These keys in `aurora.yaml` are consumed ONLY by `AuroraScoringKernel`. After flip, they become dead config. Document explicitly that they're kept only for fallback path. Do NOT remove until fallback path is removed.

### H5 [HIGH] — Write integration test: pillar_sum → engine → side
The existing `test_quadratic_scoring_kernel.py` (91 lines) only tests the kernel with a STATIC `features={"pillar_sum": 0.5}` dict. There are no tests for:
- FE → pillar_sum emission pipeline
- HTF import → pillar warmup
- End-to-end: bar → FE → pillar_sum → kernel → side

---

## 14. Recommended Final Migration Sequence

1. **[Read B1-B4 to completion]** — Audit remaining 1050 lines of `feature_engineering.py` + `aurora_handler.py` init to close NOT VERIFIED gaps.

2. **[Shadow mode]** — Add `quadratic_rollout: {shadow_enabled: true, rollback_armed: false}` to `aurora.yaml`. Deploy. Monitor shadow evaluation logs for ≥1 week. Confirm `pillar_sum` appears in features, quadratic scores are non-zero, distribution is reasonable.

3. **[Shield configuration]** — Configure `scoring_engine` block with `shield_enabled: true` and at minimum `danger_zone_shield`. Test shield cascade in shadow mode.

4. **[Hardened fallback]** — Resolve B2: either add metric+event emission on quadratic crash fallback, or switch to fail-closed (recommended for prod).

5. **[Integration tests]** — Write H5 tests. Must pass before flip.

6. **[Threshold recalibration]** — Quadratic scores are in `[0,1]` range compressed quadratically. Check if current `signal_threshold: 0.162` and per-regime multipliers are appropriate for quadratic score space. Shadow data will inform this.

7. **[Final flip]** — Change `scoring_version: "v2"` → `"quadratic"` in `aurora.yaml`. Deploy with `rollback_armed: false`. Monitor live for ≥1 session.

8. **[Rollback plan]** — If issues: set `scoring_version: "quadratic"` + `quadratic_rollout: {rollback_armed: true}` → immediately falls back to v2 live. Quadratic becomes shadow.

9. **[Cleanup]** — After 2+ weeks stable: deprecate local v2 fallback (B2 complete). Mark `signal_weights`, `feature_neutrals`, `direction_strength_scoring` as deprecated.

---

## 15. Final Go / No-Go Verdict

**GO / NO-GO FOR FULL CONVERSION RIGHT NOW:** ❌ **NO-GO**

**Blocking reasons:**
1. B1: pillar_sum emission not confirmed — risk of 100% deferred signals post-flip
2. B2: silent v2 fallback on quadratic crash — ops blindness risk
3. B3: scoring_kernel_cls init order not confirmed — crash risk
4. B4: startup backfill not confirmed wired — D1 pillar never ready in live

---

## F. FINAL VERDICT BLOCK

### WHAT QUADRATIC REALLY IS IN THIS REPO
A fully-designed, partially-wired alternative scoring engine that:
- Transforms `pillar_sum` (weighted aggregate of M15/H4/D1 indicators) via `sign(Σ)×Σ²`
- Has a complete rollout state machine (shadow/live/rollback modes)
- Has a shield cascade architecture (DangerZone, Context, Memory shields) for signal attenuation
- Has a pillar indicator library (Tactician/Operator/Strategist) with pure math functions
- Has a pillar backfill service for live startup hydration
- Uses the SAME threshold logic and side hysteresis as v2 (low migration risk there)

### WHAT IT IS NOT
- NOT a 4-layer temporal system (3 pillars: M15+H4+D1; 5m is a gate, not a pillar)
- NOT live (scoring_version="v2")
- NOT confirmed to compute and emit `pillar_sum` in real FE bars
- NOT equipped with active shields (NullShield by default, no scoring_engine config)
- NOT validated with live data (no shadow telemetry has been enabled)
- NOT tested for end-to-end pipeline (only kernel unit tests exist)
- NOT better at filtering noise than v2 in a verified, measured sense

### WHAT MUST BE TRUE BEFORE FULL SWITCH
1. `pillar_sum` confirmed in live `EVT:FEATURES_CALCULATED` payload
2. PillarBackfillService wired in live startup
3. Shadow mode run ≥1 week, quadratic scores reasonable
4. Local v2 crash fallback hardened (metric + event + optional fail-closed)
5. `scoring_kernel_cls` default initialization confirmed safe
6. At least `DangerZoneShield` configured in `scoring_engine`
7. Integration tests written and passing

### WHAT OLD V2 SURFACES MUST DIE (sequence-dependent)
- `scoring_version: "v2"` comment (after flip)
- Local crash fallback to AuroraScoringKernel (after B2 resolved)
- `signal_weights` / `feature_neutrals` / `direction_strength_scoring` config (after fallback removed, months later)
- `AuroraScoringKernel` and `scoring_direction_strength_v1.py` imports as live kernel (demote to fallback-only, eventually archive)
- Test `test_aurora_scoring_kernel.py` / `test_direction_strength_scoring_v1.py` become regression guard for fallback only

### GO / NO-GO FOR FULL CONVERSION RIGHT NOW
❌ **NO-GO** — 4 critical gaps (B1–B4) must be verified and closed first.

Estimated readiness after B1–B4 closed + shadow run: **2–4 weeks** of focused work.
