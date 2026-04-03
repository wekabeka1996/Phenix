# REGIME_CONTEXT_EVIDENCE_APPENDIX

## Evidence Rules Used

- `runtime-proven`: code path directly traced in active runtime modules
- `test-proven`: reinforced by targeted tests
- `config-only`: typed / YAML presence without live consumer proof
- `doc-only`: passport or documentation claim, not relied on as runtime proof by itself

---

## A. Regime Producer and Contract Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Regime producer is `RegimeDetector` | `apps/reference/domains/regime_detector/regime_detector.py` | `class RegimeDetector` | Detector owns regime buffers, classification, hysteresis, and event emission | runtime-proven |
| Detector subscribes to `EVT:FEATURES_CALCULATED` only | `apps/reference/domains/regime_detector/regime_detector.py` | `_subscribe_once()` | Explicit listener registration for bar features | runtime-proven |
| Tick-aware regime path is not used | `apps/reference/domains/regime_detector/regime_detector.py` | `handle_event()` early guards | Ignores `tf_sec == 0` and mismatched timeframes | runtime-proven |
| Tick and non-basis events are ignored | `tests/domains/regime_detector/test_reg_fix_01_bar_only.py` | bar-only contract tests | Tests assert detector stays silent on tick/non-basis payloads | test-proven |
| Detector emits stable plus raw regime fields | `apps/reference/domains/regime_detector/regime_detector.py` | final payload build | Payload includes `regime`, `raw_regime`, `confidence`, `raw_confidence`, hysteresis metadata | runtime-proven |
| Structural regime event schema supports current payload | `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json` | schema properties | Schema includes regime metadata, confidence, heartbeat, structural metadata | runtime-proven |
| Detector is structural / per-symbol / bar-clocked by default | `apps/reference/domains/regime_detector/regime_detector.py` | emitted payload metadata | Event carries `regime_layer=structural`, `regime_scope=per_symbol`, `regime_clock=bar` | runtime-proven |
| `basis_tf_sec`, `uncertain_cutoff`, `hysteresis_bars` are active | `config/aurora/regime.yaml` | top-level config block | Current regime config defines these values used in detector | config + runtime-proven |
| `liveness_factor` belongs to downstream guard, not detector math | `config/docs/regime_passport.md` | `liveness_factor` section | Passport matches traced runtime ownership in AuroraHandler | doc-supported + runtime-proven |

---

## B. Detector Math and Lifecycle-Like Semantics

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Detection order is volatility -> MR -> trend -> uncertain -> hysteresis | `apps/reference/domains/regime_detector/regime_detector.py` | main classification block | Branch order is explicit in code | runtime-proven |
| Volatility slope gate can demote `HIGH_VOLATILITY` to `UNCERTAIN` | `apps/reference/domains/regime_detector/regime_detector.py` | slope-gate block | Uses slope counter, epsilon, confirm bars, `storm_rejected` | runtime-proven |
| Detector keeps hysteresis counters and stable confidence | `apps/reference/domains/regime_detector/regime_detector.py` | hysteresis state and finalize block | Stable state and pending state are stored separately | runtime-proven |
| No explicit onset/mature/peak/fade labels exist | `apps/reference/domains/regime_detector/regime_detector.py` | entire module | No lifecycle enum/field or phase model found | runtime-proven negative |
| Limited lifecycle hints do exist | `apps/reference/domains/regime_detector/regime_detector.py` | `raw_regime` / `storm_rejected` / hysteresis fields | Raw vs stable distinction and storm-fade rejection are visible | runtime-proven |

---

## C. Decision and Strategy Consumer Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| DecisionMaking listens to `EVT:REGIME_DETECTED` | `apps/reference/domains/decision_making/decision_making.py` | listener wiring | Event bus registration present | runtime-proven |
| DecisionMaking stores per-symbol structural regime snapshot | `apps/reference/domains/decision_making/event_handlers.py` | `on_regime()` | Writes `_per_symbol_regimes` with regime, confidence, warmup, metadata | runtime-proven |
| Regime flips can force position close | `apps/reference/domains/decision_making/intent_emitter.py` | regime flip close path | Close on `TREND_UP/TREND_DOWN/UNCERTAIN` incompatibility | runtime-proven |
| Aurora caches regime, raw regime, confidence, heartbeat | `apps/reference/domains/decision_making/aurora_handler.py` | `SymbolState`, `on_regime_detected()` | Local strategy state mirrors structural regime | runtime-proven |
| Aurora liveness guard blocks on dead/missing detector heartbeat | `apps/reference/domains/decision_making/aurora_handler.py` | `_check_regime_liveness()` | Emits fail-closed reason codes using `basis_tf_sec * liveness_factor` | runtime-proven |
| Aurora applies separate anti-churn regime inertia | `apps/reference/domains/decision_making/aurora_handler.py` | `_update_effective_regime()` | Raw and effective regime split with delayed risk-on and immediate risk-off | runtime-proven |
| Aurora allowlist and blocked-regimes gates are active | `apps/reference/domains/decision_making/aurora_decision.py` | regime gating blocks | Entry deny uses current regime | runtime-proven |
| Aurora objective input includes regime age and confidence | `apps/reference/domains/decision_making/aurora_decision.py` | objective build block | `build_signal_input()` receives regime fields | runtime-proven |
| Safety gates deny on low regime confidence | `apps/reference/domains/decision_making/safety_gates.py` | regime-confidence gate | Reads per-symbol regime snapshot and blocks | runtime-proven |
| MD-AMR requires regime, confidence, timestamp for objective path | `apps/reference/domains/decision_making/md_amr_handler.py` | objective block | Raises if regime context missing | runtime-proven |
| Mean reversion requires regime, confidence, timestamp for objective path | `apps/reference/domains/decision_making/mean_reversion_handler.py` | objective block | Raises if regime context missing | runtime-proven |
| Execution-position only applies global adaptation for explicit global non-structural regime events | `apps/reference/contracts/runtime_regime_layers.py` | `should_apply_global_execution_regime()` | Requires `scope=global` and non-structural layer | runtime-proven |
| Structural regime does not trigger global execution adaptation | `tests/contracts/test_runtime_regime_layers.py` | compatibility tests | Default structural payload returns false for global adaptation | test-proven |

---

## D. Active vs Legacy Aurora Math Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Linear v2 file is removed | `config/docs/aurora_math_passport.md` | audit summary | Passport records removal; no live file found in repo | doc-supported + repo-shape evidence |
| Quadratic kernel is sole active path | `apps/reference/domains/decision_making/aurora_config_loader.py` | loader scoring-engine wiring | Loader mounts `QuadraticScoringKernel` | runtime-proven |
| Quadratic kernel reads `pillar_sum` only | `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | `compute()` | Compatibility kwargs accepted but not read; live input is `linear_score` or `features["pillar_sum"]` | runtime-proven |
| `signal_weights`, `feature_neutrals`, `direction_strength_scoring` are not active quadratic inputs | `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | `compute()` docstring / comments | Explicit compatibility-only statement | runtime-proven |
| `decision.regime_thresholds` is declared but not used for live threshold math | `config/docs/aurora_math_passport.md` | `regime_thresholds` section | Passport matches traced loader/helper behavior | doc-supported + runtime-proven |
| Live threshold math uses `regime_threshold_multipliers` | `apps/reference/domains/decision_making/aurora_scoring_helpers.py` | `_get_regime_thresholds()` | Per-symbol override else global multipliers | runtime-proven |
| Side-bias is active | `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | `_compute_side_bias_mult()` | Live threshold widening by side history | runtime-proven |
| Shield cascade is active | `apps/reference/domains/decision_making/aurora_config_loader.py` | shield loader block | Loader enables shield function; kernel consumes it | runtime-proven |

---

## E. Pillar and Score-Input Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Active Aurora score input is `pillar_sum` | `apps/reference/domains/decision_making/aurora_decision.py` | kernel call build | Feature payload passed to quadratic kernel with `pillar_sum` path | runtime-proven |
| FE computes pillars independently of `macro_resid` | `apps/reference/domains/feature_engineering/calculation_engine.py` | `compute_pillars()` | Pillar sum aggregates tactician/operator/strategist only | runtime-proven |
| Quadratic kernel defers when `pillar_sum` is missing | `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | `compute()` | `PILLAR_WARMUP` defer path | runtime-proven |
| Integration tests prove pillar-to-kernel path | `tests/integration/test_pillars_quadratic_pipeline.py` | end-to-end test | Basis bar carries `pillar_sum` into quadratic decision pipeline | test-proven |

---

## F. BTC / Anchor / Macro Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Market data emits `EVT:ANCHOR_UPDATED` | `apps/reference/domains/market_data/market_data_connector.py` and `proxy.py` | anchor emit blocks | Connector and proxy publish anchor updates | runtime-proven |
| FE subscribes to anchor updates | `apps/reference/domains/feature_engineering/feature_engineering.py` | listener wiring | Listener registered for `EVT:ANCHOR_UPDATED` | runtime-proven |
| FE requires exchange-derived anchor timestamps | `apps/reference/domains/feature_engineering/feature_engineering.py` | `update_anchor_price()` and `_on_anchor_updated_event()` | Wallclock fallback forbidden for anchor timestamps | runtime-proven |
| Anchor timestamp propagation is tested | `tests/domains/market_data/test_task30_anchor_ts_propagation.py` | propagation test | Proxy preserves `ts_ms`; FE rejects missing timestamps | test-proven |
| FE macro-sync path is active | `apps/reference/domains/feature_engineering/feature_engineering.py` and `macro_sync_resampler.py` | macro-sync compute path | FE updates resampler and computes macro-sync value | runtime-proven |
| FE macro-sync config is in `domains.yaml` | `config/aurora/domains.yaml` | `feature_engineering.macro_sync` block | Active config surface for anchors, TTL, bins, alignment | config + runtime-proven |
| No live decision-making consumer of `macro_sync` was proven | repo-wide trace | DM / strategy runtime search | No current DM consumer found in traced active path | runtime-negative / UNPROVEN elsewhere |
| FE macro-resid path is active | `apps/reference/domains/feature_engineering/calculation_engine.py` | `update_macro_resid()`, `compute_macro_resid()` | Signed anchor-relative residual is computed and sanitized | runtime-proven |
| Current non-BTC `macro_resid` path is effectively BTC-led | `apps/reference/domains/feature_engineering/feature_engineering.py` | macro-resid update block | Non-BTC symbols query BTC anchor price history explicitly | runtime-proven |
| Aurora `anchor_shock_veto` uses `macro_resid` | `apps/reference/domains/decision_making/aurora_decision.py` | veto block | Blocks BUY on non-anchor symbols when residual < threshold | runtime-proven |

---

## G. Assignment / Opt-In Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Strategy assignment SSOT lives in `strategies.yaml` | `config/aurora/strategies.yaml` | assignments block | Symbol-to-strategy ownership list | config-only + runtime-consumed |
| Runtime starts only assigned strategies | `apps/reference/domains/strategies/registry.py` | assignment usage | Assigned strategy set drives startup | runtime-proven |
| Arbitration blocks unassigned strategy access | `apps/reference/domains/decision_making/config_resolver.py` | `check_strategy_arbitration()` | Fail-closed on missing or unauthorized assignment | runtime-proven |
| Aurora enabled-symbol set is assignment-first | `apps/reference/domains/decision_making/aurora_handler.py` | `_is_symbol_enabled()` | Registry overrides legacy asset map | runtime-proven |
| Per-symbol `allowed_regimes` is active | `apps/reference/domains/decision_making/aurora_decision.py` | regime allowlist gate | Local per-symbol policy is enforced | runtime-proven |

---

## H. Observability Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| Safety denies emit regime-aware trace | `apps/reference/domains/decision_making/decision_making.py` | `_handle_safety_deny()` | Emits `EVT:DECISION_TRACE_EMITTED` with regime and confidence | runtime-proven |
| Aurora emits score trace | `apps/reference/domains/decision_making/aurora_decision.py` | quadratic trace emit block | `EVT:QUADRATIC_DECISION_TRACE` includes regime, thresholds, shield state | runtime-proven |
| Strategy signal includes regime context | `apps/reference/domains/decision_making/aurora_decision.py` | signal payload build | `regime_ctx` attached to `EVT:STRATEGY_SIGNAL_PRODUCED` | runtime-proven |
| Aurora ordinary no-trade denials emit structured blocked events | `apps/reference/domains/decision_making/aurora_handler.py` | `_emit_strategy_blocked()` | Emits `EVT:STRATEGY_DECISION_BLOCKED` | runtime-proven |
| Blocked decision schemas support reason chains and details | `apps/reference/domains/decision_making/schemas/decision_blocked_v1.json` and `schemas/str_decision_blocked_v1.json` | schema definitions | Rich structured deny payloads exist | runtime-proven |
| Registry documents regime and anchor events | `apps/reference/dictionaries/verb_registry_v1.yaml` | verb entries | Verbs present for detector, features, blocked events, anchor updates | runtime-proven |

---

## I. Doc Drift / Supportive Passport Evidence

| Claim | File path | Function / block | Evidence summary | Classification |
|---|---|---|---|---|
| `regime_passport.md` correctly states `liveness_factor` lives in decision-making | `config/docs/regime_passport.md` | `liveness_factor` section | Matches traced AuroraHandler liveness ownership | doc-only but aligned |
| `aurora_math_passport.md` correctly marks linear v2 as removed and quadratic as sole live path | `config/docs/aurora_math_passport.md` | audit summary | Matches traced runtime | doc-only but aligned |
| `trading_passport.md` correctly warns that `trading.market_data.macro_sync` is legacy or has no runtime consumer outside FE | `config/docs/trading_passport.md` | audit summary | Matches traced runtime reading | doc-only but aligned |
| Some old Aurora documentation still references removed linear surfaces | `config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md` | older scoring references | Use with caution; do not treat as runtime truth | doc-only / drift risk |

---

## J. Explicit UNPROVEN Items

| Item | Why unproven |
|---|---|
| Any live direct decision consumer of `features["macro_sync"]` | No active DM / strategy consumer was found in traced runtime modules |
| Any current producer of global execution regime events | Contract exists, but no producer was traced in the audited path |
| Any external consumer depending on current raw detector internals | Outside traced runtime surfaces |
| Any repo-root `domain_dict.json` SSOT | Only per-domain `domain_dict.json` files were present |
