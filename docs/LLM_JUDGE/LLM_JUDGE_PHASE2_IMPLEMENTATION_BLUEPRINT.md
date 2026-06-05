# LLM Judge Phase 2 — Implementation Blueprint

**Date**: 2026-04-13
**Artifact type**: Final Phase 2 implementation blueprint
**Artifact status**: Implementation-ready planning SSOT for Phase 2 coding work
**Code changes**: None (planning document only)
**Governing concept**: `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` (supplied authority, not yet committed)
**Frozen Phase 1 input**: `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_IMPLEMENTATION_BLUEPRINT.md`

---

## 1. Executive Verdict

**GO-WITH-CONSTRAINTS**

Phase 2 implementation planning is ready with two constraints:

1. **Phase 1 prerequisite**: Phase 1 code (contracts, schemas, config, verb registry) must be implemented and passing before Phase 2 coding begins. Phase 2 depends on `ExpertOutput`, `EntryVerdict`, `JudgeCortexConfig`, and the `judge/` sub-package existing in the repo.
2. **Concept adoption prerequisite**: The concept document must be committed to the repo (Phase 1 Subpackage 1A) before Phase 2 coding begins. This is inherited from the Phase 1 blueprint.

No blocking semantic unknowns remain for Phase 2 scope. Historical legacy behavior is fully recoverable from git history and current config surfaces. The two experts to revive — `signal_weights_expert` and `feature_neutrals_expert` — have clear evidence-based specifications. Both are ENTRY-only, shadow-only, and bounded within alpha_search-aligned placement.

---

## 2. Authority Model

### 2.1 Supplied Semantic Authority

The concept artifact `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` defines Phase 2 as **"Legacy Expert Revival"** with these directives:

- Recover `signal_weights_expert` and `feature_neutrals_expert`
- These experts run in shadow mode only
- Legacy logic is revived as explicit experts, never as hidden Aurora math
- `alpha_search` is the accepted shadow substrate
- No chamber aggregation in Phase 2
- No LLM judge runtime in Phase 2
- No direct LLM-to-exchange path

### 2.2 Repo-Resident Truth

The repository proves:

- **QuadraticScoringKernel** is the sole active Aurora scoring path since Phase 9 migration
- `signal_weights` and `feature_neutrals` are DEPRECATED config surfaces: loaded by Pydantic, passed through the call chain, but explicitly NOT read by the quadratic kernel (`quadratic_scoring_kernel.py:142-146`)
- Legacy scoring modules (`scoring_direction_strength_v1.py`, `signal_score_v2.py`) were deleted from tree but recoverable from git commit `dcaa176`
- Canonical legacy weight and neutral values are still present in `config/aurora/strategies/aurora.yaml` lines 384-413, marked DEPRECATED
- Per-symbol weight overrides exist (e.g., ETHUSDT at aurora.yaml:439-448)
- The cleanup of dead `signal_weights`/`feature_neutrals` wiring is tracked as open TODO items
- alpha_search domain exists with `AlphaModel` base class, `ProviderConfig` model, and `backtest_plugin.py` provider management
- Phase 1 `judge/` sub-package does not yet exist (prerequisite)

### 2.3 Historical Recovery Evidence

| Surface | Evidence Source | Recovery Status |
|---|---|---|
| SignalScoreV2 kernel formula | git commit `dcaa176`, `signal_score_v2.py` | **FULLY RECOVERED**: `score = SUM(w*(x - neutral)) / SUM(|w|)` |
| DirectionStrengthV1 formula | git commit `dcaa176`, `scoring_direction_strength_v1.py` | **FULLY RECOVERED**: `final = dir * (1 + alpha * clamp(strength, 0, cap))` |
| Feature partitioning | `DirectionStrengthScoringConfig` in `config_models.py:254` | **FULLY RECOVERED**: directional=[obi,tfi,delta_price,ema_bias,depth_imbalance,macro_resid,macro_sync,absorption], strength=[volume_spike,volatility_state] |
| Default weights | `aurora.yaml:400-413` | **FULLY RECOVERED**: obi=0.42, tfi=0.15, delta_price=0.15, etc. |
| Default neutrals | `aurora.yaml:386-396` | **FULLY RECOVERED**: obi=0.0, ema_bias=0.5, depth_imbalance=0.5, etc. |
| Per-symbol overrides | `aurora.yaml:439-448` (ETHUSDT example) | **FULLY RECOVERED**: calibration-adjusted weights |
| Essential features | `aurora.yaml:347` | **FULLY RECOVERED**: [obi, delta_price, macro_resid] |
| Normalization modes | Recovered from v1 module, `aurora_config_loader.py` | **FULLY RECOVERED**: "signed_v2" and "off" |
| strength_alpha, strength_cap | `aurora.yaml:330-331`, `config_models.py:254` | **FULLY RECOVERED**: 0.5, 1.0 |
| Readiness semantics | Recovered from v2 module, test `test_p0_fixes.py:204` | **FULLY RECOVERED**: `readiness.get(feat, False)`, essential missing → defer |

### 2.4 Adoption Gap

| Item | Status |
|---|---|
| Concept document | Not committed (Phase 1 prerequisite) |
| Phase 1 contracts (`ExpertOutput`, etc.) | Not in repo (Phase 1 prerequisite) |
| Phase 1 `judge/` sub-package | Not in repo (Phase 1 prerequisite) |
| Phase 1 `JudgeCortexConfig` | Not in repo (Phase 1 prerequisite) |
| Phase 1 verb registry entries | Not in repo (Phase 1 prerequisite) |
| Legacy expert modules | Not in repo (Phase 2 deliverable) |

---

## 3. Fixed Inputs from Phase 1

The following are frozen and must not be reopened:

1. **alpha_search-aligned placement**: Judge artifacts live under `apps/reference/domains/alpha_search/judge/`. Config additions go in `config/alpha_search.yaml`.
2. **ExpertOutput contract**: Pydantic model with `expert_id`, `expert_version`, `symbol`, `tf_sec`, `ts_ms`, `entry_verdict`/`lifecycle_verdict` (XOR), `confidence`, `signal_direction`, `reasoning`, `schema_version`.
3. **EntryVerdict vocabulary**: `OPEN_LONG`, `OPEN_SHORT`, `NO_ENTRY`, `SUPPRESS`, `UNKNOWN`.
4. **CortexMode vocabulary**: `off`, `shadow`, `hybrid_advisory`, `guarded_entry_authority`, `guarded_lifecycle_authority`.
5. **JudgeCortexConfig**: `enabled: bool`, `mode: CortexMode`, with Phase 1 admitting only `off`.
6. **Verb: `EVT:JUDGE_EXPERT_PRODUCED_V1`**: Deferred from Phase 1 to Phase 2 (Phase 1 blueprint Section 11.3: "Phase 2 (too noisy, register when runtime exists)").
7. **No main.py changes**: alpha_search already loads. Config additions have defaults.
8. **No decision_making changes**: No gate wiring until Phase 3+.
9. **No execution_position changes**: Judge is policy, not execution.
10. **Concept's mode surface**: Phase 2 ADDS `shadow` as an admitted mode.

---

## 4. Phase 2 Final Scope

### 4.1 In Scope

1. **`signal_weights_expert` module**: A new `AlphaModel` subclass that revives the legacy weighted-score formula as a bounded shadow expert producing `ExpertOutput`.
2. **`feature_neutrals_expert` module**: A new `AlphaModel` subclass that revives the legacy centering+direction-strength formula as a bounded shadow expert producing `ExpertOutput`.
3. **Expert config models**: Pydantic config for each expert (weights, neutrals, feature partitioning, thresholds, enable flags).
4. **Expert provider integration**: New provider type in `ProviderConfig` for judge experts, registered through `backtest_plugin.py` factory.
5. **`EVT:JUDGE_EXPERT_PRODUCED_V1` verb + schema**: Register the per-expert event deferred from Phase 1.
6. **Shadow mode admission**: Extend `JudgeCortexConfig` Phase validator to admit `shadow` alongside `off`.
7. **Expert-level config in `config/alpha_search.yaml`**: Per-expert YAML blocks with externalized constants.
8. **JSONL shadow telemetry**: Per-expert shadow output written to `logs/judge_experts/` for replay and forensic analysis.
9. **Test suite**: Unit tests for both experts, integration tests for shadow emission, regression tests for live Aurora path.
10. **Phase 2 report**: `docs/LLM_JUDGE/PHASE2_LEGACY_EXPERT_REVIVAL_REPORT.md`.

### 4.2 Out of Scope (explicitly deferred)

- No chamber aggregation (Phase 3)
- No `JudgeEvidenceEnvelope` assembly (Phase 3)
- No `JudgeVerdict` emission (Phase 3)
- No LLM judge calls (Phase 4+)
- No StrategyGateway gate insertion (Phase 3+)
- No decision_making authority changes
- No execution_position changes
- No main.py startup modifications beyond what alpha_search already has
- No lifecycle verdict experts (Phase 2 experts are ENTRY-only)
- No quadratic kernel changes
- No removal of legacy signal_weights/feature_neutrals dead wiring (orthogonal cleanup, not Phase 2)

---

## 5. FACTS

**F1.** The quadratic kernel is the sole active Aurora scoring path. It reads `pillar_sum` from feature engineering. It does NOT read `signal_weights`, `feature_neutrals`, or `direction_strength_cfg`. These are accepted in the function signature as deprecated compatibility parameters only (`quadratic_scoring_kernel.py:142-146`).

**F2.** Legacy `SignalScoreV2` formula: `score = SUM(w_i * (x_i - neutral_i)) / SUM(|w_i|)` for active features where `w != 0` and feature is present and ready. Essential feature missing → entire score deferred.

**F3.** Legacy `DirectionStrengthV1` formula: `final = dir_score * (1 + strength_alpha * clamp(strength_score, 0, strength_cap))`. Features split into directional subset and strength subset, each scored independently via SignalScoreV2.

**F4.** Canonical legacy weights from `aurora.yaml:400-413`: obi=0.42, tfi=0.15, delta_price=0.15, ema_bias=0.15, volume_spike=0.10, volatility_state=0.10, depth_imbalance=-0.15, macro_resid=0.10, absorption=0.0.

**F5.** Canonical legacy neutrals from `aurora.yaml:386-396`: obi=0.0, tfi=0.0, delta_price=0.0, ema_bias=0.5, volume_spike=0.0, volatility_state=0.0, depth_imbalance=0.5, macro_sync=0.5, macro_resid=0.0, absorption=0.0.

**F6.** Direction-strength config from `aurora.yaml:322-333`: directional=[obi, tfi, delta_price, ema_bias, depth_imbalance, macro_resid, macro_sync, absorption], strength=[volume_spike, volatility_state], strength_alpha=0.5, strength_cap=1.0.

**F7.** Normalization mode `"signed_v2"`: For `neutral == 0.5` features → `x' = 2*clamp(x, 0, 1) - 0.5`; for `neutral == 0.0` features → clamp to [-1, 1]. Mode `"off"` → no transform.

**F8.** `AlphaModel` base class (`alpha_model.py`) defines: `get_model_name() -> str`, `calculate_alpha(symbol, market_data, features, context) -> AlphaScore`. `AlphaScore` carries `model_name`, `symbol`, `score` [-1,1], `confidence` [0,1], `features_used`, `why`.

**F9.** `backtest_plugin.py` provider factory at `_create_provider_model()` dispatches on `cfg.adapter` / `cfg.ensemble`. Adding a new provider type requires: (a) new sub-config in `ProviderConfig`, (b) new factory branch, (c) new `AlphaModel` subclass.

**F10.** Features available at `EVT:FEATURES_CALCULATED` emission include: `obi`, `tfi`, `delta_price`, `ema_bias`, `volume_spike`, `volatility_state`, `depth_imbalance`, `macro_sync`, `macro_resid`, `absorption`, `pillar_sum`, `pillar_tactician`, `pillar_operator`, `pillar_strategist`, and bar/readiness metadata.

**F11.** Per-symbol weight overrides exist for ETHUSDT (`aurora.yaml:439-448`) with calibration-adjusted values. BTCUSDT and SOLUSDT use global defaults.

**F12.** Essential features default: `[obi, delta_price, macro_resid]` (`aurora.yaml:347`). Scoring defers if any essential feature is missing or not ready.

**F13.** alpha_search events are emitted via `event_bus.emit()` through FSMCore, triggering JSON Schema validation from verb_registry.

**F14.** Phase 1 blueprint deferred `EVT:JUDGE_EXPERT_PRODUCED_V1` to Phase 2 with rationale "too noisy, register when runtime exists" (Section 11.3).

**F15.** Deleted legacy modules are recoverable from git commit `dcaa176`. Structural guardrail test (`test_dm_domain_structural_guardrails.py:69-82`) enforces no live import of these deleted modules.

---

## 6. INFERENCES

**I1.** The `signal_weights_expert` is a simpler expert that computes the legacy centered weighted score WITHOUT the direction-strength split. It answers: "given these features and these weights, what is the raw weighted conviction?" This directly recovers the `SignalScoreV2.calculate_score()` behavior.

**I2.** The `feature_neutrals_expert` is a richer expert that computes the full direction-strength formula WITH the direction/strength feature split. It answers: "given the directional conviction and the strength confirmation, what is the composite signal?" This directly recovers the `compute_direction_strength_score()` behavior. The name "feature_neutrals" reflects that this expert's defining characteristic is the centering (neutralization) of features before scoring — the mathematical step that the quadratic kernel eliminated. **This name-to-formula assignment is an accepted reconstruction choice**: the historical formulas are fully proven from git; the concept supplies the expert names; this document binds them as the Phase 2 design decision.

**I3.** Both experts are ENTRY-only because: (a) the legacy scoring produced a single scalar conviction score used for entry signal generation, not position lifecycle management; (b) the concept names them as experts to be revived, not as lifecycle evaluators; (c) no historical evidence exists showing these surfaces were used for exit/protect/hold decisions.

**I4.** Both experts can be implemented as `AlphaModel` subclasses under `alpha_search/judge/experts/`, with a new `judge_expert` sub-config type added to `ProviderConfig`. This follows the existing provider factory pattern and avoids creating a parallel registration mechanism.

**I5.** Expert outputs should be dual-emitted: (a) as `ExpertOutput` (Phase 1 contract) for judge pipeline consumption in Phase 3; (b) as `EVT:JUDGE_EXPERT_PRODUCED_V1` FSM event for shadow telemetry and replay. The `AlphaScore` → `ExpertOutput` translation is deterministic.

**I6.** Constants (weights, neutrals, thresholds, feature lists) must be externalized into `config/alpha_search.yaml` under the `judge:` block, not hardcoded. This prevents silent debt reinjection and allows operator tuning without code changes.

---

## 7. ASSUMPTIONS

**A1.** The two legacy experts are semantically distinct and should remain separate modules, not merged. The `signal_weights_expert` provides a flat weighted score; the `feature_neutrals_expert` provides a direction-strength composite score. Different experts may diverge in future calibration.

**A2.** Phase 2 experts read features from the same `EVT:FEATURES_CALCULATED` payload that the live quadratic kernel consumes. They do NOT require new feature engineering work. All 9 features (obi, tfi, delta_price, ema_bias, volume_spike, volatility_state, depth_imbalance, macro_resid, macro_sync/absorption) are already emitted by FE.

**A3.** Phase 2 experts use the deprecated/legacy YAML weights and neutrals as initial config values. These are explicitly labeled as "revival defaults from Phase 9 legacy" in the config block, not as active production tuning.

**A4.** Shadow-mode expert evaluation runs on the same trigger as the alpha_search plugin (`EVT:FEATURES_CALCULATED` or `CMD:PROCESS_STRATEGY`), but expert outputs are NEVER applied to the decision pipeline. They are logged and emitted as shadow events only.

**A5.** The `EVT:JUDGE_EXPERT_PRODUCED_V1` event is registered with `status: experimental` and `owner: alpha_search`, matching the Phase 1 verb registration pattern.

---

## 8. UNKNOWNS

| Unknown | Blocking? | Mitigation |
|---|---|---|
| Whether per-symbol weight overrides (e.g., ETHUSDT) should be used by revived experts or only global defaults | No | Phase 2 supports both: global defaults in expert config, per-symbol override lookup matching existing `_get_signal_weights()` pattern. Document as implementation choice. |
| Whether `absorption` feature (weight=0.0 in global, non-zero in ETHUSDT calibration) should be active in experts | No | Include in feature list with global default weight 0.0. Per-symbol overrides may enable it. Config-driven. |
| Whether `macro_sync` (deprecated, replaced by `macro_resid` in active path) should be scored by experts | No | Include in expert feature list with weight 0.0 (disabled). Operators can re-enable via config. |
| Exact JSONL log format for shadow telemetry replay | No | Define in Phase 2 implementation. Follows existing `logs/ta_features/` JSONL pattern. |
| Whether Phase 2 experts should produce `signal_direction` on `ExpertOutput` | No | Yes — derive from score sign: positive → `LONG`, negative → `SHORT`, within neutral threshold → `NEUTRAL`. |

No blocking unknowns remain.

---

## 9. Current Repo Truth for Legacy Aurora Surfaces

### 9.1 ACTIVE NOW (production runtime)

| Surface | Location | Consumed By |
|---|---|---|
| `pillar_sum` | `EVT:FEATURES_CALCULATED` payload | `QuadraticScoringKernel.compute()` |
| `base_threshold` / `signal_threshold` | `aurora.yaml` decision block | Quadratic kernel threshold comparison |
| `regime_thresholds` | `aurora.yaml` per-symbol or global | Quadratic kernel threshold widening |
| Shield cascade (DangerZone, Context, Memory) | `ScoringEngineConfig` | Quadratic kernel attenuation |
| `score_multiplier` | `aurora.yaml` decision block | Quadratic kernel input scaling |
| `admission_mode`, `sizing_mode` | `aurora.yaml` decision block | Quadratic kernel transform geometry |

### 9.2 DEPRECATED / LEGACY (loaded but not consumed by live kernel)

| Surface | Location | Status |
|---|---|---|
| `signal_weights` | `aurora.yaml:400-413`, `config_models.py:1320` | Loaded → passed to kernel → explicitly ignored. DEPRECATED Phase 9. |
| `feature_neutrals` | `aurora.yaml:386-396`, `config_models.py:1357` | Loaded → passed to kernel → explicitly ignored. DEPRECATED Phase 9. |
| `direction_strength_scoring` | `aurora.yaml:322-333`, `config_models.py:254` | Loaded by config_loader → passed to kernel → ignored. DEPRECATED Phase 9. |
| `scoring_version` (v1/v2 values) | `config_models.py:1355` | Accepted by type but `_VALID_SCORING_VERSIONS = {"quadratic"}` enforces quadratic only. |
| Helper: `_get_signal_weights()` | `aurora_scoring_helpers.py:145-156` | Resolves per-symbol or global weights. Called by `aurora_decision.py:358`. Dead code path. |
| Helper: `_get_feature_neutrals()` | `aurora_scoring_helpers.py:352-363` | Resolves per-symbol or global neutrals. Called by `aurora_decision.py:359`. Dead code path. |
| Per-symbol `weights` overrides | `aurora.yaml:439-448` (ETHUSDT) | Loaded but never consumed by quadratic kernel. |
| `normalize_signals_mode` | `aurora.yaml` decision block | Config-loader reads it, passes to kernel where it is ignored. |

### 9.3 STILL EXISTS IN TOOLS (not live runtime)

| Surface | Location | Status |
|---|---|---|
| `calibrate_aurora_signal_weights.py` | `tools/calibration/` | Research-only. Docstring explicitly states "deprecated Aurora scoring surfaces". |
| Alpha search `scenario_matrix.yaml` weight overrides | `config/alpha_search/scenario_matrix.yaml:80-171` | Tuning dead knobs. Part of tracked cleanup TODO. |

---

## 10. Historical Recovery Findings

### 10.1 PROVEN from git/code/tests/docs

| Behavior | Evidence |
|---|---|
| **Weighted centering formula**: `score = SUM(w*(x-neutral)) / SUM(|\|w\||)` | Recovered from `signal_score_v2.py` via git commit `dcaa176`. Confirmed by inline replication in `test_p0_fixes.py:232`. |
| **Direction-strength composite**: `final = dir * (1 + alpha * clamp(strength, 0, cap))` | Recovered from `scoring_direction_strength_v1.py` via git commit `dcaa176`. Docstring formula and code match. |
| **Feature partitioning**: directional=[obi,tfi,delta_price,ema_bias,depth_imbalance,macro_resid,macro_sync,absorption], strength=[volume_spike,volatility_state] | Active in `aurora.yaml:322-333`. Pydantic model `DirectionStrengthScoringConfig` at `config_models.py:254`. |
| **Readiness semantics**: `readiness.get(feat, False)`, essential missing → defer | Recovered from `signal_score_v2.py`. Confirmed independently in `test_p0_fixes.py:204` (TestSignalScoreV2ReadinessLookup). |
| **Normalization mode `signed_v2`**: neutral=0.5 → `2*clamp(x,0,1)-0.5`; neutral=0 → clamp [-1,1] | Recovered from `scoring_direction_strength_v1.py` code. |
| **Fail-closed essential check**: score deferred when any essential feature missing or not ready | Recovered from `signal_score_v2.py`. |
| **Per-feature contribution tracking**: `contribs[feat] = w * (val - neutral)` | Recovered from `signal_score_v2.py` `ScoreResult.contribs` field. |
| **Weight normalization**: score divided by `SUM(|\|w\||)` not `SUM(w)` | Recovered from `signal_score_v2.py`. |
| **Config validation**: weighted feature without neutral entry → `ValueError` | Recovered from `SignalScoreV2.validate_config()`. |

### 10.2 UNPROVEN (gaps)

| Gap | Impact | Mitigation |
|---|---|---|
| Exact git commit where v2 linear was production-active | Low | Not needed. We revive the math, not the deployment timeline. |
| Whether per-symbol ETHUSDT calibrated weights were ever production-active under v2 | Low | We expose them as config-driven overrides. Their production provenance is immaterial to shadow revival. |
| Whether `macro_sync` was an active or deprecated feature at the time of v2 operation | Low | Include with weight=0.0. Config-driven activation. |
| Whether `absorption` contributed to production v2 scoring | Low | Include with weight=0.0 (global), per-symbol override may activate. |

---

## 11. Phase 2 Placement Decision

### 11.1 Chosen Path: `alpha_search/judge/experts/` sub-package

Phase 2 expert modules live at `apps/reference/domains/alpha_search/judge/experts/`. Responsibility is split into two layers:

**Layer 1 — Pure scoring (expert module)**: Each expert is an `AlphaModel` subclass. It receives features and config, computes a score via the recovered legacy formula, and returns an `AlphaScore`. It does NOT emit events, write logs, or construct `ExpertOutput`. It is a pure scoring unit, testable in isolation.

**Layer 2 — Integration (provider wrapper / backtest_plugin)**: The `backtest_plugin.py` integration layer (and/or `expert_output_bridge.py`) is responsible for:
- Calling the expert's `calculate_alpha()`
- Translating `AlphaScore` → `ExpertOutput` via the bridge
- Emitting `EVT:JUDGE_EXPERT_PRODUCED_V1` on the FSM event bus
- Writing JSONL shadow logs

This separation prevents experts from becoming half-orchestrators. Score math lives in expert modules; emission, logging, and contract bridging live in the integration layer.

### 11.2 Why This Path

1. **Proven provider pattern**: alpha_search already has `AlphaModel` base class, `ProviderConfig` dispatch, `backtest_plugin.py` factory. Adding a new provider type is a well-trodden extension point.
2. **Phase 1 alignment**: The `judge/` sub-package is where Phase 1 contracts and config already live. Experts under `judge/experts/` are a natural addition.
3. **Shadow substrate**: alpha_search is the accepted shadow substrate. Experts inherit its shadow-mode semantics.
4. **No new domain**: No new `DomainsConfig` entry, no new domain_builder path, no new startup wiring.
5. **Minimal blast radius**: New files under `judge/experts/` + additive config changes + new provider type option.

### 11.3 Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Standalone expert modules outside alpha_search | Violates alpha_search substrate directive. Creates orphan code with no proven loading/wiring path. |
| Expert logic embedded inside decision_making | Reinserts legacy math into the decision domain that has explicitly removed it. Conflates policy evaluation with signal generation. |
| Direct `AlphaModel` registration in `AlphaModelRegistry` | Backtest_plugin does NOT use the registry (`alpha_model.py:127`). It manages providers directly via config-driven factory. Using the unused registry creates a second provider management mechanism. |
| New top-level provider type (not under `judge/`) | Achievable but creates naming confusion. Judge experts are judge artifacts and belong under `judge/`. |

---

## 12. Revived Expert Design

### 12.1 `signal_weights_expert`

| Attribute | Value |
|---|---|
| **Purpose** | Revive the legacy flat weighted-sum scoring formula as an explicit shadow expert. Answers: "What entry signal do the legacy signal weights produce given current features?" |
| **Owner** | alpha_search (judge sub-package) |
| **Module location** | `apps/reference/domains/alpha_search/judge/experts/signal_weights_expert.py` |
| **Base class** | `AlphaModel` |
| **expert_id** | `"judge.signal_weights_v1"` |
| **Verdict scope** | ENTRY only |
| **Classification** | Entry expert — produces `entry_verdict`, `lifecycle_verdict` is always None |

**Data dependencies**:
- `EVT:FEATURES_CALCULATED` payload: requires `obi`, `tfi`, `delta_price`, `ema_bias`, `volume_spike`, `volatility_state`, `depth_imbalance`, `macro_resid` at minimum. Optional: `macro_sync`, `absorption`.
- Feature readiness map (from `bar.readiness` in features payload or derived).
- Signal weights (from expert config, not from Aurora decision config).
- Feature neutrals (from expert config, not from Aurora decision config).
- Essential features list (from expert config).

**Historical behavior anchor (proven)**:
```
For each feature f in weights where w[f] != 0:
  if f not in features or not ready[f]: skip (reduce denominator)
  if f in essential and (missing or not ready): DEFER entire score
  centered = features[f] - neutrals[f]
  contrib[f] = w[f] * centered
score_raw = SUM(contrib)
wabs = SUM(|w[f]|) for active features
score = score_raw / wabs   (if wabs > 0, else 0)
```
Source: `signal_score_v2.py` recovered from git `dcaa176`.

**Reconstructed behavior (Phase 2 implementation)**:
1. Read features from `calculate_alpha(symbol, market_data, features, context)`.
2. Read weights, neutrals, essential from expert-specific config.
3. Apply normalization mode if configured (default: `"off"` — no transform).
4. Compute flat weighted score as above.
5. Compare score magnitude against expert's `signal_threshold`.
6. Map to `ExpertOutput`:
   - `score > threshold` → `entry_verdict = OPEN_LONG`, `signal_direction = LONG`
   - `score < -threshold` → `entry_verdict = OPEN_SHORT`, `signal_direction = SHORT`
   - otherwise → `entry_verdict = NO_ENTRY`, `signal_direction = NEUTRAL`
   - `confidence = min(1.0, abs(score))`
7. Populate `reasoning` with per-feature contributions.
8. Return `AlphaScore` (for alpha_search pipeline). The integration layer (bridge) converts to `ExpertOutput` and handles emission/logging — the expert module does not.

**Config surface** (under `judge.experts.signal_weights` in `config/alpha_search.yaml`):
```yaml
enabled: bool
signal_weights: Dict[str, float]       # externalized from aurora.yaml legacy
feature_neutrals: Dict[str, float]     # externalized from aurora.yaml legacy
essential_features: List[str]           # externalized from aurora.yaml legacy
signal_threshold: float                 # default 0.162
normalize_mode: str                     # "off" or "signed_v2"
                                        # Default "off" is a SAFE ROLLOUT DEFAULT, not the
                                        # historical default. Historical v1 path used "signed_v2".
                                        # Phase 2 starts with "off" to isolate centering math
                                        # from normalization effects; operators can switch to
                                        # "signed_v2" to recover full historical behavior.
symbols: Optional[List[str]]           # null = all aurora symbols
```

**Fail-closed behavior**:
- Essential feature missing or not ready → `entry_verdict = UNKNOWN`, `confidence = 0.0`, reasoning includes `DEFER:<feature>`.
- All weights zero → `entry_verdict = UNKNOWN`, `confidence = 0.0`.
- No features available → `entry_verdict = UNKNOWN`, `confidence = 0.0`.
- Exception in calculation → `entry_verdict = UNKNOWN`, `confidence = 0.0`, reasoning includes exception class.

### 12.2 `feature_neutrals_expert`

| Attribute | Value |
|---|---|
| **Purpose** | Revive the legacy direction-strength composite formula as an explicit shadow expert. Answers: "What entry signal does the directional conviction amplified by strength confirmation produce given current features?" |
| **Owner** | alpha_search (judge sub-package) |
| **Module location** | `apps/reference/domains/alpha_search/judge/experts/feature_neutrals_expert.py` |
| **Base class** | `AlphaModel` |
| **expert_id** | `"judge.feature_neutrals_v1"` |
| **Verdict scope** | ENTRY only |
| **Classification** | Entry expert — produces `entry_verdict`, `lifecycle_verdict` is always None |

**Data dependencies**: Same as signal_weights_expert, plus `direction_strength` config block.

**Historical behavior anchor (proven formula, reconstruction-assigned name)**:

> **Note**: The direction-strength composite formula below is fully proven from git recovery. However, the assignment of this formula to the concept's `feature_neutrals_expert` name is an accepted Phase 2 reconstruction choice, not a directly proven historical identity. The concept names the expert; the repo proves the formula; this document binds them together as the accepted design decision.
```
# Partition weights into directional and strength subsets
w_dir = {k: v for k, v in weights if k in directional_set}
w_str = {k: v for k, v in weights if k in strength_set}

# Compute directional score using SignalScoreV2 formula
dir_score = weighted_centered_score(features, w_dir, neutrals, readiness, essential_dir)
# If dir deferred: DEFER entire score

# Compute strength score using SignalScoreV2 formula
strength_score = weighted_centered_score(features, w_str, neutrals, readiness, essential_str=set())
strength_clamped = max(0, min(strength_score, strength_cap))

# Composite
final = dir_score * (1 + strength_alpha * strength_clamped)
```
Source: `scoring_direction_strength_v1.py` recovered from git `dcaa176`.

**Reconstructed behavior (Phase 2 implementation)**:
1. Read features from `calculate_alpha()`.
2. Read weights, neutrals, directional/strength feature lists, strength_alpha, strength_cap, essential from expert-specific config.
3. Apply normalization mode if configured.
4. Partition weights by directional vs strength feature membership.
5. Compute directional SignalScoreV2: `dir = SUM(w_dir*(x-neutral)) / SUM(|w_dir|)`.
6. Compute strength SignalScoreV2: `str = SUM(w_str*(x-neutral)) / SUM(|w_str|)`, clamped [0, cap].
7. Composite: `final = dir * (1 + alpha * str)`.
8. Compare against signal_threshold, map to EntryVerdict (same mapping as signal_weights_expert).
9. Populate reasoning with directional contribution, strength contribution, composite.
10. Return `AlphaScore` and `ExpertOutput`.

**Config surface** (under `judge.experts.feature_neutrals` in `config/alpha_search.yaml`):
```yaml
enabled: bool
signal_weights: Dict[str, float]
feature_neutrals: Dict[str, float]
essential_features: List[str]
directional_features: List[str]        # externalized from direction_strength_scoring
strength_features: List[str]           # externalized from direction_strength_scoring
strength_alpha: float                  # default 0.5
strength_cap: float                    # default 1.0
signal_threshold: float                # default 0.162
normalize_mode: str                    # "off" or "signed_v2"
symbols: Optional[List[str]]
```

**Fail-closed behavior**: Same as signal_weights_expert, plus:
- Empty directional feature list → `entry_verdict = UNKNOWN`, `confidence = 0.0`, reason `NRR-NO-DIRECTIONAL-FEATURES`.
- Directional score deferred due to essential missing → `entry_verdict = UNKNOWN`, `confidence = 0.0`.

### 12.3 How the Two Experts Differ

| Dimension | signal_weights_expert | feature_neutrals_expert |
|---|---|---|
| **Formula** | Flat weighted sum: `SUM(w*(x-n)) / SUM(|w|)` | Direction-strength composite: `dir * (1 + alpha * strength)` |
| **Feature partitioning** | All features in one pool | Split into directional and strength subsets |
| **Strength amplification** | None | Strength features amplify directional conviction |
| **Historical origin** | `SignalScoreV2.calculate_score()` | `compute_direction_strength_score()` |
| **Sensitivity** | Equally sensitive to all feature changes | More sensitive to directional features; strength acts as multiplier |
| **When they agree** | Confirms that legacy math and composite math converge — higher confidence scenario |
| **When they disagree** | Divergence reveals whether direction-strength split was adding or distorting signal |

---

## 13. Runtime / Event Flow for Phase 2

### 13.1 Runtime Behavior in Phase 2

1. **Trigger**: `EVT:FEATURES_CALCULATED` arrives at alpha_search `backtest_plugin.py` (existing trigger path).
2. **Provider dispatch**: backtest_plugin iterates enabled providers. If judge expert providers are enabled, their `calculate_alpha()` is called.
3. **Expert execution** (Layer 1 — pure scoring): Each expert reads features, computes score via legacy formula, returns `AlphaScore`. No side effects.
4. **ExpertOutput translation** (Layer 2 — integration): `expert_output_bridge.py` maps `AlphaScore` → `ExpertOutput`. This runs in the integration layer, not inside the expert.
5. **Shadow emission** (Layer 2 — integration): Integration layer emits `EVT:JUDGE_EXPERT_PRODUCED_V1` via FSMCore with `ExpertOutput` as payload. Event is schema-validated.
6. **JSONL logging** (Layer 2 — integration): Expert output written to `logs/judge_experts/{expert_id}_{symbol}_{date}.jsonl` for replay.
7. **No downstream consumption**: No chamber, no verdict, no gate. Output is observed and logged only.

### 13.2 Events Emitted in Phase 2

| Event | Schema | Owner | Emitted When | Consumer |
|---|---|---|---|---|
| `EVT:JUDGE_EXPERT_PRODUCED_V1` | `judge/schemas/expert_output_v1.json` (from Phase 1) | alpha_search | After each expert produces an ExpertOutput | None (shadow telemetry, JSONL log) |

### 13.3 Observability / Replay Path

- **JSONL files**: `logs/judge_experts/signal_weights_v1_{symbol}_{YYYY-MM-DD}.jsonl` and `logs/judge_experts/feature_neutrals_v1_{symbol}_{YYYY-MM-DD}.jsonl`
- **FSM event bus**: `EVT:JUDGE_EXPERT_PRODUCED_V1` events visible to any subscriber (could be piped to WAL or shadow_telemetry in Phase 3)
- **Per-feature contributions**: Embedded in `ExpertOutput.reasoning` list for post-hoc analysis
- **Replay key**: `(expert_id, symbol, tf_sec, ts_ms)` as defined by Phase 1 `ExpertOutput` contract

### 13.4 Deferred to Phase 3

- Chamber aggregation of expert outputs
- Evidence envelope assembly
- Judge verdict formation
- StrategyGateway gate insertion
- Shadow telemetry domain integration (formal)

---

## 14. Config Package

### 14.1 Canonical Config Path

`config/alpha_search.yaml` — extended under the `judge:` block (created in Phase 1).

### 14.2 Phase 2 Config Surface

```yaml
judge:
  enabled: true                         # Phase 2: enable judge evaluation
  mode: "shadow"                        # Phase 2 admits: "off", "shadow"

  experts:
    signal_weights:
      enabled: true
      expert_id: "judge.signal_weights_v1"
      expert_version: "1.0.0"
      symbols: null                     # null = all aurora symbols
      signal_threshold: 0.162
      normalize_mode: "off"             # Safe rollout default. Historical was "signed_v2".
      essential_features: [obi, delta_price, macro_resid]
      # Externalized from aurora.yaml legacy (Phase 9 deprecated values)
      # These are REVIVAL DEFAULTS, not active production tuning.
      signal_weights:
        obi: 0.42
        tfi: 0.15
        delta_price: 0.15
        ema_bias: 0.15
        volume_spike: 0.10
        volatility_state: 0.10
        depth_imbalance: -0.15
        macro_resid: 0.10
        macro_sync: 0.0
        absorption: 0.0
      feature_neutrals:
        obi: 0.0
        tfi: 0.0
        delta_price: 0.0
        ema_bias: 0.5
        volume_spike: 0.0
        volatility_state: 0.0
        depth_imbalance: 0.5
        macro_sync: 0.5
        macro_resid: 0.0
        absorption: 0.0

    feature_neutrals:
      enabled: true
      expert_id: "judge.feature_neutrals_v1"
      expert_version: "1.0.0"
      symbols: null
      signal_threshold: 0.162
      normalize_mode: "off"             # Safe rollout default. Historical was "signed_v2".
      essential_features: [obi, delta_price, macro_resid]
      directional_features: [obi, tfi, delta_price, ema_bias, depth_imbalance, macro_resid, macro_sync, absorption]
      strength_features: [volume_spike, volatility_state]
      strength_alpha: 0.5
      strength_cap: 1.0
      signal_weights:
        obi: 0.42
        tfi: 0.15
        delta_price: 0.15
        ema_bias: 0.15
        volume_spike: 0.10
        volatility_state: 0.10
        depth_imbalance: -0.15
        macro_resid: 0.10
        macro_sync: 0.0
        absorption: 0.0
      feature_neutrals:
        obi: 0.0
        tfi: 0.0
        delta_price: 0.0
        ema_bias: 0.5
        volume_spike: 0.0
        volatility_state: 0.0
        depth_imbalance: 0.5
        macro_sync: 0.5
        macro_resid: 0.0
        absorption: 0.0

  shadow_log:
    enabled: true
    log_dir: "logs/judge_experts"
    max_file_size_mb: 50
    rotation: "daily"
```

### 14.3 Shadow-Mode Admission Rules

Phase 2 extends `JudgeCortexConfig` Phase validator:
- `off` → Admitted. No expert evaluation. Judge experts are disabled (even if config says `enabled: true`).
- `shadow` → Admitted. Expert evaluation runs. Outputs are logged and emitted as shadow events. Never applied.
- All other modes → Rejected with: `"Judge mode '{mode}' is not admitted in Phase 2. Only 'off' and 'shadow' are allowed."`

### 14.4 Validation Rules

- Each expert config must have non-empty `signal_weights` and `feature_neutrals` dicts.
- Every weighted feature (w != 0) must have a corresponding neutral entry (replicating `SignalScoreV2.validate_config()` invariant).
- `signal_threshold` must be > 0.
- `strength_alpha` must be >= 0.
- `strength_cap` must be >= 0.
- `essential_features` must be a subset of features present in `signal_weights`.
- `directional_features` and `strength_features` must not overlap (for feature_neutrals expert).
- `directional_features` must be non-empty (for feature_neutrals expert).
- `symbols` must be a list of valid symbol strings or null.
- `normalize_mode` must be `"off"` or `"signed_v2"`.
- Expert disabled + judge mode "shadow" → no error (expert simply not evaluated).
- Judge mode "off" → all experts silently skipped regardless of their `enabled` flag.

### 14.5 No-Hidden-Constants Policy

All numerical constants used by experts must come from config, not from code:
- Weights → `signal_weights` dict in expert config
- Neutrals → `feature_neutrals` dict in expert config
- Threshold → `signal_threshold` in expert config
- Feature sets → `essential_features`, `directional_features`, `strength_features` in expert config
- Strength params → `strength_alpha`, `strength_cap` in expert config
- Normalization → `normalize_mode` in expert config

No magic numbers in expert Python modules. Default values in Pydantic config models must match the YAML values and be documented as "Phase 9 legacy revival defaults".

---

## 15. File-by-File Implementation Blueprint

### Subpackage 2A: Expert Config Models

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/alpha_search/judge/config_models.py` | MODIFY | Add `SignalWeightsExpertConfig`, `FeatureNeutralsExpertConfig`, `JudgeExpertsConfig`, `JudgeShadowLogConfig`. Extend `JudgeCortexConfig` with `experts: Optional[JudgeExpertsConfig]` and `shadow_log: Optional[JudgeShadowLogConfig]`. Update Phase validator to admit `"shadow"`. |

### Subpackage 2B: Expert Modules

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/alpha_search/judge/experts/__init__.py` | NEW | Sub-package init. |
| `apps/reference/domains/alpha_search/judge/experts/signal_weights_expert.py` | NEW | `SignalWeightsExpert(AlphaModel)` — pure flat weighted centering score. Returns `AlphaScore`. No emission, no logging. |
| `apps/reference/domains/alpha_search/judge/experts/feature_neutrals_expert.py` | NEW | `FeatureNeutralsExpert(AlphaModel)` — pure direction-strength composite score. Returns `AlphaScore`. No emission, no logging. |
| `apps/reference/domains/alpha_search/judge/experts/expert_output_bridge.py` | NEW | Integration utility: `AlphaScore → ExpertOutput` translation, `EVT:JUDGE_EXPERT_PRODUCED_V1` emission helper, JSONL shadow log writer. Score math stays in experts; bridge/emission/logging live here. |

### Subpackage 2C: Provider Integration

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/alpha_search/config_models.py` | MODIFY | Add `judge_expert: Optional[JudgeExpertProviderConfig]` to `ProviderConfig` (alongside `adapter`, `ensemble`). Update `validate_provider_type` to allow `judge_expert` as third mutually exclusive option. |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | MODIFY | Add factory branch in `_create_provider_model()` for `cfg.judge_expert`. Import expert classes conditionally. |

### Subpackage 2D: Verb Registry + Schema + Domain Dict

| File | Action | Purpose |
|---|---|---|
| `apps/reference/dictionaries/verb_registry_v1.yaml` | MODIFY | Add `EVT:JUDGE_EXPERT_PRODUCED_V1` entry (status: experimental, owner: alpha_search, schema: `judge/schemas/expert_output_v1.json`). |
| `apps/reference/domains/alpha_search/domain_dict.json` | MODIFY | Add `EVT:JUDGE_EXPERT_PRODUCED_V1` to exports. Add judge expert components to domain boundary. (Created in Phase 1; updated in Phase 2 for new export surface.) |

### Subpackage 2E: Config YAML

| File | Action | Purpose |
|---|---|---|
| `config/alpha_search.yaml` | MODIFY | Add `judge.experts` and `judge.shadow_log` blocks as specified in Section 14.2. Update `judge.mode` default from `"off"` to `"off"` (unchanged — shadow mode requires explicit operator enablement). |

### Subpackage 2F: Test Suite

| File | Action | Purpose |
|---|---|---|
| `tests/domains/alpha_search/judge/experts/__init__.py` | NEW | Test sub-package. |
| `tests/domains/alpha_search/judge/experts/test_signal_weights_expert.py` | NEW | Unit tests for signal_weights_expert. |
| `tests/domains/alpha_search/judge/experts/test_feature_neutrals_expert.py` | NEW | Unit tests for feature_neutrals_expert. |
| `tests/domains/alpha_search/judge/experts/test_expert_output_bridge.py` | NEW | AlphaScore → ExpertOutput translation tests. |
| `tests/domains/alpha_search/judge/test_expert_config.py` | NEW | Expert config validation tests. |
| `tests/domains/alpha_search/judge/test_expert_provider_integration.py` | NEW | Provider factory + event emission integration tests. |
| `tests/domains/alpha_search/judge/test_shadow_mode_admission.py` | NEW | Shadow mode admission + expert gating tests. |
| `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py` | NEW | Regression tests verifying quadratic kernel is unaffected. |

### Subpackage 2G: Report

| File | Action | Purpose |
|---|---|---|
| `docs/LLM_JUDGE/PHASE2_LEGACY_EXPERT_REVIVAL_REPORT.md` | NEW | Final Phase 2 completion report. |

### Files Explicitly Untouched in Phase 2

| File | Reason |
|---|---|
| `apps/reference/main.py` | No startup changes. alpha_search already loads. Config additions have defaults. |
| `apps/reference/config_loader.py` | No changes. alpha_search uses its own loader. |
| `apps/reference/config_models.py` (root) | No changes. Legacy `SignalWeights`, `DirectionStrengthScoringConfig` remain as-is. |
| `apps/reference/domains/decision_making/*` | No gate wiring. No kernel changes. No scoring helper changes. |
| `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | Explicitly untouched. Phase 2 does not change live scoring. |
| `apps/reference/domains/decision_making/aurora_decision.py` | Explicitly untouched. |
| `apps/reference/domains/decision_making/aurora_handler.py` | Explicitly untouched. |
| `apps/reference/domains/decision_making/aurora_scoring_helpers.py` | Explicitly untouched. Dead wiring cleanup is a separate effort. |
| `config/aurora/strategies/aurora.yaml` | No changes to live Aurora config. Legacy values remain as-is. |
| `apps/reference/domains/execution_position/*` | No execution changes. |
| `apps/reference/domains/shadow_telemetry/*` | No integration until Phase 3. |
| `vfoundation/core/protocol.py` | No changes. |
| `vfoundation/core/schema_registry.py` | No changes (reads verb_registry automatically). |

---

## 16. Validation Blueprint

### 16.1 Test Matrix

| Category | File | Count | Description |
|---|---|---|---|
| **A. Signal Weights Expert** | `test_signal_weights_expert.py` | 15-20 | Correct score with known inputs. Centering against neutrals. Weight normalization (abs denominator). Essential feature missing → UNKNOWN. All features present → correct verdict mapping. Threshold boundary (score just above/below threshold). Negative score → OPEN_SHORT. Positive score → OPEN_LONG. Within threshold → NO_ENTRY. Confidence mapping. Fail-closed on empty features. Fail-closed on all-zero weights. Per-feature contribution in reasoning. |
| **B. Feature Neutrals Expert** | `test_feature_neutrals_expert.py` | 20-25 | All signal_weights tests above PLUS: direction-strength partitioning. Strength clamping [0, cap]. Composite formula: `dir * (1 + alpha * strength)`. Empty directional features → UNKNOWN. Strength features missing → strength=0, dir-only scoring. Directional deferred → UNKNOWN. strength_alpha=0 → equals flat directional. strength_cap effect. |
| **C. ExpertOutput Bridge** | `test_expert_output_bridge.py` | 8-10 | Score → EntryVerdict mapping (all 5 verdict values). Score → signal_direction. Confidence capping at 1.0. Schema version. Expert_id, expert_version propagation. reasoning preservation. |
| **D. Expert Config** | `test_expert_config.py` | 12-15 | Valid config loads. Unknown field rejected. Weighted feature without neutral → validation error. Empty signal_weights rejected. signal_threshold <= 0 rejected. strength_alpha < 0 rejected. directional/strength overlap rejected. Empty directional_features rejected. normalize_mode invalid rejected. symbols list validation. enabled flag respected. Default values match YAML. |
| **E. Provider Integration** | `test_expert_provider_integration.py` | 8-12 | Judge expert provider registered via backtest_plugin factory. ProviderConfig with judge_expert sub-config validates. Mutually exclusive with adapter/ensemble. Expert produces AlphaScore through provider pipeline. EVT:JUDGE_EXPERT_PRODUCED_V1 emitted on FSM. Event payload validates against expert_output_v1.json schema. |
| **F. Shadow Mode** | `test_shadow_mode_admission.py` | 6-8 | Mode "off" → experts skipped. Mode "shadow" → experts run. Mode "hybrid_advisory" rejected in Phase 2. enabled=false → expert skipped regardless of mode. Judge mode "shadow" + individual expert disabled → partial evaluation. JSONL log written when shadow mode active. |
| **G. Live Aurora Regression** | `test_no_live_aurora_regression.py` | 5-8 | QuadraticScoringKernel.compute() still reads pillar_sum not signal_weights. Existing alpha_search providers still work. No new imports in decision_making modules. No decision_making config changes. Existing verb registry entries unchanged. |
| **H. Historical Accuracy** | (in A + B) | 5-8 | Known historical inputs → matches historical formula output (Golden test: use aurora.yaml defaults + synthetic features → verify score matches hand-computed expected). Centering: `obi=0.3, neutral=0.0 → centered=0.3`. Centering: `ema_bias=0.7, neutral=0.5 → centered=0.2`. |

**Total estimated tests**: 79-106

### 16.2 Proof Artifacts

| Artifact | Required |
|---|---|
| All Phase 2 tests pass (pytest output) | YES |
| Historical golden tests pass (known inputs → expected score) | YES |
| Schema compilation proof (`EVT:JUDGE_EXPERT_PRODUCED_V1` compiles in VerbSchemaRegistry) | YES |
| ExpertOutput round-trip (Pydantic → dict → JSON Schema validation) | YES |
| Existing alpha_search tests still pass | YES (regression gate) |
| Phase 1 judge tests still pass | YES (regression gate) |
| Global test suite still pass | YES (regression gate) |
| JSONL shadow log written and parseable | YES |
| REPORT produced | YES |

### 16.3 Acceptance Gates

1. Zero test failures in Phase 2 test suite.
2. Zero regressions in Phase 1 judge test suite.
3. Zero regressions in existing alpha_search test suite.
4. Zero regressions in global test suite.
5. Both experts produce correct `ExpertOutput` for known inputs.
6. `EVT:JUDGE_EXPERT_PRODUCED_V1` registered and schema-validated.
7. Shadow mode gating works (off → skip, shadow → run).
8. No changes to `quadratic_scoring_kernel.py` or any `decision_making` module.
9. No constants hardcoded in expert modules (all from config).
10. REPORT produced with explicit verdict.

---

## 17. Risks

### R1. Legacy formula reconstruction error

| Attribute | Value |
|---|---|
| **Cause** | Historical formula recovered from git may be incomplete or misinterpreted |
| **Mechanism** | Phase 2 expert produces different scores than actual historical v2 path |
| **Effect** | Shadow analysis produces misleading comparisons |
| **Severity** | MEDIUM |
| **Mitigation** | Golden tests with hand-computed expected values. Cross-reference with `test_p0_fixes.py:232` inline formulas. Test edge cases (zero weights, all-missing, neutral=0.5 centering). |

### R2. Feature availability drift

| Attribute | Value |
|---|---|
| **Cause** | Feature engineering may rename or remove features that experts depend on |
| **Mechanism** | Expert essential feature check fails; expert always produces UNKNOWN |
| **Effect** | Expert silently useless after FE change |
| **Severity** | LOW — experts fail-closed, which is detectable |
| **Mitigation** | Golden test with current FE output. Shadow log monitoring for UNKNOWN rate. |

### R3. Config duplication between aurora.yaml and alpha_search.yaml

| Attribute | Value |
|---|---|
| **Cause** | Expert config contains the same weight/neutral values as aurora.yaml legacy block |
| **Mechanism** | Operator updates one but not the other |
| **Effect** | Divergence between (dormant) aurora.yaml legacy and (active) expert config |
| **Severity** | LOW — aurora.yaml legacy is dead code. Expert config is canonical for experts. |
| **Mitigation** | Document in expert config comments: "These are independent of aurora.yaml legacy values. Update expert config directly." |

### R4. backtest_plugin.py provider factory complexity

| Attribute | Value |
|---|---|
| **Cause** | Adding a third provider type (judge_expert) to the factory |
| **Mechanism** | Factory dispatch logic grows; potential for interaction with adapter/ensemble paths |
| **Effect** | Regression in existing provider creation |
| **Severity** | LOW — factory is a simple if/elif chain; new branch is additive |
| **Mitigation** | Provider integration tests. Existing alpha_search tests as regression gate. |

### R5. Shadow event volume

| Attribute | Value |
|---|---|
| **Cause** | Two experts × N symbols × every 5-min bar → potentially many events |
| **Mechanism** | FSM event bus and JSONL logging handle high volume |
| **Effect** | Log disk usage, potential FSM overhead |
| **Severity** | LOW — existing alpha_search already emits per-provider per-symbol events at similar cadence |
| **Mitigation** | Per-symbol enable flags in expert config. JSONL rotation config (daily, max size). |

### R6. Silent legacy math reinjection via config change

| Attribute | Value |
|---|---|
| **Cause** | Operator changes expert `mode` to "hybrid_advisory" or beyond |
| **Mechanism** | Phase validator rejects non-admitted modes |
| **Effect** | None in Phase 2 — mode admission is enforced |
| **Severity** | ZERO in Phase 2 — defense built into config validation |
| **Mitigation** | Phase validator rejects all modes except "off" and "shadow" in Phase 2. |

---

## 18. Phase-2 Package Order

### Subpackage 2A: Expert Config Models

**Contents**: `JudgeExpertsConfig`, `SignalWeightsExpertConfig`, `FeatureNeutralsExpertConfig`, `JudgeShadowLogConfig`, `JudgeExpertProviderConfig` Pydantic models. Shadow mode admission in `JudgeCortexConfig`.

**Entry gate**: Phase 1 complete (judge/ sub-package + contracts exist in repo).
**Exit gate**: All config models instantiate with valid data and reject invalid data. Shadow mode admitted. Phase 1 tests still pass.

### Subpackage 2B: Expert Modules

**Contents**: `signal_weights_expert.py`, `feature_neutrals_expert.py`, `expert_output_bridge.py`, `__init__.py` under `judge/experts/`.

**Entry gate**: 2A complete.
**Exit gate**: Both experts produce correct `ExpertOutput` for known synthetic inputs. Historical golden tests pass. Fail-closed behavior verified.

### Subpackage 2C: Provider Integration

**Contents**: ProviderConfig extension, backtest_plugin factory branch.

**Entry gate**: 2B complete.
**Exit gate**: Experts callable via provider pipeline. `EVT:JUDGE_EXPERT_PRODUCED_V1` emitted on FSM mock. Existing providers unaffected.

### Subpackage 2D: Verb Registry + Schema + Domain Dict

**Contents**: verb_registry entry for `EVT:JUDGE_EXPERT_PRODUCED_V1`. Update `domain_dict.json` with new export surface.

**Entry gate**: 2C complete (ensures schema path exists from Phase 1).
**Exit gate**: Verb compiles in VerbSchemaRegistry. Expert event payload validates against schema. domain_dict.json reflects new exports.

### Subpackage 2E: Config YAML

**Contents**: `config/alpha_search.yaml` extended with expert config blocks.

**Entry gate**: 2A complete (Pydantic models exist to validate YAML).
**Exit gate**: `load_alpha_search_config()` succeeds with expert config. Both experts configurable. Mode admission works.

### Subpackage 2F: Test Suite

**Contents**: 8 test files covering all categories in Section 16.1.

**Entry gate**: 2A-2E complete.
**Exit gate**: 79+ tests pass. Zero regressions. Historical golden tests pass.

### Subpackage 2G: Report

**Contents**: `PHASE2_LEGACY_EXPERT_REVIVAL_REPORT.md`.

**Entry gate**: 2F complete.
**Exit gate**: Report contains explicit verdict, evidence of shadow emission, historical accuracy proof, what is proven, what remains for Phase 3.

---

## 19. Done Criteria

### Phase 2 Planning Done Criteria (this document)

- [x] One final document produced
- [x] Legacy expert revival specified as explicit shadow experts only
- [x] Live Aurora quadratic path remains untouched
- [x] alpha_search-aligned placement frozen
- [x] Historical recovery work is evidence-based
- [x] Runtime/event/config scope is concrete
- [x] Test matrix is concrete
- [x] Package order is concrete
- [x] No silent legacy math reinjection possible
- [x] Both experts' formulas fully specified from recovered evidence

### Phase 2 Implementation Done Criteria (for later coding agent)

- [ ] Phase 1 judge sub-package exists as prerequisite
- [ ] Both expert Pydantic config models compile and validate
- [ ] `signal_weights_expert` produces correct score for known inputs
- [ ] `feature_neutrals_expert` produces correct score for known inputs
- [ ] Historical golden tests pass (hand-computed expected values)
- [ ] Both experts produce valid `ExpertOutput` contracts
- [ ] `EVT:JUDGE_EXPERT_PRODUCED_V1` registered in verb registry and schema compiles
- [ ] Shadow mode admission works (off → skip, shadow → run)
- [ ] JSONL shadow logs written and parseable
- [ ] No constants hardcoded in expert modules
- [ ] Provider integration works via backtest_plugin factory
- [ ] 79+ tests pass with zero failures
- [ ] Zero regressions in Phase 1 judge tests
- [ ] Zero regressions in existing alpha_search tests
- [ ] Zero regressions in global test suite
- [ ] QuadraticScoringKernel.py is byte-identical before and after Phase 2
- [ ] No decision_making modules modified
- [ ] REPORT produced with verdict

---

## 20. Final Recommended Next Coding Task

**Prerequisite**: Phase 1 must be implemented first (Subpackages 1A through 1E).

**Task**: Implement Subpackage 2A (Expert Config Models), then Subpackage 2B (Expert Modules) in strict order.

**Step 1 — Subpackage 2A (config models)**: Extend `apps/reference/domains/alpha_search/judge/config_models.py` with `SignalWeightsExpertConfig`, `FeatureNeutralsExpertConfig`, `JudgeExpertsConfig`, `JudgeShadowLogConfig`. Update `JudgeCortexConfig` to add `experts: Optional[JudgeExpertsConfig]`, `shadow_log: Optional[JudgeShadowLogConfig]`, and extend the Phase validator to admit `"shadow"`. All models use `extra='forbid'`, `frozen=True`.

**Step 2 — Subpackage 2B (expert modules)**: Create `apps/reference/domains/alpha_search/judge/experts/` with `__init__.py`, `signal_weights_expert.py` (SignalWeightsExpert extending AlphaModel), `feature_neutrals_expert.py` (FeatureNeutralsExpert extending AlphaModel), and `expert_output_bridge.py` (AlphaScore → ExpertOutput mapping).

**Acceptance**: Both expert configs validate with production-equivalent YAML. Both experts produce correct `AlphaScore` and `ExpertOutput` for synthetic inputs matching hand-computed expected values. Phase 1 judge tests still pass.

**Hard constraints**:
- Do not modify `main.py`, `config_loader.py`, root `config_models.py`, or any `decision_making` module.
- Do not modify `quadratic_scoring_kernel.py`.
- Do not emit events (event emission comes in Subpackage 2C/2D).
- Do not hardcode any numerical constants — all from config.
- All default config values must be documented as "Phase 9 legacy revival defaults".
