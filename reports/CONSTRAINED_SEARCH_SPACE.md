# CONSTRAINED SEARCH SPACE

## Search Label

- Primary reference surface remains: MARCH / SIDE B / DEGRADED PARTIAL-UNIVERSE.
- Practical execution proxy required for search planning: ETH-dominant March research surface.

## Why a Proxy Was Needed

Two computational facts were measured directly:

1. Full March side B baseline runtime is roughly one hour per run.
2. ETH-only proxy is invalid because it collapses to zero trades due to macro-resid readiness failure when BTC anchor context is removed.
3. Minimal honest ETH+BTC proxy is valid, but still costs about `1405s` per run.

Therefore PKG-4 search had to be constrained to a tiny, explicit parameter set.

## Hard Search Budget

- Maximum search parameters: `10`
- Family A: `5`
- Family B: `5`

## Family A — Regime / Context Controls

| Param | Code owner | YAML path | Current default | Allowed range / options | Why included |
| --- | --- | --- | --- | --- | --- |
| A1 | AuroraDecisionMixin | `strategies.aurora.assets.ETHUSDT.allowed_regimes` | `['TREND_DOWN','FLAT_LOW','FLAT_NORMAL','MEAN_REVERSION']` | baseline set vs v1 set without `TREND_DOWN` | Directly tests whether March edge is mainly participation/context |
| A2 | AuroraDecisionMixin | `strategies.aurora.assets.ETHUSDT.signal_threshold.value` | `0.008` | `0.006` .. `0.010` | March ETH may be too permissive or too strict around marginal entries |
| A3 | AuroraHoldingPeriodMixin | `strategies.aurora.assets.ETHUSDT.reentry_cooldown_sec` | `120` | `60` .. `240` | Tests churn suppression without inventing new gates |
| A4 | AuroraHoldingPeriodMixin | `strategies.aurora.assets.ETHUSDT.holding_period.min_duration_sec` | `45` | `30` .. `75` | Tests whether too-fast flip/exit behavior hurts March quality |
| A5 | AuroraTpslMixin | `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.MEAN_REVERSION` | `0.80` | `0.70` .. `0.95` | MEAN_REVERSION is the surviving positive ETH slice; small refinement here is defensible |

## Family B — Scoring / Threshold / Weight Controls

| Param | Code owner | YAML path | Current default | Allowed range | Why included |
| --- | --- | --- | --- | --- | --- |
| B1 | QuadraticScoringKernel | `strategies.aurora.decision.score_multiplier` | `1.0` | `0.85` .. `1.15` | Direct quadratic sensitivity lever, code-backed and active |
| B2 | AuroraScoringHelpersMixin | `strategies.aurora.assets.ETHUSDT.weights.macro_resid` | `0.25` | `0.15` .. `0.35` | Macro residual is structurally important for ETH regime context |
| B3 | AuroraScoringHelpersMixin | `strategies.aurora.assets.ETHUSDT.weights.depth_imbalance` | `-0.256` | `-0.35` .. `-0.15` | Strong directional microstructure weight; likely to affect wrong-side entries |
| B4 | AuroraScoringHelpersMixin | `strategies.aurora.assets.ETHUSDT.weights.ema_bias` | `0.20` | `0.10` .. `0.30` | Trend/mean pivot weight, plausible contributor to March behavior |
| B5 | AuroraScoringHelpersMixin | `strategies.aurora.assets.ETHUSDT.weights.delta_price` | `0.10` | `0.05` .. `0.20` | Direct price-motion influence on score; narrow range only |

## Explicit Exclusions

The following were intentionally excluded:

- broad all-symbol weight search
- 30+ parameter searches
- unrelated domains
- parameters whose runtime impact is ambiguous on the current surface
- any entry-phase / green-bounce gate, because no config-only hook exists
- `trading.symbols_to_track` overlay search, because current strict config rejects that path in `SelectiveOptimizer`

## Search Hypothesis Framing

- If Family A dominates, March is mostly a participation/context problem.
- If Family B dominates while preserving current regime surface, March is mostly a scoring/weight quality problem.
- If only `v1 + tiny B-subset` works, then March is a mixed problem.