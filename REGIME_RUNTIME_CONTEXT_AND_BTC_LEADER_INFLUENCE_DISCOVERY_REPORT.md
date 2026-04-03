# REGIME_RUNTIME_CONTEXT_AND_BTC_LEADER_INFLUENCE_DISCOVERY_REPORT

## 1. Executive Summary

### Final runtime truth in one page

- Current structural regime is produced by `apps/reference/domains/regime_detector/regime_detector.py::RegimeDetector` from `EVT:FEATURES_CALCULATED` only, on the configured basis bar clock only.
- The emitted structural regime is symbol-local, bar-clocked, hysteresis-confirmed, and accompanied by stable and raw confidence fields. It is not a global market regime.
- The current detector does not implement an explicit lifecycle model such as onset, mature, peak, or fade. It only exposes indirect lifecycle-like hints: `raw_regime` vs `regime`, hysteresis counters, volatility-slope rejection, and downstream `regime_age_sec`.
- Regime and `regime_confidence` materially affect live decisions today:
  - Aurora liveness fail-closed
  - Aurora regime allowlist / kill-switch blocking
  - Aurora threshold scaling through `regime_threshold_multipliers`
  - Aurora inception rescue logic comparing raw vs stable regime
  - safety-gate trend confirmation
  - forced close logic on regime flips
  - objective-engine context for Aurora, MD-AMR, and mean reversion
- BTC influence is already present in active runtime, but not as BTC regime mutation:
  - feature-engineering anchor intake via `EVT:ANCHOR_UPDATED`
  - active `macro_resid` computation
  - active Aurora `anchor_shock_veto`
  - active market-data anchor freshness / timestamp causality chain
- The most important hidden coupling is that current `macro_resid` logic is effectively BTC-led for non-BTC symbols, because `feature_engineering.py` currently pulls BTC anchor history explicitly for `macro_resid`. Any future BTC-follow design risks double-counting unless it is additive-only and explicitly separated from existing anchor-derived features and vetoes.

### Safest current architectural reading

- Structural regime truth should remain owned by `regime_detector`.
- Any future BTC-led influence should not overwrite local structural regime truth.
- The safest future attachment point, based on current contracts, is a separate additive policy layer or strategy-local overlay that consumes both local regime and BTC/anchor context and emits its own explainable effect.
- Mutating detector output with BTC-led logic has the highest contract and double-count risk.

---

## 2. FACTS

### Regime production

- `DecisionMaking` subscribes to `EVT:REGIME_DETECTED`, but does not compute regime.
- `RegimeDetector` subscribes to `EVT:FEATURES_CALCULATED` and ignores `TICK_FEATURES_CALCULATED`.
- `RegimeDetector.handle_event()` ignores any payload where `tf_sec == 0` or `tf_sec != basis_tf_sec`.
- `tests/domains/regime_detector/test_reg_fix_01_bar_only.py` proves tick events and non-basis bar events are ignored.
- `RegimeDetector` stores internal buffers for close, true range, ATR, volatility ratio, hysteresis, and heartbeat timing.
- Detection order is:
  1. stale / invalid / warmup guard
  2. volatility branch
  3. volatility-slope rejection branch
  4. mean-reversion branch
  5. SMA-trend branch
  6. `uncertain_cutoff` demotion
  7. hysteresis stabilization
  8. `EVT:REGIME_DETECTED` emission
- `EVT:REGIME_DETECTED` payload carries both stable and raw fields:
  - `regime`, `confidence`
  - `raw_regime`, `raw_confidence`
  - `stable_confidence`
  - `changed`
  - `last_update_ts_ms`
  - `calc_lag_ms`
  - `vol_ratio`, `vol_ratio_slope`, `storm_rejected`
  - `hysteresis_confirm_count`
  - `warmup`
  - `data_quality`
  - `regime_layer`, `regime_scope`, `regime_clock`, `regime_owner`, `structural_regime_ref`
- Current detector emits structural per-symbol regime, not a global backdrop regime.

### Regime consumption

- `DecisionMaking.event_handlers.on_regime()` stores per-symbol structural regime snapshots in `_per_symbol_regimes`.
- `intent_emitter.py` forces close on incompatible regime flips:
  - short in `TREND_UP`
  - long in `TREND_DOWN`
  - any position in `UNCERTAIN`
- `AuroraHandler.on_regime_detected()` caches `regime`, `raw_regime`, `regime_confidence`, timestamps, and detector heartbeat.
- `AuroraHandler._check_regime_liveness()` blocks fail-closed when heartbeat is missing or stale.
- `aurora_decision.py` uses current regime for threshold scaling, allowlist gating, blocked-regime gating, inception rescue, objective context, and event payloads.
- `safety_gates.py` reads per-symbol `regime` and `confidence`, and blocks if regime confidence is below the configured threshold.
- `md_amr_handler.py` and `mean_reversion_handler.py` both consume regime, regime timestamp, and regime confidence for objective-engine inputs.
- `execution_position.event_handlers.on_regime_detected()` caches per-symbol structural regime and can cancel pending entries on regime change.
- `execution_position` applies global exposure adaptation only when `should_apply_global_execution_regime(payload)` is true. Structural per-symbol regime events do not trigger that path.

### Active Aurora math path

- `quadratic_scoring_kernel.py` is the sole active Aurora scoring path.
- The quadratic kernel reads `linear_score` or `features["pillar_sum"]` as the active conviction input.
- The quadratic kernel explicitly documents that `signal_weights`, `feature_neutrals`, `direction_strength_cfg`, `essential_features`, and `regime_smoother` are accepted for compatibility but not read by the kernel.
- Threshold widening by regime is active in the kernel through `regime_threshold_multipliers`.
- Side-bias widening is active in the kernel.
- Hysteresis side selection is active in the kernel.
- Shield cascade is active in the kernel and loader.
- `decision.regime_thresholds` exists in typed config, but live Aurora math reads `regime_threshold_multipliers` via loader/helpers instead.

### BTC / anchor / macro influence

- `market_data_connector.py` and `proxy.py` emit `EVT:ANCHOR_UPDATED`.
- `feature_engineering.py` subscribes to `EVT:ANCHOR_UPDATED`, enforces exchange-derived `ts_ms`, and updates anchor buffers plus the macro-sync resampler.
- `tests/domains/market_data/test_task30_anchor_ts_propagation.py` proves the anchor timestamp propagation chain and FE fail-closed behavior on missing timestamps.
- `domains.feature_engineering.macro_sync` in `config/aurora/domains.yaml` is wired and active inside feature engineering.
- `MacroSyncResampler` is active, timestamp-aware, TTL-aware, and fail-closed.
- `feature_engineering.py` computes `macro_sync`, but no live consumer was proven in current `decision_making` runtime.
- `feature_engineering.py` computes `macro_resid`, and for non-BTC symbols it explicitly pulls BTC anchor history in the current runtime path.
- Aurora `anchor_shock_veto` reads `features["macro_resid"]`, defaults the anchor symbol to `BTCUSDT`, and blocks long entries on non-anchor symbols when the residual breaches the configured downside threshold.

### Assignment and opt-in boundaries

- `config/aurora/strategies.yaml` is the assignment SSOT for symbol-to-strategy routing.
- `StrategyRuntime` only starts handlers for strategies that are assigned in the registry.
- `ConfigResolver.check_strategy_arbitration()` fails closed when a symbol is not assigned to the strategy attempting to act.
- `AuroraHandler`, `MeanReversionHandler`, and `MD-AMR` all derive enabled symbols from registry assignments first.
- Per-symbol `allowed_regimes` are active and strategy-local.

---

## 3. INFERENCES

### I1. Current regime truth is local structural state, not macro policy state

- Cause: detector subscribes per symbol to bar feature events and emits `regime_scope=per_symbol`, `regime_layer=structural`.
- Mechanism: regime is computed from each symbol's own close / ATR / SMA / warmup state.
- Effect: detector output is the local structural market state for that symbol.
- Operational risk: if future BTC-led logic is inserted here, downstream consumers may misread BTC-conditioned policy as local truth.

### I2. There are already two separate anti-churn layers

- Cause: detector hysteresis stabilizes emitted structural regime, and Aurora optionally applies regime inertia internally through `regime_raw` vs `regime_effective`.
- Mechanism: first layer delays detector label changes; second layer can delay strategy behavior changes.
- Effect: lifecycle-like behavior is already partially masked in two places.
- Operational risk: adding lifecycle semantics without separating these layers will create hard-to-debug duplicate delays and masked transitions.

### I3. BTC influence already exists as cross-asset feature/policy context

- Cause: anchor events feed FE, `macro_resid` uses BTC anchor history for non-BTC symbols, and Aurora vetoes long entries using anchor-derived residual context.
- Mechanism: BTC affects non-BTC decisions through feature engineering and policy veto, not through detector regime mutation.
- Effect: a future BTC-follow design would not be the first BTC influence path.
- Operational risk: a new BTC-led overlay can easily count the same BTC move once in `macro_resid`, again in `anchor_shock_veto`, and again in threshold policy if not separated.

### I4. The current active Aurora score path does not prove direct use of `macro_resid` in score math

- Cause: quadratic kernel reads `pillar_sum`; FE pillar aggregation is computed from tactician/operator/strategist multi-timeframe pillars, not from `macro_resid`.
- Mechanism: `macro_resid` is still visible in feature payloads and is used by veto logic, but live quadratic math reads `pillar_sum`.
- Effect: current direct BTC impact on Aurora appears stronger in veto/policy than in the active score kernel.
- Operational risk: assuming BTC is absent from current score math is safer than assuming it is active there; current evidence supports veto influence, not pillar influence.

### I5. The cleanest future opt-in boundary already exists

- Cause: registry assignment and per-symbol strategy config already determine which strategy may act on which symbol.
- Mechanism: handlers fail closed if the symbol is not assigned or not enabled.
- Effect: later BTC-follow opt-in can be expressed as symbol/strategy-local capability, not as a global detector contract change.
- Operational risk: moving opt-in semantics into the detector or global event contract would widen blast radius unnecessarily.

---

## 4. UNKNOWNS

- UNPROVEN: whether any live non-Aurora decision path beyond vetoes uses `macro_sync` for direct decisioning today.
- UNPROVEN: whether any external/replay tooling depends on the exact current structural regime payload shape beyond traced consumers.
- UNPROVEN: whether future global execution regime producers already exist elsewhere; the contract exists, but the current traced structural detector does not emit that shape.
- UNPROVEN: whether any off-path analytics or monitoring consumers treat `raw_regime` as tradeable truth rather than diagnostics.
- UNPROVEN: whether dormant documentation around linear v2 or legacy Aurora scoring still drives operator behavior outside code.
- UNKNOWN / repo-shape issue: there is no single repo-root `domain_dict.json`; only per-domain `domain_dict.json` files were present.

---

## 5. Current Regime Runtime Truth

### Producer

- Producer path: `apps/reference/domains/regime_detector/regime_detector.py`
- Class: `RegimeDetector`
- Input event: `EVT:FEATURES_CALCULATED`
- Producer contract note: bar-only structural regime detector

### Practical event path

1. `feature_engineering` emits `EVT:FEATURES_CALCULATED` on bar closes.
2. `RegimeDetector.handle_event()` accepts only basis-bar payloads.
3. Detector computes raw regime and confidence from symbol-local state.
4. Detector stabilizes through hysteresis.
5. Detector emits `EVT:REGIME_DETECTED`.
6. `decision_making`, `objective_engine`, and `execution_position` consume the event.

### Exact gating sequence

1. Validate event type and payload shape.
2. Enforce bar-only / basis timeframe.
3. Validate staleness / warmup / data quality.
4. Update internal buffers.
5. Compute volatility state first.
6. If high volatility candidate, optionally apply volatility-slope rejection.
7. If volatility does not win, test mean reversion.
8. If mean reversion does not win, test SMA trend.
9. Apply `uncertain_cutoff`.
10. Apply hysteresis.
11. Emit stable regime payload plus raw diagnostics.

### Exact internal state

- Price / volatility buffers: `_price_buf`, `_tr_buf`, `_atr_buf`, `_atr_last`
- Heartbeat / cadence: `_ticks_seen`, `_last_basis_close_boundary_ts_ms`
- Hysteresis state: `_hysteresis_stable`, `_hysteresis_pending`, `_hysteresis_count`, `_stable_confidence`
- Volatility-slope state: `_vol_ratio_buf`, `_slope_reject_count`
- Diagnostics: `_rd_diag`

### What the current labels mean

- `raw_regime`: branch output before detector hysteresis.
- `regime`: detector-stable regime after hysteresis.
- `confidence`: stable regime confidence emitted downstream.
- `stable_confidence`: explicit stable confidence mirror.
- `raw_confidence`: pre-hysteresis confidence.

### Lifecycle semantics check

- Proven present:
  - raw vs stable transition distinction
  - hysteresis confirmation count
  - volatility-storm rejection when volatility slope decays
  - downstream `regime_age_sec`
- Not proven present:
  - onset phase label
  - mature phase label
  - exhaustion label
  - fade label
  - lifecycle-specific event contract

### Important conclusion

- Symptom: some surfaces look lifecycle-aware.
- Root cause: the system has stabilization and age metadata, not a real lifecycle model.
- Contributing factor: Aurora anti-churn adds a second masking layer.
- Masking layer: detector hysteresis plus Aurora regime inertia can make lifecycle-like effects appear without lifecycle semantics actually existing.

---

## 6. Current Regime Consumer Map

| Consumer | Location | Field consumed | Effect type | Status | Severity if wrong |
|---|---|---|---|---|---|
| DecisionMaking per-symbol cache | `apps/reference/domains/decision_making/event_handlers.py` | `regime`, `confidence`, `warmup`, metadata | Shared structural snapshot | ACTIVE | High |
| Regime flip close path | `apps/reference/domains/decision_making/intent_emitter.py` | `regime` | Forced close / flatten | ACTIVE | High |
| Aurora cache | `apps/reference/domains/decision_making/aurora_handler.py` | `regime`, `raw_regime`, `confidence`, timestamps | Strategy state | ACTIVE | High |
| Aurora liveness guard | `apps/reference/domains/decision_making/aurora_handler.py` | heartbeat + `basis_tf_sec * liveness_factor` | Fail-closed blocker | ACTIVE | High |
| Aurora threshold math | `apps/reference/domains/decision_making/aurora_decision.py` + kernel | `regime` | Threshold multiplier | ACTIVE | High |
| Aurora allowlist | `apps/reference/domains/decision_making/aurora_decision.py` | `regime` | Entry allow/deny | ACTIVE | High |
| Aurora blocked-regimes | `apps/reference/domains/decision_making/aurora_decision.py` | `regime` | Hard deny | ACTIVE | High |
| Aurora inception rescue | `apps/reference/domains/decision_making/aurora_decision.py` | `raw_regime` vs stable regime | Limited additive entry logic | ACTIVE | Medium |
| Aurora objective context | `apps/reference/domains/decision_making/aurora_decision.py` | `regime`, `regime_age_sec`, `regime_confidence` | Objective scoring context | ACTIVE | Medium |
| Safety gates | `apps/reference/domains/decision_making/safety_gates.py` | `regime`, `confidence` | Trend-confirmation deny | ACTIVE | High |
| MD-AMR objective input | `apps/reference/domains/decision_making/md_amr_handler.py` | `regime`, `confidence`, timestamp | Objective sizing context | ACTIVE | Medium |
| Mean reversion objective input | `apps/reference/domains/decision_making/mean_reversion_handler.py` | `regime`, `confidence`, timestamp | Objective sizing context | ACTIVE | Medium |
| Mean reversion regime store | `apps/reference/domains/decision_making/mean_reversion_handler.py` | `regime`, `confidence`, timestamp | Strategy-local gating context | ACTIVE | Medium |
| Objective engine registry | `apps/reference/domains/objective_engine/runtime.py` | `regime` | Snapshot annotation | ACTIVE | Low |
| Execution-position cache | `apps/reference/domains/execution_position/event_handlers.py` | `regime`, `symbol` | State cache | ACTIVE | Medium |
| Execution pending-entry cancel | `apps/reference/domains/execution_position/event_handlers.py` | `regime` change | Cancel pending entry | ACTIVE | Medium |
| Global execution regime adaptation | `apps/reference/domains/execution_position/event_handlers.py` | `regime_layer`, `regime_scope`, `regime` | Exposure adaptation | AMBIGUOUS CONTRACT / NOT TRIGGERED BY CURRENT STRUCTURAL DETECTOR | High |

### Regime-related blocked-event surfaces

- `EVT:STRATEGY_DECISION_BLOCKED`
  - Aurora ordinary no-trade denials
  - mean reversion no-trade denials
  - anchor veto
- `EVT:DECISION_BLOCKED`
  - decision-making contract failures and normalized config failures
- `EVT:DECISION_TRACE_EMITTED`
  - safety-deny trace with regime and confidence

---

## 7. Active Aurora Math / Gate Surface

### ACTIVE

- Quadratic kernel
- `pillar_sum`
- shield cascade
- `signal_threshold`
- `regime_threshold_multipliers`
- per-symbol regime threshold overrides
- hysteresis side-selection
- side-bias widening
- liquidity gate
- holding period
- reentry cooldown
- blocked-regimes kill-switch
- regime allowlist
- regime liveness
- directional sanity / safety gates
- price-motion sanity / vol-adjusted gates
- anchor shock veto
- objective-engine context

### LEGACY or DECLARED-BUT-NOT-USED

- Linear v2 kernel
- `signal_weights` as live quadratic weights
- `feature_neutrals` as live quadratic centering inputs
- `direction_strength_scoring` as live quadratic input
- global `decision.regime_thresholds`
- `regime_smoother` in current quadratic kernel
- `macro_sync` as proven live Aurora decision input

### Dangerous stale assumptions

- Assuming detector regime is the only anti-churn layer is false.
- Assuming BTC influence is absent because detector is local-only is false.
- Assuming `macro_sync` documentation implies live policy use is unsafe.
- Assuming typed presence of `regime_thresholds` means live threshold routing is unsafe.
- Assuming Aurora still depends on linear v2 math is false.

---

## 8. Existing BTC / Anchor / Macro Influence Inventory

### BTC_ANCHOR_INFLUENCE_INVENTORY

| Surface | Owner | Source | Consumer | Direct effect | Status | Double-count risk |
|---|---|---|---|---|---|---|
| `EVT:ANCHOR_UPDATED` | `market_data` | connector / proxy | `feature_engineering` | Anchor price intake only | ACTIVE | Low by itself |
| Anchor timestamp causality | `feature_engineering` | `EVT:ANCHOR_UPDATED.ts_ms` | FE readiness / buffers | Fail-closed on malformed or missing anchor timestamps | ACTIVE | Medium if future logic ignores freshness |
| `domains.feature_engineering.macro_sync.*` | `feature_engineering` | `domains.yaml` | FE macro-sync path | Correlation-style anchor context feature | ACTIVE inside FE | Medium |
| `features["macro_sync"]` | `feature_engineering` | FE payload | no live DM consumer proven | Observability / feature payload only | UNPROVEN as live decision input | Low to Medium |
| `macro_resid` compute path | `feature_engineering` | local asset return + BTC anchor return | FE payload / Aurora veto | Signed BTC-relative residual context | ACTIVE | High |
| Hardcoded BTC anchor path for `macro_resid` | `feature_engineering.py` | BTC anchor history lookup | all non-BTC `macro_resid` | Makes current residual logic BTC-led in practice | ACTIVE | High |
| `anchor_shock_veto` | Aurora decision policy | `features["macro_resid"]` + config | Aurora | Blocks BUY on non-anchor symbols during downside BTC-relative shock | ACTIVE | High |
| Market-data anchor tracking in websocket aggregator | `market_data` | anchor symbol streams | connector/proxy callback chain | Data acquisition only | ACTIVE | Low |
| Structural regime payload metadata (`regime_layer/scope`) | detector contract | structural detector | execution_position | Distinguishes structural from global regime | ACTIVE | Medium if future BTC logic fakes structural regime |

### Important conclusion

- Symptom: there is no explicit `follow_btc` strategy flag today.
- Root cause: BTC influence is already implicit in feature and veto layers.
- Contributing factor: `macro_resid` uses BTC specifically in current FE runtime.
- Masking layer: because the effect is not named `follow_btc`, it is easy to underestimate.

---

## 9. Double-Count Risk Matrix

| Severity | Overlap | Cause | Mechanism | What gets counted twice | Distortion | Needed observability |
|---|---|---|---|---|---|---|
| High | BTC-follow overlay + `macro_resid` | `macro_resid` already embeds BTC-relative context | overlay reacts to BTC move that already changed residual feature state | same BTC dislocation | exaggerated directional conviction or over-blocking | explicit local-vs-BTC contribution fields |
| High | BTC-follow overlay + `anchor_shock_veto` | Aurora already blocks BUY on BTC downside shock | overlay also reduces threshold / blocks / flips | same BTC downside event | duplicate veto stack, opaque no-trade outcomes | trace field naming every BTC-derived blocker |
| High | BTC-follow mutation + structural regime threshold multipliers | detector regime currently drives threshold widening | BTC mutation changes structural regime then threshold logic fires | BTC context once as regime mutation, again as downstream policy | wrong threshold regime, incorrect local truth | separate structural regime and additive policy regime in traces |
| High | BTC-follow mutation + regime flip forced close | regime flip close path assumes regime is local truth | BTC-conditioned regime flip can force close local positions | BTC context as fake local regime reversal | unnecessary flattening and churn | close trace must state local cause vs overlay cause |
| Medium | BTC-follow overlay + Aurora anti-churn inertia | Aurora already delays effective regime transitions | overlay adds another delay / acceleration layer | same transition timing logic | hidden phase lag and whipsaw masking | emit raw, stable, effective, overlay states separately |
| Medium | BTC-follow overlay + directional sanity / price-motion sanity | current sanity gates already block weak/overextended entries | overlay also penalizes same market regime | shared risk-off condition | strategy becomes too inert | trace must show veto order and cumulative threshold changes |
| Medium | BTC-follow overlay + symbol-specific `allowed_regimes` | symbol already uses local allowlist | overlay may indirectly convert or reinterpret local regime | same decision boundary via two abstractions | inconsistent opt-in behavior across strategies | event payload needs local regime and overlay decision separately |
| Low to Medium | BTC-follow overlay + `macro_sync` | macro-sync may be revived or read elsewhere | same anchor relation modeled twice | correlation plus leader-follow hint | operator confusion more than immediate runtime damage | contract-level status telemetry for macro_sync use |

### Worst-case scenarios

#### High-risk scenario A

- BTC sells off sharply.
- `macro_resid` turns strongly negative for ALT symbol.
- Aurora `anchor_shock_veto` blocks BUY.
- A future BTC-follow overlay also downgrades local regime to `UNCERTAIN`.
- Regime flip close path flattens open long exposure.
- Result: one BTC move is counted in feature context, blocker policy, and fake local regime mutation.

#### High-risk scenario B

- Local symbol remains in valid `TREND_UP`.
- BTC weakens temporarily.
- BTC-led mutation rewrites local regime to `UNCERTAIN`.
- Aurora threshold multipliers, forced-close logic, and allowlist gates all react as if the local symbol changed state.
- Result: policy-level macro context is misrepresented as structural truth.

#### High-risk scenario C

- BTC spike and decay happens during high-volatility local conditions.
- Detector volatility-slope gate already marks storm fade.
- Aurora anti-churn inertia delays effective switch.
- Future lifecycle overlay adds another phase gate tied to BTC.
- Result: three timing layers produce ambiguous entry/exit behavior that cannot be explained from current traces.

---

## 10. Candidate Ownership Analysis for Future Additive Logic

| Candidate owner | Ownership fit | Event contract fit | Observability fit | Double-count risk | Testability | Replay friendliness | Config complexity | Blast radius | Additive-only compatibility |
|---|---|---|---|---|---|---|---|---|---|
| `regime_detector` | Poor for BTC-led policy | Poor | Poor unless payload expands | Highest | Medium | Medium | Medium | Highest | Poor |
| `feature_engineering` | Medium for anchor context, poor for policy | Medium | Medium | High because FE already owns anchor features | High | High | Medium | High | Medium |
| `decision_making` | Strong | Strong | Strong | Medium | High | High | Medium | Medium | Strong |
| strategy-local overlay | Strong for opt-in | Strong | Strong if emitted in strategy payloads | Medium to Low | High | High | Medium to High | Low | Strong |
| separate domain/service | Strongest isolation | Medium to Strong if new explicit event | Strong if contract is explicit | Lowest | Medium | Medium to High | Highest | Medium | Strongest |

### Strongest candidate

- Best current candidate: separate additive policy layer, either:
  - a distinct decision-policy sidecar under `decision_making`, or
  - a separate domain/service consumed by strategies or decision-making

### Why that candidate wins

- Cause: structural regime contract is already well-defined and widely consumed as local truth.
- Mechanism: additive sidecar can consume local regime plus BTC context without mutating the structural contract.
- Effect: local truth remains local; BTC context remains explainable and bounded.
- Operational risk: still requires explicit observability fields, but avoids most double-count and contract corruption risk.

### Rejected candidates

- `regime_detector`
  - Reject because it would blur local structural truth with cross-asset policy interpretation.
- `feature_engineering`
  - Reject as primary owner because FE already computes anchor context; adding decision semantics here increases hidden coupling and double-count risk.
- pure strategy-local only
  - Better than detector mutation, but risks fragmentation if multiple strategies need the same semantics with inconsistent traces.

### Still unproven

- Whether a separate service should emit its own event or only annotate strategy/decision traces.
- Whether execution_position would need to see the additive context later.

---

## 11. Opt-In / Subscription Feasibility

### Feasibility assessment

- Symbol-level opt-in is feasible with current architecture.
- Strategy-level opt-in is feasible with current architecture.
- Assignment-first activation helps rather than hurts this requirement.

### Why

- `strategies.yaml` already defines symbol ownership.
- handlers already fail closed when symbol assignment is missing.
- per-symbol strategy config already supports local overrides such as `allowed_regimes`, thresholds, and cooldowns.

### Minimal future contract candidates

- per-symbol strategy-local flag
- per-strategy policy block with per-symbol override
- explicit additive context toggle in decision policy, not in structural detector config

### Best layer for future opt-in semantics

- decision-policy or strategy-local overlay layer

### What must remain immutable

- local structural regime event meaning
- assignment-first arbitration
- fail-closed handler activation rules
- `EVT:REGIME_DETECTED` as local structural truth unless a distinct new contract is introduced

---

## 12. Observability Gaps

### Current coverage map

| Question | Current evidence surface | Coverage |
|---|---|---|
| Why did detector choose this local regime? | `EVT:REGIME_DETECTED` payload fields | Partial |
| What was raw vs stable regime? | `raw_regime`, `regime`, hysteresis fields | Good |
| What was regime confidence? | `confidence`, `raw_confidence`, `stable_confidence` | Good |
| Why did Aurora deny a trade? | `EVT:STRATEGY_DECISION_BLOCKED` | Good |
| What threshold math ran? | `EVT:QUADRATIC_DECISION_TRACE` | Good |
| What regime reached strategy signal emission? | `EVT:STRATEGY_SIGNAL_PRODUCED.regime_ctx` | Good |
| What safety gate denied? | `EVT:DECISION_TRACE_EMITTED` | Good |
| What BTC/anchor effect was applied? | `macro_resid` in features, anchor veto blocked event | Partial |
| What lifecycle phase was inferred? | no dedicated field | Poor |
| What additive overlay would have changed? | no current field | Missing |

### Missing fields list

- explicit lifecycle phase
- explicit lifecycle confidence
- explicit local-regime vs overlay-regime distinction
- explicit BTC/anchor influence attribution
- explicit cumulative threshold adjustments by source
- explicit statement of whether a block was caused by structural regime, additive overlay, or anchor-derived veto

### Masking layers that make future debugging unsafe

- detector hysteresis
- Aurora anti-churn regime inertia
- threshold widening by regime
- side-bias threshold widening
- anchor shock veto
- safety-gate trend confirmation

---

## 13. What Must Not Be Changed Yet

- Do not mutate `EVT:REGIME_DETECTED` semantics to include BTC-led policy without a new explicit contract.
- Do not treat typed config presence as proof of live consumption.
- Do not anchor future design on linear v2 Aurora math.
- Do not assume `macro_sync` is the main current BTC path; `macro_resid` and vetoes are the stronger proven paths.
- Do not remove or bypass assignment-first strategy arbitration.
- Do not collapse raw regime, stable regime, and Aurora effective regime into one conceptual state.
- Do not assume lifecycle semantics already exist because there are hysteresis or age fields.

---

## 14. Final Verdict

### Answers to the operator's five design-gating questions

1. Should lifecycle modeling attach to local regime truth or to policy-level interpretation?

- Current evidence favors policy-level interpretation or a separate additive layer, not mutation of structural detector truth.

2. Should BTC-led influence be modeled as core regime mutation, sidecar context, decision policy modifier, strategy-local overlay, or separate service/domain?

- Current evidence rejects core regime mutation as the safe default.
- The safest current direction is sidecar context / decision-policy modifier / separate service.

3. Where would future additive logic create double-counting?

- `macro_resid`
- `anchor_shock_veto`
- threshold adaptation through regime multipliers
- regime flip close path if local regime is mutated
- anti-churn timing layers

4. What is the safest owner and the smallest future contract surface?

- Safest owner: additive policy layer outside structural detector, ideally in decision-making or a separate service.
- Smallest safe contract: keep local structural regime untouched and add explicit overlay context with bounded effect and observability.

5. What exact unknowns still block design?

- whether any hidden live consumers use `macro_sync`
- whether future global execution regime producers already exist or are planned
- what explicit observability fields are minimally required so additive BTC logic can be debugged without ambiguity

### Bottom line

- The current system already has meaningful BTC-led cross-asset influence.
- It does not yet have explicit regime lifecycle modeling.
- The structural detector is not the safe place to blend in BTC-led policy.
- Any future design must preserve local regime truth, avoid double-counting existing BTC-derived context, and add explicit attribution fields before rollout.
