# REGIME_AND_BTC_CONTEXT_ACTIVE_LEGACY_LEDGER

| Surface name | Owner | Status | Why classification is justified |
|---|---|---|---|
| Structural regime detector | `regime_detector` | ACTIVE | Produces live `EVT:REGIME_DETECTED` from basis-bar feature events |
| `basis_tf_sec` | `regime_detector` / Aurora liveness | ACTIVE | Detector filters on it; Aurora liveness window uses it |
| `uncertain_cutoff` | `regime_detector` | ACTIVE | Weak non-uncertain outputs are demoted at runtime |
| `hysteresis_bars` | `regime_detector` | ACTIVE | Stable regime emission depends on it |
| Volatility slope gate | `regime_detector` | ACTIVE | Can reject high-volatility storm continuation and emit `storm_rejected` |
| Mean reversion branch | `regime_detector` | ACTIVE | Live classification branch after volatility |
| SMA trend branch | `regime_detector` | ACTIVE | Live fallback branch after volatility and MR |
| Explicit lifecycle phases | no owner | UNPROVEN / ABSENT | No onset/mature/peak/fade model or field was traced |
| Detector `raw_regime` vs stable `regime` | `regime_detector` | ACTIVE | Both fields emitted live |
| Aurora regime inertia / effective regime | `decision_making` | ACTIVE | Separate anti-churn layer in AuroraHandler |
| Regime liveness guard | `decision_making` | ACTIVE | Blocks on missing/stale heartbeat |
| Regime allowlist (`allowed_regimes`) | strategy-local Aurora / MR | ACTIVE | Live deny gates depend on it |
| `blocked_regimes` | Aurora | ACTIVE | Live hard deny in Aurora decision path |
| Regime threshold multipliers | Aurora | ACTIVE | Kernel widens threshold by regime |
| `decision.regime_thresholds` | typed config | DECLARED-BUT-NOT-USED | Present in config model/passport, not used in live threshold routing |
| Quadratic kernel | Aurora decision | ACTIVE | Sole active scoring path |
| Linear v2 kernel | historical Aurora | LEGACY / REMOVED | Passport and repo shape confirm removal |
| `signal_weights` as quadratic input | Aurora config | LEGACY | Kernel accepts for compatibility only |
| `feature_neutrals` as quadratic input | Aurora config | LEGACY | Kernel accepts for compatibility only |
| `direction_strength_scoring` as quadratic input | Aurora config | LEGACY | Quadratic path skips it |
| `regime_smoother` in quadratic kernel | Aurora config | DECLARED-BUT-NOT-USED | Passed through, not read by kernel |
| `pillar_sum` | feature_engineering -> Aurora | ACTIVE | Live conviction input for quadratic kernel |
| `pillar_tactician/operator/strategist` | feature_engineering | ACTIVE | Live inputs to `pillar_sum` |
| `macro_sync` computation inside FE | feature_engineering | ACTIVE | FE computes and emits it |
| `macro_sync` as live decision input | decision-making / strategies | UNPROVEN | No live consumer found in audited runtime path |
| `macro_resid` computation | feature_engineering | ACTIVE | Live FE feature with runtime tests/wiring |
| BTC-led `macro_resid` for non-BTC symbols | feature_engineering | ACTIVE | FE macro_resid path explicitly queries BTC anchor history |
| `EVT:ANCHOR_UPDATED` | market_data | ACTIVE | Emitted by connector/proxy and consumed by FE |
| Anchor timestamp freshness chain | market_data + FE | ACTIVE | FE rejects malformed/missing exchange `ts_ms` |
| `anchor_shock_veto` | Aurora decision | ACTIVE | Live blocker using `macro_resid` |
| BTC regime mutation of alt symbols | no owner | UNPROVEN / ABSENT | No traced path overwrites local structural regime with BTC regime |
| Global execution regime contract | contracts / execution_position | ACTIVE CONTRACT, UNPROVEN CURRENT PRODUCER | Contract and tests exist, but current structural detector does not emit that shape |
| Forced close on regime flip | decision_making | ACTIVE | Intent emitter closes on incompatible structural regime flips |
| Assignment-first activation | strategies / decision_making | ACTIVE | Registry and arbitration fail closed |
| Symbol-level opt-in boundary | strategies / decision policy | ACTIVE CAPABILITY | Current architecture already supports per-symbol enablement and per-symbol overrides |
