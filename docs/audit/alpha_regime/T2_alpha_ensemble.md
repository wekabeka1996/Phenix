## Models (per-file summary)

| component | file:line | description | STATUS |
| --- | --- | --- | --- |
| `AlphaModel` / `AlphaScore` contract | `apps/reference/domains/alpha_search/alpha_model.py:20-170` | Defines `AlphaScore` (score in [-1,1], confidence in [0,1], features_used/why) and the registry that instantiates models before `calculate_all_alpha` emits `EVT:ALPHA_SCORE_CALCULATED`. | IMPLEMENTED_ACTIVE |
| `MomentumAlphaModel` | `apps/reference/domains/alpha_search/models/momentum.py:25-140` | Weighted combination of `price_momentum_5m/1h/1d`, `volume_momentum_5m`, `RSI14`, and `MACD signal` into a single `AlphaScore` plus confidence; confidence is clamped by RSI/MACD agreement and volume multiplier. | IMPLEMENTED_ACTIVE |
| `MeanReversionAlphaModel` | `apps/reference/domains/alpha_search/models/mean_reversion.py:27-150` | Uses `bb_position`, `bb_width`, `RSI14`, SMA deviation (20), `volume_sma_ratio`, and `stochastic %K/%D` to build reversion signals and a normalized `AlphaScore` with `confidence` and `why` chain. | IMPLEMENTED_ACTIVE |
| `VolatilityAlphaModel` | `apps/reference/domains/alpha_search/models/volatility.py:31-150` | Monitors `ATR14`, `ATR ratio`, `BB width/width change`, realized volatility (1h/1d), `volume_volatility_ratio`, and range ratio to emit a volatility-driven `AlphaScore` and confidence trace. | IMPLEMENTED_ACTIVE |

## Ensemble logic

| component | file:line | description | STATUS |
| --- | --- | --- | --- |
| `EnsembleModel.generate_signal` | `apps/reference/domains/alpha_search/ensemble.py:125-220` | Calls every registered model with the latest features, filters by confidence (min 0.1), and builds a weighted `AlphaScore` that reports combined score/confidence, per-model contributions, and why-chain aggregation. | IMPLEMENTED_ACTIVE |
| `EnsembleModel._combine_scores` | `apps/reference/domains/alpha_search/ensemble.py:201-241` | Normalizes per-model scores using normalized weights, sums contributions into final `AlphaScore`, and keeps feature/why union for transparency. | IMPLEMENTED_ACTIVE |
| `EnsembleModel._rebalance_weights` | `apps/reference/domains/alpha_search/ensemble.py:273-334` | Recomputes weights when the rebalance window elapses; uses stored `self.model_performance` (confidence history) to compute means, applies optional risk-adjustment (variance penalty), clamps to `min_weight/max_weight`, and renormalizes. | IMPLEMENTED_ACTIVE |

## Performance-based weighting (is it real?)

| component | file:line | description | STATUS |
| --- | --- | --- | --- |
| Confidence history cache | `apps/reference/domains/alpha_search/ensemble.py:243-265` | `self.model_performance` retains the last ~100 confidence values per model (plus `ensemble_performance`); only this proxy is persisted, no PnL/Sharpe inputs. | IMPLEMENTED_ACTIVE |
| `_rebalance_weights` | `apps/reference/domains/alpha_search/ensemble.py:269-334` | Mean of the cached confidences drives new weights, optionally penalizes variance (`risk_adjustment` block), clamps via `min_weight/max_weight`, and renormalizes; no actual profit data is referenced. | IMPLEMENTED_ACTIVE |
| `EnsembleWeights` metadata | `apps/reference/domains/alpha_search/ensemble.py:20-35` | Tracks normalized `model_weights`, `performance_score`, and `last_updated` so consumers see the current mix even though the history is only confidences. | IMPLEMENTED_ACTIVE |

## Integration points (events/calls)

| component | file:line | description | STATUS |
| --- | --- | --- | --- |
| `DecisionMaking.on_features` | `apps/reference/domains/decision_making/decision_making.py:659-749` | Upon `EVT:FEATURES_CALCULATED`, stores features, calls `AlphaModelRegistry.calculate_all_alpha`, emits `EVT:ALPHA_SCORE_CALCULATED`, logs to WAL (`wal.append`), and defers/completes decisions depending on risk/portfolio state. | IMPLEMENTED_ACTIVE |
| DecisionMaking alpha registry | `apps/reference/domains/decision_making/decision_making.py:122-135` | Instantiates `AlphaModelRegistry`, registers `Momentum/MeanReversion/Volatility` models, and exposes them to the runtime; the registry is therefore invoked each feature tick. | IMPLEMENTED_ACTIVE |
| `AlphaModelRegistry.calculate_all_alpha` | `apps/reference/domains/alpha_search/alpha_model.py:143-169` | Iterates through ready models, catches exceptions, and returns matching `AlphaScore`s. The emit path is triggered by DecisionMaking in the live FSM. | IMPLEMENTED_ACTIVE |
| event wiring | `apps/reference/domains/alpha_search/EVENTS.md` + decision_making | Only `EVT:ALPHA_SCORE_CALCULATED` exists (no `EVT:ALPHA_SIGNAL`/`EVT:ALPHA_EVAL_COMPLETED` in docs or code); it carries the ensembled score, `timestamp`, and contributions that DecisionMaking consumes. | IMPLEMENTED_ACTIVE |
| Feature inputs | `apps/reference/domains/feature_engineering/EVENTS.md` and `feature_engineering.py` | FeatureEngineering feeds `EVT:FEATURES_CALCULATED`; alpha models and DecisionMaking are downstream listeners as schematized in the docs. | IMPLEMENTED_ACTIVE |
